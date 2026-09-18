import type { TimelineEvent } from "../../lib/types";
import { formatDateTime } from "../../lib/format";

const EVENT_ICONS: Record<string, string> = {
  SUBMITTED: "\u25CF",
  ROUTED: "\u2192",
  VERIFIED: "\u2713",
  DUPLICATE_CHECK: "\u29C9",
  PRIORITY_CALCULATED: "\u25B2",
  RISK_CALCULATED: "\u26A0",
  ASSIGNED: "\u2934",
  FIELD_STARTED: "\u25B6",
  FIELD_VERIFIED: "\u2713",
  FIELD_BLOCKED: "\u2715",
  FIELD_NOTE: "\u270E",
  STATUS_CHANGE: "\u21BB",
  REOPENED: "\u21BA",
  EVIDENCE_ADDED: "\u2398",
  EVIDENCE_FLAGGED: "\u26A0",
  FOLLOWUP: "\u2709",
};

export function Timeline({ events }: { events: TimelineEvent[] }) {
  if (!events.length) {
    return <p className="text-sm text-[var(--color-ink-soft)]">No activity recorded yet.</p>;
  }
  return (
    <ol className="relative border-l border-[var(--color-line-strong)] ml-2">
      {events.map((ev) => (
        <li key={ev.id} className="mb-5 ml-5 last:mb-0">
          <span className="absolute flex h-5 w-5 items-center justify-center rounded-full bg-[var(--color-paper-raised)] border border-[var(--color-line-strong)] -left-2.5 text-[10px] text-[var(--color-teal-700)]">
            {EVENT_ICONS[ev.event_type] || "\u2022"}
          </span>
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-sm text-[var(--color-ink)]">{ev.note}</p>
            <time className="text-xs text-[var(--color-ink-soft)] shrink-0 font-[family-name:var(--font-mono)]">
              {formatDateTime(ev.at)}
            </time>
          </div>
          <p className="text-xs text-[var(--color-ink-soft)] mt-0.5">{ev.actor}</p>
        </li>
      ))}
    </ol>
  );
}
