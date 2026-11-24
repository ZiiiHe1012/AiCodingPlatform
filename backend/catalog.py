"""Account administration and classroom membership."""
import secrets
import sqlite3
from flask import Blueprint, g, request

from .auth import BUILTIN_ACCOUNTS
from .core import audit, body, db, fail, ident, now, ok, require, uid

bp = Blueprint("catalog", __name__)
def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS classes (
          id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, teacher_id TEXT NOT NULL REFERENCES users(id),
          code TEXT NOT NULL UNIQUE, archived INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS memberships (
          class_id TEXT NOT NULL REFERENCES classes(id), user_id TEXT NOT NULL REFERENCES users(id),
          joined TEXT NOT NULL, PRIMARY KEY(class_id,user_id));
    """)
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
