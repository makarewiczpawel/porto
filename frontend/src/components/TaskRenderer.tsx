import { useEffect, useState } from "react";

import { diffHint, feedbackLabel, gradeAnswer } from "@/api/grade";
import type { MatchPair, Task } from "@/api/types";
import { Matching } from "./modes/Matching";
import { TypeAnswer } from "./modes/TypeAnswer";
import { WordBank } from "./modes/WordBank";
import { Button, cx } from "./ui";

export interface AnswerEvent {
  rating?: number;
  selectedIndex?: number;
  userAnswer?: string;
  pairs?: MatchPair[];
  isCorrect: boolean;
  correctAnswer: string;
  /** Set for typed answers: exact | accent | typo | wrong. */
  match?: string;
  /** Expected answer with the differences marked. */
  diff?: string;
  /** Replaces the "correct answer" line for modes that have no single answer. */
  summary?: string;
}

interface Props {
  task: Task;
  locked: boolean;
  accentStrict?: boolean;
  /**
   * Study sessions grade on the client for instant feedback; quizzes do not —
   * their payload arrives without the answer key on purpose, so there is
   * nothing here to compare against.
   */
  localGrading?: boolean;
  onAnswer: (event: AnswerEvent) => void;
}

/**
 * One entry point for every exercise form. Adding a mode is a new branch and a
 * component — the session around it does not change.
 */
export function TaskRenderer({ task, locked, accentStrict, localGrading = true, onAnswer }: Props) {
  const shared = { task, locked, accentStrict, localGrading, onAnswer };
  switch (task.mode) {
    case "mcq_pt_pl":
    case "mcq_pl_pt":
      return <MultipleChoice {...shared} />;
    case "typing":
      return <Typing {...shared} />;
    case "cloze":
      return <Cloze {...shared} />;
    case "word_bank":
      return <Sentence {...shared} />;
    case "matching":
      return (
        <Matching
          task={task}
          onDone={(pairs) => {
            const firstTry = pairs.filter((p) => p.is_correct).length;
            onAnswer({
              pairs,
              isCorrect: firstTry === pairs.length,
              correctAnswer: "",
              // A matching round has no single right answer to show — what
              // matters is how many pairs landed without a wrong attempt.
              summary:
                firstTry === pairs.length
                  ? `Wszystkie ${pairs.length} pary za pierwszym razem.`
                  : `${firstTry} z ${pairs.length} par za pierwszym razem — reszta wróci wcześniej.`,
            });
          }}
        />
      );
    case "flashcard":
    default:
      return <Flashcard task={task} locked={locked} onAnswer={onAnswer} />;
  }
}

function gradedEvent(
  value: string,
  task: Task,
  accentStrict: boolean | undefined,
  localGrading = true,
): AnswerEvent {
  const expected = task.expected ?? task.pt;
  if (!localGrading || !expected) {
    // A quiz question: record what was typed and let the server score it.
    return { userAnswer: value, isCorrect: false, correctAnswer: "" };
  }
  const result = gradeAnswer(value, expected, {
    alternatives: task.alternatives ?? [],
    accentStrict,
  });
  return {
    userAnswer: value,
    isCorrect: result.isCorrect,
    correctAnswer: expected,
    match: result.match,
    diff: result.match === "exact" ? undefined : diffHint(value, expected),
  };
}

// ── flashcard ─────────────────────────────────────────────────────────────
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
              {task.example && <div className="pt text-[15px] text-ink-2">{task.example.pt}</div>}
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
                  onAnswer({ rating: rating.value, isCorrect: rating.value > 1, correctAnswer: back })
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

