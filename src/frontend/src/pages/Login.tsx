import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { Button, Callout } from "../components/ui/Primitives";
import { ApiError } from "../lib/api";

export function Login() {
  const { login } = useAuth();
  const { lang, setLang, t } = useLang();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const demoAccounts = [
    { email: "citizen@demo.local", label: t.roleCitizen },
    { email: "officer@demo.local", label: t.roleOfficer },
    { email: "worker@demo.local", label: t.roleFieldWorker },
    { email: "admin@demo.local", label: t.roleAdmin },
  ];

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const user = await login(email, password);
      const dest =
        user.role === "CITIZEN"
          ? "/citizen/complaints"
          : user.role === "FIELD_WORKER"
            ? "/field/tasks"
            : "/officer/queue";
      navigate(dest);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.message === "Invalid email or password") {
          setError(t.invalidCredentials);
        } else if (err.message === "Account is disabled") {
          setError(t.accountDisabled);
        } else {
          setError(err.message);
        }
      } else {
        setError(t.somethingWentWrong);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-sm mx-auto py-8">
      {/* Language Switcher on Login Page */}
      <div className="flex items-center justify-between mb-5 pb-3 border-b border-[var(--color-line)]">
        <span className="text-xs text-[var(--color-ink-soft)] flex items-center gap-1.5 font-medium">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="2" y1="12" x2="22" y2="12"></line>
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
          </svg>
          {lang === "kn" ? "ಭಾಷೆ / Language" : "Language / ಭಾಷೆ"}
        </span>
        <div className="inline-flex rounded-full border border-[var(--color-line-strong)] p-0.5 text-xs bg-[var(--color-paper-raised)]">
          <button
            type="button"
            onClick={() => setLang("en")}
            className={`px-3 py-1 rounded-full font-medium transition-all ${
              lang === "en"
                ? "bg-[var(--color-teal-700)] text-white shadow-sm"
                : "text-[var(--color-ink-soft)] hover:text-[var(--color-ink)]"
            }`}
          >
            English
          </button>
          <button
            type="button"
            onClick={() => setLang("kn")}
            className={`px-3 py-1 rounded-full font-medium transition-all ${
              lang === "kn"
                ? "bg-[var(--color-teal-700)] text-white shadow-sm"
                : "text-[var(--color-ink-soft)] hover:text-[var(--color-ink)]"
            }`}
          >
            ಕನ್ನಡ
          </button>
        </div>
      </div>

      <h1 className="font-[family-name:var(--font-display)] text-2xl mb-1">{t.login}</h1>
      <p className="text-sm text-[var(--color-ink-soft)] mb-6">{t.loginSubtitle}</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-[var(--color-ink-soft)] mb-1">{t.email}</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-3 py-2.5 text-sm outline-none focus:border-[var(--color-teal-600)]"
            placeholder="you@demo.local"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-[var(--color-ink-soft)] mb-1">{t.password}</label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-3 py-2.5 text-sm outline-none focus:border-[var(--color-teal-600)]"
          />
        </div>
        {error && <Callout tone="danger">{error}</Callout>}
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? t.loggingIn : t.login}
        </Button>
      </form>

      <div className="mt-8 border-t border-[var(--color-line)] pt-5">
        <p className="text-xs text-[var(--color-ink-soft)] mb-2">
          {t.demoAccountsPrefix} <code className="font-[family-name:var(--font-mono)]">CivicPulse@2026</code>)
        </p>
        <div className="flex flex-wrap gap-2">
          {demoAccounts.map((acc) => (
            <button
              key={acc.email}
              type="button"
              onClick={() => {
                setEmail(acc.email);
                setPassword("CivicPulse@2026");
                setError(null);
              }}
              className="text-xs px-2.5 py-1.5 rounded-full border border-[var(--color-line-strong)] text-[var(--color-ink-soft)] hover:border-[var(--color-teal-600)] hover:text-[var(--color-teal-700)] transition-colors"
            >
              {acc.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
