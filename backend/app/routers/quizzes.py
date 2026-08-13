"""Quizzes — checking what you know, separately from the review schedule.

A quiz does not move FSRS cards by default: a test is not a study session, and
scoring one should not quietly reschedule everything it touched. Mistakes can
be pushed into tomorrow's queue explicitly.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.errors import conflict, not_found, unprocessable
from app.models import Item, Quiz, QuizAnswer, QuizAttempt, User, UserItemState
from app.schemas import (
    QuizAnswersIn,
    QuizAttemptOut,
    QuizCreateIn,
    QuizHistoryOut,
    QuizMistakeOut,
    QuizOut,
    QuizQuickIn,
    QuizResultOut,
)
from app.services import grader
from app.services.task_builder import build_quiz

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])

DEFAULT_MODES = ["mcq_pt_pl", "mcq_pl_pt", "typing"]


def _public(questions: list[dict]) -> list[dict]:
    """Strip the answer key. In a quiz — unlike a study session — the score is
    the point, so grading stays entirely on the server."""
    out = []
    for question in questions:
        clean = {
            k: v
            for k, v in question.items()
            if k not in ("answer_index", "expected", "alternatives", "back")
        }
        if question["mode"] in ("typing", "cloze", "word_bank"):
            clean.pop("pt", None)
            # Hiding the written form but leaving the recording would be a
            # hole, not a safeguard — you would just press play and hear the
            # answer. The example sentence stays: it is a hint, not the key.
            audio = dict(clean.get("audio") or {})
            audio.pop("pt", None)
            audio.pop("pt_slow", None)
            clean["audio"] = audio
        if question["mode"] == "listening":
            # Here it is the other way round: the recording is the question and
            # the written word would give it away.
            clean.pop("pt", None)
        out.append(clean)
    return out


def _attempt_or_404(db: Session, user: User, attempt_id: uuid.UUID) -> QuizAttempt:
    attempt = db.get(QuizAttempt, attempt_id)
    if attempt is None or attempt.user_id != user.id:
        raise not_found("ATTEMPT_NOT_FOUND", "Nie ma takiego podejścia.")
    return attempt


def _start(
    db: Session,
    user: User,
    *,
    name: str,
    count: int,
    deck_ids: list[uuid.UUID] | None,
    level: str | None,
    modes: list[str] | None,
    quiz: Quiz | None = None,
) -> QuizAttempt:
    tasks = build_quiz(db, user, count=count, deck_ids=deck_ids, level=level, modes=modes)
    if not tasks:
        raise unprocessable(
            "NOT_ENOUGH_ITEMS", "Za mało pozycji, żeby ułożyć ten test. Poluzuj filtry."
        )
    questions = [t.as_dict() for t in tasks]
    attempt = QuizAttempt(
        quiz_id=quiz.id if quiz else None,
        user_id=user.id,
        name=name,
        questions={"questions": questions},
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


@router.get("", response_model=list[QuizOut])
def list_quizzes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    quizzes = (
        db.execute(select(Quiz).where(Quiz.owner_id == user.id).order_by(Quiz.created_at.desc()))
        .scalars()
        .all()
    )
    out = []
    for quiz in quizzes:
        last = (
            db.execute(
                select(QuizAttempt.score)
                .where(QuizAttempt.quiz_id == quiz.id, QuizAttempt.finished_at.is_not(None))
                .order_by(QuizAttempt.finished_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        data = QuizOut.model_validate(quiz)
        data.last_score = float(last) if last is not None else None
        out.append(data)
    return out


@router.post("", response_model=QuizOut, status_code=201)
def create_quiz(
    body: QuizCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    quiz = Quiz(
        owner_id=user.id,
        name=body.name,
        config={
            "deck_ids": [str(d) for d in body.deck_ids or []],
            "cefr_level": body.cefr_level,
            "count": body.count,
            "modes": body.modes or DEFAULT_MODES,
            "time_limit_s": body.time_limit_s,
        },
    )
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    return QuizOut.model_validate(quiz)


@router.delete("/{quiz_id}", status_code=204)
def delete_quiz(
    quiz_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None or quiz.owner_id != user.id:
        raise not_found("QUIZ_NOT_FOUND", "Nie ma takiego testu.")
    db.delete(quiz)
    db.commit()


@router.post("/quick", response_model=QuizAttemptOut, status_code=201)
def quick_quiz(
    body: QuizQuickIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    attempt = _start(
        db,
        user,
        name="Szybki quiz",
        count=body.count,
        deck_ids=body.deck_ids,
        level=body.cefr_level,
        modes=body.modes or DEFAULT_MODES,
    )
    return QuizAttemptOut(
        id=attempt.id,
        name=attempt.name,
        started_at=attempt.started_at,
        time_limit_s=None,
        questions=_public(attempt.questions["questions"]),
    )


@router.post("/{quiz_id}/attempts", response_model=QuizAttemptOut, status_code=201)
def start_attempt(
    quiz_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None or quiz.owner_id != user.id:
        raise not_found("QUIZ_NOT_FOUND", "Nie ma takiego testu.")
    config = quiz.config or {}
    attempt = _start(
        db,
        user,
        name=quiz.name,
        count=int(config.get("count", 10)),
        deck_ids=[uuid.UUID(d) for d in config.get("deck_ids") or []] or None,
        level=config.get("cefr_level"),
        modes=config.get("modes") or DEFAULT_MODES,
        quiz=quiz,
    )
    return QuizAttemptOut(
        id=attempt.id,
        name=attempt.name,
        started_at=attempt.started_at,
        time_limit_s=config.get("time_limit_s"),
        questions=_public(attempt.questions["questions"]),
    )


@router.post("/attempts/{attempt_id}/answers", status_code=204)
def record_answers(
    attempt_id: uuid.UUID,
    body: QuizAnswersIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Answers are stored without revealing anything — the score comes at submit."""
    attempt = _attempt_or_404(db, user, attempt_id)
    if attempt.finished_at is not None:
        raise conflict("ATTEMPT_FINISHED", "To podejście jest już zakończone.")

    questions = {q["index"]: q for q in attempt.questions["questions"]}
    seen = {
        index
        for index in db.execute(
            select(QuizAnswer.question_index).where(QuizAnswer.attempt_id == attempt.id)
        ).scalars()
    }

    for answer in body.answers:
        question = questions.get(answer.index)
        if question is None:
            raise unprocessable("UNKNOWN_QUESTION", f"Pytanie {answer.index} nie należy do tego testu.")
        if answer.index in seen:
            continue

        mode = question["mode"]
        if mode in ("mcq_pt_pl", "mcq_pl_pt"):
            options = question.get("options", [])
            picked = (
                options[answer.selected_index]
                if answer.selected_index is not None and 0 <= answer.selected_index < len(options)
                else None
            )
            is_correct = answer.selected_index == question.get("answer_index")
            match = None
        else:
            expected = question.get("expected") or question.get("pt", "")
            picked = answer.user_answer or ""
            result = grader.grade(
                picked,
                expected,
                alternatives=list(question.get("alternatives") or []),
                accent_strict=bool(user.settings.accent_strict),
            )
            is_correct = result.is_correct
            match = result.match.value

        db.add(
            QuizAnswer(
                attempt_id=attempt.id,
                item_id=uuid.UUID(question["item_id"]),
                question_index=answer.index,
                mode=mode,
                user_answer=picked,
                is_correct=is_correct,
                match=match,
                elapsed_ms=answer.elapsed_ms,
            )
        )
        seen.add(answer.index)

    db.commit()


