/** Dzielenie zwrotu na słowa, w które da się stuknąć.
 *
 * Reguła jest ta sama co po stronie serwera (`ai.words_in` w
 * `backend/app/services/ai.py`) i musi taka zostać: myślnik i apostrof
 * zostają w środku słowa, bo w portugalskim spinają jedną całość —
 * „chamo-me" to forma czasownika z zaimkiem, a nie dwa hasła. Cyfry i
 * interpunkcja słowami nie są.
 *
 * Opisu i tak szukamy po treści słowa, nie po jego numerze, więc rozjazd obu
 * reguł kończy się najwyżej brakiem opisu — a nie opisem cudzego słowa.
 */
const WORD_RE = /[\p{L}\p{M}]+(?:['’-][\p{L}\p{M}]+)*/gu;

export interface Segment {
  text: string;
  /** Słowo (stuknięcie coś robi) czy odstęp między słowami. */
  word: boolean;
}

export function splitWords(text: string): Segment[] {
  const segments: Segment[] = [];
  let cursor = 0;
  for (const match of text.matchAll(WORD_RE)) {
    const start = match.index ?? 0;
    if (start > cursor) segments.push({ text: text.slice(cursor, start), word: false });
    segments.push({ text: match[0], word: true });
    cursor = start + match[0].length;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), word: false });
  return segments;
}

/** Ile słów liczy ten napis.
 *
 * Rozbiór ma sens od dwóch słów w górę. Przy jednym („obrigado") chmurka
 * powtarzałaby to, co i tak stoi obok — a kosztowałaby osobne wywołanie
 * modelu. */
export function countWords(text: string): number {
  return splitWords(text).filter((segment) => segment.word).length;
}

/** Klucz opisu: to samo słowo na początku i w środku zdania ma jeden opis. */
export function wordKey(word: string): string {
  return word.toLocaleLowerCase("pt-PT");
}

export interface WordGloss {
  word: string;
  lemma: string;
  pos: string;
  pl: string;
  form: string | null;
  note: string | null;
}

export interface PhraseBreakdown {
  text: string;
  literal: string;
  words: WordGloss[];
  cached: boolean;
}
