from datetime import date, timedelta

from app.models import DailyStat, Review, User, UserItemState
from tests.conftest import make_items


# ── auth ──────────────────────────────────────────────────────────────────
def test_health_reports_the_database(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["db"] is True


def test_registration_requires_the_invite_code(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "x@example.com",
            "password": "long-enough-pw",
            "display_name": "X",
            "invite_code": "wrong",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVITE_INVALID"


def test_registration_rejects_a_duplicate_email(client, registered):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "PAWEL@example.com",
            "password": "another-password",
            "display_name": "Paweł",
            "invite_code": "test-invite",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


def test_login_and_refresh_round_trip(client, registered):
    login = client.post(
        "/api/auth/login", json={"email": "pawel@example.com", "password": "bem-vindo-2026"}
    )
    assert login.status_code == 200
    assert "porto_refresh" in login.cookies or "porto_refresh" in client.cookies

    refreshed = client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]


def test_wrong_password_is_rejected(client, registered):
    response = client.post(
        "/api/auth/login", json={"email": "pawel@example.com", "password": "not-the-password"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "CREDENTIALS_INVALID"


def test_protected_endpoints_need_a_token(client):
    client.headers.pop("Authorization", None)
    assert client.get("/api/study/queue/summary").status_code == 401


def test_an_access_token_cannot_be_used_as_a_refresh_token(client, registered):
    client.cookies.set("porto_refresh", registered["access_token"])
    assert client.post("/api/auth/refresh").status_code == 401


def test_me_returns_profile_and_settings(client, registered):
    body = client.get("/api/auth/me").json()
    assert body["user"]["email"] == "pawel@example.com"
    assert body["settings"]["daily_goal"] == 25
    assert body["settings"]["new_per_day"] == 10


# ── settings ──────────────────────────────────────────────────────────────
def test_settings_can_be_patched(client, registered):
    response = client.patch("/api/settings", json={"daily_goal": 40, "new_per_day": 5})
    assert response.status_code == 200
    assert response.json()["daily_goal"] == 40
    assert response.json()["new_per_day"] == 5
    assert response.json()["review_limit"] == 100, "untouched fields must stay"


def test_settings_reject_values_outside_the_supported_range(client, registered):
    assert client.patch("/api/settings", json={"desired_retention": 0.5}).status_code == 422
    assert client.patch("/api/settings", json={"new_per_day": 5000}).status_code == 422


# ── content ───────────────────────────────────────────────────────────────
def test_items_can_be_searched_in_both_languages(client, registered, db):
    make_items(db, count=5)
    assert client.get("/api/items", params={"search": "palavra1"}).json()["total"] == 1
    assert client.get("/api/items", params={"search": "slowo2"}).json()["total"] == 1
    assert client.get("/api/items").json()["total"] == 5


def test_item_detail_includes_examples_and_article(client, registered, db):
    _deck, items = make_items(db, count=3)
    body = client.get(f"/api/items/{items[0].id}").json()
    assert body["display_pt"] == "a palavra0"
    assert len(body["examples"]) == 1
    assert body["cards"] == []


def test_missing_item_returns_a_typed_error(client, registered):
    response = client.get("/api/items/11111111-1111-1111-1111-111111111111")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ITEM_NOT_FOUND"


def test_decks_carry_their_counts(client, registered, db):
    make_items(db, count=7)
    decks = client.get("/api/decks").json()
    assert len(decks) == 1
    assert decks[0]["total"] == 7
    assert decks[0]["due"] == 0
    assert decks[0]["untouched"] == 7


# ── study ─────────────────────────────────────────────────────────────────
def start_session(client, **body):
    response = client.post("/api/study/sessions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_a_session_is_built_and_hides_the_answer_key(client, registered, db):
    make_items(db, count=12)
    session = start_session(client, new_limit=6)

    assert session["planned_count"] == 6
    assert len(session["tasks"]) == 6
    for task in session["tasks"]:
        assert "answer_index" not in task, "the client must not be able to read the answer"
        assert task["mode"] == "flashcard", "new words are shown, not tested"
        assert task["direction"] == "recognition"


def test_only_one_session_can_be_open_at_a_time(client, registered, db):
    make_items(db, count=12)
    start_session(client, new_limit=3)
    response = client.post("/api/study/sessions", json={"new_limit": 3})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SESSION_ALREADY_OPEN"


def test_a_session_with_nothing_to_study_is_refused(client, registered):
    response = client.post("/api/study/sessions", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NOTHING_TO_STUDY"


def test_answering_schedules_the_card(client, registered, db):
    make_items(db, count=12)
    session = start_session(client, new_limit=3)

    answers = [{"index": t["index"], "rating": 3, "elapsed_ms": 2500} for t in session["tasks"]]
    response = client.post(f"/api/study/sessions/{session['id']}/answers", json={"answers": answers})
    assert response.status_code == 200

    results = response.json()["results"]
    assert len(results) == 3
    assert all(r["is_correct"] for r in results)
    assert all(r["next_due_label"] for r in results)
    assert db.query(UserItemState).count() == 3
    assert db.query(Review).count() == 3


def test_resending_the_same_answers_does_not_double_count(client, registered, db):
    """The offline queue retries on a dropped connection — a retry must be a
    no-op, not a second review."""
    make_items(db, count=12)
    session = start_session(client, new_limit=4)
    answers = [{"index": t["index"], "rating": 3, "elapsed_ms": 1500} for t in session["tasks"]]

    first = client.post(f"/api/study/sessions/{session['id']}/answers", json={"answers": answers})
    second = client.post(f"/api/study/sessions/{session['id']}/answers", json={"answers": answers})

    assert first.status_code == 200
    assert second.status_code == 200
    assert all(r["duplicate"] for r in second.json()["results"])
    assert all(not r["duplicate"] for r in first.json()["results"])

    assert db.query(Review).count() == 4, "a retry must not add reviews"
    states = db.query(UserItemState).all()
    assert all(s.reps == 1 for s in states), "a retry must not reschedule the card"

    stat = db.query(DailyStat).one()
    assert stat.reviews_count == 4


def test_a_wrong_multiple_choice_answer_is_graded_server_side(client, registered, db):
    from datetime import datetime, timezone

    make_items(db, count=12)
    # Put a card into learning so the builder asks it as multiple choice.
    session = start_session(client, new_limit=2)
    answers = [{"index": t["index"], "rating": 1} for t in session["tasks"]]
    client.post(f"/api/study/sessions/{session['id']}/answers", json={"answers": answers})
    client.post(f"/api/study/sessions/{session['id']}/finish")

    # "Again" schedules a minute out; pretend that minute has passed.
    for state in db.query(UserItemState).all():
        state.due = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    session2 = start_session(client, new_limit=0)
    mcq = [t for t in session2["tasks"] if t["mode"].startswith("mcq")]
    assert mcq, "a card in learning should come back as multiple choice"

    task = mcq[0]
    response = client.post(
        f"/api/study/sessions/{session2['id']}/answers",
        json={"answers": [{"index": task["index"], "selected_index": 0, "elapsed_ms": 2000}]},
    )
    result = response.json()["results"][0]
    # Whether index 0 happened to be right is up to the shuffle; either way the
    # server decides, and it reports the correct answer back.
    assert result["correct_answer"] in task["options"]
    assert isinstance(result["is_correct"], bool)


def test_an_answer_for_a_question_outside_the_session_is_refused(client, registered, db):
    make_items(db, count=12)
    session = start_session(client, new_limit=2)
    response = client.post(
        f"/api/study/sessions/{session['id']}/answers",
        json={"answers": [{"index": 99, "rating": 3}]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNKNOWN_QUESTION"


def test_an_interrupted_session_resumes_where_it_stopped(client, registered, db):
    make_items(db, count=12)
    session = start_session(client, new_limit=6)
    client.post(
        f"/api/study/sessions/{session['id']}/answers",
        json={"answers": [{"index": 0, "rating": 3}, {"index": 1, "rating": 3}]},
    )

    resumed = client.get("/api/study/sessions/active").json()
    assert resumed["id"] == session["id"]
    assert len(resumed["tasks"]) == 4
    assert {t["index"] for t in resumed["tasks"]} == {2, 3, 4, 5}


def test_finishing_a_session_summarises_it(client, registered, db):
    make_items(db, count=12)
    session = start_session(client, new_limit=5)
    # Question 0 is deliberately wrong: its index is falsy, which is exactly
    # where a lookup default can silently swallow the word.
    ratings = {0: 1, 1: 3, 2: 1, 3: 3, 4: 3}
    answers = [{"index": i, "rating": ratings[i], "elapsed_ms": 3000} for i in range(5)]
    client.post(f"/api/study/sessions/{session['id']}/answers", json={"answers": answers})

    summary = client.post(f"/api/study/sessions/{session['id']}/finish").json()
    assert summary["completed_count"] == 5
    assert summary["correct_count"] == 3
    assert summary["accuracy"] == 60.0
    assert len(summary["mistakes"]) == 2
    # Every mistake must carry its word — including the one at question 0,
    # whose index is falsy and used to fall through a lookup default.
    assert all(m["pt"] and m["pl"] for m in summary["mistakes"])

    # Session is closed, so a new one can start.
    assert client.get("/api/study/sessions/active").json() is None


def test_queue_summary_tracks_progress_towards_the_daily_goal(client, registered, db):
    make_items(db, count=30)
    client.patch("/api/settings", json={"daily_goal": 3})

    before = client.get("/api/study/queue/summary").json()
    assert before["due"] == 0
    assert before["new_available"] == 30
    assert before["done_today"] == 0
    assert before["streak"] == 0

    session = start_session(client, new_limit=4)
    client.post(
        f"/api/study/sessions/{session['id']}/answers",
        json={"answers": [{"index": i, "rating": 3} for i in range(4)]},
    )

    after = client.get("/api/study/queue/summary").json()
    assert after["done_today"] == 4
    assert after["goal_met"] is True
    assert after["streak"] == 1
    assert after["new_available"] == 26


def test_streak_counts_back_over_consecutive_days(client, registered, db):
    user = db.query(User).one()
    today = date.today()
    for offset in (0, 1, 2, 4):
        db.add(
            DailyStat(
                user_id=user.id,
                date=today - timedelta(days=offset),
                reviews_count=30,
                correct_count=28,
                goal_met=True,
            )
        )
    db.commit()

    summary = client.get("/api/study/queue/summary").json()
    assert summary["streak"] == 3, "the gap at day 3 ends the streak"


def test_a_missed_day_does_not_break_the_streak_until_it_is_over(client, registered, db):
    """Not having studied *yet today* is not a broken streak."""
    user = db.query(User).one()
    yesterday = date.today() - timedelta(days=1)
    for offset in (0, 1):
        db.add(
            DailyStat(
                user_id=user.id,
                date=yesterday - timedelta(days=offset),
                reviews_count=30,
                goal_met=True,
            )
        )
    db.commit()
    assert client.get("/api/study/queue/summary").json()["streak"] == 2


def test_users_do_not_see_each_other_progress(client, registered, db):
    make_items(db, count=10)
    session = start_session(client, new_limit=3)
    client.post(
        f"/api/study/sessions/{session['id']}/answers",
        json={"answers": [{"index": i, "rating": 3} for i in range(3)]},
    )
    client.post(f"/api/study/sessions/{session['id']}/finish")

    magda = client.post(
        "/api/auth/register",
        json={
            "email": "magda@example.com",
            "password": "outra-palavra-passe",
            "display_name": "Magda",
            "invite_code": "test-invite",
        },
    ).json()
    client.headers["Authorization"] = f"Bearer {magda['access_token']}"

    summary = client.get("/api/study/queue/summary").json()
    assert summary["due"] == 0
    assert summary["done_today"] == 0
    assert summary["new_available"] == 10, "shared content, separate progress"
    assert client.get("/api/study/sessions/active").json() is None
