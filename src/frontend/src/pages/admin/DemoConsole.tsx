import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { SurgeStatus } from "../../lib/types";
import { Button, Callout, SectionHeading, StatCard } from "../../components/ui/Primitives";
import { VerificationBadge, RiskBadge } from "../../components/ui/Badges";
import { useLang } from "../../lib/i18n";

const SCENARIOS = [
  { key: "duplicate", title: "Duplicate complaint", title_kn: "ನಕಲಿ ದೂರು", desc: "A near-identical report close to an existing one.", desc_kn: "ಈಗಿರುವ ದೂರಿಗೆ ಸಮೀಪವಿರುವ ಬಹುತೇಕ ಒಂದೇ ರೀತಿಯ ವರದಿ." },
  { key: "wrong_location", title: "Wrong location", title_kn: "ತಪ್ಪು ಸ್ಥಳ", desc: "Coordinates outside the Mysuru service area.", desc_kn: "ಮೈಸೂರು ಸೇವಾ ವ್ಯಾಪ್ತಿಯಿಂದ ಹೊರಗಿರುವ ನಿರ್ದೇಶಾಂಕಗಳು." },
  { key: "repeated_image", title: "Suspicious repeated image", title_kn: "ಅನುಮಾನಾಸ್ಪದ ಮರುಬಳಕೆಯ ಚಿತ್ರ", desc: "The same image hash submitted again.", desc_kn: "ಹಿಂದೆ ಸಲ್ಲಿಸಲಾದ ಅದೇ ಚಿತ್ರವನ್ನು ಮತ್ತೆ ಸಲ್ಲಿಸಲಾಗಿದೆ." },
  { key: "incomplete", title: "Incomplete report", title_kn: "ಅಪೂರ್ಣ ವರದಿ", desc: "A description too short to act on.", desc_kn: "ಕ್ರಮ ಕೈಗೊಳ್ಳಲು ಸಾಧ್ಯವಾಗದಷ್ಟು ಚಿಕ್ಕ ವಿವರಣೆ." },
  { key: "extreme_age", title: "Extreme complaint age", title_kn: "ದೀರ್ಘಕಾಲದ ದೂರು", desc: "A complaint left untouched for weeks.", desc_kn: "ವಾರಗಟ್ಟಲೆ ಯಾವುದೇ ಕ್ರಮವಿಲ್ಲದೆ ಉಳಿದಿರುವ ದೂರು." },
];

