import uuid
from datetime import datetime, timedelta, timezone

from app.models import UserItemState
from app.services import scheduler as sched


def fresh_card() -> UserItemState:
    return UserItemState(
        user_id=uuid.uuid4(),
        item_id=uuid.uuid4(),
        direction="recognition",
        state="new",
        due=datetime.now(timezone.utc),
    )


def test_ratings_produce_increasing_intervals():
    """Again < Hard < Good < Easy — the whole premise of the rating buttons."""
    now = datetime.now(timezone.utc)
    intervals = []
    for rating in (sched.AGAIN, sched.HARD, sched.GOOD, sched.EASY):
        card = fresh_card()
        sched.review(card, rating, now=now)
        intervals.append(card.due - now)
    assert intervals == sorted(intervals), intervals
    assert intervals[0] < timedelta(hours=1)
    assert intervals[3] > timedelta(days=1)


def test_correct_answer_grows_the_interval_over_time():
    card = fresh_card()
    now = datetime.now(timezone.utc)
    previous = timedelta(0)
    for _ in range(5):
        sched.review(card, sched.GOOD, now=now)
        gap = card.due - now
        now = card.due
        if card.state == "review":
            assert gap > previous
            previous = gap
    assert card.state == "review"
    assert card.reps == 5
    assert card.correct_reps == 5
    assert card.lapses == 0


def test_forgetting_a_review_card_counts_as_a_lapse():
    card = fresh_card()
    now = datetime.now(timezone.utc)
    for _ in range(4):
        sched.review(card, sched.GOOD, now=now)
        now = card.due
    assert card.state == "review"

    sched.review(card, sched.AGAIN, now=now)
    assert card.lapses == 1
    assert card.state == "relearning"


def test_failing_while_still_learning_is_not_a_lapse():
    card = fresh_card()
    sched.review(card, sched.AGAIN)
    assert card.lapses == 0
    assert card.correct_reps == 0
    assert card.reps == 1


def test_higher_retention_schedules_sooner():
    now = datetime.now(timezone.utc)
    relaxed, strict = fresh_card(), fresh_card()
    for _ in range(3):
        sched.review(relaxed, sched.GOOD, desired_retention=0.80, now=now)
        sched.review(strict, sched.GOOD, desired_retention=0.95, now=now)
        now += timedelta(days=1)
    assert strict.due <= relaxed.due


def test_preview_intervals_cover_all_four_buttons():
    labels = sched.preview_intervals(fresh_card())
    assert set(labels) == {1, 2, 3, 4}
    assert all(isinstance(v, str) and v for v in labels.values())


def test_humanize_interval_reads_naturally():
    assert sched.humanize_interval(timedelta(minutes=1)) == "1 min"
    assert sched.humanize_interval(timedelta(minutes=45)) == "45 min"
    assert sched.humanize_interval(timedelta(hours=5)) == "5 godz."
    assert sched.humanize_interval(timedelta(days=1)) == "1 dzień"
    assert sched.humanize_interval(timedelta(days=9)) == "9 dni"
    assert sched.humanize_interval(timedelta(days=60)) == "2 mies."
    assert "roku" in sched.humanize_interval(timedelta(days=400))


def test_rating_from_outcome():
    assert sched.rating_from_outcome(False, 1000) == sched.AGAIN
    assert sched.rating_from_outcome(True, 1000) == sched.EASY
    assert sched.rating_from_outcome(True, 30_000) == sched.GOOD
    assert sched.rating_from_outcome(True, 1000, partial=True) == sched.HARD
