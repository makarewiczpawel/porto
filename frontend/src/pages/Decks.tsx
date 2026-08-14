import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError, api } from "@/api/client";
import type { Deck, DeckDetail, StudySession } from "@/api/types";
import { ItemRow } from "./Dictionary";
import { Button, Card, EmptyState, ErrorNote, Label, Pill, Spinner } from "@/components/ui";
import { useSession } from "@/store/session";

export function DecksPage() {
  const query = useQuery({ queryKey: ["decks"], queryFn: () => api.get<Deck[]>("/api/decks") });

  if (query.isLoading) return <Spinner />;
  if (!query.data || query.data.length === 0) {
    return <EmptyState title="Brak talii" hint="Baza startowa nie została jeszcze załadowana." />;
  }

  return (
    <div className="px-4 pt-4">
      <h1 className="pt mb-3 text-2xl">Talie</h1>
      <div className="grid grid-cols-2 gap-2.5">
        {query.data.map((deck) => (
          <Link
            key={deck.id}
            to={`/talie/${deck.id}`}
            className="grid gap-2 rounded-2xl border border-line bg-surface p-3 hover:border-accent-line"
          >
            <div className="text-[14.5px] font-semibold leading-snug">
              {deck.icon && <span className="mr-1">{deck.icon}</span>}
              {deck.name}
            </div>
            <DeckBar deck={deck} />
            <div className="text-[11px] text-ink-3 tnum">
              {deck.total} pozycji{deck.due > 0 ? ` · ${deck.due} na dziś` : ""}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function DeckBar({ deck }: { deck: Deck }) {
  const learned = deck.total ? (deck.learned / deck.total) * 100 : 0;
  const due = deck.total ? (deck.due / deck.total) * 100 : 0;
  return (
    <div className="flex h-[5px] overflow-hidden rounded-full bg-surface-3">
      <span className="block h-full bg-good" style={{ width: `${learned}%` }} />
      <span className="block h-full bg-accent" style={{ width: `${due}%` }} />
    </div>
  );
}

export function DeckDetailPage() {
  const { deckId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const begin = useSession((s) => s.begin);

  const query = useQuery({
    queryKey: ["deck", deckId],
    queryFn: () => api.get<DeckDetail>(`/api/decks/${deckId}`),
    enabled: Boolean(deckId),
  });

  const start = useMutation({
    mutationFn: async () => {
      const existing = await api.get<StudySession | null>("/api/study/sessions/active");
      if (existing) await api.post(`/api/study/sessions/${existing.id}/abandon`);
      return api.post<StudySession>("/api/study/sessions", { deck_ids: [deckId] });
    },
    onSuccess: (session) => {
      begin(session);
      queryClient.invalidateQueries({ queryKey: ["active-session"] });
      navigate("/nauka");
    },
  });

  if (query.isLoading) return <Spinner />;
  if (!query.data) return <EmptyState title="Nie ma takiej talii" action={{ label: "Wróć do talii", to: "/talie" }} />;

  const deck = query.data;
  // Talia „A1" złożona z samych pozycji A1 nie potrzebuje dwudziestu plakietek
  // z napisem A1.
  const mixedLevels = new Set(deck.items.map((item) => item.cefr_level)).size > 1;
  const error =
    start.error instanceof ApiError
      ? start.error.code === "NOTHING_TO_STUDY"
        ? "W tej talii nie ma teraz nic do powtórzenia."
        : start.error.message
      : null;

  return (
    <div className="px-4 pt-4">
      <Link to="/talie" className="mb-3 inline-flex items-center gap-1.5 text-sm text-ink-2">
        <span aria-hidden="true">←</span> Talie
      </Link>
      <h1 className="pt mb-3 text-2xl">
        {deck.icon && <span className="mr-1.5">{deck.icon}</span>}
        {deck.name}
      </h1>

      <Card>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[13.5px] text-ink-2">Postęp talii</div>
            <div className="mt-0.5 text-2xl font-bold tnum">
              {deck.learned} / {deck.total}
            </div>
          </div>
          {deck.cefr_level && <Pill tone="accent">{deck.cefr_level}</Pill>}
        </div>
        {deck.description && (
          // Opis wisiał osobno między kartą a przyciskiem — jedno zdanie bez
          // przynależności. Należy do nagłówka talii, więc siedzi w tej karcie.
          <p className="mt-2.5 border-t border-line pt-2.5 text-[13px] text-ink-2">
            {deck.description}
          </p>
        )}
        <div className="mt-3">
          <DeckBar deck={deck} />
        </div>
        <div className="mt-2 text-[11px] text-ink-3 tnum">
          {deck.learned} opanowanych · {deck.due} na dziś · {deck.untouched} nietkniętych
        </div>
      </Card>



      {error && (
        <div className="mt-3">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}

      <div className="mt-3">
        <Button onClick={() => start.mutate()} disabled={start.isPending}>
          {start.isPending ? "Przygotowuję…" : "Ucz się z tej talii"}
        </Button>
      </div>

      <Label className="mb-2 mt-5">Pozycje</Label>
      <div className="grid gap-2">
        {deck.items.map((item) => (
          <ItemRow key={item.id} item={item} showLevel={mixedLevels} />
        ))}
      </div>
    </div>
  );
}
