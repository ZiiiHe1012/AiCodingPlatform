"""Model gateway credentials and classroom agent workflow settings."""
import os
from urllib.parse import parse_qsl, urlsplit

from flask import Blueprint, has_app_context, make_response, render_template, request

from .core import audit, body, db, fail, ok, require

bp = Blueprint("ai_settings", __name__)


def init_db(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS model_daily_policy (
        id INTEGER PRIMARY KEY CHECK(id=1), maximum INTEGER CHECK(maximum >= 0))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS model_daily_usage (
        utc_day TEXT PRIMARY KEY, attempts INTEGER NOT NULL)""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_service_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            url TEXT NOT NULL,
            name TEXT NOT NULL,
            api_key TEXT
        )
    """)


def model_options():
    """Read the effective gateway settings; keep the returned key server-side."""
    defaults = {key: os.getenv(var, "") for key, var in
                (("url", "CODELAB_MODEL_URL"), ("name", "CODELAB_MODEL_NAME"), ("key", "CODELAB_MODEL_KEY"))}
    if not has_app_context():
        return defaults
    row = db().execute("SELECT url,name,api_key FROM ai_service_settings WHERE id=1").fetchone()
    if row is None:
        return defaults
    key = row["api_key"]
    if key is None:
        default_service = urlsplit(defaults["url"])
        saved_service = urlsplit(row["url"])
        same_host = (saved_service.scheme, saved_service.netloc.lower()) == (default_service.scheme, default_service.netloc.lower())
        key = defaults["key"] if same_host else ""
    return {"url": row["url"], "name": row["name"], "key": key}


def daily_call_limit(conn=None):
    row = conn.execute("SELECT maximum FROM model_daily_policy WHERE id=1").fetchone() if conn is not None else None
    if row is not None:
        return row[0]
    setting = os.getenv("CODELAB_MODEL_DAILY_CALL_LIMIT")
    if setting is None:
        return None
    if not setting.isascii() or not setting.isdecimal() or len(setting) > 16 or int(setting) > 9007199254740991:
        raise ValueError("CODELAB_MODEL_DAILY_CALL_LIMIT 必须是非负整数")
    return int(setting)


def public_options():
    options = model_options()
    usage = db().execute("SELECT attempts FROM model_daily_usage WHERE utc_day=date('now')").fetchone()
    return {"url": options["url"], "name": options["name"],
            "daily_call_limit": daily_call_limit(db()), "daily_calls_used": usage[0] if usage else 0,
            "key_configured": bool(options["key"]), "configured": bool(options["url"] and options["name"])}


def clean_text(value, maximum, label):
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 or ord(c) == 127 for c in value):
        fail(422, f"{label}格式无效")
    return value.strip()


def check_url(value):
    try:
        parsed = urlsplit(value)
        valid = (parsed.hostname and parsed.port != 0 and parsed.username is None
                 and parsed.password is None and not parsed.fragment
                 and not any(ch.isspace() for ch in value) and "\\" not in value
                 and (parsed.scheme == "https" or (parsed.scheme == "http" and
                      parsed.hostname in {"127.0.0.1", "::1", "localhost"})))
    except ValueError:
        valid = False
    if not valid:
        fail(422, "请填写完整的 HTTPS 接口地址，本机 localhost 或回环地址也可使用 HTTP")
    if any(name.lower().replace("-", "_") in {"key", "api_key", "apikey", "token", "access_token",
                                              "secret", "password", "authorization"}
           for name, _ in parse_qsl(parsed.query)):
        fail(422, "请将凭证填入 API 密钥栏")


@bp.get("/settings/ai")
def page():
    response = make_response(render_template("ai_settings.html"))
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route("/api/v1/settings/ai", methods=["GET", "PUT"])
def settings():
    require("admin")
    if request.method == "GET":
        return ok(public_options())

    data = body()
    url = clean_text(data.get("url"), 2048, "接口地址")
    name = clean_text(data.get("name"), 160, "模型名称")
    if bool(url) != bool(name):
        fail(422, "接口地址和模型名称需要一起填写，或一起留空以停用服务")
    if url:
        check_url(url)
    key = clean_text(data.get("key", ""), 4096, "API 密钥")
    clear = data.get("clear_key", False)
    if type(clear) is not bool or (key and clear):
        fail(422, "请在更换密钥和清除密钥中选择一项")
    maximum = data.get("daily_call_limit")
    if maximum is not None and (type(maximum) is not int or not 0 <= maximum <= 9007199254740991):
        fail(422, "每日请求上限应为非负整数或不限。")

    conn = db()
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    current = model_options()
    if (current["key"] and url and not key and not clear
            and urlsplit(current["url"]).netloc.lower() != urlsplit(url).netloc.lower()):
        fail(422, "更换服务主机时，请填写新主机的密钥，或勾选清除原密钥")
    conn.execute("""
        INSERT INTO ai_service_settings(id,url,name,api_key) VALUES(1,?,?,?)
        ON CONFLICT(id) DO UPDATE SET url=excluded.url,name=excluded.name,
          api_key=COALESCE(excluded.api_key,ai_service_settings.api_key)
    """, (url, name, "" if clear else key or None))
    if "daily_call_limit" in data:
        conn.execute("""INSERT INTO model_daily_policy(id,maximum) VALUES(1,?)
            ON CONFLICT(id) DO UPDATE SET maximum=excluded.maximum""", (maximum,))
        audit("更新平台模型日额度", "不限" if maximum is None else str(maximum))
    audit("更新 AI 服务配置", "调整模型服务连接参数")
    return ok(public_options())
