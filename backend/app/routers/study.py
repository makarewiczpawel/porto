import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.errors import conflict, not_found, unprocessable
from app.models import Item, Review, StudySession, User, UserItemState
from app.schemas import (
    AnswerIn,
    AnswerResultOut,
    AnswersIn,
    AnswersOut,
    MistakeOut,
    QueueSummaryOut,
    SessionCreateIn,
    SessionOut,
    SessionSummaryOut,
)
from app.services import grader
from app.services import scheduler as sched
from app.services import stats as stats_service
from app.services.task_builder import build_session, queue_counts

router = APIRouter(prefix="/api/study", tags=["study"])


def _session_or_404(db: Session, user: User, session_id: uuid.UUID) -> StudySession:
    session = db.get(StudySession, session_id)
    if session is None or session.user_id != user.id:
        raise not_found("SESSION_NOT_FOUND", "Nie ma takiej sesji.")
    return session


def _tasks(session: StudySession) -> list[dict]:
    return list(session.payload.get("tasks", []))


@router.get("/queue/summary", response_model=QueueSummaryOut)
def queue_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> QueueSummaryOut:
    now = datetime.now(timezone.utc)
    counts = queue_counts(db, user, now)
    today = stats_service.today_stat(db, user, now)
    return QueueSummaryOut(
        due=counts["due"],
        new_available=counts["new_available"],
        done_today=today.reviews_count if today else 0,
        goal=user.settings.daily_goal,
        goal_met=bool(today and today.goal_met),
        streak=stats_service.streak(db, user, stats_service.local_day(user, now)),
        next_due_at=counts["next_due_at"],
    )


