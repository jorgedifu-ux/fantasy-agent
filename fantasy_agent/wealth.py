"""Patrimonio de cada mánager (caja estimada + valor de plantilla) día a día, para comparar con los rivales.

Hasta el 18/10/2026 el histórico está sembrado (`seed_patrimonio.json`, reconstruido con `/activity` y los valores diarios, ±10M); a partir de ahí
se toma una foto al día (`snapshot`) con la caja estimada por `/activity` (error ~1M) y el valor de plantilla de la clasificación."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import models, service
from .storage import Store

SEED = Path(__file__).with_name("seed_patrimonio.json")
KEY = "wealth_league"


def seed() -> dict[str, dict[str, float]]:
    try:
        return json.loads(SEED.read_text())
    except Exception:
        return {}


def series(store: Store) -> dict[str, dict[str, float]]:
    """día -> {manager_id: patrimonio en M€}; las fotos reales mandan sobre la reconstrucción."""
    out = dict(seed())
    out.update(json.loads(store.get(KEY) or "{}"))
    return dict(sorted(out.items()))


def cash_by_manager(api, league_id: str) -> dict[str, int]:
    cash: dict[str, int] = {}
    for a in service._all_activity(api, league_id):
        amount = models.to_int(models.pick(a, "amount"))
        kind = models.to_int(models.pick(a, "activityTypeId"))
        u1, u2 = str(models.pick(a, "user1Id", default="")), str(models.pick(a, "user2Id", default=""))
        for m in (u1, u2):
            cash.setdefault(m, service.STARTING_CASH)
        if kind in (1, 31):
            cash[u1] -= amount
        if kind == 33:
            cash[u1] += amount
        if kind == 1:
            cash[u2] += amount
        if kind == 6:
            cash[u1] += amount
    return cash


def snapshot(store: Store, api, world, now: datetime | None = None) -> None:
    """Una foto al día, a partir de las 4 de la madrugada (los valores se actualizan a las 00:00)."""
    now = now or datetime.now()
    day = f"{now:%Y-%m-%d}"
    stored = json.loads(store.get(KEY) or "{}")
    if now.hour < 4 or day in stored:
        return
    cash = cash_by_manager(api, world.league_id)
    row = {}
    for r in world.standing:
        mid = str(r.manager_id)
        if mid in cash:
            row[mid] = round((cash[mid] + (r.team_value or 0)) / 1e6, 1)
    if row:
        stored[day] = row
        store.set(KEY, json.dumps(dict(sorted(stored.items())[-400:])))


def points_by_week(api, league_id: str, upto: int) -> dict[str, list[int]]:
    """manager_id -> puntos de cada jornada 1..upto (de la clasificación semanal)."""
    out: dict[str, list[int]] = {}
    for w in range(1, upto + 1):
        try:
            rows = api.standing_week(league_id, w)
        except Exception:
            rows = []
        seen = set()
        for r in rows:
            t = r.get("team", {})
            mid = str(t.get("managerId", ""))
            out.setdefault(mid, []).append(int(r.get("points") or 0))
            seen.add(mid)
        for mid, lst in out.items():
            if mid not in seen:
                lst.append(0)
    return out
