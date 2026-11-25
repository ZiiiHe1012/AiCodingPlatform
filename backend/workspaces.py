"""Student-owned project workspaces. Browser previews are rendered in the runner."""
import hashlib
import json
import threading
import time

from flask import Blueprint

from . import exams, sandbox
from .core import body, db, fail, ok, uid

bp = Blueprint("workspaces", __name__)
_preview_slots = threading.BoundedSemaphore(2)


def workspace(scope, pid, write=False):
    if scope.startswith("practice-") and scope != "practice-" + pid:
        fail(404, "此题不属于当前练习。")
    eid = None if scope == "practice-" + pid else scope
    if eid and not exams.participant(exams.accessible(eid), uid()):
        fail(403, "当前账号未参加这场考试。")
    problem, _ = exams.context(pid, eid, write=write)
    draft = exams.saved(uid(), scope, pid)
    return eid, problem, draft


@bp.get("/workspaces/<scope>/<pid>")
def detail(scope, pid):
    eid, problem, draft = workspace(scope, pid)
    identity = json.dumps([uid(), scope, pid], separators=(",", ":")).encode()
    status, note = "on_demand", ""
    if eid:
        provision = db().execute("SELECT ready,last_error FROM exam_sandboxes WHERE exam_id=? AND user_id=?",
                                 (eid, uid())).fetchone()
        if exams.sheet_data(eid, uid()):
            status = "closed"
        elif provision:
            note = provision["last_error"]
            status = "ready" if provision["ready"] else ("unavailable" if note else "preparing")
        else:
            status = "preparing"
    return ok({"id": "WS-" + hashlib.sha256(identity).hexdigest()[:16], "problem_id": pid,
               "exam_id": eid, "runner_status": status, "runner_note": note, "version": draft["version"] if draft else 0,
               "preview_available": "index.html" in (draft["files"] if draft else problem["files"]),
               "stack": problem["stack"], "model": (json.loads(exams.exam_row(eid)["config"])["model"]
               if eid else "")})


def preview_actions(value):
    if not isinstance(value, list) or len(value) > 25:
        fail(422, "最多可回放 25 次操作，请重置网页预览。")
    for action in value:
        if (not isinstance(action, dict) or type(action.get("index")) is not int
                or not 0 <= action["index"] < 60 or action.get("kind") not in ("click", "fill")):
            fail(422, "预览操作无效。")
        if action["kind"] == "fill":
            if not isinstance(action.get("value"), str) or len(action["value"]) > 500:
                fail(422, "预览输入不能超过 500 个字符。")
        if set(action) - {"index", "kind", "value"}:
            fail(422, "预览操作含未知字段。")
    return value


@bp.post("/workspaces/<scope>/<pid>/preview")
def preview(scope, pid):
    eid, problem, draft = workspace(scope, pid, write=True)
    request_data = body()
    version = draft["version"] if draft else 0
    if type(request_data.get("version")) is not int or version != request_data["version"]:
        fail(409, "工作区版本已改变，请重新保存并刷新预览。")
    project = draft["files"] if draft else problem["files"]
    if "index.html" not in project:
        fail(422, "当前项目没有网页入口，请在个人沙箱运行项目检查。")
    actions = preview_actions(request_data.get("actions", []))
    if not _preview_slots.acquire(blocking=False):
        fail(429, "预览运行器正忙，请稍后再试。")
    last_check = 0.0

    def checkpoint():
        nonlocal last_check
        if eid and time.monotonic() - last_check >= 0.5:
            exams.writer(exams.exam_row(eid))
            last_check = time.monotonic()

    try:
        result = sandbox.build_preview(project, problem, {"user_id": uid(), "exam_id": eid, "problem_id": pid},
                                       checkpoint, actions=actions)
    except sandbox.ServiceFault as exc:
        fail(503, str(exc))
    except ValueError as exc:
        fail(422, str(exc))
    finally:
        _preview_slots.release()
    if eid:
        exams.writer(exams.exam_row(eid))
    latest = exams.saved(uid(), scope, pid)
    if (latest["version"] if latest else 0) != version:
        fail(409, "构建期间草稿已更新，请刷新预览。")
    return ok({**result, "version": version})
