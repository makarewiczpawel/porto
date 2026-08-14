# Porto

Prywatna aplikacja webowa (PWA) do codziennej nauki **portugalskiego europejskiego (PT-PT)**.

Codzienna sesja słówek i zwrotów z harmonogramem powtórek (FSRS), ćwiczenia w wielu formach,
quizy i wymowa w głosach pt-PT. Aplikacja jest zamknięta — konto zakłada się kodem zaproszenia.

**Status: fazy 1–3 gotowe.** Działa codzienna nauka w siedmiu formach ćwiczeń, harmonogram
FSRS, streak, quizy z historią wyników, słownik z 430 pozycjami, własne słówka i import listy,
wymowa pt-PT, praca bez zasięgu i PWA instalowalna na telefonie.

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

**Bez zasięgu.** Sesja pobiera się w całości i od tej chwili nie potrzebuje serwera: pytania,
odpowiedzi i nagrania leżą na urządzeniu, ocena dzieje się lokalnie. Odpowiedzi czekają w
kolejce i dosyłają się same, gdy wróci sieć — także po zamknięciu i ponownym otwarciu
aplikacji. Bezpieczne dzięki idempotencji z fazy 1: ta sama partia wysłana dwa razy nie liczy
się podwójnie.

**Własne słówka.** Pojedyncze pozycje z formularza albo cała lista wklejona z arkusza. Import
rozpoznaje przecinki, średniki i tabulatory, sam zgaduje typ pozycji, a wiersz z błędem
raportuje z numerem zamiast przerywać całość.

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
| Wymowa | Google Cloud Text-to-Speech (pt-PT), nagrania w bazie |
| AI | Anthropic Messages API (`anthropic`), model z `AI_MODEL` |
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
cd backend && .venv/bin/python -m pytest tests/ -q     # 142 testy
cd frontend && npm run typecheck && npm run build
```

Testy backendu tworzą i kasują bazę `porto_test` obok bazy deweloperskiej. Adres bazy dla
testów można nadpisać zmienną `TEST_DATABASE_URL`.

## Struktura

```
backend/
  app/
    models/      # ORM: users, items, decks, user_item_state, reviews, …
    routers/     # auth, content (items/decks/settings), study, quizzes, audio, ai
    services/
      scheduler.py     # opakowanie FSRS — jedyne miejsce, które zna bibliotekę
      task_builder.py  # dobór kart, przeplot nowych, wybór trybu, dystraktory
      grader.py        # ocena odpowiedzi pisanych: dobrze / prawie / źle
      tts.py           # synteza mowy — jedyne miejsce, które zna Google
      ai.py            # model językowy — jedyne miejsce, które zna Anthropic
      lexicon.py       # wspólne reguły dopisywania do słownika (rodzajnik, talia)
      importer.py      # parser CSV: wybaczający format, raport z numerami wierszy
      stats.py         # dzienne agregaty i streak w strefie użytkownika
    seed/        # 20 talii PT-PT w JSON + idempotentny loader
  scripts/       # synthesize_all.py — nagrywa całą bazę, wznawialnie
  alembic/       # migracje
  tests/
frontend/
  src/
    api/         # klient HTTP z cichym odświeżaniem tokenu
    components/  # TaskRenderer + tryby ćwiczeń, layout, elementy UI
    pages/       # Dziś, Nauka, Podsumowanie, Słownik, Dodawanie, Talie, Quizy, Postęp, Ustawienia
    store/       # auth (kontekst) + sesja nauki (Zustand + localStorage)
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
ANTHROPIC_API_KEY=<klucz z console.anthropic.com>
AI_MONTHLY_BUDGET_USD=5
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

## AI

Funkcje AI — generowanie zestawów, „dlaczego źle?", ocena tłumaczenia, dogenerowanie zdań
przykładowych — chodzą na Anthropic Messages API przez oficjalny SDK. Bez zmiennej
`ANTHROPIC_API_KEY` po prostu ich nie ma: ekran generowania mówi, że jest wyłączony, przycisk
„dlaczego źle?" się nie pokazuje, a tryb „przetłumacz zdanie" znika z sesji. Reszta aplikacji
działa bez zmian.

Trzy zabezpieczenia przed rachunkiem:

- **Księga.** Każde wywołanie, także nieudane, zostawia wiersz w `ai_generation_jobs` z liczbą
  tokenów i kosztem. Zużycie w bieżącym miesiącu widać w `/ustawienia`.
- **Twardy limit.** Po przekroczeniu `AI_MONTHLY_BUDGET_USD` (domyślnie 5 USD) funkcje AI
  zwracają `429` z komunikatem po polsku, zamiast wydawać dalej.
- **Pamięć podręczna.** Ta sama pomyłka wyjaśniana jest raz; to samo tłumaczenie oceniane raz.
  Klucz to skrót treści pytania, więc powtórka jest darmowa i natychmiastowa.

Nad tym wszystkim stoi zasada, której pilnują testy: **żadna treść z modelu nie trafia do
słownika bez akceptacji człowieka**. Wygenerowany zestaw czeka w zadaniu, aż ktoś odznaczy to,
czego nie chce, poprawi to, co chce inaczej, i kliknie „zatwierdź zaznaczone". Dopiero wtedy
powstają pozycje (`source=ai`), nowa talia i nagrania wymowy.

Prompt systemowy wymienia zakazane brazylizmy parami — „NIE ônibus / TAK autocarro" — bo
polecenie „pisz po europejsku" model traktuje jak sugestię, a konkretną listę jak regułę.

## CI

`.github/workflows/ci.yml` przy każdym pushu i pull requeście sprawdza:
testy backendu na prawdziwym Postgresie, zgodność migracji z modelami (`alembic check`),
załadowanie bazy startowej wraz z jej idempotencją, oraz typy i build frontendu.
