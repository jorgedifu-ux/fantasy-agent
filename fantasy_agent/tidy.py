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


def track(store: Store, ids: list[int], now: float | None = None, ttl_s: float = TTL_S, keep: bool = False) -> None:
    """Apunta mensajes para borrarlos dentro de `ttl_s` segundos. `keep=True`: información sin leer (avisos urgentes) que «actualizar y limpiar»
    no borra; se borra por plazo."""
    if not ids:
        return
    now = now or time.time()
    items = _load(store)
    seen = {i["id"] for i in items}
    for mid in ids:
        if mid not in seen:
            items.append({"id": int(mid), "due": round(now + ttl_s), **({"keep": True} if keep else {})})
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


RANGE_BACK = 150          # cuántos ids hacia atrás se barren al limpiar (Telegram solo deja borrar lo de menos de 48 h)


def purge(store: Store, settings, delete=None, latest: int | None = None, pinned: int | None = None) -> int:
    """«Actualizar y limpiar»: borra YA todo menos el panel fijado y los avisos urgentes sin leer. Primero lo que el bot tiene apuntado y luego un
    barrido por los últimos `RANGE_BACK` ids del chat: así también se va lo que no estaba apuntado (mensajes de antes, o mandados desde otro sitio)
    y tus propias órdenes. `latest` (último id del chat) se averigua mandando un mensaje de prueba, que también se borra."""
    delete = delete or (lambda mid: notify.delete_message(settings, mid))
    keep = keep_ids(store)
    pin = pinned if pinned is not None else notify.pinned_message_id(settings)
    if pin:
        keep.add(int(pin))
    sent, notify.SENT_IDS[:] = list(notify.SENT_IDS), []
    track(store, [m for m in sent if m not in keep])
    items = [i for i in _load(store) if i["id"] not in keep]
    unread = {i["id"] for i in items if i.get("keep")}
    keep |= unread
    if latest is None:
        try:
            latest = notify.send_telegram(settings, "🧹")
        except Exception:
            latest = None
        notify.SENT_IDS[:] = []
    deleted = 0
    tried: set[int] = set()
    for it in items:
        if it["id"] in keep:
            continue
        tried.add(it["id"])
        if delete(it["id"]):
            deleted += 1
    if latest:
        for mid in range(int(latest), max(0, int(latest) - RANGE_BACK), -1):
            if mid in keep or mid in tried:
                continue
            if delete(mid):
                deleted += 1
            time.sleep(0.03)        # sin machacar a Telegram
    store.set(KEY, json.dumps([i for i in items if i["id"] in unread][-MAX_TRACKED:]))
    return deleted
