# PRD: Porto — aplikacja do nauki portugalskiego (PT-PT)

**Wersja:** 1.0
**Data:** 2026-08-11
**Status:** Draft
**Autor:** Paweł Makarewicz (+ Claude)
**Domena docelowa:** `porto.pmakarewicz.com`

---

## 1. Przegląd projektu

### 1.1 Problem / Cel

Nauka portugalskiego europejskiego (PT-PT) jest źle obsłużona przez popularne aplikacje — Duolingo, Memrise i większość gotowych kursów uczą wariantu brazylijskiego (*você*, *trem*, *café da manhã*), co przy kontakcie z Portugalią oznacza uczenie się słów i wymowy, których nikt tam nie używa. Do tego żadna z tych aplikacji nie pozwala uczyć się z **własnych** list słówek i zdań, które zbiera się w trakcie realnego kontaktu z językiem.

Drugi problem: nauka bez systemu powtórek to nauka na krótko. Słówka przerobione raz w tygodniu 1 znikają do tygodnia 4, jeśli nic ich nie przypomni w odpowiednim momencie.

### 1.2 Rozwiązanie

Porto to prywatna aplikacja webowa (PWA, mobile-first) do codziennej nauki portugalskiego europejskiego, oparta na trzech filarach:

1. **Codzienna sesja** — jeden przycisk "Ucz się", który układa dzienną porcję materiału: nowe słówka/zwroty + powtórki zaplanowane algorytmem FSRS (spaced repetition), tak aby powtarzać dokładnie wtedy, gdy słowo zaczyna się zacierać.
2. **Wiele trybów ćwiczeń** — te same słówka wracają w różnych formach: fiszki, test wyboru, wpisywanie z pamięci, uzupełnianie luk w zdaniu, dopasowywanie par, rozsypanka słów, dyktando ze słuchu. Rozpoznawanie ≠ produkcja, więc trenujemy oba kierunki (PT→PL i PL→PT).
3. **Własna treść + AI** — startowa baza ~800 słówek i zwrotów PT-PT (A1–A2) w repo, plus generowanie nowych zestawów tematycznych przez Claude API i import własnych list.

Wymowa: serwerowy TTS z głosami **pt-PT** (nie brazylijskimi), z cache'owaniem plików audio — każde słówko i każde zdanie przykładowe da się odsłuchać.

### 1.3 Użytkownicy docelowi

| Użytkownik | Kontekst użycia | Potrzeby |
|---|---|---|
| Paweł | 10–20 min dziennie, telefon, wieczorem lub w drodze | Szybkie wejście w sesję, brak tarcia, widoczny postęp i streak |
| Magda | Jw., osobne konto i osobny postęp | To samo, ale niezależna kolejka powtórek na tych samych treściach |

Aplikacja jest **prywatna** — rejestracja zamknięta kodem zaproszenia (`INVITE_CODE`). Dwa konta, wspólna biblioteka treści, oddzielny postęp każdego użytkownika.

Główne urządzenie: **telefon** (iOS/Android, przeglądarka + PWA "dodaj do ekranu głównego"). Desktop obsługiwany, ale drugorzędny.

### 1.4 Mierniki sukcesu

| Miernik | Cel |
|---|---|
| Regularność | ≥ 5 sesji w tygodniu przez pierwsze 8 tygodni (streak) |
| Czas wejścia w naukę | Od otwarcia aplikacji do pierwszego pytania < 3 sekundy |
| Retencja materiału | > 85% poprawnych odpowiedzi na kartach w stanie *Review* (cel FSRS: `desired_retention = 0.9`) |
| Objętość | 1000+ pozycji "opanowanych" (stability > 30 dni) po 6 miesiącach |
| Koszt utrzymania | < 15 USD/mies. łącznie (Railway + TTS + Claude API) |
| Techniczne | Sesja działa bez zacięć przy słabym LTE — kolejne pytanie i audio prefetchowane z wyprzedzeniem |

---

## 2. Stack technologiczny

