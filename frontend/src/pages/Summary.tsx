import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";

import type { SessionSummary } from "@/api/types";
import { Button, Card, Label, Pill } from "@/components/ui";
import { useSession } from "@/store/session";

export function SummaryPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const reset = useSession((s) => s.reset);
  const summary = location.state as SessionSummary | null;

  useEffect(() => {
    // Przy wyniku policzonym offline stan sesji MUSI zostać: w kolejce leżą
    // nieprzesłane odpowiedzi, a `reset()` skasowałby je razem z sesją.
    // Posprząta `sync()`, gdy połączenie wróci.
    if (!summary?.offline) reset();
    queryClient.invalidateQueries({ queryKey: ["queue-summary"] });
    queryClient.invalidateQueries({ queryKey: ["active-session"] });
    queryClient.invalidateQueries({ queryKey: ["decks"] });
  }, [reset, queryClient, summary?.offline]);

  useEffect(() => {
    if (!summary) navigate("/", { replace: true });
  }, [summary, navigate]);

  if (!summary) return null;

  const minutes = Math.floor(summary.seconds / 60);
  const seconds = summary.seconds % 60;

  return (
    // Kolumna na całą wysokość: podsumowanie bywa krótkie, a wtedy treść
    // wisiała w górnej połowie ekranu nad pustką. Przycisk siada na dole, tam
    // gdzie i tak jest kciuk.
    <div className="safe-top-lg safe-bottom flex min-h-dvh flex-col px-4">
      <div className="grid justify-items-center gap-1 text-center">
        <div className="text-4xl">{summary.accuracy >= 80 ? "🎉" : "💪"}</div>
        <div className="pt text-6xl leading-none tnum">{Math.round(summary.accuracy)}%</div>
        <p className="text-sm text-ink-2">
          Sesja skończona · {summary.completed_count} kart
          {summary.offline ? "" : ` w ${minutes}:${String(seconds).padStart(2, "0")}`}
        </p>
        {summary.offline && (
          <div className="mt-3 rounded-xl border border-warm/40 bg-warm/10 px-3 py-2 text-[12.5px] text-ink-2">
            Bez połączenia — wynik policzony na urządzeniu. Odpowiedzi dolecą do serwera same,
            gdy wróci sieć; seria i statystyki dnia zaktualizują się wtedy.
          </div>
        )}
        {!summary.offline && summary.streak > 0 && (
          <div className="mt-3">
            <Pill tone="warm">🔥 {summary.streak} {summary.streak === 1 ? "dzień" : "dni"} z rzędu</Pill>
          </div>
        )}
      </div>

      <div className="mt-7 grid gap-3">
        <div className="grid grid-cols-3 gap-2">
          <Tile value={summary.correct_count} label="poprawnych" tone="text-good" />
          <Tile value={summary.completed_count - summary.correct_count} label="pomyłek" tone="text-bad" />
          <Tile value={summary.new_count} label="nowych" tone="text-accent" />
        </div>

        {/* Cel dzienny i kolejka to liczby serwera — offline byłyby zerami
            udającymi wynik. */}
        {!summary.offline && (
        <Card className={summary.goal_met ? "border-good-line bg-good-soft" : "border-line bg-surface-2"}>
          <p className="text-[13.5px]">
            {summary.goal_met ? (
              <>Cel dzienny osiągnięty ({summary.done_today}/{summary.goal}).</>
            ) : (
              <>
                Do celu dziennego zostało <b>{Math.max(summary.goal - summary.done_today, 0)}</b> kart.
              </>
            )}{" "}
            {summary.next_due_count > 0 ? (
              <>
                Czeka jeszcze <b>{summary.next_due_count}</b> powtórek.
              </>
            ) : (
              <>Kolejka na teraz pusta.</>
            )}
          </p>
        </Card>
        )}

        {summary.mistakes.length > 0 && (
          <div className="mt-1">
            <Label className="mb-2">Do powtórzenia</Label>
            <div className="grid gap-2">
              {summary.mistakes.map((mistake, index) => (
                <Card key={`${mistake.item_id}-${index}`} className="py-3">
                  {/* Poprawna odpowiedź pod hasłem, zwykłym tekstem. Wcześniej
                      siedziała w czerwonej plakietce po prawej — a czerwień w
                      całej aplikacji znaczy „błąd", więc dokładnie to, czego
                      trzeba się nauczyć, wyglądało na rzecz do odrzucenia. */}
                  <div className="pt text-[17px] leading-snug">{mistake.pt}</div>
                  <div className="mt-0.5 text-[13.5px] text-ink-2">{mistake.pl}</div>
                  {mistake.user_answer && (
                    <div className="mt-1.5 text-[12px] text-ink-3">
                      twoja odpowiedź:{" "}
                      <span className="text-bad line-through decoration-bad/50">
                        {mistake.user_answer}
                      </span>
                    </div>
                  )}
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Przycisk zamykający dzień — przyklejony do dołu, żeby ekran kończył
          się tam, gdzie kończy się telefon. */}
      <div className="mt-auto pb-4 pt-6">
        <Button onClick={() => navigate("/")}>Gotowe na dziś</Button>
      </div>
    </div>
  );
}

function Tile({ value, label, tone }: { value: number; label: string; tone: string }) {
  return (
    <div className="rounded-2xl border border-line bg-surface-2 px-2 py-3 text-center">
      <div className={`text-xl font-bold tnum ${tone}`}>{value}</div>
      <div className="text-[10.5px] text-ink-3">{label}</div>
    </div>
  );
}
