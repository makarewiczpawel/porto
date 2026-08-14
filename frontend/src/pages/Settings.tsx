import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import type {
  AiUsage,
  AudioCoverage,
  AudioUsage,
  Mode,
  Settings,
  SynthesizeBatch,
  Voice,
} from "@/api/types";
import { playRecording, unlockAudio } from "@/api/speech";
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
  {
    id: "translate_ai",
    label: "Przetłumacz zdanie",
    hint: "ocenia AI — każda odpowiedź kosztuje i trwa kilka sekund",
  },
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

      <Label className="mb-2 mt-5">AI</Label>
      <AiSettings />

      <Label className="mb-2 mt-5">Kopia zapasowa</Label>
      <Backup />

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
        Nauka działa też bez zasięgu — postęp dosyła się, gdy połączenie wróci.
      </p>
    </div>
  );
}

/** Zużycie budżetu AI w bieżącym miesiącu — jedyne miejsce, gdzie widać koszt. */
function AiSettings() {
  const usage = useQuery({
    queryKey: ["ai-usage"],
    queryFn: () => api.get<AiUsage>("/api/ai/usage"),
    retry: false,
  });

  if (usage.isLoading) return <Card><Spinner label="Sprawdzam…" /></Card>;
  if (!usage.data) return null;
  const data = usage.data;

  if (!data.configured) {
    return (
      <Card>
        <p className="text-[12px] text-ink-2">
          Funkcje AI są wyłączone — brakuje klucza do modelu. Nie ma wtedy generowania zestawów,
          przycisku „dlaczego źle?" ani trybu „przetłumacz zdanie"; reszta aplikacji działa
          normalnie.
        </p>
      </Card>
    );
  }

  const ratio = data.budget_usd > 0 ? Math.min(data.spent_usd / data.budget_usd, 1) : 0;
  return (
    <Card className="grid gap-2">
      <div className="flex items-baseline justify-between text-[13px]">
        <span>Wydane w tym miesiącu</span>
        <b className="tnum">
          {data.spent_usd.toFixed(2)} / {data.budget_usd.toFixed(2)} USD
        </b>
      </div>
      <div className="h-[6px] overflow-hidden rounded-full bg-surface-3">
        <div
          className={`h-full rounded-full ${data.over_budget ? "bg-bad" : "bg-accent"}`}
          style={{ width: `${ratio * 100}%` }}
        />
      </div>
      <div className="text-[11.5px] text-ink-3">
        Model: {data.model} · wywołań: {data.calls_this_month}.{" "}
        {data.over_budget
          ? "Budżet wyczerpany — funkcje AI wrócą pierwszego dnia miesiąca."
          : "Po wyczerpaniu budżetu funkcje AI się wyłączają, a nauka działa dalej."}
      </div>
    </Card>
  );
}

/**
 * Eksport bazy do pliku.
 *
 * CSV wychodzi w formacie, który przyjmuje import — plik stąd wraca tam bez
 * żadnej obróbki, więc to jest realna kopia zapasowa, a nie raport do
 * oglądania. JSON dokłada zdania przykładowe i przypisanie do talii, których
 * w jednej tabelce nie da się zmieścić bez wymyślania własnej składni.
 */
