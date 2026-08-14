export type Direction = "recognition" | "production";
export type Mode =
  | "flashcard"
  | "mcq_pt_pl"
  | "mcq_pl_pt"
  | "typing"
  | "cloze"
  | "matching"
  | "word_bank"
  | "listening"
  | "translate_ai";

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
  audio_url: string | null;
}

/** Adresy nagrań, jakie serwer ma gotowe dla tego zadania. */
export interface TaskAudio {
  /** portugalska strona hasła */
  pt?: string;
  /** to samo, wolniej — pod przytrzymanie głośnika */
  pt_slow?: string;
  /** zdanie przykładowe */
  example?: string;
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
  audio_url: string | null;
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
  pairs?: { item_id: string; pt: string; pl: string; audio?: string | null }[];
  /** wymowa — puste, dopóki nagranie nie powstanie */
  audio?: TaskAudio;
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
  /** Policzone lokalnie, bo serwer był nieosiągalny — część pól jest nieznana. */
  offline?: boolean;
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

export interface Voice {
  name: string;
  gender: string | null;
  quality: string;
}

export interface AudioUsage {
  configured: boolean;
  chars_this_month: number;
  monthly_limit: number;
  remaining: number;
  clips_stored: number;
  bytes_stored: number;
}

/** Ile nagrań dla wybranego głosu już istnieje. */
export interface AudioCoverage {
  voice: string;
  planned: number;
  present: number;
  missing: number;
  complete: boolean;
}

export interface SynthesizeBatch {
  done: number;
  failed: number;
  remaining: number;
  error: string | null;
}

export interface ImportRow {
  line: number;
  pt: string;
  pl: string;
  type: string;
  cefr_level: string;
  notes: string | null;
}

export interface ImportResult {
  created: number;
  updated: number;
  skipped_duplicates: number;
  deck_id: string | null;
  preview: ImportRow[];
  errors: { line: number; reason: string; raw: string }[];
}

// ── AI ─────────────────────────────────────────────────────────────────────
export interface AiUsage {
  configured: boolean;
  model: string;
  spent_usd: number;
  budget_usd: number;
  remaining_usd: number;
  calls_this_month: number;
  over_budget: boolean;
}

/** Propozycja z modelu — dopóki nie zatwierdzona, nie jest pozycją do nauki. */
export interface AiProposal {
  pt: string;
  pl: string;
  type: string;
  part_of_speech: string | null;
  article: string | null;
  gender: string | null;
  plural: string | null;
  cefr_level: string;
  notes: string | null;
  example_pt: string | null;
  example_pl: string | null;
}

export interface AiGeneration {
  job_id: string;
  deck_name: string;
  proposals: AiProposal[];
  skipped_duplicates: number;
  cost_usd: number;
}

export interface AiAccepted {
  deck_id: string;
  deck_name: string;
  created: number;
  skipped_duplicates: number;
  audio_queued: number;
}

export interface AiExplanation {
  verdict: string;
  explanation: string;
  cached: boolean;
}

export interface AiGrade {
  score: number;
  corrected: string;
  feedback: string;
  cached: boolean;
}
