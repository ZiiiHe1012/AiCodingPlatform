"""Durable evaluation, isolated public runs and project-scoped model tasks."""
from datetime import datetime, timedelta
import json
import time

import click
from flask import Blueprint, g, request
from .core import audit, body, db, fail, files, ident, now, obj, ok, require, uid
from .sandbox import Interrupted, RunnerUnavailable, ServiceFault, TransientServiceFault, sandbox

bp = Blueprint("evaluation", __name__)
STATES = {"queued": "排队中", "running": "运行中", "done": "已完成", "failed": "SYSTEM_FAILED",
          "review": "PENDING_REVIEW", "cancelled": "已中止", "code_error": "运行错误"}
def public_job_state(state):
    return state


def init_db(conn):
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS evaluation_jobs(
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, user_id TEXT NOT NULL, exam_id TEXT,
        problem_id TEXT NOT NULL, submission_id TEXT UNIQUE, payload TEXT NOT NULL,
        state TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL, token TEXT,
        lease REAL NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0, result TEXT, error TEXT);
      CREATE INDEX IF NOT EXISTS evaluation_queue ON evaluation_jobs(state,lease,created);
      CREATE TABLE IF NOT EXISTS evaluation_events(
        id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, at TEXT NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS evaluation_trace ON evaluation_events(job_id,id);
    """)


def init_app(app):
    @app.cli.command("worker")
    @click.option("--once", is_flag=True, help="处理一个待执行任务并退出")
    def worker(once):
        while True:
            found = work_once()
            if once:
                break
            if not found:
                time.sleep(0.5)


def _log(job_id, event, detail=""):
    db().execute("INSERT INTO evaluation_events(job_id,at,event,detail) VALUES(?,?,?,?)",
                 (job_id, now(), event, detail[:1800]))


def _create(kind, user, exam_id, problem_id, payload, submission_id=None):
    jid, stamp = ident("JOB"), now()
    state = "queued"
    db().execute("""INSERT INTO evaluation_jobs
        (id,kind,user_id,exam_id,problem_id,submission_id,payload,state,created,updated)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (jid, kind, user, exam_id, problem_id, submission_id, obj(payload), state, stamp, stamp))
    _log(jid, "已受理", kind)
    return jid


def _request_context(data):
    from .exams import context
    pid = data.get("problem_version_id")
    if not isinstance(pid, str) or len(pid) > 160:
        fail(400, "请提供题目版本。")
    exam_id = data.get("exam_id")
    scope = data.get("scope")
    if not exam_id and isinstance(scope, str) and not scope.startswith("practice-"):
        exam_id = scope
    if exam_id is not None and not isinstance(exam_id, str):
        fail(400, "考试编号无效。")
    problem, exam = context(pid, exam_id=exam_id, write=True)
    project = files(data.get("files"))
    return problem, exam, project


def _new_interactive(kind, payload, exam, problem):
    conn = db()
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    exam_id = exam["id"] if exam else None
    limit = int(exam.get("publicRunLimit", 100) if exam else 100)
    if kind == "run" and exam:
        n = conn.execute("""SELECT count(*) FROM evaluation_jobs WHERE kind='run'
                     AND exam_id=? AND user_id=? AND state NOT IN ('failed','cancelled')""",
                         (exam_id, uid())).fetchone()[0]
        if n >= limit:
            fail(429, "本场考试的公开运行次数已用尽。")
    active = conn.execute("""SELECT count(*) FROM evaluation_jobs WHERE user_id=?
                AND kind IN ('ai','run') AND state IN ('queued','running')""", (uid(),)).fetchone()[0]
    if active >= 3:
        fail(429, "已有运行中的任务，请稍后重试。")
    # Keep only public metadata the runner needs, and the exact submitted working copy.
    meta_keys = ("id", "version", "stack", "requirements", "title", "evaluation", "entryFile",
                 "acceptance", "repository", "commands", "weights")
    payload["problem"] = {k: problem[k] for k in meta_keys if k in problem}
    payload["rules"] = {k: exam[k] for k in ("end", "requests", "tokens", "aiMode", "aiContext", "model")
                        if exam and k in exam}
    jid = _create(kind, uid(), exam_id, problem["id"], payload)
    conn.commit()
    return jid


