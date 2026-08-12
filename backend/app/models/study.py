import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col

# Recognition (PT -> PL) and production (PL -> PT) are different skills and get
# separate schedules. Recognition always comes first; production unlocks once
# the word is recognised reliably.
DIRECTIONS = ("recognition", "production")
CARD_STATES = ("new", "learning", "review", "relearning")

# How many correct recognition answers unlock the production card.
PRODUCTION_UNLOCK_AT = 2
# A card that has been forgotten this many times is a leech.
LEECH_LAPSES = 6


class UserItemState(Base):
    """One scheduled card: a user, an item and a direction."""

    __tablename__ = "user_item_state"
    __table_args__ = (
        Index("ix_user_item_state_due", "user_id", "due"),
        Index("ix_user_item_state_user_item", "user_id", "item_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    direction: Mapped[str] = mapped_column(String(16), primary_key=True)

    state: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    stability: Mapped[float | None] = mapped_column(Float)
    difficulty: Mapped[float | None] = mapped_column(Float)
    due: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_reps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lapses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    step: Mapped[int | None] = mapped_column(Integer)
    suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    @property
    def is_leech(self) -> bool:
        return self.lapses >= LEECH_LAPSES


class Review(Base):
    """Append-only log of every answer. Never updated — it is what makes it
    possible to recompute the whole schedule later if FSRS parameters change."""

    __tablename__ = "reviews"
    __table_args__ = (
        # Answers are sent in batches from a queue that may be retried, so the
        # same question must not be able to land twice.
        UniqueConstraint("session_id", "question_index", name="uq_reviews_session_question"),
        Index("ix_reviews_user_time", "user_id", "reviewed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("study_sessions.id", ondelete="SET NULL")
    )
    question_index: Mapped[int | None] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    user_answer: Mapped[str | None] = mapped_column(Text)
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stability_after: Mapped[float | None] = mapped_column(Float)
    reviewed_at: Mapped[datetime] = created_at_col()


class StudySession(Base):
    __tablename__ = "study_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = created_at_col()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deck_ids: Mapped[list | None] = mapped_column(JSONB)
    # The generated task list, frozen. Lets a session resume after the app is
    # closed, and lets the server grade answers against what it actually asked.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class DailyStat(Base):
    __tablename__ = "daily_stats"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Calendar day in the user's own timezone — that is what a streak means.
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    reviews_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_spent_s: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    goal_met: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
