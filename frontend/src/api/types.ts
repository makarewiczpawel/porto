export type Direction = "recognition" | "production";
export type Mode = "flashcard" | "mcq_pt_pl" | "mcq_pl_pt" | "typing" | "cloze" | "matching" | "word_bank" | "listening";

export interface User {
  id: string;
  email: string;
  display_name: string;
  timezone: string;
}

export interface Settings {
  daily_goal: number;
  new_per_day: number;
  review_limit: number;
  desired_retention: number;
  enabled_modes: Mode[];
  tts_voice: string;
  tts_speed: number;
  autoplay_audio: boolean;
  accent_strict: boolean;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Example {
  id: string;
  pt: string;
  pl: string;
}

export interface Item {
  id: string;
  type: string;
  pt: string;
  display_pt: string;
  pl: string;
  variant: string;
  part_of_speech: string | null;
  gender: string | null;
  article: string | null;
  plural: string | null;
  ipa: string | null;
  cefr_level: string;
  notes: string | null;
  source: string;
  verified: boolean;
}

export interface CardState {
  direction: Direction;
  state: string;
  due: string;
  reps: number;
  lapses: number;
  suspended: boolean;
}

export interface ItemDetail extends Item {
  examples: Example[];
  cards: CardState[];
  decks: string[];
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}

export interface Deck {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  cefr_level: string | null;
  icon: string | null;
  position: number;
  total: number;
  due: number;
  learned: number;
  untouched: number;
}

export interface DeckDetail extends Deck {
  items: Item[];
}

export interface QueueSummary {
  due: number;
  new_available: number;
  done_today: number;
  goal: number;
  streak: number;
  goal_met: boolean;
  next_due_at: string | null;
}

export interface Task {
  index: number;
  item_id: string;
  direction: Direction;
  mode: Mode;
  is_new: boolean;
  pt: string;
  pl: string;
  type: string;
  cefr_level: string;
  part_of_speech: string | null;
  notes: string | null;
  example: { pt: string; pl: string } | null;
  /** multiple choice */
  question?: string;
  options?: string[];
  /** flashcard */
  front?: string;
  back?: string;
  intervals?: Record<string, string>;
  /** typing / cloze / word_bank — needed to grade locally and offline */
  expected?: string;
  alternatives?: string[];
  cloze?: { before: string; answer: string; after: string };
  tokens?: string[];
  extra?: string[];
  /** matching — one question covering several cards */
  pairs?: { item_id: string; pt: string; pl: string }[];
}

export interface StudySession {
  id: string;
  started_at: string;
  planned_count: number;
  completed_count: number;
  tasks: Task[];
}

export interface MatchPair {
  item_id: string;
  is_correct: boolean;
}

export interface AnswerPayload {
  index: number;
  rating?: number;
  selected_index?: number;
  user_answer?: string;
  pairs?: MatchPair[];
  elapsed_ms: number;
}

export interface AnswerResult {
  index: number;
  is_correct: boolean;
  rating: number;
  correct_answer: string;
  next_due: string;
  next_due_label: string;
  match?: "exact" | "accent" | "typo" | "wrong" | null;
  diff?: string | null;
  duplicate: boolean;
}

export interface Mistake {
  item_id: string;
  pt: string;
  pl: string;
  user_answer: string | null;
  mode: Mode;
}

export interface SessionSummary {
  session_id: string;
  completed_count: number;
  correct_count: number;
  accuracy: number;
  new_count: number;
  seconds: number;
  streak: number;
  goal_met: boolean;
  done_today: number;
  goal: number;
  next_due_count: number;
  mistakes: Mistake[];
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> };
}

// ── quizy ─────────────────────────────────────────────────────────────────
export interface Quiz {
  id: string;
  name: string;
  config: {
    deck_ids?: string[];
    cefr_level?: string | null;
    count?: number;
    modes?: Mode[];
    time_limit_s?: number | null;
  };
  created_at: string;
  last_score: number | null;
}

export interface QuizAttempt {
  id: string;
  name: string;
  started_at: string;
  time_limit_s: number | null;
  questions: Task[];
}

export interface QuizMistake {
  item_id: string;
  pt: string;
  pl: string;
  user_answer: string | null;
  mode: Mode;
  skipped: boolean;
}

export interface QuizResult {
  attempt_id: string;
  name: string;
  score: number;
  total: number;
  correct: number;
  seconds: number;
  previous_score: number | null;
  mistakes: QuizMistake[];
}

export interface QuizHistoryEntry {
  attempt_id: string;
  quiz_id: string | null;
  name: string;
  score: number;
  finished_at: string | null;
  total: number;
}
