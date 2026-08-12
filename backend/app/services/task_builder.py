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
    Item,
    User,
    UserItemState,
    UserSettings,
)
from app.services import scheduler as sched

# New items are dripped into the queue rather than dumped at the front: after
# this many reviews, one new card.
NEW_EVERY = 4
# Below this stability a review card is still fragile, so it gets the easier
# form of the question.
FRAGILE_STABILITY_DAYS = 21
MCQ_CHOICES = 4


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
    elif mode == "flashcard":
        payload["front"] = item.display_pt if direction == "recognition" else item.pl
        payload["back"] = item.pl if direction == "recognition" else item.display_pt
        probe = state or UserItemState(state="new", due=datetime.now(timezone.utc))
        payload["intervals"] = {str(k): v for k, v in sched.preview_intervals(probe, desired_retention).items()}

    return Task(index=index, item_id=item.id, direction=direction, mode=mode, is_new=is_new, payload=payload)


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
    for is_new, entry in interleave(states, fresh):
        index = len(tasks)
        if is_new:
            item: Item = entry
            state = None
            direction = "recognition"
        else:
            state = entry
            item = db.get(Item, state.item_id)
            if item is None:
                continue
            direction = state.direction
        mode = pick_mode(state, direction, enabled)
        tasks.append(
            build_task(
                db,
                index,
                item,
                direction,
                mode,
                is_new,
                resolved_decks,
                state,
                float(user_settings.desired_retention),
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