@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(
    body: SessionCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SessionOut:
    open_session = db.execute(
        select(StudySession).where(
            StudySession.user_id == user.id, StudySession.finished_at.is_(None)
        )
    ).scalars().first()
    if open_session is not None:
        raise conflict(
            "SESSION_ALREADY_OPEN",
            "Masz nieukończoną sesję. Dokończ ją albo przerwij.",
            session_id=str(open_session.id),
        )

    now = datetime.now(timezone.utc)
    tasks, resolved_decks = build_session(
        db,
        user,
        user.settings,
        deck_ids=body.deck_ids,
        new_limit=body.new_limit,
        review_limit=body.review_limit,
        modes=body.modes,
        now=now,
    )
    if not tasks:
        raise unprocessable(
            "NOTHING_TO_STUDY",
            "Na teraz nie ma czego powtarzać. Wróć później albo dodaj nowe pozycje.",
        )

    payload = {"tasks": [t.as_dict() for t in tasks]}
    session = StudySession(
        user_id=user.id,
        planned_count=len(tasks),
        deck_ids=[str(d) for d in resolved_decks] if resolved_decks else None,
        payload=payload,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return SessionOut(
        id=session.id,
        started_at=session.started_at,
        planned_count=session.planned_count,
        completed_count=0,
        tasks=_public_tasks(payload["tasks"]),
    )


def _public_tasks(tasks: list[dict]) -> list[dict]:
    """The client never receives `answer_index` — grading happens server-side
    against the frozen session payload."""
    out = []
    for task in tasks:
        clean = {k: v for k, v in task.items() if k != "answer_index"}
        out.append(clean)
    return out


@router.get("/sessions/active", response_model=SessionOut | None)
def active_session(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SessionOut | None:
    session = db.execute(
        select(StudySession)
        .where(StudySession.user_id == user.id, StudySession.finished_at.is_(None))
        .order_by(StudySession.started_at.desc())
    ).scalars().first()
    if session is None:
        return None
    answered = set(
        db.execute(
            select(Review.question_index).where(Review.session_id == session.id)
        ).scalars().all()
    )
    tasks = [t for t in _tasks(session) if t["index"] not in answered]
    return SessionOut(
        id=session.id,
        started_at=session.started_at,
        planned_count=session.planned_count,
        completed_count=session.completed_count,
        tasks=_public_tasks(tasks),
    )


@dataclass
class Outcome:
    """One card scored. Most questions produce exactly one; a matching round
    produces one per pair."""

    item_id: uuid.UUID
    direction: str
    is_correct: bool
    rating: int
    user_answer: str | None


@dataclass
class Graded:
    outcomes: list[Outcome]
    correct_answer: str
    match: str | None = None
    diff: str | None = None

    @property
    def is_correct(self) -> bool:
        return all(o.is_correct for o in self.outcomes) if self.outcomes else False

    @property
    def rating(self) -> int:
        return min((o.rating for o in self.outcomes), default=sched.GOOD)


def _grade(task: dict, answer: AnswerIn, *, accent_strict: bool) -> Graded:
    """Score an answer against the frozen session payload.

    The client grades locally too, for instant feedback and for offline mode,
    but this is the version that reaches the database.
    """
    mode = task["mode"]
    item_id = uuid.UUID(task["item_id"])
    direction = task["direction"]

    def one(is_correct: bool, rating: int, user_answer: str | None = None) -> list[Outcome]:
        return [Outcome(item_id, direction, is_correct, rating, user_answer)]

    if mode == "matching":
        known = {p["item_id"]: p for p in task.get("pairs", [])}
        outcomes: list[Outcome] = []
        for pair in answer.pairs or []:
            key = str(pair.item_id)
            if key not in known:
                raise unprocessable(
                    "UNKNOWN_PAIR", "Ta para nie należy do tego pytania.", item_id=key
                )
            outcomes.append(
                Outcome(
                    item_id=pair.item_id,
                    direction="recognition",
                    is_correct=pair.is_correct,
                    rating=sched.rating_from_outcome(pair.is_correct, answer.elapsed_ms),
                    user_answer=None,
                )
            )
        return Graded(outcomes, correct_answer=task.get("pl", ""))

    if mode in ("mcq_pt_pl", "mcq_pl_pt"):
        options = task.get("options", [])
        answer_index = task.get("answer_index")
        correct_text = options[answer_index] if answer_index is not None and options else task["pl"]
        picked = (
            options[answer.selected_index]
            if answer.selected_index is not None and 0 <= answer.selected_index < len(options)
            else None
        )
        is_correct = answer.selected_index is not None and answer.selected_index == answer_index
        return Graded(
            one(is_correct, sched.rating_from_outcome(is_correct, answer.elapsed_ms), picked),
            correct_answer=correct_text,
        )

    if mode in ("typing", "cloze", "word_bank"):
        expected = task.get("expected") or task.get("pt", "")
        given = answer.user_answer or ""
        result = grader.grade(
            given,
            expected,
            alternatives=list(task.get("alternatives") or []),
            accent_strict=accent_strict,
        )
        rating = sched.rating_from_outcome(
            result.is_correct, answer.elapsed_ms, partial=result.partial
        )
        return Graded(
            one(result.is_correct, rating, given),
            correct_answer=expected,
            match=result.match.value,
            diff=grader.diff_hint(given, expected) if not result.is_correct or result.partial else None,
        )

    if mode == "translate_ai":
        # Ocenę wystawił model, zanim odpowiedź tu dotarła — przy zdaniu nie ma
        # jednej poprawnej wersji, więc porównanie znak po znaku odpadłoby na
        # każdym poprawnym synonimie. Zapisujemy jego werdykt razem z tym, co
        # uczeń faktycznie napisał, żeby dało się do tego wrócić.
        rating = answer.rating or sched.GOOD
        return Graded(
            one(rating > sched.AGAIN, rating, answer.user_answer),
            correct_answer=task.get("expected") or task.get("pt", ""),
        )

    # flashcard: the user grades themselves
    rating = answer.rating or sched.GOOD
    correct_text = task.get("back") or task.get("pl", "")
    return Graded(one(rating > sched.AGAIN, rating), correct_answer=correct_text)


@router.post("/sessions/{session_id}/answers", response_model=AnswersOut)
def submit_answers(
    session_id: uuid.UUID,
    body: AnswersIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnswersOut:
    session = _session_or_404(db, user, session_id)
    tasks = {t["index"]: t for t in _tasks(session)}
    now = datetime.now(timezone.utc)
    retention = float(user.settings.desired_retention)

    # Grouped by question, because one question can cover several cards.
    already: dict[int, list[Review]] = {}
    for review in db.execute(select(Review).where(Review.session_id == session.id)).scalars().all():
        already.setdefault(review.question_index, []).append(review)

    results: list[AnswerResultOut] = []
    new_cards = 0
    seconds = 0

    for answer in body.answers:
        task = tasks.get(answer.index)
        if task is None:
            raise unprocessable("UNKNOWN_QUESTION", f"Pytanie {answer.index} nie należy do tej sesji.")

        # The answer queue can be retried after a dropped connection, so the
        # same question must never be scheduled twice.
        if answer.index in already:
            previous = already[answer.index][0]
            state = db.get(UserItemState, (user.id, previous.item_id, previous.direction))
            due = state.due if state else now
            results.append(
                AnswerResultOut(
                    index=answer.index,
                    is_correct=all(r.is_correct for r in already[answer.index]),
                    rating=previous.rating,
                    correct_answer=task.get("expected") or task.get("back") or task.get("pl", ""),
                    next_due=due,
                    next_due_label=sched.humanize_interval(due - now),
                    duplicate=True,
                )
            )
            continue

        graded = _grade(task, answer, accent_strict=bool(user.settings.accent_strict))
        if not graded.outcomes:
            raise unprocessable("EMPTY_ANSWER", "Odpowiedź nie zawiera nic do zapisania.")

        written: list[Review] = []
        last_due = now
        for outcome in graded.outcomes:
            state = db.get(UserItemState, (user.id, outcome.item_id, outcome.direction))
            if state is None:
                state = UserItemState(
                    user_id=user.id,
                    item_id=outcome.item_id,
                    direction=outcome.direction,
                    state="new",
                    due=now,
                )
                db.add(state)
                db.flush()
                new_cards += 1

            sched.review(state, outcome.rating, desired_retention=retention, now=now)
            last_due = state.due

            review = Review(
                user_id=user.id,
                item_id=outcome.item_id,
                direction=outcome.direction,
                session_id=session.id,
                question_index=answer.index,
                mode=task["mode"],
                rating=outcome.rating,
                is_correct=outcome.is_correct,
                user_answer=outcome.user_answer,
                elapsed_ms=answer.elapsed_ms,
                stability_after=state.stability,
            )
            db.add(review)
            written.append(review)

        try:
            db.flush()
        except IntegrityError:
            # Lost a race with a concurrent retry of the same batch.
            db.rollback()
            raise conflict("ANSWER_ALREADY_RECORDED", "Ta odpowiedź została już zapisana.")

        # A matching round is one question on screen but several cards in the
        # log; the session counters follow the cards.
        session.completed_count += len(written)
        session.correct_count += sum(1 for o in graded.outcomes if o.is_correct)
        seconds += round(answer.elapsed_ms / 1000)
        already[answer.index] = written

        results.append(
            AnswerResultOut(
                index=answer.index,
                is_correct=graded.is_correct,
                rating=graded.rating,
                correct_answer=graded.correct_answer,
                next_due=last_due,
                next_due_label=sched.humanize_interval(last_due - now),
                match=graded.match,
                diff=graded.diff,
            )
        )

    fresh = sum(len(already[r.index]) for r in results if not r.duplicate)
    correct = sum(
        sum(1 for review in already[r.index] if review.is_correct)
        for r in results
        if not r.duplicate
    )
    if fresh:
        stats_service.record_activity(
            db,
            user,
            user.settings,
            now,
            reviews=fresh,
            new_cards=new_cards,
            correct=correct,
            seconds=seconds,
        )
    db.commit()
    return AnswersOut(results=results)


@router.post("/sessions/{session_id}/finish", response_model=SessionSummaryOut)
def finish_session(
    session_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SessionSummaryOut:
    session = _session_or_404(db, user, session_id)
    now = datetime.now(timezone.utc)
    if session.finished_at is None:
        session.finished_at = now

    tasks = {t["index"]: t for t in _tasks(session)}
    reviews = (
        db.execute(select(Review).where(Review.session_id == session.id).order_by(Review.question_index))
        .scalars()
        .all()
    )
    mistakes: list[MistakeOut] = []
    for review in reviews:
        if review.is_correct:
            continue
        # `or -1` would swallow question 0 — index zero is falsy in Python.
        task = tasks.get(review.question_index, {}) if review.question_index is not None else {}
        mistakes.append(
            MistakeOut(
                item_id=review.item_id,
                pt=task.get("pt", ""),
                pl=task.get("pl", ""),
                user_answer=review.user_answer,
                mode=review.mode,
            )
        )

    new_count = sum(1 for t in tasks.values() if t.get("is_new") and t["index"] in {r.question_index for r in reviews})
    seconds = sum(r.elapsed_ms for r in reviews) // 1000
    completed = len(reviews)
    correct = sum(1 for r in reviews if r.is_correct)

    db.commit()

    today = stats_service.today_stat(db, user, now)
    counts = queue_counts(db, user, now)
    return SessionSummaryOut(
        session_id=session.id,
        completed_count=completed,
        correct_count=correct,
        accuracy=round(correct / completed * 100, 1) if completed else 0.0,
        new_count=new_count,
        seconds=seconds,
        streak=stats_service.streak(db, user, stats_service.local_day(user, now)),
        goal_met=bool(today and today.goal_met),
        done_today=today.reviews_count if today else 0,
        goal=user.settings.daily_goal,
        next_due_count=counts["due"],
        mistakes=mistakes,
    )


@router.post("/sessions/{session_id}/abandon", status_code=204)
def abandon_session(
    session_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    """Close a session without finishing it. Answers already recorded stay —
    the schedule they produced is real."""
    session = _session_or_404(db, user, session_id)
    if session.finished_at is None:
        session.finished_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/items/{item_id}/suspend", response_model=dict)
def suspend_item(
    item_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Take a word out of rotation without losing its history.

    For the word that keeps coming back wrong and poisoning every session —
    better parked than endlessly failed.
    """
    states = (
        db.execute(
            select(UserItemState).where(
                UserItemState.user_id == user.id, UserItemState.item_id == item_id
            )
        )
        .scalars()
        .all()
    )
    if not states:
        raise not_found("CARD_NOT_FOUND", "Nie uczysz się jeszcze tej pozycji.")
    for state in states:
        state.suspended = not state.suspended
    db.commit()
    return {"suspended": states[0].suspended}


@router.post("/items/{item_id}/reset", status_code=204)
def reset_item(
    item_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    """Forget the schedule for this word and learn it from scratch.

    The review log stays — it is append-only history, not state.
    """
    states = (
        db.execute(
            select(UserItemState).where(
                UserItemState.user_id == user.id, UserItemState.item_id == item_id
            )
        )
        .scalars()
        .all()
    )
    for state in states:
        db.delete(state)
    db.commit()


@router.get("/stats/overview")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    by_state = dict(
        db.execute(
            select(UserItemState.state, func.count())
            .where(UserItemState.user_id == user.id)
            .group_by(UserItemState.state)
        ).all()
    )
    total_items = db.execute(select(func.count()).select_from(Item).where(Item.verified.is_(True))).scalar_one()
    reviews_total = db.execute(
        select(func.count()).select_from(Review).where(Review.user_id == user.id)
    ).scalar_one()
    correct_total = db.execute(
        select(func.count()).select_from(Review).where(Review.user_id == user.id, Review.is_correct.is_(True))
    ).scalar_one()
    return {
        "streak": stats_service.streak(db, user, stats_service.local_day(user, now)),
        "cards_by_state": by_state,
        "items_total": total_items,
        "reviews_total": reviews_total,
        "accuracy": round(correct_total / reviews_total * 100, 1) if reviews_total else 0.0,
    }
