import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Link } from "react-router-dom";

import { ApiError, api } from "@/api/client";
import type { QueueSummary, StudySession } from "@/api/types";
import { Button, Card, ErrorNote, Label, Pill, ProgressRing, Spinner } from "@/components/ui";
import { useAuth } from "@/store/auth";
import { useSession } from "@/store/session";

function greeting(name: string) {
  const hour = new Date().getHours();
  if (hour < 12) return `Bom dia, ${name}`;
  if (hour < 19) return `Boa tarde, ${name}`;
  return `Boa noite, ${name}`;
}

export function TodayPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const begin = useSession((s) => s.begin);

  const summary = useQuery({
    queryKey: ["queue-summary"],
    queryFn: () => api.get<QueueSummary>("/api/study/queue/summary"),
  });

  const active = useQuery({
    queryKey: ["active-session"],
    queryFn: () => api.get<StudySession | null>("/api/study/sessions/active"),
  });

  const start = useMutation({
    mutationFn: async () => {
      const existing = await api.get<StudySession | null>("/api/study/sessions/active");
      if (existing && existing.tasks.length > 0) return existing;
      if (existing) {
        // Every question already answered — close it out so a new one can start.
        await api.post(`/api/study/sessions/${existing.id}/abandon`);
      }
      return api.post<StudySession>("/api/study/sessions", {});
    },
    onSuccess: (session) => {
      begin(session);
      queryClient.invalidateQueries({ queryKey: ["active-session"] });
      navigate("/nauka");
    },
  });

  if (summary.isLoading) return <Spinner />;
  if (summary.isError || !summary.data) {
    return (
      <div className="p-4">
        <ErrorNote>Nie udało się pobrać dzisiejszej kolejki. Sprawdź połączenie.</ErrorNote>
      </div>
    );
  }

  const data = summary.data;
  const resumable = active.data && active.data.tasks.length > 0 ? active.data : null;
  const nothingToDo = data.due === 0 && data.new_available === 0;
  const startError =
    start.error instanceof ApiError
      ? start.error.code === "NOTHING_TO_STUDY"
        ? "Na teraz nie ma czego powtarzać."
        : start.error.message
      : null;

  return (
    <div className="px-4 pt-3">
      <header className="mb-2 flex items-center justify-between gap-3">
        <h1 className="pt text-2xl">{greeting(user?.display_name ?? "")}</h1>
        <Link
          to="/ustawienia"
          aria-label="Ustawienia"
          className="grid h-9 w-9 place-items-center rounded-full border border-line bg-surface-2 text-ink-2"
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2v.2a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.6 1.7 1.7 0 0 0-1.9.4l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0-1.2-2.9H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1.1 1.7 1.7 0 0 0-.4-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3h.1A1.7 1.7 0 0 0 10 3.1V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.4l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9v.1a1.7 1.7 0 0 0 1.6 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
          </svg>
        </Link>
      </header>

      <div className="grid justify-items-center gap-2 py-3">
        <ProgressRing value={data.done_today} max={data.goal} label="kart dzisiaj" />
        {data.streak > 0 ? (
          <Pill tone="warm">🔥 {data.streak} {data.streak === 1 ? "dzień" : "dni"} z rzędu</Pill>
        ) : (
          <span className="text-[13px] text-ink-3">Zrób {data.goal} kart, żeby zacząć serię</span>
        )}
      </div>

      <div className="grid gap-3">
        <div className="grid grid-cols-2 gap-2.5">
          <div className="rounded-2xl border border-line bg-surface-2 px-3.5 py-3">
            <div className="text-2xl font-bold leading-tight text-accent tnum">{data.due}</div>
            <div className="text-xs text-ink-2">powtórek na dziś</div>
          </div>
          <div className="rounded-2xl border border-line bg-surface-2 px-3.5 py-3">
            <div className="text-2xl font-bold leading-tight tnum">{data.new_available}</div>
            <div className="text-xs text-ink-2">nowych pozycji</div>
          </div>
        </div>

        {startError && <ErrorNote>{startError}</ErrorNote>}

        {nothingToDo ? (
          <Card className="border-good-line bg-good-soft text-center">
            <div className="text-[15px] font-semibold text-good">Na dziś gotowe ✓</div>
            <p className="mt-1 text-[13px] text-ink-2">
              {data.next_due_at
                ? `Następne powtórki ${new Date(data.next_due_at).toLocaleString("pl-PL", {
                    weekday: "long",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}.`
                : "Dodaj nowe pozycje albo wróć jutro."}
            </p>
          </Card>
        ) : (
          <Button onClick={() => start.mutate()} disabled={start.isPending}>
            {start.isPending ? "Przygotowuję…" : resumable ? "Wróć do sesji" : "Ucz się"}
            <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </Button>
        )}

        {resumable && (
          <p className="text-center text-xs text-ink-3">
            Przerwana sesja: zostało {resumable.tasks.length} z {resumable.planned_count} kart.
          </p>
        )}

        <div className="mt-2">
          <Label className="mb-2">Skróty</Label>
          <div className="grid gap-2">
            <Link
              to="/talie"
              className="flex items-center justify-between rounded-2xl border border-line bg-surface px-3.5 py-3 text-[14.5px] font-semibold"
            >
              Ucz się z wybranej talii
              <span className="text-ink-3">→</span>
            </Link>
            <Link
              to="/slownik"
              className="flex items-center justify-between rounded-2xl border border-line bg-surface px-3.5 py-3 text-[14.5px] font-semibold"
            >
              Przeglądaj słownik
              <span className="text-ink-3">→</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
