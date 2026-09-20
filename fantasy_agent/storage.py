"""SQLite local: histórico de valores/estado, alertas ya enviadas, cola de confirmación."""
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
                execute_at REAL,
                status TEXT NOT NULL DEFAULT 'pending'
            );
            CREATE TABLE IF NOT EXISTS player_status_history (
                player_id TEXT NOT NULL,
                status TEXT NOT NULL,
                recorded_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auto_buys (
                player_id TEXT NOT NULL,
                price INTEGER NOT NULL,
                executed_at REAL NOT NULL
            );
            """
        )
        self._migrate()

    def _migrate(self) -> None:
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(pending_ops)")}
        if "execute_at" not in cols:
            self.db.execute("ALTER TABLE pending_ops ADD COLUMN execute_at REAL")
            self.db.commit()

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

    # ---- cola de operaciones: pendiente de confirmar -> (ejecutada | programada) ----
    def add_pending(
        self, op_id: str, kind: str, payload: dict[str, Any], description: str,
        execute_at: float | None = None,
    ) -> None:
        self.db.execute(
            "INSERT INTO pending_ops(id, kind, payload, description, created_at, execute_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
            (op_id, kind, json.dumps(payload), description, time.time(), execute_at),
        )
        self.db.commit()

    def get_pending(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, kind, payload, description, execute_at FROM pending_ops "
            "WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
        return [
            {"id": r[0], "kind": r[1], "payload": json.loads(r[2]), "description": r[3], "execute_at": r[4]}
            for r in rows
        ]

    def schedule(self, op_id: str) -> None:
        """Confirmado por el usuario pero con `execute_at` en el futuro: se ejecutará solo
        en ese momento exacto (ver confirm.run_scheduled), sin volver a preguntar."""
        self.db.execute("UPDATE pending_ops SET status = 'scheduled' WHERE id = ?", (op_id,))
        self.db.commit()

    def get_scheduled(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, kind, payload, description, execute_at FROM pending_ops "
            "WHERE status = 'scheduled' ORDER BY execute_at"
        ).fetchall()
        return [
            {"id": r[0], "kind": r[1], "payload": json.loads(r[2]), "description": r[3], "execute_at": r[4]}
            for r in rows
        ]

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

    # ---- histórico de estado del jugador (la API solo da el estado de HOY) ----
    def record_status(self, player_id: str, status: str) -> None:
        """Guarda un cambio de estado, no una fila por tick (evita ruido)."""
        last = self.db.execute(
            "SELECT status FROM player_status_history WHERE player_id = ? "
            "ORDER BY recorded_at DESC LIMIT 1",
            (player_id,),
        ).fetchone()
        if last and last[0] == status:
            return
        self.db.execute(
            "INSERT INTO player_status_history(player_id, status, recorded_at) VALUES (?, ?, ?)",
            (player_id, status, time.time()),
        )
        self.db.commit()

    def recently_recovered(self, player_id: str, within_days: float = 10) -> bool:
        """True si el último cambio de estado registrado fue de lesión/duda/sanción a ok,
        dentro de los últimos `within_days` días (proxy de "aún no revalorizado")."""
        cutoff = time.time() - within_days * 86400
        rows = self.db.execute(
            "SELECT status, recorded_at FROM player_status_history WHERE player_id = ? "
            "ORDER BY recorded_at DESC LIMIT 2",
            (player_id,),
        ).fetchall()
        if len(rows) < 2:
            return False
        (cur_status, cur_ts), (prev_status, _) = rows
        bad = {"injured", "suspended", "lesionado", "sancionado", "doubtful", "duda"}
        return cur_status.lower() == "ok" and prev_status.lower() in bad and cur_ts >= cutoff

    # ---- fichajes de emergencia (huecos en plantilla), tope semanal ----
    def record_auto_buy(self, player_id: str, price: int) -> None:
        self.db.execute(
            "INSERT INTO auto_buys(player_id, price, executed_at) VALUES (?, ?, ?)",
            (player_id, price, time.time()),
        )
        self.db.commit()

    def auto_buys_this_week(self) -> list[dict[str, Any]]:
        cutoff = time.time() - 7 * 86400
        rows = self.db.execute(
            "SELECT player_id, price, executed_at FROM auto_buys WHERE executed_at >= ?",
            (cutoff,),
        ).fetchall()
        return [{"player_id": r[0], "price": r[1], "executed_at": r[2]} for r in rows]
