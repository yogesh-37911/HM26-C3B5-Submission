import { type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { useLang } from "../../lib/i18n";
import { Button } from "../ui/Primitives";

function Logomark() {
  return (
    <svg width="26" height="26" viewBox="0 0 32 32" fill="none" aria-hidden>
      <circle cx="16" cy="16" r="15" stroke="var(--color-gold-500)" strokeWidth="1.5" />
      <path
        d="M16 6c-4 4-6 7-6 11a6 6 0 0 0 12 0c0-4-2-7-6-11Z"
        fill="var(--color-teal-700)"
      />
      <circle cx="16" cy="17" r="2.4" fill="var(--color-gold-300)" />
    </svg>
  );
}

const NAV_BY_ROLE: Record<string, { to: string; label: string }[]> = {
  CITIZEN: [
    { to: "/citizen/report", label: "Report an issue" },
    { to: "/citizen/complaints", label: "My complaints" },
  ],
  OFFICER: [
    { to: "/officer/queue", label: "Queue" },
  ],
  FIELD_WORKER: [{ to: "/field/tasks", label: "My tasks" }],
  ADMIN: [
    { to: "/officer/queue", label: "Queue" },
    { to: "/admin/jurisdictions", label: "Jurisdictions" },
    { to: "/admin/demo", label: "Demo console" },
  ],
};

export function Shell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { lang, setLang } = useLang();
  const navigate = useNavigate();

  const roleNav = user ? NAV_BY_ROLE[user.role] || [] : [];

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-[var(--color-line)] bg-[var(--color-paper-raised)]/90 backdrop-blur sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-2.5 shrink-0">
            <Logomark />
            <span className="font-[family-name:var(--font-display)] text-lg text-[var(--color-ink)] leading-none">
              CivicPulse
            </span>
          </Link>

          <nav className="hidden md:flex items-center gap-1 text-sm">
            <NavLink
              to="/public"
              className={({ isActive }) =>
                `px-3 py-2 rounded-md transition-colors ${isActive ? "text-[var(--color-teal-700)] font-medium" : "text-[var(--color-ink-soft)] hover:text-[var(--color-ink)]"}`
              }
            >
              Public dashboard
            </NavLink>
            {roleNav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `px-3 py-2 rounded-md transition-colors ${isActive ? "text-[var(--color-teal-700)] font-medium" : "text-[var(--color-ink-soft)] hover:text-[var(--color-ink)]"}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <div className="flex rounded-full border border-[var(--color-line-strong)] p-0.5 text-xs">
              <button
                onClick={() => setLang("en")}
                className={`px-2.5 py-1 rounded-full transition-colors ${lang === "en" ? "bg-[var(--color-teal-700)] text-white" : "text-[var(--color-ink-soft)]"}`}
              >
                EN
              </button>
              <button
                onClick={() => setLang("kn")}
                className={`px-2.5 py-1 rounded-full transition-colors ${lang === "kn" ? "bg-[var(--color-teal-700)] text-white" : "text-[var(--color-ink-soft)]"}`}
              >
                ಕನ್ನಡ
              </button>
            </div>
            {user ? (
              <div className="flex items-center gap-2">
                <span className="hidden sm:block text-sm text-[var(--color-ink-soft)]">{user.full_name}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    logout();
                    navigate("/");
                  }}
                >
                  Log out
                </Button>
              </div>
            ) : (
              <Button size="sm" onClick={() => navigate("/login")}>
                Log in
              </Button>
            )}
          </div>
        </div>
      </header>
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-8">{children}</main>
      <footer className="border-t border-[var(--color-line)] py-6">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-[var(--color-ink-soft)]">
          <p>Mysuru CivicPulse - HackMysuru 1.0, Phase 1 submission.</p>
          <p>Demo dataset - synthetic data for HackMysuru demonstration.</p>
        </div>
      </footer>
    </div>
  );
}
