"""„se faz favor” → „por favor” w zapisanych pozycjach

Treść startowa zmieniła „se faz favor” na „por favor”. Seed dopasowuje pozycje
po parze (pt, pl), więc sam nowy seed założyłby obok starych pozycji nowe —
a stare zostałyby w taliach z całym postępem w FSRS, jako duplikaty. Ta
migracja przemianowuje je na miejscu: postęp zostaje przy tej samej pozycji.

Osobne hasło „se faz favor” (obok istniejącego „por favor”) wypada z nauki:
zostaje w bazie razem z historią, ale nie jest już w żadnej talii i nie wraca
w powtórkach.

Pozycja, której nowa nazwa zderzyłaby się z już istniejącą, zostaje bez
zmian — lepszy jeden stary tekst niż wywrócona migracja.

Cofnięcie niczego nie robi: tekstu sprzed zmiany nie da się odtworzyć.

Revision ID: 5e1f0a9c2d7b
Revises: 2c72486549e3
Create Date: 2026-10-24
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "5e1f0a9c2d7b"
down_revision: str | None = "2c72486549e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _swap(column: str) -> str:
    return f"replace(replace({column}, 'se faz favor', 'por favor'), 'Se faz favor', 'Por favor')"


def upgrade() -> None:
    op.execute(sa.text(
        "DELETE FROM deck_items WHERE item_id IN (SELECT id FROM items WHERE lower(pt) = 'se faz favor')"
    ))
    op.execute(sa.text("UPDATE items SET verified = false WHERE lower(pt) = 'se faz favor'"))

    op.execute(sa.text(f"""
        UPDATE items AS i SET pt = {_swap('i.pt')}
        WHERE lower(i.pt) LIKE '%se faz favor%' AND lower(i.pt) <> 'se faz favor'
          AND NOT EXISTS (
            SELECT 1 FROM items AS other
            WHERE other.pt = {_swap('i.pt')} AND other.pl = i.pl AND other.id <> i.id
          )
    """))
    op.execute(sa.text(f"UPDATE items SET reply_pt = {_swap('reply_pt')} WHERE lower(reply_pt) LIKE '%se faz favor%'"))
    op.execute(sa.text(f"UPDATE examples SET pt = {_swap('pt')} WHERE lower(pt) LIKE '%se faz favor%'"))


def downgrade() -> None:
    pass
