import { Fragment } from "react";

import { cx } from "@/components/ui";

/**
 * Tekst lekcji z dwoma znacznikami: `{...}` to wstawka po portugalsku,
 * `**...**` — wyróżnienie. Wyróżnienie może zawierać portugalskie wstawki
 * („mówi się **{dele}, {dela}**”), odwrotnie nie.
 *
 * Portugalski składa się krojem portugalskim, jak wszędzie w aplikacji: w
 * polskim objaśnieniu od razu widać, które słowa są materiałem do nauki,
 * a które opisem.
 */
const TOKENS = /(\*\*.+?\*\*|\{[^}]+\})/g;

export function RichText({ text, accent = false }: { text: string; accent?: boolean }) {
  return (
    <>
      {text.split(TOKENS).map((part, index) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return (
            <b key={index} className="font-semibold text-ink">
              <RichText text={part.slice(2, -2)} accent={accent} />
            </b>
          );
        }
        if (part.startsWith("{") && part.endsWith("}")) {
          return (
            <span
              key={index}
              lang="pt-PT"
              // `leading-none`: większy krój szeryfowy w środku wiersza
              // podnosiłby cały wiersz i akapit miałby nierówne odstępy.
              className={cx("pt text-[1.07em] leading-none", accent ? "text-accent" : "text-ink")}
            >
              {part.slice(1, -1)}
            </span>
          );
        }
        return <Fragment key={index}>{part}</Fragment>;
      })}
    </>
  );
}
