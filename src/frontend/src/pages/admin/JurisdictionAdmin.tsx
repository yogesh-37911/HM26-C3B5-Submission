import { useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { JurisdictionVersion } from "../../lib/types";
import { Button, Callout, SectionHeading, Spinner } from "../../components/ui/Primitives";
import { formatDate } from "../../lib/format";

export function JurisdictionAdmin() {
  const [versions, setVersions] = useState<JurisdictionVersion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [jurisdictionId, setJurisdictionId] = useState("42");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const r = await api.get<{ items: JurisdictionVersion[] }>("/api/jurisdictions/versions");
    setVersions(r.items);
  }

  useEffect(() => {
    load();
  }, []);

  async function publishNow() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      // A small square around Ward 42's demo centre, well inside the Mysuru
      // service area, so the "publish and observe rerouting" demo has an
      // immediate, visible effect without hand-editing coordinates.
      const boundary = [
        [12.281, 76.615],
        [12.291, 76.615],
        [12.291, 76.625],
        [12.281, 76.625],
      ];
      const res = await api.post<{ version_label: string; note: string }>("/api/jurisdictions/version", {
        jurisdiction_id: Number(jurisdictionId),
        version_label: label || `demo-${Date.now().toString(36)}`,
        effective_from: "2020-01-01T00:00:00Z",
        boundary,
        close_previous: true,
      });
      setNotice(`Published version "${res.version_label}". ${res.note}`);
      setLabel("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not publish version.");
    } finally {
      setBusy(false);
    }
  }

  if (versions === null) return <Spinner />;

  return (
    <div>
      <SectionHeading
        eyebrow="Admin"
        title="Jurisdiction versions"
        description="Boundaries are versioned, not hard-coded. Publishing a new version reroutes future complaints only - history is untouched."
      />

      <div className="border border-[var(--color-line-strong)] rounded-lg p-5 mb-8">
        <h3 className="text-sm font-medium mb-3">Publish a demo boundary revision</h3>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs text-[var(--color-ink-soft)] mb-1">Jurisdiction ID</label>
            <input
              value={jurisdictionId}
              onChange={(e) => setJurisdictionId(e.target.value)}
              className="w-28 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-2.5 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-[var(--color-ink-soft)] mb-1">Version label</label>
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. demo-now"
              className="w-40 rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-2.5 py-2 text-sm"
            />
          </div>
          <Button onClick={publishNow} disabled={busy}>
            {busy ? "Publishing..." : "Publish immediately"}
          </Button>
        </div>
        <p className="text-xs text-[var(--color-ink-soft)] mt-2">
          Publishes a shrunk boundary for the given jurisdiction, effective retroactively, so the
          effect is visible right away for the demo. Existing complaints keep their original routing.
        </p>
        {notice && (
          <div className="mt-3">
            <Callout tone="info">{notice}</Callout>
          </div>
        )}
        {error && (
          <div className="mt-3">
            <Callout tone="danger">{error}</Callout>
          </div>
        )}
      </div>

      <h3 className="text-sm font-medium mb-3">All versions</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-[var(--color-ink-soft)] border-b border-[var(--color-line-strong)]">
              <th className="py-2 pr-3 font-medium">Jurisdiction</th>
              <th className="py-2 pr-3 font-medium">Version</th>
              <th className="py-2 pr-3 font-medium">Effective from</th>
              <th className="py-2 pr-3 font-medium">Effective to</th>
              <th className="py-2 pr-3 font-medium">Active</th>
            </tr>
          </thead>
          <tbody>
            {versions
              .sort((a, b) => (a.effective_from < b.effective_from ? 1 : -1))
              .slice(0, 40)
              .map((v) => (
                <tr key={v.id} className="border-b border-[var(--color-line)]">
                  <td className="py-2 pr-3">{v.name}</td>
                  <td className="py-2 pr-3 font-[family-name:var(--font-mono)]">{v.version_label}</td>
                  <td className="py-2 pr-3">{formatDate(v.effective_from)}</td>
                  <td className="py-2 pr-3">{v.effective_to ? formatDate(v.effective_to) : "open-ended"}</td>
                  <td className="py-2 pr-3">
                    {v.is_active ? (
                      <span className="text-[var(--color-good-700)]">Active</span>
                    ) : (
                      <span className="text-[var(--color-ink-soft)]">Superseded</span>
                    )}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
