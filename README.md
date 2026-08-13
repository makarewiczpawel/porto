# Porto

Prywatna aplikacja webowa (PWA) do codziennej nauki **portugalskiego europejskiego (PT-PT)**.

Codzienna sesja słówek i zwrotów z harmonogramem powtórek (FSRS), ćwiczenia w wielu formach,
quizy i wymowa w głosach pt-PT. Aplikacja jest zamknięta — konto zakłada się kodem zaproszenia.

**Status: fazy 1, 2 i wymowa z fazy 3 gotowe.** Działa codzienna nauka w siedmiu formach
ćwiczeń, harmonogram FSRS, streak, quizy z historią wyników, słownik z 430 pozycjami, wymowa
pt-PT przy każdym portugalskim słowie i PWA instalowalna na telefonie.

**Tryby ćwiczeń.** Ten sam materiał wraca w coraz trudniejszej formie, zależnie od tego, jak
dobrze znasz słowo: fiszka → test wyboru → wpisywanie z pamięci → luka w zdaniu. Do tego
dopasowywanie par jako rozgrzewka i rozsypanka słów dla całych zdań. Odpowiedzi pisane mają trzy
wyniki, nie dwa — literówka i brakujący akcent liczą się jako „prawie", wracają szybciej niż
poprawna odpowiedź, ale nie kasują postępu jak błąd.

**Wymowa.** Przy każdym portugalskim słowie i zdaniu jest głośnik: tapnięcie odtwarza,
przytrzymanie zwalnia do 0,75×. Nagrania powstają raz, syntezatorem Google w głosie pt-PT, i
leżą w bazie — odtwarzanie nic nie kosztuje i działa bez zasięgu. Doszedł tryb **ze słuchu**:
pytaniem jest samo nagranie, bez napisu. Gdy nagrania jeszcze nie ma, aplikacja sięga po głos
wbudowany w telefon — ale wyłącznie portugalski europejski; brazylijskiego świadomie nie użyje.

**Quizy.** Sprawdzian niezależny od harmonogramu: quiz mierzy, nie uczy, więc domyślnie nie
przesuwa żadnej karty. Pomyłki można jednym kliknięciem dorzucić do jutrzejszej kolejki.

## Dokumentacja

| Dokument | Zawartość |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | Pełna specyfikacja: cele, stack, model danych, endpointy, 55 funkcjonalności, plan faz |
| [`docs/PLAN.md`](docs/PLAN.md) | Plan wykonawczy z zadaniami i punktami kontrolnymi per faza |
| [`docs/mockup.html`](docs/mockup.html) | Klikalny prototyp interfejsu (otwórz w przeglądarce) |

## Stack

| Warstwa | Technologia |
|---|---|
| Backend | FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL 15+ |
| Harmonogram powtórek | `fsrs` (py-fsrs 6.x) |
| Ocena odpowiedzi | `rapidfuzz` (tolerancja literówek i akcentów) |
| Frontend | React 18 · Vite · TypeScript · Tailwind CSS 4 · TanStack Query · Zustand |
| Hosting | Railway (API + baza) · Cloudflare Pages (frontend) |

## Uruchomienie lokalne

Wymagania: Python 3.11+, Node.js 20+, PostgreSQL 15+.

```bash
# 1. Baza danych
createdb porto      # albo: docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=porto -e POSTGRES_DB=porto postgres:16

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # uzupełnij JWT_SECRET, JWT_REFRESH_SECRET, INVITE_CODE
alembic upgrade head
python -m app.seed.seed       # ładuje 20 talii / 430 pozycji PT-PT
uvicorn app.main:app --reload # http://localhost:8000/docs

# 3. Frontend
cd ../frontend
npm install
cp .env.example .env
npm run dev                   # http://localhost:5173
```

> **Uwaga o adresach.** Token odświeżający jest ciasteczkiem `httpOnly`, więc frontend i API
> muszą być na tym samym hoście (`localhost` z `localhost`, `127.0.0.1` z `127.0.0.1`).
> Mieszanie jednego z drugim sprawia, że przeglądarka uzna je za różne witryny i nie zapisze
> ciasteczka — sesja nie przeżyje odświeżenia strony.

## Testy

```bash
cd backend && .venv/bin/python -m pytest tests/ -q     # 120 testów
cd frontend && npm run typecheck && npm run build
```

Testy backendu tworzą i kasują bazę `porto_test` obok bazy deweloperskiej. Adres bazy dla
testów można nadpisać zmienną `TEST_DATABASE_URL`.

