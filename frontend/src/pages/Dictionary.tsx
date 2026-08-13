import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type { ItemDetail, Page, Item } from "@/api/types";
import { SpeakButton } from "@/components/SpeakButton";
import { Card, EmptyState, Label, Pill, Spinner, cx } from "@/components/ui";

const LEVELS = ["A1", "A2", "B1"];

export function DictionaryPage() {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [level, setLevel] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(search.trim()), 250);
    return () => clearTimeout(timer);
  }, [search]);

  const query = useQuery({
    queryKey: ["items", debounced, level],
    queryFn: () => {
      const params = new URLSearchParams({ per_page: "60" });
      if (debounced) params.set("search", debounced);
      if (level) params.set("level", level);
      return api.get<Page<Item>>(`/api/items?${params}`);
    },
  });

  return (
    <div className="px-4 pt-4">
      <h1 className="pt mb-3 text-2xl">Słownik</h1>

      <div className="grid gap-2.5">
        <div className="flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-3.5 py-2.5">
          <svg viewBox="0 0 24 24" className="h-4 w-4 text-ink-3" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-3.5-3.5" />
          </svg>
          <input
            className="w-full bg-transparent text-[15px] text-ink outline-none placeholder:text-ink-3"
            placeholder="Szukaj po polsku lub portugalsku"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
          />
        </div>

        <div className="flex gap-2 overflow-x-auto pb-1">
          <Chip active={level === null} onClick={() => setLevel(null)}>
            Wszystkie
          </Chip>
          {LEVELS.map((value) => (
            <Chip key={value} active={level === value} onClick={() => setLevel(value)}>
              {value}
            </Chip>
          ))}
        </div>
      </div>

      {query.isLoading ? (
        <Spinner />
      ) : !query.data || query.data.items.length === 0 ? (
        <EmptyState title="Nic nie znaleziono" hint="Spróbuj innego słowa albo zdejmij filtr poziomu." />
      ) : (
        <>
          <Label className="mb-2 mt-4">{query.data.total} pozycji</Label>
          <div className="grid gap-2">
            {query.data.items.map((item) => (
              <ItemRow key={item.id} item={item} />
            ))}
          </div>
          {query.data.total > query.data.items.length && (
            <p className="py-4 text-center text-xs text-ink-3">
              Pokazano {query.data.items.length} z {query.data.total}. Zawęź wyszukiwanie.
            </p>
          )}
        </>
      )}
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cx(
        "flex-none rounded-full border px-3 py-1.5 text-[12.5px] font-semibold",
        active ? "border-accent bg-accent text-accent-ink" : "border-line bg-surface text-ink-2",
      )}
    >
      {children}
    </button>
  );
}

export function ItemRow({ item }: { item: Item }) {
  return (
    <div className="flex items-center gap-2 rounded-2xl border border-line bg-surface pr-2.5 hover:border-accent-line">
      <Link to={`/slownik/${item.id}`} className="flex min-w-0 flex-1 items-center gap-3 py-2.5 pl-3">
        <div className="min-w-0">
          <div className="pt truncate text-[17px] leading-tight">{item.display_pt}</div>
          <div className="truncate text-[12.5px] text-ink-2">{item.pl}</div>
        </div>
        <div className="ml-auto flex-none">
          <Pill tone={item.cefr_level === "A1" ? "neutral" : "accent"}>{item.cefr_level}</Pill>
        </div>
      </Link>
      <SpeakButton text={item.display_pt} url={item.audio_url} size="sm" />
    </div>
  );
}

