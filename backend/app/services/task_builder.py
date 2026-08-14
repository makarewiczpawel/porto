"""Builds a study session: which cards, in what order, asked in which form."""

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    PRODUCTION_UNLOCK_AT,
    Deck,
    DeckItem,
    Example,
    Item,
    User,
    UserItemState,
    UserSettings,
)
from app.services import ai
from app.services import scheduler as sched
from app.services import tts
from app.services import voice_library
from app.services.grader import normalize, strip_accents

# New items are dripped into the queue rather than dumped at the front: after
# this many reviews, one new card.
NEW_EVERY = 4
# Below this stability a review card is still fragile, so it gets the easier
# form of the question.
FRAGILE_STABILITY_DAYS = 21
MCQ_CHOICES = 4
# A matching round covers this many pairs in one screen.
MATCHING_PAIRS = 5
# Extra wrong bricks offered next to the right ones in a word bank.
WORD_BANK_EXTRA = 3
# Long-pressing the speaker plays this slower take. Same recording pipeline,
# different cache key, so it is synthesised once and then free. Definicja
# mieszka przy bibliotece nagrań — sesja tylko z niej korzysta.
SLOW_SPEED = voice_library.SLOW_SPEED


@dataclass
class Task:
    index: int
    item_id: uuid.UUID
    direction: str
    mode: str
    is_new: bool
    payload: dict

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "item_id": str(self.item_id),
            "direction": self.direction,
            "mode": self.mode,
            "is_new": self.is_new,
            **self.payload,
        }


def pick_mode(state: UserItemState | None, direction: str, enabled: list[str]) -> str:
    """Difficulty of the question rises with how well the card is known.

    A brand new word is shown, not tested. Once it is being learned it comes
    back as multiple choice. Only later does it have to be produced from
    memory. Falls back to whatever the user has enabled.
    """

    def first(*candidates: str) -> str:
        for mode in candidates:
            if mode in enabled:
                return mode
        return enabled[0] if enabled else "flashcard"

    mcq = "mcq_pt_pl" if direction == "recognition" else "mcq_pl_pt"

    if state is None or state.state == "new":
        # First contact: show the answer, do not quiz it.
        return first("flashcard", mcq)

    if state.state in ("learning", "relearning"):
        return first(mcq, "flashcard")

    fragile = (state.stability or 0) < FRAGILE_STABILITY_DAYS
    if direction == "recognition":
        return first("listening", "flashcard", mcq) if not fragile else first("flashcard", mcq, "listening")
    return first("typing", "cloze", mcq) if not fragile else first("cloze", mcq, "typing")


def choose_mode(
    state: UserItemState | None,
    direction: str,
    enabled: list[str],
    item: Item,
    has_audio: bool = False,
) -> str:
    """`pick_mode` decides what the card deserves; this checks the item can
    deliver it and steps down through the remaining modes if not."""
    remaining = [m for m in enabled if m != "matching"]

    # Tłumaczenie całego zdania z głowy jest trudniejsze niż ułożenie go z
    # klocków, więc gdy jest włączone, ma pierwszeństwo przed „szykiem zdania".
    # Domyślnie włączone nie jest: każda odpowiedź to płatne wywołanie modelu.
    if (
        direction == "production"
        and "translate_ai" in remaining
        and state is not None
        and state.state == "review"
        and supports("translate_ai", item)
    ):
        return "translate_ai"

    # A whole sentence is worth rebuilding rather than retyping: word order is
    # the thing being learned there, and it is the only mode that drills it.
    if (
        direction == "production"
        and item.type == "sentence"
        and "word_bank" in remaining
        and state is not None
        and state.state == "review"
        and supports("word_bank", item)
    ):
        return "word_bank"

    while remaining:
        mode = pick_mode(state, direction, remaining)
        if supports(mode, item, has_audio):
            return mode
        remaining.remove(mode)
    return "flashcard"


