/**
 * Wymowa: nagranie z serwera, a gdy go nie ma — głos wbudowany w przeglądarkę.
 *
 * Nagrania pt-PT z Google brzmią jak człowiek i są identyczne na każdym
 * urządzeniu. Ale powstają dopiero po uruchomieniu syntezy, a przed tym
 * momentem (i dla słów dodanych później) lepszy jest głos systemowy niż cisza —
 * pod warunkiem, że **naprawdę** jest portugalski europejski. Głos brazylijski
 * uczyłby złej wymowy, więc jeśli takiego tylko znajdziemy, wolimy nie odezwać
 * się wcale.
 */

import { API_BASE } from "./client";

export type SpeechSource = "recording" | "browser" | "none";

let unlocked = false;
let current: HTMLAudioElement | null = null;

/** iOS odtwarza dźwięk dopiero po pierwszym geście użytkownika. */
export function unlockAudio() {
  unlocked = true;
}

export function isUnlocked() {
  return unlocked;
}

export function absoluteUrl(url: string): string {
  return url.startsWith("http") ? url : `${API_BASE}${url}`;
}

export function stop() {
  if (current) {
    current.pause();
    current = null;
  }
  if (typeof window !== "undefined" && window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
}

/**
 * Nagranie z serwera. Odrzucone obietnice są normalne (autoplay), nie błędem.
 *
 * `crossOrigin` wygląda na szczegół, a decyduje o tym, czy na telefonie w ogóle
 * coś słychać. API stoi na innej domenie niż aplikacja, więc bez tego
 * przeglądarka pobiera nagranie „na ślepo": dostaje odpowiedź nieprzezroczystą,
 * której nie wolno jej odczytać. Taka odpowiedź trafiała do pamięci offline
 * jako plik o zerowej długości i od tego momentu było już tylko gorzej —
 * Safari, które przy dźwięku zawsze prosi o fragment pliku, nie miało czego
 * odtworzyć i milczało. Na komputerze problem się nie ujawniał, bo tam
 * przeglądarka pobiera nagranie w całości i strumieniuje je z pominięciem
 * pamięci podręcznej.
 *
 * Z nagłówkami CORS odpowiedź jest zwykłym, czytelnym plikiem: da się ją
 * odtworzyć, zapisać na później i pociąć na fragmenty. Gdyby serwer ich kiedyś
 * nie przysłał, druga próba idzie po staremu — lepiej stracić tryb offline dla
 * jednego nagrania niż ciszę zamiast wymowy.
 */
function load(src: string, cors: boolean): Promise<void> {
  // Pierwsza próba mogła zostawić element w trakcie wczytywania; druga nie ma
  // się z czym ścigać.
  stop();
  return new Promise((resolve, reject) => {
    const audio = new Audio();
    if (cors) audio.crossOrigin = "anonymous";
    audio.src = src;
    current = audio;
    audio.addEventListener("error", () => reject(new Error("nie udało się wczytać nagrania")), {
      once: true,
    });
    audio.play().then(resolve, reject);
  });
}

export function playRecording(url: string): Promise<void> {
  stop();
  const src = absoluteUrl(url);
  return load(src, true).catch(() => load(src, false).catch(() => undefined));
}

function portugueseVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis?.getVoices?.() ?? [];
  // `pt-PT` dokładnie; `pt-BR` świadomie odrzucone, `pt` bez kraju bywa
  // brazylijskie, więc też odpada.
  return voices.find((voice) => voice.lang?.replace("_", "-").toLowerCase() === "pt-pt") ?? null;
}

export function browserCanSpeakPortuguese(): boolean {
  if (typeof window === "undefined" || !window.speechSynthesis) return false;
  return portugueseVoice() !== null;
}

export function speakWithBrowser(text: string, rate = 1): boolean {
  const voice = portugueseVoice();
  if (!voice) return false;
  stop();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.voice = voice;
  utterance.lang = "pt-PT";
  utterance.rate = rate;
  window.speechSynthesis.speak(utterance);
  return true;
}

/** Najlepsze dostępne źródło dźwięku dla tego tekstu. */
export async function say(
  text: string,
  options: { url?: string | null; rate?: number } = {},
): Promise<SpeechSource> {
  const { url, rate = 1 } = options;
  if (url) {
    await playRecording(url);
    return "recording";
  }
  return speakWithBrowser(text, rate) ? "browser" : "none";
}

/**
 * Lista głosów systemowych bywa pusta przy pierwszym pytaniu i dopełnia się
 * asynchronicznie — bez tego przycisk wymowy potrafi zniknąć na sekundę po
 * wejściu na stronę.
 */
export function onVoicesReady(callback: () => void): () => void {
  if (typeof window === "undefined" || !window.speechSynthesis) return () => undefined;
  const handler = () => callback();
  window.speechSynthesis.addEventListener?.("voiceschanged", handler);
  return () => window.speechSynthesis.removeEventListener?.("voiceschanged", handler);
}