## Struktura

```
backend/
  app/
    models/      # ORM: users, items, decks, user_item_state, reviews, …
    routers/     # auth, content (items/decks/settings), study
    services/
      scheduler.py     # opakowanie FSRS — jedyne miejsce, które zna bibliotekę
      task_builder.py  # dobór kart, przeplot nowych, wybór trybu, dystraktory
      grader.py        # ocena odpowiedzi pisanych: dobrze / prawie / źle
      tts.py           # synteza mowy — jedyne miejsce, które zna Google
      stats.py         # dzienne agregaty i streak w strefie użytkownika
    seed/        # 20 talii PT-PT w JSON + idempotentny loader
  scripts/       # synthesize_all.py — nagrywa całą bazę, wznawialnie
  alembic/       # migracje
  tests/
frontend/
  src/
    api/         # klient HTTP z cichym odświeżaniem tokenu
    components/  # TaskRenderer + tryby ćwiczeń, layout, elementy UI
    pages/       # Dziś, Nauka, Podsumowanie, Słownik, Talie, Quizy, Postęp, Ustawienia
    store/       # auth (kontekst) + sesja nauki (Zustand)
docs/
```

## Wdrożenie

**Backend — Railway.** Dodaj PostgreSQL i usługę z tego repo, ustaw **Root Directory: `backend`**.
`Procfile` odpala migracje i bazę startową przed startem serwera (seed jest idempotentny, więc
bezpiecznie chodzi przy każdym restarcie). Zmienne:

```
DATABASE_URL=${{Postgres.DATABASE_URL}}
JWT_SECRET=<openssl rand -base64 36>
JWT_REFRESH_SECRET=<openssl rand -base64 36>
INVITE_CODE=<własny kod>
CORS_ORIGINS=https://porto.pmakarewicz.com
COOKIE_DOMAIN=.pmakarewicz.com
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
GOOGLE_TTS_API_KEY=<klucz API z Google Cloud>
```

Przy generowaniu domeny Railway pyta o port aplikacji — podaj **8080**. Serwer słucha na
`$PORT`, a gdy hosting nie ustawi tej zmiennej, schodzi właśnie na 8080.

Po wdrożeniu `GET /api/health` powinien zwrócić `{"status":"ok","db":true}`.

**Frontend — Cloudflare Pages.** Root directory `frontend`, build `npm run build`, output `dist`,
zmienna `VITE_API_URL=https://api-porto.pmakarewicz.com`. Plik `public/_redirects` obsługuje
przekierowanie tras SPA.

> Vite wkleja `VITE_API_URL` **w czasie builda**. Zmiana tej zmiennej wymaga ponownego
> uruchomienia deploya — inaczej w plikach zostanie stary adres.

## Wymowa

Nagrania powstają **raz**, skryptem, a nie przy każdym odtworzeniu. Cała baza to około
900 klipów i niecałe 8 tysięcy znaków — mieści się w darmowym miesięcznym limicie Google
z ponadstukrotnym zapasem.

```bash
# 1. Klucz: konsola Google Cloud → włącz „Cloud Text-to-Speech API"
#    → API i usługi → Dane logowania → Utwórz klucz API
#    → w Railway dodaj zmienną GOOGLE_TTS_API_KEY

# 2. Synteza (lokalnie albo w konsoli Railway, katalog `backend`)
python -m scripts.synthesize_all --dry-run   # ile i za ile
python -m scripts.synthesize_all             # nagrywa brakujące
```

Skrypt jest wznawialny — przerwanie kosztuje najwyżej jedno nagranie. Domyślnie nagrywa dla
głosów faktycznie wybranych na kontach, więc po zmianie głosu w ustawieniach trzeba go
uruchomić ponownie.

Nagrania trzymane są w tabeli `audio_assets` w bazie, nie w osobnym magazynie plików: przy tej
skali (~10 MB) osobne konto i klucze do S3 kosztowałyby więcej pracy, niż dają korzyści, a tak
wszystko wchodzi do jednej kopii zapasowej. Adres nagrania jest skrótem jego treści, więc
`/api/audio/<hash>.mp3` jest wieczne i cache'owane na rok — również przez service workera, co
daje działającą wymowę offline.

## CI

`.github/workflows/ci.yml` przy każdym pushu i pull requeście sprawdza:
testy backendu na prawdziwym Postgresie, zgodność migracji z modelami (`alembic check`),
załadowanie bazy startowej wraz z jej idempotencją, oraz typy i build frontendu.