def _distractors(db: Session, item: Item, count: int, deck_ids: list[uuid.UUID] | None) -> list[Item]:
    """Wrong answers that are actually plausible.

    Same part of speech and level first, preferring the same deck — otherwise
    the right answer is the only one that fits the question and the exercise
    tests nothing.
    """
    base = select(Item).where(Item.id != item.id, Item.verified.is_(True))

    tiers = []
    if deck_ids:
        # An IN-subquery rather than a join: joining deck_items multiplies rows
        # for an item that sits in several decks, and DISTINCT cannot be
        # combined with ORDER BY random() in Postgres.
        in_decks = select(DeckItem.item_id).where(DeckItem.deck_id.in_(deck_ids))
        tiers.append(
            base.where(
                Item.id.in_(in_decks),
                Item.part_of_speech == item.part_of_speech,
                Item.cefr_level == item.cefr_level,
            )
        )
    tiers.append(base.where(Item.part_of_speech == item.part_of_speech, Item.cefr_level == item.cefr_level))
    tiers.append(base.where(Item.part_of_speech == item.part_of_speech))
    tiers.append(base.where(Item.cefr_level == item.cefr_level))
    tiers.append(base)

    chosen: list[Item] = []
    seen: set[uuid.UUID] = {item.id}
    seen_text = {item.pl.strip().lower(), item.pt.strip().lower()}

    for tier in tiers:
        if len(chosen) >= count:
            break
        rows = db.execute(tier.order_by(func.random()).limit(count * 4)).scalars().all()
        for candidate in rows:
            if len(chosen) >= count:
                break
            # Guard against synonyms sneaking in as "wrong" answers.
            if candidate.id in seen:
                continue
            if candidate.pl.strip().lower() in seen_text or candidate.pt.strip().lower() in seen_text:
                continue
            chosen.append(candidate)
            seen.add(candidate.id)
            seen_text.add(candidate.pl.strip().lower())
            seen_text.add(candidate.pt.strip().lower())
    return chosen



def _flatten(text: str) -> tuple[str, list[int]]:
    """Lowercase, accent-free copy of `text` plus a map back to the original
    character offsets, so a match found on the flattened form can be sliced out
    of the original with its casing intact."""
    flat: list[str] = []
    index_map: list[int] = []
    for position, char in enumerate(text):
        bare = strip_accents(char).lower()
        for piece in bare:
            flat.append(piece)
            index_map.append(position)
    return "".join(flat), index_map


def cloze_parts(item: Item, example: Example) -> dict | None:
    """Cut the item's word out of its example sentence.

    Returns `{before, answer, after}` where `answer` is the word exactly as it
    appears in the sentence, or None when the sentence does not visibly contain
    the word (an inflected form, usually) — in that case the item simply does
    not get a cloze question.
    """
    if example.cloze_start is not None and example.cloze_end is not None:
        start, end = example.cloze_start, example.cloze_end
        if 0 <= start < end <= len(example.pt):
            return {
                "before": example.pt[:start],
                "answer": example.pt[start:end],
                "after": example.pt[end:],
            }

    flat_sentence, index_map = _flatten(example.pt)
    candidates = [item.pt]
    # Multi-word entries often appear in full; a single head noun is the
    # fallback when they do not.
    if " " in item.pt:
        candidates.append(item.pt.split()[-1])

    for needle in candidates:
        flat_needle, _ = _flatten(needle)
        if not flat_needle:
            continue
        position = flat_sentence.find(flat_needle)
        if position < 0:
            continue
        start = index_map[position]
        end = index_map[position + len(flat_needle) - 1] + 1
        return {
            "before": example.pt[:start],
            "answer": example.pt[start:end],
            "after": example.pt[end:],
        }
    return None


def _first_example(item: Item) -> Example | None:
    return item.examples[0] if item.examples else None


