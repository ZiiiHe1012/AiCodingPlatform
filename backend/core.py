"""Shared SQLite connection, authenticated actor and JSON contract."""
import hashlib
import json
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import PureWindowsPath

from flask import abort, current_app, g, jsonify, request


def db():
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        g.db = conn
    return g.db


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def ident(prefix):
    return f"{prefix}-{secrets.token_hex(12)}"


def obj(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def fail(status, message):
    abort(status, description=message)


def ok(data=None, status=200):
    return jsonify(code="OK", message="成功", data=data, request_id=g.request_id), status


def body():
    data = request.get_json()
    if not isinstance(data, dict):
        fail(400, "请求体必须是 JSON 对象")
    return data


def uid():
    return g.user["id"]


def require(*roles):
    if g.user is None:
        fail(401, "请先登录")
    if roles and g.user["role"] not in roles:
        fail(403, "当前账户没有此操作权限")


def audit(action, reason):
    db().execute("INSERT INTO audits(id,action,reason,time,actor,user_id) VALUES(?,?,?,?,?,?)",
                 (ident("AUD"), action, reason, now(), g.user["nickname"], uid()))


def files(value):
    if not isinstance(value, dict) or not 1 <= len(value) <= 100:
        fail(422, "工程应包含 1–100 个文本文件")
    size, names = 0, set()
    for path, content in value.items():
        if not isinstance(path, str) or not isinstance(content, str):
            fail(422, "工程文件内容必须是文本")
        parts = path.split("/")
        if (not path or len(path) > 240 or re.search(r'[\\:*?"<>|\x00-\x1f]', path)
                or any(part in ("", ".", "..") or part.endswith((" ", "."))
                       or PureWindowsPath(part).is_reserved() for part in parts)):
            fail(422, "工程包含无效的相对路径")
        key = path.casefold()
        if key in names:
            fail(422, "文件路径大小写冲突")
        names.add(key)
        size += len(content.encode("utf-8"))
    if any("/".join(path.split("/")[:i]) in names for path in names for i in range(1, path.count("/") + 1)):
        fail(422, "文件与目录重名")
    if size > 5 * 1024 * 1024:
        fail(413, "工程内容超过 5 MiB")
    return value


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def string(value, label, limit, optional=False):
    if not isinstance(value, str) or len(value) > limit or (not optional and not value.strip()):
        fail(422, f"{label}应为长度不超过 {limit} 的文本")
    return value
