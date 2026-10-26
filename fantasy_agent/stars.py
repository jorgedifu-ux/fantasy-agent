"""Oportunidades de «estrella» (en sombra): jugadores de media alta que se pueden fichar ahora, para saber con qué frecuencia salen, a qué precio y si
habríamos podido pagarlos. Solo registra (kv `star_log`); no compra nada. Datos del 26/10/2026: por encima de 100M la media sube a ~11,5 pts/partido (frente a
5,7 en 30–60M), pero casi todos los de media ≥ 7,4 no tienen dueño en la liga y solo salen cuando LaLiga los pone en el mercado. La media de temporada engaña
(Valles, media 9,3: forma reciente 4,7 y bajando un 8,8% en 7 días), por eso se guarda también la forma."""
from __future__ import annotations

import json
import time
from datetime import datetime

from .storage import Store

KEY = "star_log"
MIN_AVG = 7.5          # media de temporada para considerarlo
MIN_VALUE = 15_000_000
MAX_LOG = 150


def candidates(market, rival_slots, trends: dict, form: dict[str, float], now: datetime, cash: int, wealth: int) -> list[dict]:
    """Anuncios de LaLiga y cláusulas de rivales ya abiertas de jugadores con media ≥ MIN_AVG y valor ≥ MIN_VALUE."""
    out = []

    def row(kind: str, p, price: int, extra: dict) -> dict:
        tr = trends.get(p.id)
        d = {"kind": kind, "player": p.name, "pos": p.position_id, "avg": round(p.avg_points, 1), "form": round(form.get(p.id, 0.0), 1),
             "d7": round(tr[1].d7, 1) if tr else None, "value": p.market_value, "price": price,
             "affordable": price <= cash, "pct_wealth": round(price / wealth * 100, 1) if wealth else None, "cash": cash}
        d.update(extra)
        return d

    for it in market:
        p = it.player
        if it.seller == "LaLiga" and p.avg_points >= MIN_AVG and p.market_value >= MIN_VALUE and it.price > 0:
            out.append(row("mercado", p, it.price, {"expires": it.expires.timestamp() if it.expires else None}))
    for sl in rival_slots:
        p = sl.player
        if p.avg_points >= MIN_AVG and p.market_value >= MIN_VALUE and sl.clause_open(now):
            out.append(row("cláusula", p, sl.clause, {"owner": sl.owner_name, "ratio": round(sl.clause / p.market_value, 2)}))
    return out


def record(store: Store, found: list[dict], now: float | None = None) -> int:
    """Añade al registro lo que no se había visto ya (mismo jugador y tipo en 24 h). Devuelve cuántos añadió."""
    now = now or time.time()
    log = json.loads(store.get(KEY) or "[]")
    added = 0
    for d in found:
        if store.alert_is_new(f"star:{d['kind']}:{d['player']}", ttl_hours=24):
            log.append({"at": round(now), **d})
            added += 1
    if added:
        store.set(KEY, json.dumps(log[-MAX_LOG:], ensure_ascii=False))
    return added
