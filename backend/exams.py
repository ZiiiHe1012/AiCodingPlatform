"""Exam rules, participant snapshots, editor leases and atomic hand-in."""
import json
import math
from datetime import datetime, timezone

from flask import Blueprint, g, request

from . import catalog
from .core import audit, body, db, fail, files, ident, now, obj, ok, require, string, uid

bp = Blueprint("exams", __name__)


def init_db(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS exams(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
      start TEXT NOT NULL,end TEXT NOT NULL,state TEXT NOT NULL,config TEXT NOT NULL,snapshots TEXT NOT NULL,
      published_at TEXT);
    CREATE TABLE IF NOT EXISTS participants(exam_id TEXT NOT NULL REFERENCES exams(id),user_id TEXT NOT NULL
      REFERENCES users(id),PRIMARY KEY(exam_id,user_id));
    CREATE INDEX IF NOT EXISTS exam_dates ON exams(state,end);
    """)
    # Old drafts stored only the unique classroom name. Bind the current class before a rename.
    conn.execute("""UPDATE exams AS e SET config=json_set(config,'$.classId',
            (SELECT c.id FROM classes c WHERE c.name=json_extract(e.config,'$.className')))
        WHERE state='draft' AND json_type(config,'$.classId') IS NULL
            AND json_extract(config,'$.personal')=0
            AND EXISTS (SELECT 1 FROM classes c WHERE c.name=json_extract(e.config,'$.className'))""")


def lock():
    if not db().in_transaction:
        db().execute("BEGIN IMMEDIATE")


def iso(value):
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError()
        return date.astimezone(timezone.utc).isoformat(timespec="milliseconds")
    except (ValueError, TypeError, AttributeError, OverflowError):
        fail(422, "考试时间必须包含时区")


def weights(values, n, positive=True):
    if (not isinstance(values, list) or len(values) != n
            or any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 100
                   or (positive and x == 0) for x in values)
            or not math.isclose(sum(values), 100, abs_tol=0.000001)):
        fail(422, "请检查权重项数及范围，各项合计须为 100%")
    return values


def exam_row(exam_id):
    row = db().execute("SELECT * FROM exams WHERE id=?", (exam_id,)).fetchone()
    if row is None:
        fail(404, "考试不存在")
    return row


def manager(row):
    return g.user["role"] == "admin" or (g.user["role"] == "teacher" and row["owner_id"] == uid()
                                          and not json.loads(row["config"])["personal"])


def manage(exam_id):
    row = exam_row(exam_id)
    if not manager(row):
        fail(403, "无权管理此考试")
    return row


def participant(row, user):
    return db().execute("SELECT 1 FROM participants WHERE exam_id=? AND user_id=?", (row["id"], user)).fetchone()


def accessible(exam_id):
    row = exam_row(exam_id)
    if not manager(row) and not participant(row, uid()):
        fail(404, "考试不存在")
    return row


def display_status(row):
    if row["state"] == "draft":
        return "草稿"
    if row["state"] == "cancelled":
        return "已归档"
    if row["published_at"]:
        return "成绩已发布"
    if now() < row["start"]:
        return "已发布"
    return "已结束" if now() >= row["end"] else "进行中"


def editable_config(row):
    return {**json.loads(row["config"]), "start": row["start"], "end": row["end"]}


def problem_weights(config):
    # Draft selection may pin a version. Drafts, submissions and browser routes use project IDs.
    weights_by_id = {}
    for ref, weight in zip(config["problemIds"], config["weights"]):
        project, _ = catalog.version_parts(ref, None)
        weights_by_id[project] = weights_by_id.get(project, 0) + weight
    return weights_by_id


def exam_data(row, include_files=True):
    data = editable_config(row)
    by_id = problem_weights(data)
    manages_exam = manager(row)
    open_paper = manages_exam or (row["state"] == "published" and now() >= row["start"])
    disclose_selection = open_paper or data["personal"]
    data.update(id=row["id"], problemCount=len(by_id), problemIds=list(by_id) if disclose_selection else [],
                weights=list(by_id.values()) if disclose_selection else [], status=display_status(row),
                published=bool(row["published_at"]), publishedAt=row["published_at"], rulesVersion="1")
    if manages_exam:
        data["participantIds"] = [v[0] for v in db().execute("SELECT user_id FROM participants WHERE exam_id=?", (row["id"],))]
    else:
        data.pop("selectedParticipants", None)
    if include_files and open_paper:
        data["snapshots"] = json.loads(row["snapshots"])
    return data


def build(data, personal):
    pids = data.get("problemIds")
    if (not isinstance(pids, list) or not 1 <= len(pids) <= 20
            or any(not isinstance(p, str) for p in pids) or len(set(pids)) != len(pids)):
        fail(422, "应选 1–20 道不重复的工程题")
    start, end = iso(data.get("start")), iso(data.get("end"))
    if start >= end or end <= now():
        fail(422, "请选择有效考试时段")
    room = None if personal else catalog.managed_class(data.get("classId") or string(data.get("className"), "班级", 100))
    name = "个人模拟 · 仅自己可见" if personal else room["name"]
    members = [uid()] if personal else catalog.class_roster(room["id"])
    roster = data.get("selectedParticipants")
    if not personal and roster is not None:
        if (not isinstance(roster, list) or not roster or any(not isinstance(u, str) for u in roster)
                or len(set(roster)) != len(roster) or not set(roster).issubset(members)):
            fail(422, "指定考生须来自当前班级且不能重复。")
        members = roster
    snaps = [catalog.get_problem(p) for p in pids]
    if personal and any(p["bank"] == "内置题库" for p in snaps):
        fail(422, "个人模拟请选择有权使用的私有题库")
    config = {"title": string(data.get("title"), "考试名称", 80), "className": name,
              "problemIds": pids, "weights": weights(data.get("weights"), len(pids)), "personal": personal,
              "model": string(data.get("model", "course-coder-v1"), "模型名称", 120),
              "leaderboard": bool(data.get("leaderboard")) and not personal}
    if room:
        config["classId"] = room["id"]
    public_board = data.get("publicLeaderboard", False)
    if type(public_board) is not bool:
        fail(422, "公开匿名榜设置须为布尔值")
    config["publicLeaderboard"] = public_board and config["leaderboard"] and not personal
    if not personal and roster is not None:
        config["selectedParticipants"] = roster
    for field, default, maximum in (("requests", 30, 500), ("tokens", 30000, 2000000), ("submissionLimit", 5, 100), ("publicRunLimit", 100, 500)):
        val = data.get(field, default)
        if type(val) is not int or not 1 <= val <= maximum:
            fail(422, f"{field} 超出范围")
        config[field] = val
    for field, choices in (("aiContext", ("项目文件", "当前文件")), ("aiMode", ("对话与代码建议", "仅分析建议"))):
        value = data.get(field, choices[0])
        if value not in choices:
            fail(422, "AI 规则无效")
        config[field] = value
    deliverables = data.get("deliverables", ["项目代码与测试", "验证说明"])
    if not isinstance(deliverables, list) or len(deliverables) > 20:
        fail(422, "交付物格式无效")
    config["deliverables"] = [string(d, "交付物", 120) for d in deliverables]
    return config, start, end, snaps, members


def members_snapshot(eid, members):
    db().executemany("INSERT INTO participants VALUES(?,?)", [(eid, m) for m in members])


@bp.route("/exams", methods=["GET", "POST"])
@bp.post("/mock-exams")
def exams():
    if request.method == "GET":
        rows = db().execute("""SELECT e.* FROM exams e WHERE (e.owner_id=? AND ?='teacher') OR ?='admin'
            OR EXISTS(SELECT 1 FROM participants p WHERE p.exam_id=e.id AND p.user_id=?) ORDER BY e.start DESC""",
                            (uid(), g.user["role"], g.user["role"], uid())).fetchall()
        return ok([exam_data(row, False) for row in rows])
    data = body()
    personal = request.path.endswith("/mock-exams") or data.get("personal") is True
    if not personal:
        require("teacher", "admin")
    lock()
    config, start, end, snaps, members = build(data, personal)
    eid = ident("EX")
    state = "published" if personal or data.get("status") in ("已发布", "进行中") else "draft"
    if state == "published" and not members:
        fail(422, "考试名单为空，请先添加班级成员")
    db().execute("INSERT INTO exams VALUES(?,?,?,?,?,?,?,NULL)",
                 (eid, uid(), start, end, state, obj(config), obj(snaps)))
    if state == "published":
        members_snapshot(eid, members)
    audit("创建考试", config["title"])
    return ok(exam_data(exam_row(eid)), 201)


@bp.route("/exams/<eid>", methods=["GET", "PATCH"])
def exam_detail(eid):
    if request.method == "GET":
        row = accessible(eid)
        return ok(exam_data(row))
    lock()
    row = manage(eid)
    if row["state"] != "draft":
        fail(409, "仅草稿可修改")
    previous, changes = editable_config(row), body()
    previous_ids = list(problem_weights(previous))
    if changes.get("problemIds") == previous_ids and len(previous["problemIds"]) == len(previous_ids):
        changes.pop("problemIds")  # An unchanged browser selection retains the draft's pinned versions.
    if "className" in changes and changes["className"] != previous["className"] and "classId" not in changes:
        previous.pop("classId", None)
    cfg, start, end, snaps, _ = build({**previous, **changes}, False)
    db().execute("UPDATE exams SET config=?,start=?,end=?,snapshots=? WHERE id=?", (obj(cfg), start, end, obj(snaps), eid))
    return ok(exam_data(exam_row(eid)))


@bp.post("/exams/<eid>/publish")
def publish(eid):
    lock()
    row = manage(eid)
    if row["state"] != "draft":
        fail(409, "仅草稿可以发布")
    cfg, _, _, snaps, members = build(editable_config(row), False)
    if not members:
        fail(422, "考试名单为空")
    members_snapshot(eid, members)
    db().execute("UPDATE exams SET state='published',config=?,snapshots=? WHERE id=?", (obj(cfg), obj(snaps), eid))
    audit("发布考试", cfg["title"])
    return ok(exam_data(exam_row(eid)))


@bp.post("/exams/<eid>/cancel")
def cancel(eid):
    lock()
    row = manage(eid)
    if row["state"] != "draft" and (row["state"] != "published" or now() >= row["start"]):
        fail(409, "仅可取消尚未开考的场次")
    audit("取消考试", string(body().get("reason"), "原因", 1000))
    db().execute("UPDATE exams SET state='cancelled' WHERE id=?", (eid,))
    return ok(exam_data(exam_row(eid)))


@bp.get("/exams/<eid>/clock")
def clock(eid):
    row = accessible(eid)
    return ok({"server_time": now(), "deadline": row["end"]})
