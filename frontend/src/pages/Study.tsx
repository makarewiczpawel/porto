import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import type { SessionSummary, StudySession } from "@/api/types";
import { Feedback, TaskRenderer } from "@/components/TaskRenderer";
import type { AnswerEvent } from "@/components/TaskRenderer";
import { Spinner } from "@/components/ui";
import { useSession } from "@/store/session";

export function StudyPage() {
  const navigate = useNavigate();
  const {
    session,
    position,
    feedback,
    error,
    begin,
    current,
    answer,
    next,
    flush,
  } = useSession();
  const [loading, setLoading] = useState(!session);
  const [finishing, setFinishing] = useState(false);

  // Deep link or refresh: pick the open session back up from the server.
  useEffect(() => {
    if (session) return;
    let cancelled = false;
    (async () => {
      try {
        const active = await api.get<StudySession | null>("/api/study/sessions/active");
        if (cancelled) return;
        if (active && active.tasks.length > 0) begin(active);
        else navigate("/", { replace: true });
      } catch {
        if (!cancelled) navigate("/", { replace: true });
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [session, begin, navigate]);

  const task = current();

  async function finish() {
    if (!session || finishing) return;
    setFinishing(true);
    await flush();
    const summary = await api.post<SessionSummary>(`/api/study/sessions/${session.id}/finish`);
    navigate("/podsumowanie", { replace: true, state: summary });
  }

  // Every question answered — wrap the session up.
  useEffect(() => {
    if (session && !task && !feedback && !loading) void finish();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, task, feedback, loading]);

  async function leave() {
    await flush();
    navigate("/", { replace: true });
  }

  if (loading || !session) return <Spinner label="Przygotowuję sesję…" />;
  if (!task && !feedback) return <Spinner label="Podsumowuję…" />;

  const total = session.planned_count || session.tasks.length;
  const done = Math.min(position + (feedback ? 1 : 0), total);

  function onAnswer(event: AnswerEvent) {
    void answer(
      { index: 0, rating: event.rating, selected_index: event.selectedIndex },
      { isCorrect: event.isCorrect, correctAnswer: event.correctAnswer },
    );
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <div className="safe-top flex items-center gap-3 px-4 pb-2 pt-3">
        <button
          type="button"
          onClick={leave}
          aria-label="Przerwij sesję"
          className="text-xl leading-none text-ink-3 hover:text-ink"
        >
          ✕
        </button>
        <div className="h-[7px] flex-1 overflow-hidden rounded-full bg-surface-3">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-300"
            style={{ width: `${total ? (done / total) * 100 : 0}%` }}
          />
        </div>
        <div className="text-xs font-semibold text-ink-3 tnum">
          {Math.min(position + 1, total)}/{total}
        </div>
      </div>

      {error && (
        <div className="mx-4 mb-2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-xs text-ink-2">
          {error}
        </div>
      )}

      <div className="flex flex-1 flex-col px-4 pb-4">
        {task && (
          <>
            <span className="mb-3 self-start rounded-full border border-accent-line bg-accent-soft px-2.5 py-1 text-[10.5px] font-bold uppercase tracking-[0.08em] text-accent">
              {task.is_new ? "Nowe słowo" : task.direction === "recognition" ? "Rozpoznawanie" : "Produkcja"}
            </span>
            <TaskRenderer task={task} locked={feedback !== null} onAnswer={onAnswer} />
          </>
        )}

        {feedback && (
          <Feedback
            isCorrect={feedback.isCorrect}
            correctAnswer={feedback.correctAnswer}
            nextDueLabel={feedback.nextDueLabel}
            note={feedback.note}
            onNext={next}
          />
        )}
      </div>
    </div>
  );
}
