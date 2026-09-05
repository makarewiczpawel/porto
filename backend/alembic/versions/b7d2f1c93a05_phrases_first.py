"""Zwroty zamiast słówek: odpowiedź rozmówcy i nastawienie kolejki

Dwie zmiany pod jedną decyzję produktową — uczymy się gotowych zwrotów, nie
pojedynczych wyrazów.

`reply_pt` / `reply_pl` trzymają to, co usłyszysz w odpowiedzi. Bez tego zwrot
jest połową umiejętności: „Quanto custa?" nic nie daje, jeśli „São dois e
cinquenta" odbija się od ucha.

`content_focus` mówi kolejce, czego dokładać przy nowym materiale. Istniejące
konta dostają „phrases", bo to jest nowe domyślne podejście; słowa zostają w
bazie i wracają po przestawieniu ustawienia.

Revision ID: b7d2f1c93a05
Revises: 9c1d7a2e5b40
Create Date: 2026-09-05 09:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b7d2f1c93a05'
down_revision: str | None = '9c1d7a2e5b40'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('items', sa.Column('reply_pt', sa.Text(), nullable=True))
    op.add_column('items', sa.Column('reply_pl', sa.Text(), nullable=True))
    op.add_column(
        'user_settings',
        sa.Column('content_focus', sa.String(length=8), nullable=False, server_default='phrases'),
    )


def downgrade() -> None:
    op.drop_column('user_settings', 'content_focus')
    op.drop_column('items', 'reply_pl')
    op.drop_column('items', 'reply_pt')
