"""Registro diario de cláusulas abiertas de TODA la liga (kv `exposure_log`), para estudiar con datos si subir una cláusula compensa: cuántos días está
abierto cada jugador (y a qué múltiplo de su valor, con qué tendencia, blindado o no) y a cuántos se les paga la cláusula (actividad tipo 1). Solo registra."""
from __future__ import annotations

import json
from datetime import datetime

from .storage import Store

KEY = "exposure_log"
MAX_ROWS = 6000


def snapshot(store: Store, world, now: datetime, rises: dict[str, float] | None = None) -> int:
    """Una foto al día (a partir de las 20:00 hora local, antes de las ofertas de las 20:53) de cada jugador de la liga con la cláusula abierta o a punto.
    Fila: [día, id jugador, dueño (id de equipo), cláusula/valor, valor en M€, subida diaria %, blindado 0/1, abierta 0/1, media de puntos]."""
    day = f"{now:%Y-%m-%d}"
    if now.hour < 20 or not store.alert_is_new(f"exposure:{day}", ttl_hours=30):
        return 0
    rows = json.loads(store.get(KEY) or "[]")
    n = 0
    for sl in list(world.my_slots) + list(world.rival_slots):
        p = sl.player
        if not p.market_value or sl.clause <= 0:
            continue
        shielded = bool(sl.shielded_until and sl.shielded_until > now.astimezone())
        opened = sl.clause_open(now.astimezone())
        if not opened and not shielded:
            continue          # ni abierta ni blindada con la cláusula ya liberada: no está expuesta
        rows.append([day, p.id, sl.owner_team_id, round(sl.clause / p.market_value, 3), round(p.market_value / 1e6, 2),
                     round((rises or {}).get(p.id, 0.0) * 100, 2), int(shielded), int(opened), round(p.avg_points, 1)])
        n += 1
    store.set(KEY, json.dumps(rows[-MAX_ROWS:]))
    return n
