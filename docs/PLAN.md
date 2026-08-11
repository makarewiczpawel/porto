# Plan budowy: Porto

**Powiązany dokument:** [PRD.md](./PRD.md)
**Data:** 2026-08-11

Ten dokument to instrukcja wykonawcza — kolejność prac, konkretne zadania i punkty kontrolne. PRD mówi **co** budujemy, ten plan mówi **w jakiej kolejności** i **jak sprawdzić, że działa**.

---

## Zasady pracy

1. **Jedna faza = jeden wdrożony kawałek produktu.** Po każdej fazie aplikacja jest używalna, nie „prawie gotowa". Faza 1 to działająca codzienna nauka, a nie „szkielet bez treści".
2. **Deploy wcześnie.** Wdrożenie na Railway i Cloudflare robimy w Fazie 1, krok 1.6 — zanim powstanie połowa funkcji. Wdrażanie gotowej aplikacji po miesiącu to najdroższy możliwy moment na odkrycie problemów z CORS, cookies i domenami.
3. **Migracje od pierwszego dnia.** Każda zmiana modelu = migracja Alembic. Nigdy `create_all()` na produkcji.
4. **Treść równolegle z kodem.** Baza 800 słówek nie powstanie w jeden wieczór — budujemy ją partiami po ~50 pozycji w tle, podczas gdy powstaje kod.
5. **Mobile-first dosłownie.** Każdy nowy widok sprawdzamy najpierw w DevTools przy szerokości 390 px, a raz na fazę na prawdziwym telefonie.
6. **Sekrety tylko w zmiennych środowiskowych.** Żadnego klucza API w repo — `.env` w `.gitignore` od pierwszego commita.

---

## Kolejność faz i zależności

```
Faza 1 (MVP: nauka działa)
   │
   ├──► Faza 2 (tryby ćwiczeń + quizy)      ── niezależna od 3
   │
   ├──► Faza 3 (audio + offline)            ── niezależna od 2
   │        │
   │        └──► tryb listening wymaga audio
   │
   ├──► Faza 4 (AI)                         ── wymaga tylko Fazy 1
   │
   └──► Faza 5 (statystyki, import, polish) ── wymaga danych z 1-2
```

Fazy 2, 3 i 4 są od siebie niezależne — kolejność można zmienić. Rekomendowana jest podana wyżej: **więcej trybów** daje najwięcej wartości na godzinę pracy, bo urozmaica codzienne używanie aplikacji, którą już się ma.

---

## Faza 0 — Przygotowanie [~2 godziny]

Do zrobienia raz, przed pisaniem kodu.