def _respond(jid, asynchronous):
    if asynchronous:
        return ok({"id": jid, "job_id": jid, "status": "queued"}, 202)
    work_once(jid)
    # The background worker may have claimed it between commit and this request.
    end = time.monotonic() + 100
    while True:
        row = _job(jid)
        if row["state"] not in ("queued", "running") or time.monotonic() >= end:
            break
        time.sleep(.1)
    if row["state"] == "failed":
        result = json.loads(row["result"] or "{}")
        fail(result.get("http_status", 503), row["error"])
    if row["state"] == "cancelled":
        fail(409, row["error"] or "任务已中止。")
    if row["state"] in ("queued", "running"):
        return ok({"id": jid, "job_id": jid, "status": row["state"], "message": "任务仍在运行。"}, 202)
    return ok({**json.loads(row["result"] or "{}"), "job_id": jid, "status": row["state"]})


@bp.post("/runs")
def run():
    data = body()
    problem, exam, project = _request_context(data)
    command = data.get("command")
    if command is not None and (not isinstance(command, str) or not 1 <= len(command.strip()) <= 500):
        fail(400, "终端命令需要 1–500 个字符。")
    jid = _new_interactive("run", {"files": project, "command": command}, exam, problem)
    return _respond(jid, data.get("async") is True)


def _job(jid):
    row = db().execute("SELECT * FROM evaluation_jobs WHERE id=?", (jid,)).fetchone()
    if not row:
        fail(404, "任务不存在。")
    return row


def _authorize(row, management=False):
    if g.user["role"] == "admin":
        return
    if not management and row["user_id"] == uid():
        return
    if row["exam_id"] and g.user["role"] == "teacher":
        from .exams import manage
        manage(row["exam_id"])
        return
    fail(403, "无权查看或处理此任务。")


def _events(jid):
    return [dict(r) for r in db().execute(
        "SELECT at,event,detail FROM evaluation_events WHERE job_id=? ORDER BY id", (jid,))]


def _summary(row):
    result = {"id": row["id"], "kind": row["kind"], "status": public_job_state(row["state"]), "user_id": row["user_id"],
              "exam_id": row["exam_id"], "problem_id": row["problem_id"], "submission_id": row["submission_id"],
              "created_at": row["created"], "updated_at": row["updated"], "error": row["error"]}
    return result


@bp.get("/jobs/<jid>")
def job_detail(jid):
    row = _job(jid)
    _authorize(row, management=row["kind"] == "grade")
    result = json.loads(row["result"] or "{}")
    return ok({**_summary(row), "result": result, "events": _events(jid)})


@bp.post("/jobs/<jid>/cancel")
def cancel(jid):
    row = _job(jid)
    _authorize(row)
    if row["kind"] == "grade":
        fail(409, "正式提交评测将继续进行。")
    changed = db().execute("""UPDATE evaluation_jobs SET state='cancelled',error='任务已中止',updated=?
                 WHERE id=? AND state IN ('queued','running')""", (now(), jid)).rowcount
    if changed:
        _log(jid, "中止任务", uid())
    return ok({"id": jid, "status": _job(jid)["state"]})


@bp.get("/exams/<eid>/process-records")
def process_records(eid):
    from .exams import manage
    manage(eid)
    student = request.args.get("user_id")
    rows = db().execute("""SELECT * FROM evaluation_jobs WHERE exam_id=? AND (? IS NULL OR user_id=?)
                ORDER BY created DESC,id DESC LIMIT 250""", (eid, student, student)).fetchall()
    return ok({"items": [{**_summary(row), "events": _events(row["id"])} for row in rows]})


def _claim(jid):
    conn = db()
    conn.execute("BEGIN IMMEDIATE")
    sql = """SELECT * FROM evaluation_jobs WHERE kind IN ('run','ai')
             AND ((state='queued' AND lease<=?) OR (state='running' AND lease<?))"""
    params = [time.time(), time.time()]
    if jid:
        sql += " AND id=?"
        params.append(jid)
    row = conn.execute(sql + " ORDER BY created,id LIMIT 1", params).fetchone()
    if not row:
        conn.commit()
        return None
    token = ident("LEASE")
    conn.execute("""UPDATE evaluation_jobs SET state='running',token=?,lease=?,attempts=attempts+1,
                 updated=? WHERE id=?""", (token, time.time()+45, now(), row["id"]))
    _log(row["id"], "执行开始", "恢复中断任务" if public_job_state(row["state"]) == "running" else "")
    conn.commit()
    return row, token


