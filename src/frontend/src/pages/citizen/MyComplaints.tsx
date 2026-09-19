import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../lib/api";
import type { ComplaintSummary } from "../../lib/types";
import { SectionHeading, EmptyState, Spinner, Button } from "../../components/ui/Primitives";
import { RiskBadge, PriorityBadge, StatusBadge, SlaBadge } from "../../components/ui/Badges";
import { relativeTime } from "../../lib/format";
import { useLang } from "../../lib/i18n";

export function MyComplaints() {
  const { lang, t } = useLang();
  const [items, setItems] = useState<ComplaintSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const navigate = useNavigate();

  useEffect(() => {
    setItems(null);
    api
      .get<{ items: ComplaintSummary[]; total: number; pages: number }>("/api/complaints", {
        mine: true,
        page,
        page_size: 20,
        sort: "created_at",
      })
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
        setPages(r.pages || 1);
      });
  }, [page]);

  return (
    <div>
      <div className="flex items-center justify-between flex-wrap gap-3 mb-6">
        <SectionHeading
          title={t.myComplaints}
          description={lang === "kn" ? "ನೀವು ದಾಖಲಿಸಿದ ಪ್ರತಿಯೊಂದು ವರದಿಯ ಪ್ರಗತಿ ಮತ್ತು ಮುಂದಿನ ಕ್ರಮಗಳನ್ನು ಟ್ರ್ಯಾಕ್ ಮಾಡಿ." : "Track every report you've filed and what's happening next."}
        />
        <Button onClick={() => navigate("/citizen/report")}>{t.reportIssue}</Button>
      </div>

      {items === null && <Spinner />}

      {items !== null && items.length === 0 && (
        <EmptyState
          title={lang === "kn" ? "ಯಾವುದೇ ದೂರುಗಳಿಲ್ಲ" : "No complaints yet"}
          description={lang === "kn" ? "ನೀವು ಸಮಸ್ಯೆಯನ್ನು ವರದಿ ಮಾಡಿದ ನಂತರ, ಅದರ ಸ್ಥಿತಿ, ಆದ್ಯತೆ ಮತ್ತು ಟೈಮ್‌ಲೈನ್‌ ಅನ್ನು ಇಲ್ಲಿ ಟ್ರ್ಯಾಕ್ ಮಾಡಬಹುದು." : "Once you report an issue, you'll be able to track its status, priority and timeline here."}
          action={<Button onClick={() => navigate("/citizen/report")}>{t.reportIssue}</Button>}
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
                  {lang === "kn" && c.category.name_kn ? c.category.name_kn : c.category.name_en} &middot;{" "}
                  {c.jurisdiction_name || (lang === "kn" ? "ವ್ಯಾಪ್ತಿ ನಿಗದಿ ಬಾಕಿ" : "Routing pending")} &middot;{" "}
                  {relativeTime(c.created_at)}
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

      {/* Pagination controls if multiple pages */}
      {pages > 1 && (
        <div className="flex items-center justify-between gap-3 mt-6 pt-4 border-t border-[var(--color-line)] text-xs text-[var(--color-ink-soft)]">
          <span>
            {t.showing} {(page - 1) * 20 + 1} {t.to} {Math.min(page * 20, total)} {t.of} {total} {t.complaints}
          </span>
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
