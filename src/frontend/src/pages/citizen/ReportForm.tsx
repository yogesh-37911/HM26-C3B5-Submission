import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../../lib/api";
import type { Category, DuplicateMatch } from "../../lib/types";
import { Button, Callout, SectionHeading, Spinner } from "../../components/ui/Primitives";
import { LocationPicker } from "../../components/map/ComplaintMap";

const MYSURU_DEFAULT: [number, number] = [12.3052, 76.6552];

export function ReportForm() {
  const navigate = useNavigate();
  const [categories, setCategories] = useState<Category[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [categoryCode, setCategoryCode] = useState("");
  const [landmark, setLandmark] = useState("");
  const [lat, setLat] = useState(MYSURU_DEFAULT[0]);
  const [lng, setLng] = useState(MYSURU_DEFAULT[1]);
  const [locating, setLocating] = useState(false);

  const [checkingDup, setCheckingDup] = useState(false);
  const [dupMatches, setDupMatches] = useState<DuplicateMatch[]>([]);
  const [acknowledgedDup, setAcknowledgedDup] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<{ items: Category[] }>("/api/meta/categories").then((r) => {
      setCategories(r.items);
      if (r.items.length) setCategoryCode(r.items[0].code);
    });
  }, []);

  // Live duplicate probe, debounced, once there's enough to check against.
  useEffect(() => {
    if (!categoryCode || title.length < 5 || description.length < 10) {
      setDupMatches([]);
      return;
    }
    setAcknowledgedDup(false);
    const handle = setTimeout(async () => {
      setCheckingDup(true);
      try {
        const res = await api.post<{ possible_duplicate: boolean; matches: DuplicateMatch[] }>(
          "/api/complaints/check-duplicates",
          { title, description, category_code: categoryCode, latitude: lat, longitude: lng },
        );
        setDupMatches(res.matches);
      } catch {
        // duplicate probe is best-effort; ignore failures silently
      } finally {
        setCheckingDup(false);
      }
    }, 700);
    return () => clearTimeout(handle);
  }, [title, description, categoryCode, lat, lng]);

  function useMyLocation() {
    if (!navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLat(pos.coords.latitude);
        setLng(pos.coords.longitude);
        setLocating(false);
      },
      () => setLocating(false),
      { timeout: 8000 },
    );
  }

  async function handleSubmit() {
    setError(null);
    setSubmitting(true);
    try {
      const res = await api.post<{ complaint: { public_id: string } }>("/api/complaints", {
        title,
        description,
        category_code: categoryCode,
        latitude: lat,
        longitude: lng,
        landmark: landmark || undefined,
        idempotency_key: crypto.randomUUID(),
      });
      navigate(`/citizen/complaints/${res.complaint.public_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit the report. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  const hasUnresolvedDuplicate = dupMatches.length > 0 && !acknowledgedDup;
  const canSubmit = title.length >= 5 && description.length >= 10 && categoryCode && !submitting;

  return (
    <div className="max-w-2xl mx-auto">
      <SectionHeading
        eyebrow="Citizen"
        title="Report an issue"
        description="Give enough detail for an officer to act on it. A photo isn't required, but it helps verification."
      />

      <div className="space-y-5">
        <div>
          <label className="block text-xs font-medium text-[var(--color-ink-soft)] mb-1">Category</label>
          <select
            value={categoryCode}
            onChange={(e) => setCategoryCode(e.target.value)}
            className="w-full rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-3 py-2.5 text-sm outline-none focus:border-[var(--color-teal-600)]"
          >
            {categories.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name_en} &middot; {c.name_kn}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-[var(--color-ink-soft)] mb-1">Title</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Large pothole near the school gate"
            className="w-full rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-3 py-2.5 text-sm outline-none focus:border-[var(--color-teal-600)]"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-[var(--color-ink-soft)] mb-1">Description</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder="What's wrong, and why it matters - e.g. two-wheelers are swerving into traffic to avoid it."
            className="w-full rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-3 py-2.5 text-sm outline-none focus:border-[var(--color-teal-600)] resize-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-[var(--color-ink-soft)] mb-1">Landmark (optional)</label>
          <input
            value={landmark}
            onChange={(e) => setLandmark(e.target.value)}
            placeholder="Near Kuvempunagar bus stop"
            className="w-full rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-3 py-2.5 text-sm outline-none focus:border-[var(--color-teal-600)]"
          />
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-[var(--color-ink-soft)]">Location</label>
            <button
              type="button"
              onClick={useMyLocation}
              className="text-xs text-[var(--color-teal-700)] hover:underline"
            >
              {locating ? "Locating..." : "Use my location"}
            </button>
          </div>
          <p className="text-xs text-[var(--color-ink-soft)] mb-2">
            Click anywhere on the map to place the pin. Coordinates: {lat.toFixed(5)}, {lng.toFixed(5)}
          </p>
          <LocationPicker lat={lat} lng={lng} onChange={(nl, ng) => { setLat(nl); setLng(ng); }} />
        </div>

        {checkingDup && <Spinner label="Checking for duplicates nearby..." />}

        {dupMatches.length > 0 && (
          <Callout tone="warn">
            <p className="font-medium mb-2">Possible duplicate found nearby</p>
            <ul className="space-y-2">
              {dupMatches.map((m) => (
                <li key={m.complaint_id} className="text-sm">
                  <span className="font-[family-name:var(--font-mono)]">{m.public_id}</span> &mdash; {m.title}
                  <br />
                  <span className="text-xs opacity-80">
                    {m.distance_m}m away, {m.text_similarity_pct}% text overlap, {m.similarity_pct}% overall match.
                    Status: {m.status.replace("_", " ")}.
                  </span>
                </li>
              ))}
            </ul>
            <div className="flex gap-2 mt-3">
              <Button size="sm" variant="secondary" onClick={() => navigate(`/citizen/complaints/${dupMatches[0].public_id}`)}>
                Follow existing complaint
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setAcknowledgedDup(true)}>
                Submit as separate issue anyway
              </Button>
            </div>
          </Callout>
        )}

        {error && <Callout tone="danger">{error}</Callout>}

        <Button
          onClick={handleSubmit}
          disabled={!canSubmit || hasUnresolvedDuplicate}
          className="w-full"
        >
          {submitting ? "Submitting..." : "Submit report"}
        </Button>
        {hasUnresolvedDuplicate && (
          <p className="text-xs text-[var(--color-ink-soft)] text-center -mt-2">
            Follow the existing complaint above, or confirm this is a separate issue, to continue.
          </p>
        )}
      </div>
    </div>
  );
}

