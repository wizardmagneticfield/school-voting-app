"""Integration tests against a real PostgreSQL database.

  createdb voting_test
  DATABASE_URL=postgresql://localhost/voting_test pytest -v
"""
import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://voting:voting@localhost:5432/voting_test")
import app as app_module  # noqa: E402
import db  # noqa: E402


@pytest.fixture()
def client():
    with db.get_cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS votes, candidates, elections, users CASCADE")
    db.init_schema()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client


def register(c, sid, admin=False):
    c.post("/api/register", json={"student_id": sid, "name": sid, "password": "password123"})
    if admin:
        with db.get_cursor() as cur:
            cur.execute("UPDATE users SET role='admin' WHERE student_id=%s", (sid,))
        c.post("/api/login", json={"student_id": sid, "password": "password123"})


def open_election(admin):
    eid = admin.post("/api/admin/elections", json={"title": "President", "candidates": ["Ana", "Ben"]}).json["id"]
    admin.patch(f"/api/admin/elections/{eid}/status", json={"status": "open"})
    cands = admin.get(f"/api/elections/{eid}").json["candidates"]
    return eid, cands


def test_one_vote_per_user(client):
    admin, student = client(), client()
    register(admin, "admin1", admin=True)
    register(student, "s1")
    eid, cands = open_election(admin)
    assert student.post(f"/api/elections/{eid}/vote", json={"candidate_id": cands[0]["id"]}).status_code == 201
    r = student.post(f"/api/elections/{eid}/vote", json={"candidate_id": cands[1]["id"]})
    assert r.status_code == 409


def test_candidate_must_belong_to_election(client):
    admin, student = client(), client()
    register(admin, "admin1", admin=True)
    register(student, "s1")
    e1, _ = open_election(admin)
    _, other = open_election(admin)
    r = student.post(f"/api/elections/{e1}/vote", json={"candidate_id": other[0]["id"]})
    assert r.status_code == 400


def test_students_cannot_use_admin_routes_or_see_live_results(client):
    admin, student = client(), client()
    register(admin, "admin1", admin=True)
    register(student, "s1")
    eid, _ = open_election(admin)
    assert student.post("/api/admin/elections", json={"title": "x", "candidates": ["a", "b"]}).status_code == 403
    assert student.get(f"/api/elections/{eid}/results").status_code == 403
    admin.patch(f"/api/admin/elections/{eid}/status", json={"status": "closed"})
    assert student.get(f"/api/elections/{eid}/results").status_code == 200


def test_cannot_vote_when_closed(client):
    admin, student = client(), client()
    register(admin, "admin1", admin=True)
    register(student, "s1")
    eid, cands = open_election(admin)
    admin.patch(f"/api/admin/elections/{eid}/status", json={"status": "closed"})
    assert student.post(f"/api/elections/{eid}/vote", json={"candidate_id": cands[0]["id"]}).status_code == 409


def test_bad_input_is_rejected_not_crashing(client):
    admin, student = client(), client()
    register(admin, "admin1", admin=True)
    register(student, "s1")
    eid, _ = open_election(admin)
    assert student.post(f"/api/elections/{eid}/vote", json={"candidate_id": "abc"}).status_code == 400
    assert student.post(f"/api/elections/{eid}/vote", json=[1, 2]).status_code == 400
    # Duplicate names collapse to one candidate, so this is not a valid election.
    r = admin.post("/api/admin/elections", json={"title": "x", "candidates": ["Ana", "Ana "]})
    assert r.status_code == 400
    r = admin.post("/api/admin/elections", json={"title": "x", "candidates": "Ana,Ben"})
    assert r.status_code == 400


def test_status_only_moves_forward(client):
    admin = client()
    register(admin, "admin1", admin=True)
    eid, _ = open_election(admin)
    assert admin.patch(f"/api/admin/elections/{eid}/status", json={"status": "draft"}).status_code == 400
    assert admin.patch(f"/api/admin/elections/{eid}/status", json={"status": "closed"}).status_code == 200
    assert admin.patch(f"/api/admin/elections/{eid}/status", json={"status": "open"}).status_code == 400


def test_results_count_votes(client):
    admin, s1, s2 = client(), client(), client()
    register(admin, "admin1", admin=True)
    register(s1, "s1")
    register(s2, "s2")
    eid, cands = open_election(admin)
    s1.post(f"/api/elections/{eid}/vote", json={"candidate_id": cands[0]["id"]})
    s2.post(f"/api/elections/{eid}/vote", json={"candidate_id": cands[0]["id"]})
    admin.patch(f"/api/admin/elections/{eid}/status", json={"status": "closed"})
    r = s1.get(f"/api/elections/{eid}/results").json
    assert r["total_votes"] == 2
    assert r["candidates"][0] == {"id": cands[0]["id"], "name": cands[0]["name"], "votes": 2}


def test_bad_login(client):
    c = client()
    register(c, "s1")
    assert c.post("/api/login", json={"student_id": "s1", "password": "wrong-pass"}).status_code == 401
