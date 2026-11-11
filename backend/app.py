"""Reunite - Flask REST API.

Public (no login): camp list, family search, report status.
Staff (camp PIN):  register arrivals, camp dashboard, verify matches, alerts.
"""
from __future__ import annotations

import os
import secrets
import uuid

from flask import Flask, abort, jsonify, request, send_from_directory

import db
from face_engine import engine
from matching import LIKELY, MIN_SAVE, score

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(ROOT, "frontend")

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

# Demo staff PINs (per camp) plus one NGO / district-authority PIN that sees all camps.
STAFF_PINS = {"1111": "CAMP-A", "2222": "CAMP-B", "3333": "CAMP-C", "0000": "*"}
SESSIONS: dict[str, str] = {}  # token -> camp code or "*"


# ---------------------------------------------------------------- helpers

def staff() -> str:
    tok = request.headers.get("X-Staff-Token") or request.args.get("t")
    if not tok or tok not in SESSIONS:
        abort(401)
    return SESSIONS[tok]


def new_ref(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(3).upper()}"


def save_photo(file) -> tuple[str | None, bytes | None]:
    if not file or not file.filename:
        return None, None
    data = file.read()
    if not data:
        return None, None
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        ext = ".jpg"
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(db.PHOTO_DIR, name), "wb") as fh:
        fh.write(data)
    return name, data


def as_int(v):
    try:
        return int(v) if v not in (None, "") else None
    except ValueError:
        return None


def person_json(r, full=True):
    d = {
        "id": r["id"], "ref": r["ref"], "age": r["age"], "gender": r["gender"],
        "camp": r["camp_name"], "camp_code": r["camp_code"], "district": r["district"],
        "status": r["status"], "created_at": r["created_at"],
    }
    if full:
        d.update(name=r["name"], origin=r["origin"], marks=r["marks"], tent=r["tent"],
                 photo=r["photo"], has_face=r["embedding"] is not None)
    return d


PEOPLE_SQL = """SELECT p.*, c.name AS camp_name, c.code AS camp_code, c.district
                FROM people p JOIN camps c ON c.id = p.camp_id"""


def add_alert(con, kind, message, camp_id=None, match_id=None):
    con.execute("INSERT INTO alerts(kind, message, camp_id, match_id) VALUES (?,?,?,?)",
                (kind, message, camp_id, match_id))


def record_match(con, report, person, s) -> int | None:
    if s is None or s["confidence"] < MIN_SAVE:
        return None
    cur = con.execute(
        """INSERT INTO matches(report_id, person_id, confidence, face_score, text_score, method)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(report_id, person_id) DO UPDATE SET confidence=excluded.confidence,
             face_score=excluded.face_score, text_score=excluded.text_score, method=excluded.method
           RETURNING id""",
        (report["id"], person["id"], s["confidence"], s["face_score"], s["text_score"], s["method"]))
    mid = cur.fetchone()[0]
    if s["confidence"] >= LIKELY:
        add_alert(con, "match",
                  f'Likely match ({s["confidence"]:.0f}%) for report {report["ref"]}: '
                  f'{person["ref"]} at {person["camp_name"]}. Needs volunteer verification.',
                  person["camp_id"], mid)
    return mid


# ---------------------------------------------------------------- public API

@app.get("/api/health")
def health():
    return jsonify(ok=True, face_engine=engine.backend)


@app.get("/api/camps")
def camps():
    with db.connect() as con:
        rows = con.execute(
            """SELECT c.*, COUNT(p.id) AS registered FROM camps c
               LEFT JOIN people p ON p.camp_id = c.id GROUP BY c.id ORDER BY c.code""").fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/api/search")
