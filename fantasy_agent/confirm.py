"""Cola de confirmación: propone por Telegram cualquier acción que gaste dinero (puja,
clausulazo) y SOLO la ejecuta si respondes "Confirmar <código>" (o "Confirmar" a secas si
solo hay una propuesta pendiente). "Cancelar" la descarta. La alineación no pasa por aquí:
al ser gratis y reversible hasta el cierre de mercado, se aplica sola (ver cli.py)."""
from __future__ import annotations

import re
import secrets
from typing import Any

from . import notify
from .api import FantasyAPI
from .config import Settings
from .storage import Store

CONFIRM_RE = re.compile(r"^\s*(confirm\w*|s[ií]|ok|vale)\b\s*([a-f0-9]{4})?", re.IGNORECASE)
CANCEL_RE = re.compile(r"^\s*(cancel\w*|no)\b\s*([a-f0-9]{4})?", re.IGNORECASE)


def propose(settings: Settings, store: Store, kind: str, payload: dict[str, Any], description: str) -> str:
    """Registra una propuesta y la manda por los canales configurados. Devuelve su código."""
    op_id = secrets.token_hex(2)  # 4 caracteres: cómodo de escribir a mano en la respuesta
    store.add_pending(op_id, kind, payload, description)
    notify.send_all(
        settings,
        f"❓ PROPUESTA [{op_id}]\n\n{description}\n\n"
        f"Responde \"Confirmar {op_id}\" o \"Cancelar {op_id}\" "
        f"(o solo \"Confirmar\"/\"Cancelar\" si es tu única propuesta pendiente).",
    )
    return op_id


def _execute(api: FantasyAPI, kind: str, payload: dict[str, Any]) -> str:
    if kind == "bid":
        api.bid(payload["league_id"], payload["market_id"], payload["money"])
        return f"✅ Puja enviada: {payload['money'] / 1_000_000:.2f}M por {payload.get('player_name', '?')}"
    if kind == "clause":
        api.pay_buyout_clause(payload["league_id"], payload["player_id"], payload["amount"])
        return f"✅ Cláusula pagada: {payload['amount'] / 1_000_000:.2f}M por {payload.get('player_name', '?')}"
    raise ValueError(f"tipo de operación desconocido: {kind}")


def poll_and_execute(settings: Settings, store: Store, api: FantasyAPI) -> list[str]:
    """Revisa mensajes nuevos de Telegram, resuelve confirmaciones/cancelaciones pendientes y
    ejecuta lo confirmado de verdad contra la API. Pensada para llamarse en cada `tick`."""
    results: list[str] = []
    if not notify.telegram_enabled(settings):
        return results

    store.expire_pending()
    last_id = store.get("telegram_last_update_id")
    offset = int(last_id) + 1 if last_id else None
    updates = notify.get_telegram_updates(settings, offset=offset)
    pending = {p["id"]: p for p in store.get_pending()}

    for upd in updates:
        store.set("telegram_last_update_id", str(upd["update_id"]))
        text = (upd.get("message") or {}).get("text", "")
        if not text:
            continue

        m_confirm = CONFIRM_RE.match(text)
        m_cancel = CANCEL_RE.match(text)
        if not (m_confirm or m_cancel):
            continue
        cancel = bool(m_cancel) and not m_confirm
        op_id = (m_cancel or m_confirm).group(2)

        if op_id is None:
            if len(pending) == 1:
                op_id = next(iter(pending))
            elif not pending:
                notify.send_all(settings, "No hay ninguna propuesta pendiente.")
                continue
            else:
                codes = ", ".join(pending)
                notify.send_all(settings, f"Hay varias propuestas pendientes, indica el código: {codes}")
                continue

        op = pending.get(op_id)
        if op is None:
            notify.send_all(settings, f"No encuentro la propuesta [{op_id}] (¿ya resuelta o caducada?).")
            continue

        if cancel:
            store.resolve_pending(op_id, "cancelled")
            del pending[op_id]
            notify.send_all(settings, f"🚫 Cancelado [{op_id}].")
            continue

        try:
            msg = _execute(api, op["kind"], op["payload"])
            store.resolve_pending(op_id, "done")
        except Exception as exc:
            msg = f"❌ Error ejecutando [{op_id}]: {exc}\nNo se ha gastado nada — revísalo y proponlo de nuevo."
            store.resolve_pending(op_id, "error")
        del pending[op_id]
        notify.send_all(settings, msg)
        results.append(msg)

    return results
