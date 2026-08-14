import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { ApiError, api } from "@/api/client";
import type { AiAccepted, AiGeneration, AiProposal, AiUsage } from "@/api/types";
import { Button, Card, ErrorNote, Label, plural } from "@/components/ui";

const LEVELS = ["A1", "A2", "B1", "B2", "C1"];
const COUNTS = [10, 15, 20, 30];

const EXAMPLES = [
  "20 zwrotów u lekarza",
  "słownictwo z kuchni",
  "rozmowa w kawiarni",
  "zwroty na lotnisku",
];

/**
 * Generowanie zestawu i jego przegląd — dwa ekrany, jedna droga.
 *
 * Reguła całej fazy 4 rządzi tym komponentem: **nic z modelu nie wchodzi do
 * słownika bez zaznaczenia**. Propozycje przychodzą odznaczalne i edytowalne,
 * a przycisk zapisu mówi wprost, ilu pozycji dotyczy. Poprawka wpisana w
 * przeglądzie jest tym, co trafia do bazy — nie oryginał od modelu.
 */
export function GenerateSet() {
  const [topic, setTopic] = useState("");
  const [count, setCount] = useState(15);
  const [level, setLevel] = useState("A2");
  const [generated, setGenerated] = useState<AiGeneration | null>(null);
  const [error, setError] = useState<string | null>(null);

  const usage = useQuery({
    queryKey: ["ai-usage"],
    queryFn: () => api.get<AiUsage>("/api/ai/usage"),
    retry: false,
  });

  const run = useMutation({
    mutationFn: () =>
      api.post<AiGeneration>("/api/ai/generate", { topic: topic.trim(), count, level }),
    onSuccess: (result) => {
      setGenerated(result);
      void usage.refetch();
    },
    onError: (caught) =>
      setError(caught instanceof Error ? caught.message : "Nie udało się wygenerować zestawu."),
  });

  if (generated) {
    return (
      <Review
        generation={generated}
        onBack={() => {
          setGenerated(null);
          setError(null);
        }}
      />
    );
  }

  if (usage.data && !usage.data.configured) {
    return (
      <Card>
        <p className="text-[13.5px] text-ink-2">
          Generowanie zestawów jest wyłączone — brakuje klucza do modelu. Reszta aplikacji działa
          normalnie; słówka możesz dodawać ręcznie albo importem listy.
        </p>
      </Card>
    );
  }

  return (
    <div className="grid gap-3">
      <Card className="grid gap-3">
        <label className="grid gap-1.5">
          <span className="text-[13px] font-semibold">O czym mają być słówka</span>
          <span className="text-[11.5px] text-ink-3">
            Zwykłym zdaniem, po polsku. Im konkretniej, tym lepszy zestaw.
          </span>
          <input
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            placeholder="np. wizyta u lekarza"
            className="rounded-xl border border-line-strong bg-surface px-3 py-2.5 text-[15px]"
          />
        </label>

        <div className="flex flex-wrap gap-1.5">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => setTopic(example)}
              className="rounded-full border border-line bg-surface-2 px-2.5 py-1 text-[11.5px] text-ink-2"
            >
              {example}
            </button>
          ))}
        </div>

        <label className="grid gap-1.5">
          <span className="text-[13px] font-semibold">Ile pozycji</span>
          <div className="flex gap-2">
            {COUNTS.map((option) => (
              <Chip key={option} on={count === option} onClick={() => setCount(option)}>
                {option}
              </Chip>
            ))}
          </div>
        </label>

        <label className="grid gap-1.5">
          <span className="text-[13px] font-semibold">Poziom</span>
          <div className="flex gap-2">
            {LEVELS.map((option) => (
              <Chip key={option} on={level === option} onClick={() => setLevel(option)}>
                {option}
              </Chip>
            ))}
          </div>
        </label>
      </Card>

      {error && <ErrorNote>{error}</ErrorNote>}

      <Button
        onClick={() => {
          setError(null);
          run.mutate();
        }}
        disabled={topic.trim().length < 3 || run.isPending}
      >
        {run.isPending ? "Układam zestaw…" : "Wygeneruj propozycje"}
      </Button>

      <p className="text-center text-[11.5px] text-ink-3">
        {run.isPending
          ? "To trwa kilkanaście sekund — model sprawdza każdą pozycję pod kątem wariantu europejskiego."
          : "Nic nie trafi do słownika, dopóki tego nie zatwierdzisz."}
      </p>

      {usage.data?.configured && <Budget usage={usage.data} />}
    </div>
  );
}

