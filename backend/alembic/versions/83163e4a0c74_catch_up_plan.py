"""Plan nadrabiania: termin i punkt startu

Dwie kolumny, obie puste, dopóki zaległości nie przekroczą progu. Bez nich
komunikat „w 7 dni wrócisz na bieżąco" liczył się codziennie od nowa i codziennie
wychodziło to samo — obietnica, która nigdy się nie przybliża.

Revision ID: 83163e4a0c74
Revises: b7d2f1c93a05
Create Date: 2026-09-12 06:11:35.251313
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '83163e4a0c74'
down_revision: str | None = 'b7d2f1c93a05'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('user_settings', sa.Column('catch_up_until', sa.Date(), nullable=True))
    op.add_column('user_settings', sa.Column('catch_up_from', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('user_settings', 'catch_up_from')
    op.drop_column('user_settings', 'catch_up_until')
