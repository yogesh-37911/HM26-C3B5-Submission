import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError, BASE_URL } from "../lib/api";
import type { ComplaintDetail as ComplaintDetailT } from "../lib/types";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
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
  const { t } = useLang();
  const [complaint, setComplaint] = useState<ComplaintDetailT | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [followupMsg, setFollowupMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [workers, setWorkers] = useState<{ id: number; full_name: string }[]>([]);
  const [selectedWorker, setSelectedWorker] = useState<string>("");

  const [selectedPhoto, setSelectedPhoto] = useState<ComplaintDetailT["evidence"][0] | null>(null);
  const [uploadingEvidence, setUploadingEvidence] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [deletingEvidenceId, setDeletingEvidenceId] = useState<number | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);
  const [imgLoading, setImgLoading] = useState(true);
  const [imgError, setImgError] = useState(false);

  // Send Update / Note to Officer state
  const [showNotifyOfficer, setShowNotifyOfficer] = useState(false);
  const [officerNote, setOfficerNote] = useState("");
  const [sendingNote, setSendingNote] = useState(false);
  const [noteSentSuccess, setNoteSentSuccess] = useState(false);

  // Field Worker action states
  const [workCompletionNote, setWorkCompletionNote] = useState("");
  const [completingWork, setCompletingWork] = useState(false);
  const [workCompletedSuccess, setWorkCompletedSuccess] = useState(false);
  const [startingTask, setStartingTask] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const token = localStorage.getItem("civicpulse.token") || "";

  const isOfficerLike = user?.role === "OFFICER" || user?.role === "ADMIN";
  const isFieldWorker = user?.role === "FIELD_WORKER";
  const isCitizen = user?.role === "CITIZEN";

  function getEvidenceUrl(ev: ComplaintDetailT["evidence"][0]) {
    const rawPath = ev.url || `/api/complaints/${complaint?.public_id || id}/evidence/${ev.id}`;
    return `${BASE_URL}${rawPath}${token ? `?token=${encodeURIComponent(token)}` : ""}`;
  }

  function formatBytes(bytes: number): string {
    if (!bytes) return "0 B";
    if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${Math.round(bytes / 1024)} KB`;
  }

  async function handleEvidenceUpload(e: ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0 || !id) return;
    setEvidenceError(null);
    const validTypes = ["image/jpeg", "image/png", "image/webp"];

    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      if (!validTypes.includes(f.type.toLowerCase())) {
        setEvidenceError("Only JPEG, PNG, and WebP images are allowed.");
        return;
      }
      if (f.size > 5 * 1024 * 1024) {
        setEvidenceError(`"${f.name}" exceeds the 5 MB file size limit.`);
        return;
      }
    }

    setUploadingEvidence(true);
    try {
      const stage = isOfficerLike || isFieldWorker ? "FIELD" : "REPORT";
      for (let i = 0; i < files.length; i++) {
        const fd = new FormData();
        fd.append("file", files[i]);
        await api.upload(`/api/complaints/${id}/evidence`, fd, { stage });
      }
      await load();
    } catch (err) {
      setEvidenceError(err instanceof ApiError ? err.message : "Failed to upload photo evidence.");
    } finally {
      setUploadingEvidence(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDeleteEvidence(evidenceId: number) {
    if (!id) return;
    setDeletingEvidenceId(evidenceId);
    setEvidenceError(null);
    try {
      await api.delete(`/api/complaints/${id}/evidence/${evidenceId}`);
      if (selectedPhoto?.id === evidenceId) setSelectedPhoto(null);
      setDeleteConfirmId(null);
      await load();
    } catch (err) {
      setEvidenceError(err instanceof ApiError ? err.message : "Failed to delete photo evidence.");
    } finally {
      setDeletingEvidenceId(null);
    }
  }

  async function handleSendNoteToOfficer(e: FormEvent) {
    e.preventDefault();
    if (!id || !officerNote.trim()) return;
    setSendingNote(true);
    setError(null);
    try {
      await api.post(`/api/complaints/${id}/followup`, {
        message: officerNote.trim(),
        kind: "CITIZEN_UPDATE",
      });
      setOfficerNote("");
      setNoteSentSuccess(true);
      setTimeout(() => setNoteSentSuccess(false), 5000);
      setShowNotifyOfficer(false);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send message to officer.");
    } finally {
      setSendingNote(false);
    }
  }

  async function handleStartTask() {
    if (!complaint) return;
    setStartingTask(true);
    setError(null);
    try {
      const taskId = complaint.assignment?.task_id;
      if (taskId) {
        await api.post(`/api/field-worker/tasks/${taskId}/start`);
      } else {
        await api.patch(`/api/complaints/${id}/status`, { to_status: "IN_PROGRESS" });
      }
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start inspection.");
    } finally {
      setStartingTask(false);
    }
  }

  async function handleCompleteTask(resolved: boolean = true) {
    if (!complaint) return;
    setCompletingWork(true);
    setError(null);
    try {
      const taskId = complaint.assignment?.task_id;
      const note =
        workCompletionNote.trim() ||
        (resolved ? "Work completed and verified on site." : "Unable to resolve on site.");
      if (taskId) {
        await api.post(`/api/field-worker/tasks/${taskId}/complete`, undefined, { note, resolved });
      } else {
        await api.patch(`/api/complaints/${id}/status`, {
          to_status: resolved ? "FIELD_VERIFIED" : "ROUTED",
        });
      }
      setWorkCompletionNote("");
      setWorkCompletedSuccess(true);
      setTimeout(() => setWorkCompletedSuccess(false), 6000);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not complete task.");
    } finally {
      setCompletingWork(false);
    }
  }

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setSelectedPhoto(null);
    }
    if (selectedPhoto) {
      setImgLoading(true);
      setImgError(false);
      window.addEventListener("keydown", handleKeyDown);
      return () => window.removeEventListener("keydown", handleKeyDown);
    }
  }, [selectedPhoto]);

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
      api
        .get<{ items: { id: number; full_name: string }[] }>("/api/auth/field-workers")
        .then((r) => setWorkers(r.items));
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
  const fieldPhotosCount = c.evidence.filter((e) => e.stage === "FIELD").length;

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

        {/* Assigned Worker Details Banner */}
        {c.assignment && (
          <div className="mt-4 p-4 rounded-lg border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)]">
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-teal-700)] flex items-center gap-1.5">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
                Assigned Field Worker
              </span>
              <span className="text-[11px] font-mono font-medium px-2.5 py-0.5 rounded-full bg-[var(--color-teal-100)] border border-[var(--color-teal-700)]/30 text-[var(--color-teal-800)]">
                {c.assignment.state || "ASSIGNED"}
              </span>
            </div>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div>
                <p className="text-sm font-semibold text-[var(--color-ink)]">{c.assignment.worker_name}</p>
                {c.assignment.worker_email && (
                  <p className="text-xs text-[var(--color-ink-soft)] font-mono">{c.assignment.worker_email}</p>
                )}
              </div>
              <div className="text-right text-xs text-[var(--color-ink-soft)]">
                <p>Assigned: {formatDateTime(c.assignment.assigned_at)}</p>
                {c.assignment.started_at && <p className="text-[var(--color-teal-700)]">Started: {formatDateTime(c.assignment.started_at)}</p>}
              </div>
            </div>
            {c.assignment.note && (
              <p className="text-xs text-[var(--color-ink-soft)] italic mt-2 bg-[var(--color-paper)] p-2 rounded border border-[var(--color-line)]">
                Assignment Note: {c.assignment.note}
              </p>
            )}
          </div>
        )}

        {typeof c.latitude === "number" && (
          <div className="mt-5 relative isolate z-0">
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

        {/* Evidence & Attached Photos Section */}
        <section className="mt-8 border-t border-[var(--color-line)] pt-6">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="font-[family-name:var(--font-display)] text-lg">
                {t.attachedPhotos}
              </h2>
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-[var(--color-paper-raised)] border border-[var(--color-line-strong)] text-[var(--color-ink-soft)]">
                {c.evidence.length}
              </span>
              {fieldPhotosCount > 0 && (
                <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--color-gold-700)] bg-[var(--color-gold-100)] px-2 py-0.5 rounded-full">
                  ✓ {fieldPhotosCount} {t.fieldPhoto}
                </span>
              )}
              <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--color-good-700)] bg-[var(--color-good-100)] px-2 py-0.5 rounded-full">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6 9 17l-5-5" />
                </svg>
                {t.sharedWithOfficerBadge}
              </span>
            </div>

            <div className="flex items-center gap-2">
              {isCitizen && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setShowNotifyOfficer(!showNotifyOfficer)}
                >
                  {t.notifyOfficer}
                </Button>
              )}
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={handleEvidenceUpload}
              />
              <Button
                size="sm"
                variant="primary"
                disabled={busy || uploadingEvidence}
                onClick={() => fileInputRef.current?.click()}
              >
                {uploadingEvidence
                  ? t.uploading
                  : isFieldWorker
                    ? "📸 Attach Completion Photos"
                    : `+ ${isOfficerLike ? t.addFieldPhoto : t.addPhoto}`}
              </Button>
            </div>
          </div>

          {/* Send Update to Officer Form */}
          {showNotifyOfficer && (
            <div className="mb-4 p-4 rounded-lg border border-[var(--color-teal-600)] bg-[var(--color-teal-100)]/20 animate-in fade-in duration-150">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-semibold text-[var(--color-teal-800)] flex items-center gap-1.5">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="m22 2-7 20-4-9-9-4Z" />
                    <path d="M22 2 11 13" />
                  </svg>
                  {t.notifyOfficer}
                </p>
                <button
                  type="button"
                  onClick={() => setShowNotifyOfficer(false)}
                  className="text-xs text-[var(--color-ink-soft)] hover:text-[var(--color-ink)]"
                >
                  ✕
                </button>
              </div>
              <p className="text-xs text-[var(--color-ink-soft)] mb-2.5">
                {t.notifyOfficerNotice}
              </p>
              <form onSubmit={handleSendNoteToOfficer} className="space-y-2">
                <textarea
                  required
                  rows={2}
                  value={officerNote}
                  onChange={(e) => setOfficerNote(e.target.value)}
                  placeholder={t.typeMessage}
                  className="w-full text-xs rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] p-2.5 outline-none focus:border-[var(--color-teal-600)] resize-none"
                />
                <div className="flex justify-end gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setShowNotifyOfficer(false)}
                  >
                    {t.cancel}
                  </Button>
                  <Button
                    type="submit"
                    size="sm"
                    disabled={sendingNote || !officerNote.trim()}
                  >
                    {sendingNote ? t.sending : t.send}
                  </Button>
                </div>
              </form>
            </div>
          )}

          {noteSentSuccess && (
            <div className="mb-3 p-3 rounded-md bg-[var(--color-good-100)] text-[var(--color-good-700)] text-xs font-medium flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 6 9 17l-5-5" />
              </svg>
              {t.updateSent}
            </div>
          )}

          {evidenceError && (
            <div className="mb-3">
              <Callout tone="danger">{evidenceError}</Callout>
            </div>
          )}

          {c.evidence.length === 0 ? (
            <div className="border border-dashed border-[var(--color-line-strong)] rounded-lg p-6 text-center bg-[var(--color-paper-raised)]">
              <p className="text-xs text-[var(--color-ink-soft)] mb-2">{t.noPhotosAttached}</p>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => fileInputRef.current?.click()}
              >
                {t.uploadPhoto}
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {c.evidence.map((ev) => (
                <div
                  key={ev.id}
                  className="group rounded-lg border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] overflow-hidden shadow-xs hover:border-[var(--color-teal-600)] transition-all flex flex-col justify-between"
                >
                  <div
                    className="h-44 bg-[var(--color-line)] relative cursor-pointer overflow-hidden flex items-center justify-center"
                    onClick={() => setSelectedPhoto(ev)}
                  >
                    <img
                      src={getEvidenceUrl(ev)}
                      alt={ev.filename}
                      loading="lazy"
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                    />
                    <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
                      <span className="opacity-0 group-hover:opacity-100 transition-opacity bg-black/75 text-white text-xs px-2.5 py-1 rounded-md font-medium flex items-center gap-1.5 shadow">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="11" cy="11" r="8" />
                          <path d="m21 21-4.3-4.3" />
                          <path d="M11 8v6" />
                          <path d="M8 11h6" />
                        </svg>
                        {t.clickToEnlarge}
                      </span>
                    </div>
                  </div>
                  <div className="p-3">
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span
                        className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                          ev.stage === "FIELD"
                            ? "bg-[var(--color-gold-100)] text-[var(--color-gold-700)]"
                            : "bg-[var(--color-teal-100)] text-[var(--color-teal-700)]"
                        }`}
                      >
                        {ev.stage === "FIELD" ? t.fieldPhoto : t.reportPhoto}
                      </span>
                      <span className="text-[11px] text-[var(--color-ink-soft)] font-mono">
                        {formatBytes(ev.size_bytes)}
                      </span>
                    </div>
                    <p className="text-xs font-medium text-[var(--color-ink)] truncate" title={ev.filename}>
                      {ev.filename}
                    </p>
                    <div className="flex items-center justify-between mt-2 pt-2 border-t border-[var(--color-line)] text-[11px] text-[var(--color-ink-soft)]">
                      <span>{formatDateTime(ev.created_at)}</span>

                      {deleteConfirmId === ev.id ? (
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            disabled={deletingEvidenceId === ev.id}
                            onClick={() => handleDeleteEvidence(ev.id)}
                            className="text-[10px] font-bold text-[var(--color-danger-700)] hover:underline"
                          >
                            {deletingEvidenceId === ev.id ? "..." : t.delete}
                          </button>
                          <span className="text-[var(--color-line-strong)]">/</span>
                          <button
                            type="button"
                            onClick={() => setDeleteConfirmId(null)}
                            className="text-[10px] text-[var(--color-ink-soft)] hover:underline"
                          >
                            {t.cancel}
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setDeleteConfirmId(ev.id)}
                          className="text-[11px] text-[var(--color-danger-700)] hover:text-[var(--color-danger-800)] hover:underline font-medium"
                          title={t.deletePhoto}
                        >
                          {t.deletePhoto}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

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

        {/* Dedicated Field Worker Execution & Resolution Panel */}
        {(isFieldWorker || (user?.role === "ADMIN" && c.assigned)) && (
          <div className="mt-8 border-t border-[var(--color-line)] pt-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[var(--color-ink)] flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[var(--color-teal-600)]"></span>
                Field Worker Actions
              </h3>
              <span className="text-xs px-2.5 py-0.5 rounded-full font-mono bg-[var(--color-teal-100)] text-[var(--color-teal-800)] font-medium">
                {c.status}
              </span>
            </div>

            {workCompletedSuccess && (
              <div className="p-3.5 rounded-lg bg-[var(--color-good-100)] text-[var(--color-good-700)] text-xs font-medium flex items-center gap-2.5 animate-in fade-in">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6 9 17l-5-5" />
                </svg>
                <span>Task marked as completed & verified! Sent to Officer for final closure.</span>
              </div>
            )}

            {c.status === "ASSIGNED" && (
              <div className="p-4 rounded-lg bg-[var(--color-paper-raised)] border border-[var(--color-line-strong)] space-y-3">
                <p className="text-xs text-[var(--color-ink-soft)]">
                  You are assigned to this task. Click below when you arrive on site to start inspection.
                </p>
                <Button
                  size="sm"
                  variant="primary"
                  disabled={startingTask || busy}
                  onClick={handleStartTask}
                  className="w-full"
                >
                  {startingTask ? "Starting inspection..." : "▶ Start Inspection / Begin Work"}
                </Button>
              </div>
            )}

            {["ASSIGNED", "IN_PROGRESS", "REOPENED"].includes(c.status) && (
              <div className="p-4 rounded-lg bg-[var(--color-paper-raised)] border border-[var(--color-line-strong)] space-y-3.5">
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-xs font-semibold text-[var(--color-ink)]">
                      1. Attach Field Completion Photos
                    </label>
                    <span className="text-[11px] font-medium text-[var(--color-gold-700)] bg-[var(--color-gold-100)] px-2 py-0.5 rounded-full">
                      {fieldPhotosCount} Attached
                    </span>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={uploadingEvidence}
                    onClick={() => fileInputRef.current?.click()}
                    className="w-full text-xs"
                  >
                    {uploadingEvidence ? "Uploading photos..." : "📸 Take / Upload Completion Photos"}
                  </Button>
                  {fieldPhotosCount === 0 && (
                    <p className="text-[11px] text-[var(--color-ink-soft)] mt-1 italic">
                      Tip: Attach a photo of the completed work for instant verification.
                    </p>
                  )}
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[var(--color-ink)] mb-1">
                    2. Work Completion Note
                  </label>
                  <textarea
                    value={workCompletionNote}
                    onChange={(e) => setWorkCompletionNote(e.target.value)}
                    rows={2}
                    placeholder="Describe the repair work done on site (e.g. Pothole filled and compacted)..."
                    className="w-full rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper)] px-3 py-2 text-xs outline-none focus:border-[var(--color-teal-600)] resize-none"
                  />
                </div>

                <div className="space-y-2 pt-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="primary"
                    disabled={completingWork || uploadingEvidence || busy}
                    onClick={() => handleCompleteTask(true)}
                    className="w-full bg-[var(--color-good-700)] hover:bg-[var(--color-good-800)] text-white font-medium py-2.5 shadow-sm"
                  >
                    {completingWork ? "Marking as completed..." : "✓ Mark Task as Completed & Verified"}
                  </Button>

                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={completingWork || busy}
                    onClick={() => {
                      const note = window.prompt("Reason unable to resolve:") || "";
                      if (note) {
                        setWorkCompletionNote(note);
                        handleCompleteTask(false);
                      }
                    }}
                    className="w-full text-xs text-[var(--color-ink-soft)] hover:text-[var(--color-danger-700)]"
                  >
                    ⚠️ Unable to Resolve / Request Reassignment
                  </Button>
                </div>
              </div>
            )}

            {["FIELD_VERIFIED", "RESOLVED"].includes(c.status) && (
              <div className="p-4 rounded-lg bg-[var(--color-good-100)] border border-[var(--color-good-700)]/30 text-[var(--color-good-700)] text-xs space-y-1.5">
                <p className="font-semibold flex items-center gap-1.5 text-sm">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                  Field Work Completed & Verified
                </p>
                <p className="text-[var(--color-ink-soft)] text-xs">
                  {c.status === "FIELD_VERIFIED"
                    ? "On-site repair verified by Field Worker. Awaiting final closure from Ward Officer."
                    : "Complaint has been officially closed as resolved."}
                </p>
              </div>
            )}
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

      {/* Lightbox / Modal for Viewing Photo Evidence Full Screen */}
      {selectedPhoto && (
        <div
          className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/85 backdrop-blur-md p-4 animate-in fade-in duration-150"
          onClick={() => setSelectedPhoto(null)}
        >
          <div
            className="relative max-w-4xl w-full bg-[var(--color-paper-raised)] border border-[var(--color-line-strong)] rounded-xl overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-[var(--color-line)]">
              <div>
                <div className="flex items-center gap-2">
                  <span
                    className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                      selectedPhoto.stage === "FIELD"
                        ? "bg-[var(--color-gold-100)] text-[var(--color-gold-700)]"
                        : "bg-[var(--color-teal-100)] text-[var(--color-teal-700)]"
                    }`}
                  >
                    {selectedPhoto.stage === "FIELD" ? t.fieldPhoto : t.reportPhoto}
                  </span>
                  <span className="text-xs font-[family-name:var(--font-mono)] text-[var(--color-ink-soft)]">
                    {c.public_id}
                  </span>
                </div>
                <p className="text-sm font-medium text-[var(--color-ink)] mt-0.5 truncate max-w-md">{selectedPhoto.filename}</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={deletingEvidenceId === selectedPhoto.id}
                  onClick={() => {
                    if (window.confirm(t.confirmDeletePhoto)) {
                      handleDeleteEvidence(selectedPhoto.id);
                    }
                  }}
                  className="px-2.5 py-1 text-xs text-[var(--color-danger-700)] hover:bg-[var(--color-danger-100)] rounded-md font-medium transition-colors"
                  title={t.deletePhoto}
                >
                  {deletingEvidenceId === selectedPhoto.id ? "..." : t.deletePhoto}
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedPhoto(null)}
                  className="w-8 h-8 rounded-full flex items-center justify-center text-[var(--color-ink-soft)] hover:text-[var(--color-ink)] hover:bg-[var(--color-line)] text-xl transition-colors"
                  title={t.close}
                >
                  &times;
                </button>
              </div>
            </div>

            <div className="p-4 flex items-center justify-center bg-black/95 max-h-[70vh] min-h-[300px] overflow-hidden relative">
              {imgLoading && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <Spinner label="Loading photo..." />
                </div>
              )}
              {imgError ? (
                <div className="text-center p-8 text-white/80">
                  <p className="text-sm font-medium mb-2">Could not display photo preview</p>
                  <a
                    href={getEvidenceUrl(selectedPhoto)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-[var(--color-teal-300)] underline font-medium"
                  >
                    Open photo in new tab &rarr;
                  </a>
                </div>
              ) : (
                <img
                  src={getEvidenceUrl(selectedPhoto)}
                  alt={selectedPhoto.filename}
                  onLoad={() => setImgLoading(false)}
                  onError={() => { setImgLoading(false); setImgError(true); }}
                  className={`max-h-[65vh] max-w-full object-contain rounded transition-opacity duration-200 ${imgLoading ? "opacity-0" : "opacity-100"}`}
                />
              )}
            </div>

            <div className="p-4 text-xs text-[var(--color-ink-soft)] flex items-center justify-between flex-wrap gap-2 border-t border-[var(--color-line)] bg-[var(--color-paper-raised)]">
              <div>
                <span>Uploaded: {formatDateTime(selectedPhoto.created_at)}</span> &middot;{" "}
                <span>Size: {formatBytes(selectedPhoto.size_bytes)}</span>
              </div>
              <div className="font-mono text-[11px] truncate max-w-xs" title={`Full SHA256: ${selectedPhoto.sha256}`}>
                SHA-256: {selectedPhoto.sha256}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