| Warstwa | Technologia | Uzasadnienie |
|---|---|---|
| Backend | FastAPI (Python 3.11+) | Znany stack, automatyczna dokumentacja OpenAPI, Pydantic v2 waliduje wejście bez pisania walidacji ręcznie |
| ORM / migracje | SQLAlchemy 2.0 + Alembic | Model danych będzie rósł (nowe tryby ćwiczeń = nowe kolumny), migracje muszą być wersjonowane od pierwszego dnia |
| Spaced repetition | `fsrs` (py-fsrs) | Gotowa, utrzymywana implementacja FSRS — nie piszemy własnego SM-2. Sterowanie jednym parametrem: `desired_retention` |
| Baza danych | PostgreSQL 15+ | Relacyjny model (użytkownik × pozycja × stan powtórki), JSONB na elastyczne pola (odmiana, tagi), pełnotekstowe wyszukiwanie słownika |
| Frontend | React 18 + Vite + TypeScript | Standardowy stack, szybki HMR, TS łapie literówki w typach zadań (7 trybów ćwiczeń = 7 kształtów danych) |
| Styling | Tailwind CSS | Mobile-first z definicji, brak osobnych plików CSS do utrzymania |
| Stan / dane | TanStack Query + Zustand | Query obsługuje cache i retry zapytań, Zustand trzyma stan bieżącej sesji nauki (lekki, bez boilerplate'u Reduxa) |
| Offline / PWA | `vite-plugin-pwa` + IndexedDB (Dexie) | Sesja pobrana na start działa w metrze bez zasięgu; odpowiedzi trafiają do kolejki i synchronizują się po powrocie sieci |
| Wykresy | Recharts | Heatmapa aktywności i prognoza powtórek — prosty, deklaratywny API |
| Hosting backend | Railway | Postgres + aplikacja w jednym miejscu, deploy z gita, tanio przy tej skali |
| Hosting frontend | Cloudflare Pages | Darmowy, globalny CDN, deploy z gita, własna domena `porto.pmakarewicz.com` |
| Pliki audio | Cloudflare R2 | Zero opłat za egress (audio to najczęściej pobierany zasób), API zgodne z S3 (`boto3`) |
| Auth | JWT (access 15 min + refresh 30 dni) | Dwa konta, rejestracja na kod zaproszenia. Refresh token w httpOnly cookie, access w pamięci |
| AI | Claude API — `claude-sonnet-5` | Generowanie zestawów tematycznych, zdań przykładowych, wyjaśnień błędów i oceny tłumaczeń |
| TTS | Google Cloud Text-to-Speech (głosy `pt-PT-*`) | Jawna kontrola wariantu europejskiego (ElevenLabs nie daje gwarancji PT-PT vs PT-BR), sterowanie tempem mowy, tanio przy cache'owaniu |

### 2.1 Zewnętrzne API i integracje

| API | Cel | Plan cenowy | Uwagi |
|---|---|---|---|
| Google Cloud Text-to-Speech | Synteza wymowy słówek i zdań (głosy pt-PT, Neural2/WaveNet) | Miesięczny darmowy limit znaków + niski koszt powyżej — **zweryfikować aktualny cennik przed Fazą 3** | Każdy plik generowany **raz** i cache'owany w R2 — realne zużycie to jednorazowa synteza całej bazy (~50k znaków) plus przyrosty |
| Anthropic Claude API | Generowanie zestawów słówek, zdań przykładowych, wyjaśnień błędów, ocena tłumaczeń | Pay-as-you-go | Twardy limit miesięczny w kodzie (`AI_MONTHLY_BUDGET_USD`), logowanie każdego wywołania z liczbą tokenów |
| Cloudflare R2 | Przechowywanie audio | Darmowy tier na start, brak opłat za egress | Publiczny bucket read-only pod własną subdomeną |

**Świadomie odrzucone:**
- ElevenLabs — lepsza jakość głosu, ale słaba kontrola wariantu językowego i wyższy koszt przy tej objętości.
- Web Speech API (TTS w przeglądarce) — darmowe, ale głos zależy od urządzenia; na Androidzie często brak głosu pt-PT (podstawia pt-BR), czyli dokładnie ten problem, który rozwiązujemy. **Zostaje jako fallback**, gdy plik audio nie jest jeszcze zsyntetyzowany.
- Gotowe API słownikowe (Wiktionary, Linguee) — jakość i licencjonowanie nieprzewidywalne; hybryda "seed w repo + AI + własne dodawanie" daje pełną kontrolę.

---

## 3. Architektura systemu

### 3.1 Diagram wysokopoziomowy

```
                        ┌──────────────────────────┐
                        │  PWA: React + Vite       │
                        │  porto.pmakarewicz.com   │
                        │  (Cloudflare Pages)      │
                        │  ├─ IndexedDB: kolejka   │
                        │  └─ Service Worker       │
                        └───────────┬──────────────┘
                                    │ HTTPS / JWT
                                    ▼
                        ┌──────────────────────────┐
                        │  API: FastAPI            │
                        │  api-porto.…com (Railway)│
                        │  ├─ Auth (JWT)           │
                        │  ├─ Scheduler (FSRS)     │
                        │  ├─ Task builder (7 mod.)│
                        │  ├─ Grader (fuzzy match) │
                        │  ├─ TTS service          │
                        │  └─ AI service           │
                        └─┬──────────┬───────────┬─┘
                          │          │           │
                ┌─────────▼──┐  ┌────▼──────┐  ┌─▼──────────────┐
                │ PostgreSQL │  │ Cloudflare│  │ Google TTS     │
                │ (Railway)  │  │ R2 (audio)│  │ Anthropic API  │
                └────────────┘  └───────────┘  └────────────────┘
```

### 3.2 Przepływ danych — główny use case ("codzienna sesja")

1. Użytkownik otwiera PWA. Frontend woła `GET /api/study/queue/summary` → `{ due: 34, new_available: 20, goal: 25, done_today: 0, streak: 12 }`.
2. Naciska **"Ucz się"** → `POST /api/study/sessions` z parametrami z ustawień (limit nowych, talie, dozwolone tryby).
3. Backend:
   - pobiera karty `due <= now()` dla użytkownika (posortowane wg `due`), przycina do `review_limit`,
   - dobiera do `new_per_day` pozycji bez stanu (`user_item_state` nie istnieje) z wybranych talii,
   - miesza kolejkę (nowe wplecione co kilka powtórek, nie hurtem na początku),
   - dla każdej pozycji **wybiera tryb ćwiczenia** zależnie od stanu karty (patrz 6.3) i buduje gotowy payload zadania — w tym dystraktory do testu wyboru i URL-e audio,
   - zwraca całą sesję (do 120 zadań) jednym responsem.
4. Frontend zapisuje sesję w IndexedDB, prefetchuje pliki audio dla pierwszych 10 zadań i renderuje pierwsze pytanie. **Od tego momentu sesja działa offline.**
5. Na każdą odpowiedź frontend: ocenia lokalnie tam, gdzie może (wybór/dopasowanie), pokazuje feedback natychmiast i wrzuca zdarzenie do kolejki `answers` w IndexedDB.
6. Kolejka jest wysyłana partiami: `POST /api/study/sessions/{id}/answers` (batch). Backend mapuje wynik na ocenę FSRS (`Again`/`Hard`/`Good`/`Easy`), przelicza `stability`, `difficulty`, `due`, zapisuje `user_item_state` i wiersz w `reviews`.
7. `POST /api/study/sessions/{id}/finish` → podsumowanie: liczba kart, % poprawnych, czas, nowy streak, lista błędów z linkiem "powtórz teraz".
8. Nocny job (Railway cron) aktualizuje `daily_stats`, wykrywa "leeches" (karty z `lapses >= 6`) i prefetchuje audio dla pozycji, które staną się `due` w ciągu 24h.

### 3.3 Przepływ danych — generowanie zestawu przez AI

1. `POST /api/ai/generate-set` → `{ topic: "W restauracji", level: "A2", count: 20, type: "phrase" }`.
2. Backend woła Claude API z promptem wymuszającym **PT-PT** (jawne instrukcje: *tu/você* po portugalsku europejsku, słownictwo portugalskie nie brazylijskie, zapis bez brazylijskich uproszczeń) i strukturą JSON.
3. Wynik trafia do `ai_generation_jobs` ze statusem `pending_review` — **nic nie wchodzi do bazy automatycznie**.
4. Użytkownik widzi listę propozycji, może edytować tłumaczenie, odrzucić pojedyncze pozycje, po czym `POST /api/ai/generate-set/{job_id}/approve` tworzy `items` + nową talię i kolejkuje syntezę audio.

Powód rozdzielenia: model potrafi wtrącić brazylijskie słownictwo albo pomylić rodzajnik. Bramka akceptacji kosztuje 30 sekund i chroni bazę przed śmieciami, których potem nie da się odróżnić od zweryfikowanych treści.

---

## 4. Model danych (schemat bazy)

### Tabela: `users`
| Kolumna | Typ | Wymagane | Opis |
|---|---|---|---|
| id | UUID PK | ✓ | Klucz główny |
| email | TEXT UNIQUE | ✓ | Login |
| password_hash | TEXT | ✓ | Argon2id |
| display_name | TEXT | ✓ | Nazwa wyświetlana |
| timezone | TEXT | ✓ | Domyślnie `Europe/Warsaw` — wyznacza granicę "dnia" dla streaka |
| created_at | TIMESTAMPTZ | ✓ | |
| last_login_at | TIMESTAMPTZ | | |

### Tabela: `user_settings`
| Kolumna | Typ | Wymagane | Opis |
|---|---|---|---|
| user_id | UUID PK FK→users | ✓ | 1:1 z użytkownikiem |
| daily_goal | INT | ✓ | Liczba kart dziennie zaliczająca streak (domyślnie 25) |
| new_per_day | INT | ✓ | Limit nowych pozycji dziennie (domyślnie 10) |
| review_limit | INT | ✓ | Maks. powtórek w sesji (domyślnie 100) |
| desired_retention | NUMERIC(3,2) | ✓ | Parametr FSRS, domyślnie 0.90 |
| enabled_modes | JSONB | ✓ | Lista aktywnych trybów, np. `["flashcard","mcq_pt_pl","typing","cloze"]` |
| tts_voice | TEXT | ✓ | Np. `pt-PT-Neural2-A` |
| tts_speed | NUMERIC(3,2) | ✓ | 0.75–1.25, domyślnie 1.00 |
| autoplay_audio | BOOLEAN | ✓ | Auto-odtwarzanie przy pokazaniu odpowiedzi |
| accent_strict | BOOLEAN | ✓ | Czy brak akcentu (`avo` zamiast `avó`) liczy się jako błąd (domyślnie `false` — zalicza jako "prawie") |

### Tabela: `items` — jednostka nauki (słówko / zwrot / zdanie)
| Kolumna | Typ | Wymagane | Opis |
|---|---|---|---|
| id | UUID PK | ✓ | |
| type | TEXT ENUM | ✓ | `word` \| `phrase` \| `sentence` |
| pt | TEXT | ✓ | Forma portugalska (hasło słownikowe) |
| pl | TEXT | ✓ | Tłumaczenie polskie (główne) |
| pl_alt | TEXT[] | | Akceptowane warianty tłumaczenia przy wpisywaniu |
| pt_alt | TEXT[] | | Akceptowane warianty formy portugalskiej |
| variant | TEXT ENUM | ✓ | `pt-PT` (domyślnie) \| `pt-BR` \| `both` — na wypadek późniejszego rozszerzenia |
| part_of_speech | TEXT | | `noun`, `verb`, `adj`, `adv`, `prep`, `expr`… — używane do doboru dystraktorów |
| gender | TEXT | | `m` \| `f` \| `mf` — dla rzeczowników |
| article | TEXT | | `o` / `a` / `os` / `as` — pokazywane przy rzeczowniku |
| plural | TEXT | | Forma mnoga, jeśli nieregularna |
| ipa | TEXT | | Transkrypcja fonetyczna (opcjonalna) |
| cefr_level | TEXT | ✓ | `A1`…`C1` |
| notes | TEXT | | Uwagi: fałszywy przyjaciel, różnica PT-PT vs PT-BR, rejestr |
| extra | JSONB | | Odmiana czasownika, kolokacje — pole na przyszłość bez migracji |
| source | TEXT ENUM | ✓ | `seed` \| `ai` \| `user` \| `import` |
| verified | BOOLEAN | ✓ | `true` dla seed i zaakceptowanych ręcznie; `false` dla świeżych z AI |
| created_by | UUID FK→users | | NULL dla seed |
| created_at | TIMESTAMPTZ | ✓ | |

Indeksy: `GIN` na `to_tsvector(pt || ' ' || pl)` (wyszukiwarka słownika), `(cefr_level, part_of_speech)` (dobór dystraktorów), `UNIQUE (pt, pl)` (ochrona przed duplikatami przy imporcie).

### Tabela: `examples` — zdania przykładowe
| Kolumna | Typ | Wymagane | Opis |
|---|---|---|---|
| id | UUID PK | ✓ | |
| item_id | UUID FK→items | ✓ | ON DELETE CASCADE |
| pt | TEXT | ✓ | Zdanie po portugalsku |
| pl | TEXT | ✓ | Tłumaczenie |
| cloze_start | INT | | Pozycja znakowa początku luki (do trybu `cloze`) |
| cloze_end | INT | | Pozycja końca luki |
| source | TEXT ENUM | ✓ | `seed` \| `ai` \| `user` |
| created_at | TIMESTAMPTZ | ✓ | |

### Tabela: `decks` — talie / zestawy tematyczne
| Kolumna | Typ | Wymagane | Opis |
|---|---|---|---|
| id | UUID PK | ✓ | |
| name | TEXT | ✓ | Np. „W restauracji", „Czasowniki nieregularne" |
| description | TEXT | | |
| cefr_level | TEXT | | Poziom dominujący |
| icon | TEXT | | Emoji / nazwa ikony |
| is_shared | BOOLEAN | ✓ | `true` = widoczna dla obu kont (wszystkie talie seed) |
| owner_id | UUID FK→users | | NULL dla talii współdzielonych |
| position | INT | ✓ | Kolejność wyświetlania |
| created_at | TIMESTAMPTZ | ✓ | |

### Tabela: `deck_items` — powiązanie M:N
| Kolumna | Typ | Wymagane | Opis |
|---|---|---|---|
| deck_id | UUID FK→decks | ✓ | PK złożony |
| item_id | UUID FK→items | ✓ | PK złożony |
| position | INT | ✓ | Kolejność wprowadzania nowych pozycji |

### Tabela: `user_item_state` — stan powtórki (rdzeń FSRS)
| Kolumna | Typ | Wymagane | Opis |
|---|---|---|---|
| user_id | UUID FK→users | ✓ | PK złożony |
| item_id | UUID FK→items | ✓ | PK złożony |
| direction | TEXT ENUM | ✓ | `recognition` (PT→PL) \| `production` (PL→PT) — **osobne karty, osobny harmonogram** |
| state | TEXT ENUM | ✓ | `new` \| `learning` \| `review` \| `relearning` |
| stability | NUMERIC | ✓ | Parametr FSRS |
| difficulty | NUMERIC | ✓ | Parametr FSRS |
| due | TIMESTAMPTZ | ✓ | Termin następnej powtórki — indeks `(user_id, due)` |
| last_review_at | TIMESTAMPTZ | | |
| reps | INT | ✓ | Liczba powtórek |
| lapses | INT | ✓ | Liczba zapomnień — `>= 6` oznacza kartę-leecha |
| step | INT | | Krok w fazie learning |
| suspended | BOOLEAN | ✓ | Karta wyłączona z kolejki (ręcznie lub jako leech) |

Rozdzielenie na `recognition` i `production` jest celowe: rozpoznanie *obrigado → dziękuję* przychodzi dużo wcześniej niż wyprodukowanie *dziękuję → obrigado*. Wspólny harmonogram dla obu kierunków oznaczałby albo przepytywanie za łatwe, albo za trudne.

### Tabela: `reviews` — log każdej odpowiedzi
| Kolumna | Typ | Wymagane | Opis |
|---|---|---|---|
| id | BIGSERIAL PK | ✓ | |
| user_id | UUID FK→users | ✓ | |
| item_id | UUID FK→items | ✓ | |
| direction | TEXT | ✓ | Jw. |
| session_id | UUID FK→study_sessions | | NULL dla odpowiedzi w quizie |
| mode | TEXT ENUM | ✓ | Tryb ćwiczenia użyty w tym pytaniu |
| rating | SMALLINT | ✓ | 1=Again, 2=Hard, 3=Good, 4=Easy |
| is_correct | BOOLEAN | ✓ | |
| user_answer | TEXT | | Co wpisał/wybrał użytkownik (do analizy błędów) |
| elapsed_ms | INT | ✓ | Czas odpowiedzi |
| stability_after | NUMERIC | | Stan po przeliczeniu — pozwala odtworzyć historię FSRS |
| reviewed_at | TIMESTAMPTZ | ✓ | Indeks `(user_id, reviewed_at)` |

Log jest niemodyfikowalny (append-only). Dzięki niemu można w przyszłości przeliczyć cały harmonogram od nowa po zmianie parametrów FSRS lub po optymalizacji na własnych danych.

### Tabela: `study_sessions`
| Kolumna | Typ | Wymagane | Opis |
|---|---|---|---|
| id | UUID PK | ✓ | |
| user_id | UUID FK→users | ✓ | |
| started_at | TIMESTAMPTZ | ✓ | |
| finished_at | TIMESTAMPTZ | | NULL = sesja przerwana |
| planned_count | INT | ✓ | Ile zadań zaplanowano |
| completed_count | INT | ✓ | Ile faktycznie zrobiono |
| correct_count | INT | ✓ | |
| deck_ids | JSONB | | Filtr talii użyty przy tworzeniu |
| payload | JSONB | ✓ | Wygenerowana lista zadań (pozwala wznowić przerwaną sesję) |

### Tabela: `quizzes` / `quiz_attempts` / `quiz_answers`

`quizzes` — konfiguracja testu (nazwa, filtr: talia/poziom/tag, liczba pytań, tryby, limit czasu, czy losować przy każdym podejściu).

| Kolumna | Typ | Wymagane | Opis |
|---|---|---|---|
| id | UUID PK | ✓ | |
| name | TEXT | ✓ | |
| config | JSONB | ✓ | `{deck_ids, cefr_level, count, modes, time_limit_s, shuffle}` |
| owner_id | UUID FK→users | ✓ | |
| created_at | TIMESTAMPTZ | ✓ | |

`quiz_attempts` — pojedyncze podejście.

| Kolumna | Typ | Wymagane | Opis |
|---|---|---|---|
| id | UUID PK | ✓ | |
| quiz_id | UUID FK→quizzes | ✓ | |
| user_id | UUID FK→users | ✓ | |
| started_at / finished_at | TIMESTAMPTZ | ✓ / | |
| score | NUMERIC(5,2) | | Wynik procentowy |
| questions | JSONB | ✓ | Zamrożony zestaw pytań tego podejścia |

`quiz_answers` — odpowiedź na pytanie (item_id, mode, user_answer, is_correct, elapsed_ms).

Quiz **nie modyfikuje** harmonogramu FSRS domyślnie — to test wiedzy, nie nauka. Przełącznik `config.affects_schedule` pozwala to zmienić.

### Tabela: `audio_assets` — cache TTS
| Kolumna | Typ | Wymagane | Opis |
|---|---|---|---|
| id | UUID PK | ✓ | |
| text_hash | TEXT UNIQUE | ✓ | `sha256(text + voice + speed)` — klucz cache |
| text | TEXT | ✓ | Zsyntetyzowany tekst |
| voice | TEXT | ✓ | Np. `pt-PT-Neural2-A` |
| speed | NUMERIC(3,2) | ✓ | |
| url | TEXT | ✓ | Publiczny URL w R2 |
| duration_ms | INT | | |
| provider | TEXT | ✓ | `google` |
| char_count | INT | ✓ | Do rozliczania kosztów |
| created_at | TIMESTAMPTZ | ✓ | |

Cache jest kluczowany po treści, nie po `item_id` — to samo zdanie w dwóch pozycjach syntetyzujemy raz.

### Tabela: `daily_stats` — agregat dzienny
| Kolumna | Typ | Wymagane | Opis |
|---|---|---|---|
| user_id | UUID FK→users | ✓ | PK złożony |
| date | DATE | ✓ | PK złożony (w strefie użytkownika) |
| reviews_count | INT | ✓ | |
| new_count | INT | ✓ | |
| correct_count | INT | ✓ | |
| time_spent_s | INT | ✓ | |
| goal_met | BOOLEAN | ✓ | Podstawa liczenia streaka i heatmapy |

### Tabela: `ai_generation_jobs`
| Kolumna | Typ | Wymagane | Opis |
|---|---|---|---|
| id | UUID PK | ✓ | |
| user_id | UUID FK→users | ✓ | |
| kind | TEXT ENUM | ✓ | `generate_set` \| `examples` \| `explain` \| `grade_translation` |
| request | JSONB | ✓ | Parametry wywołania |
| response | JSONB | | Surowa odpowiedź modelu |
| status | TEXT ENUM | ✓ | `pending` \| `pending_review` \| `approved` \| `rejected` \| `failed` |
| input_tokens / output_tokens | INT | | Do rozliczenia kosztów |
| cost_usd | NUMERIC(8,4) | | |
| error | TEXT | | |
| created_at | TIMESTAMPTZ | ✓ | |

### Relacje — podsumowanie

```
users 1─1 user_settings
users 1─N user_item_state N─1 items
users 1─N reviews N─1 items
users 1─N study_sessions 1─N reviews
users 1─N daily_stats
users 1─N quizzes 1─N quiz_attempts 1─N quiz_answers
items 1─N examples
items N─M decks  (przez deck_items)
items ─(po treści)─ audio_assets   # bez FK, wiązanie po hashu tekstu
```

---

## 5. API Endpoints

Wszystkie odpowiedzi błędów w jednym kształcie: `{ "error": { "code": "ITEM_NOT_FOUND", "message": "...", "details": {...} } }`.
Kody: `400` błędne żądanie, `401` brak/wygasły token, `403` cudzy zasób, `404` nie istnieje, `409` konflikt (duplikat pozycji), `422` walidacja Pydantic, `429` limit (AI/TTS), `500` błąd serwera.

### Autentykacja
| Method | Endpoint | Opis | Auth |
|---|---|---|---|
| POST | `/api/auth/register` | Body: `{email, password, display_name, invite_code}`. `403` gdy kod zaproszenia nieprawidłowy, `409` gdy email zajęty | ✗ |
| POST | `/api/auth/login` | Zwraca `{access_token, user}` + refresh token w httpOnly cookie | ✗ |
| POST | `/api/auth/refresh` | Nowy access token na podstawie cookie | ✗ |
| POST | `/api/auth/logout` | Unieważnia refresh token | ✓ |
| GET | `/api/auth/me` | Profil + ustawienia | ✓ |

### Ustawienia
| Method | Endpoint | Opis | Auth |
|---|---|---|---|
| GET | `/api/settings` | Pełne `user_settings` | ✓ |
| PATCH | `/api/settings` | Częściowa aktualizacja; `422` gdy `new_per_day > 100` lub `desired_retention` poza `0.7–0.97` | ✓ |

### Treść: pozycje i talie
| Method | Endpoint | Opis | Auth |
|---|---|---|---|
| GET | `/api/items` | Query: `search`, `level`, `type`, `pos`, `deck_id`, `verified`, `page`, `per_page` (maks. 100). Wyszukiwanie pełnotekstowe po `pt` i `pl` | ✓ |
| POST | `/api/items` | Tworzy pozycję (`source=user`, `verified=true`). `409` przy duplikacie pary `(pt, pl)` | ✓ |
| GET | `/api/items/{id}` | Szczegóły + przykłady + stan powtórki bieżącego użytkownika | ✓ |
| PATCH | `/api/items/{id}` | Edycja | ✓ |
| DELETE | `/api/items/{id}` | Usuwa pozycję i kaskadowo przykłady oraz stany powtórek | ✓ |
| POST | `/api/items/{id}/examples` | Dodaje zdanie przykładowe | ✓ |
| POST | `/api/items/import` | Multipart CSV: `pt,pl,type,level,pos,notes`. Zwraca `{created, skipped_duplicates, errors[]}`. Maks. 2000 wierszy | ✓ |
| GET | `/api/decks` | Talie współdzielone + własne, z licznikami `total / learned / due` | ✓ |
| POST | `/api/decks` | | ✓ |
| GET | `/api/decks/{id}` | Talia + paginowana lista pozycji | ✓ |
| PATCH | `/api/decks/{id}` | | ✓ |
| DELETE | `/api/decks/{id}` | Usuwa talię, **nie** usuwa pozycji | ✓ |
| POST | `/api/decks/{id}/items` | Body: `{item_ids: []}` — dopina istniejące pozycje | ✓ |
| DELETE | `/api/decks/{id}/items/{item_id}` | Odpina pozycję | ✓ |

### Nauka (sesja dzienna)
| Method | Endpoint | Opis | Auth |
|---|---|---|---|
| GET | `/api/study/queue/summary` | `{due, new_available, done_today, goal, streak, next_due_at}` — zasila ekran „Dziś" | ✓ |
| POST | `/api/study/sessions` | Body: `{deck_ids?, new_limit?, review_limit?, modes?}`. Zwraca sesję z pełną listą zadań (gotowe payloady, dystraktory, URL-e audio). `409` gdy istnieje nieukończona sesja | ✓ |
| GET | `/api/study/sessions/active` | Zwraca nieukończoną sesję (wznowienie po zamknięciu apki) | ✓ |
| POST | `/api/study/sessions/{id}/answers` | **Batch**: `[{item_id, direction, mode, rating?, user_answer?, is_correct?, elapsed_ms}]`. Serwer weryfikuje poprawność dla trybów tekstowych i zwraca dla każdej pozycji `{is_correct, correct_answer, next_due, match: exact|accent|typo|wrong}` | ✓ |
| POST | `/api/study/sessions/{id}/finish` | Zamyka sesję, aktualizuje `daily_stats` i streak, zwraca podsumowanie z listą błędów | ✓ |
| POST | `/api/study/items/{id}/suspend` | Wyłącza pozycję z kolejki (obie karty) | ✓ |
| POST | `/api/study/items/{id}/reset` | Kasuje stan powtórki — nauka od zera | ✓ |

### Quizy i testy
| Method | Endpoint | Opis | Auth |
|---|---|---|---|
| GET | `/api/quizzes` | Lista zapisanych konfiguracji quizów | ✓ |
| POST | `/api/quizzes` | Tworzy konfigurację. `422` gdy filtr daje mniej pozycji niż `count` | ✓ |
| POST | `/api/quizzes/{id}/attempts` | Startuje podejście — generuje i zamraża pytania, zwraca je bez odpowiedzi | ✓ |
| POST | `/api/quizzes/attempts/{id}/answers` | Batch odpowiedzi (bez ujawniania poprawnych do czasu submit) | ✓ |
| POST | `/api/quizzes/attempts/{id}/submit` | Kończy podejście: wynik %, czas, lista błędów, przycisk „dodaj błędy do powtórek" | ✓ |
| GET | `/api/quizzes/attempts` | Historia podejść z wynikami (do wykresu postępu) | ✓ |
| POST | `/api/quizzes/quick` | Quiz „na już" bez zapisywania konfiguracji: `{count, level?, deck_id?, modes?}` | ✓ |

### Statystyki
| Method | Endpoint | Opis | Auth |
|---|---|---|---|
| GET | `/api/stats/overview` | Streak, dziś/7/30 dni, łączna liczba pozycji wg stanu, średnia retencja, czas nauki | ✓ |
| GET | `/api/stats/heatmap` | Query `from`, `to` → aktywność dzienna (kalendarz w stylu GitHuba) | ✓ |
| GET | `/api/stats/forecast` | Prognoza liczby powtórek na najbliższe 30 dni — ostrzega przed nawisem po urlopie | ✓ |
| GET | `/api/stats/leeches` | Pozycje z `lapses >= 6` — kandydaci do przeformułowania lub zawieszenia | ✓ |
| GET | `/api/stats/weakest` | Najniższa skuteczność ostatnich 30 dni (min. 5 powtórek) | ✓ |

### Audio (TTS)
| Method | Endpoint | Opis | Auth |
|---|---|---|---|
| GET | `/api/audio` | Query `text` lub `item_id`, `voice?`, `speed?`. Zwraca `{url, cached}`; przy braku w cache syntetyzuje synchronicznie (limit: 2000 znaków). `429` po przekroczeniu miesięcznego budżetu znaków | ✓ |
| POST | `/api/audio/prefetch` | Batch: `{item_ids: []}` — synteza w tle dla nadchodzącej sesji | ✓ |
| GET | `/api/audio/usage` | Zużycie znaków w bieżącym miesiącu vs limit | ✓ |

### AI
| Method | Endpoint | Opis | Auth |
|---|---|---|---|
| POST | `/api/ai/generate-set` | `{topic, level, count (≤30), type}` → job `pending_review` z propozycjami. `429` po przekroczeniu budżetu | ✓ |
| GET | `/api/ai/jobs/{id}` | Status i propozycje do przeglądu | ✓ |
| POST | `/api/ai/jobs/{id}/approve` | `{accepted_items: [...], deck_name?}` → tworzy pozycje i talię, kolejkuje audio | ✓ |
| POST | `/api/ai/jobs/{id}/reject` | Odrzuca job | ✓ |
| POST | `/api/ai/examples` | `{item_id, count}` → zdania przykładowe PT-PT dla istniejącej pozycji | ✓ |
| POST | `/api/ai/explain` | `{item_id, user_answer}` → krótkie wyjaśnienie po polsku, dlaczego odpowiedź jest błędna | ✓ |
| POST | `/api/ai/grade-translation` | `{example_id, user_answer}` → `{score 0-100, feedback, corrected}` dla tłumaczenia zdania PL→PT | ✓ |
| GET | `/api/ai/usage` | Koszty i liczba wywołań w bieżącym miesiącu | ✓ |

### Systemowe
| Method | Endpoint | Opis | Auth |
|---|---|---|---|
| GET | `/api/health` | `{status, db, version}` — monitoring Railway | ✗ |

---

## 6. Funkcjonalności aplikacji

### 6.1 Pełna lista funkcjonalności

#### Moduł 1: Konto i ustawienia
- [ ] **F01 — Rejestracja na kod zaproszenia**: zakładanie konta wymaga `INVITE_CODE`; aplikacja pozostaje prywatna bez budowania panelu administracyjnego.
- [ ] **F02 — Logowanie JWT**: access token 15 min w pamięci + refresh 30 dni w httpOnly cookie; sesja przeżywa zamknięcie przeglądarki na telefonie.
- [ ] **F03 — Ustawienia nauki**: cel dzienny, limit nowych pozycji, limit powtórek, docelowa retencja FSRS, wybór aktywnych trybów ćwiczeń.
- [ ] **F04 — Ustawienia audio**: wybór głosu pt-PT, tempo mowy (0,75–1,25×), auto-odtwarzanie.
- [ ] **F05 — Tolerancja akcentów**: przełącznik decydujący, czy `avo` zamiast `avó` to błąd, czy odpowiedź „prawie dobra".
- [ ] **F06 — Osobny postęp per konto**: wspólna biblioteka treści, niezależne harmonogramy powtórek i statystyki.

#### Moduł 2: Treść (słownik)
- [ ] **F07 — Baza startowa PT-PT**: ~800 zweryfikowanych pozycji A1–A2 w seedzie (słówka, zwroty, zdania), pogrupowanych w ~20 talii tematycznych.
- [ ] **F08 — Przeglądarka słownika**: lista z wyszukiwaniem pełnotekstowym (PL i PT), filtrami po poziomie, typie, części mowy i talii.
- [ ] **F09 — Szczegóły pozycji**: rodzajnik, rodzaj, liczba mnoga, IPA, notatka (fałszywy przyjaciel / różnica PT-PT vs PT-BR), przykłady, audio, historia własnych powtórek.
- [ ] **F10 — Ręczne dodawanie pozycji**: formularz „usłyszałem nowe słowo" — minimum to `pt` + `pl`, reszta opcjonalna.
- [ ] **F11 — Import CSV**: wklejenie lub wgranie listy; raport `utworzone / pominięte duplikaty / błędy`.
- [ ] **F12 — Talie tematyczne**: tworzenie własnych talii, dopinanie i odpinanie pozycji, nauka z wybranych talii.
- [ ] **F13 — Zdania przykładowe**: każda pozycja może mieć wiele przykładów z tłumaczeniem i zaznaczoną luką dla trybu cloze.

#### Moduł 3: Codzienna nauka
- [ ] **F14 — Ekran „Dziś"**: liczba powtórek na dziś, postęp do celu, streak, jeden duży przycisk „Ucz się".
- [ ] **F15 — Harmonogram FSRS**: karty planowane algorytmem FSRS, osobno dla rozpoznawania (PT→PL) i produkcji (PL→PT).
- [ ] **F16 — Mieszana sesja**: nowe pozycje wplecione między powtórki, nie wrzucone hurtem na początek.
- [ ] **F17 — Automatyczny dobór trybu**: nowa karta → fiszka, potem test wyboru, potem wpisywanie — trudność rośnie wraz z opanowaniem (patrz 6.3).
- [ ] **F18 — Wznawianie sesji**: zamknięcie aplikacji w połowie sesji nie kasuje postępu.
- [ ] **F19 — Tryb offline**: pobrana sesja działa bez sieci, odpowiedzi czekają w IndexedDB i synchronizują się automatycznie.
- [ ] **F20 — Podsumowanie sesji**: wynik, czas, nowy streak, lista błędów z opcją natychmiastowej powtórki.
- [ ] **F21 — Streak i cel dzienny**: dzień zaliczony po wykonaniu `daily_goal` kart; granica dnia w strefie użytkownika.
- [ ] **F22 — Zawieszanie i reset pozycji**: karta-leech do zawieszenia jednym kliknięciem; reset uczy od zera.

#### Moduł 4: Tryby ćwiczeń
- [ ] **F23 — Fiszka (`flashcard`)**: pokaż stronę → odsłoń tłumaczenie → samoocena Again / Hard / Good / Easy.
- [ ] **F24 — Test wyboru PT→PL (`mcq_pt_pl`)**: 4 warianty, dystraktory z tej samej talii i części mowy.
- [ ] **F25 — Test wyboru PL→PT (`mcq_pl_pt`)**: kierunek produkcyjny, dystraktory dobrane tak, by były podobne graficznie (np. *cadeira* / *carteira* / *caneta*).
- [ ] **F26 — Wpisywanie z pamięci (`typing`)**: PL→PT z klawiaturą; pasek z portugalskimi znakami diakrytycznymi (ã á à â ç é ê í ó ô õ ú) nad polem, bo mobilna klawiatura ich nie ma pod ręką.
- [ ] **F27 — Ocena tolerancyjna**: normalizacja wielkości liter, interpunkcji i spacji; odległość Levenshteina ≤ 1 → „prawie dobrze" (liczy się jako `Hard`, nie jako błąd); brak akcentu traktowany zgodnie z F05.
- [ ] **F28 — Uzupełnij lukę (`cloze`)**: zdanie przykładowe z wyciętym słowem, wpisywanie lub wybór z 4 opcji.
- [ ] **F29 — Dopasowywanie par (`matching`)**: siatka 5×2, łączenie PT z PL na czas — szybka rozgrzewka na początku sesji.
- [ ] **F30 — Rozsypanka słów (`word_bank`)**: budowanie zdania z klocków; trenuje szyk zdania portugalskiego (pozycja zaimków, przeczenie).
- [ ] **F31 — Dyktando ze słuchu (`listening`)**: odtworzenie audio bez tekstu → wpisz, co słyszysz lub wybierz z 4 opcji.
- [ ] **F32 — Tłumaczenie zdania z oceną AI (`translate_ai`)**: PL→PT dowolnym sformułowaniem, Claude ocenia poprawność i wskazuje różnicę wobec wersji wzorcowej.

#### Moduł 5: Quizy i testy
- [ ] **F33 — Szybki quiz**: „10 pytań z talii X" bez konfiguracji, dwa kliknięcia od ekranu głównego.
- [ ] **F34 — Zapisywane konfiguracje quizów**: własne testy (filtr, liczba pytań, tryby, limit czasu) do wielokrotnego powtarzania.
- [ ] **F35 — Quiz na czas**: opcjonalny limit czasowy na cały test lub pojedyncze pytanie.
- [ ] **F36 — Wynik i analiza błędów**: procent, czas, lista błędnych odpowiedzi z poprawnymi wersjami.
- [ ] **F37 — „Dodaj błędy do powtórek"**: pozycje pomylone w quizie trafiają do kolejki nauki na jutro.
- [ ] **F38 — Historia podejść**: wykres wyników w czasie dla tej samej konfiguracji quizu.
- [ ] **F39 — Test poziomujący**: 30 pytań przekrojowych A1–B1 przy pierwszym uruchomieniu; wynik ustawia startowy poziom i wstępnie oznacza znane słowa.

#### Moduł 6: Audio i wymowa
- [ ] **F40 — Wymowa pozycji**: przycisk odtwarzania przy każdym słówku i zdaniu, głos pt-PT.
- [ ] **F41 — Cache audio w R2**: każdy tekst syntetyzowany raz, potem serwowany z CDN.
- [ ] **F42 — Prefetch audio sesji**: pliki dla nadchodzącej sesji pobierane z wyprzedzeniem — brak przerwy na ładowanie w trakcie nauki.
- [ ] **F43 — Wolne odtwarzanie**: drugie kliknięcie odtwarza z prędkością 0,75× (PT-PT redukuje samogłoski, wolna wersja realnie pomaga).
- [ ] **F44 — Fallback Web Speech API**: gdy pliku nie ma w cache i synteza się nie powiedzie, odtwarzamy głosem przeglądarki.

#### Moduł 7: AI
- [ ] **F45 — Generowanie zestawu tematycznego**: „daj mi 20 zwrotów A2 na temat wizyty u lekarza" → propozycje z tłumaczeniami i przykładami.
- [ ] **F46 — Bramka akceptacji**: żadna treść z AI nie wchodzi do bazy bez przejrzenia; można edytować i odrzucać pojedyncze pozycje.
- [ ] **F47 — Wymuszony PT-PT w promptach**: instrukcje systemowe blokujące brazylijskie słownictwo i formy; oznaczanie pozycji `verified=false` do momentu akceptacji.
- [ ] **F48 — Wyjaśnianie błędów**: po pomyłce przycisk „dlaczego źle?" → krótkie wyjaśnienie po polsku.
- [ ] **F49 — Ocena tłumaczeń**: swobodne tłumaczenie zdania oceniane przez model (wynik + poprawiona wersja).
- [ ] **F50 — Kontrola kosztów**: log każdego wywołania z tokenami i kosztem, twardy limit miesięczny, `429` po przekroczeniu.

#### Moduł 8: Statystyki i motywacja
- [ ] **F51 — Heatmapa aktywności**: kalendarz roczny w stylu GitHuba.
- [ ] **F52 — Przegląd postępu**: liczba pozycji wg stanu (nowe / w nauce / opanowane), retencja, łączny czas nauki.
- [ ] **F53 — Prognoza powtórek**: wykres obciążenia na 30 dni do przodu.
- [ ] **F54 — Lista trudnych słów**: leeches i pozycje o najgorszej skuteczności, z sugestią przeformułowania.
- [ ] **F55 — PWA na ekranie głównym**: instalowalna aplikacja z ikoną, splashem i trybem pełnoekranowym.

### 6.2 Priorytetyzacja (MoSCoW)

| ID | Funkcjonalność | Priorytet | Faza |
|---|---|---|---|
| F01, F02 | Rejestracja na kod + logowanie JWT | Must have | 1 |
| F03, F06 | Ustawienia nauki, osobny postęp per konto | Must have | 1 |
| F07 | Baza startowa PT-PT (~800 pozycji) | Must have | 1 |
| F08, F09 | Przeglądarka słownika i szczegóły pozycji | Must have | 1 |
| F14, F15, F16, F17 | Ekran „Dziś", FSRS, mieszana sesja, dobór trybu | Must have | 1 |
| F18, F20, F21 | Wznawianie sesji, podsumowanie, streak | Must have | 1 |
| F23, F24, F25 | Fiszki + testy wyboru w obu kierunkach | Must have | 1 |
| F55 | PWA na ekranie głównym | Must have | 1 |
| F10, F12, F13 | Ręczne dodawanie, własne talie, przykłady | Should have | 2 |
| F26, F27, F28 | Wpisywanie z pamięci, ocena tolerancyjna, cloze | Should have | 2 |
| F29, F30 | Dopasowywanie par, rozsypanka słów | Should have | 2 |
| F22 | Zawieszanie i reset pozycji | Should have | 2 |
| F33, F34, F36, F37 | Quizy: szybki, zapisywany, wynik, błędy do powtórek | Should have | 2 |
| F40, F41, F42, F43, F44 | Audio: wymowa, cache, prefetch, wolne tempo, fallback | Should have | 3 |
| F31 | Dyktando ze słuchu | Should have | 3 |
| F04, F05 | Ustawienia audio i tolerancji akcentów | Should have | 3 |
| F19 | Tryb offline z kolejką synchronizacji | Should have | 3 |
| F45, F46, F47, F50 | Generowanie zestawów AI z bramką akceptacji i limitem kosztów | Should have | 4 |
| F48, F49, F32 | Wyjaśnianie błędów, ocena tłumaczeń, tryb `translate_ai` | Could have | 4 |
| F11 | Import CSV | Could have | 5 |
| F35, F38, F39 | Quiz na czas, historia podejść, test poziomujący | Could have | 5 |
| F51, F52, F53, F54 | Statystyki: heatmapa, przegląd, prognoza, trudne słowa | Could have | 5 |
| — | Ocena wymowy z mikrofonu (ASR) | Won't have (v1) | — |
| — | Konwersacje z AI / chat po portugalsku | Won't have (v1) | — |
| — | Pełny moduł gramatyki i odmiany czasowników | Won't have (v1) | — |
| — | Aplikacja natywna iOS/Android | Won't have (v1) | — |

> **Legenda:** Must have = bez tego aplikacja nie ma sensu. Should have = ważne, ale MVP przeżyje bez tego. Could have = miłe dodatki. Won't have = świadomie odłożone.

### 6.3 Logika doboru trybu ćwiczenia (F17)

Ten sam materiał musi wracać w coraz trudniejszej formie, inaczej uczymy się rozpoznawać układ przycisków zamiast języka:

| Stan karty | Kierunek `recognition` (PT→PL) | Kierunek `production` (PL→PT) |
|---|---|---|
| `new` (pierwszy kontakt) | `flashcard` — pokaż, przeczytaj, zapamiętaj | — (kierunek produkcyjny startuje dopiero po 2 poprawnych rozpoznaniach) |
| `learning` | `mcq_pt_pl` (4 opcje) | `mcq_pl_pt` (4 opcje) |
| `review`, `stability < 21 dni` | `flashcard` lub `listening` | `typing` lub `cloze` |
| `review`, `stability >= 21 dni` | `listening` (najtrudniejszy wariant rozpoznania) | `typing` bez podpowiedzi, `word_bank` dla zdań |
| `relearning` (po pomyłce) | powrót do `mcq` na jedną rundę, potem normalny tor | jw. |

Tryby `matching` i `word_bank` wchodzą jako urozmaicenie: `matching` na pierwsze 10 kart sesji (rozgrzewka), `word_bank` tylko dla pozycji typu `sentence`.

Mapowanie wyniku na ocenę FSRS w trybach bez samooceny:

| Wynik | Ocena FSRS |
|---|---|
| Poprawnie, czas < 1/2 mediany dla tej karty | `Easy` (4) |
| Poprawnie | `Good` (3) |
| Poprawnie z literówką lub bez akcentu (przy `accent_strict=false`) | `Hard` (2) |
| Błędnie lub przekroczony czas | `Again` (1) |

---

## 7. Komponenty UI / Widoki

### 7.1 Nawigacja i layout

**Mobile (główny):** dolna nawigacja z 4 pozycjami — **Dziś** / **Słownik** / **Quizy** / **Postęp**; ustawienia pod ikoną w nagłówku. Sesja nauki i quiz otwierają się **pełnoekranowo, bez nawigacji** (tylko krzyżyk i pasek postępu) — nic nie ma odciągać od pytania.

**Desktop:** ta sama struktura jako lewy sidebar, treść wyśrodkowana do maks. 900 px. Skróty klawiaturowe w sesji: `spacja` = odsłoń, `1–4` = ocena/wybór odpowiedzi, `Enter` = zatwierdź, `R` = powtórz audio.

Motyw: jasny i ciemny, przełącznik plus tryb systemowy. Duże cele dotykowe (min. 44 px), akcje w zasięgu kciuka (dolna ⅓ ekranu).

### 7.2 Widoki (strony)

| Ścieżka | Nazwa widoku | Opis | Kluczowe komponenty |
|---|---|---|---|
| `/login` | Logowanie / rejestracja | Dwa pola + kod zaproszenia | `AuthForm` |
| `/` | Dziś | Streak, pierścień postępu do celu, liczba powtórek, przycisk „Ucz się", skrót do szybkiego quizu | `StreakBadge`, `ProgressRing`, `QueueSummary`, `PrimaryCTA` |
| `/study` | Sesja nauki | Pełny ekran, jedno zadanie naraz, pasek postępu | `TaskRenderer` (7 trybów), `AudioButton`, `RatingBar`, `FeedbackBanner` |
| `/study/summary` | Podsumowanie sesji | Wynik, czas, streak, lista błędów | `SessionStats`, `MistakeList` |
| `/decks` | Talie | Kafelki z licznikami `nowe / due / opanowane` | `DeckCard`, `DeckGrid` |
| `/decks/:id` | Szczegóły talii | Lista pozycji, „ucz się tej talii", edycja | `ItemList`, `DeckHeader` |
| `/items` | Słownik | Wyszukiwarka + filtry + lista wirtualizowana | `SearchBar`, `FilterChips`, `ItemRow` |
| `/items/:id` | Szczegóły pozycji | Pełne dane gramatyczne, przykłady, audio, historia powtórek | `ItemDetail`, `ExampleList`, `ReviewHistoryChart` |
| `/items/new` | Dodaj pozycję | Formularz ręczny + zakładka „generuj z AI" | `ItemForm`, `AiGeneratePanel` |
| `/quiz` | Quizy | Szybki quiz + zapisane konfiguracje + historia | `QuickQuizCard`, `QuizList` |
| `/quiz/:attemptId` | Rozgrywka | Pełny ekran, licznik pytań, opcjonalny czas | `TaskRenderer`, `QuizTimer` |
| `/quiz/:attemptId/result` | Wynik | Procent, błędy, „dodaj do powtórek" | `ScoreCard`, `MistakeList` |
| `/stats` | Postęp | Heatmapa, prognoza, retencja, trudne słowa | `ActivityHeatmap`, `ForecastChart`, `StatTiles`, `LeechList` |
| `/settings` | Ustawienia | Nauka, audio, konto, motyw | `SettingsForm`, `VoicePicker` |

### 7.3 Kluczowe komponenty

**`TaskRenderer`** — serce aplikacji. Przyjmuje obiekt zadania z dyskryminatorem `mode` i renderuje odpowiedni komponent. Wspólny kontrakt: `{ task, onAnswer(result), onSkip() }`. Dzięki temu dodanie ósmego trybu ćwiczeń to jeden nowy komponent i jeden wpis w mapie — nie przebudowa sesji.

**`FlashCard`** — animowany obrót karty (framer-motion), przód/tył, audio na obu stronach, `RatingBar` z czterema przyciskami i podpowiedzią przewidywanego interwału („za 3 dni").

**`ChoiceGrid`** — 4 duże przyciski w siatce 2×2 (kciuk sięga wszystkich), natychmiastowy feedback kolorem, poprawna odpowiedź podświetlana także przy błędzie.

**`TypeAnswer`** — pole tekstowe z `autocapitalize="off"`, `autocorrect="off"` (autokorekta telefonu psuje portugalskie słowa) i **paskiem diakrytyków** nad klawiaturą: `á à â ã ç é ê í ó ô õ ú`. Po zatwierdzeniu pokazuje różnicę znak po znaku, gdy odpowiedź była „prawie".

**`ClozeSentence`** — zdanie z luką renderowaną jako pole inline; reszta zdania czytelna, tłumaczenie polskie pod spodem jako podpowiedź kontekstu.

**`WordBank`** — klocki ze słowami do ułożenia w zdanie, tap dodaje / tap usuwa, sprawdzanie po komplecie.

**`MatchingGrid`** — dwie kolumny po 5 elementów, tap-tap łączy parę, poprawna para znika z animacją.

**`AudioButton`** — jeden komponent obsługujący cache'owany URL z R2, stan ładowania, fallback na Web Speech API i długie przytrzymanie = odtwarzanie 0,75×.

**`ActivityHeatmap`** — 53 × 7 kwadratów, intensywność wg `reviews_count`, tap na dzień pokazuje szczegóły.

---

## 8. Wymagania niefunkcjonalne

| Wymaganie | Wartość docelowa |
|---|---|
| Czas ładowania (LCP, 4G, mobile) | < 2 s |
| Czas od kliknięcia „Ucz się" do pierwszego pytania | < 1 s (sesja pobierana jednym requestem, audio prefetchowane w tle) |
| Reakcja na odpowiedź | < 100 ms — ocena lokalna na froncie, synchronizacja z serwerem asynchroniczna |
| Rozmiar bundla JS (initial) | < 250 kB gzip |
| Dostępność API | > 99% |
| Bezpieczeństwo | HTTPS wszędzie, Argon2id na hasłach, JWT (access 15 min / refresh 30 dni w httpOnly+SameSite=Strict cookie), CORS ograniczony do domeny frontu, walidacja Pydantic na każdym wejściu, rate limiting na `/api/auth/*` (10/min) i `/api/ai/*` (20/h) |
| Ochrona kosztów | Twarde limity miesięczne dla TTS (znaki) i Claude API (USD); po przekroczeniu `429` z czytelnym komunikatem zamiast rosnącego rachunku |
| Responsywność | **Mobile-first** (360–430 px projektowane najpierw), poprawne do 1920 px |
| Offline | Sesja pobrana przed utratą sieci działa do końca; odpowiedzi w IndexedDB, synchronizacja przy powrocie online; brak sieci nie kasuje postępu |
| Dostępność (a11y) | Kontrast ≥ 4.5:1, focus widoczny, pełna obsługa klawiaturą na desktopie, `aria-live` na feedbacku odpowiedzi |
| Trwałość danych | Codzienny backup Postgresa (Railway), eksport całej bazy pozycji do CSV/JSON na żądanie |
| Poprawność językowa | Każda pozycja `verified=true` przed wejściem do rotacji nauki; treści z AI zawsze przez bramkę akceptacji |

---

## 9. Plan faz

Szczegółowy, zadaniowy rozpis znajduje się w [`PLAN.md`](./PLAN.md). Poniżej ujęcie skrócone.

### Faza 1 — MVP: codzienna nauka działa [~2–3 tygodnie]

**Cel:** Można codziennie wejść na telefonie i uczyć się fiszkami oraz testem wyboru z bazy 800 słówek PT-PT, z prawdziwym harmonogramem powtórek.

**Zakres:**
- [ ] Backend: szkielet FastAPI, Postgres na Railway, Alembic, modele `users`, `user_settings`, `items`, `examples`, `decks`, `deck_items`, `user_item_state`, `reviews`, `study_sessions`, `daily_stats`
- [ ] Backend: auth JWT (F01, F02), `/api/settings`, `/api/items`, `/api/decks`
- [ ] Backend: integracja `fsrs`, builder sesji, mapowanie wyników na oceny, `/api/study/*`
- [ ] Treść: seed ~800 pozycji PT-PT A1–A2 w ~20 taliach (plik JSON w repo + skrypt `seed.py`)
- [ ] Frontend: Vite + React + TS + Tailwind, routing, auth, ekran „Dziś", sesja (`flashcard`, `mcq_pt_pl`, `mcq_pl_pt`), podsumowanie, słownik z wyszukiwarką
- [ ] Frontend: PWA (manifest, ikony, service worker, instalacja na ekranie głównym)
- [ ] Deployment: backend na Railway, front na Cloudflare Pages, domena `porto.pmakarewicz.com`, CORS, zmienne środowiskowe

**Definition of Done:** Oba konta założone; przez 3 kolejne dni da się na telefonie zrobić pełną sesję (nowe + powtórki); zamknięcie aplikacji w połowie sesji nie gubi postępu; streak nalicza się poprawnie o północy w strefie `Europe/Warsaw`; aplikacja zainstalowana na ekranie głównym telefonu.

### Faza 2 — Więcej trybów i quizy [~2 tygodnie]

**Cel:** Ten sam materiał wraca w siedmiu formach, a wiedzę da się przetestować niezależnie od harmonogramu powtórek.

**Zakres:**
- [ ] Tryby: `typing` z paskiem diakrytyków i oceną tolerancyjną (F26, F27), `cloze` (F28), `matching` (F29), `word_bank` (F30)
- [ ] Logika doboru trybu wg stanu karty (F17, sekcja 6.3)
- [ ] Moduł quizów: model danych, `/api/quizzes/*`, szybki quiz, zapisywane konfiguracje, wynik i analiza błędów, „dodaj błędy do powtórek"
- [ ] Ręczne dodawanie pozycji, własne talie, zdania przykładowe (F10, F12, F13)
- [ ] Zawieszanie i reset pozycji (F22)

**Definition of Done:** Sesja miesza minimum 5 trybów; quiz z 20 pytań kończy się wynikiem i listą błędów, a błędy wchodzą do kolejki powtórek na następny dzień; własne słówko dodane z telefonu pojawia się w nauce tego samego dnia.

### Faza 3 — Audio i offline [~1,5 tygodnia]

**Cel:** Słychać portugalski europejski, a sesja przeżywa brak zasięgu.

**Zakres:**
- [ ] Google Cloud TTS (głosy pt-PT), serwis syntezy, cache w R2, tabela `audio_assets`, `/api/audio/*`
- [ ] Skrypt masowej syntezy dla całego seeda + prefetch dla nadchodzącej sesji (F42)
- [ ] `AudioButton` z fallbackiem Web Speech API i odtwarzaniem 0,75× (F43, F44)
- [ ] Tryb `listening` / dyktando (F31)
- [ ] Ustawienia audio: głos, tempo, autoplay (F04)
- [ ] Offline: IndexedDB (Dexie), kolejka odpowiedzi, synchronizacja przy powrocie sieci, cache audio w service workerze (F19)

**Definition of Done:** Każda pozycja w seedzie ma audio pt-PT; pełną sesję da się zrobić w trybie samolotowym i po powrocie online cały postęp trafia na serwer bez duplikatów.

### Faza 4 — AI: generowanie i feedback [~1,5 tygodnia]

**Cel:** Baza rośnie na żądanie, a błędy da się zrozumieć, nie tylko odnotować.

**Zakres:**
- [ ] Serwis Claude API, tabela `ai_generation_jobs`, licznik kosztów i twardy limit (F50)
- [ ] Generowanie zestawów tematycznych z wymuszonym PT-PT (F45, F47)
- [ ] Ekran przeglądu i akceptacji propozycji z edycją pozycji (F46)
- [ ] Generowanie zdań przykładowych dla istniejących pozycji
- [ ] „Dlaczego źle?" — wyjaśnianie błędów (F48)
- [ ] Ocena tłumaczeń i tryb `translate_ai` (F32, F49)

**Definition of Done:** Zestaw „20 zwrotów A2 u lekarza" powstaje w < 30 s, po przejrzeniu ląduje w nowej talii z audio; licznik kosztów działa, a przekroczenie limitu zwraca czytelny komunikat zamiast błędu.

### Faza 5 — Statystyki, import, dopracowanie [~1 tydzień]

**Cel:** Widać postęp i da się zasilić bazę z zewnątrz.

**Zakres:**
- [ ] Heatmapa aktywności, przegląd postępu, prognoza powtórek, lista trudnych słów (F51–F54)
- [ ] Import CSV z raportem błędów (F11)
- [ ] Test poziomujący (F39), quiz na czas (F35), historia podejść (F38)
- [ ] Eksport bazy do CSV/JSON, dopracowanie a11y i wydajności, przegląd wyników Lighthouse

**Definition of Done:** Heatmapa pokazuje realną historię od pierwszego dnia; import 200-wierszowego CSV kończy się raportem bez utraty danych; Lighthouse na mobile: Performance ≥ 90, Accessibility ≥ 95, PWA installable.

---

## 10. Poza zakresem (Out of scope)

- **Ocena wymowy z mikrofonu (ASR)** — technicznie możliwe (Whisper / Google STT), ale wiarygodna ocena wymowy PT-PT to osobny projekt; łatwo zbudować coś, co myli użytkownika fałszywym „dobrze".
- **Chat konwersacyjny z AI po portugalsku** — świetny pomysł na v2, ale rozmywa cel v1, którym jest opanowanie słownictwa z powtórkami.
- **Pełny moduł gramatyki** (tabele odmian, czasy, tryb łączący) — w v1 gramatyka pojawia się wyłącznie w formie zdań i notatek przy pozycjach.
- **Aplikacja natywna** — PWA na ekranie głównym wystarcza; sklepy to koszt utrzymania bez wartości dla dwóch użytkowników.
- **Publiczna rejestracja, plany płatne, panel administracyjny** — aplikacja prywatna.
- **Powiadomienia push** — Web Push na iOS jest kapryśny; przypomnienie o nauce zastępuje ikona na ekranie głównym i nawyk. Do rozważenia po Fazie 5.
- **Rankingi, znajomi, elementy społecznościowe** — brak sensu przy dwóch kontach.
- **Wielojęzyczność interfejsu** — interfejs po polsku, materiał po portugalsku.
- **Optymalizacja parametrów FSRS na własnych danych** — dopiero po zebraniu kilku tysięcy powtórek (log `reviews` jest przygotowany, żeby to później umożliwić).

---

## 11. Otwarte pytania i ryzyka

| # | Pytanie / Ryzyko | Priorytet | Mitygacja | Status |
|---|---|---|---|---|
| 1 | **Jakość seeda PT-PT.** 800 pozycji generowanych z pomocą AI może zawierać brazylizmy i błędne rodzajniki — a błędnie nauczonego słowa trudno się oduczyć | Wysoki | Seed powstaje partiami po ~50 pozycji z jawnym przeglądem; pozycje wątpliwe oznaczone `verified=false` i wyłączone z nauki do czasu sprawdzenia | Otwarte |
| 2 | **Dostępność i jakość głosów pt-PT w Google TTS.** Trzeba potwierdzić, które głosy `pt-PT-*` są dostępne i czy brzmią naturalnie | Wysoki | Przed Fazą 3: test wszystkich dostępnych głosów pt-PT na 10 zdaniach, odsłuch i wybór; fallback na Azure Speech (dobre głosy pt-PT) jeśli jakość zawiedzie | Otwarte |
| 3 | **Aktualny cennik TTS i limity darmowe** — wartości w sekcji 2.1 wymagają weryfikacji przed wdrożeniem | Średni | Sprawdzić cennik przed Fazą 3; przy cache'owaniu realny wolumen to jednorazowa synteza bazy, więc ryzyko kosztowe jest niskie | Otwarte |
| 4 | **Nawis powtórek po przerwie.** Tydzień urlopu = 300 kart `due` i zniechęcenie | Średni | Twardy `review_limit` w sesji + sortowanie po `due` rosnąco; po dłuższej przerwie tryb „nadrabianie" rozkłada zaległości na 7 dni | Otwarte |
| 5 | **Koszty Claude API przy intensywnym generowaniu** | Średni | Twardy limit miesięczny w kodzie, log kosztów per wywołanie, `429` po przekroczeniu | Zaadresowane (F50) |
| 6 | **Dwa kierunki nauki podwajają liczbę kart** — 800 pozycji = 1600 kart, przy 10 nowych dziennie kolejka rośnie szybciej niż intuicyjnie | Średni | `new_per_day` liczy **pozycje**, nie karty; kierunek produkcyjny startuje z opóźnieniem (po 2 poprawnych rozpoznaniach), więc obciążenie narasta łagodnie | Zaadresowane (6.3) |
| 7 | **Autokorekta na telefonie psuje wpisywanie po portugalsku** | Średni | `autocorrect="off"`, `spellcheck="false"`, `autocapitalize="off"` + własny pasek diakrytyków (F26) | Zaadresowane |
| 8 | **Utrata motywacji po 2–3 tygodniach** — najczęstsza przyczyna śmierci takich projektów | Wysoki | Cel dzienny domyślnie niski (25 kart ≈ 6–8 min), streak, sesja ≤ 10 minut; lepiej krótko i codziennie niż długo i raz w tygodniu | Otwarte |
| 9 | Czy quizy mają wpływać na harmonogram FSRS? | Niski | Domyślnie nie (test ≠ nauka); przełącznik `config.affects_schedule` zostawia furtkę | Do decyzji w Fazie 2 |
| 10 | Czy potrzebny jest wspólny podgląd postępu drugiej osoby (motywacja przez porównanie)? | Niski | Do decyzji po Fazie 5; model danych na to pozwala | Otwarte |

---

## Aneks: Środowisko developerskie

### Wymagania

- Python 3.11+
- Node.js 20+
- Docker / OrbStack (lokalny Postgres)
- Konta: Railway, Cloudflare (Pages + R2), Google Cloud (TTS), Anthropic (Claude API)

### Struktura repozytorium

```
porto/
├── backend/
│   ├── app/
│   │   ├── main.py            # bootstrap FastAPI, CORS, routery
│   │   ├── config.py          # ustawienia z env (Pydantic Settings)
│   │   ├── db.py              # sesja SQLAlchemy
│   │   ├── models/            # modele ORM
│   │   ├── schemas/           # modele Pydantic (request/response)
│   │   ├── routers/           # auth, items, decks, study, quizzes, stats, audio, ai
│   │   ├── services/
│   │   │   ├── scheduler.py   # opakowanie FSRS
│   │   │   ├── task_builder.py# budowanie zadań i dystraktorów
│   │   │   ├── grader.py      # ocena odpowiedzi tekstowych
│   │   │   ├── tts.py         # Google TTS + cache w R2
│   │   │   └── ai.py          # Claude API
│   │   └── seed/
│   │       ├── items.json     # baza startowa PT-PT
│   │       └── seed.py        # skrypt ładujący
│   ├── alembic/
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/               # klient HTTP + hooki TanStack Query
│   │   ├── components/        # komponenty współdzielone
│   │   ├── features/
│   │   │   ├── study/         # TaskRenderer i 7 trybów
│   │   │   ├── quiz/
│   │   │   ├── dictionary/
│   │   │   └── stats/
│   │   ├── pages/
│   │   ├── store/             # Zustand: stan sesji
│   │   ├── db/                # Dexie: kolejka offline
│   │   └── main.tsx
│   ├── public/                # ikony PWA, manifest
│   └── package.json
└── docs/
    ├── PRD.md
    └── PLAN.md
```

### Lokalne uruchomienie

```bash
# Baza danych
docker run -d --name porto-db -p 5432:5432 \
  -e POSTGRES_PASSWORD=porto -e POSTGRES_DB=porto postgres:15

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.seed.seed          # ładuje bazę startową
uvicorn app.main:app --reload    # http://localhost:8000/docs

# Frontend
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

### Zmienne środowiskowe

**Backend (`backend/.env`):**
```env
DATABASE_URL=postgresql+psycopg://postgres:porto@localhost:5432/porto
JWT_SECRET=...
JWT_REFRESH_SECRET=...
ACCESS_TOKEN_MINUTES=15
REFRESH_TOKEN_DAYS=30
INVITE_CODE=...                       # wymagany przy rejestracji
CORS_ORIGINS=http://localhost:5173,https://porto.pmakarewicz.com

# AI (Faza 4)
ANTHROPIC_API_KEY=...
AI_MODEL=claude-sonnet-5
AI_MONTHLY_BUDGET_USD=10

# TTS (Faza 3)
GOOGLE_APPLICATION_CREDENTIALS_JSON=...   # cała zawartość JSON-a konta serwisowego
TTS_VOICE_DEFAULT=pt-PT-Neural2-A
TTS_MONTHLY_CHAR_LIMIT=500000

# Audio storage (Faza 3)
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=porto-audio
R2_PUBLIC_URL=https://audio-porto.pmakarewicz.com
```

**Frontend (`frontend/.env`):**
```env
VITE_API_URL=http://localhost:8000
```

### Deployment

| Element | Gdzie | Jak |
|---|---|---|
| Backend + Postgres | Railway | Deploy z gita (katalog `backend/`), zmienne w panelu, `alembic upgrade head` w komendzie startowej |
| Frontend | Cloudflare Pages | Build `npm run build`, katalog `frontend/dist`, domena `porto.pmakarewicz.com` |
| API | Railway domain lub Cloudflare Tunnel | `api-porto.pmakarewicz.com` |
| Audio | Cloudflare R2 | Bucket publiczny read-only pod `audio-porto.pmakarewicz.com` |
| Zadania cykliczne | Railway cron | Nocne: przeliczenie `daily_stats`, wykrywanie leeches, prefetch audio |
