"""Loads the starter content into the database.

Idempotent: running it twice does not duplicate anything. Items are keyed by
`(pt, pl)`, decks by `slug`. An item that appears in two decks (a key belongs
in both "home" and "travel") is stored once and linked twice.

    python -m app.seed.seed          # load / refresh
    python -m app.seed.seed --stats  # just report what is in the database
"""

import json
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Deck, DeckItem, Example, Item

SEED_DIR = Path(__file__).parent


def load_files() -> list[dict]:
    decks: list[dict] = []
    for path in sorted(SEED_DIR.glob("decks_*.json")):
        with path.open(encoding="utf-8") as handle:
            decks.extend(json.load(handle))
    return decks


def upsert_item(db: Session, spec: dict) -> Item:
    pt = spec["pt"].strip()
    pl = spec["pl"].strip()
    item = db.execute(select(Item).where(Item.pt == pt, Item.pl == pl)).scalar_one_or_none()
    if item is None:
        item = Item(pt=pt, pl=pl)
        db.add(item)

    item.type = spec.get("type", "word")
    item.part_of_speech = spec.get("pos")
    item.article = spec.get("article")
    item.gender = spec.get("gender")
    item.plural = spec.get("plural")
    item.ipa = spec.get("ipa")
    item.cefr_level = spec.get("level", "A1")
    item.notes = spec.get("notes")
    item.variant = spec.get("variant", "pt-PT")
    item.source = "seed"
    # Everything in the seed has been read through by hand; anything uncertain
    # is marked verified=false in the JSON and stays out of study rotation.
    item.verified = spec.get("verified", True)
    db.flush()

    wanted = [(e[0].strip(), e[1].strip()) for e in spec.get("ex", [])]
    have = {(e.pt, e.pl) for e in item.examples}
    for ex_pt, ex_pl in wanted:
        if (ex_pt, ex_pl) not in have:
            db.add(Example(item_id=item.id, pt=ex_pt, pl=ex_pl, source="seed"))
    return item


def upsert_deck(db: Session, spec: dict) -> tuple[Deck, int, int]:
    deck = db.execute(select(Deck).where(Deck.slug == spec["slug"])).scalar_one_or_none()
    if deck is None:
        deck = Deck(slug=spec["slug"])
        db.add(deck)
    deck.name = spec["name"]
    deck.description = spec.get("description")
    deck.cefr_level = spec.get("cefr_level")
    deck.icon = spec.get("icon")
    deck.position = spec.get("position", 0)
    deck.is_shared = True
    db.flush()

    existing_links = {
        link.item_id: link
        for link in db.execute(select(DeckItem).where(DeckItem.deck_id == deck.id)).scalars().all()
    }

    created = 0
    for position, item_spec in enumerate(spec["items"]):
        before = db.execute(select(func.count()).select_from(Item)).scalar_one()
        item = upsert_item(db, item_spec)
        after = db.execute(select(func.count()).select_from(Item)).scalar_one()
        created += after - before

        link = existing_links.get(item.id)
        if link is None:
            db.add(DeckItem(deck_id=deck.id, item_id=item.id, position=position))
        else:
            link.position = position
    db.flush()
    return deck, len(spec["items"]), created


def run(db: Session) -> dict:
    specs = load_files()
    total_linked = 0
    total_created = 0
    for spec in specs:
        _deck, linked, created = upsert_deck(db, spec)
        total_linked += linked
        total_created += created
    db.commit()

    return {
        "decks": len(specs),
        "links": total_linked,
        "new_items": total_created,
        "items_total": db.execute(select(func.count()).select_from(Item)).scalar_one(),
        "examples_total": db.execute(select(func.count()).select_from(Example)).scalar_one(),
    }


def stats(db: Session) -> dict:
    by_level = dict(
        db.execute(select(Item.cefr_level, func.count()).group_by(Item.cefr_level).order_by(Item.cefr_level)).all()
    )
    by_type = dict(db.execute(select(Item.type, func.count()).group_by(Item.type)).all())
    return {
        "decks": db.execute(select(func.count()).select_from(Deck)).scalar_one(),
        "items": db.execute(select(func.count()).select_from(Item)).scalar_one(),
        "examples": db.execute(select(func.count()).select_from(Example)).scalar_one(),
        "links": db.execute(select(func.count()).select_from(DeckItem)).scalar_one(),
        "by_level": by_level,
        "by_type": by_type,
    }


def main() -> None:
    with SessionLocal() as db:
        if "--stats" in sys.argv:
            report = stats(db)
        else:
            report = run(db)
            report |= {"stats": stats(db)}
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