def translation_pair(item: Item) -> tuple[str, str] | None:
    """Co przetłumaczyć i jaka jest wersja wzorcowa.

    Zdanie tłumaczy się w całości; przy pojedynczym słowie sensem ćwiczenia
    jest jego zdanie przykładowe, bo tłumaczenie jednego słowa niczego nie
    uczy o szyku ani o odmianie.
    """
    if item.type == "sentence":
        return item.pl, item.pt
    example = _first_example(item)
    if example is not None:
        return example.pl, example.pt
    return None


def supports(mode: str, item: Item, has_audio: bool = False) -> bool:
    """Whether an item can actually be asked in this form.

    Guards the mode table: a word with no example sentence cannot be a cloze,
    and only whole sentences can be reassembled from bricks.
    """
    if mode == "cloze":
        example = _first_example(item)
        return example is not None and cloze_parts(item, example) is not None
    if mode == "word_bank":
        text = item.pt if item.type == "sentence" else (_first_example(item).pt if _first_example(item) else "")
        return len(text.split()) >= 3
    if mode == "listening":
        # The question *is* the recording. Without one there is nothing to ask,
        # so an item whose audio has not been synthesised yet quietly gets a
        # different mode instead of an empty player.
        return has_audio
    if mode == "translate_ai":
        # Ocenę wystawia model, więc bez klucza tryb po prostu nie istnieje —
        # zamiast pytania bez oceny użytkownik dostaje zwykłe ćwiczenie.
        return item.type == "sentence" and translation_pair(item) is not None and ai.is_configured()
    return True


def spoken_texts(item: Item) -> dict[str, str]:
    """Which strings of this item are worth hearing.

    The Portuguese side with its article (`a casa`, not `casa`) and the example
    sentence, because hearing a word inside a sentence is where the rhythm of
    the language lives.
    """
    texts = {"pt": item.display_pt}
    example = _first_example(item)
    if example is not None:
        texts["example"] = example.pt
    return texts


def audio_index(
    db: Session, items: list[Item], voice: str, include_slow: bool = True
) -> dict[uuid.UUID, dict[str, str]]:
    """Adresy nagrań, które **już istnieją**, dla całej sesji jednym zapytaniem.

    Sesja nie syntezuje niczego w locie: czekanie na dostawcę w środku nauki
    byłoby widoczne, a rachunek zależałby od tego, jak często ktoś się uczy.
    Nagrania robi wcześniej `scripts/synthesize_all.py`, a tutaj tylko sprawdzam,
    co jest gotowe.
    """
    wanted: dict[uuid.UUID, dict[str, str]] = {}
    keys: list[str] = []
    for item in items:
        entry: dict[str, str] = {}
        for slot, text in spoken_texts(item).items():
            key = tts.cache_key(text, voice, 1.0)
            entry[slot] = key
            keys.append(key)
            if include_slow and slot == "pt":
                slow = tts.cache_key(text, voice, SLOW_SPEED)
                entry["pt_slow"] = slow
                keys.append(slow)
        wanted[item.id] = entry

    available = tts.existing_urls(db, keys)
    return {
        item_id: {slot: tts.audio_url(key) for slot, key in slots.items() if key in available}
        for item_id, slots in wanted.items()
    }


def _word_bank(db: Session, item: Item) -> dict:
    """Bricks to rebuild a sentence from, plus a few plausible wrong ones."""
    if item.type == "sentence":
        sentence, translation = item.pt, item.pl
    else:
        example = _first_example(item)
        sentence, translation = (example.pt, example.pl) if example else (item.pt, item.pl)

    tokens = sentence.split()
    pool = (
        db.execute(
            select(Example.pt)
            .where(Example.item_id != item.id)
            .order_by(func.random())
            .limit(12)
        )
        .scalars()
        .all()
    )
    used = {strip_accents(normalize(t)) for t in tokens}
    extra: list[str] = []
    for other in pool:
        for word in other.split():
            key = strip_accents(normalize(word))
            if key and key not in used and len(extra) < WORD_BANK_EXTRA:
                used.add(key)
                extra.append(word)
    return {"question": translation, "tokens": tokens, "extra": extra, "sentence": sentence}


