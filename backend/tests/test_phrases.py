"""Zwroty zamiast słówek — zmiana podejścia do nauki.

Sedno jest jedno: kolejka ma podawać rzeczy, które da się powiedzieć obcej
osobie tego samego dnia. Testy pilnują, żeby to nastawienie faktycznie
docierało do sesji, a nie zostało samą deklaracją w ustawieniach.
"""

import json
import pathlib

import pytest
from sqlalchemy import select

from app.models import Deck, DeckItem, Item, User
from app.services import task_builder as tb

SEED_DIR = pathlib.Path(__file__).resolve().parents[1] / "app" / "seed"


def _mixed_deck(db, words: int = 6, phrases: int = 6):
    """Talia, w której zwroty i słowa leżą na przemian.

    Przeplot jest celowy: gdyby zwroty leżały na początku, kolejność deklowa
    załatwiłaby test sama i nie sprawdzałby niczego.
    """
    deck = Deck(slug="mieszana", name="Mieszana", position=1, is_shared=True)
    db.add(deck)
    db.flush()
    position = 0
    for index in range(max(words, phrases)):
        if index < words:
            item = Item(pt=f"palavra{index}", pl=f"slowo{index}", type="word", cefr_level="A1", source="seed")
            db.add(item)
            db.flush()
            db.add(DeckItem(deck_id=deck.id, item_id=item.id, position=position))
            position += 1
        if index < phrases:
            item = Item(
                pt=f"quanto custa isto {index}?", pl=f"ile to kosztuje {index}?",
                type="phrase", cefr_level="A1", source="seed",
            )
            db.add(item)
            db.flush()
            db.add(DeckItem(deck_id=deck.id, item_id=item.id, position=position))
            position += 1
    db.commit()
    return deck


@pytest.fixture
def user(db, registered) -> User:
    return db.get(User, registered["user"]["id"])


# ── czym karmi się kolejka ────────────────────────────────────────────────
def test_new_material_starts_with_whole_phrases(db, user):
    _mixed_deck(db)
    fresh = tb.new_items(db, user, 6, None, focus="phrases")
    assert [item.type for item in fresh] == ["phrase"] * 6


def test_words_are_not_deleted_only_queued_later(db, user):
    """Słowa zostają w bazie. Zmiana podejścia nie może kasować materiału —
    ma zmieniać kolejność, w jakiej się go poznaje."""
    _mixed_deck(db, words=6, phrases=2)
    fresh = tb.new_items(db, user, 8, None, focus="phrases")
    kinds = [item.type for item in fresh]
    assert kinds[:2] == ["phrase", "phrase"]
    assert kinds.count("word") == 6, "słowa dochodzą, gdy zwroty się skończą"


def test_focus_words_brings_back_the_old_order(db, user):
    _mixed_deck(db)
    fresh = tb.new_items(db, user, 6, None, focus="words")
    assert [item.type for item in fresh] == ["word"] * 6


def test_focus_mixed_keeps_the_deck_order(db, user):
    _mixed_deck(db)
    fresh = tb.new_items(db, user, 4, None, focus="mixed")
    assert [item.type for item in fresh] == ["word", "phrase", "word", "phrase"]


def test_setting_reaches_the_session(client, registered, db, user):
    _mixed_deck(db, words=10, phrases=10)
    session = client.post("/api/study/sessions", json={"new_limit": 5}).json()
    fronts = [task.get("front") or task.get("pt") for task in session["tasks"]]
    assert all("quanto custa" in (front or "") for front in fronts), fronts


def test_focus_can_be_changed_and_is_validated(client, registered):
    assert client.get("/api/settings").json()["content_focus"] == "phrases"
    assert client.patch("/api/settings", json={"content_focus": "words"}).status_code == 200
    assert client.get("/api/settings").json()["content_focus"] == "words"
    assert client.patch("/api/settings", json={"content_focus": "cokolwiek"}).status_code == 422


# ── jak się ćwiczy zwrot ──────────────────────────────────────────────────
def test_a_phrase_is_rebuilt_from_bricks_not_retyped(db, user):
    """Przy zwrocie uczy się szyku — „se faz favor" na końcu to też szyk."""
    from datetime import datetime, timezone

    from app.models import UserItemState

    phrase = Item(pt="queria isto se faz favor", pl="poproszę to", type="phrase",
                  cefr_level="A1", source="seed")
    db.add(phrase)
    db.commit()
    state = UserItemState(user_id=user.id, item_id=phrase.id, direction="production",
                          state="review", due=datetime.now(timezone.utc),
                          stability=40.0, difficulty=5.0)

    assert tb.supports("word_bank", phrase) is True
    assert tb.choose_mode(state, "production", ["typing", "word_bank"], phrase) == "word_bank"


