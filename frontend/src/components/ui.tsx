import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

/** Polska odmiana przez liczbę: 1 wiersz, 2 wiersze, 5 wierszy. */
export function plural(count: number, one: string, few: string, many: string): string {
  if (count === 1) return one;
  const lastTwo = count % 100;
  const last = count % 10;
  if (last >= 2 && last <= 4 && !(lastTwo >= 12 && lastTwo <= 14)) return few;
  return many;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "quiet";
  size?: "md" | "sm";
};

export function Button({ variant = "primary", size = "md", className, ...rest }: ButtonProps) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed";
  const sizes = size === "sm" ? "px-3.5 py-2 text-sm" : "w-full px-4 py-3.5 text-base";
  const variants = {
    primary: "bg-accent text-accent-ink hover:brightness-110 active:brightness-95",
    ghost: "bg-surface text-ink border border-line-strong hover:bg-surface-2",
    quiet: "bg-transparent text-ink-2 hover:text-ink",
  }[variant];
  return <button className={cx(base, sizes, variants, className)} {...rest} />;
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("rounded-2xl border border-line bg-surface p-4", className)}>{children}</div>;
}

export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx("text-[11px] font-bold uppercase tracking-[0.12em] text-ink-3", className)}>
      {children}
    </div>
  );
}

export function Pill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "good" | "bad" | "warm";
}) {
  const tones = {
    neutral: "bg-surface-3 text-ink-2 border-line",
    accent: "bg-accent-soft text-accent border-accent-line",
    good: "bg-good-soft text-good border-good-line",
    bad: "bg-bad-soft text-bad border-bad-line",
    warm: "bg-warm/15 text-warm border-warm/35",
  }[tone];
  return (
    <span className={cx("inline-block rounded-full border px-2 py-0.5 text-[11px] font-semibold", tones)}>
      {children}
    </span>
  );
}

export function ProgressRing({ value, max, label }: { value: number; max: number; label: string }) {
  const radius = 76;
  const circumference = 2 * Math.PI * radius;
  const ratio = max > 0 ? Math.min(value / max, 1) : 0;
  return (
    <div className="relative h-44 w-44">
      <svg width="176" height="176" viewBox="0 0 176 176" className="-rotate-90">
        {/* Tor cieńszy od wypełnienia: pusty pierścień ma wyglądać jak miejsce
            czekające na wypełnienie, a nie jak ciemne koło. */}
        <circle cx="88" cy="88" r={radius} fill="none" stroke="var(--color-surface-3)" strokeWidth="9" />
        <circle
          cx="88"
          cy="88"
          r={radius}
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth="13"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - ratio)}
          className="transition-[stroke-dashoffset] duration-500"
        />
      </svg>
      <div className="absolute inset-0 grid place-content-center justify-items-center text-center">
        <div className="pt text-5xl leading-none tnum">
          {value}
          <span className="text-2xl text-ink-3">/{max}</span>
        </div>
        <div className="mt-1 text-xs text-ink-3">{label}</div>
      </div>
    </div>
  );
}

export function Spinner({ label = "Ładowanie…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-sm text-ink-3" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line-strong border-t-accent" />
      {label}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: { label: string; to: string };
}) {
  return (
    <div className="grid justify-items-center gap-3 py-14 text-center">
      <div className="text-lg font-semibold">{title}</div>
      {hint && <p className="max-w-[32ch] text-sm text-ink-2">{hint}</p>}
      {action && (
        <Link
          to={action.to}
          className="rounded-xl border border-line-strong bg-surface px-4 py-2 text-sm font-semibold"
        >
          {action.label}
        </Link>
      )}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-bad-line bg-bad-soft px-3.5 py-3 text-sm text-bad" role="alert">
      {children}
    </div>
  );
}
