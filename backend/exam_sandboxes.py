"""Provision and retire an exam container without blocking check-in or hand-in on Docker."""
import time

from .core import db, now
from .sandbox import ServiceFault, ensure_workspace, release_workspace


def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS exam_sandboxes (
            exam_id TEXT NOT NULL, user_id TEXT NOT NULL, next_check REAL NOT NULL DEFAULT 0,
            ready INTEGER NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(exam_id,user_id));
        CREATE INDEX IF NOT EXISTS sandbox_due ON exam_sandboxes(next_check);
    """)
    columns = {r[1] for r in conn.execute("PRAGMA table_info(exam_sandboxes)")}
    for column in ("busy_until", "closing"):
        if column not in columns:
            conn.execute(f"ALTER TABLE exam_sandboxes ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0")


def register(eid, user):
    db().execute("INSERT OR IGNORE INTO exam_sandboxes(exam_id,user_id) VALUES(?,?)", (eid, user))


def retire(eid, user=None):
    sql = "UPDATE exam_sandboxes SET next_check=0,closing=1 WHERE exam_id=?"
    if user is None:
        db().execute(sql, (eid,))
    else:
        db().execute(sql + " AND user_id=?", (eid,user))


def maintain_one():
    conn = db()
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute("""SELECT w.exam_id,w.user_id,e.state,e.end,s.id AS receipt
            FROM exam_sandboxes w JOIN exams e ON e.id=w.exam_id
            LEFT JOIN sheets s ON s.exam_id=w.exam_id AND s.user_id=w.user_id
            WHERE w.next_check<=? AND w.busy_until<=? ORDER BY w.next_check LIMIT 1""", (time.time(),time.time())).fetchone()
    if row is None:
        conn.commit()
        return False
    key = (row["exam_id"], row["user_id"])
    lease = time.time() + 90
    conn.execute("UPDATE exam_sandboxes SET busy_until=? WHERE exam_id=? AND user_id=?", (lease, *key))
    conn.commit()
    if row["receipt"] or row["state"] != "published" or row["end"] <= now():
        if release_workspace(row["user_id"], row["exam_id"]):
            conn.execute("DELETE FROM exam_sandboxes WHERE exam_id=? AND user_id=? AND busy_until=?", (*key, lease))
        conn.commit()
        return True
    try:
        ensure_workspace(row["user_id"], row["exam_id"])
        delay, ready, error = 120, 1, ""
    except ServiceFault as exc:
        delay, ready, error = 45, 0, str(exc)
    conn.execute("""UPDATE exam_sandboxes SET next_check=CASE WHEN closing=1 THEN 0 ELSE ? END,
                     busy_until=0,ready=?,last_error=?
                  WHERE exam_id=? AND user_id=? AND busy_until=?""",
                 (time.time()+delay, ready, error, *key, lease))
    conn.commit()
    return True
