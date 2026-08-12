import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_col

ITEM_TYPES = ("word", "phrase", "sentence")
SOURCES = ("seed", "ai", "user", "import")
CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1")


class Item(Base):
    """One unit of study: a word, a fixed phrase or a whole sentence."""

    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("pt", "pl", name="uq_items_pt_pl"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="word")
    pt: Mapped[str] = mapped_column(Text, nullable=False)
    pl: Mapped[str] = mapped_column(Text, nullable=False)
    pl_alt: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    pt_alt: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    variant: Mapped[str] = mapped_column(String(8), nullable=False, default="pt-PT")
    part_of_speech: Mapped[str | None] = mapped_column(String(16), index=True)
    gender: Mapped[str | None] = mapped_column(String(2))
    article: Mapped[str | None] = mapped_column(String(8))
    plural: Mapped[str | None] = mapped_column(Text)
    ipa: Mapped[str | None] = mapped_column(Text)
    cefr_level: Mapped[str] = mapped_column(String(2), nullable=False, default="A1", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(8), nullable=False, default="seed")
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = created_at_col()

    examples: Mapped[list["Example"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="Example.created_at"
    )
    deck_links: Mapped[list["DeckItem"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )

    @property
    def display_pt(self) -> str:
        """Nouns are learned with their article — `casa` and `a casa` are not
        the same thing to remember."""
        if self.article:
            return f"{self.article} {self.pt}"
        return self.pt


class Example(Base):
    __tablename__ = "examples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pt: Mapped[str] = mapped_column(Text, nullable=False)
    pl: Mapped[str] = mapped_column(Text, nullable=False)
    cloze_start: Mapped[int | None] = mapped_column(Integer)
    cloze_end: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(8), nullable=False, default="seed")
    created_at: Mapped[datetime] = created_at_col()

    item: Mapped[Item] = relationship(back_populates="examples")


class Deck(Base):
    __tablename__ = "decks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    cefr_level: Mapped[str | None] = mapped_column(String(8))
    icon: Mapped[str | None] = mapped_column(String(16))
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = created_at_col()

    item_links: Mapped[list["DeckItem"]] = relationship(
        back_populates="deck", cascade="all, delete-orphan", order_by="DeckItem.position"
    )


class DeckItem(Base):
    __tablename__ = "deck_items"

    deck_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("decks.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    deck: Mapped[Deck] = relationship(back_populates="item_links")
    item: Mapped[Item] = relationship(back_populates="deck_links")
