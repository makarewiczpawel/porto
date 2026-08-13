/**
 * Client-side mirror of the server's grader.
 *
 * It exists so feedback appears the moment you answer, and so a session can be
 * finished with no connection at all (phase 3). The server re-grades every
 * answer against the frozen session payload — this is the fast path, not the
 * authority. The two must stay in step: same normalisation, same accent rule,
 * same one-key tolerance.
 */

export type MatchKind = "exact" | "accent" | "typo" | "wrong";

export interface LocalGrade {
  isCorrect: boolean;
  match: MatchKind;
  partial: boolean;
}

const MIN_LENGTH_FOR_TYPO = 4;
const PUNCTUATION = /[.,;:!?¿¡"'`´“”„«»…()[\]]/g;

export function normalize(value: string | undefined | null): string {
  return (value ?? "")
    .trim()
    .toLowerCase()
    .replace(PUNCTUATION, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function stripAccents(value: string): string {
  return value.normalize("NFD").replace(/[̀-ͯ]/g, "");
}

/** Levenshtein distance, capped — we only ever care whether it is 0 or 1. */
function distance(a: string, b: string, cap = 2): number {
  if (Math.abs(a.length - b.length) > cap) return cap + 1;
  let previous = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const current = [i];
    for (let j = 1; j <= b.length; j++) {
      current[j] = Math.min(
        previous[j] + 1,
        current[j - 1] + 1,
        previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
    }
    previous = current;
    if (Math.min(...previous) > cap) return cap + 1;
  }
  return previous[b.length];
}

export function gradeAnswer(
  answer: string,
  expected: string,
  options: { alternatives?: string[]; accentStrict?: boolean } = {},
): LocalGrade {
  const { alternatives = [], accentStrict = false } = options;
  const candidates = [expected, ...alternatives];
  const given = normalize(answer);

  if (!given) return { isCorrect: false, match: "wrong", partial: false };

  for (const candidate of candidates) {
    if (given === normalize(candidate)) return { isCorrect: true, match: "exact", partial: false };
  }

  const givenBare = stripAccents(given);
  for (const candidate of candidates) {
    if (givenBare === stripAccents(normalize(candidate))) {
      return { isCorrect: !accentStrict, match: "accent", partial: !accentStrict };
    }
  }

  for (const candidate of candidates) {
    const targetBare = stripAccents(normalize(candidate));
    if (targetBare.length < MIN_LENGTH_FOR_TYPO) continue;
    if (distance(givenBare, targetBare) <= 1) {
      return { isCorrect: true, match: "typo", partial: true };
    }
  }

  return { isCorrect: false, match: "wrong", partial: false };
}

/** The expected answer with differing characters wrapped in `»…«`. */
export function diffHint(answer: string, expected: string): string {
  const given = normalize(answer);
  const target = normalize(expected);
  if (given === target) return expected;
  return [...target]
    .map((char, index) => (given[index] === char ? char : `»${char}«`))
    .join("");
}

export function feedbackLabel(match: MatchKind): string {
  return { exact: "✓ Dobrze", accent: "≈ Prawie", typo: "≈ Prawie", wrong: "✕ Nie tym razem" }[match];
}
