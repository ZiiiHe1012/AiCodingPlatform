"""Bound and report concurrent code execution and model calls within one server."""
from contextlib import contextmanager
from threading import Condition

from flask import current_app, has_app_context


class SlotPool:
    def __init__(self, limit):
        self.limit = limit
        self.available = limit
        self.waiting = 0
        self.condition = Condition()

    def acquire(self, timeout):
        with self.condition:
            if not self.available:
                self.waiting += 1
                try:
                    if not self.condition.wait_for(lambda: self.available > 0, timeout):
                        return False
                finally:
                    self.waiting -= 1
            self.available -= 1
            return True

    def release(self):
        with self.condition:
            self.available += 1
            self.condition.notify()

    def snapshot(self):
        with self.condition:
            return {"limit": self.limit, "available": self.available, "in_use": self.limit - self.available,
                    "waiting": self.waiting}


def configure(app, code_slots=8, model_slots=10):
    app.extensions["codelab_slots"] = {"code": SlotPool(code_slots), "model": SlotPool(model_slots)}


def current_capacity():
    return {name: gate.snapshot() for name, gate in current_app.extensions.get("codelab_slots", {}).items()}


@contextmanager
def slot(kind, checkpoint):
    pools = current_app.extensions.get("codelab_slots", {}) if has_app_context() else {}
    gate = pools.get(kind)
    if gate is None:
        yield
        return
    while not gate.acquire(timeout=.25):
        checkpoint()
    try:
        checkpoint()
        yield
    finally:
        gate.release()
