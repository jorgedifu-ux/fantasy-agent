"""SQLite local: histórico de valores, alertas ya enviadas y cola de confirmación."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class Store:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS alerts_sent (key TEXT PRIMARY KEY, ts REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS pending_ops (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
            );
            """
        )

    def alert_is_new(self, key: str, ttl_hours: float = 72) -> bool:
        """True la primera vez que se ve una alerta (y la registra)."""
        now = time.time()
        self.db.execute("DELETE FROM alerts_sent WHERE ts < ?", (now - ttl_hours * 3600,))
        cur = self.db.execute("INSERT OR IGNORE INTO alerts_sent(key, ts) VALUES (?, ?)", (key, now))
        self.db.commit()
        return cur.rowcount == 1

    def get(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv(key, value) VALUES (?, ?)", (key, value))
        self.db.commit()

    # ---- cola de operaciones que esperan confirmación (pujas, cláusulas) ----
    def add_pending(self, op_id: str, kind: str, payload: dict[str, Any], description: str) -> None:
        self.db.execute(
            "INSERT INTO pending_ops(id, kind, payload, description, created_at, status) "
            "VALUES (?, ?, ?, ?, ?, 'pending')",
            (op_id, kind, json.dumps(payload), description, time.time()),
        )
        self.db.commit()

    def get_pending(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, kind, payload, description FROM pending_ops WHERE status = 'pending' "
            "ORDER BY created_at"
        ).fetchall()
        return [{"id": r[0], "kind": r[1], "payload": json.loads(r[2]), "description": r[3]} for r in rows]

    def resolve_pending(self, op_id: str, status: str) -> None:
        self.db.execute("UPDATE pending_ops SET status = ? WHERE id = ?", (status, op_id))
        self.db.commit()

    def expire_pending(self, ttl_hours: float = 48) -> None:
        cutoff = time.time() - ttl_hours * 3600
        self.db.execute(
            "UPDATE pending_ops SET status = 'expired' WHERE status = 'pending' AND created_at < ?",
            (cutoff,),
        )
        self.db.commit()
