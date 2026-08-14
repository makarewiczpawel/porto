"""Faza 5 — statystyki, prognoza, nadrabianie i eksport.

Te liczby trafiają wprost na ekran i sterują tym, ile pracy dostaje człowiek,
więc każda z nich ma tu test na wartość graniczną, a nie tylko na to, że
endpoint odpowiada.
"""

import csv
import io
import json
from datetime import datetime, timedelta, timezone

from app.models import DailyStat, Review, UserItemState
from app.services import stats as stats_service
from app.services import task_builder as tb
from tests.conftest import make_items


def _review(db, user, item, *, correct: bool, when: datetime, mode: str = "typing"):
    db.add(
        Review(
            user_id=user.id,
            item_id=item.id,
            direction="production",
            mode=mode,
            rating=3 if correct else 1,
            is_correct=correct,
            elapsed_ms=4000,
            reviewed_at=when,
        )
    )


# ── mapa aktywności ───────────────────────────────────────────────────────
def test_heatmap_includes_the_empty_days(db, registered, client):
    from app.models import User

    user = db.get(User, registered["user"]["id"])
    today = stats_service.local_day(user, datetime.now(timezone.utc))
    db.add(DailyStat(user_id=user.id, date=today - timedelta(days=3), reviews_count=12))
    db.add(DailyStat(user_id=user.id, date=today, reviews_count=5))
    db.commit()

    body = client.get("/api/stats/heatmap?days=30").json()
    dates = [day["date"] for day in body["days"]]

    # Cztery dni: od pierwszego wpisu do dzisiaj, z dwoma pustymi w środku.
    assert len(dates) == 4
    assert body["active_days"] == 2
    assert body["total_reviews"] == 17
    assert [day["reviews"] for day in body["days"]] == [12, 0, 0, 5]


def test_heatmap_of_a_new_account_is_a_single_day(client, registered):
    body = client.get("/api/stats/heatmap").json()
    assert body["days"] == [] or len(body["days"]) == 1
    assert body["total_reviews"] == 0


# ── prognoza ──────────────────────────────────────────────────────────────
def test_forecast_puts_overdue_cards_on_today(db, registered, client):
    from app.models import User

    user = db.get(User, registered["user"]["id"])
    _, items = make_items(db, count=3)
    now = datetime.now(timezone.utc)
    for item, offset in zip(items, [-5, 0, 2], strict=True):
        db.add(
            UserItemState(
                user_id=user.id, item_id=item.id, direction="recognition", state="review",
                due=now + timedelta(days=offset), stability=10.0, difficulty=5.0,
            )
        )
    db.commit()

    body = client.get("/api/stats/forecast?days=7").json()
    assert body["total"] == 3
    # Karta zaległa o pięć dni czeka dziś, nie pięć dni temu.
    assert body["days"][0]["due"] == 2
    assert body["days"][2]["due"] == 1


def test_forecast_ignores_suspended_cards(db, registered, client):
    from app.models import User

    user = db.get(User, registered["user"]["id"])
    _, items = make_items(db, count=2)
    now = datetime.now(timezone.utc)
    db.add(UserItemState(user_id=user.id, item_id=items[0].id, direction="recognition",
                         state="review", due=now, stability=10.0, difficulty=5.0))
    db.add(UserItemState(user_id=user.id, item_id=items[1].id, direction="recognition",
                         state="review", due=now, stability=10.0, difficulty=5.0, suspended=True))
    db.commit()

    assert client.get("/api/stats/forecast").json()["total"] == 1


# ── retencja i najtrudniejsze słowa ───────────────────────────────────────
def test_retention_ignores_flashcards(db, registered, client):
    """Fiszkę ocenia się samemu, więc jej wynik mówi o pewności siebie, nie o
    pamięci. Wliczanie jej zawyżałoby retencję."""
    from app.models import User

    user = db.get(User, registered["user"]["id"])
    _, items = make_items(db, count=2)
    now = datetime.now(timezone.utc)
    _review(db, user, items[0], correct=False, when=now, mode="typing")
    for _ in range(5):
        _review(db, user, items[1], correct=True, when=now, mode="flashcard")
    db.commit()

    assert client.get("/api/stats/overview").json()["retention_30d"] == 0.0


def test_retention_is_none_without_data(client, registered):
    assert client.get("/api/stats/overview").json()["retention_30d"] is None


