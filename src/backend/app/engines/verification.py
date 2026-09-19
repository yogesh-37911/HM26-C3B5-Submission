"""Report verification: a confidence signal, not proof.

We never auto-reject a complaint. The worst outcome a report can receive is
SUSPICIOUS, which routes it to a human for review. A real civic system that
silently discards reports will discard real ones, and the citizens whose
reports vanish are exactly the ones least able to escalate.
"""
from __future__ import annotations

from dataclasses import dataclass

MODEL_VERSION = "verify-rule-v1"

# Rough bounding box of the Mysuru urban agglomeration + adjacent panchayats.
MYSURU_BOUNDS = {"min_lat": 12.15, "max_lat": 12.50, "min_lng": 76.50, "max_lng": 76.82}

DISCLAIMER = ("Verification is a confidence signal, not proof. It cannot "
              "reliably detect a determined false report.")


@dataclass
class VerificationResult:
    status: str
    confidence: int
    factors: list[dict]

    def as_dict(self) -> dict:
        return {
            "verification_status": self.status,
            "confidence": self.confidence,
            "verification_factors": self.factors,
            "disclaimer": DISCLAIMER,
        }


def _f(code: str, label: str, verdict: str, delta: int, detail: str) -> dict:
    return {"code": code, "label": label, "verdict": verdict,
            "score_delta": delta, "detail": detail}


def verify_report(
    *,
    latitude: float,
    longitude: float,
    description: str,
    title: str,
    has_evidence: bool,
    evidence_hash_reuse_count: int = 0,
    submissions_from_user_last_hour: int = 0,
    duplicate_count: int = 0,
    inside_known_jurisdiction: bool = True,
) -> VerificationResult:
    score = 50
    factors: list[dict] = []

    # 1. Coordinate plausibility.
    in_box = (MYSURU_BOUNDS["min_lat"] <= latitude <= MYSURU_BOUNDS["max_lat"]
              and MYSURU_BOUNDS["min_lng"] <= longitude <= MYSURU_BOUNDS["max_lng"])
    if not in_box:
        score -= 35
        factors.append(_f("coords", "Coordinate plausibility", "FAIL", -35,
                          "Coordinates fall outside the Mysuru service area."))
    elif not inside_known_jurisdiction:
        score -= 10
        factors.append(_f("coords", "Coordinate plausibility", "WARN", -10,
                          "Inside Mysuru region but outside any active ward boundary."))
    else:
        score += 15
        factors.append(_f("coords", "Coordinate plausibility", "PASS", 15,
                          "Coordinates fall inside an active jurisdiction boundary."))

    # 2. Description completeness.
    words = len((description or "").split())
    if words >= 12:
        score += 15
        factors.append(_f("text", "Description completeness", "PASS", 15,
                          f"Description has {words} words with usable detail."))
    elif words >= 5:
        score += 5
        factors.append(_f("text", "Description completeness", "WARN", 5,
                          f"Description is brief ({words} words)."))
    else:
        score -= 15
        factors.append(_f("text", "Description completeness", "FAIL", -15,
                          f"Description is too short ({words} words) to act on."))

    # 3. Evidence presence.
    if has_evidence:
        score += 15
        factors.append(_f("evidence", "Photo evidence", "PASS", 15,
                          "A photo was attached with the report."))
    else:
        score -= 5
        factors.append(_f("evidence", "Photo evidence", "WARN", -5,
                          "No photo attached. Field verification will be needed."))

    # 4. Reused image hash.
    if evidence_hash_reuse_count > 0:
        delta = -25 if evidence_hash_reuse_count >= 2 else -15
        score += delta
        factors.append(_f("hash_reuse", "Repeated evidence", "FAIL", delta,
                          f"This exact image has been submitted "
                          f"{evidence_hash_reuse_count} time(s) before."))

    # 5. Submission rate from the same account/device.
    if submissions_from_user_last_hour >= 8:
        score -= 25
        factors.append(_f("rate", "Submission rate", "FAIL", -25,
                          f"{submissions_from_user_last_hour} reports from this "
                          "account in the last hour."))
    elif submissions_from_user_last_hour >= 4:
        score -= 10
        factors.append(_f("rate", "Submission rate", "WARN", -10,
                          f"{submissions_from_user_last_hour} reports from this "
                          "account in the last hour."))

    # 6. Corroboration. Independent reports of the same issue raise trust.
    if duplicate_count >= 2:
        score += 12
        factors.append(_f("corroboration", "Independent corroboration", "PASS", 12,
                          f"{duplicate_count} other citizens reported a similar "
                          "issue nearby."))

    score = max(0, min(100, score))
    if score >= 75:
        status = "VERIFIED"
    elif score >= 55:
        status = "PLAUSIBLE"
    elif score >= 35:
        status = "NEEDS_REVIEW"
    else:
        status = "SUSPICIOUS"

    return VerificationResult(status=status, confidence=score, factors=factors)
