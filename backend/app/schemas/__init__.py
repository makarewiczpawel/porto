import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── auth ──────────────────────────────────────────────────────────────────
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)
    invite_code: str
    timezone: str = "Europe/Warsaw"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class SettingsOut(ORMModel):
    daily_goal: int
    new_per_day: int
    review_limit: int
    desired_retention: float
    enabled_modes: list[str]
    tts_voice: str
    tts_speed: float
    autoplay_audio: bool
    accent_strict: bool


class SettingsPatch(BaseModel):
    daily_goal: int | None = Field(default=None, ge=1, le=500)
    new_per_day: int | None = Field(default=None, ge=0, le=100)
    review_limit: int | None = Field(default=None, ge=1, le=500)
    desired_retention: float | None = Field(default=None, ge=0.70, le=0.97)
    enabled_modes: list[str] | None = None
    tts_voice: str | None = Field(default=None, max_length=64)
    tts_speed: float | None = Field(default=None, ge=0.5, le=2.0)
    autoplay_audio: bool | None = None
    accent_strict: bool | None = None


class UserOut(ORMModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    timezone: str


class MeOut(BaseModel):
    user: UserOut
    settings: SettingsOut


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ── content ───────────────────────────────────────────────────────────────
class ExampleOut(ORMModel):
    id: uuid.UUID
    pt: str
    pl: str


class CardStateOut(BaseModel):
    direction: str
    state: str
    due: datetime
    reps: int
    lapses: int
    suspended: bool


class ItemOut(ORMModel):
    id: uuid.UUID
    type: str
    pt: str
    display_pt: str
    pl: str
    variant: str
    part_of_speech: str | None
    gender: str | None
    article: str | None
    plural: str | None
    ipa: str | None
    cefr_level: str
    notes: str | None
    source: str
    verified: bool


class ItemDetailOut(ItemOut):
    examples: list[ExampleOut] = []
    cards: list[CardStateOut] = []
    decks: list[str] = []


class PageOut(BaseModel):
    items: list[ItemOut]
    total: int
    page: int
    per_page: int


class DeckOut(ORMModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    cefr_level: str | None
    icon: str | None
    position: int
    total: int = 0
    due: int = 0
    learned: int = 0
    untouched: int = 0


class DeckDetailOut(DeckOut):
    items: list[ItemOut] = []


# ── study ─────────────────────────────────────────────────────────────────
class QueueSummaryOut(BaseModel):
    due: int
    new_available: int
    done_today: int
    goal: int
    streak: int
    goal_met: bool
    next_due_at: datetime | None


class SessionCreateIn(BaseModel):
    deck_ids: list[uuid.UUID] | None = None
    new_limit: int | None = Field(default=None, ge=0, le=100)
    review_limit: int | None = Field(default=None, ge=1, le=500)
    modes: list[str] | None = None


class SessionOut(BaseModel):
    id: uuid.UUID
    started_at: datetime
    planned_count: int
    completed_count: int
    tasks: list[dict[str, Any]]


class AnswerIn(BaseModel):
    index: int = Field(ge=0)
    rating: int | None = Field(default=None, ge=1, le=4)
    selected_index: int | None = Field(default=None, ge=0)
    user_answer: str | None = Field(default=None, max_length=500)
    elapsed_ms: int = Field(default=0, ge=0, le=600_000)


class AnswersIn(BaseModel):
    answers: list[AnswerIn] = Field(min_length=1, max_length=200)


class AnswerResultOut(BaseModel):
    index: int
    is_correct: bool
    rating: int
    correct_answer: str
    next_due: datetime
    next_due_label: str
    duplicate: bool = False


class AnswersOut(BaseModel):
    results: list[AnswerResultOut]


class MistakeOut(BaseModel):
    item_id: uuid.UUID
    pt: str
    pl: str
    user_answer: str | None
    mode: str


class SessionSummaryOut(BaseModel):
    session_id: uuid.UUID
    completed_count: int
    correct_count: int
    accuracy: float
    new_count: int
    seconds: int
    streak: int
    goal_met: bool
    done_today: int
    goal: int
    next_due_count: int
    mistakes: list[MistakeOut]


Direction = Literal["recognition", "production"]
