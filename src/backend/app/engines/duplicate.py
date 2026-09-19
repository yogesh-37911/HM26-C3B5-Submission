"""Duplicate detection.

Combines three independent signals into one similarity score:

    similarity = 0.45 * spatial + 0.40 * textual + 0.15 * temporal

with a hard gate on category: two complaints in different categories are never
proposed as duplicates, because a pothole and a streetlight at the same
junction are two separate jobs for two separate teams.

Text similarity uses token Jaccard plus a character trigram Dice coefficient,
with civic stopwords removed and Kannada text handled by the trigram half.
No embedding model is used: at 150m radius with a category gate the candidate
set is tiny, and a transparent lexical score is something an officer can argue
with. The engine NEVER deletes or auto-merges - it proposes, the human decides.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .geo import haversine_m

MODEL_VERSION = "dup-lexical-v1"

STOPWORDS = {
    "the", "a", "an", "is", "at", "in", "on", "near", "of", "and", "to", "for",
    "there", "here", "this", "that", "very", "please", "sir", "madam", "it",
    "has", "have", "been", "was", "are", "we", "my", "our", "from", "by",
    "complaint", "issue", "problem", "kindly", "request", "area",
}

_word_re = re.compile(r"[\w\u0C80-\u0CFF]+", re.UNICODE)


def tokenize(text: str) -> set[str]:
    return {t for t in _word_re.findall((text or "").lower()) if t not in STOPWORDS and len(t) > 1}


def trigrams(text: str) -> set[str]:
    s = re.sub(r"\s+", " ", (text or "").lower()).strip()
    return {s[i:i + 3] for i in range(len(s) - 2)} if len(s) >= 3 else set()


def text_similarity(a: str, b: str) -> float:
    """0..1 lexical similarity, script-agnostic."""
    ta, tb = tokenize(a), tokenize(b)
    jaccard = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0

    ga, gb = trigrams(a), trigrams(b)
    dice = (2 * len(ga & gb) / (len(ga) + len(gb))) if (ga and gb) else 0.0

    return round(0.55 * jaccard + 0.45 * dice, 4)


def spatial_similarity(distance_m: float, radius_m: float) -> float:
    if distance_m >= radius_m:
        return 0.0
    return round(1.0 - (distance_m / radius_m) ** 0.7, 4)


def temporal_similarity(hours_apart: float, window_hours: float) -> float:
    if hours_apart >= window_hours:
        return 0.0
    return round(1.0 - (hours_apart / window_hours), 4)


@dataclass
class DuplicateMatch:
    complaint_id: int
    public_id: str
    title: str
    status: str
    distance_m: float
    text_similarity: float
    hours_apart: float
    similarity: float
    reason: str

    def as_dict(self) -> dict:
        return {
            "complaint_id": self.complaint_id,
            "public_id": self.public_id,
            "title": self.title,
            "status": self.status,
            "distance_m": round(self.distance_m),
            "text_similarity_pct": round(self.text_similarity * 100),
            "hours_apart": round(self.hours_apart, 1),
            "similarity_pct": round(self.similarity * 100),
            "reason": self.reason,
        }


def score_candidate(
    *,
    new_lat: float, new_lng: float, new_text: str, new_created_hours_ago: float,
    cand_lat: float, cand_lng: float, cand_text: str, cand_created_hours_ago: float,
    radius_m: float, window_hours: float,
) -> tuple[float, float, float, float]:
    """Return (similarity, distance_m, text_sim, hours_apart)."""
    dist = haversine_m(new_lat, new_lng, cand_lat, cand_lng)
    txt = text_similarity(new_text, cand_text)
    hours_apart = abs(new_created_hours_ago - cand_created_hours_ago)

    spatial = spatial_similarity(dist, radius_m)
    temporal = temporal_similarity(hours_apart, window_hours)
    sim = 0.45 * spatial + 0.40 * txt + 0.15 * temporal
    return round(sim, 4), dist, txt, hours_apart


def build_reason(distance_m: float, text_sim: float, hours_apart: float) -> str:
    parts = [f"{distance_m:.0f}m away"]
    parts.append(f"{text_sim * 100:.0f}% text overlap")
    if hours_apart < 48:
        parts.append(f"reported {hours_apart:.0f}h apart")
    else:
        parts.append(f"reported {hours_apart / 24:.0f} days apart")
    return "Same category, " + ", ".join(parts) + "."
