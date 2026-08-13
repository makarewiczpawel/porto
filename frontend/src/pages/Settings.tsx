import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import type { AudioUsage, Mode, Settings, Voice } from "@/api/types";
import { Button, Card, Label, Spinner } from "@/components/ui";
import { useAuth } from "@/store/auth";

/** Every mode the app can ask a question in, with what it actually drills. */
const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: "flashcard", label: "Fiszki", hint: "pokaż i oceń się sam" },
  { id: "mcq_pt_pl", label: "Wybór PT→PL", hint: "rozpoznawanie" },
  { id: "mcq_pl_pt", label: "Wybór PL→PT", hint: "produkcja z podpowiedzią" },
  { id: "typing", label: "Wpisywanie z pamięci", hint: "produkcja bez podpowiedzi" },
  { id: "cloze", label: "Luka w zdaniu", hint: "słowo w kontekście" },
  { id: "word_bank", label: "Rozsypanka", hint: "szyk zdania" },
  { id: "matching", label: "Dopasowywanie par", hint: "rozgrzewka na start sesji" },
  { id: "listening", label: "Ze słuchu", hint: "wymaga nagrania — bez niego pomijany" },
];

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

      <Label className="mb-2 mt-5">Tryby ćwiczeń</Label>
      <Card className="grid gap-0 py-1">
        {MODES.map((mode, index) => {
          const on = settings.enabled_modes.includes(mode.id);
          const last = index === MODES.length - 1;
          return (
            <div
              key={mode.id}
              className={`flex items-center justify-between gap-3 py-3 ${last ? "" : "border-b border-line"}`}
            >
              <div>
                <div className="text-[14px]">{mode.label}</div>
                <div className="text-[11.5px] text-ink-3">{mode.hint}</div>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={on}
                aria-label={mode.label}
                disabled={on && settings.enabled_modes.length === 1}
                onClick={() =>
                  patch({
                    enabled_modes: on
                      ? settings.enabled_modes.filter((m) => m !== mode.id)
                      : [...settings.enabled_modes, mode.id],
                  })
                }
                className={`relative h-[25px] w-[42px] flex-none rounded-full transition disabled:opacity-40 ${
                  on ? "bg-accent" : "bg-line-strong"
                }`}
              >
                <span
                  className={`absolute top-[3px] h-[19px] w-[19px] rounded-full bg-white transition-all ${
                    on ? "left-[20px]" : "left-[3px]"
                  }`}
                />
              </button>
            </div>
          );
        })}
      </Card>
      <p className="mt-2 text-[11.5px] text-ink-3">
        Wyłączony tryb nie zniknie z historii — po prostu nie pojawi się w nowych sesjach.
        Ostatniego włączonego trybu nie da się wyłączyć.
      </p>

      <Label className="mb-2 mt-5">Ocena odpowiedzi</Label>
      <Card>
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-[14px]">Brak akcentu to błąd</div>
            <div className="text-[11.5px] text-ink-3">
              domyślnie „avo" zamiast „avó" liczy się jako trudne, nie jako pomyłka
            </div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={settings.accent_strict}
            aria-label="Brak akcentu to błąd"
            onClick={() => patch({ accent_strict: !settings.accent_strict })}
            className={`relative h-[25px] w-[42px] flex-none rounded-full transition ${
              settings.accent_strict ? "bg-accent" : "bg-line-strong"
            }`}
          >
            <span
              className={`absolute top-[3px] h-[19px] w-[19px] rounded-full bg-white transition-all ${
                settings.accent_strict ? "left-[20px]" : "left-[3px]"
              }`}
            />
          </button>
        </div>
      </Card>

      <Label className="mb-2 mt-5">Wymowa</Label>
      <VoiceSettings settings={settings} patch={patch} />

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

      <p className="mt-6 text-center text-[11.5px] text-ink-3">Tryb offline dochodzi w fazie 3.</p>
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

