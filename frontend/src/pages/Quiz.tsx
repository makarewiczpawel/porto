import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { ApiError, api } from "@/api/client";
import type { Quiz, QuizAttempt, QuizHistoryEntry, QuizResult } from "@/api/types";
import { TaskRenderer } from "@/components/TaskRenderer";
import type { AnswerEvent } from "@/components/TaskRenderer";
import { Button, Card, EmptyState, ErrorNote, Label, Pill, Spinner, cx } from "@/components/ui";

// ── hub ───────────────────────────────────────────────────────────────────
export function QuizzesPage() {
  const navigate = useNavigate();
  const [count, setCount] = useState(10);

  const quizzes = useQuery({ queryKey: ["quizzes"], queryFn: () => api.get<Quiz[]>("/api/quizzes") });
  const history = useQuery({
    queryKey: ["quiz-history"],
    queryFn: () => api.get<QuizHistoryEntry[]>("/api/quizzes/attempts"),
  });

  const quick = useMutation({
    mutationFn: () => api.post<QuizAttempt>("/api/quizzes/quick", { count }),
    onSuccess: (attempt) => navigate(`/quizy/${attempt.id}`, { state: attempt }),
  });
  const saved = useMutation({
    mutationFn: (quizId: string) => api.post<QuizAttempt>(`/api/quizzes/${quizId}/attempts`),
    onSuccess: (attempt) => navigate(`/quizy/${attempt.id}`, { state: attempt }),
  });

  const failure = [quick.error, saved.error].find(Boolean);
  const message =
    failure instanceof ApiError
      ? failure.code === "NOT_ENOUGH_ITEMS"
        ? "Za mało pozycji na taki test. Zmniejsz liczbę pytań."
        : failure.message
      : null;

  return (
    <div className="px-4 pt-4">
      <h1 className="pt mb-3 text-2xl">Quizy</h1>

      <div className="grid gap-3">
        {message && <ErrorNote>{message}</ErrorNote>}

        <Card className="border-accent-line bg-accent-soft">
          <Label className="text-accent">Szybki quiz</Label>
          <p className="mb-3 mt-1.5 text-sm text-ink-2">
            Sprawdzian z tego, czego się uczysz. Nie rusza harmonogramu powtórek.
          </p>
          <div className="mb-3 flex gap-2">
            {[5, 10, 20].map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setCount(value)}
                aria-pressed={count === value}
                className={cx(
                  "flex-1 rounded-xl border py-2 text-sm font-semibold",
                  count === value
                    ? "border-accent bg-accent text-accent-ink"
                    : "border-line bg-surface text-ink-2",
                )}
              >
                {value} pytań
              </button>
            ))}
          </div>
          <Button onClick={() => quick.mutate()} disabled={quick.isPending}>
            {quick.isPending ? "Układam…" : "Zacznij"}
          </Button>
        </Card>

        {quizzes.data && quizzes.data.length > 0 && (
          <div>
            <Label className="mb-2">Twoje testy</Label>
            <div className="grid gap-2">
              {quizzes.data.map((quiz) => (
                <button
                  key={quiz.id}
                  type="button"
                  onClick={() => saved.mutate(quiz.id)}
                  className="flex items-center gap-3 rounded-2xl border border-line bg-surface px-3.5 py-3 text-left hover:border-accent-line"
                >
                  <div className="min-w-0">
                    <div className="truncate text-[14.5px] font-semibold">{quiz.name}</div>
                    <div className="text-[12.5px] text-ink-2">
                      {quiz.config.count ?? 10} pytań
                      {quiz.config.cefr_level ? ` · ${quiz.config.cefr_level}` : ""}
                    </div>
                  </div>
                  <div className="ml-auto flex-none">
                    {quiz.last_score !== null ? (
                      <Pill tone={quiz.last_score >= 80 ? "good" : quiz.last_score >= 60 ? "neutral" : "bad"}>
                        {Math.round(quiz.last_score)}%
                      </Pill>
                    ) : (
                      <span className="text-ink-3">→</span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {history.data && history.data.length > 0 && (
          <div className="mt-2">
            <Label className="mb-2">Historia</Label>
            <Card className="grid gap-2.5">
              {history.data.slice(0, 8).map((entry) => (
                <div key={entry.attempt_id} className="flex items-center justify-between gap-3 text-[13.5px]">
                  <span className="truncate text-ink-2">
                    {entry.name}
                    {entry.finished_at && (
                      <span className="text-ink-3">
                        {" · "}
                        {new Date(entry.finished_at).toLocaleDateString("pl-PL", {
                          day: "numeric",
                          month: "short",
                        })}
                      </span>
                    )}
                  </span>
                  <b className="tnum flex-none">{Math.round(entry.score)}%</b>
                </div>
              ))}
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}

// ── playing ───────────────────────────────────────────────────────────────
export function QuizAttemptPage() {
  const { attemptId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [attempt] = useState<QuizAttempt | null>((location.state as QuizAttempt) ?? null);
  const [position, setPosition] = useState(0);
  const [answered, setAnswered] = useState(0);
  const startedAt = useRef(Date.now());
  const pending = useRef<{ index: number; selected_index?: number; user_answer?: string; elapsed_ms: number }[]>(
    [],
  );

  const questions = attempt?.questions ?? [];
  const task = questions[position];

  useEffect(() => {
    if (!attempt) navigate("/quizy", { replace: true });
  }, [attempt, navigate]);

  const submit = useMutation({
    mutationFn: async () => {
      if (pending.current.length) {
        await api.post(`/api/quizzes/attempts/${attemptId}/answers`, { answers: pending.current });
        pending.current = [];
      }
      return api.post<QuizResult>(`/api/quizzes/attempts/${attemptId}/submit`);
    },
    onSuccess: (result) => navigate(`/quizy/${attemptId}/wynik`, { replace: true, state: result }),
  });

  function record(event: AnswerEvent) {
    if (!task) return;
    pending.current.push({
      index: task.index,
      selected_index: event.selectedIndex,
      user_answer: event.userAnswer,
      elapsed_ms: Math.min(Date.now() - startedAt.current, 600_000),
    });
    startedAt.current = Date.now();
    setAnswered((n) => n + 1);

    if (position + 1 >= questions.length) {
      submit.mutate();
    } else {
      setPosition((p) => p + 1);
    }
  }

  if (!attempt) return null;
  if (submit.isPending) return <Spinner label="Liczę wynik…" />;

  return (
    <div className="flex min-h-dvh flex-col">
      <div className="safe-top flex items-center gap-3 px-4 pb-2 pt-3">
        <button
          type="button"
          onClick={() => submit.mutate()}
          aria-label="Zakończ test"
          className="text-xl leading-none text-ink-3 hover:text-ink"
        >
          ✕
        </button>
        <div className="h-[7px] flex-1 overflow-hidden rounded-full bg-surface-3">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-300"
            style={{ width: `${(answered / questions.length) * 100}%` }}
          />
        </div>
        <div className="tnum text-xs font-semibold text-ink-3">
          {position + 1}/{questions.length}
        </div>
      </div>

      <div className="flex flex-1 flex-col px-4 pb-4">
        <span className="mb-3 self-start rounded-full border border-line bg-surface-2 px-2.5 py-1 text-[10.5px] font-bold uppercase tracking-[0.08em] text-ink-3">
          {attempt.name}
        </span>
        {/* No feedback between questions — a test tells you the score at the end. */}
        {task && (
          <TaskRenderer key={task.index} task={task} locked={false} localGrading={false} onAnswer={record} />
        )}
      </div>
    </div>
  );
}

// ── result ────────────────────────────────────────────────────────────────
export function QuizResultPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const result = location.state as QuizResult | null;

  useEffect(() => {
    if (!result) navigate("/quizy", { replace: true });
    else {
      queryClient.invalidateQueries({ queryKey: ["quiz-history"] });
      queryClient.invalidateQueries({ queryKey: ["quizzes"] });
    }
  }, [result, navigate, queryClient]);

  const toReviews = useMutation({
    mutationFn: () => api.post<{ scheduled: number }>(`/api/quizzes/attempts/${result?.attempt_id}/to-reviews`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["queue-summary"] }),
  });

  const delta = useMemo(() => {
    if (!result || result.previous_score === null) return null;
    return Math.round(result.score - result.previous_score);
  }, [result]);

  if (!result) return null;

  const minutes = Math.floor(result.seconds / 60);
  const seconds = result.seconds % 60;
  const tone = result.score >= 80 ? "text-good" : result.score >= 60 ? "text-ink" : "text-bad";

  return (
    <div className="safe-top px-4 pb-8 pt-6">
      <div className="grid justify-items-center gap-1 text-center">
        <div className={cx("pt text-6xl leading-none tnum", tone)}>{Math.round(result.score)}%</div>
        <p className="text-sm text-ink-2">
          {result.name} · {result.total} pytań · {minutes}:{String(seconds).padStart(2, "0")}
        </p>
        {delta !== null && (
          <div className="mt-2">
            <Pill tone={delta >= 0 ? "good" : "bad"}>
              {delta >= 0 ? `+${delta}` : delta} pkt vs poprzednio
            </Pill>
          </div>
        )}
      </div>

      <div className="mt-6 grid gap-3">
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-2xl border border-line bg-surface-2 px-2 py-3 text-center">
            <div className="tnum text-xl font-bold text-good">{result.correct}</div>
            <div className="text-[10.5px] text-ink-3">poprawnych</div>
          </div>
          <div className="rounded-2xl border border-line bg-surface-2 px-2 py-3 text-center">
            <div className="tnum text-xl font-bold text-bad">{result.total - result.correct}</div>
            <div className="text-[10.5px] text-ink-3">błędów</div>
          </div>
        </div>

        {result.mistakes.length > 0 ? (
          <>
            <Label className="mt-2">Do poprawy</Label>
            <div className="grid gap-2">
              {result.mistakes.map((mistake, index) => (
                <Card key={`${mistake.item_id}-${index}`} className="border-bad-line">
                  <div className="flex items-start justify-between gap-3">
                    <div className="pt text-[17px]">{mistake.pt}</div>
                    <Pill tone="bad">{mistake.pl}</Pill>
                  </div>
                  <div className="mt-1 text-xs text-ink-3">
                    {mistake.skipped ? (
                      "bez odpowiedzi"
                    ) : (
                      <>
                        twoja odpowiedź: <i>{mistake.user_answer || "—"}</i>
                      </>
                    )}
                  </div>
                </Card>
              ))}
            </div>

            <Button onClick={() => toReviews.mutate()} disabled={toReviews.isPending || toReviews.isSuccess}>
              {toReviews.isSuccess
                ? `Dodano ${toReviews.data?.scheduled ?? 0} do powtórek ✓`
                : `Dodaj ${result.mistakes.length} błędów do powtórek`}
            </Button>
          </>
        ) : (
          <EmptyState title="Komplet ✓" hint="Wszystkie odpowiedzi poprawne." />
        )}

        <Button variant="ghost" onClick={() => navigate("/quizy")}>
          Wróć do quizów
        </Button>
      </div>
    </div>
  );
}
