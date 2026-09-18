import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { Factor } from "../../lib/types";

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; size?: "sm" | "md" }) {
  const base = "inline-flex items-center justify-center gap-2 font-medium transition-colors rounded-md disabled:opacity-50 disabled:cursor-not-allowed";
  const sizes = size === "sm" ? "px-3 py-1.5 text-sm" : "px-4 py-2.5 text-sm";
  const variants: Record<string, string> = {
    primary: "bg-[var(--color-teal-700)] text-[var(--color-paper-raised)] hover:bg-[var(--color-teal-600)]",
    secondary:
      "bg-transparent text-[var(--color-teal-700)] border border-[var(--color-teal-700)]/40 hover:bg-[var(--color-teal-100)]",
    ghost: "bg-transparent text-[var(--color-ink-soft)] hover:bg-[var(--color-paper-raised)]",
    danger: "bg-[var(--color-danger-500)] text-white hover:bg-[var(--color-danger-700)]",
  };
  return <button className={`${base} ${sizes} ${variants[variant]} ${className}`} {...props} />;
}

export function SectionHeading({ eyebrow, title, description }: { eyebrow?: string; title: string; description?: string }) {
  return (
    <div className="mb-5">
      {eyebrow && <p className="text-xs font-medium tracking-wide text-[var(--color-teal-600)] mb-1">{eyebrow}</p>}
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-[var(--color-ink)]">{title}</h2>
      {description && <p className="mt-1 text-sm text-[var(--color-ink-soft)] max-w-prose">{description}</p>}
    </div>
  );
}

export function StatCard({ label, value, sub, tone = "neutral" }: { label: string; value: ReactNode; sub?: string; tone?: "neutral" | "danger" | "warn" | "good" }) {
  const toneColor =
    tone === "danger"
      ? "text-[var(--color-danger-600,var(--color-danger-700))]"
      : tone === "warn"
        ? "text-[var(--color-warn-700)]"
        : tone === "good"
          ? "text-[var(--color-good-700)]"
          : "text-[var(--color-ink)]";
  return (
    <div className="border-t-2 border-[var(--color-line-strong)] pt-3">
      <p className="text-xs text-[var(--color-ink-soft)]">{label}</p>
      <p className={`font-[family-name:var(--font-display)] text-3xl mt-1 ${toneColor}`}>{value}</p>
      {sub && <p className="text-xs text-[var(--color-ink-soft)] mt-1">{sub}</p>}
    </div>
  );
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="border border-dashed border-[var(--color-line-strong)] rounded-lg py-12 px-6 text-center">
      <p className="font-medium text-[var(--color-ink)]">{title}</p>
      {description && <p className="text-sm text-[var(--color-ink-soft)] mt-1 max-w-sm mx-auto">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-[var(--color-ink-soft)] py-6 justify-center">
      <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
        <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      </svg>
      {label || "Loading..."}
    </div>
  );
}

export function FactorBar({ factor }: { factor: Factor }) {
  const pct = factor.max_points > 0 ? Math.min(100, (factor.points / factor.max_points) * 100) : 0;
  return (
    <div className="py-2.5 border-b border-[var(--color-line)] last:border-0">
      <div className="flex items-baseline justify-between gap-4">
        <p className="text-sm font-medium text-[var(--color-ink)]">{factor.label}</p>
        <p className="text-xs font-[family-name:var(--font-mono)] text-[var(--color-ink-soft)] shrink-0">
          {factor.points.toFixed(1)} / {factor.max_points}
        </p>
      </div>
      <div className="mt-1.5 h-1.5 rounded-full bg-[var(--color-line)] overflow-hidden">
        <div
          className="h-full rounded-full bg-[var(--color-gold-500)]"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-[var(--color-ink-soft)] mt-1.5">{factor.detail}</p>
    </div>
  );
}

export function Callout({ tone = "info", children }: { tone?: "info" | "warn" | "danger"; children: ReactNode }) {
  const styles =
    tone === "danger"
      ? "bg-[var(--color-danger-100)] text-[var(--color-danger-700)]"
      : tone === "warn"
        ? "bg-[var(--color-warn-100)] text-[var(--color-warn-700)]"
        : "bg-[var(--color-info-100)] text-[var(--color-info-700)]";
  return <div className={`rounded-md px-3.5 py-2.5 text-sm ${styles}`}>{children}</div>;
}
