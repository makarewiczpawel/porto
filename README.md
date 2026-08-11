# Porto

Prywatna aplikacja webowa (PWA) do codziennej nauki **portugalskiego europejskiego (PT-PT)**.

Codzienna sesja słówek i zwrotów z harmonogramem powtórek (FSRS), siedem trybów ćwiczeń
(fiszki, testy wyboru, wpisywanie, luki w zdaniach, dopasowywanie par, rozsypanka, dyktando),
quizy sprawdzające wiedzę oraz wymowa w głosach pt-PT.

## Dokumentacja

| Dokument | Zawartość |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | Pełna specyfikacja: cele, stack, model danych, endpointy API, 55 funkcjonalności, widoki UI, plan faz, ryzyka |
| [`docs/PLAN.md`](docs/PLAN.md) | Plan wykonawczy: kolejność prac, zadania per faza, punkty kontrolne, harmonogram |

## Stack

FastAPI (Python) · PostgreSQL · React + Vite + TypeScript · Tailwind
Railway (backend) · Cloudflare Pages (frontend) · Cloudflare R2 (audio)
Google Cloud TTS (głosy pt-PT) · Claude API (generowanie treści)

## Status

Faza planowania — dokumenty gotowe, implementacja przed nami.
Uruchomienie lokalne i zmienne środowiskowe: patrz Aneks w [`docs/PRD.md`](docs/PRD.md).
