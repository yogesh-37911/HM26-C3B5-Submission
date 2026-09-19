import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import type { ComplaintSummary } from "../../lib/types";
import { SectionHeading, EmptyState, Spinner, Button } from "../../components/ui/Primitives";
import { RiskBadge, PriorityBadge, StatusBadge, SlaBadge } from "../../components/ui/Badges";
import { relativeTime } from "../../lib/format";
import { useNavigate } from "react-router-dom";

export function MyComplaints() {
  const [items, setItems] = useState<ComplaintSummary[] | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api
      .get<{ items: ComplaintSummary[] }>("/api/complaints", { mine: true, page_size: 50, sort: "created_at" })
      .then((r) => setItems(r.items));
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <SectionHeading title="My complaints" description="Track every report you've filed and what's happening next." />
        <Button onClick={() => navigate("/citizen/report")}>Report an issue</Button>
      </div>

      {items === null && <Spinner />}

      {items !== null && items.length === 0 && (
        <EmptyState
          title="No complaints yet"
          description="Once you report an issue, you'll be able to track its status, priority and timeline here."
          action={<Button onClick={() => navigate("/citizen/report")}>Report your first issue</Button>}
        />
      )}

      <div className="space-y-0">
        {items?.map((c) => (
          <Link
            key={c.id}
            to={`/citizen/complaints/${c.public_id}`}
            className="block border-b border-[var(--color-line)] py-4 hover:bg-[var(--color-paper-raised)] transition-colors -mx-3 px-3 rounded-md"
          >
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="min-w-0">
                <p className="text-xs font-[family-name:var(--font-mono)] text-[var(--color-ink-soft)]">{c.public_id}</p>
                <p className="font-medium text-[var(--color-ink)] mt-0.5">{c.title}</p>
                <p className="text-xs text-[var(--color-ink-soft)] mt-1">
                  {c.category.name_en} &middot; {c.jurisdiction_name || "Routing pending"} &middot; {relativeTime(c.created_at)}
                </p>
              </div>
              <div className="flex flex-wrap gap-1.5 shrink-0">
                <StatusBadge status={c.status} />
                <PriorityBadge level={c.priority_level} />
                <RiskBadge level={c.risk_level} />
                <SlaBadge breachRisk={c.sla.breach_risk} remainingHours={c.sla.remaining_hours} breached={c.sla.breached} />
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
