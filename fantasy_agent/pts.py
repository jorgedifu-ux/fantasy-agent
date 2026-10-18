"""Puntos de un jugador en una jornada, tomados de su FICHA (`/player/{id}`), no de la lista general: la lista de jugadores va con retraso o incompleta (18/10/2026:
Yoel Lago 2 en la lista y 7 en su ficha, Ilaix 0 y 1, y varios sin dato). Se guardan 15 min para no pedir cada jugador en cada pasada."""
from __future__ import annotations

import json
import time

from .storage import Store

KEY = "pts_cache"
TTL_S = 15 * 60


def _from_card(card: dict, week: int):
    for s in card.get("playerStats") or []:
        if s.get("weekNumber") == week and s.get("totalPoints") is not None:
            return s["totalPoints"]
    wp = card.get("weekPoints")
    return wp if isinstance(wp, (int, float)) else None


def week_points(store: Store | None, api, pid: str, week: int, list_value=None, started: bool = True):
    """Puntos del jugador en la jornada `week` (None = aún no ha jugado). `started=False`: su partido no ha empezado, no hace falta preguntar."""
    if not started:
        return None
    cache = json.loads(store.get(KEY) or "{}") if store is not None else {}
    hit = cache.get(pid)
    if hit and hit.get("w") == week and time.time() - hit.get("t", 0) < TTL_S:
        return hit.get("p")
    try:
        value = _from_card(api.player(pid), week)
    except Exception:
        return list_value if list_value is not None else (hit or {}).get("p")
    if value is None:
        value = list_value
    if store is not None:
        cache[pid] = {"w": week, "p": value, "t": round(time.time())}
        store.set(KEY, json.dumps(cache))
    return value
