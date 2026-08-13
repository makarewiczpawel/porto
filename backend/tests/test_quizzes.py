from datetime import datetime, timedelta, timezone

from app.models import Item, QuizAnswer, Review, User, UserItemState
from tests.conftest import make_items


def start_quick(client, **body):
    response = client.post("/api/quizzes/quick", json={"count": 5, **body})
    assert response.status_code == 201, response.text
    return response.json()


def answer_all(client, attempt, correct: bool):
    """Answer every question deliberately right or deliberately wrong.

    The key is stripped from the payload, but the question still carries the
    item's own `pl`/`pt`, which is enough to work out which option is the right
    one — picking "the last option" would sometimes hit it by accident.
    """
    payload = []
    for question in attempt["questions"]:
        mode = question["mode"]
        if mode.startswith("mcq"):
            options = question["options"]
            truth = question["pl"] if mode == "mcq_pt_pl" else question["pt"]
            right = options.index(truth)
            wrong = next(i for i in range(len(options)) if i != right)
            payload.append({"index": question["index"], "selected_index": right if correct else wrong})
        else:
            payload.append({"index": question["index"], "user_answer": "" if correct else "zupełnie nie to"})
    client.post(f"/api/quizzes/attempts/{attempt['id']}/answers", json={"answers": payload})


def test_quick_quiz_hides_the_answer_key(client, registered, db):
    make_items(db, count=20)
    attempt = start_quick(client)

    assert len(attempt["questions"]) == 5
    for question in attempt["questions"]:
        assert "answer_index" not in question, "a quiz is graded server-side only"
        assert "expected" not in question
        assert "alternatives" not in question


