"""Immutable submissions, published reports, grade review and exam-scoped exports."""
import json
from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, request

from . import evaluation, exams, grading
from .ai_settings import model_options
from .catalog import get_private_tests
from .core import audit, body, db, digest, fail, files, ident, now, obj, ok, string, uid

bp = Blueprint("assessments", __name__)


def init_db(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS submissions(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),
      problem_id TEXT NOT NULL,exam_id TEXT REFERENCES exams(id),kind TEXT NOT NULL,status TEXT NOT NULL,
      created_at TEXT NOT NULL,payload TEXT NOT NULL,scores TEXT,evidence TEXT NOT NULL DEFAULT '[]',
      version INTEGER NOT NULL DEFAULT 1,graded_at TEXT,idempotency_key TEXT,fingerprint TEXT,
      api_key_id TEXT REFERENCES access_keys(id),
      UNIQUE(user_id,idempotency_key));
    CREATE INDEX IF NOT EXISTS submission_grades ON submissions(exam_id,user_id,kind);
    """)
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        if "api_key_id" not in {c[1] for c in conn.execute("PRAGMA table_info(submissions)")}:
            conn.execute("ALTER TABLE submissions ADD COLUMN api_key_id TEXT REFERENCES access_keys(id)")
        conn.execute("""CREATE INDEX IF NOT EXISTS submission_key_time ON submissions(api_key_id,created_at)
                     WHERE api_key_id IS NOT NULL""")
        conn.execute("""CREATE INDEX IF NOT EXISTS submission_key_status ON submissions(api_key_id,status)
                     WHERE api_key_id IS NOT NULL""")


def record(user, problem, exam_id, kind, data, key, fingerprint, *, api_key_id=None):
    sid = ident("SUB")
    model = json.loads(exams.exam_row(exam_id)["config"])["model"] if exam_id else (model_options()["name"] or None)
    payload = {"model": model, "problemSnapshot": problem, "files": files(data.get("files")),
               "aiHistory": exams.history(data.get("ai_history", data.get("aiHistory", []))),
               "explanation": string(data.get("explanation", ""), "说明", 50000, True)}
    payload["provenance"] = {"code_sha256": digest(obj(payload["files"])), "problem_version": problem["version"],
                             "test_version": grading.test_version(problem, get_private_tests(problem["id"], problem["version"])),
                             "prompt_version": grading.prompt_version(), "rubric_version": grading.RUBRIC_VERSION}
    db().execute("""INSERT INTO submissions(id,user_id,problem_id,exam_id,kind,status,created_at,
        payload,idempotency_key,fingerprint,api_key_id) VALUES(?,?,?,?,?,'QUEUED',?,?,?,?,?)""",
                 (sid, user, problem["id"], exam_id, kind, now(), obj(payload), key, fingerprint, api_key_id))
    evaluation.enqueue(sid)
    return sid


def get_row(sid):
    if getattr(g, "api_key_id", None):
        row = db().execute("SELECT * FROM submissions WHERE id=? AND user_id=?", (sid, uid())).fetchone()
    else:
        row = db().execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
    if row and (row["user_id"] == uid() or g.user["role"] == "admin" or
                (row["exam_id"] and exams.manager(exams.exam_row(row["exam_id"])))):
        return row
    fail(404, "提交不存在")


def can_view_score(row):
    if not row["exam_id"]:
        return True
    exam = exams.exam_row(row["exam_id"])
    return bool(exam["published_at"] or exams.manager(exam) or json.loads(exam["config"])["personal"])


def serialize(row):
    data = json.loads(row["payload"])
    show = can_view_score(row)
    return {**data, "id": row["id"], "submission_id": row["id"], "problemId": row["problem_id"],
            "examId": row["exam_id"], "userId": row["user_id"], "kind": row["kind"], "status": row["status"],
            "createdAt": row["created_at"], "scores": json.loads(row["scores"]) if row["scores"] and show else None,
            "version": row["version"], "idempotencyKey": row["idempotency_key"]}


@bp.route("/submissions", methods=["GET", "POST"])
def submissions():
    if request.method == "GET":
        return ok([serialize(r) for r in db().execute("SELECT * FROM submissions WHERE user_id=? ORDER BY created_at DESC", (uid(),))])
    data = body()
    key = string(request.headers.get("Idempotency-Key"), "Idempotency-Key", 180)
    fingerprint = digest(obj(data))
    exams.lock()
    api_key_id = getattr(g, "api_key_id", None)
    if api_key_id and not db().execute("""SELECT 1 FROM access_keys WHERE id=? AND user_id=? AND revoked=0 AND expires>?""",
                                      (api_key_id, uid(), now())).fetchone():
        fail(401, "凭证无效或已过期")
    found = db().execute("SELECT * FROM submissions WHERE user_id=? AND idempotency_key=?", (uid(), key)).fetchone()
    if found:
        if found["fingerprint"] != fingerprint:
            fail(409, "幂等键已用于不同内容")
        return ok(serialize(found), 202)
    if api_key_id:
        since = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="milliseconds")
        recent = db().execute("SELECT count(*) FROM submissions WHERE api_key_id=? AND created_at>?",
                              (api_key_id, since)).fetchone()[0]
        if recent >= 10:
            fail(429, "每个凭证每分钟最多接收 10 份新提交，请稍后重试")
        pending = db().execute("""SELECT count(*) FROM submissions WHERE api_key_id=?
            AND status IN ('ACCEPTED','QUEUED','TESTING','AI_SCORING','PENDING_REVIEW')""", (api_key_id,)).fetchone()[0]
        if pending >= 5:
            fail(429, "每个凭证最多有 5 份未完成提交，请等待已有任务完成后再试")
    eid = data.get("exam_id")
    problem, exam = exams.context(data.get("problem_version_id"), eid, write=True)
    if eid:
        count = db().execute("SELECT count(*) FROM submissions WHERE user_id=? AND exam_id=? AND problem_id=? AND kind='process'",
                             (uid(), eid, problem["id"])).fetchone()[0]
        if count >= exam["submissionLimit"]:
            fail(429, "本题过程提交次数已用尽，仍可保存和交卷")
    sid = record(uid(), problem, eid, "process" if eid else "practice", data, key, fingerprint, api_key_id=api_key_id)
    return ok(serialize(get_row(sid)), 202)


@bp.get("/submissions/<sid>")
def submission(sid):
    return ok(serialize(get_row(sid)))
