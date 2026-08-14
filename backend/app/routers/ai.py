"""Funkcje oparte o model językowy: generowanie zestawów i pomoc przy błędach.

Dwie rzeczy odróżniają ten router od reszty API.

Po pierwsze, **każde wywołanie kosztuje** — dlatego trasy sięgające po model
siedzą za limitem żądań i za twardym budżetem miesięcznym, a wyczerpanie
budżetu jest zwykłym `429` z komunikatem po polsku, nie awarią.

Po drugie, **nic z modelu nie trafia do słownika samo**. `POST /generate`
zapisuje propozycje w zadaniu i tyle; pozycjami do nauki stają się dopiero te
zaznaczone w przeglądzie i wysłane do `POST /jobs/{id}/accept`. Propozycji da
się przy tym dotknąć: ekran przeglądu odsyła treść pozycji, więc poprawka
tłumaczenia zostaje zapisana tak, jak ją wpisał człowiek.
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import SessionLocal, get_db
from app.deps import RateLimiter, get_current_user
from app.errors import bad_request, not_found, too_many, unprocessable
from app.models import AiJob, Deck, DeckItem, Example, Item, User
from app.services import ai, tts
from app.services.lexicon import slugify, split_article
from app.services.task_builder import SLOW_SPEED, spoken_texts

# Dwadzieścia wywołań na godzinę. Ekran generowania da się kliknąć raz na
# kilkadziesiąt sekund, więc limit dotyka tylko pętli, która się zapętliła.
#
# Limit wisi na trasach, które faktycznie wołają model — nie na całym routerze.
# Odpytanie o zużycie budżetu jest darmowe i robi je każdy ekran ustawień;
# gdyby zjadało limit, sprawdzenie stanu konta blokowałoby korzystanie z niego.
ai_rate_limit = RateLimiter(limit=20, window_seconds=3600, code="AI_RATE_LIMITED")
COSTS_MONEY = [Depends(ai_rate_limit)]

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _fail(exc: ai.AIError):
    """Błąd serwisu na odpowiedź HTTP. Wyczerpany budżet to 429, nie 500."""
    if isinstance(exc, ai.AIBudgetReached):
        return too_many("AI_BUDGET", str(exc))
    if isinstance(exc, ai.AINotConfigured):
        return unprocessable("AI_NOT_CONFIGURED", str(exc))
    if isinstance(exc, ai.AIRefused):
        return unprocessable("AI_REFUSED", str(exc))
    return unprocessable("AI_FAILED", str(exc))


# ── schematy ──────────────────────────────────────────────────────────────
class GenerateIn(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    count: int = Field(default=15, ge=1)
    level: str = Field(default="A2", pattern="^(A1|A2|B1|B2|C1)$")


class ProposalOut(BaseModel):
    pt: str
    pl: str
    type: str
    part_of_speech: str | None = None
    article: str | None = None
    gender: str | None = None
    plural: str | None = None
    cefr_level: str
    notes: str | None = None
    example_pt: str | None = None
    example_pl: str | None = None


class GenerateOut(BaseModel):
    job_id: uuid.UUID
    deck_name: str
    proposals: list[ProposalOut]
    skipped_duplicates: int
    cost_usd: float


class AcceptIn(BaseModel):
    deck_name: str | None = Field(default=None, max_length=120)
    deck_id: uuid.UUID | None = None
    items: list[ProposalOut] = Field(min_length=1)


class AcceptOut(BaseModel):
    deck_id: uuid.UUID
    deck_name: str
    created: int
    skipped_duplicates: int
    audio_queued: int


class ExplainIn(BaseModel):
    item_id: uuid.UUID
    user_answer: str = Field(min_length=1, max_length=300)
    expected: str | None = Field(default=None, max_length=300)


class ExplainOut(BaseModel):
    verdict: str
    explanation: str
    cached: bool


class GradeIn(BaseModel):
    item_id: uuid.UUID | None = None
    prompt_pl: str | None = Field(default=None, max_length=400)
    expected_pt: str | None = Field(default=None, max_length=400)
    user_answer: str = Field(min_length=1, max_length=400)


class GradeOut(BaseModel):
    score: int
    corrected: str
    feedback: str
    cached: bool


class ExamplesIn(BaseModel):
    item_id: uuid.UUID
    count: int = Field(default=2, ge=1, le=3)


class ExampleOut(BaseModel):
    pt: str
    pl: str


class ExamplesOut(BaseModel):
    item_id: uuid.UUID
    examples: list[ExampleOut]
    cached: bool


class ExampleAcceptIn(BaseModel):
    item_id: uuid.UUID
    pt: str = Field(min_length=1, max_length=400)
    pl: str = Field(min_length=1, max_length=400)


# ── zużycie ───────────────────────────────────────────────────────────────
@router.get("/usage")
def ai_usage(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return ai.usage(db)


# ── generowanie zestawu ───────────────────────────────────────────────────
def _known_words(db: Session, user: User, topic: str) -> list[str]:
    """Hasła, które ten temat już kiedyś przyniósł.

    Poproszenie drugi raz o „zwroty u lekarza" bez tej listy kończy się tym
    samym zestawem i pustym przeglądem. Taniej jest wysłać modelowi, co już
    jest, niż wygenerować duplikaty i je odrzucić.
    """
    rows = (
        db.execute(
            select(AiJob.result)
            .where(
                AiJob.user_id == user.id,
                AiJob.kind == "set",
                AiJob.result.isnot(None),
                AiJob.prompt.ilike(f"%{topic.strip()}%"),
            )
            .order_by(AiJob.created_at.desc())
            .limit(10)
        )
        .scalars()
        .all()
    )
    words: list[str] = []
    for result in rows:
        for entry in (result or {}).get("items", []):
            word = (entry.get("pt") or "").strip()
            if word and word not in words:
                words.append(word)
    return words


@router.post("/generate", response_model=GenerateOut, dependencies=COSTS_MONEY)
def generate(
    body: GenerateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> GenerateOut:
    count = min(body.count, settings.ai_max_items_per_set)
    try:
        result, job = ai.generate_set(
            db,
            user,
            topic=body.topic,
            count=count,
            level=body.level,
            avoid=_known_words(db, user, body.topic),
        )
    except ai.AIError as exc:
        raise _fail(exc) from exc

    # Deduplikacja po `(pt, pl)` — a także po samym haśle portugalskim, bo
    # drugie tłumaczenie tego samego słowa to nie nowa pozycja do nauki, tylko
    # ta sama pozycja pytana dwa razy w jednej sesji.
    proposals: list[ProposalOut] = []
    skipped = 0
    seen: set[str] = set()
    for entry in result.items:
        pt, article = split_article(entry.pt, entry.article)
        key = pt.strip().lower()
        if key in seen:
            skipped += 1
            continue
        exists = db.execute(
            select(Item.id).where(func.lower(Item.pt) == key).limit(1)
        ).scalar_one_or_none()
        if exists is not None:
            skipped += 1
            continue
        seen.add(key)
        proposals.append(
            ProposalOut(
                pt=pt,
                pl=entry.pl.strip(),
                type=entry.type,
                part_of_speech=entry.part_of_speech,
                article=article,
                gender=entry.gender,
                plural=entry.plural,
                cefr_level=entry.cefr_level,
                notes=entry.notes,
                example_pt=entry.example_pt,
                example_pl=entry.example_pl,
            )
        )

    return GenerateOut(
        job_id=job.id,
        deck_name=result.deck_name[:120],
        proposals=proposals,
        skipped_duplicates=skipped,
        cost_usd=float(job.cost_usd),
    )


@router.get("/jobs/{job_id}", response_model=GenerateOut)
def get_job(
    job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> GenerateOut:
    """Przegląd, do którego da się wrócić — propozycje przeżywają odświeżenie."""
    job = db.get(AiJob, job_id)
    if job is None or job.user_id != user.id or job.kind != "set" or not job.result:
        raise not_found("AI_JOB_NOT_FOUND", "Nie ma takiego zestawu.")
    proposals = []
    for entry in job.result.get("items", []):
        pt, article = split_article(entry.get("pt", ""), entry.get("article"))
        proposals.append(
            ProposalOut(
                pt=pt,
                pl=entry.get("pl", ""),
                type=entry.get("type", "word"),
                part_of_speech=entry.get("part_of_speech"),
                article=article,
                gender=entry.get("gender"),
                plural=entry.get("plural"),
                cefr_level=entry.get("cefr_level", "A1"),
                notes=entry.get("notes"),
                example_pt=entry.get("example_pt"),
                example_pl=entry.get("example_pl"),
            )
        )
    return GenerateOut(
        job_id=job.id,
        deck_name=job.result.get("deck_name", "Zestaw AI")[:120],
        proposals=proposals,
        skipped_duplicates=0,
        cost_usd=float(job.cost_usd),
    )


def _synthesize(item_ids: list[uuid.UUID], voice: str) -> None:
    """Nagrania dla świeżo przyjętych pozycji, już po odpowiedzi HTTP.

    Wymowa nie może kazać czekać na przegląd — a zestaw bez nagrań i tak
    działa, tylko głośnik odzywa się głosem przeglądarki, dopóki nagrania nie
    dojdą.

    Wyczerpany limit znaków przerywa całą pętlę, bo każde kolejne hasło
    skończy się tak samo. Pojedyncza usterka sieci nie przerywa — reszta
    zestawu ma się nagrać mimo jednego hasła, które się nie udało.
    """
    if not tts.is_configured():
        return
    db = SessionLocal()
    try:
        items = (
            db.execute(select(Item).options(selectinload(Item.examples)).where(Item.id.in_(item_ids)))
            .scalars()
            .unique()
            .all()
        )
        for item in items:
            for slot, text in spoken_texts(item).items():
                speeds = [1.0, SLOW_SPEED] if slot == "pt" else [1.0]
                for speed in speeds:
                    try:
                        tts.speak(db, text, voice=voice, speed=speed)
                        db.commit()
                    except (tts.TTSLimitReached, tts.TTSNotConfigured):
                        db.rollback()
                        return
                    except tts.TTSError:
                        db.rollback()
    finally:
        db.close()


@router.post("/jobs/{job_id}/accept", response_model=AcceptOut)
def accept(
    job_id: uuid.UUID,
    body: AcceptIn,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AcceptOut:
    """Zaznaczone propozycje stają się pozycjami do nauki w nowej talii."""
    job = db.get(AiJob, job_id)
    if job is None or job.user_id != user.id or job.kind != "set":
        raise not_found("AI_JOB_NOT_FOUND", "Nie ma takiego zestawu.")

    if body.deck_id is not None:
        deck = db.get(Deck, body.deck_id)
        if deck is None or (deck.owner_id != user.id and not deck.is_shared):
            raise not_found("DECK_NOT_FOUND", "Nie ma takiej talii.")
    else:
        name = (body.deck_name or "Zestaw AI").strip()[:120]
        if not name:
            raise bad_request("DECK_NAME_REQUIRED", "Talia musi mieć nazwę.")
        slug = slugify(name, user.id)
        deck = db.execute(select(Deck).where(Deck.slug == slug)).scalar_one_or_none()
        if deck is None:
            deck = Deck(
                slug=slug,
                name=name,
                description="Zestaw wygenerowany i zatwierdzony w przeglądzie.",
                icon="✨",
                is_shared=False,
                owner_id=user.id,
                position=100,
            )
            db.add(deck)
            db.flush()

    position = (
        db.execute(
            select(func.coalesce(func.max(DeckItem.position), -1)).where(DeckItem.deck_id == deck.id)
        ).scalar_one()
        + 1
    )

    created: list[uuid.UUID] = []
    skipped = 0
    for entry in body.items:
        pt, article = split_article(entry.pt, entry.article)
        pl = entry.pl.strip()
        if not pt or not pl:
            skipped += 1
            continue
        item = db.execute(select(Item).where(Item.pt == pt, Item.pl == pl)).scalar_one_or_none()
        if item is None:
            item = Item(
                pt=pt,
                pl=pl,
                type=entry.type,
                article=article,
                gender=entry.gender,
                part_of_speech=entry.part_of_speech,
                plural=entry.plural,
                cefr_level=entry.cefr_level,
                notes=entry.notes,
                source="ai",
                # Zweryfikowane, bo przeszły przez przegląd człowieka. Pozycja
                # niezatwierdzona nie ma jak tu trafić.
                verified=True,
                created_by=user.id,
            )
            db.add(item)
            db.flush()
            if entry.example_pt and entry.example_pl:
                db.add(
                    Example(
                        item_id=item.id,
                        pt=entry.example_pt.strip(),
                        pl=entry.example_pl.strip(),
                        source="ai",
                    )
                )
            created.append(item.id)
        else:
            skipped += 1

        linked = db.execute(
            select(DeckItem).where(DeckItem.deck_id == deck.id, DeckItem.item_id == item.id)
        ).scalar_one_or_none()
        if linked is None:
            db.add(DeckItem(deck_id=deck.id, item_id=item.id, position=position))
            position += 1

    job.status = "accepted"
    job.deck_id = deck.id
    db.commit()

    if created:
        background.add_task(_synthesize, created, user.settings.tts_voice)

    return AcceptOut(
        deck_id=deck.id,
        deck_name=deck.name,
        created=len(created),
        skipped_duplicates=skipped,
        audio_queued=len(created) if tts.is_configured() else 0,
    )


# ── pomoc przy błędzie ────────────────────────────────────────────────────
def _item_or_404(db: Session, item_id: uuid.UUID) -> Item:
    item = db.execute(
        select(Item).options(selectinload(Item.examples)).where(Item.id == item_id)
    ).scalar_one_or_none()
    if item is None:
        raise not_found("ITEM_NOT_FOUND", "Nie ma takiej pozycji.")
    return item


@router.post("/explain", response_model=ExplainOut, dependencies=COSTS_MONEY)
def explain(
    body: ExplainIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ExplainOut:
    item = _item_or_404(db, body.item_id)
    expected = (body.expected or item.display_pt).strip()
    try:
        payload, was_cached = ai.explain_mistake(
            db, user, item=item, user_answer=body.user_answer.strip(), expected=expected
        )
    except ai.AIError as exc:
        raise _fail(exc) from exc
    return ExplainOut(**payload, cached=was_cached)


@router.post("/grade-translation", response_model=GradeOut, dependencies=COSTS_MONEY)
def grade_translation(
    body: GradeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> GradeOut:
    prompt_pl = (body.prompt_pl or "").strip()
    expected_pt = (body.expected_pt or "").strip()
    if body.item_id is not None:
        item = _item_or_404(db, body.item_id)
        example = item.examples[0] if item.examples else None
        # Zdanie ma pierwszeństwo nad hasłem: tłumaczy się zdania, nie słowa.
        prompt_pl = prompt_pl or (example.pl if example else item.pl)
        expected_pt = expected_pt or (example.pt if example else item.display_pt)
    if not prompt_pl or not expected_pt:
        raise bad_request("GRADE_INPUT_MISSING", "Brakuje zdania do oceny.")

    try:
        payload, was_cached = ai.grade_translation(
            db,
            user,
            prompt_pl=prompt_pl,
            expected_pt=expected_pt,
            user_answer=body.user_answer.strip(),
        )
    except ai.AIError as exc:
        raise _fail(exc) from exc
    return GradeOut(**payload, cached=was_cached)


@router.post("/examples", response_model=ExamplesOut, dependencies=COSTS_MONEY)
def examples(
    body: ExamplesIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ExamplesOut:
    item = _item_or_404(db, body.item_id)
    try:
        found, was_cached = ai.make_examples(db, user, item=item, count=body.count)
    except ai.AIError as exc:
        raise _fail(exc) from exc
    return ExamplesOut(
        item_id=item.id,
        examples=[ExampleOut(pt=e["pt"], pl=e["pl"]) for e in found],
        cached=was_cached,
    )


@router.post("/examples/accept", status_code=201)
def accept_example(
    body: ExampleAcceptIn,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Wybrane zdanie dopisane do pozycji — znów dopiero po akceptacji."""
    item = _item_or_404(db, body.item_id)
    db.add(Example(item_id=item.id, pt=body.pt.strip(), pl=body.pl.strip(), source="ai"))
    db.commit()
    background.add_task(_synthesize, [item.id], user.settings.tts_voice)
    return {"item_id": str(item.id), "ok": True}