export function DemoConsole() {
  const { lang, t } = useLang();
  const [surge, setSurge] = useState<SurgeStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [scenarioResult, setScenarioResult] = useState<{ key: string; data: Record<string, unknown> } | null>(null);
  const [showRawJson, setShowRawJson] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runningKey, setRunningKey] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  async function startSurge(count: number) {
    setStarting(true);
    setError(null);
    try {
      const res = await api.post<{ run_id: number }>("/api/demo/simulate-surge", {
        count,
        batch_size: 250,
        label: "Dasara surge (demo console)",
      });
      poll(res.run_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start simulation.");
    } finally {
      setStarting(false);
    }
  }

  function poll(runId: number) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      const status = await api.get<SurgeStatus>(`/api/demo/surge/${runId}`);
      setSurge(status);
      if (status.state === "COMPLETED" && pollRef.current) {
        clearInterval(pollRef.current);
      }
    }, 700);
  }

  async function runScenario(key: string) {
    setError(null);
    setRunningKey(key);
    try {
      const data = await api.post<Record<string, unknown>>(`/api/demo/scenario/${key}`);
      setScenarioResult({ key, data });
      setShowRawJson(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Scenario failed.");
    } finally {
      setRunningKey(null);
    }
  }

  const activeScenario = SCENARIOS.find((s) => s.key === scenarioResult?.key);

  // Helper extraction of diagnostic fields
  const resData = scenarioResult?.data;
  const verification = resData?.verification as {
    verification_status?: string;
    confidence?: number;
    verification_factors?: Array<{
      code: string;
      label: string;
      verdict: string;
      score_delta: number;
      detail: string;
    }>;
  } | undefined;

  const inputObj = resData?.input as Record<string, unknown> | undefined;
  const duplicateCandidates = resData?.duplicate_candidates as Array<{
    complaint_id: number;
    similarity_pct: number;
    distance_m: number;
  }> | undefined;

  const riskObj = resData?.risk as {
    risk_score?: number;
    risk_level?: string;
    recommended_action?: string;
  } | undefined;

  return (
    <div>
      <SectionHeading
        eyebrow={t.roleAdmin}
        title={t.demoConsole}
        description={lang === "kn" ? "ಉತ್ಪಾದನಾ ಎಂಜಿನ್‌ಗಳ ನೈಜ ವಿಶ್ಲೇಷಣೆ ಮತ್ತು ನಕಲಿ ಇನ್‌ಪುಟ್‌ಗಳ ಪರೀಕ್ಷೆ." : "Run the system's real verification and neglect-risk engines against crafted diagnostic scenarios."}
      />

      {/* Dasara Surge Simulation */}
      <section className="border border-[var(--color-line-strong)] rounded-lg p-5 mb-10 bg-[var(--color-paper-raised)]">
        <h3 className="text-sm font-medium mb-1">{t.surgeSimulation}</h3>
        <p className="text-xs text-[var(--color-ink-soft)] mb-4">
          {lang === "kn" ? "ದಸರಾ ಸಂದರ್ಭದಲ್ಲಿ ಏಕಕಾಲಕ್ಕೆ ಬರುವ ದೂರುಗಳ ಅಸಮಕಾಲಿಕ ಪ್ರಕ್ರಿಯೆಯನ್ನು ಪರೀಕ್ಷಿಸಿ." : "Simulates a burst of synthetic complaints processed as an asynchronous batch job - the UI never blocks while it runs."}
        </p>
        <div className="flex gap-2 mb-5">
          <Button size="sm" onClick={() => startSurge(2000)} disabled={starting}>
            {lang === "kn" ? "2,000 ವರದಿಗಳ ಸಿಮ್ಯುಲೇಶನ್" : "Simulate 2,000 reports"}
          </Button>
          <Button size="sm" variant="secondary" onClick={() => startSurge(5000)} disabled={starting}>
            {lang === "kn" ? "5,000 ವರದಿಗಳ ಸಿಮ್ಯುಲೇಶನ್ (ದಸರಾ ಗರಿಷ್ಠ)" : "Simulate 5,000 reports (Dasara peak)"}
          </Button>
        </div>

        {surge && (
          <div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 mb-3">
              <StatCard label="Incoming" value={surge.incoming_reports} />
              <StatCard label="Processed" value={surge.processed} tone="good" />
              <StatCard label="Queued" value={surge.queued} tone="warn" />
              <StatCard label="Duplicates found" value={surge.duplicates_detected} />
              <StatCard label="High priority" value={surge.high_priority} tone="danger" />
            </div>
            <p className="text-xs text-[var(--color-ink-soft)]">
              {surge.state === "COMPLETED" ? "Completed" : "Running"} &middot; avg latency{" "}
              {surge.avg_processing_latency_ms.toFixed(2)}ms/report
              {surge.throughput_per_sec ? ` \u00b7 ${surge.throughput_per_sec}/sec` : ""} &middot; {surge.note}
            </p>
          </div>
        )}
      </section>

      {/* Bad-Input Scenarios */}
      <section>
        <h3 className="text-sm font-medium mb-1">{t.badInputScenarios}</h3>
        <p className="text-xs text-[var(--color-ink-soft)] mb-4">
          {t.badInputDesc}
        </p>

        <div className="grid sm:grid-cols-2 gap-3 mb-6">
          {SCENARIOS.map((s) => (
            <button
              key={s.key}
              onClick={() => runScenario(s.key)}
              disabled={runningKey === s.key}
              className={`text-left border rounded-lg p-4 transition-all ${
                scenarioResult?.key === s.key
                  ? "border-[var(--color-teal-600)] bg-[var(--color-teal-100)]/20 shadow-sm"
                  : "border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] hover:border-[var(--color-teal-600)]"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium text-[var(--color-ink)]">
                  {lang === "kn" ? s.title_kn : s.title}
                </p>
                {runningKey === s.key && (
                  <span className="text-[11px] text-[var(--color-teal-700)] font-medium animate-pulse">Running...</span>
                )}
              </div>
              <p className="text-xs text-[var(--color-ink-soft)] mt-1">
                {lang === "kn" ? s.desc_kn : s.desc}
              </p>
            </button>
          ))}
        </div>

        {error && <Callout tone="danger">{error}</Callout>}

        {/* Structured Executive Intelligence Result Card */}
        {scenarioResult && (
          <div className="border border-[var(--color-line-strong)] rounded-xl bg-[var(--color-paper-raised)] p-5 animate-in fade-in duration-200 shadow-sm">
            <div className="flex items-center justify-between border-b border-[var(--color-line)] pb-4 mb-4 flex-wrap gap-2">
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-teal-700)] bg-[var(--color-teal-100)] px-2 py-0.5 rounded-full">
                  {t.diagnosticResult}
                </span>
                <h4 className="text-base font-[family-name:var(--font-display)] text-[var(--color-ink)] mt-1 font-semibold">
                  {lang === "kn" ? activeScenario?.title_kn : activeScenario?.title}
                </h4>
              </div>

              {verification?.verification_status && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-[var(--color-ink-soft)] font-medium">Verdict:</span>
                  <VerificationBadge status={verification.verification_status} />
                </div>
              )}
            </div>

            {/* Confidence & Score Metrics Bar */}
            {typeof verification?.confidence === "number" && (
              <div className="mb-5 p-3.5 rounded-lg bg-[var(--color-paper)] border border-[var(--color-line)]">
                <div className="flex items-center justify-between text-xs mb-1.5 font-medium">
                  <span className="text-[var(--color-ink)]">{t.confidenceScore}</span>
                  <span className="font-mono text-[var(--color-teal-700)] font-bold">{verification.confidence}%</span>
                </div>
                <div className="w-full bg-[var(--color-line-strong)]/40 rounded-full h-2 overflow-hidden">
                  <div
                    className={`h-2 rounded-full transition-all duration-500 ${
                      verification.confidence >= 70
                        ? "bg-[var(--color-good-600)]"
                        : verification.confidence >= 40
                          ? "bg-[var(--color-warn-600)]"
                          : "bg-[var(--color-danger-600)]"
                    }`}
                    style={{ width: `${Math.min(100, Math.max(0, verification.confidence))}%` }}
                  />
                </div>
              </div>
            )}

            {/* Verification Factors Breakdown */}
            {verification?.verification_factors && verification.verification_factors.length > 0 && (
              <div className="mb-5">
                <h5 className="text-xs font-semibold text-[var(--color-ink-soft)] uppercase tracking-wider mb-2.5">
                  {t.verificationFactors}
                </h5>
                <div className="space-y-2">
                  {verification.verification_factors.map((f, i) => (
                    <div
                      key={i}
                      className="p-3 rounded-lg border border-[var(--color-line)] bg-[var(--color-paper)] flex items-start gap-3 text-xs"
                    >
                      <span
                        className={`mt-0.5 shrink-0 h-5 w-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                          f.verdict === "PASS"
                            ? "bg-[var(--color-good-100)] text-[var(--color-good-700)]"
                            : f.verdict === "WARN"
                              ? "bg-[var(--color-warn-100)] text-[var(--color-warn-700)]"
                              : "bg-[var(--color-danger-100)] text-[var(--color-danger-700)]"
                        }`}
                      >
                        {f.verdict === "PASS" ? "✓" : f.verdict === "WARN" ? "!" : "✕"}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <p className="font-semibold text-[var(--color-ink)]">{f.label}</p>
                          <span
                            className={`font-mono text-[11px] font-semibold ${
                              f.score_delta > 0
                                ? "text-[var(--color-good-700)]"
                                : f.score_delta < 0
                                  ? "text-[var(--color-danger-700)]"
                                  : "text-[var(--color-ink-soft)]"
                            }`}
                          >
                            {f.score_delta > 0 ? `+${f.score_delta}` : f.score_delta} pts
                          </span>
                        </div>
                        <p className="text-[var(--color-ink-soft)] mt-0.5 leading-relaxed">{f.detail}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Risk Explanation if scenario tested neglect */}
            {riskObj && (
              <div className="mb-5 p-3.5 rounded-lg border border-[var(--color-danger-500)]/30 bg-[var(--color-danger-100)]/20">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-semibold text-[var(--color-danger-800)]">{t.risk}</span>
                  {riskObj.risk_level && <RiskBadge level={riskObj.risk_level} score={riskObj.risk_score || 0} />}
                </div>
                {riskObj.recommended_action && (
                  <p className="text-xs text-[var(--color-ink-soft)]">
                    <strong className="text-[var(--color-ink)]">{t.recommendedAction}:</strong> {riskObj.recommended_action}
                  </p>
                )}
              </div>
            )}

            {/* Duplicate Candidates if scenario detected duplicates */}
            {duplicateCandidates && duplicateCandidates.length > 0 && (
              <div className="mb-5 p-3.5 rounded-lg border border-[var(--color-warn-500)]/30 bg-[var(--color-warn-100)]/20">
                <span className="text-xs font-semibold text-[var(--color-warn-800)] block mb-1.5">{t.duplicateDetection}</span>
                <ul className="space-y-1 text-xs text-[var(--color-ink-soft)]">
                  {duplicateCandidates.map((d, idx) => (
                    <li key={idx}>
                      Complaint #{d.complaint_id}: {d.similarity_pct}% {t.similar}, {d.distance_m}m {t.away}.
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Input Details Summary (Replaces raw code inspection) */}
            {inputObj && Object.keys(inputObj).length > 0 && (
              <div className="mb-4">
                <h5 className="text-xs font-semibold text-[var(--color-ink-soft)] uppercase tracking-wider mb-2">
                  {t.inputDetails}
                </h5>
                <div className="bg-[var(--color-paper)] border border-[var(--color-line)] rounded-lg p-3 text-xs space-y-1">
                  {Object.entries(inputObj).map(([k, v]) => (
                    <div key={k} className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4 py-1 border-b border-[var(--color-line)] last:border-0">
                      <span className="font-mono text-[var(--color-ink-soft)] w-28 shrink-0 capitalize">{k.replace("_", " ")}:</span>
                      <span className="font-medium text-[var(--color-ink)] truncate">
                        {typeof v === "object" ? JSON.stringify(v) : String(v)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Optional Collapsible Developer Technical Payload */}
            <div className="mt-4 pt-3 border-t border-[var(--color-line)]">
              <button
                type="button"
                onClick={() => setShowRawJson(!showRawJson)}
                className="text-xs text-[var(--color-teal-700)] hover:text-[var(--color-teal-800)] hover:underline flex items-center gap-1.5 font-medium"
              >
                <span>{showRawJson ? "▲" : "▼"}</span>
                <span>{showRawJson ? t.hideTechnicalJson : t.showTechnicalJson}</span>
              </button>

              {showRawJson && (
                <pre className="mt-3 text-xs bg-[var(--color-paper)] border border-[var(--color-line)] rounded-md p-3 overflow-x-auto font-[family-name:var(--font-mono)] text-[var(--color-ink)] animate-in fade-in duration-150">
                  {JSON.stringify(scenarioResult.data, null, 2)}
                </pre>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
