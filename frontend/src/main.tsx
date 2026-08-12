import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppLayout, FullScreenLayout } from "@/components/Layout";
import { Spinner } from "@/components/ui";
import { DeckDetailPage, DecksPage } from "@/pages/Decks";
import { DictionaryPage, ItemDetailPage } from "@/pages/Dictionary";
import { LoginPage } from "@/pages/Login";
import { ProgressPage } from "@/pages/Progress";
import { SettingsPage } from "@/pages/Settings";
import { StudyPage } from "@/pages/Study";
import { SummaryPage } from "@/pages/Summary";
import { TodayPage } from "@/pages/Today";
import { AuthProvider, useAuth } from "@/store/auth";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 },
  },
});

function Shell() {
  const { user, ready } = useAuth();

  if (!ready) {
    return (
      <div className="grid min-h-dvh place-content-center">
        <Spinner label="Wczytuję…" />
      </div>
    );
  }

  if (!user) return <LoginPage />;

  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<TodayPage />} />
        <Route path="/slownik" element={<DictionaryPage />} />
        <Route path="/slownik/:itemId" element={<ItemDetailPage />} />
        <Route path="/talie" element={<DecksPage />} />
        <Route path="/talie/:deckId" element={<DeckDetailPage />} />
        <Route path="/postep" element={<ProgressPage />} />
        <Route path="/ustawienia" element={<SettingsPage />} />
      </Route>
      <Route element={<FullScreenLayout />}>
        <Route path="/nauka" element={<StudyPage />} />
        <Route path="/podsumowanie" element={<SummaryPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
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
