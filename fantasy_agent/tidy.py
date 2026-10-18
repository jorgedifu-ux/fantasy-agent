"""Orden del chat de Telegram: el panel fijado se queda y todo lo demás que manda el bot (y tus órdenes, ya contestadas) se borra pasado un tiempo,
para que la conversación no crezca. Telegram solo deja borrar mensajes de menos de 48 h, así que el plazo es de 24 h (las órdenes tuyas, 1 h)."""
from __future__ import annotations

import json
import time

from . import notify
from .storage import Store

KEY = "sent_msgs"
TTL_S = 24 * 3600
USER_TTL_S = 3600
MAX_TRACKED = 400
MAX_DELETES_PER_PASS = 40


def _load(store: Store) -> list[dict]:
    return json.loads(store.get(KEY) or "[]")


def track(store: Store, ids: list[int], now: float | None = None, ttl_s: float = TTL_S) -> None:
    """Apunta mensajes para borrarlos dentro de `ttl_s` segundos."""
    if not ids:
        return
    now = now or time.time()
    items = _load(store)
    seen = {i["id"] for i in items}
    for mid in ids:
        if mid not in seen:
            items.append({"id": int(mid), "due": round(now + ttl_s)})
    store.set(KEY, json.dumps(items[-MAX_TRACKED:]))


def keep_ids(store: Store) -> set[int]:
    out = set()
    for key in ("panel_message_id", "team_plan_message_id"):
        v = store.get(key)
        if v and v.isdigit():
            out.add(int(v))
    return out


def sweep(store: Store, settings, now: float | None = None, delete=None) -> int:
    """Recoge lo mandado en esta pasada (`notify.SENT_IDS`) y borra lo que ya ha cumplido su plazo (salvo el panel). Devuelve cuántos borró."""
    now = now or time.time()
    delete = delete or (lambda mid: notify.delete_message(settings, mid))
    sent, notify.SENT_IDS[:] = list(notify.SENT_IDS), []
    keep = keep_ids(store)
    track(store, [m for m in sent if m not in keep], now)
    items = [i for i in _load(store) if i["id"] not in keep]
    left, deleted = [], 0
    for it in sorted(items, key=lambda i: i["due"]):
        if it["due"] <= now and deleted < MAX_DELETES_PER_PASS:
            if delete(it["id"]):
                deleted += 1
                continue
        left.append(it)
    store.set(KEY, json.dumps(left[-MAX_TRACKED:]))
    return deleted


def purge(store: Store, settings, delete=None) -> int:
    """Borra YA todo lo que el bot tiene apuntado (menos el panel fijado): lo de «actualizar y limpiar»."""
    delete = delete or (lambda mid: notify.delete_message(settings, mid))
    keep = keep_ids(store)
    sent, notify.SENT_IDS[:] = list(notify.SENT_IDS), []
    track(store, [m for m in sent if m not in keep])
    items = [i for i in _load(store) if i["id"] not in keep]
    left, deleted = [], 0
    for it in items:
        if deleted < 100 and delete(it["id"]):
            deleted += 1
        else:
            left.append(it)
    store.set(KEY, json.dumps(left[-MAX_TRACKED:]))
    return deleted
