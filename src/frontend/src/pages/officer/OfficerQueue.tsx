import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import type { ComplaintSummary } from "../../lib/types";
import { SectionHeading, Spinner, StatCard, EmptyState } from "../../components/ui/Primitives";
import { RiskBadge, PriorityBadge, StatusBadge, SlaBadge } from "../../components/ui/Badges";
import { formatHours, relativeTime } from "../../lib/format";

const SORTS = [
  { value: "risk", label: "Risk" },
  { value: "priority", label: "Priority" },
  { value: "age", label: "Age" },
  { value: "sla", label: "SLA due" },
];

export function OfficerQueue() {
  const [items, setItems] = useState<ComplaintSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [sort, setSort] = useState("risk");
  const [statusFilter, setStatusFilter] = useState("");
  const [unassignedOnly, setUnassignedOnly] = useState(false);
  const [slaBreachedOnly, setSlaBreachedOnly] = useState(false);

  useEffect(() => {
    setItems(null);
    api
      .get<{ items: ComplaintSummary[]; total: number }>("/api/complaints", {
        sort,
        order: "desc",
        page_size: 40,
        status: statusFilter || undefined,
        unassigned: unassignedOnly || undefined,
        sla_breached: slaBreachedOnly || undefined,
      })
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
      });
  }, [sort, statusFilter, unassignedOnly, slaBreachedOnly]);

  const openItems = items?.filter((c) => !["RESOLVED", "REJECTED"].includes(c.status)) ?? [];
  const counts = {
    open: openItems.length,
    critical: openItems.filter((c) => c.priority_level === "CRITICAL").length,
    highRisk: openItems.filter((c) => c.risk_level === "HIGH").length,
    slaBreach: openItems.filter((c) => c.sla.breached).length,
    unassigned: openItems.filter((c) => !c.assigned).length,
    reopened: openItems.filter((c) => c.status === "REOPENED").length,
  };

  return (
    <div>
      <SectionHeading eyebrow="Officer" title="Complaint queue" description={`${total} complaints in view.`} />

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-5 mb-8">
        <StatCard label="Open" value={counts.open} />
        <StatCard label="Critical" value={counts.critical} tone="danger" />
        <StatCard label="High risk" value={counts.highRisk} tone="danger" />
        <StatCard label="SLA breach" value={counts.slaBreach} tone="warn" />
        <StatCard label="Unassigned" value={counts.unassigned} tone="warn" />
        <StatCard label="Reopened" value={counts.reopened} tone="warn" />
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-4 text-sm">
        <label className="flex items-center gap-1.5 text-[var(--color-ink-soft)]">
          Sort by
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-2 py-1.5 text-sm"
          >
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-2 py-1.5 text-sm"
        >
          <option value="">All statuses</option>
          <option value="ROUTED">Routed</option>
          <option value="ASSIGNED">Assigned</option>
          <option value="IN_PROGRESS">In progress</option>
          <option value="FIELD_VERIFIED">Field verified</option>
          <option value="REOPENED">Reopened</option>
          <option value="RESOLVED">Resolved</option>
        </select>
        <label className="flex items-center gap-1.5 text-[var(--color-ink-soft)]">
          <input type="checkbox" checked={unassignedOnly} onChange={(e) => setUnassignedOnly(e.target.checked)} />
          Unassigned only
        </label>
        <label className="flex items-center gap-1.5 text-[var(--color-ink-soft)]">
          <input type="checkbox" checked={slaBreachedOnly} onChange={(e) => setSlaBreachedOnly(e.target.checked)} />
          SLA breached only
        </label>
      </div>

      {items === null && <Spinner />}
      {items !== null && items.length === 0 && <EmptyState title="No complaints match these filters" />}

      {items && items.length > 0 && (
        <div className="overflow-x-auto -mx-4 sm:mx-0">
          <table className="w-full text-sm min-w-[860px]">
            <thead>
              <tr className="text-left text-xs text-[var(--color-ink-soft)] border-b border-[var(--color-line-strong)]">
                <th className="py-2 px-3 font-medium">Complaint</th>
                <th className="py-2 px-3 font-medium">Category</th>
                <th className="py-2 px-3 font-medium">Ward</th>
                <th className="py-2 px-3 font-medium">Age</th>
                <th className="py-2 px-3 font-medium">Priority</th>
                <th className="py-2 px-3 font-medium">Risk</th>
                <th className="py-2 px-3 font-medium">Assigned</th>
                <th className="py-2 px-3 font-medium">SLA</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} className="border-b border-[var(--color-line)] hover:bg-[var(--color-paper-raised)]">
                  <td className="py-2.5 px-3">
                    <Link to={`/officer/complaints/${c.public_id}`} className="block">
                      <p className="font-[family-name:var(--font-mono)] text-xs text-[var(--color-teal-700)]">
                        {c.public_id}
                      </p>
                      <p className="text-[var(--color-ink)]">{c.title}</p>
                    </Link>
                  </td>
                  <td className="py-2.5 px-3 text-[var(--color-ink-soft)]">{c.category.name_en}</td>
                  <td className="py-2.5 px-3 text-[var(--color-ink-soft)]">{c.ward ?? "-"}</td>
                  <td className="py-2.5 px-3 text-[var(--color-ink-soft)]">{formatHours(c.age_hours)}</td>
                  <td className="py-2.5 px-3">
                    <PriorityBadge level={c.priority_level} />
                  </td>
                  <td className="py-2.5 px-3">
                    <RiskBadge level={c.risk_level} score={c.risk_score} />
                  </td>
                  <td className="py-2.5 px-3">
                    {c.assigned ? (
                      <StatusBadge status="ASSIGNED" />
                    ) : (
                      <span className="text-xs text-[var(--color-warn-700)]">Unassigned</span>
                    )}
                  </td>
                  <td className="py-2.5 px-3">
                    <SlaBadge
                      breachRisk={c.sla.breach_risk}
                      remainingHours={c.sla.remaining_hours}
                      breached={c.sla.breached}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {items && items.length > 0 && (
        <p className="text-xs text-[var(--color-ink-soft)] mt-3">
          Showing {items.length} of {total}. Newest activity {items[0] ? relativeTime(items[0].last_action_at) : ""}.
        </p>
      )}
    </div>
  );
}
