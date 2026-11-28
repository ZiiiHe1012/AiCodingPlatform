"""Flask application factory for the CodeLab engineering assessment platform."""
import os
import re
import threading
import time
from contextlib import contextmanager
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

import click
from flask import Flask, g, jsonify, redirect, request, send_from_directory, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.serving import run_simple

from . import ai_settings, assessments, auth, catalog, evaluation, exams, frontend_bridge, workspaces, exam_sandboxes
from .core import db, fail, ident, ok
from . import capacity


@contextmanager
def background_tasks(app, workers, model_slots):
    """Run the durable queue, exam clock, workspace maintenance and backups together."""
    capacity.configure(app, workers, model_slots)
    stop = threading.Event()

    def poll(action, interval):
        while not stop.is_set():
            try:
                with app.app_context():
                    worked = action()
            except Exception:
                app.logger.exception("后台任务暂时失败：%s", action.__name__)
                worked = False
            if not worked:
                stop.wait(interval)

    actions = [(exams.close_next_due, .75), (exam_sandboxes.maintain_one, .75)]
    actions.extend([(evaluation.work_once, .75)] * (workers + model_slots))
    threads = []
    try:
        for action, interval in actions:
            thread = threading.Thread(target=poll, args=(action, interval), daemon=True, name=action.__name__)
            thread.start()
            threads.append(thread)
        yield
    finally:
        stop.set()
        deadline = time.monotonic() + 5
        for thread in threads:
            if thread.is_alive():
                thread.join(max(0, deadline - time.monotonic()))


def create_app(config=None):
    root = Path(__file__).resolve().parent.parent
    app = Flask(__name__, static_folder=None, instance_path=str(root / "instance"))
    app.config.from_mapping(DATABASE=os.environ.get("CODELAB_DATABASE", str(root / "instance/codelab.sqlite3")),
                            COOKIE_SECURE=os.environ.get("CODELAB_HTTPS") == "1",
                            MAX_CONTENT_LENGTH=22 * 1024 * 1024)
    if config:
        app.config.update(config)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    app.json.ensure_ascii = False
    capacity.configure(app)

    @app.teardown_appcontext
    def close_db(error):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    with app.app_context():
        conn = db()
        conn.execute("PRAGMA journal_mode=WAL")
        for module in (auth, catalog, exams, assessments, evaluation, ai_settings, exam_sandboxes):
            module.init_db(conn)
        conn.commit()

    for module in (auth, catalog, exams, assessments, evaluation, workspaces):
        app.register_blueprint(module.bp, url_prefix="/api/v1")

    app.register_blueprint(ai_settings.bp)
    app.register_blueprint(frontend_bridge.bp)

    @app.before_request
    def authorize():
        g.request_id = ident("REQ")
        if not request.path.startswith("/api/"):
            return
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("Origin")
            if origin:
                try:
                    parsed = urlsplit(origin)
                    same_origin = parsed.netloc == request.host and parsed.scheme == request.scheme
                except ValueError:
                    same_origin = False
                if not same_origin:
                    fail(403, "写入请求必须来自当前站点")
        if (request.url_rule and request.endpoint not in ("health", "auth.login", "auth.register")
                and request.method != "OPTIONS"):
            auth.authenticate()
            expected = request.headers.get("X-CodeLab-User")
            if expected and expected != g.user["id"]:
                fail(409, "登录账号已变更，请刷新工作台。")

    @app.after_request
    def finish_request(response):
        if "db" in g:
            if response.status_code < 400:
                g.db.commit()
            else:
                g.db.rollback()
        response.headers["X-Request-ID"] = g.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.errorhandler(HTTPException)
    def error(exc):
        return jsonify(code=exc.name.upper().replace(" ", "_"), message=exc.description,
                       data=None, request_id=g.request_id), exc.code

    @app.get("/api/v1/health")
    def health():
        db().execute("SELECT 1")
        return ok({"status": "ok"})

    @app.get("/")
    @app.get("/<path:resource>")
    def frontend(resource=""):
        if resource == "api" or resource.startswith("api/"):
            fail(404, "接口不存在")
        # Tabs opened before release directories existed still request /assets/Workspace.js.
        dist = root / "dist"
        if re.fullmatch(r"assets/[\w.-]+\.(?:js|css|ttf)", resource) and not (dist / resource).is_file():
            name = resource.split("/")[1]
            for release in sorted((dist / "assets").glob("????????T?????????Z"), reverse=True):
                if (release / name).is_file():
                    return redirect(url_for("frontend", resource=f"assets/{release.name}/{name}"))
        if resource.startswith("assets/") or "." in resource.rpartition("/")[2]:
            return send_from_directory(dist, resource)
        response = send_from_directory(dist, "index.html")
        response.headers["Cache-Control"] = "no-cache"
        return response

    evaluation.init_app(app)
    app.cli.add_command(auth.create_user_command)

    @app.cli.command("serve")
    @click.option("--host", default="127.0.0.1", show_default=True)
    @click.option("--port", default=4173, type=click.IntRange(1, 65535), show_default=True)
    @click.option("--workers", type=click.IntRange(1, 8), default=2, envvar="CODELAB_WORKERS", show_default=True,
                  help="同时执行代码的最大槽位数。")
    @click.option("--model-slots", type=click.IntRange(1, 10), default=2, envvar="CODELAB_MODEL_SLOTS",
                  show_default=True, help="同时发往模型服务的最大请求数。")
    def serve(host, port, workers, model_slots):
        """Serve the local UI/API, evaluation queue and exam deadline scheduler."""
        try:
            local_only = ip_address(host).is_loopback
        except ValueError:
            local_only = host.lower().rstrip(".") == "localhost"
        if not local_only:
            pending = auth.accounts_using_demo_passwords()
            if pending:
                raise click.ClickException(
                    "开放课堂前请先修改以下账号的演示密码：" + "、".join(pending) +
                    "。运行 python -m flask --app app serve，"
                    "在本机依次登录这些账号，在「个人设置 → 修改密码」保存新密码。"
                    "完成后按 Ctrl+C 结束本机服务，再启动课堂。"
                )
        with background_tasks(app, workers, model_slots):
            run_simple(host, port, app, threaded=True, use_reloader=False, use_debugger=False)
    return app