def test_hardest_needs_more_than_one_slip(db, registered, client):
    """Słowo pomylone raz nie jest jeszcze problemem — z progiem 0% wyglądałoby
    na najtrudniejsze w całej bazie."""
    from app.models import User

    user = db.get(User, registered["user"]["id"])
    _, items = make_items(db, count=2)
    now = datetime.now(timezone.utc)
    _review(db, user, items[0], correct=False, when=now)
    for correct in (True, False, False, False):
        _review(db, user, items[1], correct=correct, when=now)
    db.commit()

    found = client.get("/api/stats/hardest").json()["items"]
    assert [entry["pt"] for entry in found] == ["a palavra1"]
    assert found[0]["attempts"] == 4 and found[0]["misses"] == 3
    assert found[0]["accuracy"] == 25


def test_hardest_skips_words_answered_correctly(db, registered, client):
    from app.models import User

    user = db.get(User, registered["user"]["id"])
    _, items = make_items(db, count=1)
    now = datetime.now(timezone.utc)
    for _ in range(4):
        _review(db, user, items[0], correct=True, when=now)
    db.commit()

    assert client.get("/api/stats/hardest").json()["items"] == []


# ── nadrabianie po przerwie ───────────────────────────────────────────────
def test_small_queue_is_not_a_backlog():
    assert tb.catch_up_plan(due=tb.BACKLOG_THRESHOLD, review_limit=100) is None


def test_backlog_is_spread_over_a_week():
    plan = tb.catch_up_plan(due=300, review_limit=100)
    assert plan == {"backlog": 300, "today": 43, "days": 7}
    # Siedem dni po tyle wystarczy, żeby nawis zniknął.
    assert plan["today"] * plan["days"] >= 300


def test_catch_up_never_exceeds_the_users_own_limit():
    plan = tb.catch_up_plan(due=3000, review_limit=100)
    assert plan["today"] == 100


def test_session_after_a_break_takes_only_todays_portion(db, registered, client):
    from app.models import User

    user = db.get(User, registered["user"]["id"])
    _, items = make_items(db, count=80)
    past = datetime.now(timezone.utc) - timedelta(days=20)
    for item in items:
        db.add(UserItemState(user_id=user.id, item_id=item.id, direction="recognition",
                             state="review", due=past, stability=20.0, difficulty=5.0,
                             reps=3, correct_reps=3))
    db.commit()

    summary = client.get("/api/study/queue/summary").json()
    assert summary["due"] == 80
    assert summary["catch_up"]["backlog"] == 80
    assert summary["catch_up"]["today"] == 12

    session = client.post("/api/study/sessions", json={"new_limit": 0}).json()
    # Pytań jest mniej niż kart, bo rozgrzewka pakuje pięć par w jedno pytanie.
    # Istotne jest to, że ze ściany 80 kart zrobiła się dzienna porcja.
    assert 1 <= session["planned_count"] <= 12


# ── eksport ───────────────────────────────────────────────────────────────
def test_csv_export_round_trips_through_the_importer(db, registered, client):
    make_items(db, count=3)
    response = client.get("/api/items/export?format=csv")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]

    text = response.text.lstrip("﻿")
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    assert rows[0][:2] == ["pt", "pl"]
    assert len(rows) == 4

    # Plik stąd musi wracać przez import bez żadnej obróbki — inaczej nie jest
    # kopią zapasową, tylko raportem do oglądania.
    parsed = client.post("/api/items/import", json={"csv": text, "dry_run": True}).json()
    assert parsed["errors"] == []
    assert len(parsed["preview"]) == 3


def test_json_export_keeps_examples_and_decks(db, registered, client):
    make_items(db, count=2, deck_name="Wakacje")
    body = json.loads(client.get("/api/items/export?format=json").text)
    assert body["count"] == 2
    first = body["items"][0]
    assert first["decks"] == ["Wakacje"]
    assert first["examples"][0]["pt"].startswith("Esta é")


def test_export_can_skip_the_seed_base(db, registered, client):
    """Baza startowa wraca przy każdym wdrożeniu, więc w kopii zapasowej jest
    tylko ciężarem."""
    make_items(db, count=2)  # source="seed"
    client.post("/api/items", json={"pt": "saudade", "pl": "tęsknota", "cefr_level": "B1"})

    everything = client.get("/api/items/export?format=json").json()
    mine = client.get("/api/items/export?format=json&mine_only=true").json()
    assert everything["count"] == 3
    assert [item["pt"] for item in mine["items"]] == ["saudade"]