def test_quiz_refuses_when_the_filter_is_too_narrow(client, registered, db):
    make_items(db, count=3, level="A1")
    response = client.post("/api/quizzes/quick", json={"count": 5, "cefr_level": "C1"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NOT_ENOUGH_ITEMS"


def test_scoring_counts_only_correct_answers(client, registered, db):
    _deck, items = make_items(db, count=20)
    by_pl = {item.pl: item for item in items}
    attempt = start_quick(client, modes=["mcq_pt_pl"])

    # Answer the first three correctly, leave the rest wrong.
    payload = []
    for position, question in enumerate(attempt["questions"]):
        options = question["options"]
        item = by_pl.get(question["pl"])
        assert item is not None
        right = options.index(item.pl)
        wrong = next(i for i in range(len(options)) if i != right)
        payload.append({"index": question["index"], "selected_index": right if position < 3 else wrong})
    client.post(f"/api/quizzes/attempts/{attempt['id']}/answers", json={"answers": payload})

    result = client.post(f"/api/quizzes/attempts/{attempt['id']}/submit").json()
    assert result["total"] == 5
    assert result["correct"] == 3
    assert result["score"] == 60.0
    assert len(result["mistakes"]) == 2
    assert all(m["pt"] and m["pl"] for m in result["mistakes"])


def test_unanswered_questions_count_as_mistakes_and_are_marked_skipped(client, registered, db):
    make_items(db, count=20)
    attempt = start_quick(client, modes=["mcq_pt_pl"])
    first = attempt["questions"][0]
    client.post(
        f"/api/quizzes/attempts/{attempt['id']}/answers",
        json={"answers": [{"index": first["index"], "selected_index": 0}]},
    )

    result = client.post(f"/api/quizzes/attempts/{attempt['id']}/submit").json()
    skipped = [m for m in result["mistakes"] if m["skipped"]]
    assert len(skipped) == 4, "four questions were never answered"


def test_a_quiz_does_not_touch_the_review_schedule(client, registered, db):
    """A test measures; it does not teach. Nothing may be rescheduled by it."""
    make_items(db, count=20)
    attempt = start_quick(client)
    answer_all(client, attempt, correct=False)
    client.post(f"/api/quizzes/attempts/{attempt['id']}/submit")

    assert db.query(UserItemState).count() == 0
    assert db.query(Review).count() == 0, "quiz answers must not land in the review log"
    assert db.query(QuizAnswer).count() > 0


def test_mistakes_can_be_pushed_into_tomorrow(client, registered, db):
    make_items(db, count=20)
    attempt = start_quick(client)
    answer_all(client, attempt, correct=False)
    client.post(f"/api/quizzes/attempts/{attempt['id']}/submit")

    response = client.post(f"/api/quizzes/attempts/{attempt['id']}/to-reviews").json()
    assert response["scheduled"] == 5

    states = db.query(UserItemState).all()
    assert len(states) == 5
    horizon = datetime.now(timezone.utc) + timedelta(days=1, hours=2)
    assert all(s.due <= horizon for s in states)
    assert all(s.direction == "recognition" for s in states)


def test_pushing_mistakes_never_delays_a_card_that_is_already_sooner(client, registered, db):
    _deck, items = make_items(db, count=20)
    user = db.query(User).one()
    soon = datetime.now(timezone.utc) - timedelta(hours=1)
    db.add(
        UserItemState(
            user_id=user.id,
            item_id=items[0].id,
            direction="recognition",
            state="review",
            due=soon,
            stability=3.0,
            difficulty=5.0,
        )
    )
    db.commit()

    attempt = start_quick(client, count=20)
    answer_all(client, attempt, correct=False)
    client.post(f"/api/quizzes/attempts/{attempt['id']}/submit")
    client.post(f"/api/quizzes/attempts/{attempt['id']}/to-reviews")

    db.expire_all()
    state = db.get(UserItemState, (user.id, items[0].id, "recognition"))
    assert state.due == soon, "a card already due must not be pushed back"
    assert state.stability == 3.0, "the quiz must not rewrite what real reviews established"


def test_saved_quiz_can_be_repeated_and_history_records_the_scores(client, registered, db):
    make_items(db, count=20)
    quiz = client.post(
        "/api/quizzes", json={"name": "Restauracja", "count": 5, "modes": ["mcq_pt_pl"]}
    ).json()

    for _ in range(2):
        attempt = client.post(f"/api/quizzes/{quiz['id']}/attempts").json()
        answer_all(client, attempt, correct=False)
        client.post(f"/api/quizzes/attempts/{attempt['id']}/submit")

    history = client.get("/api/quizzes/attempts").json()
    assert len(history) == 2
    assert all(h["name"] == "Restauracja" for h in history)

    listed = client.get("/api/quizzes").json()
    assert listed[0]["last_score"] is not None


def test_second_submit_keeps_the_first_score(client, registered, db):
    make_items(db, count=20)
    attempt = start_quick(client, modes=["mcq_pt_pl"])
    answer_all(client, attempt, correct=False)

    first = client.post(f"/api/quizzes/attempts/{attempt['id']}/submit").json()
    second = client.post(f"/api/quizzes/attempts/{attempt['id']}/submit").json()
    assert first["score"] == second["score"]


def test_answers_are_refused_after_the_attempt_is_finished(client, registered, db):
    make_items(db, count=20)
    attempt = start_quick(client)
    client.post(f"/api/quizzes/attempts/{attempt['id']}/submit")

    response = client.post(
        f"/api/quizzes/attempts/{attempt['id']}/answers",
        json={"answers": [{"index": 0, "selected_index": 0}]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ATTEMPT_FINISHED"


def test_a_quiz_belongs_to_its_owner(client, registered, db):
    make_items(db, count=20)
    attempt = start_quick(client)

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

    assert client.post(f"/api/quizzes/attempts/{attempt['id']}/submit").status_code == 404
    assert client.get("/api/quizzes").json() == []


def test_typed_quiz_answers_are_graded_with_accent_tolerance(client, registered, db):
    item = Item(pt="avó", pl="babcia", article="a", part_of_speech="noun", cefr_level="A1", verified=True)
    db.add(item)
    db.commit()

    attempt = client.post("/api/quizzes/quick", json={"count": 3, "modes": ["typing"]}).json()
    question = attempt["questions"][0]
    client.post(
        f"/api/quizzes/attempts/{attempt['id']}/answers",
        json={"answers": [{"index": question["index"], "user_answer": "a avo"}]},
    )
    result = client.post(f"/api/quizzes/attempts/{attempt['id']}/submit").json()
    assert result["correct"] == 1, "a missing accent still counts as knowing the word"
