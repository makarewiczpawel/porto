import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col

# Rodzaje wywołań. Trzymane w jednej tabeli, bo wszystkie kosztują z tego
# samego budżetu i miesięczne zużycie ma być jedną sumą, a nie czterema.
AI_KINDS = ("set", "explain", "grade", "examples")
AI_STATUSES = ("ready", "accepted", "failed")


class AiJob(Base):
    """Jedno wywołanie modelu: co poszło, co wróciło i ile to kosztowało.

    Tabela pełni dwie role naraz. Po pierwsze jest rejestrem kosztów — suma
    `cost_usd` z bieżącego miesiąca decyduje, czy kolejne wywołanie w ogóle
    dojdzie do skutku. Po drugie przechowuje propozycje wygenerowanego zestawu
    między wygenerowaniem a przeglądem: nic z AI nie trafia do słownika bez
    zatwierdzenia, więc propozycje muszą gdzieś przeczekać ten moment, a
    `result` jest tym miejscem.

    Wywołania nieudane też tu lądują, z `status="failed"` i powodem w `error`.
    Kosztowały tokeny wejściowe, więc pominięcie ich zaniżałoby rachunek.
    """

    __tablename__ = "ai_generation_jobs"
    # Budżet miesięczny sumuje koszty po dacie przy każdym wywołaniu modelu.
    __table_args__ = (Index("ix_ai_jobs_created_at", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ready", index=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Numeric, nie float — to pieniądze, a suma miesięczna liczona jest w bazie.
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    deck_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("decks.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = created_at_col()


class AiCacheEntry(Base):
    """Odpowiedź na pytanie, które ktoś już zadał.

    Ta sama pomyłka w tym samym słowie zdarza się wielokrotnie — i za każdym
    razem zasługuje na to samo wyjaśnienie. Klucz to skrót z rodzaju wywołania
    i jego treści, więc drugie pytanie nie kosztuje ani grosza, ani sekundy
    czekania.
    """

    __tablename__ = "ai_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_col()
