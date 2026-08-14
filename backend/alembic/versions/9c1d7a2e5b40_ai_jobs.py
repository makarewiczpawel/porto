"""ai_generation_jobs i ai_cache — rejestr wywołań modelu i ich koszt

Dwie tabele o różnych zadaniach. `ai_generation_jobs` jest księgą: co poszło do
modelu, co wróciło, ile tokenów i ile dolarów. Suma kosztów z bieżącego
miesiąca jest jedynym hamulcem wydatków, więc wiersz powstaje także przy
wywołaniu nieudanym. Ta sama tabela przechowuje propozycje zestawu między
wygenerowaniem a przeglądem — nic z modelu nie trafia do słownika bez
zatwierdzenia, więc propozycje muszą gdzieś przeczekać.

`ai_cache` pilnuje, żeby ta sama pomyłka nie kosztowała dwa razy.

Revision ID: 9c1d7a2e5b40
Revises: 4be3f407a1d7
Create Date: 2026-08-14 09:10:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '9c1d7a2e5b40'
down_revision: str | None = '4be3f407a1d7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'ai_generation_jobs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='ready'),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False, server_default=''),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost_usd', sa.Numeric(precision=10, scale=6), nullable=False, server_default='0'),
        sa.Column('deck_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['deck_id'], ['decks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ai_generation_jobs_kind'), 'ai_generation_jobs', ['kind'])
    op.create_index(op.f('ix_ai_generation_jobs_status'), 'ai_generation_jobs', ['status'])
    op.create_index(op.f('ix_ai_generation_jobs_user_id'), 'ai_generation_jobs', ['user_id'])
    # Budżet miesięczny sumuje koszty po dacie i robi to przy każdym wywołaniu.
    op.create_index('ix_ai_jobs_created_at', 'ai_generation_jobs', ['created_at'])

    op.create_table(
        'ai_cache',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('cache_key', sa.String(length=64), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ai_cache_cache_key'), 'ai_cache', ['cache_key'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_ai_cache_cache_key'), table_name='ai_cache')
    op.drop_table('ai_cache')
    op.drop_index('ix_ai_jobs_created_at', table_name='ai_generation_jobs')
    op.drop_index(op.f('ix_ai_generation_jobs_user_id'), table_name='ai_generation_jobs')
    op.drop_index(op.f('ix_ai_generation_jobs_status'), table_name='ai_generation_jobs')
    op.drop_index(op.f('ix_ai_generation_jobs_kind'), table_name='ai_generation_jobs')
    op.drop_table('ai_generation_jobs')
