import { useEffect, useMemo, useState } from "react";

import type { Task } from "@/api/types";
import { Button, cx } from "../ui";

interface Brick {
  key: string;
  word: string;
}

/**
 * Rebuild a sentence from its words.
 *
 * The point is word order, not vocabulary: where the negation sits, where the
 * pronoun attaches — the places Polish intuition quietly misleads.
 */
export function WordBank({
  task,
  disabled,
  onSubmit,
}: {
  task: Task;
  disabled?: boolean;
  onSubmit: (sentence: string) => void;
}) {
  const bricks = useMemo<Brick[]>(() => {
    const all = [...(task.tokens ?? []), ...(task.extra ?? [])];
    return all
      .map((word, index) => ({ key: `${index}-${word}`, word }))
      .sort(() => Math.random() - 0.5);
  }, [task.index]); // eslint-disable-line react-hooks/exhaustive-deps

  const [chosen, setChosen] = useState<Brick[]>([]);

  useEffect(() => {
    setChosen([]);
  }, [task.index]);

  const used = new Set(chosen.map((b) => b.key));

  return (
    <>
      <div className="flex flex-1 flex-col justify-center">
        <div className="text-[11px] font-bold uppercase tracking-[0.1em] text-ink-3">Ułóż zdanie</div>
        <p className="mt-2 text-lg font-semibold">{task.question}</p>
      </div>

      <div className="grid gap-3">
        <div className="flex min-h-[58px] flex-wrap content-start gap-1.5 border-b-2 border-dashed border-line-strong pb-2.5">
          {chosen.map((brick, index) => (
            <button
              key={brick.key}
              type="button"
              disabled={disabled}
              onClick={() => setChosen((current) => current.filter((_, i) => i !== index))}
              className="pt rounded-lg border border-line bg-surface px-3 py-2 text-[17px]"
            >
              {brick.word}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap justify-center gap-1.5">
          {bricks.map((brick) => (
            <button
              key={brick.key}
              type="button"
              disabled={disabled || used.has(brick.key)}
              onClick={() => setChosen((current) => [...current, brick])}
              className={cx(
                "pt rounded-lg border border-line bg-surface px-3 py-2 text-[17px] hover:border-accent-line hover:bg-accent-soft",
                // Kept in place rather than removed, so the layout does not
                // jump under the thumb mid-tap.
                used.has(brick.key) && "invisible",
              )}
            >
              {brick.word}
            </button>
          ))}
        </div>

        {!disabled && (
          <Button onClick={() => onSubmit(chosen.map((b) => b.word).join(" "))} disabled={chosen.length === 0}>
            Sprawdź
          </Button>
        )}
      </div>
    </>
  );
}
