import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { ApiError, api } from "@/api/client";
import { splitWords, wordKey } from "@/api/words";
import type { PhraseBreakdown, WordGloss } from "@/api/words";
import { cx } from "@/components/ui";

/** Rozbiory pobrane w tej sesji przeglądarki.
 *
 * Serwer i tak liczy każdy zwrot raz i pamięta go na stałe, ale powrót do tej
 * samej karty nie powinien nawet czekać na sieć. Klucz po treści zwrotu, tak
 * jak w pamięci serwera — ten sam zwrot pod inną pozycją jest już znany. */
const known = new Map<string, PhraseBreakdown>();

const cacheKey = (text: string) =>
  text.split(/\s+/).join(" ").trim().toLowerCase();

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; data: PhraseBreakdown }
  | { kind: "error"; message: string }
  /** Model niedostępny — bez klucza albo po wyczerpaniu budżetu. Wtedy słowa
   *  przestają wyglądać na klikalne, zamiast obiecywać coś, czego nie ma. */
  | { kind: "off"; message: string };

/**
 * Zwrot, w którego słowa da się stuknąć.
 *
 * Zwrot uczy się szybciej niż pojedyncze słowo, ale zostawia pytanie, którego
 * przy słowie nie było: *co tu właściwie robi każdy wyraz*. „Quanto custa?"
 * wchodzi do głowy jako jeden dźwięk i tak zostaje — dopóki nie widać, że
 * „custa" to forma „custar" i że wróci w „quanto custam?".
 *
 * Jedno wywołanie opisuje cały zwrot, więc pierwsze stuknięcie opłaca
 * wszystkie następne, a powrót do tego zwrotu jest darmowy i natychmiastowy.
 */
export function TappableText({
  text,
  itemId,
  className,
}: {
  text: string;
  itemId: string;
  className?: string;
}) {
  const [state, setState] = useState<State>(() => {
    const hit = known.get(cacheKey(text));
    return hit ? { kind: "ready", data: hit } : { kind: "idle" };
  });
  const [open, setOpen] = useState<number | null>(null);
  // Chmurka siada przy *wierszu* stukniętego słowa, nie pod całym zwrotem.
  // Zdanie zawija się na trzy linijki i strzałka wskazywałaby wtedy w próżnię
  // pod ostatnią z nich, zamiast na słowo, o które pytano.
  //
  // `screen` to ten sam wiersz, ale we współrzędnych ekranu — po nim poznajemy,
  // czy pod słowem starczy jeszcze miejsca.
  const [at, setAt] = useState({ x: 24, top: 0, bottom: 0 });
  const [screen, setScreen] = useState({ top: 0, bottom: 0 });
  const [above, setAbove] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  const anchor = useRef<HTMLSpanElement>(null);
  const bubble = useRef<HTMLSpanElement>(null);

  // Stuknięcie obok chmurki ją zamyka — tak samo jak Escape. Bez tego jedyną
  // drogą wyjścia byłoby trafienie w to samo słowo drugi raz.
  useEffect(() => {
    if (open === null) return;
    const away = (event: Event) => {
      if (!box.current?.contains(event.target as Node)) setOpen(null);
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(null);
    };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", key);
    };
  }, [open]);

  useEffect(() => {
    setOpen(null);
    const hit = known.get(cacheKey(text));
    setState(hit ? { kind: "ready", data: hit } : { kind: "idle" });
  }, [text]);

  async function fetchOnce() {
    if (
      state.kind === "ready" ||
      state.kind === "loading" ||
      state.kind === "off"
    )
      return;
    setState({ kind: "loading" });
    try {
      const data = await api.post<PhraseBreakdown>("/api/ai/breakdown", {
        item_id: itemId,
        text,
      });
      known.set(cacheKey(text), data);
      setState({ kind: "ready", data });
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "AI_NOT_CONFIGURED") {
        setState({
          kind: "off",
          message: "Rozbiór zwrotów wymaga klucza do modelu.",
        });
      } else if (caught instanceof ApiError && caught.code === "AI_BUDGET") {
        setState({
          kind: "off",
          message: "Budżet na ten miesiąc się skończył.",
        });
      } else {
        setState({
          kind: "error",
          message: "Nie udało się teraz sprawdzić. Spróbuj za chwilę.",
        });
      }
    }
  }

  function tap(event: React.MouseEvent<HTMLButtonElement>, index: number) {
    // Zwrot bywa w miejscu, które samo reaguje na dotyk — odsłonięcie karty
    // nie ma się dziać przy okazji pytania o słowo.
    event.stopPropagation();
    if (open === index) {
      setOpen(null);
      return;
    }
    const parent = anchor.current?.getBoundingClientRect();
    const word = event.currentTarget.getBoundingClientRect();
    if (parent) {
      const middle = word.left + word.width / 2 - parent.left;
      setAt({
        x: Math.min(Math.max(middle, 18), Math.max(parent.width - 18, 18)),
        top: word.top - parent.top,
        bottom: word.bottom - parent.top,
      });
      setScreen({ top: word.top, bottom: word.bottom });
      setAbove(false);
    }
    setOpen(index);
    void fetchOnce();
  }

  // Chmurka staje po tej stronie wiersza, gdzie jest więcej miejsca.
  //
  // Samo „zmieści się na ekranie" to za mało. Przy ocenie zwrot stoi tuż nad
  // przyciskiem „Dalej": chmurka mieści się pod nim co do piksela i przykrywa
  // jedyne wyjście z ekranu. Nad zwrotem jest wtedy pusto — i tam ma iść.
  // Liczone po doczytaniu opisu, bo dopiero wtedy znamy jej wysokość.
  useLayoutEffect(() => {
    const node = bubble.current;
    if (open === null || !node) return;
    const height = node.offsetHeight + 16;
    const below = window.innerHeight - screen.bottom;
    const up = screen.top;
    setAbove(up >= height && (below < height || up > below));
  }, [open, state.kind, screen]);

  const glosses = state.kind === "ready" ? state.data : null;
  const segments = splitWords(text);
  const dead = state.kind === "off";

  function glossFor(word: string): WordGloss | null {
    if (!glosses) return null;
    return (
      glosses.words.find((entry) => wordKey(entry.word) === wordKey(word)) ??
      null
    );
  }

  return (
    <span ref={box} className={cx("block", className)}>
      <span ref={anchor} className="relative block">
        {segments.map((segment, index) =>
          segment.word && !dead ? (
            <button
              key={index}
              type="button"
              onClick={(event) => tap(event, index)}
              aria-expanded={open === index}
              className={cx(
                "-mx-0.5 rounded px-0.5 underline decoration-dotted decoration-from-font underline-offset-[3px] transition",
                open === index
                  ? "bg-accent-soft decoration-accent text-accent"
                  : "decoration-ink-3/50 active:bg-surface-3",
              )}
            >
              {segment.text}
            </button>
          ) : (
            <span key={index}>{segment.text}</span>
          ),
        )}

        {open !== null && (
          <span
            ref={bubble}
            role="dialog"
            className="animate-reveal absolute left-0 right-0 z-30 block rounded-xl border border-line-strong bg-surface text-left shadow-pop"
            style={
              above
                ? { top: at.top - 8, transform: "translateY(-100%)" }
                : { top: at.bottom + 8 }
            }
          >
            <span
              aria-hidden="true"
              className={cx(
                "absolute block h-[10px] w-[10px] rotate-45 border-line-strong bg-surface",
                above ? "-bottom-[6px] border-b border-r" : "-top-[6px] border-l border-t",
              )}
              style={{ left: at.x - 5 }}
            />
            {/* Przewijanie siedzi w środku, nie na chmurce: `overflow` na
                zewnętrznej ramce przycinał strzałkę, bo ta wystaje poza jej
                brzeg. Ograniczenie wysokości chroni przed opisem dłuższym
                niż ekran. */}
            <span className="block max-h-[45vh] overflow-y-auto p-3">
              <Bubble
                word={segments[open]?.text ?? ""}
                gloss={glossFor(segments[open]?.text ?? "")}
                literal={glosses?.literal ?? null}
                state={state}
              />
            </span>
          </span>
        )}
      </span>

    </span>
  );
}

