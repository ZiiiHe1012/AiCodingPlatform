import json
import re
import secrets
import sqlite3
import time

import click
from flask.cli import with_appcontext
from flask import Blueprint, current_app, g, make_response, request
from werkzeug.security import check_password_hash, generate_password_hash

from .core import audit, body, db, digest, fail, ident, now, obj, ok, string, uid

bp = Blueprint("auth", __name__)
COOKIE = "codelab_session"
BUILTIN_ACCOUNTS = {
    "builtin-admin": ("admin", "admin123", "超级管理员", "admin"),
    "builtin-teacher": ("teacher", "teacher123", "教师", "teacher"),
}


def init_db(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT NOT NULL UNIQUE COLLATE NOCASE,
      nickname TEXT NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'student',
      enabled INTEGER NOT NULL DEFAULT 1,revision INTEGER NOT NULL DEFAULT 1,
      profile TEXT NOT NULL DEFAULT '{}',joined_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),
      revision INTEGER NOT NULL,expires INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS login_limits(name TEXT PRIMARY KEY,count INTEGER NOT NULL,since INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS audits(id TEXT PRIMARY KEY,action TEXT,reason TEXT,time TEXT,actor TEXT,user_id TEXT);
    """)
    conn.execute("BEGIN IMMEDIATE")
    for user_id, (username, password, nickname, role) in BUILTIN_ACCOUNTS.items():
        previous = conn.execute("SELECT id FROM users WHERE username=? AND id<>?", (username, user_id)).fetchone()
        if previous:
            # Keep the old account and its work separate from the privileged identity.
            alias = f"{username}_previous"
            suffix = 1
            while conn.execute("SELECT 1 FROM users WHERE username=?", (alias,)).fetchone():
                suffix += 1
                alias = f"{username}_previous{suffix}"
            conn.execute("UPDATE users SET username=?,revision=revision+1 WHERE id=?", (alias, previous[0]))
            conn.execute("INSERT INTO audits(id,action,reason,time,actor,user_id) VALUES(?,?,?,?,?,?)",
                         (ident("AUD"), "迁移保留用户名", f"{username} → {alias}", now(), "系统", previous[0]))
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            conn.execute("""INSERT INTO users(id,username,password_hash,nickname,role,joined_at)
                            VALUES(?,?,?,?,?,?)""",
                         (user_id, username, generate_password_hash(password), nickname, role, now()))
        elif row["username"] != username or row["role"] != role or not row["enabled"]:
            conn.execute("""UPDATE users SET username=?,role=?,enabled=1,revision=revision+1
                            WHERE id=?""", (username, role, user_id))
        else:
            continue
        conn.execute("DELETE FROM login_limits WHERE name=?", (username,))
    conn.commit()


def accounts_using_demo_passwords():
    pending = []
    for user_id, (username, _, _, _) in BUILTIN_ACCOUNTS.items():
        row = db().execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None or any(check_password_hash(row["password_hash"], account[1])
                              for account in BUILTIN_ACCOUNTS.values()):
            pending.append(username)
    return pending


def profile(row):
    return {**{"bio": "", "className": "", "skills": [], "avatar": "blue"}, **json.loads(row["profile"]),
            **{k: row[k] for k in ("id", "username", "nickname", "role")}, "joinedAt": row["joined_at"], "demo": False}


def authenticate():
    g.user = None
    if request.cookies.get(COOKIE):
        g.user = db().execute("""SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
           WHERE token=? AND expires>? AND s.revision=u.revision AND u.enabled=1""",
                              (digest(request.cookies[COOKIE]), int(time.time()))).fetchone()
    if not g.user:
        fail(401, "请登录后继续")


def create_user(username, password, nickname, role="student"):
    if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_]{4,32}", username):
        fail(422, "用户名需为 4–32 个字母、数字或下划线")
    validate_password(password)
    string(nickname, "昵称", 24)
    identifier = ident("U")
    try:
        db().execute("INSERT INTO users(id,username,password_hash,nickname,role,joined_at) VALUES(?,?,?,?,?,?)",
                     (identifier, username.lower(), generate_password_hash(password), nickname.strip(), role, now()))
    except sqlite3.IntegrityError:
        fail(409, "用户名已被使用")
    return db().execute("SELECT * FROM users WHERE id=?", (identifier,)).fetchone()


def validate_password(password):
    if not isinstance(password, str) or not password.strip() or not 8 <= len(password) <= 64:
        fail(422, "密码长度应为 8–64 个字符")


def session_response(user, remember=False, status=200):
    token = secrets.token_urlsafe(32)
    duration = (30 if remember else 1) * 86400
    db().execute("DELETE FROM sessions WHERE expires<=? OR token=?",
                 (int(time.time()), digest(request.cookies.get(COOKIE, ""))))
    db().execute("INSERT INTO sessions VALUES(?,?,?,?)",
                 (digest(token), user["id"], user["revision"], int(time.time()) + duration))
    response = make_response(ok(profile(user), status))
    response.set_cookie(COOKIE, token, max_age=duration if remember else None, httponly=True,
                        secure=current_app.config["COOKIE_SECURE"], samesite="Lax", path="/")
    return response


@bp.post("/auth/register")
def register():
    data = body()
    return session_response(create_user(data.get("username"), data.get("password"), data.get("nickname")),
                            data.get("remember") is True, 201)


@bp.post("/auth/login")
def login():
    data = body()
    username = string(data.get("username"), "用户名", 32).strip().lower()
    password = string(data.get("password"), "密码", 64)
    current = int(time.time())
    item = db().execute("SELECT * FROM login_limits WHERE name=?", (username,)).fetchone()
    if item and item["since"] > current - 600 and item["count"] >= 5:
        fail(429, "登录尝试过多，请稍后再试")
    row = db().execute("SELECT * FROM users WHERE username=? AND enabled=1", (username,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        db().execute("""INSERT INTO login_limits VALUES(?,1,?) ON CONFLICT(name) DO UPDATE SET
            count=CASE WHEN since<=excluded.since-600 THEN 1 ELSE count+1 END,
            since=CASE WHEN since<=excluded.since-600 THEN excluded.since ELSE since END""", (username, current))
        db().commit()
        fail(401, "用户名或密码不正确")
    db().execute("DELETE FROM login_limits WHERE name=?", (username,))
    return session_response(row, data.get("remember") is True)


@bp.post("/auth/logout")
def logout():
    db().execute("DELETE FROM sessions WHERE token=?", (digest(request.cookies.get(COOKIE, "")),))
    response = make_response(ok(None))
    response.delete_cookie(COOKIE)
    return response


@bp.route("/users/me", methods=["GET", "PATCH"])
def me():
    if request.method == "PATCH":
        data = body()
        values = json.loads(g.user["profile"])
        for field, limit in (("bio", 500), ("className", 80), ("avatar", 160)):
            if field in data:
                values[field] = string(data[field], field, limit, optional=True)
        if "skills" in data:
            if not isinstance(data["skills"], list) or len(data["skills"]) > 20:
                fail(422, "技术标签最多 20 项")
            values["skills"] = [string(v, "标签", 32) for v in data["skills"]]
        nickname = string(data.get("nickname", g.user["nickname"]), "昵称", 24).strip()
        db().execute("UPDATE users SET nickname=?,profile=? WHERE id=?", (nickname, obj(values), uid()))
        g.user = db().execute("SELECT * FROM users WHERE id=?", (uid(),)).fetchone()
    return ok(profile(g.user))


def replace_password(user_id, new_password):
    db().execute("UPDATE users SET password_hash=?,revision=revision+1 WHERE id=?",
                 (generate_password_hash(new_password), user_id))


@bp.post("/users/me/password")
def password():
    data = body()
    validate_password(data.get("new_password"))
    if not check_password_hash(g.user["password_hash"], string(data.get("old_password"), "旧密码", 64)):
        fail(403, "旧密码不正确")
    if uid() in BUILTIN_ACCOUNTS and any(data["new_password"] == item[1] for item in BUILTIN_ACCOUNTS.values()):
        fail(422, "请为课堂账号设置自选密码，避免使用公开的演示密码")
    replace_password(uid(), data["new_password"])
    audit("修改密码", "旧会话已失效")
    return logout()


@click.command("create-user")
@click.argument("username")
@click.option("--role", type=click.Choice(["student", "teacher", "admin"]), required=True)
@click.option("--nickname", prompt="显示名称")
@click.password_option()
@with_appcontext
def create_user_command(username, role, nickname, password):
    """Create an account on this installation."""
    from werkzeug.exceptions import HTTPException
    try:
        user = create_user(username, password, nickname, role)
        db().commit()
    except HTTPException as exc:
        raise click.ClickException(exc.description) from exc
    click.echo(f"{user['username']} ({role})")
