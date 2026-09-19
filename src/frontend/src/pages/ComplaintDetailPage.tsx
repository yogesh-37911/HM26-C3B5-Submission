import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import type { ComplaintDetail as ComplaintDetailT } from "../lib/types";
import { useAuth } from "../lib/auth";
import { Button, Callout, FactorBar, Spinner } from "../components/ui/Primitives";
import { PriorityBadge, RiskBadge, SlaBadge, StatusBadge, VerificationBadge } from "../components/ui/Badges";
import { Timeline } from "../components/ui/Timeline";
import { formatDateTime, formatHours } from "../lib/format";
import { ComplaintMap } from "../components/map/ComplaintMap";

const NEXT_STATUS: Record<string, string[]> = {
  SUBMITTED: ["VALIDATING", "ROUTED", "REJECTED"],
  VALIDATING: ["ROUTED", "REJECTED"],
  ROUTED: ["ASSIGNED", "REJECTED"],
  ASSIGNED: ["IN_PROGRESS", "ROUTED", "REJECTED"],
  IN_PROGRESS: ["FIELD_VERIFIED", "ASSIGNED", "RESOLVED"],
  FIELD_VERIFIED: ["RESOLVED", "IN_PROGRESS"],
  RESOLVED: ["REOPENED"],
  REOPENED: ["ASSIGNED", "ROUTED", "IN_PROGRESS"],
  REJECTED: ["REOPENED"],
};

