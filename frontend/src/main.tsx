import { StrictMode, Suspense, lazy, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";

import { AppLayout, FullScreenLayout } from "@/components/Layout";
import { Spinner } from "@/components/ui";
import { LoginPage } from "@/pages/Login";
import { TodayPage } from "@/pages/Today";

/**
 * Ekrany doczytywane na żądanie.
 *
 * Logowanie i „Dziś" idą w głównej paczce, bo od nich zaczyna się każde
 * uruchomienie. Reszta — słownik, talie, quizy, wykresy postępu, generowanie
 * z AI — to kod, którego pierwszy ekran nie potrzebuje, a przy starcie
 * kosztował ponad połowę pobranego JavaScriptu.
 */
const AddItemPage = lazy(() => import("@/pages/AddItem").then((m) => ({ default: m.AddItemPage })));
const DecksPage = lazy(() => import("@/pages/Decks").then((m) => ({ default: m.DecksPage })));
const DeckDetailPage = lazy(() =>
  import("@/pages/Decks").then((m) => ({ default: m.DeckDetailPage })),
);
const DictionaryPage = lazy(() =>
  import("@/pages/Dictionary").then((m) => ({ default: m.DictionaryPage })),
);
const ItemDetailPage = lazy(() =>
  import("@/pages/Dictionary").then((m) => ({ default: m.ItemDetailPage })),
);
const ProgressPage = lazy(() =>
  import("@/pages/Progress").then((m) => ({ default: m.ProgressPage })),
);
const QuizzesPage = lazy(() => import("@/pages/Quiz").then((m) => ({ default: m.QuizzesPage })));
const QuizAttemptPage = lazy(() =>
  import("@/pages/Quiz").then((m) => ({ default: m.QuizAttemptPage })),
);
const QuizResultPage = lazy(() =>
  import("@/pages/Quiz").then((m) => ({ default: m.QuizResultPage })),
);
const SettingsPage = lazy(() =>
  import("@/pages/Settings").then((m) => ({ default: m.SettingsPage })),
);
const StudyPage = lazy(() => import("@/pages/Study").then((m) => ({ default: m.StudyPage })));
const SummaryPage = lazy(() => import("@/pages/Summary").then((m) => ({ default: m.SummaryPage })));
const LessonsPage = lazy(() => import("@/pages/Lessons").then((m) => ({ default: m.LessonsPage })));
const LessonPage = lazy(() => import("@/pages/Lessons").then((m) => ({ default: m.LessonPage })));
import { AuthProvider, useAuth } from "@/store/auth";
import { watchConnection } from "@/store/session";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 },
  },
});

/**
 * Sprząta pamięć podręczną nagrań z poprzedniej wersji.
 *
 * Tamta zdążyła zapisać odpowiedzi nieprzezroczyste o zerowej długości —
 * telefon uznawał je za gotowe nagrania i odtwarzał ciszę. Nowa nazwa sprawia,
 * że nikt już do nich nie zagląda, ale bez tego zostałyby na urządzeniu
 * na rok. Usunięcie jest bezpieczne: nagrania pobiorą się ponownie przy
 * pierwszym odtworzeniu.
 */
function dropPoisonedAudioCache() {
  if (typeof caches === "undefined") return;
  void caches.delete("porto-audio");
}

function GrammarRedirect() {
  const { slug } = useParams();
  return <Navigate to={`/lekcje/${slug ?? ""}`} replace />;
}

function Shell() {
  const { user, ready } = useAuth();

  // Dosyłanie zaległych odpowiedzi żyje poza ekranem sesji: użytkownik może
  // zamknąć aplikację w metrze i otworzyć ją następnego dnia w domu.
  useEffect(() => watchConnection(), []);
  useEffect(dropPoisonedAudioCache, []);

  if (!ready) {
    return (
      <div className="grid min-h-dvh place-content-center">
        <Spinner label="Wczytuję…" />
      </div>
    );
  }

  if (!user) return <LoginPage />;

  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<TodayPage />} />
        <Route path="/slownik" element={<DictionaryPage />} />
        <Route path="/slownik/dodaj" element={<AddItemPage />} />
        <Route path="/slownik/:itemId" element={<ItemDetailPage />} />
        <Route path="/talie" element={<DecksPage />} />
        <Route path="/talie/:deckId" element={<DeckDetailPage />} />
        <Route path="/lekcje" element={<LessonsPage />} />
        <Route path="/lekcje/:slug" element={<LessonPage />} />
        {/* Stare adresy z czasów samej gramatyki — zakładki i historia na
            telefonie wciąż mogą do nich prowadzić. */}
        <Route path="/gramatyka" element={<Navigate to="/lekcje?dzial=gramatyka" replace />} />
        <Route path="/gramatyka/:slug" element={<GrammarRedirect />} />
        <Route path="/quizy" element={<QuizzesPage />} />
        <Route path="/postep" element={<ProgressPage />} />
        <Route path="/ustawienia" element={<SettingsPage />} />
      </Route>
      <Route element={<FullScreenLayout />}>
        <Route path="/nauka" element={<StudyPage />} />
        <Route path="/podsumowanie" element={<SummaryPage />} />
        <Route path="/quizy/:attemptId" element={<QuizAttemptPage />} />
        <Route path="/quizy/:attemptId/wynik" element={<QuizResultPage />} />
      </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Shell />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
