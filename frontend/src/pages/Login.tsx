import { useState } from "react";

import { ApiError } from "@/api/client";
import { Button, ErrorNote } from "@/components/ui";
import { useAuth } from "@/store/auth";

export function LoginPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register({ email, password, display_name: displayName, invite_code: inviteCode });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Coś poszło nie tak. Spróbuj ponownie.");
    } finally {
      setBusy(false);
    }
  }

  const field =
    "w-full rounded-xl border border-line bg-surface-2 px-3.5 py-3 text-[15px] text-ink outline-none focus:border-accent";

  return (
    <div className="mx-auto flex min-h-dvh max-w-[460px] flex-col justify-center gap-7 px-5 py-10">
      <header>
        <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-accent">
          Português europeu
        </div>
        <h1 className="pt mt-2 text-6xl leading-none">Porto</h1>
        <p className="mt-3 text-[15px] text-ink-2">
          Codzienna nauka portugalskiego. Powtórki planowane algorytmem FSRS.
        </p>
      </header>

      <form onSubmit={submit} className="grid gap-3">
        {mode === "register" && (
          <label className="grid gap-1.5">
            <span className="text-[13px] font-semibold text-ink-2">Imię</span>
            <input
              className={field}
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              required
              autoComplete="given-name"
            />
          </label>
        )}

        <label className="grid gap-1.5">
          <span className="text-[13px] font-semibold text-ink-2">E-mail</span>
          <input
            className={field}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            autoCapitalize="off"
          />
        </label>

        <label className="grid gap-1.5">
          <span className="text-[13px] font-semibold text-ink-2">Hasło</span>
          <input
            className={field}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
        </label>

        {mode === "register" && (
          <label className="grid gap-1.5">
            <span className="text-[13px] font-semibold text-ink-2">Kod zaproszenia</span>
            <input
              className={field}
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              required
              autoCapitalize="off"
            />
            <span className="text-xs text-ink-3">Rejestracja jest zamknięta — aplikacja jest prywatna.</span>
          </label>
        )}

        {error && <ErrorNote>{error}</ErrorNote>}

        <Button type="submit" disabled={busy} className="mt-1">
          {busy ? "Chwileczkę…" : mode === "login" ? "Zaloguj się" : "Załóż konto"}
        </Button>
      </form>

      <button
        type="button"
        className="text-sm text-ink-2 underline decoration-dotted underline-offset-4"
        onClick={() => {
          setMode(mode === "login" ? "register" : "login");
          setError(null);
        }}
      >
        {mode === "login" ? "Nie masz konta? Załóż je kodem zaproszenia." : "Mam już konto — zaloguj mnie."}
      </button>
    </div>
  );
}
