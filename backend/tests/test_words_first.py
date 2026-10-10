"""Nauka zaczyna od słów, a dłuższe zwroty czekają odłożone.

Zwroty jako pierwszy materiał okazały się za trudne: zdanie z pięciu słów to
pięć słów naraz. Przy nastawieniu na słowa zwroty dłuższe niż trzy słowa
schodzą z kolejki — nie przychodzą jako nowe i nie wracają w powtórkach.

Trzy rzeczy są tu ważniejsze od samego filtra: nic nie jest kasowane, każdy
licznik mówi to samo co sesja, a powrót do zwrotów przywraca karty tam, gdzie
były.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Deck, DeckItem, Item, User, UserItemState
from app.services import task_builder as tb


@pytest.fixture
def user(db, registered) -> User:
    return db.get(User, registered["user"]["id"])


def _deck(db, entries: list[tuple[str, str]]) -> list[Item]:
    deck = Deck(slug="slowa-i-zwroty", name="Słowa i zwroty", position=1, is_shared=True)
    db.add(deck)
    db.flush()
    items = []
    for position, (pt, kind) in enumerate(entries):
        item = Item(pt=pt, pl=f"pl {pt}", type=kind, cefr_level="A1", source="seed", verified=True)
        db.add(item)
        db.flush()
        db.add(DeckItem(deck_id=deck.id, item_id=item.id, position=position))
        items.append(item)
    db.commit()
    return items


ENTRIES = [
    ("é só isto, obrigado", "phrase"),      # 4 słowa — odłożony
    ("casa", "word"),
    ("quanto custa?", "phrase"),            # 2 słowa — zostaje
    ("queria isto, se faz favor", "phrase"),  # 5 słów — odłożony
    ("chamo-me Ana", "phrase"),             # 2 słowa: myślnik nie dzieli
    ("livro", "word"),
]


def _review_all(db, user, items):
    # Poniżej progu odblokowania drugiego kierunku: budowa sesji nie dokłada
    # wtedy kart PL→PT i liczby sprawdzają sam filtr, a nie tamten mechanizm.
    past = datetime.now(timezone.utc) - timedelta(days=1)
    for item in items:
        db.add(UserItemState(user_id=user.id, item_id=item.id, direction="recognition",
                             state="review", due=past, stability=5.0, difficulty=5.0,
                             reps=1, correct_reps=1))
    db.commit()


def test_long_phrases_do_not_come_as_new_material(db, user):
    _deck(db, ENTRIES)
    fresh = tb.new_items(db, user, 10, None, focus="words")
    assert {item.pt for item in fresh} == {"casa", "livro", "quanto custa?", "chamo-me Ana"}


def test_words_come_before_short_phrases(db, user):
    _deck(db, ENTRIES)
    kinds = [item.type for item in tb.new_items(db, user, 10, None, focus="words")]
    assert kinds == ["word", "word", "phrase", "phrase"]


def test_long_phrases_leave_the_reviews_too(db, user):
    items = _deck(db, ENTRIES)
    _review_all(db, user, items)
    due = tb.due_states(db, user, datetime.now(timezone.utc), 50, None)
    shown = {db.get(Item, state.item_id).pt for state in due}
    assert "queria isto, se faz favor" not in shown
    assert "é só isto, obrigado" not in shown
    assert "quanto custa?" in shown


def test_nothing_is_deleted_and_switching_back_restores_them(client, registered, db, user):
    """Odłożenie to filtr, nie kasowanie. Po przełączeniu na „po równo” karty
    wracają z całym postępem."""
    items = _deck(db, ENTRIES)
    _review_all(db, user, items)
    assert db.query(UserItemState).count() == len(ENTRIES)

    client.patch("/api/settings", json={"content_focus": "mixed"})
    db.refresh(user.settings)
    due = tb.due_states(db, user, datetime.now(timezone.utc), 50, None)
    assert len(due) == len(ENTRIES)


def test_the_counter_says_what_the_session_will_give(client, registered, db, user):
    """Licznik „powtórek na dziś” i sesja czytają ten sam warunek. Kiedy się
    rozjeżdżają, ekran obiecuje karty, których nauka potem nie pokazuje."""
    items = _deck(db, ENTRIES)
    _review_all(db, user, items)

    summary = client.get("/api/study/queue/summary").json()
    assert summary["due"] == 4
    assert summary["set_aside"] == 2

    session = client.post("/api/study/sessions", json={"new_limit": 0, "modes": ["flashcard"]}).json()
    assert session["planned_count"] == summary["due"]


def test_the_deck_list_counts_the_same_way(client, registered, db, user):
    items = _deck(db, ENTRIES)
    _review_all(db, user, items)
    decks = client.get("/api/decks").json()
    deck = next(d for d in decks if d["name"] == "Słowa i zwroty")
    assert deck["due"] == 4


def test_other_focus_settings_hide_nothing(db, user):
    _deck(db, ENTRIES)
    for focus in ("mixed", "phrases"):
        assert len(tb.new_items(db, user, 10, None, focus=focus)) == len(ENTRIES)
    assert tb.set_aside("mixed") is None
