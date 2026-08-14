import { useState } from "react";

import { api } from "@/api/client";
import type { AiGrade, Task } from "@/api/types";
import type { AnswerEvent } from "../TaskRenderer";
import { TypeAnswer } from "./TypeAnswer";

/**
 * Przetłumacz zdanie — jedyny tryb, w którym oceny nie da się policzyć na
 * miejscu.
 *
 * Zdanie można powiedzieć po portugalsku na kilka poprawnych sposobów, więc
 * porównanie znak po znaku wywaliłoby każdą poprawną wersję inną niż wzorzec.
 * Ocenę wystawia model: liczbę 0-100, poprawioną wersję i jedno zdanie o tym,
 * co zmienić.
 *
 * Tryb jest domyślnie wyłączony, bo każda odpowiedź to płatne wywołanie i
 * kilka sekund czekania. Gdy model jest nieosiągalny — brak zasięgu, wyczerpany
 * budżet — odpowiedź nie przepada: wraca ocena „trudne" z komunikatem, więc
 * karta wróci wcześniej, zamiast zniknąć bez śladu.
 */
function ratingFromScore(score: number): number {
  if (score < 50) return 1; // znowu
  if (score < 75) return 2; // trudne
  if (score < 92) return 3; // dobrze
  return 4; // łatwe
}

export function Translate({
  task,
  locked,
  onAnswer,
}: {
  task: Task;
  locked: boolean;
  onAnswer: (event: AnswerEvent) => void;
}) {
  const [checking, setChecking] = useState(false);
  const expected = task.expected ?? task.pt;

  async function submit(value: string) {
    if (checking || locked) return;
    const answer = value.trim();
    if (!answer) return;
    setChecking(true);
    try {
      const grade = await api.post<AiGrade>("/api/ai/grade-translation", {
        item_id: task.item_id,
        prompt_pl: task.question ?? task.pl,
        expected_pt: expected,
        user_answer: answer,
      });
      const rating = ratingFromScore(grade.score);
      onAnswer({
        userAnswer: answer,
        rating,
        isCorrect: grade.score >= 75,
        correctAnswer: grade.corrected || expected,
        summary: `${grade.score}/100 — ${grade.feedback}`,
        heading: grade.score >= 92 ? "✓ Bez zarzutu" : grade.score >= 75 ? "✓ Dobrze" : "◐ Do poprawki",
      });
    } catch {
      onAnswer({
        userAnswer: answer,
        rating: 2,
        isCorrect: false,
        correctAnswer: expected,
        summary:
          "Nie udało się ocenić tej odpowiedzi — porównaj sam z wersją poniżej. Karta wróci wcześniej.",
        heading: "◐ Bez oceny",
      });
    } finally {
      setChecking(false);
    }
  }

  return (
    <TypeAnswer
      prompt={
        <div className="grid gap-2">
          <div className="text-[11px] font-bold uppercase tracking-[0.1em] text-ink-3">
            Przetłumacz na portugalski
          </div>
          <div className="text-[22px] leading-snug">{task.question ?? task.pl}</div>
          {checking && <div className="text-[12.5px] text-ink-3">Sprawdzam…</div>}
        </div>
      }
      placeholder="całe zdanie po portugalsku"
      disabled={locked || checking}
      onSubmit={(value) => void submit(value)}
    />
  );
}
