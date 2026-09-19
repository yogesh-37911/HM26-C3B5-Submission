import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { SurgeStatus } from "../../lib/types";
import { Button, Callout, SectionHeading, StatCard } from "../../components/ui/Primitives";

const SCENARIOS = [
  { key: "duplicate", title: "Duplicate complaint", desc: "A near-identical report close to an existing one." },
  { key: "wrong_location", title: "Wrong location", desc: "Coordinates outside the Mysuru service area." },
  { key: "repeated_image", title: "Suspicious repeated image", desc: "The same image hash submitted again." },
  { key: "incomplete", title: "Incomplete report", desc: "A description too short to act on." },
  { key: "extreme_age", title: "Extreme complaint age", desc: "A complaint left untouched for weeks." },
];

export function DemoConsole() {
  const [surge, setSurge] = useState<SurgeStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [scenarioResult, setScenarioResult] = useState<{ key: string; data: unknown } | null>(null);
  const [error, setError] = useState<string | null>(null);
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
    try {
      const data = await api.post(`/api/demo/scenario/${key}`);
      setScenarioResult({ key, data });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Scenario failed.");
    }
  }

  return (
    <div>
      <SectionHeading
        eyebrow="Admin"
        title="Demo console"
        description="Run the system's real engines against synthetic load and crafted bad inputs - not canned responses."
      />

      <section className="border border-[var(--color-line-strong)] rounded-lg p-5 mb-10">
        <h3 className="text-sm font-medium mb-1">Dasara surge simulation</h3>
        <p className="text-xs text-[var(--color-ink-soft)] mb-4">
          Simulates a burst of synthetic complaints processed as an asynchronous batch job -
          the UI never blocks while it runs.
        </p>
        <div className="flex gap-2 mb-5">
          <Button size="sm" onClick={() => startSurge(2000)} disabled={starting}>
            Simulate 2,000 reports
          </Button>
          <Button size="sm" variant="secondary" onClick={() => startSurge(5000)} disabled={starting}>
            Simulate 5,000 reports (Dasara peak)
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

      <section>
        <h3 className="text-sm font-medium mb-1">Bad-input scenarios</h3>
        <p className="text-xs text-[var(--color-ink-soft)] mb-4">
          Each button runs the production verification/duplicate/risk engines against a crafted input.
        </p>
        <div className="grid sm:grid-cols-2 gap-3 mb-5">
          {SCENARIOS.map((s) => (
            <button
              key={s.key}
              onClick={() => runScenario(s.key)}
              className="text-left border border-[var(--color-line-strong)] rounded-lg p-4 hover:border-[var(--color-teal-600)] transition-colors"
            >
              <p className="text-sm font-medium">{s.title}</p>
              <p className="text-xs text-[var(--color-ink-soft)] mt-0.5">{s.desc}</p>
            </button>
          ))}
        </div>

        {error && <Callout tone="danger">{error}</Callout>}

        {scenarioResult && (
          <div className="border-t border-[var(--color-line)] pt-4">
            <p className="text-sm font-medium mb-2">
              Result: {SCENARIOS.find((s) => s.key === scenarioResult.key)?.title}
            </p>
            <pre className="text-xs bg-[var(--color-paper-raised)] border border-[var(--color-line)] rounded-md p-3 overflow-x-auto font-[family-name:var(--font-mono)]">
              {JSON.stringify(scenarioResult.data, null, 2)}
            </pre>
          </div>
        )}
      </section>
    </div>
  );
}
