import { useEffect, useState } from "react";

import type { Task } from "@/api/types";
import { Button, cx } from "./ui";

export interface AnswerEvent {
  rating?: number;
  selectedIndex?: number;
  isCorrect: boolean;
  correctAnswer: string;
}

interface Props {
  task: Task;
  locked: boolean;
  onAnswer: (event: AnswerEvent) => void;
}

/**
 * One entry point for every exercise form. A new mode is a new branch plus a
 * component — the session around it does not change.
 */
export function TaskRenderer({ task, locked, onAnswer }: Props) {
  switch (task.mode) {
    case "mcq_pt_pl":
    case "mcq_pl_pt":
      return <MultipleChoice task={task} locked={locked} onAnswer={onAnswer} />;
    case "flashcard":
    default:
      return <Flashcard task={task} locked={locked} onAnswer={onAnswer} />;
  }
}

const RATINGS = [
  { value: 1, label: "Znów", tone: "hover:border-bad hover:text-bad" },
  { value: 2, label: "Trudne", tone: "hover:border-accent hover:text-accent" },
  { value: 3, label: "Dobrze", tone: "hover:border-accent hover:text-accent" },
  { value: 4, label: "Łatwe", tone: "hover:border-good hover:text-good" },
];

function Flashcard({ task, locked, onAnswer }: Props) {
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    setRevealed(false);
  }, [task.index]);

  useEffect(() => {
    if (locked) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === " " && !revealed) {
        event.preventDefault();
        setRevealed(true);
        return;
      }
      if (revealed && ["1", "2", "3", "4"].includes(event.key)) {
        const rating = Number(event.key);
        onAnswer({ rating, isCorrect: rating > 1, correctAnswer: task.back ?? task.pl });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [revealed, locked, onAnswer, task]);

  const front = task.front ?? task.pt;
  const back = task.back ?? task.pl;
  const frontIsPortuguese = task.direction === "recognition";

  return (
    <>
      <div className="flex flex-1 flex-col justify-center">
        <button
          type="button"
          onClick={() => !revealed && setRevealed(true)}
          disabled={revealed}
          className={cx(
            "grid min-h-[220px] w-full content-center justify-items-center gap-3 rounded-3xl border border-line bg-surface-2 px-5 py-7 text-center",
            !revealed && "hover:border-accent-line",
          )}
        >
          <div className={cx("text-4xl leading-tight", frontIsPortuguese && "pt")}>{front}</div>
          {!revealed ? (
            <div className="text-[13px] text-ink-3">Tapnij, żeby odsłonić</div>
          ) : (
            <div className="animate-reveal grid justify-items-center gap-3">
              <div className={cx("text-2xl font-semibold", !frontIsPortuguese && "pt")}>{back}</div>
              {task.example && (
                <div className="pt text-[15px] text-ink-2">{task.example.pt}</div>
              )}
              {task.notes && (
                <div className="rounded-xl border border-line bg-surface px-3 py-2 text-left text-[13px] text-ink-2">
                  {task.notes}
                </div>
              )}
            </div>
          )}
        </button>
      </div>

      {revealed && !locked && (
        <div className="animate-reveal">
          <div className="mb-2 text-center text-xs text-ink-3">Jak dobrze pamiętałeś?</div>
          <div className="grid grid-cols-4 gap-2">
            {RATINGS.map((rating) => (
              <button
                key={rating.value}
                type="button"
                onClick={() =>
                  onAnswer({
                    rating: rating.value,
                    isCorrect: rating.value > 1,
                    correctAnswer: back,
                  })
                }
                className={cx(
                  "grid gap-0.5 rounded-xl border border-line bg-surface px-1 py-2.5 text-[13px] font-semibold transition",
                  rating.tone,
                )}
              >
                {rating.label}
                <small className="text-[10px] font-normal text-ink-3">
                  {task.intervals?.[String(rating.value)] ?? ""}
                </small>
              </button>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function MultipleChoice({ task, locked, onAnswer }: Props) {
  const [picked, setPicked] = useState<number | null>(null);
  const [correctIndex, setCorrectIndex] = useState<number | null>(null);

  useEffect(() => {
    setPicked(null);
    setCorrectIndex(null);
  }, [task.index]);

  const options = task.options ?? [];
  const answerText = task.mode === "mcq_pt_pl" ? task.pl : task.pt;
  const questionIsPortuguese = task.mode === "mcq_pt_pl";

  function choose(index: number) {
    if (picked !== null || locked) return;
    setPicked(index);
    // The correct option is known locally (it is the item's own translation);
    // the server re-checks it against the frozen session payload.
    const truth = options.findIndex((option) => option === answerText);
    setCorrectIndex(truth);
    onAnswer({
      selectedIndex: index,
      isCorrect: index === truth,
      correctAnswer: truth >= 0 ? options[truth] : answerText,
    });
  }

  useEffect(() => {
    if (locked || picked !== null) return;
    const onKey = (event: KeyboardEvent) => {
      const index = Number(event.key) - 1;
      if (index >= 0 && index < options.length) choose(index);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <>
      <div className="flex flex-1 flex-col justify-center">
        <div className="text-[11px] font-bold uppercase tracking-[0.1em] text-ink-3">
          {questionIsPortuguese ? "Co to znaczy?" : "Jak to powiedzieć?"}
        </div>
        <div className={cx("mt-3 text-center text-3xl leading-tight", questionIsPortuguese && "pt")}>
          {task.question}
        </div>
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
                !questionIsPortuguese && "pt text-[17px]",
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

export function Feedback({
  isCorrect,
  correctAnswer,
  nextDueLabel,
  note,
  onNext,
}: {
  isCorrect: boolean;
  correctAnswer: string;
  nextDueLabel: string;
  note: string | null;
  onNext: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onNext();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onNext]);

  return (
    <div
      className={cx(
        "safe-bottom animate-reveal -mx-4 grid gap-2.5 border-t px-4 pb-4 pt-3.5",
        isCorrect ? "border-good-line bg-good-soft" : "border-bad-line bg-bad-soft",
      )}
      aria-live="polite"
    >
      <div className={cx("flex items-center gap-2 text-[15px] font-bold", isCorrect ? "text-good" : "text-bad")}>
        {isCorrect ? "✓ Dobrze" : "✕ Nie tym razem"}
      </div>
      <div className="text-[13.5px] text-ink-2">
        {isCorrect ? (
          nextDueLabel ? (
            <>
              Wraca za <b className="font-semibold text-ink">{nextDueLabel}</b>.
            </>
          ) : (
            "Zapisane."
          )
        ) : (
          <>
            Poprawnie: <b className="pt text-[16px] font-normal text-ink">{correctAnswer}</b>.
          </>
        )}
        {note && <div className="mt-1 text-[12.5px] text-ink-3">{note}</div>}
      </div>
      <Button onClick={onNext} autoFocus>
        Dalej
      </Button>
    </div>
  );
}
