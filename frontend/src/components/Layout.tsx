import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useSession } from "@/store/session";
import { cx } from "./ui";

const TABS = [
  {
    to: "/",
    label: "Dziś",
    icon: (
      <path d="M3 10.5L12 4l9 6.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />
    ),
  },
  {
    to: "/slownik",
    label: "Słownik",
    icon: (
      <>
        <path d="M4 5a2 2 0 0 1 2-2h12v18H6a2 2 0 0 1-2-2z" />
        <path d="M8 7h7M8 11h7" />
      </>
    ),
  },
  {
    to: "/talie",
    label: "Talie",
    icon: (
      <>
        <rect x="3" y="6" width="13" height="14" rx="2" />
        <path d="M8 3h11a2 2 0 0 1 2 2v11" />
      </>
    ),
  },
  {
    to: "/quizy",
    label: "Quizy",
    icon: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M9 9a3 3 0 1 1 4 2.8c-.7.3-1 .9-1 1.7v.4" />
        <circle cx="12" cy="17.4" r="0.6" fill="currentColor" />
      </>
    ),
  },
  {
    to: "/postep",
    label: "Postęp",
    icon: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  },
];

export function AppLayout() {
  const location = useLocation();
  // Brak zasięgu widać teraz wszędzie, nie tylko w trakcie sesji. Bez tego
  // ekran talii po prostu nie doczytywał się w nieskończoność i wyglądał na
  // zepsuty, zamiast powiedzieć, o co chodzi.
  const online = useSession((state) => state.online);

  return (
    <div className="mx-auto flex min-h-dvh max-w-[560px] flex-col bg-surface">
      {!online && (
        <div
          role="status"
          className="safe-top bg-warm/15 px-4 pb-2 text-center text-[12px] text-ink-2"
        >
          <span aria-hidden="true">✈ </span>
          Brak połączenia — postęp zapisuje się na urządzeniu i doleci później.
        </div>
      )}
      <main className="flex-1 pb-24">
        <Outlet />
      </main>
      <nav
        className="safe-bottom fixed inset-x-0 bottom-0 z-20 mx-auto grid max-w-[560px] grid-cols-5 border-t border-line bg-surface pt-2"
        aria-label="Nawigacja główna"
      >
        {TABS.map((tab) => {
          const active =
            tab.to === "/" ? location.pathname === "/" : location.pathname.startsWith(tab.to);
          return (
            <NavLink
              key={tab.to}
              to={tab.to}
              aria-current={active ? "page" : undefined}
              className={cx(
                "grid justify-items-center gap-0.5 rounded-lg py-1 text-[11px] font-semibold",
                active ? "text-accent" : "text-ink-3",
              )}
            >
              <svg
                viewBox="0 0 24 24"
                className="h-[21px] w-[21px]"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                {tab.icon}
              </svg>
              {tab.label}
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}

/** Study and summary run without the tab bar — nothing should compete with the
 *  question on screen. */
export function FullScreenLayout() {
  return (
    <div className="mx-auto flex min-h-dvh max-w-[560px] flex-col bg-surface">
      <Outlet />
    </div>
  );
}