@router.post("/attempts/{attempt_id}/submit", response_model=QuizResultOut)
def submit_attempt(
    attempt_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    attempt = _attempt_or_404(db, user, attempt_id)
    questions = {q["index"]: q for q in attempt.questions["questions"]}
    answers = (
        db.execute(
            select(QuizAnswer)
            .where(QuizAnswer.attempt_id == attempt.id)
            .order_by(QuizAnswer.question_index)
        )
        .scalars()
        .all()
    )

    total = len(questions)
    correct = sum(1 for a in answers if a.is_correct)
    score = round(correct / total * 100, 1) if total else 0.0

    if attempt.finished_at is None:
        attempt.finished_at = datetime.now(timezone.utc)
        attempt.score = score

    answered = {a.question_index for a in answers}
    mistakes: list[QuizMistakeOut] = []
    by_index = {a.question_index: a for a in answers}
    for index, question in sorted(questions.items()):
        answer = by_index.get(index)
        if answer is not None and answer.is_correct:
            continue
        mistakes.append(
            QuizMistakeOut(
                item_id=uuid.UUID(question["item_id"]),
                pt=question.get("pt") or question.get("expected", ""),
                pl=question.get("pl", ""),
                user_answer=answer.user_answer if answer else None,
                mode=question["mode"],
                skipped=index not in answered,
            )
        )

    previous = (
        db.execute(
            select(QuizAttempt.score)
            .where(
                QuizAttempt.user_id == user.id,
                QuizAttempt.quiz_id == attempt.quiz_id,
                QuizAttempt.id != attempt.id,
                QuizAttempt.finished_at.is_not(None),
            )
            .order_by(QuizAttempt.finished_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )

    db.commit()
    return QuizResultOut(
        attempt_id=attempt.id,
        name=attempt.name,
        score=score,
        total=total,
        correct=correct,
        seconds=sum(a.elapsed_ms for a in answers) // 1000,
        previous_score=float(previous) if previous is not None else None,
        mistakes=mistakes,
    )


@router.post("/attempts/{attempt_id}/to-reviews", response_model=dict)
def mistakes_to_reviews(
    attempt_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Put the words missed in a test at the front of tomorrow's queue.

    Only the due date moves — stability and difficulty stay where the real
    review history put them, so one bad test does not rewrite the schedule.
    """
    attempt = _attempt_or_404(db, user, attempt_id)
    questions = {q["index"]: q for q in attempt.questions["questions"]}
    answers = (
        db.execute(select(QuizAnswer).where(QuizAnswer.attempt_id == attempt.id)).scalars().all()
    )
    answered = {a.question_index: a for a in answers}

    tomorrow = datetime.now(timezone.utc) + timedelta(hours=16)
    touched = 0
    for index, question in questions.items():
        answer = answered.get(index)
        if answer is not None and answer.is_correct:
            continue
        item_id = uuid.UUID(question["item_id"])
        if db.get(Item, item_id) is None:
            continue
        state = db.get(UserItemState, (user.id, item_id, "recognition"))
        if state is None:
            db.add(
                UserItemState(
                    user_id=user.id,
                    item_id=item_id,
                    direction="recognition",
                    state="new",
                    due=tomorrow,
                )
            )
        elif state.due > tomorrow:
            state.due = tomorrow
        else:
            continue
        touched += 1

    db.commit()
    return {"scheduled": touched}


@router.get("/attempts", response_model=list[QuizHistoryOut])
def attempt_history(
    limit: int = 20, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    rows = (
        db.execute(
            select(QuizAttempt)
            .where(QuizAttempt.user_id == user.id, QuizAttempt.finished_at.is_not(None))
            .order_by(QuizAttempt.finished_at.desc())
            .limit(min(limit, 100))
        )
        .scalars()
        .all()
    )
    return [
        QuizHistoryOut(
            attempt_id=row.id,
            quiz_id=row.quiz_id,
            name=row.name,
            score=float(row.score) if row.score is not None else 0.0,
            finished_at=row.finished_at,
            total=len(row.questions.get("questions", [])),
        )
        for row in rows
    ]
