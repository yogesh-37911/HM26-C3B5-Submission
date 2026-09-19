import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../../lib/api";
import type { FieldTask } from "../../lib/types";
import { Button, Callout, EmptyState, SectionHeading, Spinner } from "../../components/ui/Primitives";
import { PriorityBadge, SlaBadge } from "../../components/ui/Badges";
import { formatHours } from "../../lib/format";

interface QueuedAction {
  idempotency_key: string;
  action_type: "TASK_START" | "TASK_COMPLETE" | "FIELD_NOTE";
  payload: Record<string, unknown>;
  label: string;
}

const QUEUE_KEY = "civicpulse.offline_queue";

function loadQueue(): QueuedAction[] {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
  } catch {
    return [];
  }
}
function saveQueue(q: QueuedAction[]) {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(q));
}

export function FieldTasks() {
  const [tasks, setTasks] = useState<FieldTask[] | null>(null);
  const [isOffline, setIsOffline] = useState(!navigator.onLine);
  const [queue, setQueue] = useState<QueuedAction[]>(loadQueue());
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const r = await api.get<{ items: FieldTask[] }>("/api/field-worker/tasks");
      setTasks(r.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load tasks.");
    }
  }

  useEffect(() => {
    load();
    const on = () => setIsOffline(false);
    const off = () => setIsOffline(true);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);

  function enqueue(action: QueuedAction) {
    const next = [...queue, action];
    setQueue(next);
    saveQueue(next);
  }

  async function startTask(task: FieldTask) {
    const action: QueuedAction = {
      idempotency_key: crypto.randomUUID(),
      action_type: "TASK_START",
      payload: { task_id: task.task_id },
      label: `Start ${task.public_id}`,
    };
    if (isOffline) {
      enqueue(action);
      return;
    }
    try {
      await api.post(`/api/field-worker/tasks/${task.task_id}/start`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start task.");
    }
  }

  async function completeTask(task: FieldTask) {
    const note = window.prompt("Notes on the work done:") || "Job completed on site.";
    const action: QueuedAction = {
      idempotency_key: crypto.randomUUID(),
      action_type: "TASK_COMPLETE",
      payload: { task_id: task.task_id, note },
      label: `Complete ${task.public_id}`,
    };
    if (isOffline) {
      enqueue(action);
      return;
    }
    try {
      await api.post(`/api/field-worker/tasks/${task.task_id}/complete`, undefined, { note, resolved: true });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not complete task.");
    }
  }

  async function syncQueue() {
    if (!queue.length) return;
    setSyncing(true);
    setSyncMessage(null);
    try {
      const res = await api.post<{ applied: number; skipped: number; failed: number; message: string }>(
        "/api/field-worker/sync",
        { actions: queue.map(({ label: _label, ...rest }) => rest) },
      );
      setQueue([]);
      saveQueue([]);
      setSyncMessage(res.message);
      await load();
    } catch (err) {
      setSyncMessage(err instanceof ApiError ? err.message : "Sync failed. Will retry when back online.");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <SectionHeading eyebrow="Field worker" title="My tasks" />
        <button
          type="button"
          onClick={() => setIsOffline((v) => !v)}
          className="text-xs px-3 py-1.5 rounded-full border border-[var(--color-line-strong)] text-[var(--color-ink-soft)]"
          title="Toggle for demo purposes"
        >
          {isOffline ? "\u25CF Offline (simulated)" : "\u25CF Online"} &middot; tap to toggle
        </button>
      </div>

      {queue.length > 0 && (
        <Callout tone="warn">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <span>
              {queue.length} action{queue.length > 1 ? "s" : ""} pending sync
              {isOffline ? " (waiting for connection)" : ""}.
            </span>
            {!isOffline && (
              <Button size="sm" onClick={syncQueue} disabled={syncing}>
                {syncing ? "Syncing..." : "Sync now"}
              </Button>
            )}
          </div>
        </Callout>
      )}
      {syncMessage && (
        <div className="mt-2">
          <Callout tone="info">{syncMessage}</Callout>
        </div>
      )}
      {error && (
        <div className="mt-2">
          <Callout tone="danger">{error}</Callout>
        </div>
      )}

      <div className="mt-6">
        {tasks === null && <Spinner />}
        {tasks !== null && tasks.length === 0 && (
          <EmptyState title="No tasks assigned" description="New assignments will appear here." />
        )}
        <div className="space-y-3">
          {tasks?.map((task) => (
            <div key={task.task_id} className="border border-[var(--color-line-strong)] rounded-lg p-4">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div>
                  <p className="text-xs font-[family-name:var(--font-mono)] text-[var(--color-ink-soft)]">
                    {task.public_id}
                  </p>
                  <Link to={`/officer/complaints/${task.public_id}`} className="font-medium hover:underline">
                    {task.title}
                  </Link>
                  <p className="text-xs text-[var(--color-ink-soft)] mt-1">
                    {task.category} {task.landmark ? `\u00b7 ${task.landmark}` : ""}
                  </p>
                </div>
                <div className="flex gap-1.5 flex-wrap">
                  <PriorityBadge level={task.priority_level} />
                  <SlaBadge
                    breachRisk={task.sla.breach_risk}
                    remainingHours={task.sla.remaining_hours}
                    breached={task.sla.breached}
                  />
                </div>
              </div>
              <p className="text-sm text-[var(--color-ink-soft)] mt-2">{task.description}</p>
              <div className="flex items-center gap-2 mt-3">
                {!task.started_at && (
                  <Button size="sm" variant="secondary" onClick={() => startTask(task)}>
                    Start
                  </Button>
                )}
                <Button size="sm" onClick={() => completeTask(task)}>
                  Mark complete
                </Button>
                <span className="text-xs text-[var(--color-ink-soft)] ml-auto">
                  SLA: {formatHours(task.sla.remaining_hours)} remaining
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
