"""Nauka zaczyna od słów

Zmienia domyślne nastawienie kolejki z „zwroty" na „słowa" — i przestawia na
słowa konta, które miały domyślne zwroty. Zwroty okazały się za trudne jako
pierwszy materiał; dłuższe z nich czekają teraz odłożone, z nietkniętym
postępem, i wracają po przełączeniu ustawienia.

Nic nie jest usuwane. Cofnięcie przywraca dawną wartość domyślną kolumny, ale
nie przestawia kont z powrotem — tego, kto wybrał słowa świadomie, nie da się
już odróżnić od tego, komu wybrała je migracja.

Revision ID: 2c72486549e3
Revises: 83163e4a0c74
Create Date: 2026-10-10
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "2c72486549e3"
down_revision: str | None = "83163e4a0c74"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("user_settings", "content_focus", server_default="words")
    op.execute(sa.text("UPDATE user_settings SET content_focus = 'words' WHERE content_focus = 'phrases'"))


def downgrade() -> None:
    op.alter_column("user_settings", "content_focus", server_default="phrases")
