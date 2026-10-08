/** Lekcje gramatyki — kształt odpowiedzi `/api/grammar`. */

export interface LessonSummary {
  slug: string;
  title: string;
  summary: string;
  level: string;
  part: string;
  position: number;
  examples: number;
  questions: number;
}

export interface LessonExample {
  pt: string;
  pl: string;
  /** Nagranie wybranym głosem; null, dopóki nie powstało. */
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
  | { type: "tip"; tone: "trap" | "pt" | "info"; title: string; text: string };

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
