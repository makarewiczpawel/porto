/** Lekcje — dialogi i gramatyka. Kształt odpowiedzi `/api/lessons`. */

export type LessonKind = "dialogi" | "gramatyka";

export interface LessonSummary {
  slug: string;
  kind: LessonKind;
  title: string;
  summary: string;
  level: string;
  part: string;
  position: number;
  /** Ile zdań da się odsłuchać: przykładów albo kwestii dialogu. */
  spoken: number;
  questions: number;
}

export interface LessonExample {
  pt: string;
  pl: string;
  /** Nagranie wybranym głosem; null, dopóki nie powstało. */
  audio: string | null;
}

export interface DialogueLine {
  /** Kto mówi, po polsku. „Ty” to kwestie ucznia. */
  who: string;
  pt: string;
  pl: string;
  audio: string | null;
}

export type LessonBlock =
  | { type: "p"; text: string }
  | { type: "h"; text: string }
  | {
      type: "table";
      caption: string | null;
      head: string[];
      rows: string[][];
      pt_cols: number[];
      br_cols: number[];
    }
  | { type: "examples"; items: LessonExample[] }
  | { type: "tip"; tone: "trap" | "pt" | "info"; title: string; text: string }
  | { type: "dialogue"; lines: DialogueLine[] };

export interface LessonQuestion {
  q: string;
  options: string[];
  answer: number;
  why: string;
}

export interface Lesson extends LessonSummary {
  blocks: LessonBlock[];
  check: LessonQuestion[];
  /** Brakujące nagrania właśnie się dogrywają — warto za chwilę dopytać. */
  audio_pending: boolean;
  previous: LessonSummary | null;
  next: LessonSummary | null;
}
