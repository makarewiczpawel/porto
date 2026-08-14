"""Ile z biblioteki nagrań istnieje dla danego głosu — i dogrywanie brakujących.

Nagrania są kluczowane nazwą głosu, więc zmiana głosu w ustawieniach nie
przerabia niczego, tylko odsyła aplikację po zbiór nagrań, którego jeszcze nie
ma. Do tej pory kończyło się to najgorszym z możliwych zachowań: cisza po
stronie serwera, przycisk głośnika po cichu schodzi na głos wbudowany w
telefon — czyli dokładnie ten syntetyczny, od którego uciekaliśmy — i nic
nigdzie nie mówi, że czegoś brakuje.

Ten moduł istnieje po to, żeby brak nagrań był **widoczny i policzalny**, a
dogranie ich nie wymagało konsoli.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Item
from app.services import tts

# Wolniejsze podejście pod przytrzymanie głośnika. Stała mieszka tutaj, a nie
# w budowniczym zadań, bo dotyczy biblioteki nagrań, nie sesji nauki.
SLOW_SPEED = 0.75


@dataclass(frozen=True)
class Coverage:
    voice: str
    planned: int
    present: int

    @property
    def missing(self) -> int:
        return max(self.planned - self.present, 0)

    @property
    def complete(self) -> bool:
        return self.missing == 0

    def as_dict(self) -> dict:
        return {
            "voice": self.voice,
            "planned": self.planned,
            "present": self.present,
            "missing": self.missing,
            "complete": self.complete,
        }


def planned(db: Session) -> list[tuple[str, float]]:
    """Pary (tekst, tempo), które powinny istnieć dla każdego głosu."""
    wanted: list[tuple[str, float]] = []
    seen: set[tuple[str, float]] = set()

    items = (
        db.execute(select(Item).options(selectinload(Item.examples)).where(Item.verified.is_(True)))
        .scalars()
        .unique()
        .all()
    )
    for item in items:
        for text, speed in (
            (item.display_pt, 1.0),
            (item.display_pt, SLOW_SPEED),
            *[(example.pt, 1.0) for example in item.examples],
        ):
            clean = tts.normalize_text(text)
            if not clean or (clean, speed) in seen:
                continue
            seen.add((clean, speed))
            wanted.append((clean, speed))
    return wanted


def missing_for(db: Session, voice: str) -> list[tuple[str, float]]:
    wanted = planned(db)
    keys = [tts.cache_key(text, voice, speed) for text, speed in wanted]
    have = tts.existing_urls(db, keys)
    return [entry for entry, key in zip(wanted, keys, strict=True) if key not in have]


def coverage(db: Session, voice: str) -> Coverage:
    wanted = planned(db)
    keys = [tts.cache_key(text, voice, speed) for text, speed in wanted]
    have = tts.existing_urls(db, keys)
    return Coverage(voice=voice, planned=len(wanted), present=len(have))


@dataclass
class BatchResult:
    done: int
    failed: int
    remaining: int
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "done": self.done,
            "failed": self.failed,
            "remaining": self.remaining,
            "error": self.error,
        }


def synthesize_batch(
    db: Session, voice: str, limit: int, provider: tts.Provider | None = None
) -> BatchResult:
    """Dogrywa najwyżej `limit` brakujących nagrań i mówi, ile zostało.

    Porcjami, bo całość to kilkaset wywołań i kilka minut — dłużej, niż powinno
    trwać jedno żądanie HTTP. Wywołujący pyta ponownie, aż `remaining` spadnie
    do zera, i po drodze ma czym pokazać postęp.
    """
    todo = missing_for(db, voice)
    remaining = len(todo)
    if not todo:
        return BatchResult(done=0, failed=0, remaining=0)

    engine = provider or tts.get_provider()
    done = failed = streak = 0
    error: str | None = None
    for text, speed in todo[:limit]:
        try:
            tts.speak(db, text, voice=voice, speed=speed, provider=engine)
            db.commit()
        except tts.TTSLimitReached as exc:
            db.rollback()
            error = str(exc)
            break
        except tts.TTSError as exc:
            db.rollback()
            failed += 1
            streak += 1
            # Pojedyncze hasło potrafi się nie udać z powodu sieci. Pięć pod
            # rząd znaczy, że nie uda się żadne — najczęściej głos nie przyjmuje
            # tego, o co go prosimy — i dalsze próby tylko palą czas i pieniądze.
            if streak >= 5:
                error = str(exc)
                break
        else:
            done += 1
            streak = 0

    return BatchResult(done=done, failed=failed, remaining=max(remaining - done, 0), error=error)