def build_task(
    db: Session,
    index: int,
    item: Item,
    direction: str,
    mode: str,
    is_new: bool,
    deck_ids: list[uuid.UUID] | None,
    state: UserItemState | None,
    desired_retention: float,
    audio: dict[str, str] | None = None,
) -> Task:
    example = item.examples[0] if item.examples else None
    payload: dict = {
        "pt": item.display_pt,
        "pl": item.pl,
        "type": item.type,
        "cefr_level": item.cefr_level,
        "part_of_speech": item.part_of_speech,
        "notes": item.notes,
        "example": {"pt": example.pt, "pl": example.pl} if example else None,
        "audio": audio or {},
    }

    if mode in ("mcq_pt_pl", "mcq_pl_pt"):
        wrong = _distractors(db, item, MCQ_CHOICES - 1, deck_ids)
        field = "pl" if mode == "mcq_pt_pl" else "pt"

        def label(candidate: Item) -> str:
            return candidate.pl if field == "pl" else candidate.display_pt

        options = [label(item)] + [label(w) for w in wrong]
        random.shuffle(options)
        payload["question"] = item.display_pt if mode == "mcq_pt_pl" else item.pl
        payload["options"] = options
        payload["answer_index"] = options.index(label(item))
    elif mode == "listening":
        # Nothing to read: the recording is the question. Same four choices as
        # a normal recognition test, so the only new skill being tested is
        # catching the word by ear.
        wrong = _distractors(db, item, MCQ_CHOICES - 1, deck_ids)
        options = [item.pl] + [w.pl for w in wrong]
        random.shuffle(options)
        payload["question"] = None
        payload["options"] = options
        payload["answer_index"] = options.index(item.pl)
    elif mode == "flashcard":
        payload["front"] = item.display_pt if direction == "recognition" else item.pl
        payload["back"] = item.pl if direction == "recognition" else item.display_pt
        probe = state or UserItemState(state="new", due=datetime.now(timezone.utc))
        payload["intervals"] = {str(k): v for k, v in sched.preview_intervals(probe, desired_retention).items()}
    elif mode == "typing":
        # Always produce Portuguese from Polish — typing the translation of a
        # word you can already read is not the skill worth drilling.
        payload["question"] = item.pl
        payload["expected"] = item.display_pt
        payload["alternatives"] = list(item.pt_alt or [])
    elif mode == "cloze":
        example = _first_example(item)
        parts = cloze_parts(item, example) if example else None
        if parts is None:  # pragma: no cover - guarded by supports()
            payload["question"] = item.pl
            payload["expected"] = item.display_pt
            mode = "typing"
        else:
            payload["cloze"] = parts
            payload["expected"] = parts["answer"]
            payload["alternatives"] = []
            payload["question"] = example.pl
    elif mode == "translate_ai":
        pair = translation_pair(item)
        if pair is None:  # pragma: no cover - guarded by supports()
            payload["question"] = item.pl
            payload["expected"] = item.display_pt
            mode = "typing"
        else:
            payload["question"], payload["expected"] = pair
            payload["alternatives"] = []
    elif mode == "word_bank":
        payload.update(_word_bank(db, item))
        payload["expected"] = payload.pop("sentence")

    return Task(index=index, item_id=item.id, direction=direction, mode=mode, is_new=is_new, payload=payload)


def build_matching_task(
    db: Session, index: int, states: list[UserItemState]
) -> Task | None:
    """One screen covering several cards — the warm-up that opens a session.

    Unlike every other task this one carries a list of items; answering it
    produces one review per pair.
    """
    pairs = []
    for state in states:
        item = db.get(Item, state.item_id)
        if item is None:
            continue
        pairs.append({"item_id": str(item.id), "pt": item.display_pt, "pl": item.pl})
    if len(pairs) < 2:
        return None
    return Task(
        index=index,
        item_id=uuid.UUID(pairs[0]["item_id"]),
        direction="recognition",
        mode="matching",
        is_new=False,
        payload={"pairs": pairs, "pt": pairs[0]["pt"], "pl": pairs[0]["pl"]},
    )


