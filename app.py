"""Serve the original Vue preview locally with Flask."""
from pathlib import Path

import click
from flask import Flask, abort, send_from_directory


def create_app():
    dist = Path(__file__).resolve().parent / "dist"
    app = Flask(__name__, static_folder=None)

    @app.get("/")
    @app.get("/<path:resource>")
    def frontend(resource=""):
        if resource == "api" or resource.startswith("api/"):
            abort(404)
        if resource.startswith("assets/") or "." in resource.rpartition("/")[2]:
            return send_from_directory(dist, resource)
        return send_from_directory(dist, "index.html", max_age=0)

    @app.cli.command("serve")
    @click.option("--port", type=click.IntRange(1, 65535), default=4173, show_default=True)
    def serve(port):
        app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)

    return app
