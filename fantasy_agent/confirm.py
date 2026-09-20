"""Cola de confirmación: propone por Telegram cualquier acción que gaste dinero (puja,
clausulazo) y SOLO la ejecuta si respondes "Confirmar <código>" (o "Confirmar" a secas si
solo hay una propuesta pendiente). "Cancelar" la descarta. La alineación no pasa por aquí:
al ser gratis y reversible hasta el cierre de mercado, se aplica sola (ver cli.py).

Para cláusulas que aún no se han liberado: el precio es fijo y conocido de antemano (no es
una puja a ciegas), así que tu "Confirmar" de ahora vale como aprobación del importe exacto
— no hace falta que estés pendiente en el segundo en que se libera. `run_scheduled()` espera
internamente hasta ese instante y ejecuta sola, sin volver a preguntarte."""
from __future__ import annotations

import re
import secrets
import time
from typing import Any

from . import notify
from .api import FantasyAPI
from .config import Settings
from .storage import Store

CONFIRM_RE = re.compile(r"^\s*(confirm\w*|s[ií]|ok|vale)\b\s*([a-f0-9]{4})?", re.IGNORECASE)
CANCEL_RE = re.compile(r"^\s*(cancel\w*|no)\b\s*([a-f0-9]{4})?", re.IGNORECASE)

IMMEDIATE_WINDOW_S = 60  # si execute_at está a menos de esto, se ejecuta ya, no se programa


def propose(
    settings: Settings, store: Store, kind: str, payload: dict[str, Any], description: str,
    *, execute_at: float | None = None, label: str = "",
) -> str:
    """Registra una propuesta y la manda por los canales configurados, con botones de
    Confirmar/Cancelar (además de aceptar la respuesta escrita, por si acaso). Devuelve el
    código de la propuesta.

    `execute_at` (timestamp unix, opcional): si se da y está en el futuro, al confirmar no
    se ejecuta al momento — se programa para ese instante exacto (ver `run_scheduled`).
    `label`: etiqueta de urgencia/calidad ya formateada (ver analysis.clause_urgency_label /
    player_quality_label) para que sepas de un vistazo qué tan buena es la operación."""
    op_id = secrets.token_hex(2)  # 4 caracteres: cómodo de escribir a mano si el botón falla
    store.add_pending(op_id, kind, payload, description, execute_at=execute_at)
    when_note = ""
    if execute_at and execute_at - time.time() > IMMEDIATE_WINDOW_S:
        when = time.strftime("%d/%m %H:%M", time.localtime(execute_at))
        when_note = f"\n\n⏱️ <i>Si confirmas, se ejecuta sola el {when} — no hace falta que estés pendiente.</i>"
    label_line = f"<b>{notify.esc(label)}</b>\n\n" if label else ""
    notify.send_all(
        settings,
        f"❓ <b>PROPUESTA [{op_id}]</b>\n\n{label_line}{notify.esc(description)}{when_note}",
        buttons=[("✅ Confirmar", f"confirm:{op_id}"), ("❌ Cancelar", f"cancel:{op_id}")],
        html=True,
    )
    return op_id


def _execute(api: FantasyAPI, store: Store, kind: str, payload: dict[str, Any]) -> str:
    name = notify.esc(str(payload.get("player_name", "?")))
    if kind == "bid":
        api.bid(payload["league_id"], payload["market_id"], payload["money"])
        store.add_market_bid(payload["player_id"], name, payload["money"], payload.get("expires_at"))
        return (
            f"📨 Puja <b>enviada</b> (pendiente de resolverse): <b>{payload['money'] / 1_000_000:.2f}M</b> "
            f"por <b>{name}</b>\nTe aviso en cuanto se sepa si la ganas."
        )
    if kind == "clause":
        api.pay_buyout_clause(payload["league_id"], payload["player_id"], payload["amount"])
        return f"✅ Cláusula pagada: <b>{payload['amount'] / 1_000_000:.2f}M</b> por <b>{name}</b> — ya es tuyo."
    if kind == "sell":
        api.sell_player(payload["league_id"], payload["player_id"], payload["sale_price"])
        store.add_market_bid(payload["player_id"], name, payload["sale_price"], None, direction="sell")
        return (
            f"📨 Puesto a la venta (pendiente de que alguien lo compre): <b>{name}</b> "
            f"por <b>{payload['sale_price'] / 1_000_000:.2f}M</b>\nTe aviso en cuanto se venda de verdad."
        )
    raise ValueError(f"tipo de operación desconocido: {kind}")


def _run_and_report(settings: Settings, store: Store, api: FantasyAPI, op_id: str, op: dict) -> str:
    try:
        msg = _execute(api, store, op["kind"], op["payload"])
        store.resolve_pending(op_id, "done")
    except Exception as exc:
        msg = f"❌ Error ejecutando [{op_id}]: {notify.esc(str(exc))}\nNo se ha gastado nada — revísalo y proponlo de nuevo."
        store.resolve_pending(op_id, "error")
    notify.send_all(settings, msg, html=True)
    return msg


def poll_and_execute(settings: Settings, store: Store, api: FantasyAPI) -> list[str]:
    """Revisa mensajes nuevos de Telegram, resuelve confirmaciones/cancelaciones pendientes y
    ejecuta lo confirmado de verdad contra la API (o lo programa, si su `execute_at` está lejos
    en el futuro). Pensada para llamarse en cada `tick`."""
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

        cq = upd.get("callback_query")
        if cq:
            # Botón pulsado: "confirm:<id>" o "cancel:<id>", siempre con código explícito.
            data = cq.get("data", "")
            action, _, cq_op_id = data.partition(":")
            notify.answer_callback(settings, cq["id"])
            if action not in ("confirm", "cancel") or not cq_op_id:
                continue
            cancel, op_id = action == "cancel", cq_op_id
        else:
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

        execute_at = op.get("execute_at")
        if execute_at and execute_at - time.time() > IMMEDIATE_WINDOW_S:
            store.schedule(op_id)
            when = time.strftime("%d/%m %H:%M", time.localtime(execute_at))
            msg = f"👍 Programado [{op_id}] para el {when}. No hace falta que hagas nada más."
            notify.send_all(settings, msg)
            results.append(msg)
        else:
            results.append(_run_and_report(settings, store, api, op_id, op))
        del pending[op_id]

    return results


def run_scheduled(settings: Settings, store: Store, api: FantasyAPI, *, max_wait_s: int = 25 * 60) -> list[str]:
    """Ejecuta lo que ya confirmaste con antelación, en su instante exacto. Si el próximo
    programado cae dentro de `max_wait_s`, este proceso ESPERA (duerme) hasta ese segundo
    exacto y ejecuta — así no hace falta un servidor 24/7 para llegar a tiempo. Si cae más
    lejos, no hace nada: el tick de dentro de esa ventana ya lo recogerá."""
    results: list[str] = []
    due_soon = [s for s in store.get_scheduled() if s["execute_at"] and s["execute_at"] - time.time() <= max_wait_s]
    for op in sorted(due_soon, key=lambda s: s["execute_at"]):
        wait = op["execute_at"] - time.time()
        if wait > 0:
            time.sleep(wait)
        results.append(_run_and_report(settings, store, api, op["id"], op))
    return results