function Bubble({
  word,
  gloss,
  literal,
  state,
}: {
  word: string;
  gloss: WordGloss | null;
  /** Dosłowne tłumaczenie całego zwrotu — puenta rozbioru. */
  literal: string | null;
  state: State;
}) {
  if (state.kind === "loading") {
    return (
      <span className="block text-[13px] text-ink-2">Sprawdzam „{word}"…</span>
    );
  }
  if (state.kind === "error" || state.kind === "off") {
    return (
      <span className="block text-[13px] text-ink-2">{state.message}</span>
    );
  }
  if (!gloss) {
    // Zdarza się, gdy podział na słowa po obu stronach nie zgadza się co do
    // joty. Lepiej powiedzieć wprost, niż podstawić opis sąsiedniego słowa.
    return (
      <span className="block text-[13px] text-ink-2">
        Nie mam opisu tego słowa.
      </span>
    );
  }

  const base = gloss.lemma.trim();
  const isVerb = gloss.pos.toLowerCase().startsWith("czasownik");
  const showBase = base.toLowerCase() !== word.toLowerCase();

  return (
    <>
      <span className="flex items-baseline gap-2">
        <span className="pt text-[17px] leading-tight">{word}</span>
        <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3">
          {gloss.pos}
        </span>
      </span>
      <span className="mt-0.5 block text-[14px] font-medium">{gloss.pl}</span>
      {showBase && (
        <span className="mt-1.5 block text-[12.5px] text-ink-2">
          {isVerb ? "bezokolicznik" : "forma podstawowa"}:{" "}
          <b className="pt font-normal text-ink">{base}</b>
        </span>
      )}
      {gloss.form && (
        <span className="block text-[12.5px] text-ink-2">{gloss.form}</span>
      )}
      {gloss.note && (
        <span className="mt-1.5 block border-t border-line pt-1.5 text-[12.5px] text-ink-2">
          {gloss.note}
        </span>
      )}
      {literal && (
        // Dosłowne tłumaczenie całości mieszka tutaj, a nie osobną linijką pod
        // zwrotem: tam wchodziło między portugalski a polski i czytało się
        // jak druga, gorsza wersja tłumaczenia. W chmurce jest tym, czym ma
        // być — puentą, po której „faz favor" wreszcie się składa.
        <span className="mt-1.5 block border-t border-line pt-1.5 text-[11.5px] text-ink-3">
          cały zwrot dosłownie: {literal}
        </span>
      )}
    </>
  );
}
