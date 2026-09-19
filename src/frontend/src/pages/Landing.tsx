import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui/Primitives";
import { useLang } from "../lib/i18n";

export function Landing() {
  const navigate = useNavigate();
  const { t } = useLang();

  const steps = [
    t.stepReport,
    t.stepVerify,
    t.stepRoute,
    t.stepPrioritize,
    t.stepPredict,
    t.stepAct,
    t.stepResolve,
  ];

  return (
    <div>
      <section className="grid lg:grid-cols-[1.1fr_0.9fr] gap-12 items-center py-8 lg:py-16">
        <div className="rise-in">
          <p className="text-xs font-semibold tracking-wide text-[var(--color-gold-700)] mb-4">
            {t.eyebrowGov}
          </p>
          <h1 className="font-[family-name:var(--font-display)] text-3xl sm:text-5xl leading-[1.1] text-[var(--color-ink)]">
            {t.landingTitle}
          </h1>
          <p className="mt-5 text-base text-[var(--color-ink-soft)] max-w-lg leading-relaxed">
            {t.landingSubtitle}
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button onClick={() => navigate("/citizen/report")}>{t.reportIssue}</Button>
            <Button variant="secondary" onClick={() => navigate("/citizen/complaints")}>
              {t.trackComplaint}
            </Button>
            <Button variant="ghost" onClick={() => navigate("/public")}>
              {t.publicDashboard}
            </Button>
            <Button variant="ghost" onClick={() => navigate("/login")}>
              {t.officerLogin}
            </Button>
          </div>
        </div>

        <div className="rise-in" style={{ animationDelay: "80ms" }}>
          <div className="border border-[var(--color-line-strong)] rounded-xl bg-[var(--color-paper-raised)] p-6 shadow-xs">
            <p className="text-xs font-semibold text-[var(--color-ink-soft)] mb-4 uppercase tracking-wider">
              {t.flowTitle}
            </p>
            <ol className="space-y-0">
              {steps.map((step, i) => (
                <li key={step} className="flex items-center gap-3 py-2.5 border-b border-[var(--color-line)] last:border-0">
                  <span className="font-[family-name:var(--font-mono)] text-xs text-[var(--color-teal-600)] w-5 font-bold">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span className="text-sm font-medium text-[var(--color-ink)]">{step}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      <section className="grid sm:grid-cols-3 gap-8 py-10 border-t border-[var(--color-line)]">
        <div>
          <h3 className="font-[family-name:var(--font-display)] text-lg mb-2 font-semibold">{t.predictiveEngine}</h3>
          <p className="text-sm text-[var(--color-ink-soft)] leading-relaxed">
            {t.predictiveDesc}
          </p>
        </div>
        <div>
          <h3 className="font-[family-name:var(--font-display)] text-lg mb-2 font-semibold">{t.safeBoundaries}</h3>
          <p className="text-sm text-[var(--color-ink-soft)] leading-relaxed">
            {t.safeBoundariesDesc}
          </p>
        </div>
        <div>
          <h3 className="font-[family-name:var(--font-display)] text-lg mb-2 font-semibold">{t.transparency}</h3>
          <p className="text-sm text-[var(--color-ink-soft)] leading-relaxed">
            {t.transparencyDesc}
          </p>
        </div>
      </section>
    </div>
  );
}
