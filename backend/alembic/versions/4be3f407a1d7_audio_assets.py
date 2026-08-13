"""audio_assets — nagrania wymowy trzymane w bazie

Bajty MP3 lądują w kolumnie zamiast w osobnym magazynie plików: cała biblioteka
to kilkaset klipów po kilkanaście kilobajtów, więc nie ma czego skalować, a
nagrania wchodzą do tej samej kopii zapasowej co słowa, których dotyczą.

Revision ID: 4be3f407a1d7
Revises: 08e7a31b6732
Create Date: 2026-08-13 17:26:57.406131
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '4be3f407a1d7'
down_revision: str | None = '08e7a31b6732'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('audio_assets',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('cache_key', sa.String(length=64), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('voice', sa.String(length=64), nullable=False),
    sa.Column('speed', sa.Numeric(precision=3, scale=2), nullable=False),
    sa.Column('mime', sa.String(length=32), nullable=False),
    sa.Column('data', sa.LargeBinary(), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('char_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audio_assets_cache_key'), 'audio_assets', ['cache_key'], unique=True)

    # Konta założone wcześniej mają zapisany głos `pt-PT-Neural2-A` — nazwę,
    # której Google dla portugalskiego europejskiego nie oferuje. Nagrania
    # szuka się po nazwie głosu, więc bez tej poprawki żadne by się nie
    # dopasowało i wymowa byłaby cicha bez żadnego komunikatu o błędzie.
    op.execute(
        "UPDATE user_settings SET tts_voice = 'pt-PT-Wavenet-A' "
        "WHERE tts_voice = 'pt-PT-Neural2-A'"
    )

    # Tryb `listening` był wyłączony u wszystkich, bo bez nagrań nie dało się go
    # zrobić. Teraz się da, a pozostawienie go wyłączonym znaczyłoby, że nowa
    # funkcja nie działa, dopóki ktoś nie znajdzie przełącznika w ustawieniach.
    # Nadal można go wyłączyć ręcznie, a pozycje bez nagrania i tak go omijają.
    op.execute(
        "UPDATE user_settings SET enabled_modes = enabled_modes || '[\"listening\"]'::jsonb "
        "WHERE NOT (enabled_modes @> '[\"listening\"]'::jsonb)"
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_audio_assets_cache_key'), table_name='audio_assets')
    op.drop_table('audio_assets')
