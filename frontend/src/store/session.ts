import { create } from "zustand";

import { api } from "@/api/client";
import type { AnswerPayload, AnswerResult, StudySession, Task } from "@/api/types";

/** Answers are queued locally and flushed in batches. The server dedupes by
 *  (session, question index), so a retry after a dropped connection is safe —
 *  which is also the groundwork for offline mode in phase 3. */
const FLUSH_EVERY = 5;

interface Feedback {
  isCorrect: boolean;
  rating: number;
  correctAnswer: string;
  nextDueLabel: string;
  note: string | null;
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

  begin: (session: StudySession) => void;
  current: () => Task | null;
  answer: (payload: Omit<AnswerPayload, "elapsed_ms">, localResult?: Partial<Feedback>) => Promise<void>;
  next: () => void;
  flush: () => Promise<AnswerResult[]>;
  reset: () => void;
}

export const useSession = create<SessionState>((set, get) => ({
  session: null,
  position: 0,
  queue: [],
  pending: false,
  feedback: null,
  correct: 0,
  answered: 0,
  startedAt: Date.now(),
  error: null,

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
    const entry: AnswerPayload = { ...payload, index: task.index, elapsed_ms: Math.min(elapsed, 600_000) };

    // Show the outcome immediately; the server confirms in the background.
    const optimistic: Feedback = {
      isCorrect: localResult?.isCorrect ?? true,
      rating: payload.rating ?? 3,
      correctAnswer: localResult?.correctAnswer ?? task.back ?? task.pl,
      nextDueLabel: localResult?.nextDueLabel ?? "",
      note: task.notes,
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
    const { position, startedAt } = get();
    void startedAt;
    set({ position: position + 1, feedback: null, startedAt: Date.now() });
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
      set({ queue: [], pending: false });
      return body.results;
    } catch {
      // Keep the queue — it will go out with the next flush or on finish.
      set({ pending: false, error: "Brak połączenia. Postęp zapisany lokalnie." });
      return [];
    }
  },

  reset: () =>
    set({ session: null, position: 0, queue: [], feedback: null, correct: 0, answered: 0, error: null }),
}));