def test_a_single_word_is_still_typed_not_assembled(db, user):
    from datetime import datetime, timezone

    from app.models import UserItemState

    word = Item(pt="autocarro", pl="autobus", type="word", cefr_level="A1", source="seed")
    db.add(word)
    db.commit()
    state = UserItemState(user_id=user.id, item_id=word.id, direction="production",
                          state="review", due=datetime.now(timezone.utc),
                          stability=40.0, difficulty=5.0)

    assert tb.choose_mode(state, "production", ["typing", "word_bank"], word) == "typing"


def test_the_expected_reply_travels_with_the_task(db, user):
    phrase = Item(pt="quanto custa?", pl="ile to kosztuje?", type="phrase", cefr_level="A1",
                  source="seed", reply_pt="São dois euros.", reply_pl="Dwa euro.")
    db.add(phrase)
    db.commit()

    task = tb.build_task(db, 0, phrase, "recognition", "flashcard", True, None, None, 0.9).as_dict()
    assert task["reply"] == {"pt": "São dois euros.", "pl": "Dwa euro."}


def test_a_plain_word_carries_no_reply(db, user):
    word = Item(pt="autocarro", pl="autobus", type="word", cefr_level="A1", source="seed")
    db.add(word)
    db.commit()
    task = tb.build_task(db, 0, word, "recognition", "flashcard", True, None, None, 0.9).as_dict()
    assert task["reply"] is None, "nikt nie odpowiada na rzeczownik"


# ── baza startowa ─────────────────────────────────────────────────────────
def test_situational_decks_lead_the_seed():
    """Talie sytuacyjne mają być pierwsze — to od nich zaczyna nowe konto."""
    positions = {}
    for path in sorted(SEED_DIR.glob("decks_*.json")):
        for deck in json.loads(path.read_text()):
            positions[deck["name"]] = deck["position"]

    leading = sorted(positions.items(), key=lambda entry: entry[1])[:10]
    assert all(position <= 10 for _, position in leading)
    assert "W sklepie" in dict(leading)
    assert "W restauracji" in dict(leading)


def test_the_seed_is_now_mostly_phrases():
    kinds = {"word": 0, "phrase": 0, "sentence": 0}
    for path in sorted(SEED_DIR.glob("decks_*.json")):
        for deck in json.loads(path.read_text()):
            for item in deck["items"]:
                kinds[item.get("type", "word")] += 1
    speakable = kinds["phrase"] + kinds["sentence"]
    # Słowa zostają, ale to zwroty mają być pierwszym, co widzi nowe konto.
    assert speakable >= 200, kinds


def test_situational_phrases_teach_the_reply_too():
    """Zwrot bez odpowiedzi to połowa umiejętności: „Quanto custa?" nic nie da,
    jeśli „São dois e cinquenta" odbije się od ucha."""
    with_reply = 0
    total = 0
    for name in ("decks_05_sytuacje.json", "decks_06_sytuacje2.json"):
        for deck in json.loads((SEED_DIR / name).read_text()):
            for item in deck["items"]:
                total += 1
                if item.get("reply"):
                    with_reply += 1
    assert total >= 140
    assert with_reply / total >= 0.3, f"tylko {with_reply} z {total} zwrotów ma odpowiedź"


def test_no_brazilian_words_slipped_into_the_new_decks():
    banned = ("ônibus", "trem ", "celular", "banheiro", "café da manhã", "suco",
              "sorvete", "xícara", "você", "estou fazendo", "estou comendo")
    offenders = []
    for name in ("decks_05_sytuacje.json", "decks_06_sytuacje2.json"):
        for deck in json.loads((SEED_DIR / name).read_text()):
            for item in deck["items"]:
                haystack = " ".join(
                    filter(None, [item["pt"], (item.get("reply") or [None])[0]])
                ).lower()
                offenders += [(item["pt"], word) for word in banned if word in haystack]
    assert offenders == []


def test_every_new_phrase_has_a_polish_translation():
    for name in ("decks_05_sytuacje.json", "decks_06_sytuacje2.json"):
        for deck in json.loads((SEED_DIR / name).read_text()):
            for item in deck["items"]:
                assert item["pt"].strip() and item["pl"].strip(), item
                reply = item.get("reply")
                if reply is not None:
                    assert len(reply) == 2 and all(part.strip() for part in reply), item
