"""Modo estrella (opción B, acordado el 8/11/2026): cada día se compara el once actual con el que saldría de fichar a una estrella (cláusula abierta de un rival),
vendiendo lo que haga falta para pagarla. Se compra solo si el once mejora ≥ `STAR_MIN_GAIN` pts/jornada y compensa la fricción de comprar y vender (~5% del
precio). Estudio del 8/11 (12 jornadas): con ~400M de presupuesto el mejor once ya lleva una estrella y con ~600M, dos; antes, obligar a una resta puntos.
Módulo puro (sin red ni base de datos); la ejecución está en `cli._star_mode`."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import autopilot as ap
from .models import Player, SquadSlot

STAR_MIN_GAIN = 3.0         # pts esperados por jornada que debe ganar el once
STAR_MIN_XPTS = 9.0         # puntos esperados del fichaje (media con algo de forma)
STAR_MAX_RATIO = 1.12       # cláusula como mucho ×1,12 su valor
STAR_MAX_SHARE = 0.55       # el precio no supera el 55% del patrimonio
STAR_MIN_HOURS = 72         # solo con ≥3 días por delante de la próxima jornada (o en parón): vender titulares cerca de una jornada es peligroso
STAR_MIN_WEEKS = 15         # quedan al menos 15 jornadas por jugar
STAR_FRICTION = 0.05        # coste de comprar y vender (ofertas ×0,95–1,0 y primas), en fracción del precio
STAR_SALE_HAIRCUT = 0.97    # lo que se espera cobrar por lo que se vende (oferta ≥×0,97)
STAR_CASH_RESERVE = 2_000_000
STAR_SALE_MIN = 0.97        # oferta mínima que se acepta por un jugador del plan


@dataclass
class StarPlan:
    player_id: str
    name: str
    price: int
    gain: float                          # pts/jornada que gana el once
    sells: list[tuple[str, str]] = field(default_factory=list)      # (id, nombre) de lo que se vende para pagarla
    xpts: float = 0.0

    def to_json(self) -> dict:
        return {"player_id": self.player_id, "name": self.name, "price": self.price, "gain": self.gain, "sells": self.sells, "xpts": self.xpts}


def plan(mine: list[Player], rival_slots: list[SquadSlot], trends: dict, form: dict[str, float] | None, cash: int, wealth: int, now: datetime,
         hours_to_next: float | None, weeks_left: int) -> StarPlan | None:
    """La mejor estrella que compensa fichar ahora (o None). `trends`: id -> (jugador, Trend)."""
    if hours_to_next is None or hours_to_next < STAR_MIN_HOURS or weeks_left < STAR_MIN_WEEKS or wealth <= 0:
        return None
    base = ap.squad_value(mine, form, complete_bonus=False)
    best: StarPlan | None = None
    for sl in rival_slots:
        p = sl.player
        if not p.market_value or sl.clause <= 0 or not sl.clause_open(now) or p.status.lower() in ap.INJURED:
            continue
        if sl.clause / p.market_value > STAR_MAX_RATIO or sl.clause > wealth * STAR_MAX_SHARE:
            continue
        tr = trends.get(p.id)
        if tr is not None and tr[1].d7 < -3.0:
            continue
        x = ap.xpts(p, form)
        if x < STAR_MIN_XPTS:
            continue
        need = sl.clause * 1.01 + STAR_CASH_RESERVE - cash
        cur = list(mine)
        sells: list[Player] = []
        raised = 0.0
        while raised < need:
            cands = [q for q in cur if q.position_id != 1]          # los porteros no se venden para esto
            if not cands:
                break
            q = min(cands, key=lambda c: ap.sale_loss(cur, c.id, form) / max(c.market_value, 1))
            sells.append(q)
            cur.remove(q)
            raised += q.market_value * STAR_SALE_HAIRCUT
        if raised < need:
            continue
        after = cur + [p]
        if not ap.complete_eleven(after):
            continue
        gain = ap.squad_value(after, form, complete_bonus=False) - base
        friction_m = STAR_FRICTION * sl.clause / 1e6
        if gain < STAR_MIN_GAIN or gain * ap.POINT_VALUE_M * min(weeks_left, 20) < friction_m:
            continue
        if best is None or gain > best.gain:
            best = StarPlan(p.id, p.name, sl.clause, round(gain, 1), [(q.id, q.name) for q in sells], round(x, 1))
    return best