function Backup() {
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  async function download(format: "csv" | "json") {
    setBusy(format);
    setProblem(null);
    try {
      const blob = await api.blob(`/api/items/export?format=${format}&mine_only=false`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `porto-${new Date().toISOString().slice(0, 10)}.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setProblem(caught instanceof Error ? caught.message : "Nie udało się pobrać pliku.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="grid gap-2">
      <p className="text-[12.5px] text-ink-2">
        Cały słownik w jednym pliku. CSV otwiera się w arkuszu i wraca przez import bez
        przeróbek; JSON dodatkowo zachowuje zdania przykładowe i talie.
      </p>
      <div className="flex gap-2">
        <Button variant="ghost" size="sm" onClick={() => void download("csv")} disabled={busy !== null}>
          {busy === "csv" ? "Pobieram…" : "Pobierz CSV"}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => void download("json")} disabled={busy !== null}>
          {busy === "json" ? "Pobieram…" : "Pobierz JSON"}
        </Button>
      </div>
      {problem && <p className="text-[12px] text-bad">{problem}</p>}
    </Card>
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
 * Wymowa: wybór głosu, odsłuchanie go przed decyzją i stan biblioteki nagrań.
 *
 * Dwie rzeczy, których wcześniej tu brakowało, a bez których ten ekran wprowadzał
 * w błąd.
 *
 * Po pierwsze, **głosu nie da się ocenić z nazwy**. „Wavenet-B" nic nie znaczy,
 * dopóki się go nie usłyszy, a wybranie złego kosztuje całą bibliotekę nagraną
 * od nowa. Teraz każdy głos można przesłuchać na jednym zdaniu, zanim się go
 * ustawi.
 *
 * Po drugie, **zmiana głosu nie przerabia istniejących nagrań** — one są
 * kluczowane jego nazwą, więc po zmianie aplikacja nie znajduje żadnego i po
 * cichu schodzi na głos wbudowany w telefon. Ten brzmi sztucznie i nie reaguje
 * na tutejsze ustawienia, więc wygląda to jak „zmiana nic nie dała". Licznik
 * pokrycia mówi teraz wprost, ile nagrań istnieje, a przycisk obok dogrywa
 * resztę — bez wchodzenia do konsoli serwera.
 */
function VoiceSettings({
  settings,
  patch,
}: {
  settings: Settings;
  patch: (body: Partial<Settings>) => Promise<void>;
}) {
  const queryClient = useQueryClient();
  const [choice, setChoice] = useState(settings.tts_voice);
  const [playing, setPlaying] = useState(false);
  const [note, setNote] = useState<string | null>(null);

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
  const chosen = available.find((voice) => voice.name === choice);

  async function preview() {
    setNote(null);
    setPlaying(true);
    unlockAudio();
    try {
      const sample = await api.post<{ url: string }>(
        `/api/audio/sample?voice=${encodeURIComponent(choice)}`,
      );
      await playRecording(sample.url);
      void usage.refetch();
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "Nie udało się odtworzyć próbki.");
    } finally {
      setPlaying(false);
    }
  }

  async function useThisVoice() {
    await patch({ tts_voice: choice });
    queryClient.invalidateQueries({ queryKey: ["audio-coverage"] });
  }

  return (
    <>
      <Card className="grid gap-3">
        {!configured && (
          <p className="rounded-xl border border-line bg-surface-2 px-3 py-2 text-[12px] text-ink-2">
            {usage.data && usage.data.clips_stored > 0
              ? "Brakuje klucza do syntezy mowy, więc nowe nagrania nie powstaną. Te już zapisane działają normalnie."
              : "Nagrania nie są jeszcze włączone — brakuje klucza do syntezy mowy. Do tego czasu aplikacja czyta portugalski głosem wbudowanym w telefon, o ile ma zainstalowany europejski."}
          </p>
        )}

        {available.length > 0 && (
          <>
            <label className="grid gap-1.5">
              <span className="text-[14px]">Głos</span>
              <select
                value={choice}
                onChange={(event) => setChoice(event.target.value)}
                className="rounded-xl border border-line-strong bg-surface px-3 py-2.5 text-[14px]"
              >
                {available.some((voice) => voice.name === choice) ? null : (
                  <option value={choice}>{choice} (niedostępny)</option>
                )}
                {available.map((voice) => (
                  <option key={voice.name} value={voice.name}>
                    {voice.name.replace("pt-PT-", "")}
                    {voice.gender === "female" ? " · kobiecy" : voice.gender === "male" ? " · męski" : ""}
                    {" · "}
                    {qualityLabel(voice.quality)}
                  </option>
                ))}
              </select>
            </label>

            {chosen?.quality === "standard" && (
              <p className="rounded-xl border border-warm/40 bg-warm/10 px-3 py-2 text-[12px] text-ink-2">
                To głos podstawowy — brzmi wyraźnie syntetycznie. Głosy oznaczone jako
                naturalne są nagrane inaczej i słychać różnicę od pierwszego słowa.
              </p>
            )}

            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => void preview()} disabled={playing}>
                {playing ? "Odtwarzam…" : "▶ Posłuchaj"}
              </Button>
              {choice !== settings.tts_voice && (
                <Button size="sm" onClick={() => void useThisVoice()}>
                  Ustaw ten głos
                </Button>
              )}
            </div>
            {note && <p className="text-[12px] text-bad">{note}</p>}
            <span className="text-[11.5px] text-ink-3">
              Próbka to jedno zdanie — kosztuje ułamek grosza i zostaje zapamiętana.
            </span>
          </>
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

      {configured && <Library voice={settings.tts_voice} />}
    </>
  );
}

function qualityLabel(quality: string): string {
  if (quality === "standard") return "podstawowy";
  if (quality === "chirp") return "naturalny (najlepszy)";
  return `naturalny (${quality})`;
}

/**
 * Ile z biblioteki jest nagrane tym głosem — i przycisk, który dogrywa resztę.
 *
 * To jest odpowiedź na najbardziej mylące zachowanie całej aplikacji: brak
 * nagrania nie jest błędem, więc nic o nim nie mówiło. Aplikacja po prostu
 * czytała głosem telefonu, a użytkownik widział „wymowa brzmi źle i zmiana
 * ustawień nic nie daje".
 */
function Library({ voice }: { voice: string }) {
  const queryClient = useQueryClient();
  const [running, setRunning] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const coverage = useQuery({
    queryKey: ["audio-coverage", voice],
    queryFn: () => api.get<AudioCoverage>("/api/audio/coverage"),
    retry: false,
  });

  async function fillIn() {
    setRunning(true);
    setProblem(null);
    try {
      // Porcjami, bo całość to kilkaset wywołań i kilka minut — dłużej, niż
      // powinno wisieć jedno żądanie. Pętla kończy się sama, gdy nie ma już
      // czego nagrywać albo gdy serwer mówi, że dalej nie warto próbować.
      for (;;) {
        const batch = await api.post<SynthesizeBatch>("/api/audio/synthesize-missing", {
          limit: 40,
        });
        await coverage.refetch();
        if (batch.error) {
          setProblem(batch.error);
          break;
        }
        if (batch.remaining === 0 || batch.done === 0) break;
      }
      queryClient.invalidateQueries({ queryKey: ["tts-usage"] });
      queryClient.invalidateQueries({ queryKey: ["items"] });
      queryClient.invalidateQueries({ queryKey: ["deck"] });
    } catch (caught) {
      setProblem(caught instanceof Error ? caught.message : "Nagrywanie się nie udało.");
    } finally {
      setRunning(false);
    }
  }

  if (!coverage.data) return null;
  const data = coverage.data;
  const ratio = data.planned > 0 ? data.present / data.planned : 0;

  return (
    <Card className="mt-3 grid gap-2">
      <div className="flex items-baseline justify-between text-[13px]">
        <span>Nagrania dla tego głosu</span>
        <b className="tnum">
          {data.present} / {data.planned}
        </b>
      </div>
      <div className="h-[6px] overflow-hidden rounded-full bg-surface-3">
        <div
          className={`h-full rounded-full transition-[width] duration-500 ${
            data.complete ? "bg-good" : "bg-accent"
          }`}
          style={{ width: `${ratio * 100}%` }}
        />
      </div>

      {data.present === 0 ? (
        <p className="rounded-xl border border-warm/40 bg-warm/10 px-3 py-2 text-[12px] text-ink-2">
          Dla tego głosu nie ma jeszcze <b>żadnego</b> nagrania. Aplikacja czyta wtedy głosem
          wbudowanym w telefon — ten brzmi sztucznie i nie zmienia się razem z ustawieniem
          powyżej. Nagraj bibliotekę, żeby usłyszeć wybrany głos.
        </p>
      ) : data.complete ? (
        <p className="text-[11.5px] text-ink-3">
          Komplet. Każde słowo i zdanie ma wymowę w tym głosie.
        </p>
      ) : (
        <p className="text-[11.5px] text-ink-3">
          Brakujące pozycje czyta na razie głos telefonu. Nagranie {data.missing} sztuk zajmie
          około {Math.max(1, Math.round((data.missing * 0.4) / 60))} min.
        </p>
      )}

      {problem && <p className="text-[12px] text-bad">{problem}</p>}

      {!data.complete && (
        <Button size="sm" onClick={() => void fillIn()} disabled={running}>
          {running ? `Nagrywam… zostało ${data.missing}` : `Nagraj brakujące (${data.missing})`}
        </Button>
      )}
    </Card>
  );
}