- [ ] **0.1** Konta i dostępy: Railway (projekt + Postgres), Cloudflare (Pages + R2 + DNS dla `pmakarewicz.com`), Google Cloud (projekt + włączone Text-to-Speech API + konto serwisowe), Anthropic (klucz API).
- [ ] **0.2** Struktura repo: katalogi `backend/`, `frontend/`, `docs/`; `.gitignore` (Python, Node, `.env`, `.venv`, `dist/`); `README.md` z opisem projektu i instrukcją uruchomienia.
- [ ] **0.3** DNS w Cloudflare: rekordy dla `porto.pmakarewicz.com` (front), `api-porto.pmakarewicz.com` (backend), `audio-porto.pmakarewicz.com` (R2) — nawet jeśli jeszcze nie wskazują na nic.
- [ ] **0.4** Decyzja o głosie TTS: odsłuchać dostępne głosy `pt-PT-*` w konsoli Google Cloud na 3 zdaniach testowych, zapisać wybór w PRD (ryzyko #2). Można zrobić przed Fazą 3, ale wcześniejsze sprawdzenie chroni przed przebudową planu audio.

**Punkt kontrolny:** `git push` działa, wszystkie klucze API są wygenerowane i zapisane w menedżerze haseł.

---

## Faza 1 — MVP: codzienna nauka [~2–3 tygodnie]

**Cel fazy:** wieczorem, na telefonie, jednym kliknięciem wchodzę w sesję 25 kart i uczę się portugalskiego z realnym harmonogramem powtórek.

### 1.1 Szkielet backendu [~3 h]
- [ ] FastAPI + struktura katalogów (patrz Aneks w PRD), `config.py` na Pydantic Settings
- [ ] Połączenie z lokalnym Postgresem (Docker), SQLAlchemy 2.0, Alembic zainicjowany
- [ ] `GET /api/health` zwraca `{status, db, version}` i faktycznie odpytuje bazę
- [ ] CORS skonfigurowany z listy w `CORS_ORIGINS`

### 1.2 Auth [~4 h]
- [ ] Modele `users`, `user_settings`; migracja
- [ ] Argon2id na hasłach (`passlib[argon2]`)
- [ ] `POST /api/auth/register` z walidacją `INVITE_CODE` (`403` przy złym kodzie, `409` przy zajętym emailu)
- [ ] `POST /api/auth/login` → access token w body, refresh w httpOnly + SameSite=Strict + Secure cookie
- [ ] `POST /api/auth/refresh`, `POST /api/auth/logout`, `GET /api/auth/me`
- [ ] Zależność `get_current_user` używana przez wszystkie chronione endpointy
- [ ] Rate limiting na `/api/auth/*` (10 żądań/min na IP)
- [ ] Domyślne `user_settings` tworzone automatycznie przy rejestracji

> **Uwaga o cookies:** front (`porto.pmakarewicz.com`) i API (`api-porto.pmakarewicz.com`) to różne subdomeny. Refresh cookie musi mieć `Domain=.pmakarewicz.com`, a fetch po stronie frontu `credentials: 'include'`. To najczęstsze źródło „działa lokalnie, nie działa na produkcji" — dlatego deploy jest w tej samej fazie.

### 1.3 Model treści [~4 h]
- [ ] Modele `items`, `examples`, `decks`, `deck_items`; migracja
- [ ] Indeks GIN pełnotekstowy na `pt` + `pl`, indeks `(cefr_level, part_of_speech)`, unikalność `(pt, pl)`
- [ ] `GET /api/items` z wyszukiwaniem, filtrami i paginacją
- [ ] `GET /api/items/{id}` ze stanem powtórki bieżącego użytkownika
- [ ] `GET /api/decks` z licznikami `total / due / learned` (jedno zapytanie z agregacją, nie N+1)
- [ ] `GET /api/decks/{id}`

### 1.4 Silnik nauki [~8 h] — najważniejszy fragment całego projektu
- [ ] Modele `user_item_state`, `reviews`, `study_sessions`, `daily_stats`; migracja; indeks `(user_id, due)`
- [ ] `services/scheduler.py` — opakowanie biblioteki `fsrs`: `schedule(state, rating, now) -> new_state`, konfiguracja z `desired_retention` użytkownika
- [ ] `services/task_builder.py`:
  - pobranie kart `due` (limit + sort po `due`)
  - dobranie nowych pozycji (limit `new_per_day`, kolejność `deck_items.position`)
  - **przeplot**: nowe wplatane co 4–5 powtórek zamiast na początku
  - wybór trybu wg tabeli z PRD 6.3
  - generowanie dystraktorów do MCQ: ta sama część mowy i poziom, preferencja tej samej talii, wykluczenie synonimów; fallback na losowe z tego poziomu, gdy kandydatów < 3
- [ ] `POST /api/study/sessions` zwraca kompletną sesję jednym responsem (zadania gotowe do renderowania)
- [ ] `GET /api/study/sessions/active` — wznawianie
- [ ] `POST /api/study/sessions/{id}/answers` — **batch**, idempotentny po `(session_id, item_id, direction, question_index)`, żeby ponowna wysyłka z kolejki offline nie zdublowała powtórki
- [ ] `POST /api/study/sessions/{id}/finish` — podsumowanie + aktualizacja `daily_stats` + przeliczenie streaka w strefie użytkownika
- [ ] `GET /api/study/queue/summary`
- [ ] Testy jednostkowe: scheduler (4 oceny → sensowne interwały), przeplot kolejki, dystraktory (nigdy nie zawierają poprawnej odpowiedzi), idempotencja batcha

> **Idempotencja jest wymagana już tutaj**, mimo że offline przychodzi dopiero w Fazie 3. Dorobienie jej później oznacza migrację i przepisanie logiki zapisu powtórek.

### 1.5 Baza startowa [~6 h, rozłożone] — praca równoległa
- [ ] Format `backend/app/seed/items.json` + skrypt `seed.py` (idempotentny: ponowne uruchomienie nie duplikuje)
- [ ] ~20 talii tematycznych A1–A2: Powitania i uprzejmości · Liczby i czas · Rodzina · Jedzenie i restauracja · Zakupy · Dom i mieszkanie · Transport i kierunki · Praca i zawody · Kolory i opisy · Pogoda i pory roku · Ciało i zdrowie · Czasowniki podstawowe · Czasowniki nieregularne (ser/estar/ter/ir/fazer) · Przymiotniki podstawowe · Przyimki i spójniki · Zwroty na co dzień · W kawiarni · Telefon i internet · Podróż i hotel · Small talk
- [ ] ~40 pozycji na talię (słówka + zwroty + po kilka zdań), każda z tłumaczeniem, rodzajnikiem dla rzeczowników i minimum jednym zdaniem przykładowym
- [ ] Weryfikacja PT-PT: brak brazylizmów (*você* → *tu*, *trem* → *comboio*, *ônibus* → *autocarro*, *café da manhã* → *pequeno-almoço*, *celular* → *telemóvel*, *banheiro* → *casa de banho*)
- [ ] Notatki przy pozycjach ryzykownych: fałszywi przyjaciele (*esquisito* ≠ „wyszukany", *constipado* ≠ „zaparty"), różnice PT-PT/PT-BR

> Pozycje niepewne oznaczamy `verified=false` — nie wchodzą do rotacji nauki, ale są w bazie i czekają na sprawdzenie. Lepsza pusta talia niż talia ucząca błędów.

### 1.6 Deployment [~3 h] — **robimy teraz, nie na końcu**
- [ ] Railway: serwis z `backend/`, Postgres, zmienne środowiskowe, `alembic upgrade head` w komendzie startowej
- [ ] Domena `api-porto.pmakarewicz.com` → Railway
- [ ] Cloudflare Pages: build z `frontend/`, domena `porto.pmakarewicz.com`
- [ ] Test end-to-end: rejestracja i logowanie **z telefonu**, na produkcji (weryfikuje cookies między subdomenami)
- [ ] Seed uruchomiony na produkcyjnej bazie

### 1.7 Szkielet frontendu [~5 h]
- [ ] Vite + React 18 + TypeScript + Tailwind, ścieżki aliasowane (`@/`)
- [ ] Klient API z automatycznym odświeżaniem tokenu przy `401` (jedno odświeżenie, potem wylogowanie)
- [ ] TanStack Query, Zustand na stan sesji
- [ ] Routing + guard tras chronionych
- [ ] Layout mobilny: dolna nawigacja (Dziś / Słownik / Quizy / Postęp), motyw jasny/ciemny
- [ ] `/login` — logowanie i rejestracja z kodem zaproszenia

### 1.8 Ekran „Dziś" [~3 h]
- [ ] `QueueSummary`: liczba powtórek, nowych, postęp do celu
- [ ] `ProgressRing` + `StreakBadge`
- [ ] Duży przycisk „Ucz się" (dolna ⅓ ekranu, zasięg kciuka)
- [ ] Stan pusty: „Na dziś gotowe ✓" + skrót do dodatkowej porcji nowych pozycji

### 1.9 Sesja nauki [~8 h]
- [ ] `TaskRenderer` z dyskryminatorem `mode` i wspólnym kontraktem `{task, onAnswer, onSkip}` — od razu przygotowany na 7 trybów
- [ ] `FlashCard` z animacją obrotu i `RatingBar` (Again / Hard / Good / Easy + przewidywany interwał)
- [ ] `ChoiceGrid` 2×2 z natychmiastowym feedbackiem kolorem
- [ ] Pasek postępu, krzyżyk „przerwij" (zapisuje postęp), skróty klawiaturowe na desktopie
- [ ] Kolejka odpowiedzi w pamięci + wysyłka batchem co 5 odpowiedzi (fundament pod offline)
- [ ] `/study/summary`: wynik, czas, streak, lista błędów z „powtórz teraz"
- [ ] Wznawianie przerwanej sesji przy wejściu na `/study`

### 1.10 Słownik [~4 h]
- [ ] `/items` — wyszukiwarka z debounce, filtry (poziom, typ, talia), lista wirtualizowana
- [ ] `/items/:id` — pełne dane, przykłady, historia powtórek
- [ ] `/decks` i `/decks/:id` z przyciskiem „ucz się tej talii"

### 1.11 PWA [~2 h]
- [ ] `vite-plugin-pwa`, manifest, ikony (192/512/maskable), splash
- [ ] Service worker: cache app shell (na razie bez offline dla danych)
- [ ] Test instalacji na iOS i Androidzie

### Definition of Done — Faza 1
- [ ] Oba konta działają na produkcji, każde z własnym postępem
- [ ] Trzy kolejne dni pełnych sesji na telefonie, bez błędów
- [ ] Zamknięcie aplikacji w połowie sesji → postęp odtworzony po ponownym wejściu
- [ ] Streak przeskakuje poprawnie o północy czasu `Europe/Warsaw`
- [ ] Karty powtórzone dziś wracają w terminach wyznaczonych przez FSRS (weryfikacja w bazie: `due` rośnie z każdą poprawną odpowiedzią)
- [ ] Aplikacja zainstalowana na ekranie głównym obu telefonów
- [ ] Minimum 600 zweryfikowanych pozycji w bazie produkcyjnej

---

## Faza 2 — Tryby ćwiczeń i quizy [~2 tygodnie]

**Cel fazy:** ten sam materiał wraca w siedmiu formach, a wiedzę można sprawdzić testem niezależnym od harmonogramu.

### 2.1 Ocena odpowiedzi tekstowych [~4 h]
- [ ] `services/grader.py`: normalizacja (małe litery, usunięcie interpunkcji i podwójnych spacji), porównanie z `pt_alt` / `pl_alt`
- [ ] Warstwa akcentów: porównanie po usunięciu diakrytyków → wynik `accent` (traktowany wg `accent_strict`)
- [ ] Warstwa literówek: `rapidfuzz`, odległość Levenshteina ≤ 1 dla słów ≥ 4 znaków → wynik `typo`
- [ ] Zwracany kształt: `{is_correct, match: exact|accent|typo|wrong, correct_answer, diff}`
- [ ] Testy: 30 przypadków brzegowych (rodzajniki, wielkie litery, `ç`, warianty tłumaczeń, spacje)

### 2.2 Nowe tryby [~10 h]
- [ ] `TypeAnswer` + pasek diakrytyków (á à â ã ç é ê í ó ô õ ú), `autocorrect/autocapitalize/spellcheck = off`
- [ ] Wizualizacja różnicy znak po znaku przy wyniku `typo` lub `accent`
- [ ] `ClozeSentence` — luka inline, tłumaczenie pod spodem jako kontekst; generowanie luk z `examples.cloze_start/end`, a przy braku danych automatycznie po dopasowaniu formy hasła w zdaniu
- [ ] `MatchingGrid` 5×2 z animacją znikania par
- [ ] `WordBank` — klocki, tap dodaje/usuwa, sprawdzenie po komplecie (tylko `type=sentence`)
- [ ] Rozszerzenie `task_builder` o nowe tryby i pełną tabelę doboru z PRD 6.3
- [ ] Ustawienie „aktywne tryby" w `/settings` (F03)

### 2.3 Edycja treści [~5 h]
- [ ] `POST/PATCH/DELETE /api/items`, `POST /api/items/{id}/examples`
- [ ] `/items/new` — formularz minimalny (pt + pl) z opcjonalnymi polami gramatycznymi
- [ ] Tworzenie i edycja własnych talii, dopinanie/odpinanie pozycji
- [ ] `POST /api/study/items/{id}/suspend` i `/reset` + przyciski w widoku pozycji

### 2.4 Moduł quizów [~10 h]
- [ ] Modele `quizzes`, `quiz_attempts`, `quiz_answers`; migracja
- [ ] `POST /api/quizzes/quick` — szybki quiz bez zapisywania konfiguracji
- [ ] CRUD zapisywanych konfiguracji + walidacja (`422`, gdy filtr daje mniej pozycji niż `count`)
- [ ] Podejście: zamrożenie pytań w `quiz_attempts.questions`, odpowiedzi bez ujawniania poprawnych do `submit`
- [ ] `submit` → wynik %, czas, lista błędów
- [ ] „Dodaj błędy do powtórek" — ustawia `due = jutro` dla pomylonych pozycji (bez modyfikacji `stability`)
- [ ] Widoki: `/quiz`, `/quiz/:attemptId`, `/quiz/:attemptId/result`

### Definition of Done — Faza 2
- [ ] Jedna sesja miesza minimum 5 różnych trybów
- [ ] Wpisywanie z telefonu działa bez walki z autokorektą, pasek diakrytyków jest w zasięgu kciuka
- [ ] `avo` zamiast `avó` daje „prawie dobrze" i ocenę `Hard`, nie błąd (przy `accent_strict=false`)
- [ ] Quiz z 20 pytań: wynik, lista błędów, błędy w kolejce na jutro
- [ ] Słówko dodane z telefonu pojawia się w nauce tego samego dnia

---

## Faza 3 — Audio i offline [~1,5 tygodnia]

**Cel fazy:** słychać portugalski europejski, a brak zasięgu nie przerywa nauki.

### 3.1 Serwis TTS [~6 h]
- [ ] Konto serwisowe Google w zmiennej `GOOGLE_APPLICATION_CREDENTIALS_JSON` (cały JSON jako string — Railway nie ma systemu plików do wgrywania kluczy)
- [ ] `services/tts.py`: `synthesize(text, voice, speed) -> url`, klucz cache `sha256(text|voice|speed)`
- [ ] Model `audio_assets`; migracja
- [ ] Upload do R2 przez `boto3` (endpoint S3-kompatybilny), publiczny URL
- [ ] Licznik znaków miesięcznie + twardy limit `TTS_MONTHLY_CHAR_LIMIT` → `429`
- [ ] `GET /api/audio`, `POST /api/audio/prefetch`, `GET /api/audio/usage`

### 3.2 Masowa synteza [~2 h]
- [ ] Skrypt `scripts/synthesize_all.py`: cała baza (hasła + zdania przykładowe), z progresem i wznawianiem po przerwaniu
- [ ] Job nocny: prefetch audio dla pozycji `due` w ciągu najbliższych 24 h

### 3.3 Audio na froncie [~4 h]
- [ ] `AudioButton`: stany (ładowanie / gotowe / błąd), preload w tle, długie przytrzymanie = 0,75×
- [ ] Fallback Web Speech API z wymuszeniem `lang="pt-PT"`, gdy plik niedostępny
- [ ] Autoplay przy odsłonięciu odpowiedzi (przełącznik w ustawieniach)
- [ ] Ustawienia audio: wybór głosu z podglądem, tempo

### 3.4 Tryb listening [~3 h]
- [ ] Zadanie: audio bez tekstu → wpisz lub wybierz z 4 opcji
- [ ] Włączenie do tabeli doboru trybów (karty o `stability >= 21 dni`)
- [ ] Wymóg: pozycja bez audio nigdy nie trafia do tego trybu

### 3.5 Offline [~6 h]
- [ ] Dexie: schemat lokalny (`session`, `answers_queue`)
- [ ] Zapis sesji przy pobraniu, kolejkowanie odpowiedzi lokalnie
- [ ] Synchronizacja przy `online` i przy starcie aplikacji, z wykorzystaniem idempotencji z 1.4
- [ ] Cache plików audio bieżącej sesji w service workerze
- [ ] Wskaźnik „offline — postęp zapisany lokalnie" w interfejsie sesji

### Definition of Done — Faza 3
- [ ] Każda zweryfikowana pozycja i każde zdanie przykładowe ma audio pt-PT
- [ ] Pełna sesja przeprowadzona w trybie samolotowym; po powrocie online cały postęp jest na serwerze, bez duplikatów w `reviews`
- [ ] Audio startuje < 200 ms po kliknięciu (plik z CDN, prefetch)
- [ ] Miesięczne zużycie znaków TTS widoczne w `/api/audio/usage`

---

## Faza 4 — AI [~1,5 tygodnia]

**Cel fazy:** baza rośnie na żądanie, a błędy da się zrozumieć.

### 4.1 Fundament [~4 h]
- [ ] `services/ai.py`: Anthropic SDK, model z `AI_MODEL`, timeouty i retry
- [ ] Model `ai_generation_jobs`; migracja
- [ ] Log tokenów i kosztu każdego wywołania; twardy limit `AI_MONTHLY_BUDGET_USD` → `429` z czytelnym komunikatem
- [ ] Rate limit `/api/ai/*` (20/h)

### 4.2 Generowanie zestawów [~6 h]
- [ ] Prompt systemowy wymuszający PT-PT: jawna lista zakazanych brazylizmów, wymóg podania rodzajnika i rodzaju dla rzeczowników, zdanie przykładowe do każdej pozycji, wyjście jako ścisły JSON
- [ ] Walidacja odpowiedzi schematem Pydantic; niepoprawny JSON → jedna próba naprawcza, potem `failed`
- [ ] Automatyczne odrzucanie pozycji już istniejących w bazie (deduplikacja po `(pt, pl)`)
- [ ] Ekran przeglądu: lista propozycji z checkboxami, edycja inline tłumaczeń i notatek, „zatwierdź zaznaczone"
- [ ] Akceptacja → `items` (`source=ai`, `verified=true`), nowa talia, kolejka syntezy audio

### 4.3 Feedback [~5 h]
- [ ] `POST /api/ai/explain` — po błędzie przycisk „dlaczego źle?"; odpowiedź maks. 2 zdania po polsku, cache'owana per `(item_id, user_answer)`, żeby ta sama pomyłka nie kosztowała dwa razy
- [ ] `POST /api/ai/grade-translation` — ocena 0–100, feedback, poprawiona wersja
- [ ] Tryb `translate_ai` w sesji (opcjonalny, wyłączony domyślnie ze względu na koszt i czas odpowiedzi)
- [ ] `POST /api/ai/examples` — dogenerowanie zdań przykładowych dla pozycji, która ich nie ma
- [ ] Widok `/settings` → zużycie AI w bieżącym miesiącu

### Definition of Done — Faza 4
- [ ] „20 zwrotów A2 u lekarza" → propozycje w < 30 s, po przeglądzie w nowej talii z audio
- [ ] Żadna treść z AI nie trafia do bazy bez akceptacji
- [ ] Przekroczenie limitu miesięcznego zwraca `429` z komunikatem, nie błąd 500
- [ ] Ręczny przegląd 20 wygenerowanych pozycji: brak brazylizmów, poprawne rodzajniki

---

## Faza 5 — Statystyki, import, dopracowanie [~1 tydzień]

### 5.1 Statystyki [~6 h]
- [ ] `GET /api/stats/overview`, `/heatmap`, `/forecast`, `/leeches`, `/weakest`
- [ ] `/stats`: kafelki (streak, opanowane, retencja, czas), `ActivityHeatmap`, `ForecastChart`, lista trudnych słów z akcjami (zawieś / zresetuj / edytuj)

### 5.2 Import i eksport [~4 h]
- [ ] `POST /api/items/import` — CSV (`pt,pl,type,level,pos,notes`), limit 2000 wierszy, raport `{created, skipped_duplicates, errors[]}` z numerami wierszy
- [ ] Interfejs importu: wklejenie tekstu lub plik, podgląd pierwszych 10 wierszy przed zatwierdzeniem
- [ ] Eksport całej bazy do CSV/JSON

### 5.3 Uzupełnienia [~5 h]
- [ ] Test poziomujący: 30 pytań A1–B1, wynik ustawia poziom startowy i oznacza znane pozycje jako `review` z krótkim interwałem
- [ ] Quiz na czas (limit na test lub pytanie)
- [ ] Historia podejść quizu z wykresem
- [ ] Tryb „nadrabianie" po przerwie: rozkłada nawis `due` na 7 dni zamiast wywalać 300 kart naraz (ryzyko #4)

### 5.4 Polish [~4 h]
- [ ] Lighthouse mobile: Performance ≥ 90, Accessibility ≥ 95, PWA installable
- [ ] Przegląd a11y: kontrasty, focus, `aria-live` na feedbacku odpowiedzi
- [ ] Obsługa błędów sieci w interfejsie (banner „brak połączenia", retry)
- [ ] Backup bazy: potwierdzić harmonogram na Railway + jednorazowy eksport testowy

### Definition of Done — Faza 5
- [ ] Heatmapa pokazuje pełną historię od pierwszego dnia nauki
- [ ] Import 200-wierszowego CSV → raport, zero utraconych wierszy bez wyjaśnienia
- [ ] Wyniki Lighthouse osiągnięte
- [ ] Eksport bazy odtworzony w świeżej instancji lokalnej

---

## Szacunek całości

| Faza | Zakres | Czas |
|---|---|---|
| 0 | Przygotowanie | ~2 h |
| 1 | MVP: codzienna nauka | ~2–3 tygodnie |
| 2 | Tryby ćwiczeń i quizy | ~2 tygodnie |
| 3 | Audio i offline | ~1,5 tygodnia |
| 4 | AI | ~1,5 tygodnia |
| 5 | Statystyki, import, polish | ~1 tydzień |

**Razem: ~8–9 tygodni** przy pracy wieczorami (2–3 h dziennie) w parze z Claude. Faza 1 to około połowy wysiłku pojedynczej fazy w przeliczeniu na kod, ale zawiera najwięcej decyzji projektowych — warto jej nie ścinać.

Po Fazie 1 aplikacja jest już używalna na co dzień. Kolejne fazy można wdrażać w dowolnych odstępach, ucząc się w międzyczasie z tego, co już działa.

---

## Kolejność pracy w praktyce (sugerowany pierwszy tydzień)

| Dzień | Zadania | Efekt |
|---|---|---|
| 1 | 0.1–0.4, 1.1 | Repo, konta, DNS, `/api/health` działa lokalnie |
| 2 | 1.2 | Rejestracja i logowanie działają (Swagger) |
| 3 | 1.3 + start 1.5 | Model treści, pierwsze 3 talie w seedzie |
| 4 | 1.4 (część 1) | Modele powtórek + scheduler FSRS z testami |
| 5 | 1.4 (część 2) | `/api/study/*` działa end-to-end w Swaggerze |
| 6 | 1.6 | **Backend na produkcji**, logowanie z telefonu działa |
| 7 | 1.7 | Szkielet frontu, logowanie z interfejsu |

Od drugiego tygodnia: ekran „Dziś", sesja, słownik, PWA, a w tle codziennie 1–2 nowe talie do seeda.

---

## Decyzje techniczne do potwierdzenia w trakcie

| # | Decyzja | Kiedy | Domyślnie |
|---|---|---|---|
| 1 | Konkretny głos pt-PT | Faza 0 lub 3 | `pt-PT-Neural2-A`, do odsłuchania |
| 2 | Czy quizy wpływają na harmonogram FSRS | Faza 2 | Nie (flaga `affects_schedule` zostaje w modelu) |
| 3 | Czy kierunek produkcyjny startuje po 2 czy 3 poprawnych rozpoznaniach | Faza 1, po tygodniu używania | 2 |
| 4 | Domyślna liczba nowych pozycji dziennie | Faza 1, po tygodniu | 10 pozycji (= do 20 kart) |
| 5 | Czy dodać powiadomienia push | Po Fazie 5 | Nie |

Każda z nich jest odwracalna i żadna nie blokuje startu — ustawiamy wartość domyślną i korygujemy po pierwszych tygodniach realnego używania.
