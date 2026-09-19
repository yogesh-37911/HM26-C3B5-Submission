import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../../lib/api";
import type { Category, DuplicateMatch } from "../../lib/types";
import { useLang } from "../../lib/i18n";
import { Button, Callout, SectionHeading, Spinner } from "../../components/ui/Primitives";
import { LocationPicker } from "../../components/map/ComplaintMap";

const MYSURU_DEFAULT: [number, number] = [12.3052, 76.6552];

export function ReportForm() {
  const navigate = useNavigate();
  const { lang, t } = useLang();
  const [categories, setCategories] = useState<Category[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [categoryCode, setCategoryCode] = useState("");
  const [landmark, setLandmark] = useState("");
  const [lat, setLat] = useState(MYSURU_DEFAULT[0]);
  const [lng, setLng] = useState(MYSURU_DEFAULT[1]);
  const [locating, setLocating] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

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

  const [photos, setPhotos] = useState<Array<{ file: File; preview: string; id: string }>>([]);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handlePhotoFiles(files: FileList | File[]) {
    setPhotoError(null);
    const validTypes = ["image/jpeg", "image/png", "image/webp"];
    const newItems: Array<{ file: File; preview: string; id: string }> = [];

    if (photos.length + files.length > 5) {
      setPhotoError("Maximum 5 photos allowed. Please select up to 5 photos in total.");
      return;
    }

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (!validTypes.includes(file.type.toLowerCase())) {
        setPhotoError("Only JPEG, PNG, and WebP images are allowed.");
        return;
      }
      if (file.size > 5 * 1024 * 1024) {
        setPhotoError(`"${file.name}" exceeds the 5 MB file size limit.`);
        return;
      }
      newItems.push({
        file,
        preview: URL.createObjectURL(file),
        id: `${file.name}-${file.lastModified}-${Math.random()}`,
      });
    }

    setPhotos((prev) => [...prev, ...newItems]);
  }

  function removePhoto(idToRemove: string) {
    setPhotos((prev) => {
      const target = prev.find((p) => p.id === idToRemove);
      if (target) URL.revokeObjectURL(target.preview);
      return prev.filter((p) => p.id !== idToRemove);
    });
    setPhotoError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
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

      const pubId = res.complaint.public_id;

      // Upload all selected photos sequentially to the complaint
      for (const item of photos) {
        try {
          const fd = new FormData();
          fd.append("file", item.file);
          await api.upload(`/api/complaints/${pubId}/evidence`, fd, { stage: "REPORT" });
        } catch (uploadErr) {
          console.warn("Evidence photo upload failed for:", item.file.name, uploadErr);
        }
      }

      // Cleanup object URLs
      photos.forEach((p) => URL.revokeObjectURL(p.preview));

      navigate(`/citizen/complaints/${pubId}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.somethingWentWrong);
    } finally {
      setSubmitting(false);
    }
  }

  const hasUnresolvedDuplicate = dupMatches.length > 0 && !acknowledgedDup;
  const canSubmit = title.length >= 5 && description.length >= 10 && categoryCode && !submitting;

  return (
    <div className="max-w-2xl mx-auto">
      <SectionHeading
        eyebrow={t.roleCitizen}
        title={t.reportIssue}
        description={lang === "kn" ? "ಅಧಿಕಾರಿಗಳು ಕ್ರಮ ಕೈಗೊಳ್ಳಲು ಸಾಕಷ್ಟು ವಿವರಗಳನ್ನು ನೀಡಿ. ಫೋಟೋ ಕಡ್ಡಾಯವಲ್ಲ, ಆದರೆ ತ್ವರಿತ ಪರಿಶೀಲನೆಗೆ ಸಹಾಯ ಮಾಡುತ್ತದೆ." : "Give enough detail for an officer to act on it. A photo isn't required, but it helps rapid verification."}
      />

      <div className="space-y-5">
        <div>
          <label className="block text-xs font-medium text-[var(--color-ink-soft)] mb-1">{t.category}</label>
          <select
            value={categoryCode}
            onChange={(e) => setCategoryCode(e.target.value)}
            className="w-full rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-3 py-2.5 text-sm outline-none focus:border-[var(--color-teal-600)]"
          >
            {categories.map((c) => (
              <option key={c.code} value={c.code}>
                {lang === "kn" && c.name_kn ? `${c.name_kn} (${c.name_en})` : `${c.name_en} · ${c.name_kn}`}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-[var(--color-ink-soft)] mb-1">{t.title}</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={lang === "kn" ? "ಉದಾಹರಣೆಗೆ: ಶಾಲೆಯ ಗೇಟ್ ಬಳಿ ದೊಡ್ಡ ಗುಂಡಿ" : "Large pothole near the school gate"}
            className="w-full rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-3 py-2.5 text-sm outline-none focus:border-[var(--color-teal-600)]"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-[var(--color-ink-soft)] mb-1">{t.description}</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder={lang === "kn" ? "ಏನು ಸಮಸ್ಯೆಯಾಗಿದೆ ಮತ್ತು ಏಕೆ ಮುಖ್ಯ - ಉದಾ: ದ್ವಿಚಕ್ರ ವಾಹನ ಸವಾರರು ತಪ್ಪಿಸಲು ವಾಹನಗಳ ನಡುವೆ ನುಗ್ಗುತ್ತಿದ್ದಾರೆ." : "What's wrong, and why it matters - e.g. two-wheelers are swerving into traffic to avoid it."}
            className="w-full rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-3 py-2.5 text-sm outline-none focus:border-[var(--color-teal-600)] resize-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-[var(--color-ink-soft)] mb-1">{t.landmark}</label>
          <input
            value={landmark}
            onChange={(e) => setLandmark(e.target.value)}
            placeholder={lang === "kn" ? "ಉದಾ: ಕುವೆಂಪುನಗರ ಬಸ್ ನಿಲ್ದಾಣದ ಬಳಿ" : "Near Kuvempunagar bus stop"}
            className="w-full rounded-md border border-[var(--color-line-strong)] bg-[var(--color-paper-raised)] px-3 py-2.5 text-sm outline-none focus:border-[var(--color-teal-600)]"
          />
        </div>

        {/* Multi-Photo Upload Section */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-[var(--color-ink-soft)] flex items-center gap-1.5">
              <span>{t.photoUpload}</span>
              <span className="text-[11px] font-normal text-[var(--color-teal-700)]">({photos.length}/5)</span>
            </label>
            <span className="text-[11px] text-[var(--color-ink-soft)]">{t.maxPhotosLimit}</span>
          </div>

          {photos.length < 5 && (
            <div
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setIsDragging(false);
                if (e.dataTransfer.files?.length) handlePhotoFiles(e.dataTransfer.files);
              }}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-lg p-5 text-center cursor-pointer transition-all ${
                isDragging
                  ? "border-[var(--color-teal-600)] bg-[var(--color-teal-100)]/40"
                  : "border-[var(--color-line-strong)] hover:border-[var(--color-teal-600)] bg-[var(--color-paper-raised)]"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={(e: ChangeEvent<HTMLInputElement>) => {
                  if (e.target.files?.length) handlePhotoFiles(e.target.files);
                }}
              />
              <div className="flex flex-col items-center gap-1.5">
                <div className="w-9 h-9 rounded-full bg-[var(--color-teal-100)] text-[var(--color-teal-700)] flex items-center justify-center">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>
                    <circle cx="9" cy="9" r="2"/>
                    <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>
                  </svg>
                </div>
                <p className="text-sm font-medium text-[var(--color-ink)]">
                  {t.dragOrBrowse}
                </p>
                <p className="text-xs text-[var(--color-ink-soft)] max-w-md">
                  {t.photoHelp}
                </p>
              </div>
            </div>
          )}

          {/* Attached Photos Grid Preview */}
          {photos.length > 0 && (
            <div className="mt-3 space-y-2">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {photos.map((p) => (
                  <div
                    key={p.id}
                    className="border border-[var(--color-line-strong)] rounded-lg p-2.5 bg-[var(--color-paper-raised)] flex items-center gap-3 shadow-xs"
                  >
                    <img
                      src={p.preview}
                      alt={p.file.name}
                      className="w-14 h-14 object-cover rounded border border-[var(--color-line)] shrink-0 bg-black/5"
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-[var(--color-ink)] truncate" title={p.file.name}>
                        {p.file.name}
                      </p>
                      <p className="text-[11px] text-[var(--color-ink-soft)] mt-0.5">
                        {(p.file.size / (1024 * 1024) >= 1 ? `${(p.file.size / (1024 * 1024)).toFixed(1)} MB` : `${Math.round(p.file.size / 1024)} KB`)}
                      </p>
                      <span className="inline-flex items-center text-[10px] font-medium text-[var(--color-good-700)] bg-[var(--color-good-100)] px-1.5 py-0.2 rounded mt-1">
                        {t.sharedWithOfficerBadge}
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        removePhoto(p.id);
                      }}
                      className="p-1 rounded text-[var(--color-danger-700)] hover:bg-[var(--color-danger-100)] text-xs font-medium"
                      title={t.removePhoto}
                    >
                      {t.removePhoto}
                    </button>
                  </div>
                ))}
              </div>

              {/* Automatic Officer Sharing Reassurance Notice */}
              <div className="p-2.5 rounded-md bg-[var(--color-good-100)]/40 border border-[var(--color-good-500)]/30 text-xs text-[var(--color-good-700)] flex items-center gap-2">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
                  <path d="M20 6 9 17l-5-5"/>
                </svg>
                <span className="font-medium">{t.photosSharedNotice}</span>
              </div>
            </div>
          )}

          {photoError && (
            <p className="text-xs text-[var(--color-danger-700)] mt-1.5">{photoError}</p>
          )}
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-[var(--color-ink-soft)]">{t.location}</label>
            <button
              type="button"
              onClick={useMyLocation}
              className="text-xs text-[var(--color-teal-700)] hover:underline"
            >
              {locating ? (lang === "kn" ? "ಸ್ಥಳ ಪತ್ತೆಮಾಡಲಾಗುತ್ತಿದೆ..." : "Locating...") : t.useMyLocation}
            </button>
          </div>
          <p className="text-xs text-[var(--color-ink-soft)] mb-2">
            {t.dragPinPrompt} Coordinates: {lat.toFixed(5)}, {lng.toFixed(5)}
          </p>
          <LocationPicker lat={lat} lng={lng} onChange={(nl, ng) => { setLat(nl); setLng(ng); }} />
        </div>

        {checkingDup && <Spinner label={t.checking} />}

        {dupMatches.length > 0 && (
          <Callout tone="warn">
            <p className="font-medium mb-2">{t.possibleDuplicate}</p>
            <ul className="space-y-2">
              {dupMatches.map((m) => (
                <li key={m.complaint_id} className="text-sm">
                  <span className="font-[family-name:var(--font-mono)]">{m.public_id}</span> &mdash; {m.title}
                  <br />
                  <span className="text-xs opacity-80">
                    {m.distance_m}m {t.away}, {m.similarity_pct}% {t.similar}.
                    {t.status}: {m.status.replace("_", " ")}.
                  </span>
                </li>
              ))}
            </ul>
            <div className="flex gap-2 mt-3">
              <Button size="sm" variant="secondary" onClick={() => navigate(`/citizen/complaints/${dupMatches[0].public_id}`)}>
                {t.followExisting}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setAcknowledgedDup(true)}>
                {t.submitSeparately}
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
          {submitting ? t.submitting : t.submit}
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

