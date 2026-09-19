import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { DashboardOverview, MapMarker, WardExplain, WardSummary } from "../../lib/types";
import { SectionHeading, Spinner, StatCard } from "../../components/ui/Primitives";
import { ComplaintMap } from "../../components/map/ComplaintMap";
import { useLang } from "../../lib/i18n";

const MYSURU_BOUNDS = { min_lat: 12.15, max_lat: 12.5, min_lng: 76.5, max_lng: 76.82 };

export function PublicDashboard() {
  const { lang, t } = useLang();
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [wards, setWards] = useState<WardSummary[] | null>(null);
  const [markers, setMarkers] = useState<MapMarker[]>([]);
  const [selectedWard, setSelectedWard] = useState<number | null>(null);
  const [explain, setExplain] = useState<WardExplain | null>(null);

  useEffect(() => {
    api.get<DashboardOverview>("/api/dashboard/overview").then(setOverview);
    api.get<{ items: WardSummary[] }>("/api/dashboard/wards").then((r) => setWards(r.items));
    api
      .get<{ markers: MapMarker[] }>("/api/dashboard/map", { ...MYSURU_BOUNDS, limit: 300 })
      .then((r) => setMarkers(r.markers));
  }, []);

  useEffect(() => {
    if (selectedWard === null) {
      setExplain(null);
      return;
    }
    api.get<WardExplain>(`/api/dashboard/wards/${selectedWard}/explain`).then(setExplain);
  }, [selectedWard]);

  if (!overview || !wards) return <Spinner />;

  return (
    <div>
      <SectionHeading
        eyebrow={lang === "kn" ? "ಸಾರ್ವಜನಿಕ" : "Public"}
        title={t.publicOverview}
        description={lang === "kn" ? "ಮೈಸೂರಿನಾದ್ಯಂತ ನಾಗರಿಕ ದೂರುಗಳ ಲೈವ್ ಸ್ಥಿತಿ, ಎಲ್ಲರೂ ವೀಕ್ಷಿಸಲು ಮುಕ್ತವಾಗಿದೆ." : "Live status of civic complaints across Mysuru, for anyone to see."}
      />
      <p className="text-xs text-[var(--color-warn-700)] bg-[var(--color-warn-100)] inline-block px-2.5 py-1 rounded-md mb-6">
        {overview.disclaimer}
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-5 mb-10">
        <StatCard label={t.totalComplaints} value={overview.total_complaints} />
        <StatCard label={t.openStat} value={overview.open_complaints} />
        <StatCard label={t.resolvedComplaints} value={overview.resolved_complaints} tone="good" />
        <StatCard label={t.resolutionRate} value={`${overview.resolution_rate_pct}%`} tone="good" />
        <StatCard label={t.highRiskOpen} value={overview.high_risk_open} tone="danger" />
        <StatCard label={t.slaBreachStat} value={overview.sla_breached_open} tone="warn" />
        <StatCard label={t.stagnantComplaints} value={overview.stagnant_complaints} tone="warn" />
        <StatCard
          label={t.avgResolution}
          value={overview.avg_resolution_hours ? `${Math.round(overview.avg_resolution_hours)}h` : "-"}
        />
      </div>

      <section className="mb-10">
        <h2 className="font-[family-name:var(--font-display)] text-lg mb-3">{t.map}</h2>
        <ComplaintMap
          markers={markers}
          height={440}
          onSelect={(m) => {
            if (m.jurisdiction_id) {
              setSelectedWard(m.jurisdiction_id);
              return;
            }
            if (m.ward) {
              const w = wards.find((x) => x.ward === m.ward);
              if (w) {
                setSelectedWard(w.jurisdiction_id);
                return;
              }
            }
            const w = wards.find((x) => (x.name ?? "").includes((m.jurisdiction || "").split(" Ward")[0] ?? "___"));
            if (w) setSelectedWard(w.jurisdiction_id);
          }}
        />
      </section>

      <section className="grid lg:grid-cols-[1.1fr_0.9fr] gap-10">
        <div>
          <h2 className="font-[family-name:var(--font-display)] text-lg mb-3">{t.byWard}</h2>
          <div className="overflow-x-auto rounded-lg border border-[var(--color-line)] bg-[var(--color-paper-raised)]">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-[var(--color-ink-soft)] border-b border-[var(--color-line-strong)] bg-[var(--color-paper)]">
                  <th className="py-2.5 px-3 font-medium">{t.wardCol}</th>
                  <th className="py-2.5 px-3 font-medium">{t.openStat}</th>
                  <th className="py-2.5 px-3 font-medium">{t.highRiskStat}</th>
                  <th className="py-2.5 px-3 font-medium">{t.resolutionRate}</th>
                </tr>
              </thead>
              <tbody>
                {wards.slice(0, 20).map((w) => (
                  <tr
                    key={w.jurisdiction_id}
                    onClick={() => setSelectedWard(w.jurisdiction_id)}
                    className={`border-b border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-paper)]/60 transition-colors ${
                      selectedWard === w.jurisdiction_id ? "bg-[var(--color-teal-100)] font-medium" : ""
                    }`}
                  >
                    <td className="py-2 px-3">{w.name}</td>
                    <td className="py-2 px-3">{w.open}</td>
                    <td className="py-2 px-3 text-[var(--color-danger-700)]">{w.high_risk || "-"}</td>
                    <td className="py-2 px-3">{w.resolution_rate_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <h2 className="font-[family-name:var(--font-display)] text-lg mb-3">{t.wardExplain}</h2>
          {!explain && (
            <p className="text-sm text-[var(--color-ink-soft)]">{t.selectWardPrompt}</p>
          )}
          {explain && (
            <div className="p-4 rounded-lg border border-[var(--color-line)] bg-[var(--color-paper-raised)]">
              <p className="font-semibold text-sm mb-1">{explain.jurisdiction.name}</p>
              <p className="text-xs text-[var(--color-ink-soft)] mb-4">
                {explain.open_complaints} {t.openStat.toLowerCase()} &middot; {explain.unassigned} {t.unassignedStat.toLowerCase()} &middot; {explain.high_risk} {t.highRiskStat.toLowerCase()}
              </p>
              <ol className="space-y-3">
                {explain.reasons.map((r, i) => (
                  <li key={r.code} className="border-l-2 border-[var(--color-gold-500)] pl-3">
                    <p className="text-sm font-medium text-[var(--color-ink)]">
                      <span className="font-[family-name:var(--font-mono)] text-xs text-[var(--color-ink-soft)] mr-1.5">
                        {i + 1}.
                      </span>
                      {r.text}
                    </p>
                    <p className="text-xs text-[var(--color-teal-700)] mt-0.5">{r.action}</p>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
