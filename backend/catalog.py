"""Versioned engineering projects, private banks and class access."""
import json
import math
import secrets
import sqlite3
from pathlib import Path

from flask import Blueprint, g, request

from .auth import BUILTIN_ACCOUNTS
from .core import audit, body, db, fail, files, ident, now, obj, ok, require, uid

bp = Blueprint("catalog", __name__)
BUILTIN = "builtin"
DEFAULT_BANK = "我的工程实践题库"
WEIGHTS = [40, 15, 15, 10, 10, 10]
TASK_TYPES = ("需求实现", "代码理解", "缺陷修复", "工程重构", "算法实现", "功能补全", "测试编写")
OWN_BANK = """(b.owner_id=? AND (b.class_id IS NULL OR EXISTS (
    SELECT 1 FROM users u JOIN classes c ON c.id=b.class_id
    WHERE u.id=b.owner_id AND (u.role='admin' OR (u.role='teacher' AND c.teacher_id=u.id)))))"""
READ_BANK = f"""(b.id='builtin' OR {OWN_BANK} OR (
    b.class_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM memberships m WHERE m.class_id=b.class_id AND m.user_id=?)))"""


def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS classes (
          id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, teacher_id TEXT NOT NULL REFERENCES users(id),
          code TEXT NOT NULL UNIQUE, archived INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS memberships (
          class_id TEXT NOT NULL REFERENCES classes(id), user_id TEXT NOT NULL REFERENCES users(id),
          joined TEXT NOT NULL, PRIMARY KEY(class_id,user_id));
        CREATE TABLE IF NOT EXISTS banks (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_id TEXT REFERENCES users(id),
          class_id TEXT REFERENCES classes(id), UNIQUE(owner_id,name));
        CREATE TABLE IF NOT EXISTS projects (
          id TEXT PRIMARY KEY, bank_id TEXT NOT NULL REFERENCES banks(id));
        CREATE TABLE IF NOT EXISTS problem_versions (
          problem_id TEXT NOT NULL REFERENCES projects(id), seq INTEGER NOT NULL, version TEXT NOT NULL,
          status TEXT NOT NULL, metadata TEXT NOT NULL, private_tests TEXT NOT NULL DEFAULT '{}',
          reference_files TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(problem_id,version), UNIQUE(problem_id,seq));
        CREATE INDEX IF NOT EXISTS versions_by_status ON problem_versions(status,problem_id,seq);
        CREATE TABLE IF NOT EXISTS project_imports (
          id TEXT PRIMARY KEY, bank_id TEXT NOT NULL REFERENCES banks(id),
          owner_id TEXT NOT NULL REFERENCES users(id), filename TEXT NOT NULL, contents BLOB,
          validation_id TEXT UNIQUE, result TEXT, created_project TEXT REFERENCES projects(id));
    """)
    conn.execute("INSERT OR IGNORE INTO banks(id,name) VALUES(?,?)", (BUILTIN, "内置题库"))
    for p in json.loads(Path(__file__).with_name("catalog_seed.json").read_text(encoding="utf-8")):
        conn.execute("INSERT OR IGNORE INTO projects VALUES(?,?)", (p["id"], BUILTIN))
        conn.execute("""INSERT OR IGNORE INTO problem_versions
            (problem_id,seq,version,status,metadata) VALUES(?,2,?,?,?)""",
                     (p["id"], p["version"], p["status"], obj(p)))
    conn.commit()


def text_field(value, label, maximum=200):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        fail(400, f"{label}不能为空，最多 {maximum} 字")
    return value.strip()


def reserve_write():
    """Read ownership, state and the version counter in the same write transaction."""
    if not db().in_transaction:
        db().execute("BEGIN IMMEDIATE")


def pagination():
    try:
        page = int(request.args.get("page", "1"))
        size = int(request.args.get("page_size", "20"))
        if page <= 0 or not 1 <= size <= 100:
            raise ValueError
    except ValueError:
        fail(400, "分页参数无效，每页应为 1–100 条")
    return page, size


def page_of(items):
    page, size = pagination()
    start = (page - 1) * size
    return {"items": items[start:start + size], "total": len(items), "page": page, "page_size": size}


def owned_bank(bank_ref):
    if not isinstance(bank_ref, str) or len(bank_ref) > 100:
        fail(400, "请选择所属题库")
    current = uid()
    row = db().execute(f"""SELECT b.* FROM banks b WHERE (b.id=? OR b.name=?)
           AND ({OWN_BANK} OR b.id='builtin') ORDER BY (b.id=?) DESC LIMIT 1""",
                       (bank_ref, bank_ref, current, bank_ref)).fetchone()
    if not row:
        fail(404, "题库不存在或无权管理")
    if row["id"] == BUILTIN:
        require("admin")
    return row


def managed_bank_by_project(problem_id):
    row = db().execute("SELECT bank_id FROM projects WHERE id=?", (problem_id,)).fetchone()
    if not row:
        fail(404, "题目不存在")
    return owned_bank(row["bank_id"])


def version_parts(problem_id, version):
    if version is None and "@" in problem_id:
        return problem_id.rsplit("@", 1)
    return problem_id, version


def problem_dict(row):
    data = json.loads(row["metadata"])
    data.update(id=row["problem_id"], version=row["version"], status=row["status"],
                bank=row["bank_name"], bank_id=row["bank_id"],
                problem_version_id=f"{row['problem_id']}@{row['version']}")
    return data


PROJECT_QUERY = """SELECT v.*, b.name bank_name, b.id bank_id, b.owner_id
                   FROM problem_versions v JOIN projects p ON p.id=v.problem_id
                   JOIN banks b ON b.id=p.bank_id"""


def get_project_row(problem_id, version=None, manage=False):
    problem_id, version = version_parts(problem_id, version)
    user_id = uid()
    sql = PROJECT_QUERY + " WHERE p.id=? AND " + READ_BANK
    args = [problem_id, user_id, user_id]
    if version:
        sql += " AND v.version=?"
        args.append(version)
    if manage:
        sql += f" AND (v.status='已发布' OR {OWN_BANK} OR (b.id='builtin' AND ?='admin'))"
        args += [user_id, g.user["role"]]
    else:
        sql += " AND v.status='已发布'"
    row = db().execute(sql + " ORDER BY v.seq DESC LIMIT 1", args).fetchone()
    if not row:
        fail(404, "题目版本不存在或当前不可用")
    return row


def get_problem(problem_id, version=None):
    return problem_dict(get_project_row(problem_id, version))


def get_private_tests(problem_id, version):
    row = db().execute("SELECT private_tests FROM problem_versions WHERE problem_id=? AND version=?",
                       (problem_id, version)).fetchone()
    return json.loads(row["private_tests"]) if row else {}


def writable_file(path):
    parts = {part.casefold() for part in path.split("/")}
    return not parts.intersection({"hidden", "reference", "private", ".git", "__pycache__", "node_modules"})


def public_metadata(raw):
    """Copy only candidate-facing fields. Never reflect author-only manifest fields."""
    allowed = ("title", "type", "difficulty", "description", "stack", "repository", "entryFile",
               "source", "duration", "tags", "requirements", "constraints", "deliverables", "weights")
    data = {key: raw[key] for key in allowed if key in raw}
    for key, default in (("tags", []), ("requirements", []), ("constraints", []),
                         ("deliverables", []), ("weights", list(WEIGHTS))):
        data.setdefault(key, default)
    for key in ("title", "type", "difficulty", "description", "stack", "repository", "entryFile", "source"):
        data.setdefault(key, "")
        if not isinstance(data[key], str):
            fail(400, f"{key} 必须是文本")
    for key in ("tags", "requirements", "constraints", "deliverables"):
        if not isinstance(data[key], list) or not all(isinstance(s, str) for s in data[key]):
            fail(400, f"{key} 必须是文本数组")
    data.setdefault("duration", 60)
    if type(data["duration"]) is not int:
        fail(400, "duration 必须为整数")
    if not isinstance(data["weights"], list) or not all(type(w) in (int, float) and 0 <= w <= 100 and math.isfinite(w)
                                                       for w in data["weights"]):
        fail(400, "weights 必须是数值数组")
    acceptance = raw.get("acceptance", [])
    if not isinstance(acceptance, list) or not all(isinstance(a, dict) for a in acceptance):
        fail(400, "acceptance 必须是验收场景数组")
    data["acceptance"] = []
    for entry in acceptance:
        clean = {k: entry.get(k, "") for k in ("id", "scenario", "expected")}
        if not all(isinstance(s, str) for s in clean.values()):
            fail(400, "验收场景字段必须是文本")
        data["acceptance"].append(clean)
    commands = raw.get("commands", {})
    if not isinstance(commands, dict) or not all(isinstance(commands.get(k, ""), str)
                                                 for k in ("setup", "test", "start")):
        fail(400, "commands 必须是文本配置")
    data["commands"] = {k: commands.get(k, "") for k in ("setup", "test", "start")}
    limits = raw.get("evaluation", {})
    if not isinstance(limits, dict) or not all(type(limits.get(k, v)) is int
                                               for k, v in (("timeout", 10), ("memory", 512))):
        fail(400, "evaluation 资源限制必须为整数")
    data["evaluation"] = {"timeout": limits.get("timeout", 10), "memory": limits.get("memory", 512),
                          "network": "禁用"}
    data["files"] = files(raw["files"]) if raw.get("files") else {}
    if not all(writable_file(path) for path in data["files"]):
        fail(400, "公开模板不能包含保留的私有目录")
    data.update(solved=False, attempts=0, passRate=0)
    return data


def problems_with(data):
    """Return localized issues for an author to fix before publication."""
    issues = []
    def issue(field, message):
        issues.append({"file": "manifest.json", "field": field, "message": message, "severity": "error"})

    for key in ("title", "description", "stack", "repository", "source"):
        if not data.get(key, "").strip():
            issue(key, "不能为空")
    if data["type"] not in TASK_TYPES:
        issue("type", "未知的工程任务类型")
    if data["difficulty"] not in ("简单", "中等", "困难"):
        issue("difficulty", "无效的难度")
    if data["duration"] < 15:
        issue("duration", "建议时长至少15分钟")
    for key in ("requirements", "deliverables"):
        if not data[key] or not all(s.strip() for s in data[key]):
            issue(key, "应提供非空条目")
    cases = data["acceptance"]
    if not cases or any(not all(s.strip() for s in c.values()) for c in cases):
        issue("acceptance", "请填写验收编号、场景与预期")
    if len({c["id"] for c in cases}) != len(cases):
        issue("acceptance", "验收编号重复")
    if not data["files"].get(data["entryFile"], "").strip():
        issue("entryFile", "入口文件缺失或为空")
    if not any(p.startswith(("tests/", "test/")) and content.strip() for p, content in data["files"].items()):
        issue("files", "缺少公开测试")
    if len(data["weights"]) != 6 or any(w < 0 for w in data["weights"]) or not math.isclose(sum(data["weights"]), 100):
        issue("weights", "六维权重应非负且合计100")
    if not data["commands"]["test"].strip():
        issue("commands.test", "缺少测试命令")
    limits = data["evaluation"]
    if not (1 <= limits["timeout"] <= 120 and 128 <= limits["memory"] <= 1024):
        issue("evaluation", "时间应在1–120秒内，内存应在128–1024MB内")
    return issues


@bp.get("/problems")
def list_projects():
    current = uid()
    sql = PROJECT_QUERY + " WHERE " + READ_BANK
    args = [current, current]
    if request.args.get("manage") == "1":
        sql += f" AND (v.status='已发布' OR {OWN_BANK} OR (b.id='builtin' AND ?='admin'))"
        args += [current, g.user["role"]]
    else:
        sql += " AND v.status='已发布'"
    # Filter the latest visible version before reading its (possibly multi-MB) file map.
    ranked = sql.replace("SELECT v.*,", "SELECT ROW_NUMBER() OVER (PARTITION BY p.id ORDER BY v.seq DESC) rn, v.*,", 1)
    query = request.args
    page, size = pagination()
    current_only = """SELECT problem_id,COUNT(*) attempts,
                       MAX(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) solved,
                       AVG(CASE WHEN status='COMPLETED' THEN CASE WHEN json_extract(scores,'$[0]')=100 THEN 100.0 ELSE 0.0 END END) passRate
                       FROM submissions WHERE user_id=? AND exam_id IS NULL AND kind='practice' GROUP BY problem_id"""
    # The catalog never infers practice statistics from unpublished exam grades.
    filtered = " FROM (" + ranked + ") r LEFT JOIN (" + current_only + ") s ON s.problem_id=r.problem_id WHERE r.rn=1"
    args.append(current)
    keyword = (query.get("q") or query.get("keyword") or "").strip()
    if keyword:
        filtered += """ AND (instr(lower(r.problem_id||json_extract(metadata,'$.title')||
                         json_extract(metadata,'$.tags')||json_extract(metadata,'$.description')),lower(?))>0)"""
        args.append(keyword)
    for key in ("type", "difficulty", "stack"):
        if query.get(key):
            filtered += f" AND json_extract(metadata,'$.{key}')=?"
            args.append(query[key])
    if query.get("tag"):
        filtered += " AND EXISTS(SELECT 1 FROM json_each(metadata,'$.tags') WHERE value=?)"
        args.append(query["tag"])
    if query.get("bank"):
        filtered += " AND (r.bank_id=? OR r.bank_name=?)"
        args.extend([query["bank"], query["bank"]])
    if query.get("status"):
        filtered += " AND r.status=?"
        args.append(query["status"])
    if query.get("completion_status"):
        mode = query["completion_status"]
        if mode not in ("已完成", "未开始", "进行中"):
            fail(400, "无效的完成状态")
        filtered += {"已完成": " AND coalesce(s.solved,0)=1",
                     "未开始": " AND coalesce(s.attempts,0)=0",
                     "进行中": " AND s.attempts>0 AND s.solved=0"}[mode]
    if query.get("solved"):
        if query["solved"].lower() not in ("true", "false"):
            fail(400, "solved 应为布尔值")
        filtered += " AND coalesce(s.solved,0)=?"
        args.append(query["solved"].lower() == "true")
    total = db().execute("SELECT count(*)" + filtered, args).fetchone()[0]
    rows = db().execute("SELECT r.*,s.attempts,s.solved,s.passRate" + filtered +
                        " ORDER BY r.problem_id LIMIT ? OFFSET ?", [*args, size, (page-1)*size])
    items = [{**problem_dict(r), "attempts": r["attempts"] or 0, "solved": bool(r["solved"]),
              "passRate": round(r["passRate"] or 0, 2)} for r in rows]
    return ok({"items": items, "total": total, "page": page, "page_size": size})

@bp.get("/problems/<project>")
def detail(project):
    row = get_project_row(project, request.args.get("version"), request.args.get("manage") == "1")
    return ok(problem_dict(row))


def store_project(bank, data, private=None, reference=None):
    project = ident("E")
    db().execute("INSERT INTO projects VALUES(?,?)", (project, bank["id"]))
    db().execute("INSERT INTO problem_versions VALUES(?,1,'v1.0','草稿',?,?,?)",
                 (project, obj(data), obj(private or {}), obj(reference or {})))
    return project


@bp.post("/problems")
def create_project():
    reserve_write()
    raw = body()
    bank_ref = raw.get("bank_id") or raw.get("bank")
    bank = owned_bank(default_bank() if not bank_ref or bank_ref == DEFAULT_BANK else bank_ref)
    data = public_metadata(raw)
    text_field(data.get("title"), "题名", 120)
    private, reference = packages.author_materials(raw)
    project = store_project(bank, data, private, reference)
    audit("创建工程任务", project)
    db().commit()
    return ok(problem_dict(get_project_row(project, manage=True)), 201)


@bp.post("/problems/<project>/versions")
def new_version(project):
    reserve_write()
    managed_bank_by_project(project)
    previous = get_project_row(project, manage=True)
    raw = body()
    if raw.get("version") and raw["version"] != previous["version"]:
        fail(409, "题目已有更新版本，请刷新")
    data = public_metadata({**json.loads(previous["metadata"]), **raw})
    text_field(data.get("title"), "题名", 120)
    private, reference = packages.author_materials(raw, previous)
    seq = previous["seq"] + 1
    version = f"v{seq}.0"
    db().execute("INSERT INTO problem_versions VALUES(?,?,?,'草稿',?,?,?)",
                 (project, seq, version, obj(data), obj(private), obj(reference)))
    audit("创建题目版本", f"{project}@{version}")
    db().commit()
    return ok(problem_dict(get_project_row(project, version, True)), 201)


@bp.post("/problem-versions/<ref>/<action>")
def change_version(ref, action):
    if action not in ("precheck", "publish", "unpublish"):
        fail(404, "操作不存在")
    project, version = version_parts(ref, None)
    reserve_write()
    managed_bank_by_project(project)
    row = get_project_row(project, version, True)
    key = project, row["version"]
    if action == "precheck":
        data = json.loads(row["metadata"])
        issues = problems_with(data)
        if not issues and row["status"] == "草稿":
            db().execute("UPDATE problem_versions SET status='预检通过' WHERE problem_id=? AND version=?", key)
        db().commit()
        return ok({"validation_id": "@".join(key), "valid": not issues, "items": issues})
    if action == "publish":
        if row["status"] != "预检通过":
            fail(409, "请先完成该题目版本的预检")
        db().execute("UPDATE problem_versions SET status='已下架' WHERE problem_id=? AND status='已发布'", (project,))
        status, reason = "已发布", "发布经预检的不可变版本"
    else:
        if row["status"] != "已发布":
            fail(409, "仅已发布的版本可下架")
        status, reason = "已下架", text_field(body().get("reason"), "下架原因", 1000)
    db().execute("UPDATE problem_versions SET status=? WHERE problem_id=? AND version=?", (status, *key))
    audit(status + "工程任务", f"{ref} {reason}")
    db().commit()
    return ok(problem_dict(get_project_row(project, row["version"], True)))


def default_bank():
    user_id = uid()
    bank_id = "personal-" + user_id
    db().execute("INSERT OR IGNORE INTO banks(id,name,owner_id) VALUES(?,?,?)",
                 (bank_id, DEFAULT_BANK, user_id))
    return bank_id


def bank_dict(row):
    return {**dict(row), "visibility": "public" if row["id"] == BUILTIN else
            ("class" if row["class_id"] else "private")}


@bp.get("/banks")
def list_banks():
    default_bank()
    current = uid()
    rows = db().execute("SELECT b.* FROM banks b WHERE " + READ_BANK + " ORDER BY b.id='builtin',b.name",
                        (current, current)).fetchall()
    db().commit()
    return ok([bank_dict(r) for r in rows])


@bp.post("/banks")
def create_bank():
    reserve_write()
    current = uid()
    raw = body()
    name = text_field(raw.get("name"), "题库名称", 80)
    if name in (DEFAULT_BANK, "内置题库"):
        fail(409, "题库名称已使用")
    visibility = raw.get("visibility", "private")
    if visibility not in ("private", "class"):
        fail(400, "请选择私有或本人任课班级")
    class_id = None
    if visibility == "class":
        class_id = managed_class(raw.get("class_id"))["id"]
    new_id = ident("bank")
    try:
        db().execute("INSERT INTO banks VALUES(?,?,?,?)", (new_id, name, current, class_id))
    except sqlite3.IntegrityError:
        fail(409, "题库名称重复")
    audit("创建题库", name)
    db().commit()
    return ok(bank_dict(owned_bank(new_id)), 201)


def managed_class(ref):
    require("teacher", "admin")
    if not isinstance(ref, str):
        fail(400, "请提供班级名称或编号")
    row = db().execute("SELECT * FROM classes WHERE id=? OR name=? ORDER BY (id=?) DESC LIMIT 1",
                       (ref, ref, ref)).fetchone()
    if not row or (g.user["role"] != "admin" and row["teacher_id"] != uid()):
        fail(404, "班级不存在或无权管理")
    if row["archived"]:
        fail(409, "班级已归档")
    return row


def class_roster(class_id):
    return [r[0] for r in db().execute("""SELECT m.user_id FROM memberships m
               JOIN users u ON u.id=m.user_id WHERE m.class_id=? AND u.enabled=1
               ORDER BY m.user_id""", (class_id,))]


def classroom(row):
    manager = g.user["role"] == "admin" or (g.user["role"] == "teacher" and row["teacher_id"] == uid())
    teacher = db().execute("SELECT nickname FROM users WHERE id=?", (row["teacher_id"],)).fetchone()[0]
    members = db().execute("""SELECT u.id,u.nickname name,m.joined FROM memberships m JOIN users u
                  ON u.id=m.user_id WHERE m.class_id=? ORDER BY m.joined,u.id""", (row["id"],)).fetchall()
    return {"id": row["id"], "name": row["name"], "teacher": teacher, "teacher_id": row["teacher_id"],
            "code": row["code"] if manager else "", "archived": bool(row["archived"]),
            "memberCount": len(members), "members": [dict(r) for r in members if manager or r["id"] == uid()]}


def invite_code():
    return secrets.token_hex(5).upper()


@bp.get("/classes")
def list_classes():
    current = uid()
    rows = db().execute("""SELECT * FROM classes c WHERE (c.teacher_id=? AND ?='teacher') OR ?='admin' OR EXISTS
           (SELECT 1 FROM memberships m WHERE m.class_id=c.id AND m.user_id=?) ORDER BY c.name""",
                        (current, g.user["role"], g.user["role"], current))
    return ok([classroom(r) for r in rows])


@bp.post("/classes")
def create_class():
    require("teacher", "admin")
    name = text_field(body().get("name"), "班级名称", 60)
    class_id = ident("class")
    try:
        db().execute("INSERT INTO classes(id,name,teacher_id,code) VALUES(?,?,?,?)",
                     (class_id, name, uid(), invite_code()))
    except sqlite3.IntegrityError:
        fail(409, "班级名称重复")
    audit("创建班级", name)
    db().commit()
    return ok(classroom(managed_class(class_id)), 201)


@bp.patch("/classes/<class_id>")
def update_class(class_id):
    reserve_write()
    room = managed_class(class_id)
    raw = body()
    name = text_field(raw.get("name", room["name"]), "班级名称", 60)
    archived = raw.get("archived", bool(room["archived"]))
    if not isinstance(archived, bool):
        fail(400, "archived 应为布尔值")
    try:
        db().execute("UPDATE classes SET name=?, archived=? WHERE id=?", (name, archived, class_id))
    except sqlite3.IntegrityError:
        fail(409, "班级名称重复")
    audit("更新班级", f"{class_id} {name} 归档={archived}")
    db().commit()
    return ok(classroom(db().execute("SELECT * FROM classes WHERE id=?", (class_id,)).fetchone()))


@bp.post("/classes/<class_id>/invitation/reset")
def reset_invitation(class_id):
    reserve_write()
    managed_class(class_id)
    db().execute("UPDATE classes SET code=? WHERE id=?", (invite_code(), class_id))
    audit("重置邀请码", class_id)
    db().commit()
    return ok(classroom(managed_class(class_id)))


def invited():
    uid()
    code = text_field(body().get("code"), "邀请码", 32).upper()
    room = db().execute("SELECT * FROM classes WHERE code=? AND archived=0", (code,)).fetchone()
    if not room:
        fail(404, "邀请码无效或班级已归档")
    return room


@bp.post("/classes/invitations/preview")
def preview_class():
    room = invited()
    teacher = db().execute("SELECT nickname FROM users WHERE id=?", (room["teacher_id"],)).fetchone()[0]
    return ok({"class_name": room["name"], "teacher_nickname": teacher})


@bp.post("/classes/join")
def join_class():
    reserve_write()
    room = invited()
    db().execute("""INSERT OR IGNORE INTO memberships
               SELECT id,?,? FROM classes WHERE id=? AND code=? AND archived=0""",
                 (uid(), now(), room["id"], room["code"]))
    joined = db().execute("SELECT 1 FROM memberships WHERE class_id=? AND user_id=?", (room["id"], uid())).fetchone()
    if not joined:
        fail(409, "邀请码已更新")
    db().commit()
    return ok(classroom(room))


@bp.post("/classes/<class_id>/members/import")
def import_members(class_id):
    reserve_write()
    managed_class(class_id)
    members = body().get("members")
    if not isinstance(members, list) or not 1 <= len(members) <= 1000:
        fail(400, "名单应包含1至1000行")
    users, errors = [], []
    for i, entry in enumerate(members, start=1):
        fields = entry.split(",") if isinstance(entry, str) else []
        if len(fields) not in (1, 2) or not all(f.strip() for f in fields):
            errors.append({"line": i, "message": "请填写有效的用户编号或用户名，可附带逗号和昵称"})
            continue
        ref = fields[0].strip()
        user = db().execute("SELECT id FROM users WHERE (id=? OR username=?) AND enabled=1", (ref, ref)).fetchone()
        if user:
            users.append(user[0])
        else:
            errors.append({"line": i, "message": "不存在的用户或账户已停用"})
    if errors:
        return ok({"imported": 0, "duplicates": 0, "errors": errors})
    imported = 0
    for member in users:
        imported += db().execute("INSERT OR IGNORE INTO memberships VALUES(?,?,?)",
                                 (class_id, member, now())).rowcount
    audit("导入班级成员", f"{class_id} 新增{imported}人")
    db().commit()
    return ok({"imported": imported, "duplicates": len(users)-imported, "errors": []})


@bp.delete("/classes/<class_id>/members/<member>")
def remove_member(class_id, member):
    reserve_write()
    managed_class(class_id)
    db().execute("DELETE FROM memberships WHERE class_id=? AND user_id=?", (class_id, member))
    audit("移除班级成员", f"{class_id} {member}")
    db().commit()
    return ok({"removed": member})


@bp.get("/admin/users")
def admin_users():
    require("admin")
    q = "%" + request.args.get("q", "") + "%"
    rows = db().execute("""SELECT id,username,nickname,nickname name,role,enabled FROM users
         WHERE id LIKE ? OR nickname LIKE ? OR username LIKE ? ORDER BY username""", (q,q,q))
    return ok(page_of([{**dict(r), "enabled": bool(r["enabled"])} for r in rows]))


@bp.patch("/admin/users/<user_id>/<attribute>")
def change_account(user_id, attribute):
    require("admin")
    raw = body()
    reason = text_field(raw.get("reason"), "变更原因", 1000)
    if attribute == "role" and raw.get("role") in ("student", "teacher", "admin"):
        column, value = "role", raw["role"]
    elif attribute == "status" and type(raw.get("enabled")) is bool:
        column, value = "enabled", raw["enabled"]
    else:
        fail(400, "无效的角色或账户状态")
    # Serialize the last-admin check with the mutation, including concurrent demotions.
    reserve_write()
    before = db().execute("SELECT role,enabled FROM users WHERE id=?", (user_id,)).fetchone()
    if not before:
        fail(404, "用户不存在")
    if before[column] != value:
        if user_id in BUILTIN_ACCOUNTS:
            fail(409, "内置账户的身份和启用状态固定")
        if before["role"] == "admin" and before["enabled"] and db().execute(
                "SELECT count(*) FROM users WHERE role='admin' AND enabled=1").fetchone()[0] == 1:
            fail(409, "不能禁用或降级最后一个有效管理员")
        db().execute(f"UPDATE users SET {column}=?,revision=revision+1 WHERE id=?", (value, user_id))
        db().execute("UPDATE access_keys SET revoked=1 WHERE user_id=? AND revoked=0", (user_id,))
        audit("变更用户权限", f"{user_id} {column} {before[column]} → {value}。{reason}")
    db().commit()
    return ok({"id": user_id, column: value})


@bp.get("/admin/audits")
def list_audits():
    require("admin")
    rows = db().execute("SELECT id,action,reason,time,actor FROM audits ORDER BY time DESC,rowid DESC")
    return ok(page_of([dict(r) for r in rows]))


# Import route definitions after the catalog helpers they use.
from . import packages  # noqa: E402,F401
