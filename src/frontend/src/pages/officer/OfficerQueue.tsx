import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import type { ComplaintSummary } from "../../lib/types";
import { SectionHeading, Spinner, StatCard, EmptyState, Button } from "../../components/ui/Primitives";
import { RiskBadge, PriorityBadge, StatusBadge, SlaBadge } from "../../components/ui/Badges";
import { formatHours } from "../../lib/format";
import { useLang } from "../../lib/i18n";

export function OfficerQueue() {
  const { lang, t } = useLang();
  const [items, setItems] = useState<ComplaintSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(40);

  const [sort, setSort] = useState("risk");
  const [statusFilter, setStatusFilter] = useState("");
  const [wardFilter, setWardFilter] = useState("");
  const [unassignedOnly, setUnassignedOnly] = useState(false);
  const [slaBreachedOnly, setSlaBreachedOnly] = useState(false);

  const sorts = [
    { value: "risk", label: t.riskCol },
    { value: "priority", label: t.priorityCol },
    { value: "age", label: t.ageCol },
    { value: "sla", label: t.slaCol },
  ];

  useEffect(() => {
    setItems(null);
    api
      .get<{ items: ComplaintSummary[]; total: number; pages: number; page: number }>("/api/complaints", {
        page,
        page_size: pageSize,
        sort,
        order: "desc",
        status: statusFilter || undefined,
        ward: wardFilter ? Number(wardFilter) : undefined,
        unassigned: unassignedOnly || undefined,
        sla_breached: slaBreachedOnly || undefined,
      })
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
        setPages(r.pages || 1);
      });
  }, [page, pageSize, sort, statusFilter, wardFilter, unassignedOnly, slaBreachedOnly]);

  const openItems = items?.filter((c) => !["RESOLVED", "REJECTED"].includes(c.status)) ?? [];
  const counts = {
    open: openItems.length,
    critical: openItems.filter((c) => c.priority_level === "CRITICAL").length,
    highRisk: openItems.filter((c) => c.risk_level === "HIGH").length,
    slaBreach: openItems.filter((c) => c.sla.breached).length,
    unassigned: openItems.filter((c) => !c.assigned).length,
    reopened: openItems.filter((c) => c.status === "REOPENED").length,
  };

  const startIdx = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const endIdx = Math.min(page * pageSize, total);

  return (
    <div>
      <SectionHeading
        eyebrow={t.roleOfficer}
        title={t.officerQueue}
        description={lang === "kn" ? `${total} ದೂರುಗಳು ಲಭ್ಯವಿವೆ.` : `${total} complaints in view across Mysuru.`}
      />

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
        <StatCard label={t.openStat} value={counts.open} />
        <StatCard label={t.criticalStat} value={counts.critical} tone="danger" />
        <StatCard label={t.highRiskStat} value={counts.highRisk} tone="danger" />
        <StatCard label={t.slaBreachStat} value={counts.slaBreach} tone="warn" />
        <StatCard label={t.unassignedStat} value={counts.unassigned} tone="warn" />
        <StatCard label={t.reopenedStat} value={counts.reopened} tone="warn" />
      </div>

      {/* Filter and Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 text-sm bg-[var(--color-paper-raised)] p-3 rounded-lg border border-[var(--color-line)]">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-[var(--color-ink-soft)] font-medium">
            {t.sortBy}
            <select
              value={sort}
              onChange={(e) => { setSort(e.target.value); setPage(1); }}
              className="rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper)] px-2 py-1 text-xs outline-none"
            >
              {sorts.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>

          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            className="rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper)] px-2 py-1 text-xs outline-none"
          >
            <option value="">{t.allStatuses}</option>
            <option value="SUBMITTED">Submitted</option>
            <option value="ROUTED">Routed</option>
            <option value="ASSIGNED">Assigned</option>
            <option value="IN_PROGRESS">In progress</option>
            <option value="FIELD_VERIFIED">Field verified</option>
            <option value="REOPENED">Reopened</option>
            <option value="RESOLVED">Resolved</option>
          </select>

          {/* Ward filter dropdown */}
          <select
            value={wardFilter}
            onChange={(e) => { setWardFilter(e.target.value); setPage(1); }}
            className="rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper)] px-2 py-1 text-xs outline-none"
          >
            <option value="">{t.allWards}</option>
            {Array.from({ length: 65 }, (_, i) => i + 1).map((w) => (
              <option key={w} value={String(w)}>
                {lang === "kn" ? `ವಾರ್ಡ್ ${w}` : `Ward ${w}`}
              </option>
            ))}
          </select>

          <label className="flex items-center gap-1 text-xs text-[var(--color-ink-soft)] cursor-pointer">
            <input
              type="checkbox"
              checked={unassignedOnly}
              onChange={(e) => { setUnassignedOnly(e.target.checked); setPage(1); }}
              className="rounded"
            />
            {t.unassignedOnly}
          </label>
          <label className="flex items-center gap-1 text-xs text-[var(--color-ink-soft)] cursor-pointer">
            <input
              type="checkbox"
              checked={slaBreachedOnly}
              onChange={(e) => { setSlaBreachedOnly(e.target.checked); setPage(1); }}
              className="rounded"
            />
            {t.slaBreachedOnly}
          </label>
        </div>

        {/* Page size dropdown */}
        <div className="flex items-center gap-1.5 text-xs text-[var(--color-ink-soft)]">
          <span>{t.showing}</span>
          <select
            value={pageSize}
            onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
            className="rounded border border-[var(--color-line-strong)] bg-[var(--color-paper)] px-2 py-0.5 text-xs"
          >
            <option value="20">20</option>
            <option value="40">40</option>
            <option value="100">100</option>
          </select>
          <span>{t.perPage}</span>
        </div>
      </div>

      {items === null && <Spinner />}
      {items !== null && items.length === 0 && <EmptyState title={t.noComplaintsMatch} />}

      {items && items.length > 0 && (
        <div className="overflow-x-auto -mx-4 sm:mx-0 rounded-lg border border-[var(--color-line)] bg-[var(--color-paper-raised)]">
          <table className="w-full text-sm min-w-[860px]">
            <thead>
              <tr className="text-left text-xs text-[var(--color-ink-soft)] border-b border-[var(--color-line-strong)] bg-[var(--color-paper)]">
                <th className="py-2.5 px-3 font-medium">{t.complaintCol}</th>
                <th className="py-2.5 px-3 font-medium">{t.categoryCol}</th>
                <th className="py-2.5 px-3 font-medium">{t.wardCol}</th>
                <th className="py-2.5 px-3 font-medium">{t.ageCol}</th>
                <th className="py-2.5 px-3 font-medium">{t.priorityCol}</th>
                <th className="py-2.5 px-3 font-medium">{t.riskCol}</th>
                <th className="py-2.5 px-3 font-medium">{t.assignedCol}</th>
                <th className="py-2.5 px-3 font-medium">{t.slaCol}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} className="border-b border-[var(--color-line)] hover:bg-[var(--color-paper)]/50 transition-colors">
                  <td className="py-2.5 px-3">
                    <Link to={`/officer/complaints/${c.public_id}`} className="block group">
                      <p className="font-[family-name:var(--font-mono)] text-xs text-[var(--color-teal-700)] group-hover:underline font-medium">
                        {c.public_id}
                      </p>
                      <p className="text-[var(--color-ink)] font-medium text-xs truncate max-w-sm mt-0.5">{c.title}</p>
                    </Link>
                  </td>
                  <td className="py-2.5 px-3 text-xs text-[var(--color-ink-soft)]">
                    {lang === "kn" && c.category.name_kn ? c.category.name_kn : c.category.name_en}
                  </td>
                  <td className="py-2.5 px-3 text-xs text-[var(--color-ink-soft)]">
                    {c.ward ? `${lang === "kn" ? "ವಾರ್ಡ್" : "Ward"} ${c.ward}` : "-"}
                  </td>
                  <td className="py-2.5 px-3 text-xs text-[var(--color-ink-soft)]">{formatHours(c.age_hours)}</td>
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
                      <span className="text-xs text-[var(--color-warn-700)] font-medium">{t.unassigned}</span>
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

      {/* Pagination Footer */}
      {items && items.length > 0 && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 mt-4 pt-2 text-xs text-[var(--color-ink-soft)]">
          <p>
            {t.showing} <span className="font-semibold text-[var(--color-ink)]">{startIdx}</span> {t.to}{" "}
            <span className="font-semibold text-[var(--color-ink)]">{endIdx}</span> {t.of}{" "}
            <span className="font-semibold text-[var(--color-ink)]">{total}</span> {t.complaints}.
          </p>

          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              &larr; {t.previous}
            </Button>

            <span className="px-3 py-1 font-mono font-medium rounded border border-[var(--color-line)] bg-[var(--color-paper-raised)] text-[var(--color-ink)]">
              {t.page} {page} {t.of} {pages}
            </span>

            <Button
              size="sm"
              variant="secondary"
              disabled={page >= pages}
              onClick={() => setPage((p) => Math.min(pages, p + 1))}
            >
              {t.next} &rarr;
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