def family_search():
    """A relative searches with a photo and/or a description. No login needed.

    The search is saved as an open report so that anyone registered later is
    matched against it at intake. Public results carry no photos or names.
    """
    f = request.form
    fname, data = save_photo(request.files.get("photo"))
    emb, face_found = None, None
    if data is not None:
        vec = engine.embed(data)
        face_found = vec is not None
        emb = vec.tobytes() if vec is not None else None

    if not any([emb, f.get("name"), f.get("age"), f.get("gender"), f.get("last_seen"), f.get("marks")]):
        return jsonify(error="Add a photo or at least one detail about the person."), 400

    with db.connect() as con:
        ref = new_ref("RPT")
        con.execute(
            """INSERT INTO reports(ref, seeker_name, seeker_phone, relation, name, age, gender,
                                   last_seen, marks, photo, embedding)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (ref, f.get("seeker_name"), f.get("seeker_phone"), f.get("relation"), f.get("name"),
             as_int(f.get("age")), f.get("gender") or None, f.get("last_seen"), f.get("marks"),
             fname, emb))
        report = con.execute("SELECT * FROM reports WHERE ref=?", (ref,)).fetchone()

        results = []
        for p in con.execute(PEOPLE_SQL + " WHERE p.status='registered'").fetchall():
            s = score(report, p)
            if s is None or s["confidence"] < MIN_SAVE:
                continue
            record_match(con, report, p, s)
            results.append({**s, "person": person_json(p, full=False)})
        results.sort(key=lambda r: r["confidence"], reverse=True)

    return jsonify(report_ref=ref, face_found=face_found, results=results[:5],
                   engine=engine.backend)


@app.get("/api/reports/<ref>")
def report_status(ref):
    with db.connect() as con:
        r = con.execute("SELECT * FROM reports WHERE ref=?", (ref.upper(),)).fetchone()
        if not r:
            return jsonify(error="No report with that reference."), 404
        m = con.execute(
            """SELECT m.*, c.name AS camp_name, c.district, p.tent FROM matches m
               JOIN people p ON p.id=m.person_id JOIN camps c ON c.id=p.camp_id
               WHERE m.report_id=? AND m.status='verified' ORDER BY m.confidence DESC LIMIT 1""",
            (r["id"],)).fetchone()
        pending = con.execute(
            "SELECT COUNT(*) FROM matches WHERE report_id=? AND status='pending'", (r["id"],)
        ).fetchone()[0]
    out = {"ref": r["ref"], "status": r["status"], "pending_candidates": pending,
           "created_at": r["created_at"]}
    if m:  # Only after a volunteer has verified do we reveal where the person is.
        out["found"] = {"camp": m["camp_name"], "district": m["district"], "tent": m["tent"],
                        "confidence": m["confidence"]}
    return jsonify(out)


# ---------------------------------------------------------------- staff API

@app.post("/api/login")
def login():
    pin = (request.get_json(silent=True) or {}).get("pin", "")
    camp = STAFF_PINS.get(pin)
    if not camp:
        return jsonify(error="Invalid PIN"), 401
    tok = secrets.token_urlsafe(16)
    SESSIONS[tok] = camp
    with db.connect() as con:
        c = con.execute("SELECT * FROM camps WHERE code=?", (camp,)).fetchone()
    return jsonify(token=tok, scope=camp, camp=dict(c) if c else None)


@app.get("/api/photos/<name>")
def photo(name):
    staff()  # full photos are visible to verified staff only
    return send_from_directory(db.PHOTO_DIR, name)


@app.get("/api/people")
def people():
    scope = staff()
    q, where, args = request.args, [], []
    camp = q.get("camp") if scope == "*" else scope
    if camp:
        where.append("c.code=?"); args.append(camp)
    if q.get("gender"):
        where.append("p.gender=?"); args.append(q["gender"])
    if q.get("status"):
        where.append("p.status=?"); args.append(q["status"])
    if q.get("age_min"):
        where.append("p.age>=?"); args.append(as_int(q["age_min"]))
    if q.get("age_max"):
        where.append("p.age<=?"); args.append(as_int(q["age_max"]))
    if q.get("q"):
        where.append("(p.name LIKE ? OR p.ref LIKE ? OR p.origin LIKE ? OR p.marks LIKE ?)")
        args += [f'%{q["q"]}%'] * 4
    sql = PEOPLE_SQL + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY p.id DESC"
    with db.connect() as con:
        rows = con.execute(sql, args).fetchall()
    return jsonify([person_json(r) for r in rows])


@app.post("/api/people")
def register():
    """Camp intake. The new arrival is matched against every open family report immediately."""
    scope = staff()
    f = request.form
    if f.get("consent") != "true":
        return jsonify(error="Consent is required before a person can be registered."), 400
    camp_code = f.get("camp") if scope == "*" else scope
    fname, data = save_photo(request.files.get("photo"))
    emb, face_found = None, None
    if data is not None:
        vec = engine.embed(data)
        face_found = vec is not None
        emb = vec.tobytes() if vec is not None else None

    with db.connect() as con:
        camp = con.execute("SELECT * FROM camps WHERE code=?", (camp_code,)).fetchone()
        if not camp:
            return jsonify(error="Unknown camp"), 400
        ref = new_ref("REG")
        con.execute(
            """INSERT INTO people(ref, name, age, gender, origin, marks, camp_id, tent, photo,
                                  embedding, consent) VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
            (ref, f.get("name") or None, as_int(f.get("age")), f.get("gender") or None,
             f.get("origin"), f.get("marks"), camp["id"], f.get("tent"), fname, emb))
        person = con.execute(PEOPLE_SQL + " WHERE p.ref=?", (ref,)).fetchone()
        add_alert(con, "intake", f'{ref} registered at {camp["name"]}'
                  + (" with face photo" if emb else ""), camp["id"])

        matches = []
        for rep in con.execute("SELECT * FROM reports WHERE status='open'").fetchall():
            s = score(rep, person)
            mid = record_match(con, rep, person, s)
            if mid:
                matches.append({"match_id": mid, "report_ref": rep["ref"], **s})
        matches.sort(key=lambda m: m["confidence"], reverse=True)

    return jsonify(person=person_json(person), face_found=face_found, intake_matches=matches)


