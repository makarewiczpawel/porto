"""Lekcje gramatyki: spis i pojedyncza lekcja z nagraniami przykładów.

Treść jest statyczna (`app/grammar`), więc jedyne, co tu zależy od
użytkownika, to nagrania: przykłady brzmią głosem wybranym w ustawieniach,
tak samo jak fiszki. Brakujące nagrania dogrywają się w tle przy pierwszym
otwarciu lekcji, a odpowiedź mówi o tym wprost (`audio_pending`), żeby ekran
mógł dopytać i podmienić głos telefonu na właściwy, zamiast zostawić go na
zawsze bez słowa wyjaśnienia.
"""

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app import grammar
from app.db import get_db
from app.deps import get_current_user
from app.errors import not_found
from app.models import User
from app.services import tts, voice_library

router = APIRouter(prefix="/api/grammar", tags=["grammar"])


def _summary(lesson: grammar.Lesson) -> dict:
    return {
        "slug": lesson.slug,
        "title": lesson.title,
        "summary": lesson.summary,
        "level": lesson.level,
        "part": lesson.part,
        "position": lesson.position,
        "examples": len(lesson.examples()),
        "questions": len(lesson.check),
    }


@router.get("")
def list_lessons(_: User = Depends(get_current_user)) -> dict:
    return {"lessons": [_summary(lesson) for lesson in grammar.lessons()]}


@router.get("/{slug}")
def get_lesson(
    slug: str,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    lesson = grammar.by_slug(slug)
    if lesson is None:
        raise not_found("LESSON_NOT_FOUND", "Nie ma takiej lekcji.")

    voice = user.settings.tts_voice
    texts = [example.pt for example in lesson.examples()]
    keys = {text: tts.cache_key(text, voice, 1.0) for text in texts}
    have = tts.existing_urls(db, list(keys.values()))
    audio = {text: tts.audio_url(key) for text, key in keys.items() if key in have}

    missing = [text for text in texts if text not in audio]
    pending = bool(missing) and tts.is_configured()
    if pending:
        background.add_task(voice_library.synthesize_texts, f"lekcja:{lesson.slug}", missing, voice)

    blocks = []
    for block in lesson.blocks:
        data = block.model_dump()
        if block.type == "examples":
            for example in data["items"]:
                example["audio"] = audio.get(example["pt"])
        blocks.append(data)

    ordered = grammar.lessons()
    index = lesson.position - 1
    neighbour = lambda i: _summary(ordered[i]) if 0 <= i < len(ordered) else None  # noqa: E731

    return {
        **_summary(lesson),
        "blocks": blocks,
        "check": [question.model_dump() for question in lesson.check],
        "audio_pending": pending,
        "previous": neighbour(index - 1),
        "next": neighbour(index + 1),
    }
