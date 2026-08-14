import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import type { Forecast, HardItem, Heatmap, HeatmapDay, Overview, QueueSummary } from "@/api/types";
import { Card, Label, Spinner, plural } from "@/components/ui";

const STATE_LABELS: Record<string, string> = {
  new: "nowe",
  learning: "w nauce",
  review: "opanowane",
  relearning: "do poprawy",
};

export function ProgressPage() {
  const overview = useQuery({
    queryKey: ["overview"],
    queryFn: () => api.get<Overview>("/api/stats/overview"),
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
        {/* Retencja, nie skuteczność od początku świata: liczy ostatni miesiąc
            i tylko karty powtarzane, więc mówi, czy materiał zostaje w głowie
            teraz. Brak danych to „—", bo zero procent to zupełnie co innego. */}
        <Tile
          value={data.retention_30d === null ? "—" : `${data.retention_30d}%`}
          label="pamiętasz"
          tone="text-accent"
        />
      </div>

      <ActivityHeatmap />
      <ReviewForecast />

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

      <HardestWords />

      <Card className="mt-3">
        <Label className="mb-2">Baza</Label>
        <div className="grid gap-1.5 text-[13.5px]">
          <Row label="Pozycji w słowniku" value={data.items_total} />
          <Row label="Wszystkich powtórek" value={data.reviews_total} />
          <Row label="Czas nauki" value={formatDuration(data.seconds_total)} />
          <Row label="Powtórek czekających" value={summary.data?.due ?? 0} />
          <Row label="Nietkniętych pozycji" value={summary.data?.new_available ?? 0} />
        </div>
      </Card>
    </div>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} s`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  return hours > 0 ? `${hours} h ${minutes} min` : `${minutes} min`;
}

/**
 * Kalendarz aktywności — jeden kwadrat na dzień, ostatnie pół roku.
 *
 * Dni puste są tu równie ważne jak pełne: bez nich nie widać przerw, a przerwy
 * są jedyną rzeczą, o której ta mapa ma coś powiedzieć. Kolumna to tydzień,
 * poniedziałek u góry — tak jak w polskim kalendarzu.
 */
function ActivityHeatmap() {
  const query = useQuery({
    queryKey: ["heatmap"],
    queryFn: () => api.get<Heatmap>("/api/stats/heatmap?days=182"),
    retry: false,
  });
  if (!query.data || query.data.days.length === 0) return null;
  const days = query.data.days;

  // Dopełnienie do poniedziałku, żeby kolumny były tygodniami, a nie
  // przypadkowymi siódemkami dni.
  const first = new Date(days[0].date);
  const padding = (first.getDay() + 6) % 7;
  const cells: (HeatmapDay | null)[] = [...Array(padding).fill(null), ...days];
  const weeks: (HeatmapDay | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));

  return (
    <Card className="mt-3">
      <div className="mb-3 flex items-baseline justify-between">
        <Label>Aktywność</Label>
        <span className="text-[11.5px] text-ink-3">
          {query.data.active_days} {plural(query.data.active_days, "dzień", "dni", "dni")} nauki
        </span>
      </div>
      <div className="flex gap-[3px] overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {weeks.map((week, index) => (
          <div key={index} className="grid flex-none gap-[3px]">
            {week.map((day, position) =>
              day === null ? (
                <span key={position} className="h-[11px] w-[11px]" />
              ) : (
                <span
                  key={day.date}
                  title={`${day.date}: ${day.reviews} ${plural(day.reviews, "karta", "karty", "kart")}`}
                  className={`h-[11px] w-[11px] rounded-[3px] ${intensity(day)}`}
                />
              ),
            )}
          </div>
        ))}
      </div>
      <div className="mt-2 flex items-center gap-1.5 text-[10.5px] text-ink-3">
        mniej
        <span className="h-[9px] w-[9px] rounded-[2px] bg-surface-3" />
        <span className="h-[9px] w-[9px] rounded-[2px] bg-accent/30" />
        <span className="h-[9px] w-[9px] rounded-[2px] bg-accent/60" />
        <span className="h-[9px] w-[9px] rounded-[2px] bg-accent" />
        więcej
      </div>
    </Card>
  );
}

/** Wysokość obszaru słupków w pikselach. */
const BAR_AREA = 76;

function intensity(day: HeatmapDay): string {
  if (day.reviews === 0) return "bg-surface-3";
  if (day.reviews < 10) return "bg-accent/30";
  if (day.reviews < 25) return "bg-accent/60";
  return "bg-accent";
}

/**
 * Ile powtórek wypada w najbliższych dwóch tygodniach.
 *
 * Sens tego wykresu jest ostrzegawczy: pokazuje górkę, zanim się w nią wejdzie,
 * więc da się nadrobić dzień wcześniej zamiast zobaczyć nagle sto kart.
 */
function ReviewForecast() {
  const query = useQuery({
    queryKey: ["forecast"],
    queryFn: () => api.get<Forecast>("/api/stats/forecast?days=14"),
    retry: false,
  });
  if (!query.data || query.data.total === 0) return null;
  const days = query.data.days;
  const peak = Math.max(...days.map((day) => day.due), 1);

  return (
    <Card className="mt-3">
      <div className="mb-3 flex items-baseline justify-between">
        <Label>Powtórki na najbliższe dni</Label>
        <span className="text-[11.5px] text-ink-3 tnum">{query.data.total} łącznie</span>
      </div>
      {/* Wysokość słupka w pikselach, nie w procentach: procent potrzebuje
          rodzica o znanej wysokości, a w kolumnie elastycznej takiego nie ma —
          słupki wychodziły niewidoczne, zostawały same podpisy dat. */}
      <div className="flex items-end gap-[3px]" style={{ height: BAR_AREA + 16 }}>
        {days.map((day, index) => (
          <div key={day.date} className="flex flex-1 flex-col items-center justify-end gap-1">
            <span
              className={`w-full rounded-t-[3px] ${index === 0 ? "bg-accent" : "bg-accent/40"}`}
              style={{ height: day.due > 0 ? Math.max((day.due / peak) * BAR_AREA, 4) : 1 }}
              title={`${day.date}: ${day.due}`}
            />
            <span className="h-[12px] text-[9px] leading-[12px] text-ink-3">
              {index % 2 === 0 ? new Date(day.date).getDate() : ""}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

/**
 * Słowa, które wracają jako pomyłka najczęściej.
 *
 * Lista jest krótka i ma prowadzić do działania, nie do zawstydzenia — stąd
 * przejście prosto do pozycji, gdzie da się ją zawiesić albo zacząć od zera.
 */
function HardestWords() {
  const query = useQuery({
    queryKey: ["hardest"],
    queryFn: () => api.get<{ items: HardItem[] }>("/api/stats/hardest?limit=8"),
    retry: false,
  });
  const items = query.data?.items ?? [];
  if (items.length === 0) return null;

  return (
    <div className="mt-3">
      <Label className="mb-2">Idzie najgorzej</Label>
      <div className="grid gap-2">
        {items.map((item) => (
          <Link
            key={item.item_id}
            to={`/slownik/${item.item_id}`}
            className="flex items-center gap-3 rounded-2xl border border-line bg-surface px-3.5 py-2.5 transition hover:border-accent-line"
          >
            <div className="min-w-0 flex-1">
              <div className="pt truncate text-[16px] leading-tight">{item.pt}</div>
              <div className="truncate text-[12.5px] text-ink-2">{item.pl}</div>
            </div>
            <div className="flex-none text-right">
              <div
                className={`text-[15px] font-bold tnum ${
                  item.accuracy < 50 ? "text-bad" : "text-warm"
                }`}
              >
                {item.accuracy}%
              </div>
              <div className="text-[10.5px] text-ink-3 tnum">
                {item.misses} z {item.attempts}
              </div>
            </div>
          </Link>
        ))}
      </div>
      <p className="mt-2 text-[11.5px] text-ink-3">
        Wejdź w pozycję, żeby ją zawiesić albo zacząć jej naukę od zera.
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

function Row({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-ink-2">{label}</span>
      <span className="tnum">{value}</span>
    </div>
  );
}