@app.get("/api/matches")
def list_matches():
    scope = staff()
    status = request.args.get("status", "pending")
    sql = """SELECT m.*, r.ref AS report_ref, r.seeker_name, r.seeker_phone, r.relation,
                    r.name AS r_name, r.age AS r_age, r.gender AS r_gender, r.last_seen,
                    r.marks AS r_marks, r.photo AS r_photo,
                    p.ref AS p_ref, p.name AS p_name, p.age AS p_age, p.gender AS p_gender,
                    p.origin AS p_origin, p.marks AS p_marks, p.photo AS p_photo, p.tent,
                    c.name AS camp_name, c.code AS camp_code, c.district
             FROM matches m JOIN reports r ON r.id=m.report_id
             JOIN people p ON p.id=m.person_id JOIN camps c ON c.id=p.camp_id
             WHERE m.status=?"""
    args = [status]
    if scope != "*":
        sql += " AND c.code=?"; args.append(scope)
    sql += " ORDER BY m.confidence DESC"
    with db.connect() as con:
        rows = con.execute(sql, args).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/api/matches/<int:mid>/decision")
def decide(mid):
    scope = staff()
    decision = (request.get_json(silent=True) or {}).get("decision")
    if decision not in ("verified", "rejected"):
        return jsonify(error="decision must be verified or rejected"), 400
    with db.connect() as con:
        m = con.execute(
            """SELECT m.*, r.ref AS report_ref, r.seeker_name, r.seeker_phone, p.ref AS p_ref,
                      p.camp_id, p.tent, c.name AS camp_name, c.code AS camp_code
               FROM matches m JOIN reports r ON r.id=m.report_id JOIN people p ON p.id=m.person_id
               JOIN camps c ON c.id=p.camp_id WHERE m.id=?""", (mid,)).fetchone()
        if not m or (scope != "*" and m["camp_code"] != scope):
            abort(404)
        con.execute("UPDATE matches SET status=? WHERE id=?", (decision, mid))
        if decision == "verified":
            con.execute("UPDATE reports SET status='resolved' WHERE id=?", (m["report_id"],))
            con.execute("UPDATE people SET status='reunited' WHERE id=?", (m["person_id"],))
            con.execute("UPDATE matches SET status='rejected' WHERE report_id=? AND id<>? AND status='pending'",
                        (m["report_id"], mid))
            who = m["seeker_name"] or "The family"
            phone = f' ({m["seeker_phone"]})' if m["seeker_phone"] else ""
            add_alert(con, "verified",
                      f'Match verified: {m["p_ref"]} at {m["camp_name"]}, Tent {m["tent"] or "-"}. '
                      f'{who}{phone} notified for report {m["report_ref"]}.', m["camp_id"], mid)
        else:
            add_alert(con, "rejected", f'Candidate {m["p_ref"]} rejected for report {m["report_ref"]}.',
                      m["camp_id"], mid)
    return jsonify(ok=True)


@app.get("/api/alerts")
def alerts():
    scope = staff()
    sql = "SELECT a.*, c.name AS camp_name FROM alerts a LEFT JOIN camps c ON c.id=a.camp_id"
    args = []
    if scope != "*":
        sql += " WHERE c.code=?"; args.append(scope)
    sql += " ORDER BY a.id DESC LIMIT 40"
    with db.connect() as con:
        rows = con.execute(sql, args).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/stats")
def stats():
    scope = staff()
    cf, args = ("", []) if scope == "*" else (" AND c.code=?", [scope])
    with db.connect() as con:
        one = lambda sql: con.execute(sql, args).fetchone()[0]
        out = {
            "registered": one("SELECT COUNT(*) FROM people p JOIN camps c ON c.id=p.camp_id WHERE 1=1" + cf),
            "with_face": one("SELECT COUNT(*) FROM people p JOIN camps c ON c.id=p.camp_id WHERE p.embedding IS NOT NULL" + cf),
            "children": one("SELECT COUNT(*) FROM people p JOIN camps c ON c.id=p.camp_id WHERE p.age<14" + cf),
            "elderly": one("SELECT COUNT(*) FROM people p JOIN camps c ON c.id=p.camp_id WHERE p.age>=60" + cf),
            "pending": one("SELECT COUNT(*) FROM matches m JOIN people p ON p.id=m.person_id JOIN camps c ON c.id=p.camp_id WHERE m.status='pending'" + cf),
            "reunited": one("SELECT COUNT(*) FROM people p JOIN camps c ON c.id=p.camp_id WHERE p.status='reunited'" + cf),
            "open_reports": con.execute("SELECT COUNT(*) FROM reports WHERE status='open'").fetchone()[0],
        }
    out["face_engine"] = engine.backend
    return jsonify(out)


# ---------------------------------------------------------------- frontend

@app.get("/")
@app.get("/<path:path>")
def spa(path="index.html"):
    if path.startswith("api/"):
        abort(404)
    full = os.path.join(FRONTEND, path)
    if os.path.isfile(full):
        return send_from_directory(FRONTEND, path)
    return send_from_directory(FRONTEND, "index.html")


db.init()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Reunite running on http://localhost:{port}  (face engine: {engine.backend})")
    app.run(host="0.0.0.0", port=port, debug=False)
