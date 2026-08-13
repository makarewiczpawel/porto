import uuid
from datetime import datetime

from sqlalchemy import Integer, LargeBinary, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col


class AudioAsset(Base):
    """One synthesised recording, stored as bytes.

    The audio lives in the database rather than in object storage. The whole
    library is a few hundred clips of a few kilobytes each — well under the
    size where a bucket starts paying for itself, and this way the recordings
    ride along in the same backup as the words they belong to, with no second
    account and no second set of credentials to keep alive.

    `cache_key` is a hash of everything that changes the sound: the text, the
    voice and the speed. Identical requests therefore find the existing row and
    the paid synthesis runs exactly once per distinct recording.
    """

    __tablename__ = "audio_assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    voice: Mapped[str] = mapped_column(String(64), nullable=False)
    speed: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=1.00)
    mime: Mapped[str] = mapped_column(String(32), nullable=False, default="audio/mpeg")
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="google")
    # Billing is per character of input, so the length is worth keeping next to
    # the row that caused the charge — the monthly usage report reads this
    # instead of re-measuring text that may since have been edited.
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = created_at_col()
