"""Revalorización diaria de cada plantilla: lo que sube o baja el valor de los jugadores de cada mánager cuando se actualizan los valores (00:00, listo hacia las
00:20). Se calcula con la plantilla de hoy sobre el historial de valor de cada jugador, así que es la ganancia (o pérdida) «de mercado» del equipo, sin contar
compras, ventas ni premios."""
from __future__ import annotations

import json
import time
from datetime import datetime

from .storage import Store

KEY = "reval"
DAYS_BACK = 5


def _series(history) -> list[tuple[str, float]]:
    out = []
    for h in history or []:
        d, v = str(h.get("date", ""))[:10], h.get("marketValue")
        if d and v:
            out.append((d, float(v)))
    return sorted(out)


def compute(world, api) -> dict | None:
    """{day, managers: {mid: {name, me, value, delta, pct, days: [delta de cada uno de los últimos días], up: [(jugador, delta)], down: [...]}}} o None si falla."""
    owner_by_team = {r.team_id: str(r.manager_id) for r in world.standing}
    names = {str(r.manager_id): r.manager_name for r in world.standing}
    me = next((str(r.manager_id) for r in world.standing if r.team_id == world.my_team_id), "")
    squads: dict[str, list] = {mid: [] for mid in names}
    for sl in list(world.my_slots) + list(world.rival_slots):
        mid = owner_by_team.get(sl.owner_team_id)
        if mid in squads:
            squads[mid].append(sl.player)
    series: dict[str, list[tuple[str, float]]] = {}
    for players in squads.values():
        for p in players:
            if p.id not in series:
                try:
                    series[p.id] = _series(api.market_value_history(p.id))
                except Exception:
                    series[p.id] = []
    all_days = sorted({d for s in series.values() for d, _ in s})
    if len(all_days) < 2:
        return None
    days = all_days[-(DAYS_BACK + 1):]
    out = {"day": days[-1], "managers": {}}
    for mid, players in squads.items():
        per_day = [0.0] * (len(days) - 1)
        movers = []
        total_now = total_prev = 0.0
        for p in players:
            vals = dict(series.get(p.id, []))
            for i in range(1, len(days)):
                if days[i] in vals and days[i - 1] in vals:
                    per_day[i - 1] += vals[days[i]] - vals[days[i - 1]]
            if days[-1] in vals and days[-2] in vals:
                total_now += vals[days[-1]]
                total_prev += vals[days[-2]]
                movers.append((p.name, vals[days[-1]] - vals[days[-2]]))
        movers.sort(key=lambda x: -x[1])
        out["managers"][mid] = {"name": names[mid], "me": mid == me, "value": total_now, "delta": per_day[-1] if per_day else 0.0,
                                "pct": ((total_now - total_prev) / total_prev * 100) if total_prev else 0.0, "days": per_day,
                                "up": [m for m in movers if m[1] > 0][:3], "down": [m for m in reversed(movers) if m[1] < 0][:3]}
    return out


def refresh(store: Store, world, api, now: datetime | None = None) -> dict | None:
    """Una vez al día, a partir de las 00:20 (los valores se actualizan a las 00:00): guarda la revalorización en `kv.reval`. Devuelve lo guardado."""
    now = now or datetime.now()
    cached = json.loads(store.get(KEY) or "null")
    due = (now.hour, now.minute) >= (0, 20) and (not cached or cached.get("computed") != f"{now:%Y-%m-%d}")
    if due:
        data = compute(world, api)
        if data:
            data["computed"] = f"{now:%Y-%m-%d}"
            data["at"] = round(time.time())
            store.set(KEY, json.dumps(data, ensure_ascii=False))
            return data
    return cached


def load(store: Store) -> dict | None:
    return json.loads(store.get(KEY) or "null")
