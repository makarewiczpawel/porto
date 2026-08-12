import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import type { Settings } from "@/api/types";
import { Button, Card, Label, Spinner } from "@/components/ui";
import { useAuth } from "@/store/auth";

export function SettingsPage() {
  const { user, logout, refreshMe } = useAuth();
  const queryClient = useQueryClient();

  const query = useQuery({ queryKey: ["settings"], queryFn: () => api.get<Settings>("/api/settings") });

  async function patch(body: Partial<Settings>) {
    await api.patch<Settings>("/api/settings", body);
    await refreshMe();
    queryClient.invalidateQueries({ queryKey: ["settings"] });
    queryClient.invalidateQueries({ queryKey: ["queue-summary"] });
  }

  if (query.isLoading || !query.data) return <Spinner />;
  const settings = query.data;

  return (
    <div className="px-4 pt-4">
      <Link to="/" className="mb-3 inline-flex items-center gap-1.5 text-sm text-ink-2">
        <span aria-hidden="true">←</span> Dziś
      </Link>
      <h1 className="pt mb-4 text-2xl">Ustawienia</h1>

      <Label className="mb-2">Nauka</Label>
      <Card className="grid gap-0 py-1">
        <Stepper
          label="Cel dzienny"
          hint="kart potrzebnych do zaliczenia dnia"
          value={settings.daily_goal}
          step={5}
          min={5}
          max={200}
          onChange={(daily_goal) => patch({ daily_goal })}
        />
        <Stepper
          label="Nowe pozycje dziennie"
          hint="liczone jako słowa, nie karty"
          value={settings.new_per_day}
          step={5}
          min={0}
          max={50}
          onChange={(new_per_day) => patch({ new_per_day })}
        />
        <Stepper
          label="Limit powtórek w sesji"
          hint="chroni przed nawisem po przerwie"
          value={settings.review_limit}
          step={20}
          min={20}
          max={300}
          onChange={(review_limit) => patch({ review_limit })}
        />
        <Stepper
          label="Docelowa retencja"
          hint="parametr FSRS — wyżej = częstsze powtórki"
          value={settings.desired_retention}
          step={0.05}
          min={0.7}
          max={0.95}
          format={(value) => value.toFixed(2).replace(".", ",")}
          onChange={(desired_retention) => patch({ desired_retention: Number(desired_retention.toFixed(2)) })}
          last
        />
      </Card>

      <Label className="mb-2 mt-5">Konto</Label>
      <Card className="grid gap-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-[14px]">{user?.display_name}</div>
            <div className="text-[11.5px] text-ink-3">{user?.email}</div>
          </div>
          <span className="text-[11.5px] text-ink-3">{user?.timezone}</span>
        </div>
        <Button variant="ghost" onClick={logout}>
          Wyloguj się
        </Button>
      </Card>

      <p className="mt-6 text-center text-[11.5px] text-ink-3">
        Tryby ćwiczeń, wymowa i tryb offline dochodzą w kolejnych fazach.
      </p>
    </div>
  );
}

function Stepper({
  label,
  hint,
  value,
  step,
  min,
  max,
  onChange,
  format,
  last,
}: {
  label: string;
  hint: string;
  value: number;
  step: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
  format?: (value: number) => string;
  last?: boolean;
}) {
  const clamp = (next: number) => Math.min(Math.max(next, min), max);
  return (
    <div
      className={`flex items-center justify-between gap-3 py-3 ${last ? "" : "border-b border-line"}`}
    >
      <div>
        <div className="text-[14px]">{label}</div>
        <div className="text-[11.5px] text-ink-3">{hint}</div>
      </div>
      <div className="flex flex-none items-center gap-2.5">
        <button
          type="button"
          aria-label={`Zmniejsz: ${label}`}
          onClick={() => onChange(clamp(value - step))}
          disabled={value <= min}
          className="h-8 w-8 rounded-full border border-line bg-surface-2 disabled:opacity-40"
        >
          −
        </button>
        <b className="min-w-[3ch] text-center text-[15px] tnum">{format ? format(value) : value}</b>
        <button
          type="button"
          aria-label={`Zwiększ: ${label}`}
          onClick={() => onChange(clamp(value + step))}
          disabled={value >= max}
          className="h-8 w-8 rounded-full border border-line bg-surface-2 disabled:opacity-40"
        >
          +
        </button>
      </div>
    </div>
  );
}
