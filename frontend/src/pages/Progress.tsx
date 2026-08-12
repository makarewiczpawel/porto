import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { QueueSummary } from "@/api/types";
import { Card, Label, Spinner } from "@/components/ui";

interface Overview {
  streak: number;
  cards_by_state: Record<string, number>;
  items_total: number;
  reviews_total: number;
  accuracy: number;
}

const STATE_LABELS: Record<string, string> = {
  new: "nowe",
  learning: "w nauce",
  review: "opanowane",
  relearning: "do poprawy",
};

export function ProgressPage() {
  const overview = useQuery({
    queryKey: ["overview"],
    queryFn: () => api.get<Overview>("/api/study/stats/overview"),
  });
  const summary = useQuery({
    queryKey: ["queue-summary"],
    queryFn: () => api.get<QueueSummary>("/api/study/queue/summary"),
  });

  if (overview.isLoading || !overview.data) return <Spinner />;
  const data = overview.data;
  const states = data.cards_by_state ?? {};
  const totalCards = Object.values(states).reduce((sum, value) => sum + value, 0);

  return (
    <div className="px-4 pt-4">
      <h1 className="pt mb-4 text-2xl">Postęp</h1>

      <div className="grid grid-cols-3 gap-2">
        <Tile value={data.streak} label="dni z rzędu" tone="text-warm" />
        <Tile value={states.review ?? 0} label="opanowanych" tone="text-good" />
        <Tile value={`${data.accuracy}%`} label="skuteczność" tone="text-ink" />
      </div>

      <Card className="mt-3">
        <Label className="mb-3">Twoje karty</Label>
        {totalCards === 0 ? (
          <p className="text-[13.5px] text-ink-2">
            Jeszcze nie zacząłeś. Pierwsza sesja utworzy karty powtórek.
          </p>
        ) : (
          <div className="grid gap-2.5">
            {Object.entries(STATE_LABELS).map(([key, label]) => {
              const value = states[key] ?? 0;
              const share = totalCards ? (value / totalCards) * 100 : 0;
              return (
                <div key={key}>
                  <div className="mb-1 flex items-center justify-between text-[13px]">
                    <span className="text-ink-2">{label}</span>
                    <span className="tnum">{value}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-surface-3">
                    <span
                      className={`block h-full rounded-full ${
                        key === "review" ? "bg-good" : key === "relearning" ? "bg-bad" : "bg-accent"
                      }`}
                      style={{ width: `${share}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <Card className="mt-3">
        <Label className="mb-2">Baza</Label>
        <div className="grid gap-1.5 text-[13.5px]">
          <Row label="Pozycji w słowniku" value={data.items_total} />
          <Row label="Wszystkich powtórek" value={data.reviews_total} />
          <Row label="Powtórek czekających" value={summary.data?.due ?? 0} />
          <Row label="Nietkniętych pozycji" value={summary.data?.new_available ?? 0} />
        </div>
      </Card>

      <p className="mt-6 text-center text-[11.5px] text-ink-3">
        Heatmapa aktywności i prognoza powtórek dochodzą w fazie 5.
      </p>
    </div>
  );
}

function Tile({ value, label, tone }: { value: number | string; label: string; tone: string }) {
  return (
    <div className="rounded-2xl border border-line bg-surface-2 px-2 py-3 text-center">
      <div className={`text-xl font-bold tnum ${tone}`}>{value}</div>
      <div className="text-[10.5px] text-ink-3">{label}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-ink-2">{label}</span>
      <span className="tnum">{value}</span>
    </div>
  );
}
