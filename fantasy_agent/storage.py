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
                kind TEXT NOT NULL DEFAULT 'emergency_buy',
                executed_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS purchase_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id TEXT NOT NULL,
                origin TEXT NOT NULL,
                price INTEGER NOT NULL,
                ts REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS wealth (
                day TEXT PRIMARY KEY,
                cash INTEGER NOT NULL,
                squad_value INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS offer_log (
                id TEXT PRIMARY KEY,
                player_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                value INTEGER NOT NULL,
                money INTEGER NOT NULL,
                is_system INTEGER NOT NULL,
                seen_at REAL NOT NULL,
                ask INTEGER NOT NULL DEFAULT 0,
                listed_value INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS market_bids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                price INTEGER NOT NULL,
                expires_at REAL,
                status TEXT NOT NULL DEFAULT 'pending',
                direction TEXT NOT NULL DEFAULT 'buy',
                sell_kind TEXT,
                market_id TEXT,
                created_at REAL NOT NULL
            );
            """
        )
        self._migrate()

    def _migrate(self) -> None:
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(pending_ops)")}
        if "execute_at" not in cols:
            self.db.execute("ALTER TABLE pending_ops ADD COLUMN execute_at REAL")
            self.db.commit()
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(market_bids)")}
        if "direction" not in cols:
            self.db.execute("ALTER TABLE market_bids ADD COLUMN direction TEXT NOT NULL DEFAULT 'buy'")
            self.db.commit()
        if "sell_kind" not in cols:
            self.db.execute("ALTER TABLE market_bids ADD COLUMN sell_kind TEXT")
            self.db.commit()
        if "market_id" not in cols:
            self.db.execute("ALTER TABLE market_bids ADD COLUMN market_id TEXT")
            self.db.commit()
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(market_bids)")}
        if "ask" not in cols:
            self.db.execute("ALTER TABLE market_bids ADD COLUMN ask INTEGER NOT NULL DEFAULT 0")
            self.db.commit()
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(offer_log)")}
        for col in ("ask", "listed_value"):
            if col not in cols:
                self.db.execute(f"ALTER TABLE offer_log ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
        self.db.commit()
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(auto_buys)")}
        if "kind" not in cols:
            self.db.execute("ALTER TABLE auto_buys ADD COLUMN kind TEXT NOT NULL DEFAULT 'emergency_buy'")
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

    def retire_all_pending(self) -> int:
        """Modo autónomo: las propuestas que esperaban tu "Confirmar" ya no tienen sentido
        (el piloto automático decide solo); se retiran para que nada antiguo se ejecute."""
        cur = self.db.execute(
            "UPDATE pending_ops SET status = 'superseded' WHERE status IN ('pending', 'scheduled')"
        )
        self.db.commit()
        return cur.rowcount

    def supersede_pending_for_player(self, kind: str, player_id: str) -> int:
        """Cancela cualquier propuesta PENDIENTE del mismo tipo para el mismo jugador antes de
        crear una nueva — evita acumular dos "Confirmar/Cancelar" para lo mismo (p.ej. la
        misma cláusula subió de precio y salió una propuesta nueva sin retirar la vieja).
        Devuelve cuántas se han retirado."""
        rows = self.db.execute(
            "SELECT id, payload FROM pending_ops WHERE status = 'pending' AND kind = ?", (kind,)
        ).fetchall()
        n = 0
        for op_id, payload_json in rows:
            payload = json.loads(payload_json)
            if payload.get("player_id") == player_id:
                self.db.execute("UPDATE pending_ops SET status = 'superseded' WHERE id = ?", (op_id,))
                n += 1
        if n:
            self.db.commit()
        return n

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

    # ---- operaciones autónomas (sin confirmación): emergencia, compra o venta, tope semanal cada una ----
    def record_auto_op(self, kind: str, player_id: str, price: int) -> None:
        self.db.execute(
            "INSERT INTO auto_buys(player_id, price, kind, executed_at) VALUES (?, ?, ?, ?)",
            (player_id, price, kind, time.time()),
        )
        self.db.commit()


    # ---- autoajuste: origen de cada compra, resultado de las pujas y parámetros vivos ----
    def log_purchase(self, player_id: str, origin: str, price: int) -> None:
        self.db.execute("INSERT INTO purchase_log(player_id, origin, price, ts) VALUES (?, ?, ?, ?)",
                        (player_id, origin, price, time.time()))
        self.db.commit()

    def purchases(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT player_id, origin, price, ts FROM purchase_log ORDER BY ts").fetchall()
        return [{"pid": r[0], "origin": r[1], "price": r[2], "ts": r[3]} for r in rows]

    def bid_results(self) -> list[bool]:
        """Pujas de compra ya resueltas, de la más antigua a la más reciente: True = ganada."""
        rows = self.db.execute(
            "SELECT status FROM market_bids WHERE direction = 'buy' AND ask > 0 AND status IN ('won', 'lost') "
            "ORDER BY created_at").fetchall()
        return [r[0] == "won" for r in rows]

    def get_params(self) -> dict[str, float]:
        return json.loads(self.get("params") or "{}")

    def set_params(self, values: dict[str, float]) -> None:
        self.set("params", json.dumps(values))

    def param_history(self) -> list[dict[str, Any]]:
        return json.loads(self.get("params_history") or "[]")

    def log_param_change(self, key: str, old: float, new: float, why: str) -> None:
        hist = self.param_history()
        hist.append({"at": time.time(), "key": key, "old": old, "new": new, "why": why})
        self.set("params_history", json.dumps(hist[-60:]))

    def log_proposal(self, changes: dict[str, dict]) -> None:
        """Ajustes que el autoajuste HARÍA (modo shadow); se acumulan para revisarlos."""
        items = json.loads(self.get("proposals") or "[]")
        if items and items[-1]["changes"] == changes:
            return
        items.append({"at": time.time(), "changes": changes})
        self.set("proposals", json.dumps(items[-40:]))

    def proposals(self) -> list[dict[str, Any]]:
        return json.loads(self.get("proposals") or "[]")

    # ---- exportar / importar el estado (para analizarlo fuera de GitHub, ver export.py) ----
    TABLES = {
        "offer_log": ("id", "player_id", "player_name", "value", "money", "is_system", "seen_at", "ask", "listed_value"),
        "market_bids": ("player_id", "player_name", "price", "expires_at", "status", "direction", "sell_kind", "market_id", "created_at", "ask"),
        "purchase_log": ("player_id", "origin", "price", "ts"),
        "wealth": ("day", "cash", "squad_value"),
        "auto_buys": ("player_id", "price", "kind", "executed_at"),
        "player_status_history": ("player_id", "status", "recorded_at"),
    }
    EXPORT_KV = ("params", "params_history", "proposals", "siege_state", "siege_ids", "liquidity", "rival_premium",
                 "sold_ids", "lineup_variant")

    def export_state(self) -> dict[str, Any]:
        out: dict[str, Any] = {"tables": {}, "kv": {}}
        for table, cols in self.TABLES.items():
            rows = self.db.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
            out["tables"][table] = {"columns": list(cols), "rows": [list(r) for r in rows]}
        for key in self.EXPORT_KV:
            value = self.get(key)
            if value is not None:
                out["kv"][key] = value
        return out

    def import_state(self, state: dict[str, Any]) -> None:
        """Carga un estado exportado en esta base de datos (vacía): para analizar lo de la nube en local."""
        for table, spec in state.get("tables", {}).items():
            cols = spec["columns"]
            marks = ", ".join("?" for _ in cols)
            self.db.executemany(f"INSERT OR IGNORE INTO {table}({', '.join(cols)}) VALUES ({marks})", spec["rows"])
        for key, value in state.get("kv", {}).items():
            self.set(key, value)
        self.db.commit()

    # ---- patrimonio (saldo + valor de la plantilla), una foto al día ----
    def log_wealth(self, day: str, cash: int, squad_value: int) -> None:
        self.db.execute("INSERT OR IGNORE INTO wealth(day, cash, squad_value) VALUES (?, ?, ?)", (day, cash, squad_value))
        self.db.commit()

    def wealth_on_or_before(self, day: str) -> tuple[str, int, int] | None:
        r = self.db.execute("SELECT day, cash, squad_value FROM wealth WHERE day <= ? ORDER BY day DESC LIMIT 1", (day,)).fetchone()
        return (r[0], r[1], r[2]) if r else None

    def wealth_first(self) -> tuple[str, int, int] | None:
        r = self.db.execute("SELECT day, cash, squad_value FROM wealth ORDER BY day LIMIT 1").fetchone()
        return (r[0], r[1], r[2]) if r else None

    # ---- ofertas vistas: para aprender cómo se distribuyen respecto al valor ----
    def log_offer(self, offer_id: str, player_id: str, player_name: str, value: int, money: int, is_system: bool,
                  ask: int = 0, listed_value: int = 0) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO offer_log(id, player_id, player_name, value, money, is_system, seen_at, ask, listed_value) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (offer_id, player_id, player_name, value, money, int(is_system), time.time(), ask, listed_value),
        )
        self.db.commit()

    def offer_rows(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT player_name, value, money, ask, listed_value, is_system FROM offer_log WHERE value > 0 ORDER BY seen_at"
        ).fetchall()
        return [{"name": r[0], "value": r[1], "money": r[2], "ask": r[3], "listed_value": r[4], "system": bool(r[5])} for r in rows]

    def offer_ratios(self, system_only: bool = True) -> list[float]:
        """oferta / valor del jugador en el momento de verla, de todas las ofertas registradas."""
        q = "SELECT money * 1.0 / value FROM offer_log WHERE value > 0"
        if system_only:
            q += " AND is_system = 1"
        return sorted(r[0] for r in self.db.execute(q).fetchall())

    # ---- seguimiento de pujas/ventas: "enviada" no es "ganada"/"vendida" — hay que saber en qué queda ----
    def add_market_bid(
        self, player_id: str, player_name: str, price: int, expires_at: float | None, direction: str = "buy",
        sell_kind: str | None = None, market_id: str | None = None, ask: int = 0,
    ) -> None:
        self.db.execute(
            "INSERT INTO market_bids(player_id, player_name, price, expires_at, status, direction, "
            "sell_kind, market_id, created_at, ask) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)",
            (player_id, player_name, price, expires_at, direction, sell_kind, market_id, time.time(), ask),
        )
        self.db.commit()

    def unresolved_market_bids(self, direction: str = "buy") -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, player_id, player_name, price, expires_at, sell_kind, market_id FROM market_bids "
            "WHERE status = 'pending' AND direction = ?",
            (direction,),
        ).fetchall()
        return [
            {"id": r[0], "player_id": r[1], "player_name": r[2], "price": r[3], "expires_at": r[4],
             "sell_kind": r[5], "market_id": r[6]}
            for r in rows
        ]

    def resolve_market_bid(self, bid_id: int, status: str) -> None:
        self.db.execute("UPDATE market_bids SET status = ? WHERE id = ?", (status, bid_id))
        self.db.commit()
