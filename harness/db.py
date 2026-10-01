# ~/agent_team/harness/db.py
"""SQLite schema and trace logging."""

import sqlite3
import time
import json
from pathlib import Path
from typing import Any

DB_PATH = Path.home() / "agent_team" / "traces.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          TEXT PRIMARY KEY,
            created_at  REAL NOT NULL,
            task_input  TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'running',
            title       TEXT,
            parent_id   TEXT
        );

        CREATE TABLE IF NOT EXISTS traces (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            step        INTEGER NOT NULL,
            agent       TEXT NOT NULL,
            action      TEXT NOT NULL,
            tool_name   TEXT,
            tool_args   TEXT,
            tool_result TEXT,
            model_out   TEXT,
            tokens_in   INTEGER,
            tokens_out  INTEGER,
            elapsed_ms  INTEGER,
            created_at  REAL NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS checkpoints (
            session_id  TEXT PRIMARY KEY,
            step        INTEGER NOT NULL,
            state_json  TEXT NOT NULL,
            updated_at  REAL NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        """)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
        if "title" not in cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN title TEXT")
        if "parent_id" not in cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN parent_id TEXT")


def log_trace(
    session_id: str,
    step: int,
    agent: str,
    action: str,
    tool_name: str | None = None,
    tool_args: dict | None = None,
    tool_result: dict | None = None,
    model_out: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    elapsed_ms: int = 0,
) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO traces
            (session_id, step, agent, action, tool_name, tool_args, tool_result,
             model_out, tokens_in, tokens_out, elapsed_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, step, agent, action, tool_name,
            json.dumps(tool_args) if tool_args else None,
            json.dumps(tool_result) if tool_result else None,
            model_out, tokens_in, tokens_out, elapsed_ms, time.time()
        ))


def save_checkpoint(session_id: str, step: int, state: dict) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO checkpoints (session_id, step, state_json, updated_at)
            VALUES (?, ?, ?, ?)
        """, (session_id, step, json.dumps(state), time.time()))


def load_checkpoint(session_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT step, state_json FROM checkpoints WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        if row:
            return {"step": row["step"], "state": json.loads(row["state_json"])}
        return None


def create_session(session_id: str, task_input: str = "", title: str | None = None, parent_id: str | None = None) -> None:
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if existing:
            if title:
                conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
        else:
            conn.execute(
                "INSERT INTO sessions (id, created_at, task_input, status, title, parent_id) VALUES (?, ?, ?, 'running', ?, ?)",
                (session_id, time.time(), task_input, title or (task_input[:50] if task_input else session_id), parent_id)
            )


def close_session(session_id: str, status: str = "done") -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET status = ? WHERE id = ?",
            (status, session_id)
        )


def list_sessions() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT s.id, s.created_at, s.task_input, s.status, s.title, s.parent_id,
                   COUNT(t.id) as trace_count
            FROM sessions s
            LEFT JOIN traces t ON s.id = t.session_id
            GROUP BY s.id
            ORDER BY s.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]


def get_session(session_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None


def delete_session(session_id: str) -> bool:
    with get_conn() as conn:
        conn.execute("DELETE FROM checkpoints WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM traces WHERE session_id = ?", (session_id,))
        cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return cur.rowcount > 0


def branch_session(source_id: str, new_id: str, title: str | None = None) -> bool:
    with get_conn() as conn:
        src = conn.execute("SELECT * FROM sessions WHERE id = ?", (source_id,)).fetchone()
        if not src:
            return False
        new_title = title or f"branch of {src['title'] or source_id}"
        conn.execute(
            "INSERT INTO sessions (id, created_at, task_input, status, title, parent_id) VALUES (?, ?, ?, 'running', ?, ?)",
            (new_id, time.time(), src["task_input"], new_title, source_id)
        )
        ckpt = conn.execute("SELECT * FROM checkpoints WHERE session_id = ?", (source_id,)).fetchone()
        if ckpt:
            conn.execute(
                "INSERT OR REPLACE INTO checkpoints (session_id, step, state_json, updated_at) VALUES (?, ?, ?, ?)",
                (new_id, ckpt["step"], ckpt["state_json"], time.time())
            )
        return True

