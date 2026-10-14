"""Flask API for the school voting app."""
import os
from functools import wraps

import bcrypt
import psycopg2.errors
from flask import Flask, jsonify, request, session
from flask_cors import CORS

import db

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
CORS(app, supports_credentials=True, origins=os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173"))


# ---------------------------------------------------------------- helpers
def error(msg, code):
    return jsonify({"error": msg}), code


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user_id" not in session:
            return error("login required", 401)
        return f(*a, **kw)
    return wrapper


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*a, **kw):
        if session.get("role") != "admin":
            return error("admin only", 403)
        return f(*a, **kw)
    return wrapper


def body(*fields):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    missing = [f for f in fields if not str(data.get(f, "")).strip()]
    return data, missing


# ---------------------------------------------------------------- auth
@app.post("/api/register")
def register():
    data, missing = body("student_id", "name", "password")
    if missing:
        return error(f"missing: {', '.join(missing)}", 400)
    if not all(isinstance(data[f], str) for f in ("student_id", "name", "password")):
        return error("student_id, name and password must be strings", 400)
    if len(data["password"]) < 8:
        return error("password must be at least 8 characters", 400)
    pw_hash = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt(rounds=12)).decode()
    try:
        with db.get_cursor() as cur:
            cur.execute("INSERT INTO users (student_id, name, password_hash) VALUES (%s, %s, %s) "
                        "RETURNING id, student_id, name, role",
                        (data["student_id"].strip(), data["name"].strip(), pw_hash))
            user = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return error("that student ID is already registered", 409)
    session.clear()
    session.update(user_id=user["id"], role=user["role"])
    return jsonify(user), 201


@app.post("/api/login")
def login():
    data, missing = body("student_id", "password")
    if missing:
        return error("student ID and password required", 400)
    if not isinstance(data["student_id"], str) or not isinstance(data["password"], str):
        return error("student ID and password must be strings", 400)
    with db.get_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE student_id = %s", (data["student_id"].strip(),))
        user = cur.fetchone()
    if not user or not bcrypt.checkpw(data["password"].encode(), user["password_hash"].encode()):
        return error("invalid student ID or password", 401)
    session.clear()
    session.update(user_id=user["id"], role=user["role"])
    return jsonify({k: user[k] for k in ("id", "student_id", "name", "role")})


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/me")
@login_required
def me():
    with db.get_cursor() as cur:
        cur.execute("SELECT id, student_id, name, role FROM users WHERE id = %s", (session["user_id"],))
        return jsonify(cur.fetchone())


# ---------------------------------------------------------------- elections (students)
@app.get("/api/elections")
@login_required
def list_elections():
    is_admin = session.get("role") == "admin"
    with db.get_cursor() as cur:
        cur.execute(f"""
            SELECT e.id, e.title, e.description, e.status,
                   EXISTS (SELECT 1 FROM votes v WHERE v.election_id = e.id AND v.user_id = %s) AS has_voted
            FROM elections e
            {"" if is_admin else "WHERE e.status <> 'draft'"}
            ORDER BY e.created_at DESC""", (session["user_id"],))
        return jsonify(cur.fetchall())


@app.get("/api/elections/<int:eid>")
@login_required
def get_election(eid):
    with db.get_cursor() as cur:
        cur.execute("SELECT id, title, description, status FROM elections WHERE id = %s", (eid,))
        election = cur.fetchone()
        if not election or (election["status"] == "draft" and session.get("role") != "admin"):
            return error("election not found", 404)
        cur.execute("SELECT id, name, platform FROM candidates WHERE election_id = %s ORDER BY name", (eid,))
        election["candidates"] = cur.fetchall()
        cur.execute("SELECT 1 FROM votes WHERE election_id = %s AND user_id = %s", (eid, session["user_id"]))
        election["has_voted"] = cur.fetchone() is not None
    return jsonify(election)


