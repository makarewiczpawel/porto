"""Nagrywa całą bazę: hasła, ich wolniejsze wersje i zdania przykładowe.

Uruchomienie (lokalnie albo w konsoli Railway):

    python -m scripts.synthesize_all              # brakujące nagrania
    python -m scripts.synthesize_all --dry-run    # tylko policz, nic nie wołaj
    python -m scripts.synthesize_all --limit 50   # partiami

Skrypt jest przerywalny i wznawialny: każde nagranie zapisuje się osobno, więc
Ctrl+C albo zerwane połączenie kosztuje najwyżej jedno hasło. Ponowne
uruchomienie pomija to, co już jest.
"""

from __future__ import annotations

import argparse
import sys
import time

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import UserSettings
from app.services import tts
from app.services.voice_library import planned

# Google przyjmuje spokojnie kilka żądań na sekundę; ta przerwa trzyma nas
# z dala od limitu, a przy kilkuset nagraniach kosztuje minutę.
PAUSE_SECONDS = 0.12


def voices_in_use(db) -> list[str]:
    """Głosy, których ktoś naprawdę używa, plus domyślny.

    Nagrania są kluczowane nazwą głosu, więc synteza tylko dla wartości
    domyślnej zostawiłaby bez dźwięku każdego, kto zmienił głos w ustawieniach —
    po cichu, bo brak nagrania nie jest błędem.
    """
    chosen = db.execute(select(UserSettings.tts_voice).distinct()).scalars().all()
    unique = {voice for voice in chosen if voice} | {settings.tts_voice_default}
    return sorted(unique)


def main() -> int:
    parser = argparse.ArgumentParser(description="Synteza wymowy dla całej bazy.")
    parser.add_argument("--dry-run", action="store_true", help="policz, nie syntezuj")
    parser.add_argument("--limit", type=int, default=0, help="maksymalna liczba nowych nagrań")
    parser.add_argument("--voice", default=None, help="domyślnie: głosy używane przez konta")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        voices = [args.voice] if args.voice else voices_in_use(db)
        texts = planned(db)
        wanted = [(text, speed, voice) for voice in voices for text, speed in texts]
        keys = [tts.cache_key(text, voice, speed) for text, speed, voice in wanted]
        have = tts.existing_urls(db, keys)
        missing = [
            entry for entry, key in zip(wanted, keys, strict=True) if key not in have
        ]

        chars = sum(len(text) for text, _, _ in missing)
        print(f"Głosy:       {', '.join(voices)}")
        print(f"Zaplanowane: {len(wanted)} nagrań")
        print(f"Już w bazie: {len(wanted) - len(missing)}")
        print(f"Do nagrania: {len(missing)} ({chars} znaków)")

        if args.dry_run or not missing:
            return 0
        if not tts.is_configured():
            print("\nBrakuje GOOGLE_TTS_API_KEY — nie ma czym syntezować.", file=sys.stderr)
            return 1

        provider = tts.get_provider()
        todo = missing[: args.limit] if args.limit else missing
        done = failed = 0
        for index, (text, speed, voice) in enumerate(todo, start=1):
            try:
                tts.speak(db, text, voice=voice, speed=speed, provider=provider)
                db.commit()
                done += 1
            except tts.TTSLimitReached as exc:
                db.rollback()
                print(f"\n{exc}", file=sys.stderr)
                break
            except tts.TTSError as exc:
                db.rollback()
                failed += 1
                print(f"\n  ✕ {text!r} ({voice}, {speed}×): {exc}", file=sys.stderr)
                if failed >= 5:
                    print("Pięć błędów pod rząd — przerywam.", file=sys.stderr)
                    break
            else:
                failed = 0
            print(f"\r  {index}/{len(todo)}  {text[:40]:<40}", end="", flush=True)
            time.sleep(PAUSE_SECONDS)

        print(f"\nGotowe: {done} nowych nagrań.")
        usage = tts.usage(db)
        print(
            f"W tym miesiącu: {usage['chars_this_month']} / {usage['monthly_limit']} znaków. "
            f"W bazie: {usage['clips_stored']} nagrań, {usage['bytes_stored'] / 1_048_576:.1f} MB."
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
