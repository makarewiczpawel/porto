import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, api } from "@/api/client";
import type { Deck, ImportResult, ItemDetail } from "@/api/types";
import { Button, Card, ErrorNote, Label, plural } from "@/components/ui";
import { GenerateSet } from "./AiGenerate";

const LEVELS = ["A1", "A2", "B1", "B2", "C1"];

/** Trzy drogi do tego samego: jedno słowo, gotowa lista albo zestaw z AI. */
export function AddItemPage() {
  const [tab, setTab] = useState<"one" | "many" | "ai">("one");

  return (
    <div className="px-4 pt-4">
      <Link to="/slownik" className="mb-3 inline-flex items-center gap-1.5 text-sm text-ink-2">
        <span aria-hidden="true">←</span> Słownik
      </Link>
      <h1 className="pt mb-4 text-2xl">Dodaj słówka</h1>

      <div className="mb-4 grid grid-cols-3 gap-2">
        {(
          [
            ["one", "Pojedyncze"],
            ["many", "Import listy"],
            ["ai", "Wygeneruj"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`rounded-xl border px-3 py-2 text-[13.5px] font-semibold transition ${
              tab === id
                ? "border-accent bg-accent-soft text-accent"
                : "border-line bg-surface text-ink-2"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "one" && <SingleItemForm />}
      {tab === "many" && <ImportForm />}
      {tab === "ai" && <GenerateSet />}
    </div>
  );
}

function useDecks() {
  return useQuery({ queryKey: ["decks"], queryFn: () => api.get<Deck[]>("/api/decks") });
}

function SingleItemForm() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const decks = useDecks();

  const [form, setForm] = useState({
    pt: "",
    pl: "",
    cefr_level: "A1",
    notes: "",
    example_pt: "",
    example_pl: "",
    deck_id: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () =>
      api.post<ItemDetail>("/api/items", {
        pt: form.pt,
        pl: form.pl,
        cefr_level: form.cefr_level,
        notes: form.notes || null,
        example_pt: form.example_pt || null,
        example_pl: form.example_pl || null,
        deck_id: form.deck_id || null,
      }),
    onSuccess: (item) => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
      queryClient.invalidateQueries({ queryKey: ["decks"] });
      queryClient.invalidateQueries({ queryKey: ["queue-summary"] });
      navigate(`/slownik/${item.id}`);
    },
    onError: (caught) => {
      if (caught instanceof ApiError && caught.code === "ITEM_EXISTS") {
        setDuplicate(String(caught.details.item_id ?? ""));
        setError("Taka pozycja już jest w słowniku.");
        return;
      }
      setError(caught instanceof Error ? caught.message : "Nie udało się zapisać.");
    },
  });

  const ready = form.pt.trim().length > 0 && form.pl.trim().length > 0;

  return (
    <form
      className="grid gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        setError(null);
        setDuplicate(null);
        if (ready) save.mutate();
      }}
    >
      <Card className="grid gap-3">
        <Field
          label="Po portugalsku"
          hint="rodzajnik możesz wpisać razem ze słowem — „a casa"
          value={form.pt}
          onChange={(pt) => setForm({ ...form, pt })}
          lang="pt"
        />
        <Field
          label="Po polsku"
          value={form.pl}
          onChange={(pl) => setForm({ ...form, pl })}
        />
        <label className="grid gap-1.5">
          <span className="text-[13px] font-semibold">Poziom</span>
          <div className="flex gap-2">
            {LEVELS.map((level) => (
              <button
                key={level}
                type="button"
                onClick={() => setForm({ ...form, cefr_level: level })}
                className={`rounded-full border px-3 py-1.5 text-[12.5px] font-semibold ${
                  form.cefr_level === level
                    ? "border-accent bg-accent-soft text-accent"
                    : "border-line bg-surface text-ink-2"
                }`}
              >
                {level}
              </button>
            ))}
          </div>
        </label>
      </Card>

      <Card className="grid gap-3">
        <Label>Nieobowiązkowe</Label>
        <Field
          label="Zdanie przykładowe (PT)"
          value={form.example_pt}
          onChange={(example_pt) => setForm({ ...form, example_pt })}
          lang="pt"
        />
        <Field
          label="Tłumaczenie zdania"
          value={form.example_pl}
          onChange={(example_pl) => setForm({ ...form, example_pl })}
        />
        <Field
          label="Notatka"
          hint="np. czym różni się od podobnego słowa"
          value={form.notes}
          onChange={(notes) => setForm({ ...form, notes })}
        />
        <label className="grid gap-1.5">
          <span className="text-[13px] font-semibold">Talia</span>
          <select
            value={form.deck_id}
            onChange={(event) => setForm({ ...form, deck_id: event.target.value })}
            className="rounded-xl border border-line-strong bg-surface px-3 py-2.5 text-[14px]"
          >
            <option value="">Moje słówka (domyślnie)</option>
            {(decks.data ?? [])
              .filter((deck) => deck.slug.startsWith("moje-") === false)
              .map((deck) => (
                <option key={deck.id} value={deck.id}>
                  {deck.name}
                </option>
              ))}
          </select>
        </label>
      </Card>

      {error && (
        <ErrorNote>
          {error}{" "}
          {duplicate && (
            <Link to={`/slownik/${duplicate}`} className="underline">
              Zobacz ją
            </Link>
          )}
        </ErrorNote>
      )}

      <Button type="submit" disabled={!ready || save.isPending}>
        {save.isPending ? "Zapisuję…" : "Dodaj do słownika"}
      </Button>
    </form>
  );
}

function ImportForm() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [csv, setCsv] = useState("");
  const [deckName, setDeckName] = useState("");
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useMutation({
    mutationFn: (dryRun: boolean) =>
      api.post<ImportResult>("/api/items/import", {
        csv,
        deck_name: deckName.trim() || null,
        dry_run: dryRun,
      }),
    onError: (caught) => setError(caught instanceof Error ? caught.message : "Import się nie udał."),
  });

  async function check() {
    setError(null);
    const result = await run.mutateAsync(true);
    setPreview(result);
  }

  async function confirm() {
    setError(null);
    const result = await run.mutateAsync(false);
    queryClient.invalidateQueries({ queryKey: ["items"] });
    queryClient.invalidateQueries({ queryKey: ["decks"] });
    queryClient.invalidateQueries({ queryKey: ["queue-summary"] });
    navigate(result.deck_id ? `/talie/${result.deck_id}` : "/slownik");
  }

  return (
    <div className="grid gap-3">
      <Card className="grid gap-3">
        <label className="grid gap-1.5">
          <span className="text-[13px] font-semibold">Lista słówek</span>
          <span className="text-[11.5px] text-ink-3">
            Jedna pozycja w wierszu: portugalski, potem polski. Przecinki, średniki albo
            tabulatory — obojętne. Dalej możesz dopisać poziom (A1–C1) i notatkę, w dowolnej
            kolejności; typ rozpoznaje się sam.
          </span>
          <textarea
            value={csv}
            onChange={(event) => {
              setCsv(event.target.value);
              setPreview(null);
            }}
            rows={8}
            spellCheck={false}
            placeholder={"a praia, plaża, A1\no mar, morze\numa toalha, ręcznik"}
            className="rounded-xl border border-line-strong bg-surface px-3 py-2.5 font-mono text-[13px]"
          />
        </label>

        <label className="grid gap-1.5">
          <span className="text-[13px] font-semibold">Nowa talia (nieobowiązkowo)</span>
          <input
            value={deckName}
            onChange={(event) => setDeckName(event.target.value)}
            placeholder="np. Wakacje"
            className="rounded-xl border border-line-strong bg-surface px-3 py-2.5 text-[14px]"
          />
          <span className="text-[11.5px] text-ink-3">
            Puste — pozycje trafią do talii „Moje słówka".
          </span>
        </label>
      </Card>

      {error && <ErrorNote>{error}</ErrorNote>}

      {preview && (
        <Card className="grid gap-2">
          <Label>Podgląd</Label>
          <p className="text-[13.5px]">
            Rozpoznane pozycje: <b>{preview.preview.length >= 10 ? "10+" : preview.preview.length}</b>
            {preview.errors.length > 0 && (
              <>
                {" · "}
                <span className="text-bad">
                  {preview.errors.length} {plural(preview.errors.length, "wiersz", "wiersze", "wierszy")}{" "}
                  do poprawy
                </span>
              </>
            )}
          </p>
          <div className="grid gap-1">
            {preview.preview.map((row) => (
              <div key={`${row.line}`} className="flex items-baseline gap-2 text-[13px]">
                <span className="pt">{row.pt}</span>
                <span className="text-ink-3">→</span>
                <span className="text-ink-2">{row.pl}</span>
                <span className="ml-auto text-[11px] text-ink-3">{row.cefr_level}</span>
              </div>
            ))}
          </div>
          {preview.errors.length > 0 && (
            <div className="mt-1 grid gap-1 rounded-xl border border-bad-line bg-bad-soft px-3 py-2">
              {preview.errors.slice(0, 5).map((problem) => (
                <div key={problem.line} className="text-[12px] text-bad">
                  wiersz {problem.line}: {problem.reason}
                </div>
              ))}
              {preview.errors.length > 5 && (
                <div className="text-[12px] text-bad">…i {preview.errors.length - 5} więcej</div>
              )}
            </div>
          )}
        </Card>
      )}

      {preview ? (
        <Button onClick={confirm} disabled={run.isPending}>
          {run.isPending ? "Importuję…" : "Zaimportuj"}
        </Button>
      ) : (
        <Button onClick={check} disabled={csv.trim().length === 0 || run.isPending}>
          {run.isPending ? "Sprawdzam…" : "Sprawdź listę"}
        </Button>
      )}
    </div>
  );
}

function Field({
  label,
  hint,
  value,
  onChange,
  lang,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  lang?: string;
}) {
  return (
    <label className="grid gap-1.5">
      <span className="text-[13px] font-semibold">{label}</span>
      {hint && <span className="text-[11.5px] text-ink-3">{hint}</span>}
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        lang={lang}
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        className={`rounded-xl border border-line-strong bg-surface px-3 py-2.5 text-[15px] ${
          lang === "pt" ? "pt" : ""
        }`}
      />
    </label>
  );
}
