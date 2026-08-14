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
    audio_url: str | None = None


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
    # Wypełniane przez router, gdy nagranie istnieje — sam model nie wie nic
    # o syntezie mowy.
    audio_url: str | None = None


class ItemDetailOut(ItemOut):
    examples: list[ExampleOut] = []
    cards: list[CardStateOut] = []
    decks: list[str] = []


class ItemCreateIn(BaseModel):
    pt: str = Field(min_length=1, max_length=200)
    pl: str = Field(min_length=1, max_length=200)
    type: Literal["word", "phrase", "sentence"] = "word"
    article: str | None = Field(default=None, max_length=8)
    gender: Literal["m", "f", "mf"] | None = None
    part_of_speech: str | None = Field(default=None, max_length=16)
    cefr_level: Literal["A1", "A2", "B1", "B2", "C1"] = "A1"
    notes: str | None = Field(default=None, max_length=500)
    pt_alt: list[str] = Field(default_factory=list, max_length=5)
    pl_alt: list[str] = Field(default_factory=list, max_length=5)
    example_pt: str | None = Field(default=None, max_length=300)
    example_pl: str | None = Field(default=None, max_length=300)
    deck_id: uuid.UUID | None = None


class ItemPatchIn(BaseModel):
    pt: str | None = Field(default=None, min_length=1, max_length=200)
    pl: str | None = Field(default=None, min_length=1, max_length=200)
    article: str | None = Field(default=None, max_length=8)
    gender: Literal["m", "f", "mf"] | None = None
    part_of_speech: str | None = Field(default=None, max_length=16)
    cefr_level: Literal["A1", "A2", "B1", "B2", "C1"] | None = None
    notes: str | None = Field(default=None, max_length=500)
    pt_alt: list[str] | None = Field(default=None, max_length=5)
    pl_alt: list[str] | None = Field(default=None, max_length=5)


class DeckCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=300)
    icon: str | None = Field(default=None, max_length=16)


class ImportIn(BaseModel):
    #: Surowy CSV — wklejony tekst albo zawartość pliku.
    csv: str = Field(min_length=1, max_length=500_000)
    deck_name: str | None = Field(default=None, max_length=120)
    deck_id: uuid.UUID | None = None
    #: Sam podgląd: parsuje i raportuje, ale niczego nie zapisuje.
    dry_run: bool = False


class ImportRowError(BaseModel):
    line: int
    reason: str
    raw: str


class ImportOut(BaseModel):
    created: int
    updated: int
    skipped_duplicates: int
    deck_id: uuid.UUID | None
    #: Pierwsze wiersze po sparsowaniu — do podglądu przed zatwierdzeniem.
    preview: list[dict[str, Any]]
    errors: list[ImportRowError]


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
class CatchUpOut(BaseModel):
    """Plan nadrabiania po przerwie: ile zaległości i ile z nich na dziś."""

    backlog: int
    today: int
    days: int


class QueueSummaryOut(BaseModel):
    due: int
    new_available: int
    done_today: int
    goal: int
    streak: int
    goal_met: bool
    next_due_at: datetime | None
    catch_up: CatchUpOut | None = None


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


class MatchPairIn(BaseModel):
    """One pair from a matching round — the client reports whether it was
    joined correctly on the first try."""

    item_id: uuid.UUID
    is_correct: bool


class AnswerIn(BaseModel):
    index: int = Field(ge=0)
    rating: int | None = Field(default=None, ge=1, le=4)
    selected_index: int | None = Field(default=None, ge=0)
    user_answer: str | None = Field(default=None, max_length=500)
    #: Only for `matching`, which scores several cards at once.
    pairs: list[MatchPairIn] | None = Field(default=None, max_length=20)
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
    #: exact | accent | typo | wrong — only for typed answers.
    match: str | None = None
    #: Expected answer with the differing characters marked, e.g. `av»ó«`.
    diff: str | None = None
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


# ── quizy ─────────────────────────────────────────────────────────────────
class QuizCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    deck_ids: list[uuid.UUID] | None = None
    cefr_level: str | None = Field(default=None, max_length=2)
    count: int = Field(default=10, ge=3, le=100)
    modes: list[str] | None = None
    time_limit_s: int | None = Field(default=None, ge=30, le=3600)


class QuizOut(ORMModel):
    id: uuid.UUID
    name: str
    config: dict[str, Any]
    created_at: datetime
    last_score: float | None = None


class QuizQuickIn(BaseModel):
    count: int = Field(default=10, ge=3, le=50)
    deck_ids: list[uuid.UUID] | None = None
    cefr_level: str | None = Field(default=None, max_length=2)
    modes: list[str] | None = None
    time_limit_s: int | None = Field(default=None, ge=30, le=3600)


class QuizAttemptOut(BaseModel):
    id: uuid.UUID
    name: str
    started_at: datetime
    time_limit_s: int | None
    #: Questions without the answer key — a quiz is graded server-side only.
    questions: list[dict[str, Any]]


class QuizAnswerIn(BaseModel):
    index: int = Field(ge=0)
    selected_index: int | None = Field(default=None, ge=0)
    user_answer: str | None = Field(default=None, max_length=500)
    elapsed_ms: int = Field(default=0, ge=0, le=600_000)


class QuizAnswersIn(BaseModel):
    answers: list[QuizAnswerIn] = Field(min_length=1, max_length=100)


class QuizMistakeOut(BaseModel):
    item_id: uuid.UUID
    pt: str
    pl: str
    user_answer: str | None
    mode: str
    skipped: bool = False


class QuizResultOut(BaseModel):
    attempt_id: uuid.UUID
    name: str
    score: float
    total: int
    correct: int
    seconds: int
    previous_score: float | None
    mistakes: list[QuizMistakeOut]


class QuizHistoryOut(BaseModel):
    attempt_id: uuid.UUID
    quiz_id: uuid.UUID | None
    name: str
    score: float
    finished_at: datetime | None
    total: int


Direction = Literal["recognition", "production"]