// ── multiple choice ───────────────────────────────────────────────────────
function MultipleChoice({ task, locked, localGrading = true, onAnswer }: Props) {
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
    // In a quiz nothing is revealed between questions.
    const truth = localGrading ? options.findIndex((option) => option === answerText) : -1;
    setCorrectIndex(localGrading ? truth : null);
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

// ── typing ────────────────────────────────────────────────────────────────
function Typing({ task, locked, accentStrict, localGrading, onAnswer }: Props) {
  return (
    <TypeAnswer
      disabled={locked}
      prompt={
        <>
          <div className="text-[11px] font-bold uppercase tracking-[0.1em] text-ink-3">
            Napisz po portugalsku
          </div>
          <p className="mt-3 text-2xl font-semibold">{task.question ?? task.pl}</p>
        </>
      }
      onSubmit={(value) => onAnswer(gradedEvent(value, task, accentStrict, localGrading))}
    />
  );
}

// ── cloze ─────────────────────────────────────────────────────────────────
function Cloze({ task, locked, accentStrict, localGrading, onAnswer }: Props) {
  const cloze = task.cloze;
  if (!cloze)
    return (
      <Typing
        task={task}
        locked={locked}
        accentStrict={accentStrict}
        localGrading={localGrading}
        onAnswer={onAnswer}
      />
    );

  return (
    <TypeAnswer
      disabled={locked}
      inline
      placeholder="brakujące słowo"
      prompt={
        <>
          <div className="text-[11px] font-bold uppercase tracking-[0.1em] text-ink-3">Uzupełnij lukę</div>
          <p className="pt mt-4 text-center text-[23px] leading-relaxed">
            {cloze.before}
            <span className="mx-1 inline-block min-w-[80px] border-b-2 border-accent align-baseline" />
            {cloze.after}
          </p>
          {task.question && <p className="mt-3 text-center text-[13.5px] text-ink-3">{task.question}</p>}
        </>
      }
      onSubmit={(value) => onAnswer(gradedEvent(value, task, accentStrict, localGrading))}
    />
  );
}

// ── word bank ─────────────────────────────────────────────────────────────
function Sentence({ task, locked, accentStrict, localGrading, onAnswer }: Props) {
  return (
    <WordBank
      task={task}
      disabled={locked}
      onSubmit={(sentence) => onAnswer(gradedEvent(sentence, task, accentStrict, localGrading))}
    />
  );
}

// ── feedback ──────────────────────────────────────────────────────────────
export function Feedback({
  isCorrect,
  correctAnswer,
  nextDueLabel,
  note,
  match,
  diff,
  summary,
  onNext,
}: {
  isCorrect: boolean;
  correctAnswer: string;
  nextDueLabel: string;
  note: string | null;
  match?: string;
  diff?: string;
  summary?: string;
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

  const almost = match === "accent" || match === "typo";
  const heading = summary
    ? isCorrect
      ? "✓ Komplet"
      : "◐ Rozgrzewka zaliczona"
    : match
      ? feedbackLabel(match as never)
      : isCorrect
        ? "✓ Dobrze"
        : "✕ Nie tym razem";

  return (
    <div
      className={cx(
        "safe-bottom animate-reveal -mx-4 grid gap-2.5 border-t px-4 pb-4 pt-3.5",
        isCorrect && !almost && "border-good-line bg-good-soft",
        (almost || (summary && !isCorrect)) && "border-warm/40 bg-warm/10",
        !isCorrect && !summary && "border-bad-line bg-bad-soft",
      )}
      aria-live="polite"
    >
      <div
        className={cx(
          "flex items-center gap-2 text-[15px] font-bold",
          isCorrect && !almost && "text-good",
          (almost || (summary && !isCorrect)) && "text-warm",
          !isCorrect && !summary && "text-bad",
        )}
      >
        {heading}
      </div>

      <div className="text-[13.5px] text-ink-2">
        {summary ? (
          summary
        ) : almost ? (
          <>
            Poprawnie: <b className="pt text-[16px] font-normal text-ink">{diff ?? correctAnswer}</b>.{" "}
            {match === "accent" ? "Brakuje akcentu" : "Literówka"} — liczy się jako trudne.
          </>
        ) : isCorrect ? (
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
