import { useEffect, useRef, useState } from "react";

import { Button, cx } from "../ui";

/** The characters a Polish keyboard cannot reach. Ordered by how often they
 *  actually turn up in Portuguese, not alphabetically. */
export const DIACRITICS = ["ã", "ç", "á", "é", "ó", "ê", "â", "í", "ú", "õ", "à", "ô"];

interface Props {
  /** What is being asked for — the Polish prompt, or a sentence with a gap. */
  prompt: React.ReactNode;
  placeholder?: string;
  disabled?: boolean;
  inline?: boolean;
  onSubmit: (value: string) => void;
}

/**
 * A text field built for typing Portuguese on a Polish phone: autocorrect off
 * (it mangles the words), and the accented characters one tap away.
 */
export function TypeAnswer({ prompt, placeholder = "wpisz po portugalsku", disabled, inline, onSubmit }: Props) {
  const [value, setValue] = useState("");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setValue("");
  }, [prompt]);

  function insert(char: string) {
    const field = input.current;
    if (!field) {
      setValue((current) => current + char);
      return;
    }
    const start = field.selectionStart ?? value.length;
    const end = field.selectionEnd ?? start;
    const next = value.slice(0, start) + char + value.slice(end);
    setValue(next);
    requestAnimationFrame(() => {
      field.focus();
      field.setSelectionRange(start + char.length, start + char.length);
    });
  }

  function submit() {
    if (disabled) return;
    onSubmit(value);
  }

  return (
    <>
      <div className="flex flex-1 flex-col justify-center">{prompt}</div>

      <div className="grid gap-2">
        <input
          ref={input}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              // Ten sam Enter nie może zatwierdzić odpowiedzi i od razu zamknąć
              // informacji zwrotnej, która właśnie się przez niego pojawiła.
              // Ekran oceny nasłuchuje na oknie, więc event musi się tu skończyć.
              event.stopPropagation();
              submit();
            }
          }}
          disabled={disabled}
          placeholder={placeholder}
          // The phone's own corrections rewrite Portuguese into Polish-looking
          // words, so every assistive feature is switched off here.
          autoCapitalize="off"
          autoCorrect="off"
          autoComplete="off"
          spellCheck={false}
          inputMode="text"
          aria-label="Twoja odpowiedź"
          className={cx(
            "pt w-full rounded-2xl border-[1.5px] border-line-strong bg-surface px-4 py-3.5 text-xl text-ink outline-none",
            "placeholder:font-[var(--font-ui)] placeholder:text-base placeholder:text-ink-3",
            "focus:border-accent disabled:opacity-70",
            inline && "text-center",
          )}
        />

        <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {DIACRITICS.map((char) => (
            <button
              key={char}
              type="button"
              tabIndex={-1}
              disabled={disabled}
              onClick={() => insert(char)}
              className="pt h-10 min-w-[38px] flex-none rounded-lg border border-line bg-surface-2 text-lg hover:border-accent-line hover:bg-accent-soft disabled:opacity-50"
            >
              {char}
            </button>
          ))}
        </div>

        {!disabled && <Button onClick={submit}>Sprawdź</Button>}
      </div>
    </>
  );
}
