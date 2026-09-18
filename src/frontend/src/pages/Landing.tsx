import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui/Primitives";

const FLOW = ["Report", "Verify", "Route", "Prioritize", "Predict", "Act", "Resolve"];

export function Landing() {
  const navigate = useNavigate();
  return (
    <div>
      <section className="grid lg:grid-cols-[1.1fr_0.9fr] gap-12 items-center py-8 lg:py-16">
        <div className="rise-in">
          <p className="text-xs font-medium tracking-wide text-[var(--color-gold-700)] mb-4">
            HackMysuru 1.0 &middot; Sub-problem 2: Follow-through
          </p>
          <h1 className="font-[family-name:var(--font-display)] text-4xl sm:text-5xl leading-[1.08] text-[var(--color-ink)]">
            From complaint to closure &mdash; before civic issues are forgotten.
          </h1>
          <p className="mt-5 text-base text-[var(--color-ink-soft)] max-w-lg leading-relaxed">
            An explainable civic intelligence platform for Mysuru that routes, verifies,
            prioritizes and tracks complaints so nothing quietly stalls between a citizen's
            report and an officer's action.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button onClick={() => navigate("/citizen/report")}>Report an Issue</Button>
            <Button variant="secondary" onClick={() => navigate("/citizen/complaints")}>
              Track Complaint
            </Button>
            <Button variant="ghost" onClick={() => navigate("/public")}>
              Public Dashboard
            </Button>
            <Button variant="ghost" onClick={() => navigate("/login")}>
              Officer Login
            </Button>
          </div>
        </div>

        <div className="rise-in" style={{ animationDelay: "80ms" }}>
          <div className="border border-[var(--color-line-strong)] rounded-lg bg-[var(--color-paper-raised)] p-6">
            <p className="text-xs text-[var(--color-ink-soft)] mb-4">
              What happens the moment a complaint is filed
            </p>
            <ol className="space-y-0">
              {FLOW.map((step, i) => (
                <li key={step} className="flex items-center gap-3 py-2.5 border-b border-[var(--color-line)] last:border-0">
                  <span className="font-[family-name:var(--font-mono)] text-xs text-[var(--color-teal-600)] w-5">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span className="text-sm text-[var(--color-ink)]">{step}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      <section className="grid sm:grid-cols-3 gap-8 py-10 border-t border-[var(--color-line)]">
        <div>
          <h3 className="font-[family-name:var(--font-display)] text-lg mb-2">Predictive neglect engine</h3>
          <p className="text-sm text-[var(--color-ink-soft)] leading-relaxed">
            Every open complaint carries a 0-100 neglect-risk score with a plain-language
            explanation and a recommended action &mdash; not a mysterious number.
          </p>
        </div>
        <div>
          <h3 className="font-[family-name:var(--font-display)] text-lg mb-2">Boundaries that change safely</h3>
          <p className="text-sm text-[var(--color-ink-soft)] leading-relaxed">
            Jurisdictions are versioned. A ward redraw affects new complaints only &mdash;
            history never silently rewrites itself.
          </p>
        </div>
        <div>
          <h3 className="font-[family-name:var(--font-display)] text-lg mb-2">Nothing vanishes silently</h3>
          <p className="text-sm text-[var(--color-ink-soft)] leading-relaxed">
            Duplicates are surfaced, not deleted. Suspicious reports are flagged for review,
            never auto-rejected.
          </p>
        </div>
      </section>
    </div>
  );
}
