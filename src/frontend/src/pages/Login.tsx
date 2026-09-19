import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Button, Callout } from "../components/ui/Primitives";
import { ApiError } from "../lib/api";

const DEMO_ACCOUNTS = [
  { email: "citizen@demo.local", label: "Citizen" },
  { email: "officer@demo.local", label: "Officer (Ward 42)" },
  { email: "worker@demo.local", label: "Field worker" },
  { email: "admin@demo.local", label: "Admin" },
];

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-sm mx-auto py-8">
      <h1 className="font-[family-name:var(--font-display)] text-2xl mb-1">Log in</h1>
      <p className="text-sm text-[var(--color-ink-soft)] mb-6">Access your CivicPulse account.</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-[var(--color-ink-soft)] mb-1">Email</label>
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
          <label className="block text-xs font-medium text-[var(--color-ink-soft)] mb-1">Password</label>
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
          {busy ? "Logging in..." : "Log in"}
        </Button>
      </form>

      <div className="mt-8 border-t border-[var(--color-line)] pt-5">
        <p className="text-xs text-[var(--color-ink-soft)] mb-2">
          Demo accounts (password: <code className="font-[family-name:var(--font-mono)]">CivicPulse@2026</code>)
        </p>
        <div className="flex flex-wrap gap-2">
          {DEMO_ACCOUNTS.map((acc) => (
            <button
              key={acc.email}
              type="button"
              onClick={() => {
                setEmail(acc.email);
                setPassword("CivicPulse@2026");
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