/** Przegląd: co wchodzi, w jakim brzmieniu i do której talii. */
function Review({ generation, onBack }: { generation: AiGeneration; onBack: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [items, setItems] = useState<AiProposal[]>(generation.proposals);
  const [chosen, setChosen] = useState<Set<number>>(
    () => new Set(generation.proposals.map((_, index) => index)),
  );
  const [deckName, setDeckName] = useState(generation.deck_name);
  const [open, setOpen] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () =>
      api.post<AiAccepted>(`/api/ai/jobs/${generation.job_id}/accept`, {
        deck_name: deckName.trim() || generation.deck_name,
        items: items.filter((_, index) => chosen.has(index)),
      }),
    onSuccess: (result) => {
      for (const key of ["items", "decks", "queue-summary", "ai-usage"]) {
        queryClient.invalidateQueries({ queryKey: [key] });
      }
      navigate(`/talie/${result.deck_id}`);
    },
    onError: (caught) => {
      if (caught instanceof ApiError && caught.code === "AI_JOB_NOT_FOUND") {
        setError("Ten zestaw wygasł. Wygeneruj go jeszcze raz.");
        return;
      }
      setError(caught instanceof Error ? caught.message : "Nie udało się zapisać.");
    },
  });

  function update(index: number, patch: Partial<AiProposal>) {
    setItems((current) =>
      current.map((entry, position) => (position === index ? { ...entry, ...patch } : entry)),
    );
  }

  function toggle(index: number) {
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  if (items.length === 0) {
    return (
      <div className="grid gap-3">
        <Card>
          <p className="text-[13.5px] text-ink-2">
            Wszystkie propozycje już masz w słowniku. Spróbuj węższego tematu albo wyższego poziomu.
          </p>
        </Card>
        <Button variant="ghost" onClick={onBack}>
          Wróć do generowania
        </Button>
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      <Card className="grid gap-2">
        <div className="flex items-baseline justify-between gap-2">
          <Label>Do przejrzenia</Label>
          <span className="text-[11.5px] text-ink-3">
            zaznaczone: <b className="text-ink-2 tnum">{chosen.size}</b> z {items.length}
          </span>
        </div>
        {generation.skipped_duplicates > 0 && (
          <p className="text-[11.5px] text-ink-3">
            Pominięto {generation.skipped_duplicates}{" "}
            {plural(generation.skipped_duplicates, "pozycję, którą", "pozycje, które", "pozycji, które")}{" "}
            już masz.
          </p>
        )}
        <div className="flex gap-2 pt-0.5">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setChosen(new Set(items.map((_, index) => index)))}
          >
            Zaznacz wszystko
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setChosen(new Set())}>
            Odznacz wszystko
          </Button>
        </div>
      </Card>

      <div className="grid gap-2">
        {items.map((entry, index) => {
          const on = chosen.has(index);
          const expanded = open === index;
          return (
            <div
              key={index}
              className={`rounded-2xl border bg-surface transition ${
                on ? "border-accent-line" : "border-line opacity-60"
              }`}
            >
              <div className="flex items-start gap-3 p-3">
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={on}
                  aria-label={`${entry.pt} — ${entry.pl}`}
                  onClick={() => toggle(index)}
                  className={`mt-0.5 grid h-[22px] w-[22px] flex-none place-content-center rounded-md border text-[13px] font-bold ${
                    on ? "border-accent bg-accent text-accent-ink" : "border-line-strong bg-surface"
                  }`}
                >
                  {on ? "✓" : ""}
                </button>
                <button
                  type="button"
                  onClick={() => setOpen(expanded ? null : index)}
                  className="grid flex-1 gap-0.5 text-left"
                >
                  <span className="pt text-[16px]">
                    {entry.article ? `${entry.article} ` : ""}
                    {entry.pt}
                  </span>
                  <span className="text-[13px] text-ink-2">{entry.pl}</span>
                  {entry.example_pt && !expanded && (
                    <span className="pt truncate text-[12px] text-ink-3">{entry.example_pt}</span>
                  )}
                </button>
                <span className="flex-none text-[11px] text-ink-3">{entry.cefr_level}</span>
              </div>

              {expanded && (
                <div className="grid gap-2.5 border-t border-line px-3 py-3">
                  <Inline
                    label="Po portugalsku"
                    value={entry.pt}
                    lang="pt"
                    onChange={(pt) => update(index, { pt })}
                  />
                  <Inline
                    label="Po polsku"
                    value={entry.pl}
                    onChange={(pl) => update(index, { pl })}
                  />
                  <Inline
                    label="Zdanie przykładowe"
                    value={entry.example_pt ?? ""}
                    lang="pt"
                    onChange={(example_pt) => update(index, { example_pt })}
                  />
                  <Inline
                    label="Tłumaczenie zdania"
                    value={entry.example_pl ?? ""}
                    onChange={(example_pl) => update(index, { example_pl })}
                  />
                  <Inline
                    label="Notatka"
                    value={entry.notes ?? ""}
                    onChange={(notes) => update(index, { notes })}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <Card className="grid gap-1.5">
        <span className="text-[13px] font-semibold">Nazwa talii</span>
        <input
          value={deckName}
          onChange={(event) => setDeckName(event.target.value)}
          className="rounded-xl border border-line-strong bg-surface px-3 py-2.5 text-[14px]"
        />
      </Card>

      {error && <ErrorNote>{error}</ErrorNote>}

      <Button onClick={() => save.mutate()} disabled={chosen.size === 0 || save.isPending}>
        {save.isPending
          ? "Zapisuję…"
          : `Zatwierdź zaznaczone (${chosen.size})`}
      </Button>
      <Button variant="quiet" onClick={onBack}>
        Odrzuć i zacznij od nowa
      </Button>
    </div>
  );
}

function Budget({ usage }: { usage: AiUsage }) {
  const ratio = usage.budget_usd > 0 ? Math.min(usage.spent_usd / usage.budget_usd, 1) : 0;
  return (
    <div className="grid gap-1.5 rounded-xl border border-line bg-surface-2 px-3 py-2.5">
      <div className="flex items-baseline justify-between text-[11.5px] text-ink-3">
        <span>Budżet AI w tym miesiącu</span>
        <span className="tnum">
          {usage.spent_usd.toFixed(2)} / {usage.budget_usd.toFixed(2)} USD
        </span>
      </div>
      <div className="h-[5px] overflow-hidden rounded-full bg-surface-3">
        <div
          className={`h-full rounded-full ${usage.over_budget ? "bg-bad" : "bg-accent"}`}
          style={{ width: `${ratio * 100}%` }}
        />
      </div>
    </div>
  );
}

function Chip({
  on,
  onClick,
  children,
}: {
  on: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-1.5 text-[12.5px] font-semibold ${
        on ? "border-accent bg-accent-soft text-accent" : "border-line bg-surface text-ink-2"
      }`}
    >
      {children}
    </button>
  );
}

function Inline({
  label,
  value,
  lang,
  onChange,
}: {
  label: string;
  value: string;
  lang?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1">
      <span className="text-[11.5px] font-semibold text-ink-3">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        lang={lang}
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        className={`rounded-lg border border-line-strong bg-surface px-2.5 py-2 text-[14px] ${
          lang === "pt" ? "pt" : ""
        }`}
      />
    </label>
  );
}
