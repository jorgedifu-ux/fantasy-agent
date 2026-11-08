"""Modo estrella (opción B, acordado el 8/11/2026): cada día se compara el once actual con el que saldría de fichar a una estrella (cláusula abierta de un rival),
vendiendo lo que haga falta para pagarla. Se compra solo si el once mejora ≥ `STAR_MIN_GAIN` pts/jornada y compensa la fricción de comprar y vender (~5% del
precio). Estudio del 8/11 (12 jornadas): con ~400M de presupuesto el mejor once ya lleva una estrella y con ~600M, dos; antes, obligar a una resta puntos.
Módulo puro (sin red ni base de datos); la ejecución está en `cli._star_mode`."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import autopilot as ap
from .models import MarketItem, Player, SquadSlot

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


# ---------------------------------------------------------------------------------------------
# Estrellas del MERCADO (anuncios de LaLiga): no se da dinero a un rival y no hay clausulazo que provoque una venta. 8/11/2026, acordado con el usuario:
# la puja depende del poder adquisitivo de los rivales (su caja estimada con /activity). Sin ventas previas: se paga con caja + crédito.
# ---------------------------------------------------------------------------------------------
STAR_BID_MARGIN = 1.01          # si ningún rival puede pagarla, un 1% sobre el mínimo
STAR_MAX_PREMIUM = 0.15         # techo de la prima sobre el valor al pujar por una estrella
STAR_DEFAULT_PREMIUM = 0.08     # prima típica si no hay datos de las pujas ganadas por los rivales
STAR_MIN_PREMIUM = 0.03


@dataclass
class MarketPlan:
    item: MarketItem
    bid: int
    gain: float
    xpts: float
    rivals_able: int            # rivales con caja para pagar el mínimo
    uses_credit: int = 0        # parte de la puja que sale del crédito

    @property
    def name(self) -> str:
        return self.item.player.name


def star_bid(floor: int, rivals_cash: list[int], p75_premium: float | None, value: int) -> tuple[int, int]:
    """(puja, nº de rivales que pueden pagar el mínimo). Sin rivales con caja suficiente: mínimo +1%. Con rivales: el mínimo más la prima típica de los rivales
    (entre +3% y +15%), y si el más rico no llega a esa cifra, se puja justo por encima de lo máximo que puede ofrecer (su caja)."""
    able = [c for c in rivals_cash if c >= floor * 1.005]
    if not able:
        return round(floor * STAR_BID_MARGIN), 0
    prem = min(STAR_MAX_PREMIUM, max(STAR_MIN_PREMIUM, (p75_premium - 1) if p75_premium and p75_premium > 1 else STAR_DEFAULT_PREMIUM))
    target = floor * (1 + prem)
    richest = max(able)
    if richest < target:
        target = max(floor * STAR_BID_MARGIN, richest * 1.005)
    return round(min(target, max(value, floor) * (1 + STAR_MAX_PREMIUM))), len(able)


def market_plan(mine: list[Player], market: list[MarketItem], trends: dict, form: dict[str, float] | None, budget: int, credit: int, wealth: int,
                rivals_cash: list[int], p75_premium: float | None, hours_to_next: float | None, weeks_left: int, max_squad: int) -> MarketPlan | None:
    """La mejor estrella del mercado que compensa pujar ahora (o None). `budget`: saldo que se puede gastar; `credit`: crédito para pujas."""
    if hours_to_next is None or hours_to_next < STAR_MIN_HOURS or weeks_left < STAR_MIN_WEEKS or wealth <= 0 or len(mine) >= max_squad:
        return None
    base = ap.squad_value(mine, form, complete_bonus=False)
    best: MarketPlan | None = None
    for it in market:
        p = it.player
        if it.seller != "LaLiga" or not it.market_id or it.my_bid or it.price <= 0 or not p.market_value or p.status.lower() in ap.INJURED:
            continue
        tr = trends.get(p.id)
        if tr is not None and tr[1].d7 < -3.0:
            continue
        x = ap.xpts(p, form)
        if x < STAR_MIN_XPTS:
            continue
        floor = ap.bid_floor(it)
        if floor > wealth * STAR_MAX_SHARE:
            continue
        bid, able = star_bid(floor, rivals_cash, p75_premium, p.market_value)
        if bid > budget + credit:
            continue
        gain = ap.squad_value(mine + [p], form, complete_bonus=False) - base
        premium_cost_m = max(0, bid - p.market_value) / 1e6 + 0.02 * p.market_value / 1e6       # prima pagada + ~2% de diferencia al revender
        if gain < STAR_MIN_GAIN or gain * ap.POINT_VALUE_M * min(weeks_left, 20) < premium_cost_m:
            continue
        if best is None or gain > best.gain:
            best = MarketPlan(it, bid, round(gain, 1), round(x, 1), able, max(0, bid - budget))
    return best
