"""Minimal chat-completions client. Credentials are only present in the trusted Flask worker."""
import base64
import http.client
import json
import queue
import sqlite3
import ssl
import threading
from contextlib import closing
from urllib.parse import unquote, urlsplit
from urllib.request import getproxies, proxy_bypass
from .sandbox import ServiceFault, TransientServiceFault
from .ai_settings import daily_call_limit, model_options
from flask import current_app, has_app_context


class InvalidModelResponse(ServiceFault):
    """A successful model request produced an unreadable structured answer."""


def _reserve_daily_call():
    """Count attempts across grading, chat and workers before the outbound request."""
    if not has_app_context():
        default = daily_call_limit()
        if default is None:
            return
        raise ServiceFault("平台已暂停模型调用。" if default == 0 else "模型调用缺少平台额度上下文。")
    # Commit independently: an ambiguous timeout or a worker restart may already be billable.
    with closing(sqlite3.connect(current_app.config["DATABASE"], timeout=10)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            maximum = daily_call_limit(conn)
        except ValueError as error:
            raise ServiceFault("模型日调用上限配置无效，请管理员检查服务配置。") from error
        if maximum == 0:
            raise ServiceFault("平台已暂停模型调用。")
        reserved = conn.execute("""INSERT INTO model_daily_usage(utc_day,attempts) VALUES(date('now'),1)
            ON CONFLICT(utc_day) DO UPDATE SET attempts=attempts+1 WHERE ? IS NULL OR attempts < ?""", (maximum, maximum))
        if not reserved.rowcount:
            raise ServiceFault("平台今日模型调用额度已用完，按 UTC 日期重置。")


def configured():
    options = model_options()
    return bool(options["url"] and options["name"])


def model_name(frozen=None, options=None):
    deployed = (options or model_options())["name"]
    if frozen is not None and frozen != deployed:
        raise ServiceFault("考试冻结的模型与当前部署不一致，请恢复指定模型或转人工评阅。")
    return frozen or deployed


def chat(messages, max_tokens, checkpoint=lambda: None, *, model=None, request_key=None):
    from .capacity import slot
    with slot("model", checkpoint):
        return _request(messages, max_tokens, checkpoint, model=model, request_key=request_key)


def _connection(url):
    if url.scheme == "http":
        return http.client.HTTPConnection(url.hostname, url.port, timeout=45)
    if url.hostname == "api.openai.com" and not proxy_bypass(url.hostname):
        proxy = urlsplit(getproxies().get("https", ""))
        if proxy.scheme == "http" and proxy.hostname:
            conn = http.client.HTTPSConnection(proxy.hostname, proxy.port or 80, timeout=45)
            headers = {}
            if proxy.username is not None:
                auth = f"{unquote(proxy.username)}:{unquote(proxy.password or '')}".encode()
                headers["Proxy-Authorization"] = "Basic " + base64.b64encode(auth).decode("ascii")
            conn.set_tunnel(url.hostname, url.port or 443, headers=headers)
            return conn
    return http.client.HTTPSConnection(url.hostname, url.port, timeout=45)


def _request(messages, max_tokens, checkpoint, *, model, request_key):
    options = model_options()
    if not options["url"] or not options["name"]:
        raise ServiceFault("尚未配置模型服务，请联系管理员在 AI 服务设置页填写接口地址和模型。")
    url = urlsplit(options["url"])
    if not url.hostname or url.username or url.password or url.scheme not in {"https", "http"}:
        raise ServiceFault("模型服务地址无效。")
    if url.scheme == "http" and url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ServiceFault("远程模型服务需要 HTTPS 地址。")
    conn = _connection(url)
    headers = {"Content-Type": "application/json"}
    key = options["key"]
    if key:
        headers["Authorization"] = "Bearer " + key
    if request_key:
        headers["Idempotency-Key"] = request_key
    payload = {"model": model_name(model, options), "messages": messages}
    if url.hostname == "api.openai.com":
        payload.update(max_completion_tokens=max_tokens, response_format={"type": "json_object"})
        if payload["model"] == "gpt-6-luna":
            payload["reasoning_effort"] = "none"
    else:
        payload.update(max_tokens=max_tokens, temperature=0)
    if url.hostname == "api.deepseek.com":
        # Each agent step needs a complete JSON action within its allotted output tokens.
        payload.update(response_format={"type": "json_object"}, thinking={"type": "disabled"})
    body = json.dumps(payload, ensure_ascii=False).encode()
    results = queue.Queue(1)
    def send():
        try:
            conn.request("POST", (url.path or "/") + ("?" + url.query if url.query else ""),
                         body=body, headers=headers)
            resp = conn.getresponse()
            if resp.status == 402:
                raise ServiceFault("模型供应商返回 HTTP 402，请管理员检查账户余额和计费状态。")
            if resp.status != 200:
                fault = TransientServiceFault if resp.status in (408, 429) or resp.status >= 500 else ServiceFault
                raise fault(f"模型服务请求失败（HTTP {resp.status}）。")
            raw = resp.read(256 * 1024 + 1)
            if len(raw) > 256 * 1024:
                raise ServiceFault("模型响应超过大小限制。")
            envelope = json.loads(raw)
            answer = envelope["choices"][0]["message"]["content"]
            if not isinstance(answer, str):
                raise ValueError()
            if answer.strip().startswith("```"):
                answer = "\n".join(answer.strip().splitlines()[1:-1])
            parsed = json.loads(answer)
            if not isinstance(parsed, dict):
                raise ValueError()
            usage = envelope.get("usage", {}).get("total_tokens")
            results.put((parsed, usage if type(usage) is int and usage > 0 else None))
        except ServiceFault as exc:
            results.put(exc)
        except (ValueError, TypeError, AttributeError, KeyError, IndexError, RecursionError):
            results.put(InvalidModelResponse("模型响应不符合 JSON 对象格式。"))
        except ConnectionRefusedError:
            results.put(TransientServiceFault("模型服务或已配置的代理拒绝连接。请管理员检查服务地址和代理是否运行。"))
        except ssl.SSLCertVerificationError:
            results.put(ServiceFault("模型接口的 HTTPS 证书校验失败，请管理员检查服务地址和证书链。"))
        except (OSError, http.client.HTTPException):
            results.put(TransientServiceFault("无法连接模型服务或读取其响应。"))
        finally:
            conn.close()
    checkpoint()
    _reserve_daily_call()
    threading.Thread(target=send, daemon=True).start()
    try:
        while True:
            checkpoint()
            try:
                result = results.get(timeout=0.25)
            except queue.Empty:
                continue
            if isinstance(result, Exception):
                raise result
            return result
    finally:
        conn.close()
