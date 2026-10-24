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
COVERAGE = 0.9          # fracción de jugadores que ha de tener valor un día para darlo por actualizado
RETRY_S = 1800         # si lo guardado parece erróneo, se vuelve a calcular cada media hora


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
    # Un día solo cuenta si casi todos los jugadores ya tienen su valor (la actualización de las 00:00 llega escalonada: con unos pocos jugadores
    # al día nuevo, los demás salían a 0 y el panel decía que nadie había ganado ni perdido nada).
    have = [s for s in series.values() if s]
    if not have:
        return None
    all_days = sorted({d for s in have for d, _ in s})
    all_days = [d for d in all_days if sum(1 for s in have if any(x == d for x, _ in s)) >= COVERAGE * len(have)]
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


def looks_wrong(data: dict | None) -> bool:
    """Imposible en la práctica: ninguna plantilla se mueve ni un euro (valores a medio actualizar)."""
    ms = (data or {}).get("managers") or {}
    return bool(ms) and all(abs(m.get("delta", 0.0)) < 1 for m in ms.values())


def refresh(store: Store, world, api, now: datetime | None = None) -> dict | None:
    """Una vez al día, a partir de las 00:20 (los valores se actualizan a las 00:00): guarda la revalorización en `kv.reval`. Devuelve lo guardado.
    Si lo guardado parece erróneo (`looks_wrong`) se recalcula cada `RETRY_S` segundos; un cálculo erróneo no se guarda."""
    now = now or datetime.now()
    cached = json.loads(store.get(KEY) or "null")
    stale = bool(cached) and cached.get("computed") != f"{now:%Y-%m-%d}"
    retry = looks_wrong(cached) and time.time() - (cached.get("at") or 0) >= RETRY_S
    due = (now.hour, now.minute) >= (0, 20) and (not cached or stale or retry)
    if due:
        data = compute(world, api)
        if data and not looks_wrong(data):
            data["computed"] = f"{now:%Y-%m-%d}"
            data["at"] = round(time.time())
            store.set(KEY, json.dumps(data, ensure_ascii=False))
            return data
        if cached and not stale:
            cached["at"] = round(time.time())      # para no reintentar en cada pasada
            store.set(KEY, json.dumps(cached, ensure_ascii=False))
    return cached


def load(store: Store) -> dict | None:
    return json.loads(store.get(KEY) or "null")
