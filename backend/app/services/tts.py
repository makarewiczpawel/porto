"""Zamiana tekstu na mowę — jedyne miejsce, które rozmawia z Google.

Trzy zasady, na których stoi ten moduł:

1. **Każde nagranie powstaje raz.** Klucz `sha256(tekst|głos|tempo)` trafia do
   bazy razem z bajtami. Drugie żądanie o to samo nie kosztuje ani grosza, ani
   milisekundy oczekiwania na Google.
2. **Tylko portugalski europejski.** Nazwa głosu musi zaczynać się od `pt-PT`.
   Domyślne „portugalskie" głosy u większości dostawców są brazylijskie, a
   różnica jest słyszalna w pierwszym słowie — dlatego to twardy warunek, a nie
   ustawienie domyślne.
3. **Twardy limit miesięczny.** Rachunek za API rośnie po cichu i bez sufitu.
   Licznik znaków w bieżącym miesiącu zatrzymuje syntezę, zanim to nastąpi.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AudioAsset

GOOGLE_ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"
GOOGLE_VOICES_ENDPOINT = "https://texttospeech.googleapis.com/v1/voices"
REQUIRED_LOCALE = "pt-PT"
MAX_CHARS = 400
TIMEOUT_SECONDS = 30.0


class TTSError(RuntimeError):
    """Synteza się nie udała. Komunikat jest po polsku, bo trafia do interfejsu."""


class TTSNotConfigured(TTSError):
    pass


class TTSLimitReached(TTSError):
    pass


@dataclass(frozen=True)
class Spoken:
    data: bytes
    mime: str
    char_count: int


class Provider(Protocol):
    name: str

    def synthesize(self, text: str, voice: str, speed: float) -> Spoken: ...

    def voices(self) -> list[dict]: ...


class GoogleTTS:
    """Google Cloud Text-to-Speech przez REST i zwykły klucz API.

    Konto serwisowe dałoby to samo, ale wymaga wgrania pliku JSON tam, gdzie nie
    ma systemu plików, i nadania ról w konsoli. Klucz API to jedna zmienna
    środowiskowa — przy aplikacji dla dwóch osób to właściwy kompromis.
    """

    name = "google"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def synthesize(self, text: str, voice: str, speed: float) -> Spoken:
        payload = {
            "input": {"text": text},
            "voice": {"languageCode": REQUIRED_LOCALE, "name": voice},
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": round(float(speed), 2),
                # Krótkie hasła w oderwaniu od zdania brzmią urwanie; lekkie
                # obniżenie tempa mowy załatwia to lepiej niż cisza na końcu.
                "effectsProfileId": ["handset-class-device"],
            },
        }
        try:
            response = httpx.post(
                GOOGLE_ENDPOINT,
                params={"key": self.api_key},
                json=payload,
                timeout=TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:  # sieć padła, DNS, timeout
            raise TTSError(f"Nie udało się połączyć z syntezatorem mowy: {exc}") from exc

        if response.status_code != 200:
            raise TTSError(_google_message(response))

        content = response.json().get("audioContent")
        if not content:
            raise TTSError("Syntezator zwrócił pustą odpowiedź.")

        return Spoken(data=base64.b64decode(content), mime="audio/mpeg", char_count=len(text))

    def voices(self) -> list[dict]:
        try:
            response = httpx.get(
                GOOGLE_VOICES_ENDPOINT,
                params={"key": self.api_key, "languageCode": REQUIRED_LOCALE},
                timeout=TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise TTSError(f"Nie udało się pobrać listy głosów: {exc}") from exc
        if response.status_code != 200:
            raise TTSError(_google_message(response))

        found = []
        for voice in response.json().get("voices", []):
            name = voice.get("name", "")
            if not name.startswith(REQUIRED_LOCALE):
                continue
            found.append(
                {
                    "name": name,
                    "gender": voice.get("ssmlGender", "").lower() or None,
                    # Wavenet/Neural/Chirp brzmią jak człowiek, Standard jak
                    # syntezator z 2010 roku. Wyciągam to na wierzch, żeby
                    # dało się wybrać świadomie.
                    "quality": _quality_of(name),
                }
            )
        return sorted(found, key=lambda v: (v["quality"] == "standard", v["name"]))


def _quality_of(name: str) -> str:
    lowered = name.lower()
    for marker in ("chirp", "neural", "studio", "wavenet", "polyglot"):
        if marker in lowered:
            return marker
    return "standard"


def _google_message(response: httpx.Response) -> str:
    """Google zwraca sensowny powód w JSON-ie; bez tego użytkownik widzi 400."""
    try:
        detail = response.json().get("error", {}).get("message", "")
    except ValueError:
        detail = ""
    if response.status_code in (401, 403):
        return f"Klucz API został odrzucony przez Google. {detail}".strip()
    return f"Synteza nie powiodła się (HTTP {response.status_code}). {detail}".strip()


def get_provider() -> Provider:
    if not settings.google_tts_api_key:
        raise TTSNotConfigured(
            "Synteza mowy nie jest skonfigurowana — brakuje zmiennej GOOGLE_TTS_API_KEY."
        )
    return GoogleTTS(settings.google_tts_api_key)


def is_configured() -> bool:
    return bool(settings.google_tts_api_key)


# ── klucz cache ───────────────────────────────────────────────────────────
def normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


def cache_key(text: str, voice: str, speed: float) -> str:
    raw = f"{normalize_text(text)}|{voice}|{float(speed):.2f}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def audio_url(key: str) -> str:
    return f"/api/audio/{key}.mp3"


def lookup(db: Session, text: str, voice: str, speed: float) -> AudioAsset | None:
    key = cache_key(text, voice, speed)
    return db.execute(select(AudioAsset).where(AudioAsset.cache_key == key)).scalar_one_or_none()


def existing_urls(db: Session, keys: list[str]) -> set[str]:
    """Które z tych nagrań już istnieją — jedno zapytanie zamiast N."""
    if not keys:
        return set()
    rows = db.execute(
        select(AudioAsset.cache_key).where(AudioAsset.cache_key.in_(keys))
    ).scalars()
    return set(rows)


# ── limit miesięczny ──────────────────────────────────────────────────────
def chars_this_month(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = db.execute(
        select(func.coalesce(func.sum(AudioAsset.char_count), 0)).where(
            AudioAsset.created_at >= start
        )
    ).scalar_one()
    return int(total)


def usage(db: Session, now: datetime | None = None) -> dict:
    used = chars_this_month(db, now)
    limit = settings.tts_monthly_char_limit
    stored = db.execute(select(func.count(AudioAsset.id))).scalar_one()
    size = db.execute(select(func.coalesce(func.sum(AudioAsset.size), 0))).scalar_one()
    return {
        "configured": is_configured(),
        "chars_this_month": used,
        "monthly_limit": limit,
        "remaining": max(limit - used, 0),
        "clips_stored": int(stored),
        "bytes_stored": int(size),
    }


# ── synteza z pamięcią podręczną ──────────────────────────────────────────
def speak(
    db: Session,
    text: str,
    voice: str | None = None,
    speed: float = 1.0,
    provider: Provider | None = None,
) -> AudioAsset:
    """Zwraca nagranie dla tekstu, tworząc je tylko gdy jeszcze nie istnieje."""
    clean = normalize_text(text)
    if not clean:
        raise TTSError("Pusty tekst nie ma jak zabrzmieć.")
    if len(clean) > MAX_CHARS:
        raise TTSError(f"Tekst jest dłuższy niż {MAX_CHARS} znaków.")

    voice = voice or settings.tts_voice_default
    if not voice.startswith(REQUIRED_LOCALE):
        # Bez tego jedna literówka w ustawieniach zamienia całą naukę na
        # portugalski brazylijski i nikt tego nie zauważa od razu.
        raise TTSError(
            f"Głos {voice} nie jest głosem portugalskim europejskim "
            f"(oczekiwana nazwa zaczyna się od {REQUIRED_LOCALE}-)."
        )

    key = cache_key(clean, voice, speed)
    found = db.execute(select(AudioAsset).where(AudioAsset.cache_key == key)).scalar_one_or_none()
    if found is not None:
        return found

    if chars_this_month(db) + len(clean) > settings.tts_monthly_char_limit:
        raise TTSLimitReached(
            "Miesięczny limit syntezy mowy został wyczerpany. "
            "Nagrania już zapisane działają dalej."
        )

    engine = provider or get_provider()
    spoken = engine.synthesize(clean, voice, speed)

    asset = AudioAsset(
        cache_key=key,
        text=clean,
        voice=voice,
        speed=speed,
        mime=spoken.mime,
        data=spoken.data,
        size=len(spoken.data),
        provider=engine.name,
        char_count=spoken.char_count,
    )
    db.add(asset)
    db.flush()
    return asset