@app.post("/api/elections/<int:eid>/vote")
@login_required
def vote(eid):
    data, missing = body("candidate_id")
    if missing:
        return error("candidate_id required", 400)
    try:
        candidate_id = int(data["candidate_id"])
    except (TypeError, ValueError):
        return error("candidate_id must be an integer", 400)
    try:
        with db.get_cursor() as cur:            # single transaction
            # Lock the election row so it can't be closed halfway through this vote.
            cur.execute("SELECT status FROM elections WHERE id = %s FOR SHARE", (eid,))
            row = cur.fetchone()
            if not row:
                return error("election not found", 404)
            if row["status"] != "open":
                return error("this election is not open for voting", 409)
            cur.execute("INSERT INTO votes (user_id, election_id, candidate_id) VALUES (%s, %s, %s)",
                        (session["user_id"], eid, candidate_id))
    except psycopg2.errors.UniqueViolation:
        # The UNIQUE(user_id, election_id) constraint caught a second vote,
        # even if two requests raced each other.
        return error("you have already voted in this election", 409)
    except psycopg2.errors.ForeignKeyViolation:
        return error("that candidate is not in this election", 400)
    return jsonify({"ok": True}), 201


@app.get("/api/elections/<int:eid>/results")
@login_required
def results(eid):
    with db.get_cursor() as cur:
        cur.execute("SELECT title, status FROM elections WHERE id = %s", (eid,))
        e = cur.fetchone()
        if not e:
            return error("election not found", 404)
        if e["status"] != "closed" and session.get("role") != "admin":
            return error("results are available once the election closes", 403)
        cur.execute("""
            SELECT c.id, c.name, COUNT(v.id)::int AS votes
            FROM candidates c LEFT JOIN votes v ON v.candidate_id = c.id
            WHERE c.election_id = %s GROUP BY c.id ORDER BY votes DESC, c.name""", (eid,))
        rows = cur.fetchall()
    total = sum(r["votes"] for r in rows)
    return jsonify({"title": e["title"], "status": e["status"], "total_votes": total, "candidates": rows})


# ---------------------------------------------------------------- admin
@app.post("/api/admin/elections")
@admin_required
def create_election():
    data, missing = body("title")
    if missing or not isinstance(data["title"], str):
        return error("title required", 400)
    raw = data.get("candidates", [])
    if not isinstance(raw, list) or not all(isinstance(n, str) for n in raw):
        return error("candidates must be a list of names", 400)
    names = list(dict.fromkeys(n.strip() for n in raw if n.strip()))   # de-duplicate, keep order
    if len(names) < 2:
        return error("add at least two different candidates", 400)
    description = data.get("description") or ""
    if not isinstance(description, str):
        return error("description must be text", 400)
    with db.get_cursor() as cur:
        cur.execute("INSERT INTO elections (title, description, created_by) VALUES (%s, %s, %s) RETURNING id",
                    (data["title"].strip(), description, session["user_id"]))
        eid = cur.fetchone()["id"]
        for name in names:
            cur.execute("INSERT INTO candidates (election_id, name) VALUES (%s, %s)", (eid, name))
    return jsonify({"id": eid}), 201


@app.patch("/api/admin/elections/<int:eid>/status")
@admin_required
def set_status(eid):
    status = (request.get_json(silent=True) or {}).get("status")
    allowed = {"draft": "open", "open": "closed"}        # draft -> open -> closed, no going back
    with db.get_cursor() as cur:
        cur.execute("SELECT status FROM elections WHERE id = %s FOR UPDATE", (eid,))
        row = cur.fetchone()
        if not row:
            return error("election not found", 404)
        if allowed.get(row["status"]) != status:
            return error(f"can't move from {row['status']} to {status}", 400)
        cur.execute("UPDATE elections SET status = %s WHERE id = %s", (status, eid))
    return jsonify({"id": eid, "status": status})


@app.get("/api/admin/stats")
@admin_required
def stats():
    with db.get_cursor() as cur:
        cur.execute("""SELECT (SELECT COUNT(*) FROM users WHERE role = 'student')::int AS students,
                              (SELECT COUNT(DISTINCT user_id) FROM votes)::int AS voters,
                              (SELECT COUNT(*) FROM votes)::int AS votes""")
        return jsonify(cur.fetchone())


# ---------------------------------------------------------------- CLI
@app.cli.command("init-db")
def init_db_cmd():
    """flask init-db : create tables"""
    db.init_schema()
    print("Schema created.")


@app.cli.command("make-admin")
def make_admin_cmd():
    """flask make-admin : promote a registered student to admin"""
    sid = input("Student ID to promote: ").strip()
    with db.get_cursor() as cur:
        cur.execute("UPDATE users SET role = 'admin' WHERE student_id = %s RETURNING name", (sid,))
        row = cur.fetchone()
    print(f"{row['name']} is now an admin." if row else "No such user.")


db.init_pool()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
