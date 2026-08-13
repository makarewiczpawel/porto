import { create } from "zustand";
import { persist } from "zustand/middleware";

import { ApiError, api } from "@/api/client";
import type { AnswerPayload, AnswerResult, SessionSummary, StudySession, Task } from "@/api/types";

/**
 * Sesja nauki, która przeżywa brak zasięgu.
 *
 * Cała sesja przychodzi z serwera za jednym razem i od tej chwili jest
 * samowystarczalna: pytania, poprawne odpowiedzi i adresy nagrań leżą w
 * przeglądarce, ocena odbywa się lokalnie. Odpowiedzi trafiają do kolejki i
 * lecą partiami — a gdy nie mają dokąd polecieć, po prostu w niej zostają.
 *
 * Bezpieczne jest to dzięki idempotencji z fazy 1: serwer rozpoznaje odpowiedź
 * po `(sesja, numer pytania, pozycja, kierunek)`, więc ta sama partia wysłana
 * dwa razy nie liczy się podwójnie. Bez tego ponowna wysyłka po zerwanym
 * połączeniu psułaby harmonogram.
 *
 * Stan siedzi w `localStorage`, nie w IndexedDB. Plan zakładał Dexie, ale cała
 * sesja to kilkadziesiąt kilobajtów JSON-a — biblioteka i asynchroniczne API
 * kosztowałyby więcej, niż dają. Gdyby kiedyś doszła historia offline albo
 * cały słownik, wtedy Dexie zacznie mieć sens.
 */
const FLUSH_EVERY = 5;
const STORAGE_KEY = "porto.study.v1";

interface Feedback {
  isCorrect: boolean;
  rating: number;
  correctAnswer: string;
  nextDueLabel: string;
  note: string | null;
  match?: string;
  diff?: string;
  summary?: string;
}

interface SessionState {
  session: StudySession | null;
  position: number;
  queue: AnswerPayload[];
  pending: boolean;
  feedback: Feedback | null;
  correct: number;
  answered: number;
  startedAt: number;
  error: string | null;
  /** Sesja doszła do końca, ale serwer nie potwierdził jeszcze zamknięcia. */
  finishRequested: boolean;
  /** Ostatni stan łącza — do wyświetlenia paska „bez połączenia". */
  online: boolean;

  begin: (session: StudySession) => void;
  current: () => Task | null;
  answer: (payload: Omit<AnswerPayload, "elapsed_ms">, localResult?: Partial<Feedback>) => Promise<void>;
  next: () => void;
  flush: () => Promise<AnswerResult[]>;
  finish: () => Promise<SessionSummary>;
  sync: () => Promise<void>;
  setOnline: (online: boolean) => void;
  reset: () => void;
}

/** Podsumowanie policzone na miejscu, gdy serwer jest nieosiągalny. */
function localSummary(state: SessionState): SessionSummary {
  const session = state.session;
  const answered = state.answered;
  return {
    session_id: session?.id ?? "",
    completed_count: answered,
    correct_count: state.correct,
    accuracy: answered > 0 ? (state.correct / answered) * 100 : 0,
    new_count: session?.tasks.filter((task) => task.is_new).length ?? 0,
    seconds: 0,
    streak: 0,
    goal_met: false,
    done_today: answered,
    goal: 0,
    next_due_count: 0,
    mistakes: [],
    // Podsumowanie z serwera zawiera streak i statystyki dnia, których offline
    // policzyć się nie da. Ekran wie o tym po tej fladze i nie pokazuje zer
    // tak, jakby były prawdziwym wynikiem.
    offline: true,
  };
}