export function ItemDetailPage() {
  const { itemId } = useParams();
  const query = useQuery({
    queryKey: ["item", itemId],
    queryFn: () => api.get<ItemDetail>(`/api/items/${itemId}`),
    enabled: Boolean(itemId),
  });

  if (query.isLoading) return <Spinner />;
  if (!query.data) return <EmptyState title="Nie ma takiej pozycji" action={{ label: "Wróć do słownika", to: "/slownik" }} />;

  const item = query.data;

  return (
    <div className="px-4 pt-4">
      <Link to="/slownik" className="mb-3 inline-flex items-center gap-1.5 text-sm text-ink-2">
        <span aria-hidden="true">←</span> Słownik
      </Link>

      <Card className="text-center">
        <div className="pt text-3xl leading-tight">
          {item.article && <span className="text-[0.62em] text-ink-3">{item.article} </span>}
          {item.pt}
        </div>
        <div className="mt-1 text-base text-ink-2">{item.pl}</div>
        <div className="mt-3 flex flex-wrap justify-center gap-2">
          {item.part_of_speech && (
            <Pill>
              {posLabel(item.part_of_speech)}
              {item.gender ? ` · ${item.gender}` : ""}
            </Pill>
          )}
          <Pill tone="accent">{item.cefr_level}</Pill>
          {item.plural && <Pill>lm. {item.plural}</Pill>}
        </div>
        {item.ipa && <div className="mt-2 text-[11.5px] text-ink-3">{item.ipa}</div>}
        <div className="mt-3 flex justify-center">
          <SpeakButton text={item.display_pt} url={item.audio_url} size="lg" />
        </div>
      </Card>

      {item.notes && (
        <Card className="mt-3 border-accent-line bg-accent-soft">
          <Label className="mb-1 text-accent">Uwaga</Label>
          <p className="text-[13.5px]">{item.notes}</p>
        </Card>
      )}

      {item.examples.length > 0 && (
        <div className="mt-4">
          <Label className="mb-2">Przykłady</Label>
          <div className="grid gap-2">
            {item.examples.map((example) => (
              <Card key={example.id}>
                <div className="flex items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="pt text-[16px]">{example.pt}</div>
                    <div className="mt-0.5 text-[12.5px] text-ink-2">{example.pl}</div>
                  </div>
                  <SpeakButton text={example.pt} size="sm" />
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4">
        <Label className="mb-2">Twoje powtórki</Label>
        <Card>
          {item.cards.length === 0 ? (
            <p className="text-[13.5px] text-ink-2">Jeszcze nie uczyłeś się tej pozycji.</p>
          ) : (
            <div className="grid gap-2.5">
              {item.cards.map((card) => (
                <div key={card.direction} className="flex items-center justify-between gap-3">
                  <span className="text-[13.5px] text-ink-2">
                    {card.direction === "recognition" ? "Rozpoznawanie PT→PL" : "Produkcja PL→PT"}
                  </span>
                  <Pill tone={new Date(card.due) <= new Date() ? "bad" : "good"}>
                    {formatDue(card.due)}
                  </Pill>
                </div>
              ))}
              <div className="flex items-center justify-between gap-3 border-t border-line pt-2.5">
                <span className="text-[13.5px] text-ink-2">Powtórzeń · pomyłek</span>
                <span className="text-[13.5px] tnum">
                  {item.cards.reduce((sum, c) => sum + c.reps, 0)} ·{" "}
                  {item.cards.reduce((sum, c) => sum + c.lapses, 0)}
                </span>
              </div>
            </div>
          )}
        </Card>
      </div>

      {item.decks.length > 0 && (
        <div className="mt-4">
          <Label className="mb-2">W taliach</Label>
          <div className="flex flex-wrap gap-2">
            {item.decks.map((name) => (
              <Pill key={name}>{name}</Pill>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function posLabel(pos: string) {
  return (
    {
      noun: "rzeczownik",
      verb: "czasownik",
      adj: "przymiotnik",
      adv: "przysłówek",
      prep: "przyimek",
      conj: "spójnik",
      num: "liczebnik",
      expr: "zwrot",
    }[pos] ?? pos
  );
}

function formatDue(due: string) {
  const date = new Date(due);
  const days = Math.round((date.getTime() - Date.now()) / 86_400_000);
  if (days <= 0) return "dziś";
  if (days === 1) return "jutro";
  if (days < 31) return `za ${days} dni`;
  const months = Math.round(days / 30);
  return `za ${months} mies.`;
}
