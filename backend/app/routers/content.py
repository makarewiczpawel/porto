import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import get_current_user
from app.errors import conflict, forbidden, not_found
from app.models import Deck, DeckItem, Example, Item, User, UserItemState
from app.schemas import (
    CardStateOut,
    DeckCreateIn,
    DeckDetailOut,
    DeckOut,
    ImportIn,
    ImportOut,
    ImportRowError,
    ItemCreateIn,
    ItemDetailOut,
    ItemOut,
    ItemPatchIn,
    PageOut,
    SettingsOut,
    SettingsPatch,
)
from app.services import importer
from app.services.lexicon import DEFAULT_DECK_NAME, default_deck, slugify, split_article
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


# ── własne pozycje i talie ────────────────────────────────────────────────
def _own_deck_or_404(db: Session, user: User, deck_id: uuid.UUID) -> Deck:
    deck = db.get(Deck, deck_id)
    if deck is None or (deck.owner_id != user.id and not deck.is_shared):
        raise not_found("DECK_NOT_FOUND", "Nie ma takiej talii.")
    return deck


@router.post("/decks", response_model=DeckOut, status_code=201)
def create_deck(
    body: DeckCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> DeckOut:
    deck = Deck(
        slug=slugify(body.name, user.id),
        name=body.name.strip(),
        description=body.description,
        icon=body.icon,
        is_shared=False,
        owner_id=user.id,
        # Własne talie idą po wbudowanych, których pozycje kończą się na 20.
        position=100,
    )
    db.add(deck)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict("DECK_EXISTS", "Masz już talię o tej nazwie.") from None
    db.refresh(deck)
    return DeckOut.model_validate(deck)


@router.post("/items", response_model=ItemDetailOut, status_code=201)
def create_item(
    body: ItemCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ItemDetailOut:
    pt, article = split_article(body.pt, body.article)
    pl = body.pl.strip()
    existing = db.execute(select(Item).where(Item.pt == pt, Item.pl == pl)).scalar_one_or_none()
    if existing is not None:
        raise conflict(
            "ITEM_EXISTS",
            "Taka pozycja już jest w słowniku.",
            item_id=str(existing.id),
        )

    item = Item(
        pt=pt,
        pl=pl,
        type=body.type,
        article=article,
        gender=body.gender,
        part_of_speech=body.part_of_speech,
        cefr_level=body.cefr_level,
        notes=body.notes,
        pt_alt=body.pt_alt or None,
        pl_alt=body.pl_alt or None,
        source="user",
        # Własne pozycje są zaufane od razu — dodał je człowiek, który się
        # uczy, a nie generator treści.
        verified=True,
        created_by=user.id,
    )
    db.add(item)
    db.flush()

    if body.example_pt and body.example_pl:
        db.add(
            Example(
                item_id=item.id,
                pt=body.example_pt.strip(),
                pl=body.example_pl.strip(),
                source="user",
            )
        )

    deck = (
        _own_deck_or_404(db, user, body.deck_id) if body.deck_id is not None else default_deck(db, user)
    )
    position = db.execute(
        select(func.coalesce(func.max(DeckItem.position), -1)).where(DeckItem.deck_id == deck.id)
    ).scalar_one()
    db.add(DeckItem(deck_id=deck.id, item_id=item.id, position=position + 1))

    db.commit()
    db.refresh(item)
    return get_item(item.id, user, db)


@router.patch("/items/{item_id}", response_model=ItemDetailOut)
def patch_item(
    item_id: uuid.UUID,
    body: ItemPatchIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItemDetailOut:
    item = db.get(Item, item_id)
    if item is None:
        raise not_found("ITEM_NOT_FOUND", "Nie ma takiej pozycji.")
    if item.source == "seed":
        # Baza startowa jest wspólna dla obu kont i wraca przy każdym wdrożeniu
        # — edycja i tak zostałaby nadpisana, więc lepiej powiedzieć to wprost.
        raise forbidden(
            "ITEM_READONLY",
            "Pozycji z bazy startowej nie da się zmienić. Zawieś ją albo dodaj własną wersję.",
        )

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    return get_item(item_id, user, db)


@router.delete("/items/{item_id}", status_code=204)
def delete_item(
    item_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    item = db.get(Item, item_id)
    if item is None:
        raise not_found("ITEM_NOT_FOUND", "Nie ma takiej pozycji.")
    if item.source == "seed":
        raise forbidden(
            "ITEM_READONLY",
            "Pozycji z bazy startowej nie da się skasować. Zawieś ją w szczegółach pozycji.",
        )
    # Kasowanie zabiera ze sobą historię powtórek obu kont — stąd ograniczenie
    # do pozycji dodanych ręcznie.
    db.delete(item)
    db.commit()


@router.post("/items/import", response_model=ImportOut)
def import_items(
    body: ImportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ImportOut:
    parsed = importer.parse(body.csv)
    errors = [
        ImportRowError(line=problem.line, reason=problem.reason, raw=problem.raw)
        for problem in parsed.problems
    ]
    preview = [row.as_dict() for row in parsed.rows[:10]]

    if body.dry_run:
        return ImportOut(
            created=0,
            updated=0,
            skipped_duplicates=0,
            deck_id=None,
            preview=preview,
            errors=errors,
        )

    deck: Deck
    if body.deck_id is not None:
        deck = _own_deck_or_404(db, user, body.deck_id)
    elif body.deck_name:
        deck = Deck(
            slug=slugify(body.deck_name, user.id),
            name=body.deck_name.strip(),
            is_shared=False,
            owner_id=user.id,
            position=100,
        )
        db.add(deck)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise conflict("DECK_EXISTS", "Masz już talię o tej nazwie.") from None
    else:
        deck = default_deck(db, user)

    position = (
        db.execute(
            select(func.coalesce(func.max(DeckItem.position), -1)).where(DeckItem.deck_id == deck.id)
        ).scalar_one()
        + 1
    )

    created = skipped = 0
    for row in parsed.rows:
        pt, article = split_article(row.pt, row.article)
        item = db.execute(select(Item).where(Item.pt == pt, Item.pl == row.pl)).scalar_one_or_none()
        if item is None:
            item = Item(
                pt=pt,
                pl=row.pl,
                type=row.type,
                cefr_level=row.cefr_level,
                part_of_speech=row.part_of_speech,
                article=article,
                gender=row.gender,
                notes=row.notes,
                source="import",
                verified=True,
                created_by=user.id,
            )
            db.add(item)
            db.flush()
            if row.example_pt and row.example_pl:
                db.add(Example(item_id=item.id, pt=row.example_pt, pl=row.example_pl, source="import"))
            created += 1
        else:
            # Pozycja już istnieje — nie nadpisujemy jej treścią z pliku, bo
            # mogła zostać poprawiona ręcznie. Dopięcie do talii i tak ma sens.
            skipped += 1

        linked = db.execute(
            select(DeckItem).where(DeckItem.deck_id == deck.id, DeckItem.item_id == item.id)
        ).scalar_one_or_none()
        if linked is None:
            db.add(DeckItem(deck_id=deck.id, item_id=item.id, position=position))
            position += 1

    db.commit()
    return ImportOut(
        created=created,
        updated=0,
        skipped_duplicates=skipped,
        deck_id=deck.id,
        preview=preview,
        errors=errors,
    )