def _resolve_decks(db: Session, user: User, deck_ids: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
    if not deck_ids:
        return None
    rows = (
        db.execute(
            select(Deck.id).where(
                Deck.id.in_(deck_ids),
                or_(Deck.is_shared.is_(True), Deck.owner_id == user.id),
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def due_states(
    db: Session, user: User, now: datetime, limit: int, deck_ids: list[uuid.UUID] | None
) -> list[UserItemState]:
    query = (
        select(UserItemState)
        .join(Item, Item.id == UserItemState.item_id)
        .where(
            UserItemState.user_id == user.id,
            UserItemState.suspended.is_(False),
            UserItemState.due <= now,
            Item.verified.is_(True),
        )
    )
    if deck_ids:
        query = query.join(DeckItem, DeckItem.item_id == Item.id).where(DeckItem.deck_id.in_(deck_ids))
    query = query.order_by(UserItemState.due.asc()).limit(limit)
    return list(db.execute(query).scalars().unique().all())


def new_items(
    db: Session, user: User, limit: int, deck_ids: list[uuid.UUID] | None
) -> list[Item]:
    """Items the user has never seen. Only recognition cards are created for
    them — production unlocks later, so the daily load grows gently."""
    if limit <= 0:
        return []
    seen = select(UserItemState.item_id).where(UserItemState.user_id == user.id)
    query = (
        select(Item, DeckItem.position)
        .join(DeckItem, DeckItem.item_id == Item.id)
        .join(Deck, Deck.id == DeckItem.deck_id)
        .where(
            Item.verified.is_(True),
            Item.id.not_in(seen),
            or_(Deck.is_shared.is_(True), Deck.owner_id == user.id),
        )
    )
    if deck_ids:
        query = query.where(DeckItem.deck_id.in_(deck_ids))
    query = query.order_by(Deck.position.asc(), DeckItem.position.asc()).limit(limit * 3)

    out: list[Item] = []
    seen_ids: set[uuid.UUID] = set()
    for item, _pos in db.execute(query).unique().all():
        if item.id in seen_ids:
            continue
        seen_ids.add(item.id)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def interleave(reviews: list, news: list) -> list[tuple[bool, object]]:
    """Weave new material between reviews instead of front-loading it.

    Returns [(is_new, entry)] — reviews first so the session opens with
    something familiar.
    """
    out: list[tuple[bool, object]] = []
    news_left = list(news)
    for i, entry in enumerate(reviews):
        out.append((False, entry))
        if news_left and (i + 1) % NEW_EVERY == 0:
            out.append((True, news_left.pop(0)))
    out.extend((True, n) for n in news_left)
    return out


def unlock_production(db: Session, user: User, now: datetime) -> int:
    """Give a production card to every word that is recognised reliably.

    Returns how many were unlocked.
    """
    recognised = select(UserItemState).where(
        UserItemState.user_id == user.id,
        UserItemState.direction == "recognition",
        UserItemState.correct_reps >= PRODUCTION_UNLOCK_AT,
        UserItemState.suspended.is_(False),
    )
    existing = {
        row
        for row in db.execute(
            select(UserItemState.item_id).where(
                UserItemState.user_id == user.id, UserItemState.direction == "production"
            )
        )
        .scalars()
        .all()
    }
    created = 0
    for state in db.execute(recognised).scalars().all():
        if state.item_id in existing:
            continue
        db.add(
            UserItemState(
                user_id=user.id,
                item_id=state.item_id,
                direction="production",
                state="new",
                due=now,
            )
        )
        created += 1
    if created:
        db.flush()
    return created


def build_session(
    db: Session,
    user: User,
    user_settings: UserSettings,
    *,
    deck_ids: list[uuid.UUID] | None = None,
    new_limit: int | None = None,
    review_limit: int | None = None,
    modes: list[str] | None = None,
    now: datetime | None = None,
) -> tuple[list[Task], list[uuid.UUID] | None]:
    now = now or datetime.now(timezone.utc)
    resolved_decks = _resolve_decks(db, user, deck_ids)
    enabled = modes or list(user_settings.enabled_modes or [])
    if not enabled:
        enabled = ["flashcard"]

    unlock_production(db, user, now)

    review_cap = user_settings.review_limit if review_limit is None else review_limit
    new_cap = user_settings.new_per_day if new_limit is None else new_limit

    states = due_states(db, user, now, review_cap, resolved_decks)
    fresh = new_items(db, user, new_cap, resolved_decks)

    tasks: list[Task] = []

    # A matching round opens the session: five known pairs, quick taps, a way
    # into the language before anything is actually demanded.
    warmup: list[UserItemState] = []
    if "matching" in enabled:
        recognition_due = [s for s in states if s.direction == "recognition" and s.state == "review"]
        if len(recognition_due) >= MATCHING_PAIRS:
            warmup = recognition_due[:MATCHING_PAIRS]
            warmup_ids = {(s.item_id, s.direction) for s in warmup}
            states = [s for s in states if (s.item_id, s.direction) not in warmup_ids]
            task = build_matching_task(db, 0, warmup)
            if task is not None:
                tasks.append(task)
            else:  # pragma: no cover - only when items vanished mid-build
                states = warmup + states

    queue: list[tuple[bool, Item, UserItemState | None, str]] = []
    for is_new, entry in interleave(states, fresh):
        if is_new:
            queue.append((True, entry, None, "recognition"))
        else:
            item = db.get(Item, entry.item_id)
            if item is not None:
                queue.append((False, item, entry, entry.direction))

    heard = [item for _, item, _, _ in queue]
    for state in warmup:
        warm_item = db.get(Item, state.item_id)
        if warm_item is not None:
            heard.append(warm_item)

    recordings = audio_index(db, heard, user_settings.tts_voice)
    if tasks and tasks[0].mode == "matching":
        for pair in tasks[0].payload["pairs"]:
            pair["audio"] = recordings.get(uuid.UUID(pair["item_id"]), {}).get("pt")

    for is_new, item, state, direction in queue:
        audio = recordings.get(item.id, {})
        mode = choose_mode(state, direction, enabled, item, has_audio="pt" in audio)
        tasks.append(
            build_task(
                db,
                len(tasks),
                item,
                direction,
                mode,
                is_new,
                resolved_decks,
                state,
                float(user_settings.desired_retention),
                audio,
            )
        )
    return tasks, resolved_decks


def queue_counts(db: Session, user: User, now: datetime, deck_ids: list[uuid.UUID] | None = None) -> dict:
    due_q = (
        select(func.count())
        .select_from(UserItemState)
        .join(Item, Item.id == UserItemState.item_id)
        .where(
            UserItemState.user_id == user.id,
            UserItemState.suspended.is_(False),
            UserItemState.due <= now,
            Item.verified.is_(True),
        )
    )
    seen = select(UserItemState.item_id).where(UserItemState.user_id == user.id)
    new_q = (
        select(func.count(func.distinct(Item.id)))
        .select_from(Item)
        .join(DeckItem, DeckItem.item_id == Item.id)
        .join(Deck, Deck.id == DeckItem.deck_id)
        .where(
            Item.verified.is_(True),
            Item.id.not_in(seen),
            or_(Deck.is_shared.is_(True), Deck.owner_id == user.id),
        )
    )
    next_due = db.execute(
        select(func.min(UserItemState.due)).where(
            UserItemState.user_id == user.id,
            UserItemState.suspended.is_(False),
            UserItemState.due > now,
        )
    ).scalar_one_or_none()

    return {
        "due": db.execute(due_q).scalar_one(),
        "new_available": db.execute(new_q).scalar_one(),
        "next_due_at": next_due,
    }


def deck_counts(db: Session, user: User, now: datetime) -> dict[uuid.UUID, dict]:
    """Per-deck totals in one query each, rather than N+1 over the deck list."""
    totals = dict(
        db.execute(
            select(DeckItem.deck_id, func.count(func.distinct(DeckItem.item_id))).group_by(DeckItem.deck_id)
        ).all()
    )
    due = dict(
        db.execute(
            select(DeckItem.deck_id, func.count(func.distinct(DeckItem.item_id)))
            .join(
                UserItemState,
                and_(
                    UserItemState.item_id == DeckItem.item_id,
                    UserItemState.user_id == user.id,
                    UserItemState.suspended.is_(False),
                    UserItemState.due <= now,
                ),
            )
            .group_by(DeckItem.deck_id)
        ).all()
    )
    learned = dict(
        db.execute(
            select(DeckItem.deck_id, func.count(func.distinct(DeckItem.item_id)))
            .join(
                UserItemState,
                and_(
                    UserItemState.item_id == DeckItem.item_id,
                    UserItemState.user_id == user.id,
                    UserItemState.direction == "recognition",
                    UserItemState.state == "review",
                ),
            )
            .group_by(DeckItem.deck_id)
        ).all()
    )
    started = dict(
        db.execute(
            select(DeckItem.deck_id, func.count(func.distinct(DeckItem.item_id)))
            .join(
                UserItemState,
                and_(
                    UserItemState.item_id == DeckItem.item_id,
                    UserItemState.user_id == user.id,
                ),
            )
            .group_by(DeckItem.deck_id)
        ).all()
    )
    out: dict[uuid.UUID, dict] = {}
    for deck_id, total in totals.items():
        out[deck_id] = {
            "total": total,
            "due": due.get(deck_id, 0),
            "learned": learned.get(deck_id, 0),
            "untouched": total - started.get(deck_id, 0),
        }
    return out


def build_quiz(
    db: Session,
    user: User,
    *,
    count: int,
    deck_ids: list[uuid.UUID] | None = None,
    level: str | None = None,
    modes: list[str] | None = None,
) -> list[Task]:
    """Questions for a test.

    Unlike a study session this ignores the schedule — a quiz checks what you
    know, not what is due. It prefers words you have actually started learning,
    and only falls back to untouched ones when there are not enough.
    """
    allowed = [m for m in (modes or ["mcq_pt_pl", "mcq_pl_pt", "typing"]) if m != "matching"]
    if not allowed:
        allowed = ["mcq_pt_pl"]

    base = select(Item).where(Item.verified.is_(True))
    if level:
        base = base.where(Item.cefr_level == level.upper())
    if deck_ids:
        base = base.where(Item.id.in_(select(DeckItem.item_id).where(DeckItem.deck_id.in_(deck_ids))))

    started = select(UserItemState.item_id).where(UserItemState.user_id == user.id)
    known = list(
        db.execute(base.where(Item.id.in_(started)).order_by(func.random()).limit(count))
        .scalars()
        .unique()
        .all()
    )
    if len(known) < count:
        filler = (
            db.execute(
                base.where(Item.id.not_in([i.id for i in known] or [uuid.uuid4()]))
                .order_by(func.random())
                .limit(count - len(known))
            )
            .scalars()
            .unique()
            .all()
        )
        known.extend(filler)

    chosen = known[:count]
    recordings = audio_index(db, chosen, user.settings.tts_voice)

    tasks: list[Task] = []
    for item in chosen:
        audio = recordings.get(item.id, {})
        feasible = [m for m in allowed if supports(m, item, has_audio="pt" in audio)] or ["mcq_pt_pl"]
        mode = random.choice(feasible)
        direction = "production" if mode in ("mcq_pl_pt", "typing", "word_bank") else "recognition"
        tasks.append(
            build_task(db, len(tasks), item, direction, mode, False, deck_ids, None, 0.90, audio)
        )
    return tasks
