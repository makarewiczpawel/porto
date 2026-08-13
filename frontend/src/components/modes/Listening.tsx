import { useEffect, useState } from "react";

import type { Task } from "@/api/types";
import type { AnswerEvent } from "../TaskRenderer";
import { playRecording, unlockAudio } from "@/api/speech";
import { cx } from "../ui";

/**
 * Słuchanie: pytaniem jest nagranie, nie napis.
 *
 * Najtrudniejszy z trybów, bo jako jedyny nie daje się zdać wzrokiem — dlatego
 * dostają go tylko słowa już rozpoznawane pewnie. Nagranie odtwarza się samo po
 * wejściu na ekran, a duży przycisk pozwala powtórzyć tyle razy, ile trzeba:
 * karą za wielokrotne odsłuchanie byłoby zniechęcenie, nie nauka.
 */
export function Listening({
  task,
  locked,
  localGrading = true,
  onAnswer,
}: {
  task: Task;
  locked: boolean;
  localGrading?: boolean;
  onAnswer: (event: AnswerEvent) => void;
}) {
  const [picked, setPicked] = useState<number | null>(null);
  const [correctIndex, setCorrectIndex] = useState<number | null>(null);
  const [plays, setPlays] = useState(0);

  const options = task.options ?? [];
  const url = task.audio?.pt;

  useEffect(() => {
    setPicked(null);
    setCorrectIndex(null);
    setPlays(0);
  }, [task.index]);

  useEffect(() => {
    if (!url) return;
    void playRecording(url);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task.index, url]);

  function replay(slow: boolean) {
    unlockAudio();
    const source = slow ? task.audio?.pt_slow ?? url : url;
    if (source) {
      void playRecording(source);
      setPlays((count) => count + 1);
    }
  }

  function choose(index: number) {
    if (picked !== null || locked) return;
    setPicked(index);
    const truth = localGrading ? options.findIndex((option) => option === task.pl) : -1;
    setCorrectIndex(localGrading ? truth : null);
    onAnswer({
      selectedIndex: index,
      isCorrect: index === truth,
      correctAnswer: truth >= 0 ? options[truth] : task.pl,
    });
  }

  return (
    <>
      <div className="flex flex-1 flex-col items-center justify-center gap-4">
        <div className="text-[11px] font-bold uppercase tracking-[0.1em] text-ink-3">Co słyszysz?</div>

        <button
          type="button"
          onClick={() => replay(false)}
          className="grid h-28 w-28 place-content-center rounded-full border-2 border-accent-line bg-accent-soft text-accent transition active:scale-95"
          aria-label="Odtwórz jeszcze raz"
        >
          <svg viewBox="0 0 24 24" width="44" height="44" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M11 5 6.5 9H3v6h3.5L11 19z" strokeLinejoin="round" />
            <path d="M15.5 9.5a3.5 3.5 0 0 1 0 5" strokeLinecap="round" />
            <path d="M18.5 6.5a7.5 7.5 0 0 1 0 11" strokeLinecap="round" />
          </svg>
        </button>

        <button
          type="button"
          onClick={() => replay(true)}
          className="rounded-full border border-line px-3 py-1.5 text-[12.5px] font-semibold text-ink-2 hover:text-ink"
        >
          Wolniej
        </button>

        {plays > 0 && <div className="text-[11.5px] text-ink-3">Odsłuchane {plays + 1}×</div>}
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        {options.map((option, index) => {
          const isAnswer = correctIndex === index;
          const isWrongPick = picked === index && correctIndex !== index;
          return (
            <button
              key={option}
              type="button"
              onClick={() => choose(index)}
              disabled={picked !== null}
              className={cx(
                "grid min-h-[76px] place-items-center rounded-2xl border px-3 py-4 text-center text-[15px] font-medium leading-snug transition",
                isAnswer && "border-good bg-good-soft text-good",
                isWrongPick && "border-bad bg-bad-soft text-bad",
                picked === null && "border-line bg-surface hover:border-accent hover:bg-accent-soft",
                picked !== null && !isAnswer && !isWrongPick && "border-line bg-surface opacity-60",
              )}
            >
              {option}
            </button>
          );
        })}
      </div>
    </>
  );
}