export function ComplaintDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [complaint, setComplaint] = useState<ComplaintDetailT | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [followupMsg, setFollowupMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [workers, setWorkers] = useState<{ id: number; full_name: string }[]>([]);
  const [selectedWorker, setSelectedWorker] = useState<string>("");

  const isOfficerLike = user?.role === "OFFICER" || user?.role === "ADMIN";
  const isFieldWorker = user?.role === "FIELD_WORKER";
  const isCitizen = user?.role === "CITIZEN";

  async function load() {
    if (!id) return;
    try {
      const c = await api.get<ComplaintDetailT>(`/api/complaints/${id}`);
      setComplaint(c);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load this complaint.");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (isOfficerLike) {
      api.get<{ items: { id: number; full_name: string }[] }>("/api/auth/field-workers").then((r) => setWorkers(r.items));
    }
  }, [isOfficerLike]);

  async function changeStatus(to: string) {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      await api.patch(`/api/complaints/${id}/status`, { to_status: to });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change status.");
    } finally {
      setBusy(false);
    }
  }

  async function assign() {
    if (!id || !selectedWorker) return;
    setBusy(true);
    setError(null);
    try {
      await api.post(`/api/complaints/${id}/assign`, { field_worker_id: Number(selectedWorker) });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not assign.");
    } finally {
      setBusy(false);
    }
  }

  async function submitFollowup(e: FormEvent) {
    e.preventDefault();
    if (!id || !followupMsg.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.post(`/api/complaints/${id}/followup`, { message: followupMsg });
      setFollowupMsg("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add follow-up.");
    } finally {
      setBusy(false);
    }
  }

  async function requestReopen() {
    if (!id) return;
    const message = window.prompt("Describe why the issue remains unresolved:");
    if (!message) return;
    setBusy(true);
    try {
      await api.post(`/api/complaints/${id}/reopen`, { message });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reopen.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !complaint) return <Callout tone="danger">{error}</Callout>;
  if (!complaint) return <Spinner />;

  const c = complaint;

  return (
    <div className="grid lg:grid-cols-[1.5fr_1fr] gap-10">
      <div>
        <p className="text-xs font-[family-name:var(--font-mono)] text-[var(--color-ink-soft)]">{c.public_id}</p>
        <h1 className="font-[family-name:var(--font-display)] text-2xl mt-1">{c.title}</h1>
        <div className="flex flex-wrap gap-1.5 mt-3">
          <StatusBadge status={c.status} />
          <PriorityBadge level={c.priority_level} />
          <RiskBadge level={c.risk_level} score={c.risk_score} />
          <VerificationBadge status={c.verification_status} />
          <SlaBadge breachRisk={c.sla.breach_risk} remainingHours={c.sla.remaining_hours} breached={c.sla.breached} />
        </div>

        {c.description && (
          <p className="text-sm text-[var(--color-ink-soft)] mt-4 leading-relaxed max-w-prose">{c.description}</p>
        )}

        <div className="mt-4 text-sm text-[var(--color-ink-soft)] space-y-1">
          <p>
            <span className="text-[var(--color-ink)]">Jurisdiction:</span>{" "}
            {c.jurisdiction.authority
              ? `${c.jurisdiction.authority}${c.jurisdiction.ward ? ` Ward ${c.jurisdiction.ward}` : ""}`
              : "Not yet routed"}
            {c.jurisdiction.boundary_version && ` (boundary ${c.jurisdiction.boundary_version})`}
          </p>
          <p className="text-xs">{c.jurisdiction.note}</p>
          {c.jurisdiction.reason && <p className="text-xs italic">{c.jurisdiction.reason}</p>}
        </div>

        {typeof c.latitude === "number" && (
          <div className="mt-5">
            <ComplaintMap
              markers={[
                {
                  public_id: c.public_id,
                  lat: c.latitude,
                  lng: c.longitude!,
                  category: c.category.code,
                  category_name: c.category.name_en,
                  status: c.status,
                  priority_level: c.priority_level,
                  risk_score: c.risk_score,
                  risk_level: c.risk_level,
                  age_hours: c.age_hours,
                  jurisdiction: c.jurisdiction_name,
                },
              ]}
              height={260}
            />
          </div>
        )}

        {c.risk_explanation && (
          <section className="mt-8">
            <h2 className="font-[family-name:var(--font-display)] text-lg mb-1">Why this neglect risk?</h2>
            <Callout tone={c.risk_explanation.risk_level === "HIGH" ? "danger" : "info"}>
              <span className="font-medium">Recommended action:</span> {c.risk_explanation.recommended_action}
            </Callout>
            <div className="mt-3">
              {c.risk_explanation.risk_factors.map((f) => (
                <FactorBar key={f.code} factor={f} />
              ))}
            </div>
          </section>
        )}

        {c.priority_explanation && (
          <section className="mt-8">
            <h2 className="font-[family-name:var(--font-display)] text-lg mb-1">Why this priority?</h2>
            <div className="mt-3">
              {c.priority_explanation.priority_factors.map((f) => (
                <FactorBar key={f.code} factor={f} />
              ))}
            </div>
          </section>
        )}

        <section className="mt-8">
          <h2 className="font-[family-name:var(--font-display)] text-lg mb-1">Verification</h2>
          <p className="text-xs text-[var(--color-ink-soft)] mb-3">{c.verification.disclaimer}</p>
          <div className="space-y-2">
            {c.verification.verification_factors.map((f) => (
              <div key={f.code} className="flex items-start gap-2.5 text-sm">
                <span
                  className={`mt-0.5 shrink-0 h-4 w-4 rounded-full flex items-center justify-center text-[10px] font-bold ${
                    f.verdict === "PASS"
                      ? "bg-[var(--color-good-100)] text-[var(--color-good-700)]"
                      : f.verdict === "WARN"
                        ? "bg-[var(--color-warn-100)] text-[var(--color-warn-700)]"
                        : "bg-[var(--color-danger-100)] text-[var(--color-danger-700)]"
                  }`}
                >
                  {f.verdict === "PASS" ? "\u2713" : f.verdict === "WARN" ? "!" : "\u2715"}
                </span>
                <div>
                  <p className="text-[var(--color-ink)]">{f.label}</p>
                  <p className="text-xs text-[var(--color-ink-soft)]">{f.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {c.duplicates.length > 0 && (
          <section className="mt-8">
            <h2 className="font-[family-name:var(--font-display)] text-lg mb-2">Related reports</h2>
            <ul className="space-y-2">
              {c.duplicates.map((d) => (
                <li key={d.complaint_id} className="text-sm border-b border-[var(--color-line)] py-2">
                  <span className="font-[family-name:var(--font-mono)]">{d.public_id}</span> &mdash; {d.similarity_pct}%
                  similar, {d.distance_m}m away.{" "}
                  <span className="text-xs text-[var(--color-ink-soft)]">({d.decision})</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      <div>
        <h2 className="font-[family-name:var(--font-display)] text-lg mb-4">Timeline</h2>
        <Timeline events={c.timeline} />

        {error && (
          <div className="mt-4">
            <Callout tone="danger">{error}</Callout>
          </div>
        )}

        {isOfficerLike && (
          <div className="mt-8 border-t border-[var(--color-line)] pt-5 space-y-4">
            <h3 className="text-sm font-medium">Officer actions</h3>
            <div>
              <p className="text-xs text-[var(--color-ink-soft)] mb-1.5">Change status</p>
              <div className="flex flex-wrap gap-2">
                {(NEXT_STATUS[c.status] || []).map((s) => (
                  <Button key={s} size="sm" variant="secondary" disabled={busy} onClick={() => changeStatus(s)}>
                    {s.replace("_", " ")}
                  </Button>
                ))}
                {(NEXT_STATUS[c.status] || []).length === 0 && (
                  <p className="text-xs text-[var(--color-ink-soft)]">No further transitions from this status.</p>
                )}
              </div>
            </div>
            {!c.assigned && workers.length > 0 && (
              <div>
                <p className="text-xs text-[var(--color-ink-soft)] mb-1.5">Assign field worker</p>
                <div className="flex gap-2">
                  <select
                    value={selectedWorker}
                    onChange={(e) => setSelectedWorker(e.target.value)}
                    className="flex-1 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-2.5 py-2 text-sm"
                  >
                    <option value="">Select a worker...</option>
                    {workers.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.full_name}
                      </option>
                    ))}
                  </select>
                  <Button size="sm" disabled={busy || !selectedWorker} onClick={assign}>
                    Assign
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {isCitizen && (
          <div className="mt-8 border-t border-[var(--color-line)] pt-5 space-y-4">
            <h3 className="text-sm font-medium">Add follow-up</h3>
            <form onSubmit={submitFollowup} className="space-y-2">
              <textarea
                value={followupMsg}
                onChange={(e) => setFollowupMsg(e.target.value)}
                rows={2}
                placeholder="Still not fixed, please look into this."
                className="w-full rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-3 py-2 text-sm outline-none focus:border-[var(--color-teal-600)] resize-none"
              />
              <Button type="submit" size="sm" disabled={busy || !followupMsg.trim()}>
                Add follow-up
              </Button>
            </form>
            {c.status === "RESOLVED" && (
              <Button variant="ghost" size="sm" onClick={requestReopen} disabled={busy}>
                Report issue remains unresolved
              </Button>
            )}
          </div>
        )}

        {isFieldWorker && (
          <div className="mt-8 border-t border-[var(--color-line)] pt-5">
            <p className="text-xs text-[var(--color-ink-soft)]">
              Manage this job from your{" "}
              <a href="/field/tasks" className="text-[var(--color-teal-700)] underline">
                task list
              </a>
              .
            </p>
          </div>
        )}

        {c.followups.length > 0 && (
          <div className="mt-8 border-t border-[var(--color-line)] pt-5">
            <h3 className="text-sm font-medium mb-2">Follow-ups</h3>
            <ul className="space-y-2">
              {c.followups.map((f) => (
                <li key={f.id} className="text-sm">
                  <p className="text-[var(--color-ink)]">{f.message}</p>
                  <p className="text-xs text-[var(--color-ink-soft)]">
                    {formatDateTime(f.at)} &middot; {f.kind}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-8 border-t border-[var(--color-line)] pt-5 text-xs text-[var(--color-ink-soft)] space-y-1">
          <p>
            SLA target: {c.sla.target_hours}h &middot; elapsed {formatHours(c.sla.elapsed_hours)}
          </p>
          {c.sla.note && <p>{c.sla.note}</p>}
          {c.is_synthetic && <p className="italic">Synthetic demo record.</p>}
        </div>
      </div>
    </div>
  );
}