def _guard(row, token):
    last = [0.0]
    def check():
        t = time.time()
        if t - last[0] < .35:
            return
        last[0] = t
        conn = db()
        item = conn.execute("SELECT state,token,lease FROM evaluation_jobs WHERE id=?", (row["id"],)).fetchone()
        if public_job_state(item["state"]) != "running" or item["token"] != token:
            raise Interrupted("任务已中止或由其他工作进程接管。")
        if row["kind"] != "grade" and row["exam_id"]:
            exam = conn.execute("SELECT end,state FROM exams WHERE id=?", (row["exam_id"],)).fetchone()
            if not exam or exam["state"] != "published":
                raise Interrupted("考试已关闭。")
            if conn.execute("SELECT 1 FROM sheets WHERE exam_id=? AND user_id=?",
                            (row["exam_id"], row["user_id"])).fetchone():
                raise Interrupted("考生已交卷。")
            deadline = datetime.fromisoformat(exam["end"].replace("Z","+00:00")).timestamp()
            if t >= deadline:
                raise Interrupted("考试已截止。")
        if item["lease"] - t < 30:
            conn.execute("UPDATE evaluation_jobs SET lease=? WHERE id=? AND token=?",
                         (t+45, row["id"], token))
            conn.commit()
    return check


def _terminal(project, problem, command, check, workspace=None):
    if command is None:
        command = problem.get("commands", {}).get("test") or "python -m pytest -q"
    # Shell parsing and execution take place exclusively within the disposable container.
    identity = {"user_id": workspace["user_id"], "exam_id": workspace["exam_id"]} if workspace else None
    return sandbox(project, {"action": "command", "argv": ["/bin/sh", "-c", command]}, problem, check, workspace=identity)


def _finish(row, token, state, result, reason):
    conn = db()
    conn.execute("BEGIN IMMEDIATE")
    if row["exam_id"]:
        exam = conn.execute("SELECT state,end FROM exams WHERE id=?", (row["exam_id"],)).fetchone()
        sealed = conn.execute("SELECT 1 FROM sheets WHERE exam_id=? AND user_id=?",
                              (row["exam_id"], row["user_id"])).fetchone()
        if not exam or sealed or exam["state"] != "published" or datetime.fromisoformat(exam["end"].replace("Z","+00:00")).timestamp() <= time.time():
            state, result, reason = "cancelled", {}, "考试已截止、已关闭或考生已交卷。"
    changed = conn.execute("""UPDATE evaluation_jobs SET state=?,result=?,error=?,updated=?,token=NULL,lease=0
             WHERE id=? AND token=? AND state='running'""",
             (state, obj(result), reason, now(), row["id"], token)).rowcount
    if changed:
        _log(row["id"], STATES[state], reason or result.get("message", "")[:400])
    conn.commit()


def work_once(jid=None):
    claimed = _claim(jid)
    if not claimed:
        return False
    row, token = claimed
    check = _guard(row, token)
    try:
        check()
        data = json.loads(row["payload"])
        outcome = _terminal(data["files"], data["problem"], data.get("command"), check, row)
        code = outcome["code"]
        message = f"退出码 {code}" + (" · 超过运行限时" if outcome["timed_out"] else "")
        result = {"message": message + "\n" + outcome["output"], "exit_code": code}
        state, reason = ("done", "") if code == 0 else ("code_error", message)
        check()
    except Interrupted as exc:
        state, result, reason = "cancelled", {}, str(exc)
    except ServiceFault as exc:
        state, result, reason = "failed", {}, str(exc)
    except Exception:
        # Avoid leaking host paths, hidden tests, provider responses or source into learner-visible messages.
        from flask import current_app
        current_app.logger.exception("评测任务执行失败 job=%s", row["id"])
        state, result, reason = "failed", {}, "工作进程异常，请联系教师查看任务并重评。"
    if db().in_transaction:
        db().rollback()
    _finish(row, token, state, result, reason)
    return True
