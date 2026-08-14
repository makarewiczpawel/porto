"""Wymowa: odtwarzanie, synteza na żądanie i raport zużycia.

Uwaga o dostępie: samo **odtworzenie** nagrania nie wymaga tokenu, cała reszta
tak. Powód jest praktyczny — `<audio src="…">` w przeglądarce nie potrafi
dołożyć nagłówka `Authorization`, a obejścia (pobranie przez `fetch` do blobu)
psują cache przeglądarki i pamięć offline. Ryzyko jest żadne: adres to skrót
kryptograficzny, a treść to słownikowe „bom dia", nie dane nikogo z użytkowników.
Tworzenie nagrań, lista głosów i zużycie limitu wymagają zalogowania, bo to one
kosztują.
"""

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.errors import not_found, unprocessable
from app.models import AudioAsset, User
from app.services import tts, voice_library

router = APIRouter(prefix="/api/audio", tags=["audio"])

# Nagranie pod danym adresem nigdy się nie zmieni — adres jest hashem jego
# treści. Rok w cache i `immutable` znaczy, że telefon pobiera każde słowo raz
# w życiu.
CACHE_HEADER = "public, max-age=31536000, immutable"


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=tts.MAX_CHARS)
    voice: str | None = Field(default=None, max_length=64)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class SpeakOut(BaseModel):
    url: str
    cache_key: str
    cached: bool


class SynthesizeIn(BaseModel):
    # Czterdzieści nagrań to kilkanaście sekund pracy — na tyle krótko, żeby
    # żądanie nie wisiało, i na tyle długo, żeby pasek postępu ruszał z sensem.
    limit: int = Field(default=40, ge=1, le=200)
    voice: str | None = Field(default=None, max_length=64)


# Zdanie do odsłuchania głosu przed wyborem. Ma w sobie to, po czym poznaje się
# portugalski europejski: ścieśnione „e", szeleszczące „s" na końcu sylaby i
# nosówkę w „não".
SAMPLE_TEXT = "Bom dia! Hoje não vou de comboio, prefiro passear pela cidade."


@router.get("/voices")
def list_voices(user: User = Depends(get_current_user)) -> dict:
    """Głosy pt-PT prosto od dostawcy — do odsłuchania w ustawieniach."""
    if not tts.is_configured():
        return {"configured": False, "voices": []}
    try:
        return {"configured": True, "voices": tts.get_provider().voices()}
    except tts.TTSError as exc:
        raise unprocessable("TTS_FAILED", str(exc)) from exc


@router.get("/usage")
def audio_usage(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return tts.usage(db)


@router.get("/coverage")
def coverage(
    voice: str | None = Query(default=None, max_length=64),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Ile nagrań dla tego głosu już jest, a ilu brakuje.

    Bez tej liczby zmiana głosu wygląda jak brak zmiany: aplikacja nie znajduje
    nagrań, po cichu schodzi na głos z telefonu i nic nie mówi.
    """
    return voice_library.coverage(db, voice or user.settings.tts_voice).as_dict()


@router.post("/synthesize-missing")
def synthesize_missing(
    body: SynthesizeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Dogrywa porcję brakujących nagrań. Front woła w pętli aż do zera."""
    voice = body.voice or user.settings.tts_voice
    try:
        result = voice_library.synthesize_batch(db, voice, body.limit)
    except tts.TTSNotConfigured as exc:
        raise unprocessable("TTS_NOT_CONFIGURED", str(exc)) from exc
    except tts.TTSError as exc:
        raise unprocessable("TTS_FAILED", str(exc)) from exc
    return result.as_dict()


@router.post("/sample", response_model=SpeakOut)
def sample(
    voice: str = Query(min_length=1, max_length=64),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpeakOut:
    """Zdanie na próbę w podanym głosie — do posłuchania przed wyborem.

    Głosu nie da się ocenić z nazwy, a wybranie złego kosztuje całą bibliotekę
    nagraną od nowa. Jedno zdanie to ułamek grosza.
    """
    before = tts.lookup(db, SAMPLE_TEXT, voice, 1.0)
    try:
        asset = tts.speak(db, SAMPLE_TEXT, voice=voice, speed=1.0)
    except tts.TTSNotConfigured as exc:
        raise unprocessable("TTS_NOT_CONFIGURED", str(exc)) from exc
    except tts.TTSLimitReached as exc:
        raise unprocessable("TTS_LIMIT", str(exc)) from exc
    except tts.TTSError as exc:
        raise unprocessable("TTS_FAILED", str(exc)) from exc
    db.commit()
    return SpeakOut(url=tts.audio_url(asset.cache_key), cache_key=asset.cache_key, cached=before is not None)


@router.post("/speak", response_model=SpeakOut)
def speak(
    body: SpeakIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SpeakOut:
    """Wymowa dowolnego tekstu — używane, gdy nagranie nie powstało wcześniej."""
    voice = body.voice or user.settings.tts_voice
    before = tts.lookup(db, body.text, voice, body.speed)
    try:
        asset = tts.speak(db, body.text, voice=voice, speed=body.speed)
    except tts.TTSNotConfigured as exc:
        raise unprocessable("TTS_NOT_CONFIGURED", str(exc)) from exc
    except tts.TTSLimitReached as exc:
        raise unprocessable("TTS_LIMIT", str(exc)) from exc
    except tts.TTSError as exc:
        raise unprocessable("TTS_FAILED", str(exc)) from exc

    db.commit()
    return SpeakOut(url=tts.audio_url(asset.cache_key), cache_key=asset.cache_key, cached=before is not None)


@router.get("/lookup")
def lookup(
    text: str = Query(min_length=1, max_length=tts.MAX_CHARS),
    speed: float = Query(default=1.0, ge=0.5, le=2.0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Czy nagranie już jest? Front pyta o to, zanim pokaże przycisk głośnika."""
    asset = tts.lookup(db, text, user.settings.tts_voice, speed)
    return {"url": tts.audio_url(asset.cache_key) if asset else None}


@router.get("/{cache_key}.mp3")
def play(cache_key: str, db: Session = Depends(get_db)) -> Response:
    asset = db.execute(
        select(AudioAsset).where(AudioAsset.cache_key == cache_key)
    ).scalar_one_or_none()
    if asset is None:
        raise not_found("AUDIO_NOT_FOUND", "Nie ma takiego nagrania.")
    return Response(
        content=asset.data,
        media_type=asset.mime,
        headers={
            "Cache-Control": CACHE_HEADER,
            "ETag": f'"{asset.cache_key}"',
            "Content-Length": str(asset.size),
        },
    )
