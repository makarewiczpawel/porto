import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_col, uuid_pk

# Modes the session builder may pick from. Phase 1 ships the first three;
# the rest arrive in phase 2/3 and are already accepted in settings so the
# column does not need a migration then.
ALL_MODES = [
    "flashcard",
    "mcq_pt_pl",
    "mcq_pl_pt",
    "typing",
    "cloze",
    "matching",
    "word_bank",
    "listening",
]
PHASE1_MODES = ["flashcard", "mcq_pt_pl", "mcq_pl_pt"]
# What a new account starts with. `listening` waits for audio in phase 3.
DEFAULT_MODES = [
    "flashcard",
    "mcq_pt_pl",
    "mcq_pl_pt",
    "typing",
    "cloze",
    "matching",
    "word_bank",
]


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Warsaw")
    created_at: Mapped[datetime] = created_at_col()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    settings: Mapped["UserSettings"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    daily_goal: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    new_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    review_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    desired_retention: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=0.90)
    enabled_modes: Mapped[list] = mapped_column(JSONB, nullable=False, default=lambda: list(DEFAULT_MODES))
    tts_voice: Mapped[str] = mapped_column(String(64), nullable=False, default="pt-PT-Neural2-A")
    tts_speed: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=1.00)
    autoplay_audio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    accent_strict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped[User] = relationship(back_populates="settings")
