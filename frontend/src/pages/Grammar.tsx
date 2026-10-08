import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type { Lesson, LessonBlock, LessonQuestion, LessonSummary } from "@/api/grammar";
import { RichText } from "@/components/RichText";
import { SpeakButton } from "@/components/SpeakButton";
import { EmptyState, Label, Pill, Spinner, cx, plural } from "@/components/ui";

// ── spis lekcji ───────────────────────────────────────────────────────────
export function GrammarPage() {
  const query = useQuery({
    queryKey: ["grammar"],
    queryFn: () => api.get<{ lessons: LessonSummary[] }>("/api/grammar"),
  });

  // Części w kolejności pierwszego pojawienia się — tak, jak ułożone są pliki
  // lekcji. Spis to kurs, nie katalog: ma się czytać od góry.
  const parts = useMemo(() => {
    const grouped = new Map<string, LessonSummary[]>();
    for (const lesson of query.data?.lessons ?? []) {
      grouped.set(lesson.part, [...(grouped.get(lesson.part) ?? []), lesson]);
    }
    return [...grouped.entries()];
  }, [query.data]);

  if (query.isLoading) return <Spinner />;
  if (!query.data?.lessons.length) {
    return <EmptyState title="Brak lekcji" hint="Lekcje gramatyki jeszcze się nie wczytały." />;
  }

  const count = query.data.lessons.length;

  return (
    <div className="px-4 pt-4">
      <h1 className="pt text-2xl">Gramatyka</h1>
      <p className="mb-5 mt-1 text-[13.5px] text-ink-2">
        {count} {plural(count, "lekcja", "lekcje", "lekcji")} po polsku — każda z przykładami do
        odsłuchania i krótkim sprawdzianem na koniec.
      </p>

      <div className="grid gap-6">
        {parts.map(([part, lessons]) => (
          <section key={part}>
            <Label className="mb-2">{part}</Label>
            <div className="grid gap-2">
              {lessons.map((lesson) => (
                <Link
                  key={lesson.slug}
                  to={`/gramatyka/${lesson.slug}`}
                  className="flex items-start gap-3 rounded-2xl border border-line bg-surface p-3.5 transition hover:border-accent-line active:bg-surface-2"
                >
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent-soft text-[14px] font-bold text-accent tnum">
                    {lesson.position}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[15px] font-semibold leading-snug">
                      {lesson.title}
                    </span>
                    <span className="mt-0.5 block text-[12.5px] leading-snug text-ink-2">
                      <RichText text={lesson.summary} />
                    </span>
                  </span>
                  <span className="shrink-0 pt-0.5 text-[11px] font-semibold text-ink-3">
                    {lesson.level}
                  </span>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

// ── lekcja ────────────────────────────────────────────────────────────────
// Ile razy ekran dopyta o świeżo dograne nagrania, zanim da spokój. Kilka
// sekund wystarcza na kilkanaście krótkich zdań; jeśli coś nie wyjdzie
// (limit, brak sieci), przyciski zostają przy głosie telefonu i mówią o tym
// przerywaną obwódką, zamiast odpytywać serwer bez końca.
const AUDIO_POLLS = 6;

export function LessonPage() {
  const { slug } = useParams();
  const query = useQuery({
    queryKey: ["grammar", slug],
    queryFn: () => api.get<Lesson>(`/api/grammar/${slug}`),
    enabled: Boolean(slug),
    refetchInterval: (q) =>
      q.state.data?.audio_pending && q.state.dataUpdateCount <= AUDIO_POLLS ? 3000 : false,
  });

  if (query.isLoading) return <Spinner />;
  const lesson = query.data;
  if (!lesson) {
    return (
      <EmptyState
        title="Nie ma takiej lekcji"
        action={{ label: "Wróć do gramatyki", to: "/gramatyka" }}
      />
    );
  }

  return (
    <article className="px-4 pb-6 pt-4" key={lesson.slug}>
      <Link to="/gramatyka" className="mb-4 inline-flex items-center gap-1.5 text-sm text-ink-2">
        <span aria-hidden="true">←</span> Gramatyka
      </Link>

      <header className="mb-5">
        <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-accent">
          Lekcja {lesson.position} · {lesson.part}
        </div>
        <h1 className="pt mt-1.5 text-[28px] leading-tight">{lesson.title}</h1>
        <p className="mt-1.5 text-[14px] text-ink-2">
          <RichText text={lesson.summary} />
        </p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          <Pill tone="accent">{lesson.level}</Pill>
          <Pill>
            {lesson.examples} {plural(lesson.examples, "przykład", "przykłady", "przykładów")}
          </Pill>
          <Pill>
            {lesson.questions} {plural(lesson.questions, "pytanie", "pytania", "pytań")} na koniec
          </Pill>
        </div>
        {lesson.audio_pending && (
          <p className="mt-3 text-[12px] text-ink-3">
            Nagrania przykładów dogrywają się — za chwilę zabrzmią głosem wybranym w ustawieniach.
          </p>
        )}
      </header>

      <div className="grid gap-3.5">
        {lesson.blocks.map((block, index) => (
          <LessonBlockView key={index} block={block} />
        ))}
      </div>

      <LessonCheck questions={lesson.check} />

      <nav className="mt-8 grid grid-cols-2 gap-2.5" aria-label="Sąsiednie lekcje">
        {lesson.previous ? (
          <Neighbour lesson={lesson.previous} label="← Poprzednia" />
        ) : (
          <span />
        )}
        {lesson.next ? <Neighbour lesson={lesson.next} label="Następna →" align="right" /> : <span />}
      </nav>
    </article>
  );
}

function LessonBlockView({ block }: { block: LessonBlock }) {
  switch (block.type) {
    case "p":
      return (
        <p className="text-[15px] leading-relaxed text-ink-2">
          <RichText text={block.text} accent />
        </p>
      );
    case "h":
      return <h2 className="mt-4 text-[17px] font-bold leading-snug">{block.text}</h2>;
    case "table":
      return <LessonTable block={block} />;
    case "examples":
      return (
        <div className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
          {block.items.map((example) => (
            <div key={example.pt} className="flex items-center gap-3 px-3.5 py-2.5">
              <div className="min-w-0 flex-1">
                <div lang="pt-PT" className="pt text-[17px] leading-snug">
                  {example.pt}
                </div>
                <div className="mt-0.5 text-[12.5px] leading-snug text-ink-2">{example.pl}</div>
              </div>
              <SpeakButton text={example.pt} url={example.audio} size="sm" />
            </div>
          ))}
        </div>
      );
    case "tip":
      return <Tip tone={block.tone} title={block.title} text={block.text} />;
  }
}

function LessonTable({ block }: { block: Extract<LessonBlock, { type: "table" }> }) {
  return (
    // Tabela odmiany bywa szersza niż telefon. Przewija się w swoim pudełku,
    // a nie razem z całą stroną — inaczej rozjeżdża się cały ekran lekcji.
    <div className="overflow-x-auto rounded-2xl border border-line bg-surface">
      <table className="w-full border-collapse text-left text-[13.5px]">
        {block.caption && <caption className="px-3.5 pt-3 text-left text-ink-3">{block.caption}</caption>}
        <thead>
          <tr className="border-b border-line bg-surface-2">
            {block.head.map((cell, col) => (
              <th
                key={col}
                scope="col"
                // Nagłówek się zawija: „QUERER (CHCIEĆ)” w jednej linii rozpychał
                // czterokolumnową tabelę odmiany poza ekran telefonu i ostatni
                // czasownik trzeba było przewijać, choć mieścił się bez tego.
                className={cx(
                  // Bez wersalików: „PRZYCHODZIĆ” wersalikami to jedno słowo szersze
                  // niż kolumna, którego nie da się złamać, i tabela odmiany z
                  // czterema czasownikami znowu wystawała poza telefon.
                  "px-2 py-2 align-bottom text-[11.5px] font-semibold leading-tight first:pl-3",
                  block.br_cols.includes(col) ? "text-ink-3" : "text-ink-2",
                )}
              >
                <RichText text={cell} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, r) => (
            <tr key={r} className="border-b border-line last:border-0">
              {row.map((cell, col) => {
                const pt = block.pt_cols.includes(col);
                const br = block.br_cols.includes(col);
                // Pojedyncza forma ({faço}, {estamos a fazer}) nie powinna się
                // łamać w pół. Całe zdanie w tabeli porównawczej — owszem, inaczej
                // wypycha kolumnę ze znaczeniem poza ekran.
                const short = cell.length <= 16;
                // Tabela z czterema czasownikami obok siebie to pięć kolumn na
                // telefonie — tu krój musi ustąpić o pół stopnia, żeby się zmieścić.
                const dense = block.head.length >= 5;
                return (
                  <td
                    key={col}
                    lang={pt || br ? "pt" : undefined}
                    className={cx(
                      "px-2 py-2 align-top leading-snug first:pl-3",
                      pt && cx("pt text-ink", dense ? "text-[14.5px]" : "text-[15.5px]"),
                      br && "pt text-[15px] italic text-ink-3",
                      (pt || br) && short && "whitespace-nowrap",
                      !pt && !br && (col === 0 ? "text-ink-2" : "text-ink"),
                    )}
                  >
                    <RichText text={cell} />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const TIP_STYLE = {
  trap: { box: "border-warm/40 bg-warm/10", title: "text-warm", icon: "⚠" },
  pt: { box: "border-accent-line bg-accent-soft", title: "text-accent", icon: "🇵🇹" },
  info: { box: "border-line bg-surface-2", title: "text-ink", icon: "💡" },
} as const;

function Tip({ tone, title, text }: { tone: keyof typeof TIP_STYLE; title: string; text: string }) {
  const style = TIP_STYLE[tone];
  return (
    <aside className={cx("rounded-2xl border px-3.5 py-3", style.box)}>
      <div className={cx("flex items-start gap-2 text-[13.5px] font-bold leading-snug", style.title)}>
        <span aria-hidden="true">{style.icon}</span>
        <span>{title}</span>
      </div>
      <p className="mt-1 text-[13.5px] leading-relaxed text-ink-2">
        <RichText text={text} />
      </p>
    </aside>
  );
}

function Neighbour({
  lesson,
  label,
  align = "left",
}: {
  lesson: LessonSummary;
  label: string;
  align?: "left" | "right";
}) {
  return (
    <Link
      to={`/gramatyka/${lesson.slug}`}
      className={cx(
        "grid gap-0.5 rounded-2xl border border-line bg-surface p-3 hover:border-accent-line",
        align === "right" && "text-right",
      )}
    >
      <span className="text-[11px] font-semibold text-ink-3">{label}</span>
      <span className="text-[13.5px] font-semibold leading-snug">{lesson.title}</span>
    </Link>
  );
}

// ── sprawdź się ───────────────────────────────────────────────────────────
/** Kolejność odpowiedzi tasowana raz na wejście w lekcję. W pliku poprawna
 *  odpowiedź stoi tam, gdzie ją wpisano — bez tasowania po dwóch lekcjach
 *  wiadomo by było, gdzie jej szukać. */
function shuffled(count: number): number[] {
  const order = Array.from({ length: count }, (_, i) => i);
  for (let i = order.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }
  return order;
}

function LessonCheck({ questions }: { questions: LessonQuestion[] }) {
  const [round, setRound] = useState(0);
  const orders = useMemo(
    () => questions.map((question) => shuffled(question.options.length)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [questions, round],
  );
  const [picked, setPicked] = useState<Record<number, number>>({});

  const answered = Object.keys(picked).length;
  const correct = questions.filter((question, i) => picked[i] === question.answer).length;
  const finished = answered === questions.length;

  return (
    <section className="mt-9" aria-labelledby="sprawdz-sie">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 id="sprawdz-sie" className="pt text-[22px]">
          Sprawdź się
        </h2>
        <span className="text-[12px] font-semibold text-ink-3 tnum">
          {answered}/{questions.length}
        </span>
      </div>

      <ol className="grid gap-3">
        {questions.map((question, i) => {
          const choice = picked[i];
          const done = choice !== undefined;
          return (
            <li key={`${round}-${i}`} className="rounded-2xl border border-line bg-surface p-3.5">
              <div className="text-[14.5px] font-semibold leading-snug">
                <span className="mr-1.5 text-ink-3 tnum">{i + 1}.</span>
                <RichText text={question.q} />
              </div>
              <div className="mt-2.5 grid gap-1.5">
                {orders[i].map((option) => {
                  const isAnswer = option === question.answer;
                  const isChoice = option === choice;
                  return (
                    <button
                      key={option}
                      type="button"
                      disabled={done}
                      onClick={() => setPicked((prev) => ({ ...prev, [i]: option }))}
                      className={cx(
                        "rounded-xl border px-3 py-2.5 text-left text-[14.5px] leading-snug transition",
                        !done && "border-line-strong bg-surface hover:border-accent-line active:bg-surface-2",
                        done && isAnswer && "border-good-line bg-good-soft text-good",
                        done && isChoice && !isAnswer && "border-bad-line bg-bad-soft text-bad",
                        done && !isAnswer && !isChoice && "border-line bg-surface text-ink-3",
                      )}
                    >
                      <RichText text={question.options[option]} />
                    </button>
                  );
                })}
              </div>
              {done && (
                <p className="animate-reveal mt-2.5 text-[13px] leading-relaxed text-ink-2">
                  <b className={choice === question.answer ? "text-good" : "text-bad"}>
                    {choice === question.answer ? "Dobrze. " : "Nie tym razem. "}
                  </b>
                  <RichText text={question.why} />
                </p>
              )}
            </li>
          );
        })}
      </ol>

      {finished && (
        <div className="animate-reveal mt-3 flex items-center justify-between gap-3 rounded-2xl border border-accent-line bg-accent-soft px-3.5 py-3">
          <div className="text-[14px]">
            <b className="tnum">
              {correct}/{questions.length}
            </b>{" "}
            {correct === questions.length
              ? "— komplet."
              : correct >= questions.length - 1
                ? "— prawie komplet."
                : "— warto wrócić do lekcji."}
          </div>
          <button
            type="button"
            onClick={() => {
              setPicked({});
              setRound((value) => value + 1);
            }}
            className="rounded-full border border-accent-line bg-surface px-3 py-1.5 text-[12.5px] font-semibold text-accent"
          >
            Jeszcze raz
          </button>
        </div>
      )}
    </section>
  );
}
