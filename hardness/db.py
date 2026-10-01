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
            status      TEXT NOT NULL DEFAULT 'running'
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


def create_session(session_id: str, task_input: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (id, created_at, task_input) VALUES (?, ?, ?)",
            (session_id, time.time(), task_input)
        )


def close_session(session_id: str, status: str = "done") -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET status = ? WHERE id = ?",
            (status, session_id)
        )