/**
 * Wymowa: wybór głosu, tempo, autoodtwarzanie i stan biblioteki nagrań.
 *
 * Lista głosów przychodzi prosto od dostawcy, a nie z listy wpisanej na sztywno
 * w kodzie — dzięki temu nie da się wybrać głosu, którego nie ma, i nie trzeba
 * aktualizować aplikacji, gdy dojdą nowe.
 */
function VoiceSettings({
  settings,
  patch,
}: {
  settings: Settings;
  patch: (body: Partial<Settings>) => Promise<void>;
}) {
  const voices = useQuery({
    queryKey: ["tts-voices"],
    queryFn: () => api.get<{ configured: boolean; voices: Voice[] }>("/api/audio/voices"),
    staleTime: 60 * 60 * 1000,
    retry: false,
  });
  const usage = useQuery({
    queryKey: ["tts-usage"],
    queryFn: () => api.get<AudioUsage>("/api/audio/usage"),
    retry: false,
  });

  const available = voices.data?.voices ?? [];
  const configured = voices.data?.configured ?? false;

  return (
    <Card className="grid gap-3">
      {!configured && (
        <p className="rounded-xl border border-line bg-surface-2 px-3 py-2 text-[12px] text-ink-2">
          {usage.data && usage.data.clips_stored > 0
            ? "Brakuje klucza do syntezy mowy, więc nowe nagrania nie powstaną. Te już zapisane działają normalnie."
            : "Nagrania nie są jeszcze włączone — brakuje klucza do syntezy mowy. Do tego czasu aplikacja czyta portugalski głosem wbudowanym w telefon, o ile ma zainstalowany europejski."}
        </p>
      )}

      {available.length > 0 && (
        <label className="grid gap-1.5">
          <span className="text-[14px]">Głos</span>
          <select
            value={settings.tts_voice}
            onChange={(event) => void patch({ tts_voice: event.target.value })}
            className="rounded-xl border border-line-strong bg-surface px-3 py-2.5 text-[14px]"
          >
            {available.some((voice) => voice.name === settings.tts_voice) ? null : (
              <option value={settings.tts_voice}>{settings.tts_voice} (niedostępny)</option>
            )}
            {available.map((voice) => (
              <option key={voice.name} value={voice.name}>
                {voice.name.replace("pt-PT-", "")}
                {voice.gender === "female" ? " · kobiecy" : voice.gender === "male" ? " · męski" : ""}
                {voice.quality === "standard" ? " · podstawowy" : ""}
              </option>
            ))}
          </select>
          <span className="text-[11.5px] text-ink-3">
            Zmiana głosu nie kasuje nagrań — nowe powstaną przy następnej syntezie.
          </span>
        </label>
      )}

      <div className="flex items-center justify-between gap-3 border-t border-line pt-3">
        <div>
          <div className="text-[14px]">Odtwarzaj automatycznie</div>
          <div className="text-[11.5px] text-ink-3">wymowa odzywa się, gdy pojawia się portugalski</div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={settings.autoplay_audio}
          aria-label="Odtwarzaj automatycznie"
          onClick={() => void patch({ autoplay_audio: !settings.autoplay_audio })}
          className={`relative h-[25px] w-[42px] flex-none rounded-full transition ${
            settings.autoplay_audio ? "bg-accent" : "bg-line-strong"
          }`}
        >
          <span
            className={`absolute top-[3px] h-[19px] w-[19px] rounded-full bg-white transition-all ${
              settings.autoplay_audio ? "left-[20px]" : "left-[3px]"
            }`}
          />
        </button>
      </div>

      {usage.data && (
        <div className="border-t border-line pt-3 text-[11.5px] text-ink-3">
          Nagrań w bazie: <b className="text-ink-2">{usage.data.clips_stored}</b> (
          {(usage.data.bytes_stored / 1_048_576).toFixed(1)} MB). W tym miesiącu zsyntezowano{" "}
          {usage.data.chars_this_month.toLocaleString("pl")} z {usage.data.monthly_limit.toLocaleString("pl")}{" "}
          znaków.
        </div>
      )}
    </Card>
  );
}
