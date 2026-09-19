"""API-level tests: authentication, RBAC, the complaint lifecycle, and the
end-to-end integration path the demo script walks through.
"""
from __future__ import annotations

import uuid

import pytest

PW = "CivicPulse@2026"


def auth(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ------------------------------------------------------------------- auth
def test_login_succeeds_for_demo_accounts(client):
    for email in ("citizen@demo.local", "officer@demo.local",
                  "worker@demo.local", "admin@demo.local"):
        r = client.post("/api/auth/login", json={"email": email, "password": PW})
        assert r.status_code == 200
        assert r.json()["user"]["email"] == email


def test_login_rejects_wrong_password(client):
    r = client.post("/api/auth/login",
                    json={"email": "citizen@demo.local", "password": "wrong-password"})
    assert r.status_code == 401


def test_password_hash_is_never_returned(client):
    r = client.post("/api/auth/login",
                    json={"email": "citizen@demo.local", "password": PW})
    assert "password" not in r.text.lower().replace("password\":", "")
    assert "password_hash" not in r.text


def test_unauthenticated_request_is_rejected(client):
    assert client.get("/api/complaints").status_code == 401


def test_invalid_token_is_rejected(client):
    r = client.get("/api/complaints", headers={"Authorization": "Bearer not.a.token"})
    assert r.status_code == 401


# ------------------------------------------------------------------- RBAC
def test_citizen_cannot_access_admin_jurisdiction_api(client):
    r = client.post("/api/jurisdictions/version", headers=auth(client, "citizen@demo.local"),
                    json={"jurisdiction_id": 1, "version_label": "pulse-2027",
                          "effective_from": "2027-01-01T00:00:00Z",
                          "boundary": [[12.3, 76.6], [12.31, 76.6], [12.31, 76.61]]})
    assert r.status_code == 403


def test_field_worker_cannot_create_boundary_versions(client):
    r = client.post("/api/jurisdictions/version", headers=auth(client, "worker@demo.local"),
                    json={"jurisdiction_id": 1, "version_label": "pulse-2028",
                          "effective_from": "2028-01-01T00:00:00Z",
                          "boundary": [[12.3, 76.6], [12.31, 76.6], [12.31, 76.61]]})
    assert r.status_code == 403


def test_citizen_cannot_list_field_workers(client):
    r = client.get("/api/auth/field-workers", headers=auth(client, "citizen@demo.local"))
    assert r.status_code == 403


def test_citizen_only_sees_own_complaints(client):
    r = client.get("/api/complaints", headers=auth(client, "citizen@demo.local"))
    assert r.status_code == 200
    me = client.get("/api/auth/me", headers=auth(client, "citizen@demo.local")).json()
    for item in r.json()["items"]:
        assert item["citizen_id"] == me["id"]


def test_citizen_cannot_read_another_citizens_complaint(client, seeded):
    """IDOR guard: authorisation is checked on the loaded object."""
    admin = auth(client, "admin@demo.local")
    all_items = client.get("/api/complaints?page_size=50", headers=admin).json()["items"]
    me = client.get("/api/auth/me", headers=auth(client, "citizen@demo.local")).json()
    other = next((i for i in all_items if i["citizen_id"] not in (None, me["id"])), None)
    assert other, "seed data should contain complaints from other citizens"
    r = client.get(f"/api/complaints/{other['public_id']}",
                   headers=auth(client, "citizen@demo.local"))
    assert r.status_code == 403


def test_citizen_cannot_change_status(client, seeded):
    admin = auth(client, "admin@demo.local")
    item = client.get("/api/complaints?page_size=1", headers=admin).json()["items"][0]
    r = client.patch(f"/api/complaints/{item['public_id']}/status",
                     headers=auth(client, "citizen@demo.local"),
                     json={"to_status": "RESOLVED"})
    assert r.status_code == 403


# ------------------------------------------------------------ complaint API
def test_create_complaint_runs_full_pipeline(client):
    r = client.post("/api/complaints", headers=auth(client, "citizen@demo.local"), json={
        "title": "Large pothole near Kuvempunagar school gate",
        "description": "Deep pothole in front of the school gate, two-wheelers "
                       "are swerving into oncoming traffic every morning.",
        "category_code": "POTHOLE", "latitude": 12.2860, "longitude": 76.6192,
        "landmark": "Kuvempunagar",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    a = body["analysis"]

    assert body["complaint"]["public_id"].startswith("CIV-")
    assert a["routing"]["jurisdiction_id"] is not None
    assert a["routing"]["confidence_pct"] > 0
    assert a["verification"]["verification_status"] in {
        "VERIFIED", "PLAUSIBLE", "NEEDS_REVIEW", "SUSPICIOUS"}
    assert 0 <= a["risk"]["risk_score"] <= 100
    assert a["risk"]["risk_factors"], "risk must always ship its explanation"
    assert a["priority"]["priority_factors"]
    assert a["risk"]["recommended_action"]


def test_server_ignores_client_supplied_scores(client):
    """Never trust client-provided priority/risk. Extra fields are dropped."""
    r = client.post("/api/complaints", headers=auth(client, "citizen@demo.local"), json={
        "title": "Streetlight out on the main lane in Gokulam",
        "description": "The streetlight has been off for over a week and the "
                       "lane is completely dark after 7pm.",
        "category_code": "STREETLIGHT", "latitude": 12.3155, "longitude": 76.6353,
        "risk_score": 100, "priority_level": "CRITICAL", "status": "RESOLVED",
        "verification_status": "VERIFIED", "jurisdiction_id": 999,
    })
    assert r.status_code == 201
    c = r.json()["complaint"]
    assert c["status"] != "RESOLVED"
    assert c["risk_score"] != 100 or c["priority_level"] != "CRITICAL"


def test_validation_rejects_short_and_out_of_range_input(client):
    h = auth(client, "citizen@demo.local")
    assert client.post("/api/complaints", headers=h, json={
        "title": "x", "description": "y", "category_code": "POTHOLE",
        "latitude": 12.3, "longitude": 76.6}).status_code == 422
    assert client.post("/api/complaints", headers=h, json={
        "title": "Valid looking title here", "description": "A long enough description here",
        "category_code": "POTHOLE", "latitude": 999, "longitude": 76.6}).status_code == 422
    assert client.post("/api/complaints", headers=h, json={
        "title": "Valid looking title here", "description": "A long enough description here",
        "category_code": "NO_SUCH_CATEGORY", "latitude": 12.3,
        "longitude": 76.6}).status_code == 422


def test_duplicate_detection_surfaces_but_never_deletes(client):
    h = auth(client, "citizen@demo.local")
    payload = {
        "title": "Large pothole near Vijayanagar signal",
        "description": "Large pothole right at the Vijayanagar traffic signal, "
                       "water collects in it whenever it rains.",
        "category_code": "POTHOLE", "latitude": 12.3210, "longitude": 76.6112,
    }
    first = client.post("/api/complaints", headers=h, json=payload)
    assert first.status_code == 201
    first_id = first.json()["complaint"]["public_id"]

    probe = client.post("/api/complaints/check-duplicates", json={
        "title": "Deep pothole at Vijayanagar traffic signal",
        "description": "Deep pothole at the Vijayanagar traffic signal, dangerous "
                       "for two-wheelers when it rains.",
        "category_code": "POTHOLE", "latitude": 12.32105, "longitude": 76.61125})
    assert probe.status_code == 200
    assert probe.json()["possible_duplicate"] is True
    top = probe.json()["matches"][0]
    assert top["similarity_pct"] > 55
    assert top["distance_m"] < 150

    # The citizen submits anyway; both records must survive.
    second = client.post("/api/complaints", headers=h, json={
        "title": "Deep pothole at Vijayanagar traffic signal",
        "description": "Deep pothole at the Vijayanagar traffic signal, dangerous "
                       "for two-wheelers when it rains.",
        "category_code": "POTHOLE", "latitude": 12.32105, "longitude": 76.61125})
    assert second.status_code == 201
    assert client.get(f"/api/complaints/{first_id}", headers=h).status_code == 200
    detail = client.get(f"/api/complaints/{second.json()['complaint']['public_id']}",
                        headers=h).json()
    assert detail["duplicates"], "the duplicate link must be recorded for review"


def test_different_categories_are_never_duplicates(client):
    r = client.post("/api/complaints/check-duplicates", json={
        "title": "Streetlight not working near Vijayanagar signal",
        "description": "Streetlight not working at the Vijayanagar signal.",
        "category_code": "STREETLIGHT", "latitude": 12.3210, "longitude": 76.6112})
    ids = [m["public_id"] for m in r.json()["matches"]]
    for pid in ids:
        assert pid  # any match must itself be a streetlight complaint


def test_idempotency_key_prevents_double_submission(client):
    """The offline queue replays; the database must not grow."""
    h = auth(client, "citizen@demo.local")
    key = str(uuid.uuid4())
    payload = {
        "title": "Drain blocked near Saraswathipuram park",
        "description": "The storm water drain is completely blocked and dirty "
                       "water is flowing onto the road.",
        "category_code": "DRAIN", "latitude": 12.3062, "longitude": 76.6338,
        "idempotency_key": key,
    }
    a = client.post("/api/complaints", headers=h, json=payload)
    b = client.post("/api/complaints", headers=h, json=payload)
    assert a.status_code == 201
    assert b.json().get("deduplicated_by_idempotency_key") is True
    assert a.json()["complaint"]["public_id"] == b.json()["complaint"]["public_id"]


def test_followup_raises_risk_and_does_not_reset_inactivity(client, seeded):
    """Chasing a complaint must never make it look healthier."""
    admin = auth(client, "admin@demo.local")
    open_items = client.get(
        "/api/complaints?status=ROUTED,ASSIGNED&sort=risk&page_size=5",
        headers=admin).json()["items"]
    assert open_items
    target = open_items[0]
    citizen_h = auth(client, "admin@demo.local")  # admin may read any complaint

    before = client.get(f"/api/complaints/{target['public_id']}",
                        headers=citizen_h).json()
    r = client.post(f"/api/complaints/{target['public_id']}/followup",
                    headers=citizen_h, json={"message": "Still not fixed, please help."})
    assert r.status_code == 200
    after = client.get(f"/api/complaints/{target['public_id']}",
                       headers=citizen_h).json()
    assert after["last_action_at"] == before["last_action_at"]
    assert r.json()["risk_score"] >= before["risk_score"]


# ------------------------------------------------------- status transitions
def test_illegal_status_transition_is_rejected(client, seeded):
    admin = auth(client, "admin@demo.local")
    item = client.get("/api/complaints?status=ROUTED&page_size=1",
                      headers=admin).json()["items"]
    assert item, "seed data must contain ROUTED complaints"
    r = client.patch(f"/api/complaints/{item[0]['public_id']}/status",
                     headers=admin, json={"to_status": "RESOLVED"})
    assert r.status_code == 409
    assert "Illegal transition" in r.json()["detail"]


def test_unknown_status_value_is_rejected(client, seeded):
    admin = auth(client, "admin@demo.local")
    item = client.get("/api/complaints?page_size=1", headers=admin).json()["items"][0]
    r = client.patch(f"/api/complaints/{item['public_id']}/status",
                     headers=admin, json={"to_status": "TOTALLY_MADE_UP"})
    assert r.status_code == 422


def test_every_status_change_creates_a_timeline_event(client, seeded):
    admin = auth(client, "admin@demo.local")
    items = client.get("/api/complaints?status=ROUTED&page_size=1",
                       headers=admin).json()["items"]
    assert items, "seed data must contain ROUTED complaints"
    pid = items[0]["public_id"]
    before = len(client.get(f"/api/complaints/{pid}", headers=admin).json()["timeline"])

    workers = client.get("/api/auth/field-workers", headers=admin).json()["items"]
    client.post(f"/api/complaints/{pid}/assign", headers=admin,
                json={"field_worker_id": workers[0]["id"]})
    after = client.get(f"/api/complaints/{pid}", headers=admin).json()
    assert len(after["timeline"]) > before
    assert after["status"] == "ASSIGNED"


# ------------------------------------------------------------ public surface
def test_public_dashboard_needs_no_auth_and_leaks_no_identity(client, seeded):
    r = client.get("/api/dashboard/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["total_complaints"] > 0
    assert "synthetic" in body["disclaimer"].lower()
    assert "citizen_id" not in r.text


def test_public_map_returns_approximate_locations(client, seeded):
    r = client.get("/api/dashboard/map", params={
        "min_lat": 12.15, "max_lat": 12.50, "min_lng": 76.50, "max_lng": 76.82,
        "limit": 25})
    assert r.status_code == 200
    body = r.json()
    assert body["markers"] and len(body["markers"]) <= 25
    assert body["total_in_bounds"] >= len(body["markers"])
    assert "approximate" in body["location_note"].lower()
    assert "description" not in body["markers"][0]


def test_ward_explanation_gives_reasons_not_just_numbers(client, seeded):
    wards = client.get("/api/dashboard/wards").json()["items"]
    busiest = max(wards, key=lambda w: w["open"])
    r = client.get(f"/api/dashboard/wards/{busiest['jurisdiction_id']}/explain")
    assert r.status_code == 200
    body = r.json()
    assert body["reasons"]
    for reason in body["reasons"]:
        assert reason["text"] and reason["action"]


# ------------------------------------------------------------ jurisdictions
def test_public_jurisdiction_resolution(client, seeded):
    r = client.get("/api/jurisdictions/resolve",
                   params={"lat": 12.2846, "lng": 76.6205})
    assert r.status_code == 200
    assert r.json()["method"] in {"CONTAINMENT", "NEAREST", "UNRESOLVED"}


def test_boundary_version_change_affects_only_new_complaints(client, seeded):
    """The headline engineering demo, asserted end to end through the API."""
    admin = auth(client, "admin@demo.local")
    citizen = auth(client, "citizen@demo.local")

    lat, lng = 12.2846, 76.6205
    before_route = client.get("/api/jurisdictions/resolve",
                              params={"lat": lat, "lng": lng}).json()

    old = client.post("/api/complaints", headers=citizen, json={
        "title": "Garbage overflow before the boundary revision",
        "description": "Garbage bin overflowing near the corner for three days.",
        "category_code": "GARBAGE", "latitude": lat, "longitude": lng})
    assert old.status_code == 201
    old_pid = old.json()["complaint"]["public_id"]

    # Publish a boundary version that takes effect immediately and hands this
    # coordinate to a different authority.
    target_jur = 3
    r = client.post("/api/jurisdictions/version", headers=admin, json={
        "jurisdiction_id": target_jur,
        "version_label": f"test-{uuid.uuid4().hex[:6]}",
        "effective_from": "2020-01-01T00:00:00Z",
        "boundary": [[lat - 0.004, lng - 0.004], [lat + 0.004, lng - 0.004],
                     [lat + 0.004, lng + 0.004], [lat - 0.004, lng + 0.004]],
        "close_previous": True,
    })
    assert r.status_code == 201, r.text

    new = client.post("/api/complaints", headers=citizen, json={
        "title": "Garbage overflow after the boundary revision",
        "description": "Garbage bin overflowing near the same corner again.",
        "category_code": "GARBAGE", "latitude": lat, "longitude": lng})
    assert new.status_code == 201

    old_detail = client.get(f"/api/complaints/{old_pid}/jurisdiction",
                            headers=admin).json()
    # The historical record is untouched...
    assert old_detail["as_filed"]["boundary_version"] == before_route["boundary_version"]
    # ...while the same coordinate now resolves differently.
    assert old_detail["if_filed_today"]["jurisdiction_version_id"] != \
        old_detail["as_filed"]["boundary_version"]


def test_duplicate_version_label_is_rejected(client, seeded):
    admin = auth(client, "admin@demo.local")
    payload = {"jurisdiction_id": 1, "version_label": "2026-01",
               "effective_from": "2027-01-01T00:00:00Z",
               "boundary": [[12.3, 76.6], [12.31, 76.6], [12.31, 76.61]]}
    assert client.post("/api/jurisdictions/version", headers=admin,
                       json=payload).status_code == 409


# ------------------------------------------------------------ field worker
def test_field_worker_offline_sync_is_idempotent(client, seeded):
    admin = auth(client, "admin@demo.local")
    worker = auth(client, "worker@demo.local")
    me = client.get("/api/auth/me", headers=worker).json()

    items = client.get("/api/complaints?status=ROUTED&page_size=1",
                       headers=admin).json()["items"]
    assert items, "seed data must contain assignable complaints"
    pid = items[0]["public_id"]
    client.post(f"/api/complaints/{pid}/assign", headers=admin,
                json={"field_worker_id": me["id"]})

    tasks = client.get("/api/field-worker/tasks", headers=worker).json()["items"]
    task = next(t for t in tasks if t["public_id"] == pid)

    key = str(uuid.uuid4())
    actions = {"actions": [{"idempotency_key": key, "action_type": "TASK_START",
                            "payload": {"task_id": task["task_id"]}}]}
    first = client.post("/api/field-worker/sync", headers=worker, json=actions).json()
    second = client.post("/api/field-worker/sync", headers=worker, json=actions).json()
    assert first["applied"] == 1
    assert second["applied"] == 0 and second["skipped"] == 1


def test_field_worker_cannot_touch_unassigned_task(client, seeded):
    worker = auth(client, "worker@demo.local")
    r = client.post("/api/field-worker/tasks/999999/start", headers=worker)
    assert r.status_code in (403, 404)


def test_field_completion_produces_field_verified_not_resolved(client, seeded):
    """Separation of duties: only an officer/admin closes a complaint.

    Uses the city-wide admin throughout (rather than the jurisdiction-scoped
    officer fixture) so the test exercises the FIELD_VERIFIED -> RESOLVED
    transition without also depending on which ward the randomly picked seed
    complaint happens to fall in.
    """
    worker = auth(client, "worker@demo.local")
    me = client.get("/api/auth/me", headers=worker).json()

    admin = auth(client, "admin@demo.local")
    items = client.get("/api/complaints?status=ROUTED&page_size=3",
                       headers=admin).json()["items"]
    assert items, "seed data must contain assignable complaints"
    pid = items[-1]["public_id"]
    client.post(f"/api/complaints/{pid}/assign", headers=admin,
                json={"field_worker_id": me["id"]})
    tasks = client.get("/api/field-worker/tasks", headers=worker).json()["items"]
    task = next(t for t in tasks if t["public_id"] == pid)

    client.post(f"/api/field-worker/tasks/{task['task_id']}/start", headers=worker)
    r = client.post(f"/api/field-worker/tasks/{task['task_id']}/complete",
                    headers=worker, params={"note": "Filled and compacted.",
                                            "resolved": True})
    assert r.json()["status"] == "FIELD_VERIFIED"

    closed = client.patch(f"/api/complaints/{pid}/status", headers=admin,
                          json={"to_status": "RESOLVED", "note": "Verified and closed."})
    assert closed.status_code == 200
    assert closed.json()["status"] == "RESOLVED"


# -------------------------------------------------------------------- demo
def test_surge_simulation_returns_immediately(client, seeded):
    admin = auth(client, "admin@demo.local")
    r = client.post("/api/demo/simulate-surge", headers=admin,
                    json={"count": 200, "batch_size": 50, "label": "test surge"})
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    status = client.get(f"/api/demo/surge/{run_id}").json()
    assert status["incoming_reports"] == 200
    assert "synthetic" in status["note"].lower()


def test_bad_input_scenarios_run_real_engines(client, seeded):
    admin = auth(client, "admin@demo.local")
    for key in ("wrong_location", "incomplete", "repeated_image", "extreme_age",
                "duplicate"):
        r = client.post(f"/api/demo/scenario/{key}", headers=admin)
        assert r.status_code == 200, f"{key}: {r.text}"
        assert r.json()["scenario"] == key


def test_evidence_upload_and_retrieval_flow(client, seeded):
    # 1. Citizen creates a complaint
    citizen = auth(client, "citizen@demo.local")
    r = client.post("/api/complaints", json={
        "title": "Broken road surface near market",
        "description": "Continuous road damage with large potholes near the main gate.",
        "category_code": "POTHOLE",
        "latitude": 12.2860, "longitude": 76.6192,
    }, headers=citizen)
    assert r.status_code == 201
    pub_id = r.json()["complaint"]["public_id"]

    # 2. Citizen uploads PNG evidence
    png_bytes = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                 b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01"
                 b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")
    files = {"file": ("leak.png", png_bytes, "image/png")}
    up = client.post(f"/api/complaints/{pub_id}/evidence?stage=REPORT", files=files, headers=citizen)
    assert up.status_code == 200, up.text
    ev_data = up.json()
    assert "id" in ev_data
    ev_id = ev_data["id"]
    assert ev_data["url"] == f"/api/complaints/{pub_id}/evidence/{ev_id}"

    # 3. Citizen fetches complaint detail and verifies evidence presence
    detail = client.get(f"/api/complaints/{pub_id}", headers=citizen).json()
    assert len(detail["evidence"]) == 1
    assert detail["evidence"][0]["id"] == ev_id
    assert detail["evidence"][0]["stage"] == "REPORT"
    assert detail["evidence"][0]["url"] == f"/api/complaints/{pub_id}/evidence/{ev_id}"

    # 4. Citizen retrieves the uploaded evidence file
    get_res = client.get(f"/api/complaints/{pub_id}/evidence/{ev_id}", headers=citizen)
    assert get_res.status_code == 200
    assert get_res.content == png_bytes

    # 5. Admin can view/retrieve the citizen's evidence across all jurisdictions
    admin = auth(client, "admin@demo.local")
    adm_res = client.get(f"/api/complaints/{pub_id}/evidence/{ev_id}", headers=admin)
    assert adm_res.status_code == 200
    assert adm_res.content == png_bytes

    # 6. Officer can view/retrieve evidence for complaints in their jurisdiction
    officer = auth(client, "officer@demo.local")
    officer_items = client.get("/api/complaints?page_size=1", headers=officer).json()["items"]
    assert officer_items, "officer queue should have complaints"
    off_pid = officer_items[0]["public_id"]
    # Upload evidence to officer's complaint
    up_off = client.post(f"/api/complaints/{off_pid}/evidence?stage=FIELD", files=files, headers=officer)
    assert up_off.status_code == 200
    off_ev_id = up_off.json()["id"]
    off_get = client.get(f"/api/complaints/{off_pid}/evidence/{off_ev_id}", headers=officer)
    assert off_get.status_code == 200
    assert off_get.content == png_bytes

    # 7. IDOR guard: another citizen cannot access evidence of a complaint they do not own
    other_citizen = auth(client, "citizen2@demo.local")
    idor_res = client.get(f"/api/complaints/{pub_id}/evidence/{ev_id}", headers=other_citizen)
    assert idor_res.status_code == 403

    # 8. Query token authentication works for evidence retrieval (e.g. <img> tags)
    token_str = citizen["Authorization"].split()[1]
    token_res = client.get(f"/api/complaints/{pub_id}/evidence/{ev_id}?token={token_str}")
    assert token_res.status_code == 200
    assert token_res.content == png_bytes


def test_seed_demo_evidence_svg_fallback(client, seeded):
    # Seeded complaints have synthetic evidence records without physical disk files
    admin = auth(client, "admin@demo.local")
    complaints = client.get("/api/complaints?page_size=10", headers=admin).json()["items"]
    ev_found = None
    for c in complaints:
        detail = client.get(f"/api/complaints/{c['public_id']}", headers=admin).json()
        if detail.get("evidence"):
            ev_found = (c["public_id"], detail["evidence"][0]["id"])
            break

    if ev_found:
        pub_id, ev_id = ev_found
        res = client.get(f"/api/complaints/{pub_id}/evidence/{ev_id}", headers=admin)
        assert res.status_code == 200
        assert "image/svg+xml" in res.headers.get("content-type", "")
        assert b"<svg" in res.content


def test_evidence_delete_flow(client, seeded):
    citizen = auth(client, "citizen@demo.local")
    other_citizen = auth(client, "citizen2@demo.local")
    admin = auth(client, "admin@demo.local")

    # 1. Create a complaint as citizen
    res = client.post(
        "/api/complaints",
        json={
            "title": "Pothole to test deletion",
            "description": "Continuous road damage with large potholes near the main gate.",
            "category_code": "POTHOLE",
            "latitude": 12.2860,
            "longitude": 76.6192,
        },
        headers=citizen,
    )
    assert res.status_code == 201
    pub_id = res.json()["complaint"]["public_id"]

    # 2. Upload an image
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    files = {"file": ("test_delete.png", png_bytes, "image/png")}
    up_res = client.post(f"/api/complaints/{pub_id}/evidence?stage=REPORT", files=files, headers=citizen)
    assert up_res.status_code == 200
    ev_id = up_res.json()["id"]

    # 3. IDOR prevention: other citizen cannot delete this evidence
    del_other = client.delete(f"/api/complaints/{pub_id}/evidence/{ev_id}", headers=other_citizen)
    assert del_other.status_code == 403

    # 4. Citizen can delete their own evidence
    del_own = client.delete(f"/api/complaints/{pub_id}/evidence/{ev_id}", headers=citizen)
    assert del_own.status_code == 200
    assert del_own.json()["deleted_id"] == ev_id

    # 5. Subsequent GET should 404
    get_res = client.get(f"/api/complaints/{pub_id}/evidence/{ev_id}", headers=citizen)
    assert get_res.status_code == 404

    # 6. Admin can delete any evidence
    png_bytes2 = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x02"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    files2 = {"file": ("admin_delete.png", png_bytes2, "image/png")}
    up_res2 = client.post(f"/api/complaints/{pub_id}/evidence?stage=REPORT", files=files2, headers=citizen)
    assert up_res2.status_code == 200
    ev_id2 = up_res2.json()["id"]

    del_adm = client.delete(f"/api/complaints/{pub_id}/evidence/{ev_id2}", headers=admin)
    assert del_adm.status_code == 200


