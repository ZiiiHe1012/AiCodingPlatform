"""Staff-only account administration and audit history."""
from flask import Blueprint, g, request

from .auth import BUILTIN_ACCOUNTS
from .core import audit, body, db, fail, ok, require

bp = Blueprint("catalog", __name__)
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
