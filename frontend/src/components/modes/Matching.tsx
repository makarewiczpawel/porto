import { useMemo, useState } from "react";

import type { Task } from "@/api/types";
import { cx } from "../ui";

export interface MatchOutcome {
  item_id: string;
  is_correct: boolean;
}

interface Tile {
  key: string;
  itemId: string;
  text: string;
  side: "pt" | "pl";
}

/**
 * The warm-up: five words, five translations, shuffled into two columns.
 *
 * A pair joined on the first try counts as remembered; one that took a wrong
 * attempt first counts as shaky and comes back sooner.
 */
export function Matching({ task, onDone }: { task: Task; onDone: (outcomes: MatchOutcome[]) => void }) {
  const pairs = task.pairs ?? [];

  const [left, right] = useMemo(() => {
    const shuffle = <T,>(list: T[]) => [...list].sort(() => Math.random() - 0.5);
    return [
      shuffle(pairs.map<Tile>((p) => ({ key: `pt-${p.item_id}`, itemId: p.item_id, text: p.pt, side: "pt" }))),
      shuffle(pairs.map<Tile>((p) => ({ key: `pl-${p.item_id}`, itemId: p.item_id, text: p.pl, side: "pl" }))),
    ];
  }, [task.index]); // eslint-disable-line react-hooks/exhaustive-deps

  const [selected, setSelected] = useState<Tile | null>(null);
  const [done, setDone] = useState<Set<string>>(new Set());
  const [missed, setMissed] = useState<Set<string>>(new Set());
  const [shake, setShake] = useState<string[]>([]);

  function tap(tile: Tile) {
    if (done.has(tile.itemId)) return;

    if (!selected) {
      setSelected(tile);
      return;
    }
    if (selected.key === tile.key) {
      setSelected(null);
      return;
    }
    if (selected.side === tile.side) {
      setSelected(tile);
      return;
    }

    if (selected.itemId === tile.itemId) {
      const nextDone = new Set(done).add(tile.itemId);
      setDone(nextDone);
      setSelected(null);
      if (nextDone.size === pairs.length) {
        onDone(
          pairs.map((pair) => ({ item_id: pair.item_id, is_correct: !missed.has(pair.item_id) })),
        );
      }
      return;
    }

    // Wrong join — both words involved are marked as shaky.
    setMissed((current) => new Set(current).add(selected.itemId).add(tile.itemId));
    setShake([selected.key, tile.key]);
    setSelected(null);
    window.setTimeout(() => setShake([]), 420);
  }

  function tile(item: Tile) {
    const isDone = done.has(item.itemId);
    const isSelected = selected?.key === item.key;
    const isShaking = shake.includes(item.key);
    return (
      <button
        key={item.key}
        type="button"
        onClick={() => tap(item)}
        disabled={isDone}
        aria-pressed={isSelected}
        className={cx(
          "grid min-h-[52px] place-items-center rounded-xl border px-2 py-3 text-center text-sm leading-snug transition",
          item.side === "pt" && "pt text-base",
          isDone && "border-dashed border-line opacity-30",
          isSelected && "border-accent bg-accent-soft text-accent",
          isShaking && "border-bad bg-bad-soft",
          !isDone && !isSelected && !isShaking && "border-line bg-surface",
        )}
      >
        {item.text}
      </button>
    );
  }

  return (
    <div className="flex flex-1 flex-col justify-center">
      <p className="mb-3 text-[13.5px] text-ink-2">Połącz pary — kolumny są przetasowane.</p>
      <div className="grid grid-cols-2 gap-2">
        {left.map((item, index) => (
          <div key={item.key} className="contents">
            {tile(item)}
            {tile(right[index])}
          </div>
        ))}
      </div>
    </div>
  );
}
