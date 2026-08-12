"""Thin wrapper around py-fsrs.

The rest of the app never imports `fsrs` directly — it works with
`UserItemState` rows and calls `review()`. That keeps the FSRS version and its
`Card` object in one place, and makes the scheduler easy to test.
"""

from datetime import datetime, timedelta, timezone

from fsrs import Card, Rating, Scheduler, State

from app.models import UserItemState

# FSRS state -> our string, and back.
_STATE_TO_STR = {State.Learning: "learning", State.Review: "review", State.Relearning: "relearning"}
_STR_TO_STATE = {v: k for k, v in _STATE_TO_STR.items()}

AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4


def _scheduler(desired_retention: float) -> Scheduler:
    return Scheduler(desired_retention=float(desired_retention))


def _to_card(state: UserItemState) -> Card:
    if state.state == "new" or state.stability is None:
        return Card()
    return Card(
        state=_STR_TO_STATE[state.state],
        step=state.step,
        stability=state.stability,
        difficulty=state.difficulty,
        due=state.due,
        last_review=state.last_review_at,
    )


def review(
    state: UserItemState,
    rating: int,
    desired_retention: float = 0.90,
    now: datetime | None = None,
) -> UserItemState:
    """Apply one answer to a card and write the new schedule back onto it.

    Mutates and returns the same `UserItemState` instance.
    """
    now = now or datetime.now(timezone.utc)
    card = _to_card(state)
    updated, _log = _scheduler(desired_retention).review_card(card, Rating(rating), review_datetime=now)

    was_review = state.state == "review"
    state.state = _STATE_TO_STR[updated.state]
    state.stability = updated.stability
    state.difficulty = updated.difficulty
    state.due = updated.due
    state.last_review_at = now
    state.step = updated.step
    # Column defaults only land on INSERT, so a state that has not been flushed
    # yet still carries None here.
    state.reps = (state.reps or 0) + 1
    state.correct_reps = state.correct_reps or 0
    state.lapses = state.lapses or 0
    if rating > AGAIN:
        state.correct_reps += 1
    elif was_review:
        # Forgetting a card that was already in review is a lapse; failing one
        # that is still being learned is just part of learning it.
        state.lapses += 1
    return state


def preview_intervals(state: UserItemState, desired_retention: float = 0.90) -> dict[int, str]:
    """What each rating button would schedule, so the UI can show it.

    Returns {rating: human label in Polish}.
    """
    now = datetime.now(timezone.utc)
    out: dict[int, str] = {}
    for rating in (AGAIN, HARD, GOOD, EASY):
        card = _to_card(state)
        updated, _ = _scheduler(desired_retention).review_card(card, Rating(rating), review_datetime=now)
        out[rating] = humanize_interval(updated.due - now)
    return out


def humanize_interval(delta: timedelta) -> str:
    minutes = max(1, round(delta.total_seconds() / 60))
    if minutes < 60:
        return f"{minutes} min"
    hours = round(minutes / 60)
    if hours < 24:
        return f"{hours} godz."
    days = round(delta.total_seconds() / 86400)
    if days < 31:
        return "1 dzień" if days == 1 else f"{days} dni"
    months = round(days / 30)
    if months < 12:
        return "1 mies." if months == 1 else f"{months} mies."
    years = days / 365
    return f"{years:.1f} roku".replace(".", ",")


def rating_from_outcome(
    is_correct: bool,
    elapsed_ms: int,
    *,
    fast_threshold_ms: int = 4000,
    partial: bool = False,
) -> int:
    """Map a graded answer onto an FSRS rating for modes without self-grading.

    `partial` covers "almost right" answers (a typo or a missing accent) — they
    are not failures, but they should come back sooner than a clean hit.
    """
    if not is_correct:
        return AGAIN
    if partial:
        return HARD
    if 0 < elapsed_ms <= fast_threshold_ms:
        return EASY
    return GOOD
