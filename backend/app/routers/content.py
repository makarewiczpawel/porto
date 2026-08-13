import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import get_current_user
from app.errors import not_found
from app.models import Deck, DeckItem, Item, User, UserItemState
from app.schemas import (
    CardStateOut,
    DeckDetailOut,
    DeckOut,
    ItemDetailOut,
    ItemOut,
    PageOut,
    SettingsOut,
    SettingsPatch,
)
from app.services.task_builder import audio_index, deck_counts

router = APIRouter(prefix="/api", tags=["content"])


def _with_audio(db: Session, rows: list[Item], user: User) -> list[ItemOut]:
    """Pozycje z adresem wymowy, jednym zapytaniem na całą listę.

    Każde miejsce zwracające listę słów musi przejść przez tę funkcję —
    inaczej gdzieś w aplikacji głośnik po cichu przestaje działać, bo pozycja
    wygląda na taką bez nagrania. Tak właśnie wyglądał widok talii, zanim to
    powstało.
    """
    recordings = audio_index(db, rows, user.settings.tts_voice, include_slow=False)
    out = []
    for row in rows:
        entry = ItemOut.model_validate(row)
        entry.audio_url = recordings.get(row.id, {}).get("pt")
        out.append(entry)
    return out


@router.get("/settings", response_model=SettingsOut)
def get_settings(user: User = Depends(get_current_user)) -> SettingsOut:
    return SettingsOut.model_validate(user.settings)


@router.patch("/settings", response_model=SettingsOut)
def patch_settings(
    body: SettingsPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SettingsOut:
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user.settings, field, value)
    db.commit()
    db.refresh(user.settings)
    return SettingsOut.model_validate(user.settings)


@router.get("/items", response_model=PageOut)
def list_items(
    search: str | None = Query(default=None, max_length=100),
    level: str | None = Query(default=None, max_length=2),
    type: str | None = Query(default=None, max_length=16),
    pos: str | None = Query(default=None, max_length=16),
    deck_id: uuid.UUID | None = None,
    verified: bool | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PageOut:
    query = select(Item)
    count_query = select(func.count(func.distinct(Item.id))).select_from(Item)

    filters = []
    if search:
        needle = f"%{search.strip().lower()}%"
        filters.append(or_(func.lower(Item.pt).like(needle), func.lower(Item.pl).like(needle)))
    if level:
        filters.append(Item.cefr_level == level.upper())
    if type:
        filters.append(Item.type == type)
    if pos:
        filters.append(Item.part_of_speech == pos)
    if verified is not None:
        filters.append(Item.verified.is_(verified))

    if deck_id is not None:
        query = query.join(DeckItem, DeckItem.item_id == Item.id).where(DeckItem.deck_id == deck_id)
        count_query = count_query.join(DeckItem, DeckItem.item_id == Item.id).where(
            DeckItem.deck_id == deck_id
        )

    for condition in filters:
        query = query.where(condition)
        count_query = count_query.where(condition)

    total = db.execute(count_query).scalar_one()
    rows = (
        db.execute(query.order_by(Item.pt.asc()).offset((page - 1) * per_page).limit(per_page))
        .scalars()
        .unique()
        .all()
    )
    return PageOut(
        items=_with_audio(db, list(rows), user), total=total, page=page, per_page=per_page
    )


@router.get("/items/{item_id}", response_model=ItemDetailOut)
def get_item(
    item_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ItemDetailOut:
    item = db.execute(
        select(Item).options(selectinload(Item.examples)).where(Item.id == item_id)
    ).scalar_one_or_none()
    if item is None:
        raise not_found("ITEM_NOT_FOUND", "Nie ma takiej pozycji.")

    cards = (
        db.execute(
            select(UserItemState).where(
                UserItemState.user_id == user.id, UserItemState.item_id == item_id
            )
        )
        .scalars()
        .all()
    )
    deck_names = (
        db.execute(
            select(Deck.name).join(DeckItem, DeckItem.deck_id == Deck.id).where(DeckItem.item_id == item_id)
        )
        .scalars()
        .all()
    )

    out = ItemDetailOut.model_validate(item)
    recordings = audio_index(db, [item], user.settings.tts_voice, include_slow=False).get(item.id, {})
    out.audio_url = recordings.get("pt")
    # Zdanie przykładowe ma własne nagranie — tego, jak słowo brzmi w zdaniu,
    # nie da się usłyszeć z wymowy samego hasła.
    for example in out.examples:
        if example.pt == (item.examples[0].pt if item.examples else None):
            example.audio_url = recordings.get("example")
    out.cards = [
        CardStateOut(
            direction=c.direction,
            state=c.state,
            due=c.due,
            reps=c.reps,
            lapses=c.lapses,
            suspended=c.suspended,
        )
        for c in cards
    ]
    out.decks = list(deck_names)
    return out


@router.get("/decks", response_model=list[DeckOut])
def list_decks(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[DeckOut]:
    now = datetime.now(timezone.utc)
    decks = (
        db.execute(
            select(Deck)
            .where(or_(Deck.is_shared.is_(True), Deck.owner_id == user.id))
            .order_by(Deck.position.asc(), Deck.name.asc())
        )
        .scalars()
        .all()
    )
    counts = deck_counts(db, user, now)
    out = []
    for deck in decks:
        data = DeckOut.model_validate(deck)
        stats = counts.get(deck.id, {})
        data.total = stats.get("total", 0)
        data.due = stats.get("due", 0)
        data.learned = stats.get("learned", 0)
        data.untouched = stats.get("untouched", data.total)
        out.append(data)
    return out


@router.get("/decks/{deck_id}", response_model=DeckDetailOut)
def get_deck(
    deck_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=100, ge=1, le=300),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeckDetailOut:
    deck = db.execute(
        select(Deck).where(
            Deck.id == deck_id, or_(Deck.is_shared.is_(True), Deck.owner_id == user.id)
        )
    ).scalar_one_or_none()
    if deck is None:
        raise not_found("DECK_NOT_FOUND", "Nie ma takiej talii.")

    rows = (
        db.execute(
            select(Item)
            .join(DeckItem, DeckItem.item_id == Item.id)
            .where(DeckItem.deck_id == deck_id)
            .order_by(DeckItem.position.asc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        .scalars()
        .unique()
        .all()
    )

    now = datetime.now(timezone.utc)
    stats = deck_counts(db, user, now).get(deck.id, {})
    out = DeckDetailOut.model_validate(deck)
    out.total = stats.get("total", 0)
    out.due = stats.get("due", 0)
    out.learned = stats.get("learned", 0)
    out.untouched = stats.get("untouched", out.total)
    out.items = _with_audio(db, list(rows), user)
    return out
