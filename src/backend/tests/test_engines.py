"""Unit tests for the scoring engines.

The engines are pure functions with no database or clock dependency, which is
precisely why they are testable: every assertion below pins a behaviour we
claim in the documentation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.engines import duplicate as dup
from app.engines.geo import bbox_for_radius, haversine_m, jitter_for_public, point_in_polygon
from app.engines.jurisdiction import active_versions, resolve
from app.engines.priority import compute_priority
from app.engines.risk import compute_risk
from app.engines.sla import sla_state
from app.engines.verification import verify_report

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------- geo
def test_haversine_known_distance():
    # Mysuru Palace to Chamundi Hill, roughly 4.4 km apart.
    d = haversine_m(12.3052, 76.6552, 12.2724, 76.6706)
    assert 3500 < d < 5200


def test_bbox_contains_radius():
    min_lat, max_lat, min_lng, max_lng = bbox_for_radius(12.30, 76.65, 150)
    assert min_lat < 12.30 < max_lat and min_lng < 76.65 < max_lng
    # A point 100m north must be inside the box; 300m north must not.
    assert min_lat <= 12.30 + 100 / 111_320 <= max_lat
    assert not (12.30 + 300 / 111_320 <= max_lat)


def test_point_in_polygon():
    square = [[12.30, 76.65], [12.31, 76.65], [12.31, 76.66], [12.30, 76.66]]
    assert point_in_polygon(12.305, 76.655, square)
    assert not point_in_polygon(12.32, 76.655, square)


def test_public_jitter_is_deterministic_and_offset():
    a = jitter_for_public(12.30, 76.65, seed=42)
    b = jitter_for_public(12.30, 76.65, seed=42)
    assert a == b, "markers must not jump between page loads"
    assert a != (12.30, 76.65), "exact coordinates must never be published"
    assert haversine_m(12.30, 76.65, *a) < 200


# -------------------------------------------------------------------- risk
def _risk(**over):
    base = dict(
        created_at=NOW - timedelta(hours=10), last_action_at=NOW - timedelta(hours=10),
        status="ROUTED", sla_target_hours=72, category_avg_resolution_hours=48,
        jurisdiction_avg_resolution_hours=None, has_field_worker=True,
        status_change_count=1, duplicate_count=0, followup_count=0, reopen_count=0,
        base_severity=3, safety_impact=1, has_evidence=True, now=NOW)
    base.update(over)
    return compute_risk(**base)


def test_risk_is_zero_for_closed_complaints():
    for st in ("RESOLVED", "REJECTED"):
        r = _risk(status=st)
        assert r.score == 0 and r.level == "LOW"


def test_risk_rises_with_inactivity():
    fresh = _risk(last_action_at=NOW - timedelta(hours=2))
    stale = _risk(created_at=NOW - timedelta(hours=200),
                  last_action_at=NOW - timedelta(hours=200))
    assert stale.score > fresh.score


def test_unassigned_complaint_scores_higher_than_assigned():
    assigned = _risk(has_field_worker=True)
    unassigned = _risk(has_field_worker=False)
    assert unassigned.score > assigned.score


def test_risk_is_bounded_and_explained():
    r = _risk(created_at=NOW - timedelta(days=40), last_action_at=NOW - timedelta(days=40),
              has_field_worker=False, duplicate_count=9, followup_count=9,
              reopen_count=3, base_severity=5, safety_impact=3, has_evidence=False)
    assert 0 <= r.score <= 100
    assert r.level == "HIGH"
    assert r.factors, "a score with no explanation is exactly what we promised not to ship"
    assert r.recommended_action


def test_risk_factor_points_never_exceed_their_cap():
    r = _risk(created_at=NOW - timedelta(days=60), last_action_at=NOW - timedelta(days=60))
    for f in r.factors:
        if f.max_points:
            assert f.points <= f.max_points + 1e-6


# ---------------------------------------------------------------- priority
def _prio(**over):
    base = dict(base_severity=3, safety_impact=1, nearby_sensitive=[],
                duplicate_cluster_size=1, followup_count=0,
                created_at=NOW - timedelta(hours=10), sla_target_hours=72, now=NOW)
    base.update(over)
    return compute_priority(**base)


def test_report_volume_cannot_dominate_priority():
    """The headline design claim: brigading must not beat a genuine hazard."""
    brigaded_cosmetic = _prio(base_severity=2, safety_impact=0,
                              duplicate_cluster_size=50, followup_count=50)
    hazard_near_school = _prio(
        base_severity=5, safety_impact=3, duplicate_cluster_size=1,
        nearby_sensitive=[{"type": "SCHOOL", "name": "X", "distance_m": 60}])
    assert hazard_near_school.score > brigaded_cosmetic.score


def test_sensitive_location_raises_priority():
    plain = _prio(base_severity=4, safety_impact=2)
    near_hospital = _prio(base_severity=4, safety_impact=2,
                          nearby_sensitive=[{"type": "HOSPITAL", "name": "H",
                                             "distance_m": 40}])
    assert near_hospital.score > plain.score


def test_distant_sensitive_place_is_ignored():
    far = _prio(nearby_sensitive=[{"type": "SCHOOL", "name": "X", "distance_m": 900}])
    none = _prio(nearby_sensitive=[])
    assert far.score == pytest.approx(none.score)


def test_priority_levels_are_ordered():
    low = _prio(base_severity=1, safety_impact=0, created_at=NOW)
    high = _prio(base_severity=5, safety_impact=3, duplicate_cluster_size=6,
                 created_at=NOW - timedelta(hours=100),
                 nearby_sensitive=[{"type": "HOSPITAL", "name": "H", "distance_m": 30}],
                 is_recurring_location=True)
    assert low.score < high.score
    assert high.level in {"HIGH", "CRITICAL"}


# --------------------------------------------------------------- duplicates
def test_text_similarity_recognises_paraphrase():
    a = "Large pothole near Kuvempunagar signal"
    b = "Deep pothole at Kuvempunagar traffic signal"
    c = "Streetlight not working in Gokulam"
    assert dup.text_similarity(a, b) > dup.text_similarity(a, c)
    assert dup.text_similarity(a, b) > 0.35


def test_text_similarity_handles_kannada():
    a = "ಕುವೆಂಪುನಗರದಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ ಇದೆ"
    b = "ಕುವೆಂಪುನಗರದಲ್ಲಿ ಗುಂಡಿ ಇದೆ"
    assert dup.text_similarity(a, b) > 0.4


def test_similarity_decays_with_distance():
    near = dup.score_candidate(
        new_lat=12.30, new_lng=76.65, new_text="pothole near signal",
        new_created_hours_ago=0, cand_lat=12.3001, cand_lng=76.6501,
        cand_text="deep pothole at signal", cand_created_hours_ago=-2,
        radius_m=150, window_hours=336)[0]
    far = dup.score_candidate(
        new_lat=12.30, new_lng=76.65, new_text="pothole near signal",
        new_created_hours_ago=0, cand_lat=12.3010, cand_lng=76.6510,
        cand_text="deep pothole at signal", cand_created_hours_ago=-2,
        radius_m=150, window_hours=336)[0]
    assert near > far


# ------------------------------------------------------------ verification
def test_out_of_area_coordinates_are_suspicious():
    r = verify_report(latitude=28.61, longitude=77.20,  # New Delhi
                      description="Garbage not collected for several days here",
                      title="Garbage", has_evidence=False,
                      inside_known_jurisdiction=False)
    assert r.status in {"SUSPICIOUS", "NEEDS_REVIEW"}
    assert any(f["code"] == "coords" and f["verdict"] == "FAIL" for f in r.factors)


def test_reused_image_hash_lowers_trust_but_never_rejects():
    clean = verify_report(latitude=12.30, longitude=76.65,
                          description="Garbage bin overflowing for three days now",
                          title="Garbage", has_evidence=True)
    reused = verify_report(latitude=12.30, longitude=76.65,
                           description="Garbage bin overflowing for three days now",
                           title="Garbage", has_evidence=True,
                           evidence_hash_reuse_count=3)
    assert reused.confidence < clean.confidence
    assert reused.status in {"NEEDS_REVIEW", "SUSPICIOUS", "PLAUSIBLE"}


def test_corroboration_raises_trust():
    alone = verify_report(latitude=12.30, longitude=76.65,
                          description="Streetlight out for a week on this lane",
                          title="Streetlight", has_evidence=True)
    corroborated = verify_report(latitude=12.30, longitude=76.65,
                                 description="Streetlight out for a week on this lane",
                                 title="Streetlight", has_evidence=True,
                                 duplicate_count=4)
    assert corroborated.confidence > alone.confidence


# ---------------------------------------------------------------------- SLA
def test_sla_breach_when_past_due():
    s = sla_state(created_at=NOW - timedelta(hours=100), target_hours=72, now=NOW)
    assert s["breached"] and s["breach_probability"] == 100


def test_sla_remaining_and_probability():
    s = sla_state(created_at=NOW - timedelta(hours=51, minutes=20),
                  target_hours=72, risk_score=80, now=NOW)
    assert 20 < s["remaining_hours"] < 21
    assert s["breach_risk"] in {"MODERATE", "HIGH"}


def test_resolved_within_target_is_met():
    s = sla_state(created_at=NOW - timedelta(hours=30), target_hours=72,
                  resolved_at=NOW - timedelta(hours=10), now=NOW)
    assert s["breach_risk"] == "MET" and not s["breached"]


# ------------------------------------------------------ jurisdiction versions
class _V:
    def __init__(self, vid, jid, label, ring, start, end):
        self.id, self.jurisdiction_id, self.version_label = vid, jid, label
        self.boundary_json = ring
        self.effective_from, self.effective_to = start, end
        self.min_lat = min(p[0] for p in ring)
        self.max_lat = max(p[0] for p in ring)
        self.min_lng = min(p[1] for p in ring)
        self.max_lng = max(p[1] for p in ring)


class _J:
    def __init__(self, jid, authority, ward):
        self.id, self.authority, self.ward_number = jid, authority, ward
        self.authority_type = "MUNICIPAL"
        self.name = f"{authority} {ward}"


BIG = [[12.300, 76.640], [12.320, 76.640], [12.320, 76.670], [12.300, 76.670]]
SMALL = [[12.300, 76.640], [12.308, 76.640], [12.308, 76.650], [12.300, 76.650]]
PANCH = [[12.306, 76.648], [12.322, 76.648], [12.322, 76.672], [12.306, 76.672]]


def test_active_versions_respects_effective_window():
    v_old = _V(1, 1, "2026-01", BIG, datetime(2026, 1, 1, tzinfo=timezone.utc),
               datetime(2026, 10, 1, tzinfo=timezone.utc))
    v_new = _V(2, 1, "2026-10", SMALL, datetime(2026, 10, 1, tzinfo=timezone.utc), None)
    assert [v.id for v in active_versions([v_old, v_new], NOW)] == [1]
    later = datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert [v.id for v in active_versions([v_old, v_new], later)] == [2]


def test_boundary_change_reroutes_new_complaints_only():
    """The core versioning claim, tested end to end at engine level."""
    v_old = _V(1, 1, "2026-01", BIG, datetime(2026, 1, 1, tzinfo=timezone.utc),
               datetime(2026, 10, 1, tzinfo=timezone.utc))
    v_new = _V(2, 1, "2026-10", SMALL, datetime(2026, 10, 1, tzinfo=timezone.utc), None)
    v_panch = _V(3, 2, "2026-10", PANCH, datetime(2026, 10, 1, tzinfo=timezone.utc), None)
    index = {1: _J(1, "Mysuru City Corporation", 42), 2: _J(2, "Bogadi Gram Panchayat", None)}
    versions = [v_old, v_new, v_panch]
    point = (12.315, 76.660)

    before = resolve(latitude=point[0], longitude=point[1], versions=versions,
                     jurisdiction_index=index, at=NOW)
    after = resolve(latitude=point[0], longitude=point[1], versions=versions,
                    jurisdiction_index=index,
                    at=datetime(2026, 11, 1, tzinfo=timezone.utc))

    assert before.authority == "Mysuru City Corporation"
    assert before.version_label == "2026-01"
    assert after.authority == "Bogadi Gram Panchayat"
    assert after.version_label == "2026-10"
    assert before.jurisdiction_version_id != after.jurisdiction_version_id


def test_unroutable_point_is_flagged_not_guessed():
    v = _V(1, 1, "2026-01", SMALL, datetime(2026, 1, 1, tzinfo=timezone.utc), None)
    r = resolve(latitude=28.61, longitude=77.20, versions=[v],
                jurisdiction_index={1: _J(1, "MCC", 1)}, at=NOW)
    assert r.method == "UNRESOLVED" and r.confidence == 0.0


def test_containment_beats_nearest_and_reports_confidence():
    v = _V(1, 1, "2026-01", BIG, datetime(2026, 1, 1, tzinfo=timezone.utc), None)
    inside = resolve(latitude=12.310, longitude=76.655, versions=[v],
                     jurisdiction_index={1: _J(1, "MCC", 42)}, at=NOW)
    assert inside.method == "CONTAINMENT" and inside.confidence >= 0.75
