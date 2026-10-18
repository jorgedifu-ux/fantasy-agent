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
        same_since = hit.get("same_since", hit.get("t", time.time())) if hit and hit.get("w") == week and hit.get("p") == value else time.time()
        cache[pid] = {"w": week, "p": value, "t": round(time.time()), "same_since": round(same_since)}
        store.set(KEY, json.dumps(cache))
    return value


# ---- puntos DEFINITIVOS: partido terminado Y puntos ya asignados por Fantasy ----
FULL_TIME_S = 115 * 60        # saque inicial + duración
GRACE_S = 40 * 60             # Fantasy tarda en repartir los puntos tras el pitido final
STABLE_S = 20 * 60            # y el valor debe llevar al menos esto sin cambiar entre lecturas


def schedule(api, week: int) -> dict[str, dict]:
    """team_id -> {kickoff, finished} de la jornada (del calendario)."""
    from . import models
    out: dict[str, dict] = {}
    try:
        for m in models.as_list(api.calendar(week), "matches", "elements", "calendar"):
            when = models.parse_dt(m.get("matchDate") or m.get("date"))
            if when is None:
                continue
            done = m.get("localScore") is not None or m.get("matchState") == 7
            for team in (str(m.get("localId")), str(m.get("visitorId"))):
                out[team] = {"kickoff": when, "finished": bool(done)}
    except Exception:
        pass
    return out


def settled_points(store: Store, api, pid: str, week: int, match: dict | None, now: float | None = None):
    """Puntos del jugador en `week` solo si son definitivos: el partido terminó hace ≥ `GRACE_S` y el valor de su ficha lleva ≥ `STABLE_S` sin cambiar. Si no, None."""
    now = now or time.time()
    if not match or not match.get("finished"):
        return None
    if now < match["kickoff"].timestamp() + FULL_TIME_S + GRACE_S:
        return None
    value = week_points(store, api, pid, week, started=True)
    entry = (json.loads(store.get(KEY) or "{}") if store is not None else {}).get(pid) or {}
    if value is None or now - entry.get("same_since", now) < STABLE_S:
        return None
    return value
