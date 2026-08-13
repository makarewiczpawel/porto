import { useEffect, useRef, useState } from "react";
import { browserCanSpeakPortuguese, onVoicesReady, say, unlockAudio } from "../api/speech";
import { cx } from "./ui";

/**
 * Głośnik przy portugalskim tekście.
 *
 * Przytrzymanie odtwarza wolniejszą wersję — przy słuchaniu obcego języka to
 * jedyna rzecz, o którą się prosi, a osobny przycisk zajmowałby miejsce, które
 * na telefonie jest na wagę złota.
 *
 * Gdy nie ma ani nagrania, ani portugalskiego głosu w systemie, przycisk
 * znika. Cichy przycisk uczy, że aplikacja jest zepsuta.
 */

const HOLD_MS = 350;

export function SpeakButton({
  text,
  url,
  slowUrl,
  size = "md",
  autoPlay = false,
  className,
}: {
  text: string;
  url?: string | null;
  slowUrl?: string | null;
  size?: "md" | "sm" | "lg";
  autoPlay?: boolean;
  className?: string;
}) {
  const [playing, setPlaying] = useState(false);
  const [slow, setSlow] = useState(false);
  const [available, setAvailable] = useState(() => Boolean(url) || browserCanSpeakPortuguese());
  const holdTimer = useRef<number | null>(null);
  const heldRef = useRef(false);
  const playedRef = useRef<string | null>(null);

  useEffect(() => {
    setAvailable(Boolean(url) || browserCanSpeakPortuguese());
    return onVoicesReady(() => setAvailable(Boolean(url) || browserCanSpeakPortuguese()));
  }, [url, text]);

  async function play(useSlow: boolean) {
    setPlaying(true);
    setSlow(useSlow);
    try {
      await say(text, { url: useSlow ? slowUrl ?? url : url, rate: useSlow ? 0.7 : 1 });
    } finally {
      // Nie znamy długości nagrania bez wczytania metadanych; krótka animacja
      // to potwierdzenie tapnięcia, nie pasek postępu.
      window.setTimeout(() => {
        setPlaying(false);
        setSlow(false);
      }, 600);
    }
  }

  // Autoodtwarzanie po odsłonięciu odpowiedzi — raz na tekst, nigdy w kółko.
  useEffect(() => {
    if (!autoPlay || !available) return;
    const key = `${text}|${url ?? ""}`;
    if (playedRef.current === key) return;
    playedRef.current = key;
    void play(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoPlay, available, text, url]);

  if (!available) return null;

  const dimensions = { sm: "h-8 w-8 text-sm", md: "h-10 w-10 text-base", lg: "h-12 w-12 text-lg" }[size];

  function startHold() {
    unlockAudio();
    heldRef.current = false;
    holdTimer.current = window.setTimeout(() => {
      heldRef.current = true;
      void play(true);
    }, HOLD_MS);
  }

  function endHold() {
    if (holdTimer.current !== null) {
      window.clearTimeout(holdTimer.current);
      holdTimer.current = null;
    }
    if (!heldRef.current) void play(false);
    heldRef.current = false;
  }

  return (
    <button
      type="button"
      aria-label={`Posłuchaj: ${text}`}
      title="Tapnij, żeby posłuchać · przytrzymaj, żeby wolniej"
      onPointerDown={startHold}
      onPointerUp={endHold}
      onPointerLeave={() => {
        if (holdTimer.current !== null) {
          window.clearTimeout(holdTimer.current);
          holdTimer.current = null;
        }
      }}
      onContextMenu={(event) => event.preventDefault()}
      className={cx(
        "inline-grid shrink-0 place-content-center rounded-full border transition select-none touch-manipulation",
        playing
          ? "border-accent-line bg-accent-soft text-accent"
          : "border-line-strong bg-surface text-ink-2 hover:text-ink",
        dimensions,
        className,
      )}
    >
      {slow ? <SlowIcon /> : <SpeakerIcon animated={playing} />}
    </button>
  );
}

function SpeakerIcon({ animated }: { animated: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="1.25em" height="1.25em" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M11 5 6.5 9H3v6h3.5L11 19z" strokeLinejoin="round" />
      <path d="M15.5 9.5a3.5 3.5 0 0 1 0 5" strokeLinecap="round" className={animated ? "animate-pulse" : ""} />
      <path
        d="M18.5 6.5a7.5 7.5 0 0 1 0 11"
        strokeLinecap="round"
        className={animated ? "animate-pulse" : "opacity-45"}
      />
    </svg>
  );
}

function SlowIcon() {
  return (
    <svg viewBox="0 0 24 24" width="1.25em" height="1.25em" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M11 5 6.5 9H3v6h3.5L11 19z" strokeLinejoin="round" />
      <path d="M15 12h5" strokeLinecap="round" />
      <path d="M17.5 9.5 20 12l-2.5 2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
