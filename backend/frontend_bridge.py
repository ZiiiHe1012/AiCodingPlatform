"""Serve the shared same-origin transport used by the Vue build."""
from pathlib import Path

from flask import Blueprint, send_from_directory

bp = Blueprint("frontend_bridge", __name__)
ROOT = Path(__file__).resolve().parent


@bp.get("/assets/codelab-backend.js")
def transport():
    return send_from_directory(ROOT / "static", "codelab-backend.js")