export const useSession = create<SessionState>()(
  persist(
    (set, get) => ({
      session: null,
      position: 0,
      queue: [],
      pending: false,
      feedback: null,
      correct: 0,
      answered: 0,
      startedAt: Date.now(),
      error: null,
      finishRequested: false,
      online: typeof navigator === "undefined" ? true : navigator.onLine,

      begin: (session) =>
        set({
          session,
          position: 0,
          queue: [],
          feedback: null,
          correct: 0,
          answered: 0,
          startedAt: Date.now(),
          error: null,
          finishRequested: false,
        }),

      current: () => {
        const { session, position } = get();
        if (!session) return null;
        return session.tasks[position] ?? null;
      },

      answer: async (payload, localResult) => {
        const state = get();
        const task = state.current();
        if (!task || state.feedback) return;

        const elapsed = Date.now() - state.startedAt;
        const entry: AnswerPayload = {
          ...payload,
          index: task.index,
          elapsed_ms: Math.min(elapsed, 600_000),
        };

        // Show the outcome immediately; the server confirms in the background.
        const optimistic: Feedback = {
          isCorrect: localResult?.isCorrect ?? true,
          rating: payload.rating ?? 3,
          correctAnswer: localResult?.correctAnswer ?? task.back ?? task.pl,
          nextDueLabel: localResult?.nextDueLabel ?? "",
          note: task.notes,
          match: localResult?.match,
          diff: localResult?.diff,
          summary: localResult?.summary,
        };

        set({
          queue: [...state.queue, entry],
          feedback: optimistic,
          answered: state.answered + 1,
          correct: state.correct + (optimistic.isCorrect ? 1 : 0),
        });

        if (get().queue.length >= FLUSH_EVERY) {
          const results = await get().flush();
          const mine = results.find((r) => r.index === entry.index);
          if (mine && get().feedback) {
            set({
              feedback: {
                ...get().feedback!,
                isCorrect: mine.is_correct,
                correctAnswer: mine.correct_answer,
                nextDueLabel: mine.next_due_label,
              },
            });
          }
        }
      },

      next: () => {
        set({ position: get().position + 1, feedback: null, startedAt: Date.now() });
      },

      flush: async () => {
        const { session, queue, pending } = get();
        if (!session || queue.length === 0 || pending) return [];
        set({ pending: true, error: null });
        try {
          const body = await api.post<{ results: AnswerResult[] }>(
            `/api/study/sessions/${session.id}/answers`,
            { answers: queue },
          );
          set({ queue: [], pending: false, online: true });
          return body.results;
        } catch (error) {
          // Serwer odpowiedział i odmówił — sesji już nie ma (zamknięta na
          // innym urządzeniu, skasowana, wygasła). Trzymanie kolejki w
          // nieskończoność zamieniłoby to w wieczny komunikat o braku sieci,
          // więc odpuszczamy ją świadomie i mówimy o tym wprost.
          if (error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 401) {
            set({
              queue: [],
              pending: false,
              online: true,
              error: "Ta sesja już nie istnieje na serwerze — postęp z niej nie został zapisany.",
              finishRequested: false,
            });
            return [];
          }
          // Brak sieci: kolejka zostaje i pójdzie, gdy połączenie wróci.
          set({
            pending: false,
            online: false,
            error: "Brak połączenia. Postęp zapisany na urządzeniu.",
          });
          return [];
        }
      },

      finish: async () => {
        const state = get();
        if (!state.session) throw new Error("Nie ma sesji do zamknięcia.");
        set({ finishRequested: true });
        await get().flush();

        if (get().queue.length > 0) {
          // Część odpowiedzi nie doszła — zamykanie sesji teraz zgubiłoby je.
          // Zostaje do dosłania, a użytkownik dostaje wynik policzony lokalnie.
          return localSummary(get());
        }
        try {
          const summary = await api.post<SessionSummary>(
            `/api/study/sessions/${state.session.id}/finish`,
          );
          set({ finishRequested: false, online: true });
          return summary;
        } catch {
          set({ online: false });
          return localSummary(get());
        }
      },

      /** Dosyła to, co czeka. Wołane po powrocie sieci i przy starcie aplikacji. */
      sync: async () => {
        const { session, queue, finishRequested } = get();
        if (!session) return;
        if (queue.length > 0) await get().flush();
        if (finishRequested && get().queue.length === 0) {
          try {
            await api.post<SessionSummary>(`/api/study/sessions/${session.id}/finish`);
            get().reset();
          } catch {
            set({ online: false });
          }
        }
      },

      setOnline: (online) => set({ online, error: online ? null : get().error }),

      reset: () =>
        set({
          session: null,
          position: 0,
          queue: [],
          feedback: null,
          correct: 0,
          answered: 0,
          error: null,
          finishRequested: false,
        }),
    }),
    {
      name: STORAGE_KEY,
      // `pending` i `feedback` opisują bieżącą chwilę, nie postęp — po
      // ponownym otwarciu aplikacji nie mają sensu i mogłyby zablokować ekran.
      partialize: (state) => ({
        session: state.session,
        position: state.position,
        queue: state.queue,
        correct: state.correct,
        answered: state.answered,
        finishRequested: state.finishRequested,
      }),
    },
  ),
);

/**
 * Pilnuje dosyłania: przy starcie aplikacji i za każdym razem, gdy sieć wraca.
 *
 * `online` z przeglądarki bywa optymistyczne (mówi „jest łącze" przy hotspocie
 * bez internetu), więc traktujemy je jako podpowiedź, kiedy spróbować — o tym,
 * czy się udało, decyduje odpowiedź serwera.
 */
export function watchConnection(): () => void {
  const store = useSession.getState();

  const goOnline = () => {
    useSession.getState().setOnline(true);
    void useSession.getState().sync();
  };
  const goOffline = () => useSession.getState().setOnline(false);

  window.addEventListener("online", goOnline);
  window.addEventListener("offline", goOffline);
  // Powrót do karty po dłuższej przerwie to równie dobry moment jak zdarzenie
  // `online`, które w tle bywa niedostarczone.
  const onVisible = () => {
    if (document.visibilityState === "visible" && navigator.onLine) void useSession.getState().sync();
  };
  document.addEventListener("visibilitychange", onVisible);

  if (store.queue.length > 0 || store.finishRequested) void store.sync();

  return () => {
    window.removeEventListener("online", goOnline);
    window.removeEventListener("offline", goOffline);
    document.removeEventListener("visibilitychange", onVisible);
  };
}
