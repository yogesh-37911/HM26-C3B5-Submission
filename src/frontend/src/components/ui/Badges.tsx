import type { ReactNode } from "react";

type Tone = "danger" | "warn" | "good" | "info" | "neutral" | "plum";

const toneClasses: Record<Tone, string> = {
  danger: "bg-[var(--color-danger-100)] text-[var(--color-danger-700)] border-[var(--color-danger-500)]/30",
  warn: "bg-[var(--color-warn-100)] text-[var(--color-warn-700)] border-[var(--color-warn-500)]/30",
  good: "bg-[var(--color-good-100)] text-[var(--color-good-700)] border-[var(--color-good-500)]/30",
  info: "bg-[var(--color-info-100)] text-[var(--color-info-700)] border-[var(--color-info-500)]/30",
  neutral: "bg-[var(--color-paper-raised)] text-[var(--color-ink-soft)] border-[var(--color-line-strong)]",
  plum: "bg-[var(--color-plum-500)]/10 text-[var(--color-plum-700)] border-[var(--color-plum-500)]/30",
};

function Pill({ tone, children, dot }: { tone: Tone; children: ReactNode; dot?: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium leading-none ${toneClasses[tone]}`}
    >
      {dot && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function RiskBadge({ level, score }: { level: string; score?: number }) {
  const tone: Tone = level === "HIGH" ? "danger" : level === "MODERATE" ? "warn" : "good";
  return (
    <Pill tone={tone} dot>
      {level === "HIGH" && score !== undefined && score >= 85 ? "pulse-dot inline-block" : ""}
      Risk {level}
      {score !== undefined ? ` \u00b7 ${Math.round(score)}` : ""}
    </Pill>
  );
}

export function PriorityBadge({ level }: { level: string }) {
  const tone: Tone =
    level === "CRITICAL" ? "danger" : level === "HIGH" ? "warn" : level === "MEDIUM" ? "info" : "neutral";
  return <Pill tone={tone}>{level}</Pill>;
}

export function VerificationBadge({ status }: { status: string }) {
  const tone: Tone =
    status === "VERIFIED" ? "good" : status === "PLAUSIBLE" ? "info" : status === "NEEDS_REVIEW" ? "warn" : "danger";
  const label = status.replace("_", " ");
  return <Pill tone={tone}>{label}</Pill>;
}

const STATUS_LABELS: Record<string, string> = {
  SUBMITTED: "Submitted",
  VALIDATING: "Validating",
  ROUTED: "Routed",
  ASSIGNED: "Assigned",
  IN_PROGRESS: "In progress",
  FIELD_VERIFIED: "Field verified",
  RESOLVED: "Resolved",
  REOPENED: "Reopened",
  REJECTED: "Rejected",
};

export function StatusBadge({ status }: { status: string }) {
  const tone: Tone =
    status === "RESOLVED"
      ? "good"
      : status === "REJECTED"
        ? "neutral"
        : status === "REOPENED"
          ? "danger"
          : status === "IN_PROGRESS" || status === "FIELD_VERIFIED"
            ? "info"
            : "plum";
  return <Pill tone={tone}>{STATUS_LABELS[status] || status}</Pill>;
}

export function SlaBadge({ breachRisk, remainingHours, breached }: { breachRisk: string; remainingHours: number; breached: boolean }) {
  const tone: Tone = breached ? "danger" : breachRisk === "HIGH" ? "warn" : breachRisk === "MODERATE" ? "info" : "good";
  return (
    <Pill tone={tone} dot>
      {breached ? "SLA overdue" : `SLA ${remainingHours.toFixed(0)}h left`}
    </Pill>
  );
}
