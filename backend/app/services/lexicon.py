"""Drobiazgi wspólne dla każdego miejsca, które dopisuje coś do słownika.

Ręczne dodanie pozycji, import listy z pliku i przegląd zestawu z AI robią na
końcu to samo: zakładają talię, odklejają rodzajnik od hasła i wpinają pozycję
w kolejkę nauki. Reguły muszą być identyczne we wszystkich trzech, bo różnica
objawiłaby się dopiero na fiszce — jako „a a esplanada" albo jako słowo, które
nigdy nie trafia do sesji.
"""

import re
import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Deck, User

DEFAULT_DECK_NAME = "Moje słówka"
ARTICLES = ("a", "o", "as", "os", "um", "uma")


def slugify(name: str, user_id: uuid.UUID) -> str:
    """Slug talii bierze kawałek identyfikatora właściciela.

    Dwie osoby mogą nazwać swoją talię „Praca" i obie mają do tego prawo, a
    `slug` jest unikalny w całej bazie.
    """
    base = re.sub(
        r"[^a-z0-9]+",
        "-",
        unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode(),
    ).strip("-")
    return f"{base or 'talia'}-{user_id.hex[:6]}"


def split_article(pt: str, article: str | None) -> tuple[str, str | None]:
    """Rodzajnik trzymamy w osobnej kolumnie, ale ludzie piszą go w słowie.

    Bez tego „a esplanada" z rodzajnikiem „a" wyświetla się jako
    „a a esplanada". Doklejamy go z powrotem przy wyświetlaniu, więc tutaj musi
    zniknąć z samego hasła.
    """
    text = pt.strip()
    lowered = text.lower()
    if article:
        prefix = f"{article.strip().lower()} "
        if lowered.startswith(prefix):
            return text[len(prefix):].strip(), article.strip()
        return text, article.strip()
    for candidate in ARTICLES:
        if lowered.startswith(f"{candidate} "):
            return text[len(candidate) + 1:].strip(), candidate
    return text, None


def default_deck(db: Session, user: User) -> Deck:
    """Prywatna talia, do której trafia wszystko dodane bez wskazania miejsca.

    Kolejka nauki dobiera nowe pozycje przez talie — słowo poza jakąkolwiek
    talią istniałoby w słowniku, ale nigdy nie pojawiłoby się w sesji. Zamiast
    zmuszać do zakładania talii przed dodaniem pierwszego słowa, zakładamy ją
    po cichu przy pierwszej potrzebie.
    """
    slug = f"moje-{user.id.hex[:6]}"
    deck = db.execute(select(Deck).where(Deck.slug == slug)).scalar_one_or_none()
    if deck is None:
        deck = Deck(
            slug=slug,
            name=DEFAULT_DECK_NAME,
            description="Pozycje dodane ręcznie i zaimportowane.",
            icon="✍️",
            is_shared=False,
            owner_id=user.id,
            position=100,
        )
        db.add(deck)
        db.flush()
    return deck
