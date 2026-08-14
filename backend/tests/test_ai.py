"""Faza 4 — generowanie zestawów, pomoc przy błędach, koszty.

Prawdziwy model nie jest tu wołany ani razu. Testowany jest nie on, tylko
wszystko dookoła: czy koszt trafia do księgi, czy limit zatrzymuje wydawanie,
czy odpowiedź da się dostać z pamięci podręcznej zamiast z API i — przede
wszystkim — czy propozycja może wejść do słownika bez akceptacji człowieka.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.config import settings
from app.models import AiCacheEntry, AiJob, Deck, DeckItem, Example, Item, Review, User, UserItemState
from app.routers.ai import ai_rate_limit
from app.services import ai
from app.services import task_builder as tb
from tests.conftest import make_items


def _payload(**overrides) -> dict:
    base = {
        "pt": "autocarro",
        "pl": "autobus",
        "type": "word",
        "part_of_speech": "noun",
        "article": "o",
        "gender": "m",
        "plural": None,
        "cefr_level": "A1",
        "notes": None,
        "example_pt": "O autocarro está atrasado.",
        "example_pl": "Autobus jest spóźniony.",
    }
    base.update(overrides)
    return base


class FakeEngine:
    """Zamiast Anthropic. Oddaje przygotowane odpowiedzi po kolei i liczy,
    ile razy ktoś po nie sięgnął — bo najważniejsze w tym module jest to, ile
    razy się *nie* zapłaciło."""

    name = "fake"

    def __init__(self, *responses, tokens=(1000, 500), fail: Exception | None = None) -> None:
        self.responses = list(responses)
        self.tokens = tokens
        self.fail = fail
        self.calls: list[dict] = []

    def complete(self, *, system, prompt, schema, effort, max_tokens):
        self.calls.append({"system": system, "prompt": prompt, "effort": effort})
        if self.fail:
            raise self.fail
        data = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return ai.Completion(
            data=data,
            input_tokens=self.tokens[0],
            output_tokens=self.tokens[1],
            model="claude-opus-5",
        )


def a_set(*items, deck_name="U lekarza") -> dict:
    return {"deck_name": deck_name, "items": list(items) or [_payload()]}


@pytest.fixture
def user(db, registered) -> User:
    return db.get(User, registered["user"]["id"])


@pytest.fixture(autouse=True)
def budget(monkeypatch):
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", 5.0)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    ai_rate_limit.reset()
    yield


# ── koszt ─────────────────────────────────────────────────────────────────
def test_cost_uses_the_model_price_list():
    # 1M wejścia + 1M wyjścia po cenniku Opus 5 = 5 + 25 dolarów.
    assert ai.cost_of("claude-opus-5", 1_000_000, 1_000_000) == Decimal("30.000000")


def test_unknown_model_is_priced_high_not_free():
    """Cennik, którego nie znamy, liczymy najdrożej — pomyłka ma zatrzymywać
    wydawanie za wcześnie, nie za późno."""
    known = ai.cost_of("claude-opus-5", 1_000_000, 1_000_000)
    assert ai.cost_of("model-z-przyszlosci", 1_000_000, 1_000_000) > known


def test_every_call_lands_in_the_ledger(db, user):
    engine = FakeEngine(a_set())
    ai.generate_set(db, user, topic="u lekarza", count=1, level="A1", engine=engine)

    job = db.query(AiJob).one()
    assert job.kind == "set"
    assert job.status == "ready"
    assert (job.input_tokens, job.output_tokens) == (1000, 500)
    assert job.cost_usd == ai.cost_of("claude-opus-5", 1000, 500)


def test_failed_call_is_logged_too(db, user):
    """Nieudane wywołanie też kosztowało tokeny wejściowe — pominięcie go w
    księdze zaniżałoby rachunek."""
    engine = FakeEngine(a_set(), fail=ai.AIError("padło"))
    with pytest.raises(ai.AIError):
        ai.generate_set(db, user, topic="u lekarza", count=1, level="A1", engine=engine)

    job = db.query(AiJob).one()
    assert job.status == "failed"
    assert "padło" in job.error


def test_spend_counts_only_this_month(db, user):
    old = AiJob(user_id=user.id, kind="set", model="claude-opus-5", cost_usd=Decimal("4.00"))
    db.add(old)
    db.flush()
    old.created_at = datetime.now(timezone.utc) - timedelta(days=45)
    db.add(AiJob(user_id=user.id, kind="set", model="claude-opus-5", cost_usd=Decimal("0.50")))
    db.commit()

    assert ai.spend_this_month(db) == Decimal("0.50")


def test_budget_stops_the_next_call(db, user, monkeypatch):
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", 0.10)
    db.add(AiJob(user_id=user.id, kind="set", model="claude-opus-5", cost_usd=Decimal("0.10")))
    db.commit()

    engine = FakeEngine(a_set())
    with pytest.raises(ai.AIBudgetReached):
        ai.generate_set(db, user, topic="u lekarza", count=1, level="A1", engine=engine)
    assert engine.calls == [], "po wyczerpaniu budżetu nie wolno nawet zapytać"


def test_missing_key_is_configuration_not_failure(db, user, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert ai.is_configured() is False
    with pytest.raises(ai.AINotConfigured):
        ai.generate_set(db, user, topic="u lekarza", count=1, level="A1")


# ── prompt ────────────────────────────────────────────────────────────────
def test_prompt_names_the_forbidden_words(db, user):
    engine = FakeEngine(a_set())
    ai.generate_set(db, user, topic="transport", count=1, level="A1", engine=engine)

    system = engine.calls[0]["system"]
    # „Pisz po europejsku" model traktuje jak sugestię; konkretną parę słów
    # jak regułę. Te dwie różnią się całkowicie, nie akcentem.
    assert "ônibus" in system and "autocarro" in system
    assert "telemóvel" in system
    assert "estar a + bezokolicznik" in system


def test_prompt_carries_topic_level_and_count(db, user):
    engine = FakeEngine(a_set())
    ai.generate_set(db, user, topic="u lekarza", count=12, level="B1", engine=engine)

    prompt = engine.calls[0]["prompt"]
    assert "u lekarza" in prompt and "12" in prompt and "B1" in prompt


def test_known_words_are_sent_so_the_second_set_is_new(db, user, client):
    engine = FakeEngine(a_set(_payload(pt="consulta", pl="wizyta")))
    ai.generate_set(
        db, user, topic="u lekarza", count=5, level="A1", engine=engine, avoid=["consulta"]
    )
    assert "consulta" in engine.calls[0]["prompt"]


# ── walidacja i próba naprawcza ───────────────────────────────────────────
def test_noun_without_article_triggers_one_repair_attempt(db, user):
    broken = a_set(_payload(article=None, gender=None))
    engine = FakeEngine(broken, a_set())
    ai.generate_set(db, user, topic="u lekarza", count=1, level="A1", engine=engine)

    assert len(engine.calls) == 2, "jedna próba naprawcza, nie zero i nie dwie"
    assert "rodzajnika" in engine.calls[1]["prompt"]


def test_second_failure_gives_up_instead_of_looping(db, user):
    broken = a_set(_payload(article=None, gender=None))
    engine = FakeEngine(broken, broken)
    with pytest.raises(ai.AIError):
        ai.generate_set(db, user, topic="u lekarza", count=1, level="A1", engine=engine)

    assert len(engine.calls) == 2
    assert db.query(AiJob).count() == 2
    assert {job.status for job in db.query(AiJob).all()} == {"failed"}


def test_duplicate_entries_inside_one_set_are_rejected(db, user):
    twice = a_set(_payload(), _payload())
    engine = FakeEngine(twice, a_set())
    ai.generate_set(db, user, topic="u lekarza", count=2, level="A1", engine=engine)
    assert len(engine.calls) == 2


def test_refusal_is_its_own_error(db, user):
    engine = FakeEngine(a_set(), fail=ai.AIRefused("nie tym razem"))
    with pytest.raises(ai.AIRefused):
        ai.generate_set(db, user, topic="cokolwiek", count=1, level="A1", engine=engine)


# ── pamięć podręczna ──────────────────────────────────────────────────────
def test_the_same_mistake_is_explained_once(db, user):
    _, items = make_items(db, count=1)
    engine = FakeEngine({"verdict": "brazylijski", "explanation": "To wersja z Brazylii."})

    first, cached_first = ai.explain_mistake(
        db, user, item=items[0], user_answer="ônibus", expected="autocarro", engine=engine
    )
    second, cached_second = ai.explain_mistake(
        db, user, item=items[0], user_answer="ônibus", expected="autocarro", engine=engine
    )

    assert first == second
    assert (cached_first, cached_second) == (False, True)
    assert len(engine.calls) == 1, "druga pomyłka tej samej treści nie może kosztować"
    assert db.query(AiCacheEntry).count() == 1


def test_a_different_mistake_is_a_different_question(db, user):
    _, items = make_items(db, count=1)
    engine = FakeEngine({"verdict": "ortografia", "explanation": "Literówka."})
    ai.explain_mistake(db, user, item=items[0], user_answer="avo", expected="avó", engine=engine)
    ai.explain_mistake(db, user, item=items[0], user_answer="avô", expected="avó", engine=engine)
    assert len(engine.calls) == 2


def test_grading_is_cached_per_answer(db, user):
    engine = FakeEngine({"score": 80, "corrected": "Estou a comer.", "feedback": "Prawie."})
    for _ in range(3):
        ai.grade_translation(
            db,
            user,
            prompt_pl="Jem.",
            expected_pt="Estou a comer.",
            user_answer="Estou comendo.",
            engine=engine,
        )
    assert len(engine.calls) == 1


# ── API: generowanie i przegląd ───────────────────────────────────────────
def test_generate_returns_proposals_without_touching_the_dictionary(client, db, user, monkeypatch):
    engine = FakeEngine(a_set(_payload(), _payload(pt="consulta", pl="wizyta", gender="f", article="a")))
    monkeypatch.setattr(ai, "get_engine", lambda: engine)

    response = client.post("/api/ai/generate", json={"topic": "u lekarza", "count": 2, "level": "A1"})
    assert response.status_code == 200, response.text
    body = response.json()

    assert len(body["proposals"]) == 2
    assert body["cost_usd"] > 0
    assert db.query(Item).count() == 0, "propozycja nie jest jeszcze pozycją do nauki"


def test_generate_drops_words_already_in_the_dictionary(client, db, user, monkeypatch):
    db.add(Item(pt="autocarro", pl="autobus", type="word", cefr_level="A1", source="seed"))
    db.commit()
    engine = FakeEngine(a_set(_payload(), _payload(pt="consulta", pl="wizyta", article="a", gender="f")))
    monkeypatch.setattr(ai, "get_engine", lambda: engine)

    body = client.post("/api/ai/generate", json={"topic": "u lekarza", "count": 2}).json()
    assert body["skipped_duplicates"] == 1
    assert [p["pt"] for p in body["proposals"]] == ["consulta"]


def test_article_written_into_the_word_is_not_doubled(client, db, user, monkeypatch):
    engine = FakeEngine(a_set(_payload(pt="o autocarro")))
    monkeypatch.setattr(ai, "get_engine", lambda: engine)

    body = client.post("/api/ai/generate", json={"topic": "transport", "count": 1}).json()
    assert body["proposals"][0]["pt"] == "autocarro"
    assert body["proposals"][0]["article"] == "o"


def test_review_survives_a_refresh(client, db, user, monkeypatch):
    engine = FakeEngine(a_set())
    monkeypatch.setattr(ai, "get_engine", lambda: engine)
    job_id = client.post("/api/ai/generate", json={"topic": "u lekarza", "count": 1}).json()["job_id"]

    again = client.get(f"/api/ai/jobs/{job_id}")
    assert again.status_code == 200
    assert again.json()["proposals"][0]["pt"] == "autocarro"


def test_only_the_selected_items_become_words(client, db, user, monkeypatch):
    engine = FakeEngine(a_set(_payload(), _payload(pt="consulta", pl="wizyta", article="a", gender="f")))
    monkeypatch.setattr(ai, "get_engine", lambda: engine)
    generated = client.post("/api/ai/generate", json={"topic": "u lekarza", "count": 2}).json()

    chosen = [generated["proposals"][0]]
    response = client.post(
        f"/api/ai/jobs/{generated['job_id']}/accept",
        json={"deck_name": "U lekarza", "items": chosen},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 1

    words = db.query(Item).all()
    assert [w.pt for w in words] == ["autocarro"]
    assert words[0].source == "ai" and words[0].verified is True
    assert words[0].article == "o"


def test_accepted_items_are_edited_the_way_the_reviewer_left_them(client, db, user, monkeypatch):
    engine = FakeEngine(a_set())
    monkeypatch.setattr(ai, "get_engine", lambda: engine)
    generated = client.post("/api/ai/generate", json={"topic": "transport", "count": 1}).json()

    corrected = dict(generated["proposals"][0])
    corrected["pl"] = "autobus miejski"
    corrected["notes"] = "poprawione ręcznie"
    client.post(
        f"/api/ai/jobs/{generated['job_id']}/accept",
        json={"deck_name": "Transport", "items": [corrected]},
    )

    item = db.query(Item).one()
    assert item.pl == "autobus miejski"
    assert item.notes == "poprawione ręcznie"


def test_accepted_set_lands_in_a_deck_so_it_reaches_the_queue(client, db, user, monkeypatch):
    """Pozycja poza talią istnieje w słowniku, ale nigdy nie trafi do sesji —
    kolejka dobiera nowe słowa przez talie."""
    engine = FakeEngine(a_set())
    monkeypatch.setattr(ai, "get_engine", lambda: engine)
    generated = client.post("/api/ai/generate", json={"topic": "transport", "count": 1}).json()
    client.post(
        f"/api/ai/jobs/{generated['job_id']}/accept",
        json={"deck_name": "Transport", "items": generated["proposals"]},
    )

    deck = db.query(Deck).filter(Deck.name == "Transport").one()
    assert deck.owner_id == user.id and deck.is_shared is False
    assert db.query(DeckItem).filter(DeckItem.deck_id == deck.id).count() == 1


def test_example_sentence_comes_along(client, db, user, monkeypatch):
    engine = FakeEngine(a_set())
    monkeypatch.setattr(ai, "get_engine", lambda: engine)
    generated = client.post("/api/ai/generate", json={"topic": "transport", "count": 1}).json()
    client.post(
        f"/api/ai/jobs/{generated['job_id']}/accept",
        json={"deck_name": "Transport", "items": generated["proposals"]},
    )

    example = db.query(Example).one()
    assert example.pt == "O autocarro está atrasado."
    assert example.source == "ai"


def test_accepting_twice_does_not_duplicate_the_word(client, db, user, monkeypatch):
    engine = FakeEngine(a_set())
    monkeypatch.setattr(ai, "get_engine", lambda: engine)
    generated = client.post("/api/ai/generate", json={"topic": "transport", "count": 1}).json()
    payload = {"deck_name": "Transport", "items": generated["proposals"]}
    client.post(f"/api/ai/jobs/{generated['job_id']}/accept", json=payload)
    second = client.post(f"/api/ai/jobs/{generated['job_id']}/accept", json=payload)

    assert second.json()["skipped_duplicates"] == 1
    assert db.query(Item).count() == 1


# ── API: budżet, limity, brak klucza ──────────────────────────────────────
def test_exhausted_budget_is_429_not_500(client, db, user, monkeypatch):
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", 0.01)
    db.add(AiJob(user_id=user.id, kind="set", model="claude-opus-5", cost_usd=Decimal("1.00")))
    db.commit()

    response = client.post("/api/ai/generate", json={"topic": "u lekarza", "count": 5})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "AI_BUDGET"
    assert "budżet" in response.json()["error"]["message"].lower()


def test_no_key_says_so_instead_of_breaking(client, registered, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    response = client.post("/api/ai/generate", json={"topic": "u lekarza", "count": 5})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AI_NOT_CONFIGURED"


def test_usage_report_shows_what_is_left(client, db, user):
    db.add(AiJob(user_id=user.id, kind="set", model="claude-opus-5", cost_usd=Decimal("1.25")))
    db.commit()
    body = client.get("/api/ai/usage").json()
    assert body["spent_usd"] == pytest.approx(1.25)
    assert body["remaining_usd"] == pytest.approx(3.75)
    assert body["over_budget"] is False


def test_rate_limit_caps_the_hourly_spend(client, db, user, monkeypatch):
    engine = FakeEngine(a_set())
    monkeypatch.setattr(ai, "get_engine", lambda: engine)
    codes = [
        client.post("/api/ai/generate", json={"topic": "transport", "count": 1}).status_code
        for _ in range(21)
    ]
    assert codes[-1] == 429
    assert codes.count(200) == 20


def test_ai_endpoints_need_a_login(client):
    response = client.post(
        "/api/ai/explain", json={"item_id": str(uuid.uuid4()), "user_answer": "x"}
    )
    assert response.status_code == 401


# ── API: pomoc przy błędzie ───────────────────────────────────────────────
def test_explain_answers_in_two_sentences(client, db, user, monkeypatch):
    _, items = make_items(db, count=1)
    engine = FakeEngine({"verdict": "brazylijski", "explanation": "W Portugalii mówi się autocarro."})
    monkeypatch.setattr(ai, "get_engine", lambda: engine)

    body = client.post(
        "/api/ai/explain", json={"item_id": str(items[0].id), "user_answer": "ônibus"}
    ).json()
    assert body["verdict"] == "brazylijski"
    assert body["cached"] is False
    assert client.post(
        "/api/ai/explain", json={"item_id": str(items[0].id), "user_answer": "ônibus"}
    ).json()["cached"] is True


def test_grade_translation_uses_the_items_example(client, db, user, monkeypatch):
    _, items = make_items(db, count=1)
    engine = FakeEngine({"score": 90, "corrected": "Esta é a palavra0.", "feedback": "Dobrze."})
    monkeypatch.setattr(ai, "get_engine", lambda: engine)

    body = client.post(
        "/api/ai/grade-translation",
        json={"item_id": str(items[0].id), "user_answer": "Esta e a palavra0."},
    ).json()
    assert body["score"] == 90
    assert "palavra0" in engine.calls[0]["prompt"]


def test_generated_example_needs_accepting_too(client, db, user, monkeypatch):
    item = Item(pt="saudade", pl="tęsknota", type="word", cefr_level="B1", source="user")
    db.add(item)
    db.commit()
    engine = FakeEngine({"examples": [{"pt": "Tenho saudades tuas.", "pl": "Tęsknię za tobą."}]})
    monkeypatch.setattr(ai, "get_engine", lambda: engine)

    body = client.post("/api/ai/examples", json={"item_id": str(item.id)}).json()
    assert body["examples"][0]["pt"] == "Tenho saudades tuas."
    assert db.query(Example).count() == 0, "propozycja zdania to jeszcze nie zdanie"

    client.post(
        "/api/ai/examples/accept",
        json={"item_id": str(item.id), "pt": body["examples"][0]["pt"], "pl": body["examples"][0]["pl"]},
    )
    assert db.query(Example).count() == 1


# ── tryb „przetłumacz zdanie" ─────────────────────────────────────────────
def test_translate_mode_is_off_by_default(client, registered):
    modes = client.get("/api/settings").json()["enabled_modes"]
    assert "translate_ai" not in modes, "tryb płatny za odpowiedź nie włącza się sam"


def test_translate_mode_needs_a_key(db, monkeypatch):
    sentence = Item(pt="Estou a comer.", pl="Jem.", type="sentence", cefr_level="A2", source="seed")
    db.add(sentence)
    db.commit()

    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert tb.supports("translate_ai", sentence) is False
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    assert tb.supports("translate_ai", sentence) is True


def test_translate_mode_asks_for_the_whole_sentence(db):
    sentence = Item(pt="Estou a comer.", pl="Jem.", type="sentence", cefr_level="A2", source="seed")
    db.add(sentence)
    db.commit()

    task = tb.build_task(
        db, 0, sentence, "production", "translate_ai", False, None, None, 0.9
    ).as_dict()
    assert task["question"] == "Jem."
    assert task["expected"] == "Estou a comer."


def test_translate_mode_wins_over_word_bank_when_enabled(db, user):
    """Włączenie płatnego trybu ma być decyzją widoczną w sesji — inaczej nie
    byłoby po co go włączać."""
    sentence = Item(pt="Estou a comer.", pl="Jem.", type="sentence", cefr_level="A2", source="seed")
    db.add(sentence)
    db.commit()
    state = UserItemState(
        user_id=user.id, item_id=sentence.id, direction="production", state="review",
        due=datetime.now(timezone.utc), stability=40.0, difficulty=5.0,
    )

    without = tb.choose_mode(state, "production", ["typing", "word_bank"], sentence)
    with_it = tb.choose_mode(state, "production", ["typing", "word_bank", "translate_ai"], sentence)
    assert without == "word_bank"
    assert with_it == "translate_ai"


def test_server_records_the_models_verdict(client, db, user, monkeypatch):
    """Zdanie da się powiedzieć poprawnie na kilka sposobów, więc serwer nie
    porównuje znak po znaku — zapisuje ocenę, którą wystawił model, i to, co
    uczeń faktycznie napisał."""
    sentence = Item(pt="Estou a comer.", pl="Jem.", type="sentence", cefr_level="A2", source="seed")
    deck = Deck(slug=f"zdania-{uuid.uuid4().hex[:6]}", name="Zdania", is_shared=True, position=1)
    db.add_all([sentence, deck])
    db.flush()
    db.add(DeckItem(deck_id=deck.id, item_id=sentence.id, position=0))
    db.add(
        UserItemState(
            user_id=user.id, item_id=sentence.id, direction="production", state="review",
            due=datetime.now(timezone.utc) - timedelta(hours=1),
            stability=40.0, difficulty=5.0, reps=5, correct_reps=5,
        )
    )
    db.commit()

    client.patch("/api/settings", json={"enabled_modes": ["translate_ai"]})
    session = client.post("/api/study/sessions", json={"limit": 1}).json()
    task = session["tasks"][0]
    assert task["mode"] == "translate_ai"
    assert task["question"] == "Jem."

    result = client.post(
        f"/api/study/sessions/{session['id']}/answers",
        json={
            "answers": [
                {
                    "index": task["index"],
                    "rating": 2,
                    "user_answer": "Estou comendo.",
                    "elapsed_ms": 9000,
                }
            ]
        },
    )
    assert result.status_code == 200, result.text
    body = result.json()["results"][0]
    assert body["is_correct"] is True  # ocena 2 to „trudne", nie pomyłka
    assert body["correct_answer"] == "Estou a comer."

    review = db.query(Review).one()
    assert review.mode == "translate_ai"
    assert review.rating == 2
    assert review.user_answer == "Estou comendo."
