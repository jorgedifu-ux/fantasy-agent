"""Piloto automático: decisiones autónomas, puras (sin red) y testeables.

Sustituye a los "Confirmar" y a los topes de nº de operaciones por reglas económicas:
- Comprar (puja o cláusula) solo si SUBE los puntos esperados de tu once y cabe en el saldo
  sin tocar el colchón — contando también lo ya comprometido en pujas y lo reservado para
  cláusulas que se liberan pronto. Nunca se puede acabar en negativo por esto.
- Tener 11 alineables vale muchísimo más que cualquier mejora: una alineación incompleta es
  la jornada entera a cero, así que completar el once se prioriza siempre.
- Vender: ofertas de la liga por encima del valor de mercado se aceptan (salvo jugadores
  clave); las de rivales se rechazan salvo que sean excepcionales.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import lineup
from .models import MarketItem, Offer, Player, SquadSlot

FIELD_POSITIONS = (1, 2, 3, 4)
POINT_VALUE_M = 0.30         # lo que vale un punto de jornada (0,1M de premio + posición en la liga)
GAIN_HORIZON = 3             # jornadas durante las que se espera disfrutar de lo que un fichaje suma al once
RESALE_SPREAD = 0.05         # lo que se pierde al revender (las ofertas medias están ~5% bajo lo que se paga)
MAX_CLAUSE_RATIO = 1.2       # cláusula "lógica": ≤1.2x el valor de mercado
SHORT_CLAUSE_RATIO = 1.35    # si falta cubrir esa posición (sin ella no hay once legal) se admite algo más de prima
MIN_GAIN = 0.5               # pts/jornada que como mínimo debe sumar una compra
COMPLETE_XI_BONUS = 15.0     # completar el once pesa más que cualquier fichaje
BENCH_WEIGHT = 0.15          # los suplentes cuentan algo (lesiones, rotaciones)
BENCH_SLOTS = 4
PENALTY_FACTOR = 0.6         # clausular por venganza o pagando prima al líder: se puede, con menos prioridad
# Quitarle un jugador al líder (8/10/2026): si su cláusula ≈ su valor no le regalamos dinero (cobra lo que
# vale) y pierde los puntos de ese jugador: doble efecto en la clasificación. Lo que pierde se mide
# (`leader_loss`: cuánto empeora su mejor once, y mucho más si se queda sin once completo) y se suma al
# beneficio del fichaje para UNA jornada; por eso se ejecuta justo antes de la congelación de cláusulas
# (`STRIKE_MARGIN`): ya no puede reponerlo por cláusula y solo le queda el mercado de ese día.
LEADER_FAIR_RATIO = 1.05
STRIKE_MARGIN = timedelta(minutes=3)
STRIKE_HORIZON_H = 24       # si la congelación llega en <24 h, se espera a ella en vez de pagar ya
MAX_OVERBID = 0.12           # nunca pujar más de +12% sobre el precio de salida (4/10/2026: con +20%
# se pagó Soria un 18% sobre su valor y Gueye un 15%: pérdida inmediata de ~15M)

LEAGUE_OFFER_MIN = 1.05      # oferta de la liga: vender desde +5% sobre el valor
CUT_LOSS_OFFER_MIN = 0.97    # jugador en caída/lesionado: salir aunque sea a ~valor
KEY_PLAYER_OFFER_MIN = 1.25  # jugador clave: solo por una oferta muy alta
KEY_PLAYER_LOSS = 3.0        # "clave" = quitarlo baja el once ≥3 pts/jornada
STARTER_LOSS = 1.0           # titular: a <48h de la jornada solo se vende por mucho
BENCH_LOSS = 0.5             # suplente que apenas suma
BENCH_OFFER_MIN = 0.97       # con la plantilla llena, un suplente se vende a ~su valor
LIQUIDITY_OFFER_MIN = 0.97   # para liberar capital hacia una inversión en subida
INJURED_OFFER_MIN = 1.0      # un lesionado se vende a ~su valor
RISING_D3 = 1.0              # sigue subiendo mientras gane >1% en 3 días
RISING_HOLD_MIN = 1.25       # y mientras tanto solo se vende por una oferta fuera de lo normal
# Efecto del partido en los puntos (calibrado el 10/10/2026 con 1.661 actuaciones de la J1 a la J8; validado
# jornada a jornada): casa ×1,06 / fuera ×0,94; contra los 4 primeros de LaLiga ×0,80 (antes ×0,92: los
# jugadores sacan un 27% menos); resto ±8% según el puesto del rival; los DEFENSAS lo notan 1,5 veces más.
# Reduce el error de predicción un 4,2% frente a ignorar al rival (el ajuste anterior, un 2,6%); un partido
# suelto sigue siendo muy ruidoso (desviación 0,71 × la media del jugador). Solo se usa para ELEGIR EL ONCE.
HOME_FACTOR = 1.06
RIVAL_DIFFICULTY = 0.08
TOP_RANK_N = 4
TOP_RANK_FACTOR = 0.80
DEFENDER_SENSITIVITY = 1.5
RIVAL_OFFER_MIN = 1.30       # ofertas de rivales: casi nunca convienen
AT_RISK_HOURS = 72           # se empieza a intentar vender 3 días antes de que acabe su
# protección: la liga genera una oferta al día (~20:53), así hay 3 oportunidades
AT_RISK_OFFER_START = 1.03   # a 3 días: solo una buena oferta...
AT_RISK_OFFER_LAST = 1.00    # ...el último día: su valor. Nunca menos que la cláusula: si un rival la paga,
# cobras la cláusula entera, que es lo máximo entre lo que pagaste y su valor (comprobado el 8/10/2026 en 49
# de 55 jugadores de la liga; el resto, cláusulas subidas a mano). Vender por debajo de eso es perder dinero
# frente a que te lo quiten (caso David Soria, decisión del usuario).
AT_RISK_KEY_EXTRA = 0.07     # un jugador clave exige un poco más en todo el tramo
LISTING_MARKUP = 1.10        # precio al que se ponen a la venta los tuyos

INJURED = ("injured", "suspended", "lesionado", "sancionado")

# ---- Parámetros que el bot ajusta solo (ver learn.py). Valores de fábrica, límites de seguridad
# que ningún ajuste puede superar, y los valores vivos que lee el resto del módulo.
DEFAULTS = {
    "league_offer_min": 1.05,      # umbral de venta de una oferta de la liga (× valor)
    "bid_base_premium": 0.03,      # prima base de las pujas sin competencia
    "invest_mult": 1.0,            # multiplicador del dinero dedicado a inversión
    "drift_strong_good": 0.25,     # revalorización esperada a 7 días por nivel (ver drift_tier)
    "drift_strong_mid": 0.15,
    "drift_strong_bad": 0.08,
    "drift_early": 0.08,
}
BOUNDS = {
    "league_offer_min": (1.02, 1.10),
    "bid_base_premium": (0.01, 0.08),
    "invest_mult": (0.3, 1.5),
    "drift_strong_good": (0.05, 0.40),
    "drift_strong_mid": (0.03, 0.30),
    "drift_strong_bad": (0.0, 0.20),
    "drift_early": (0.0, 0.20),
}
PARAMS: dict[str, float] = dict(DEFAULTS)


def apply_params(values: dict[str, float]) -> None:
    """Carga parámetros guardados, recortándolos siempre a sus límites de seguridad."""
    for key, value in values.items():
        if key in BOUNDS:
            lo, hi = BOUNDS[key]
            PARAMS[key] = min(hi, max(lo, float(value)))


def reset_params() -> None:
    PARAMS.clear()
    PARAMS.update(DEFAULTS)


def xpts(p: Player, form: dict[str, float] | None = None) -> float:
    """Puntos esperados por jornada: media de la temporada mezclada con la racha reciente.
    Un jugador sin puntos (media 0) casi no juega: vale muy poco, no una media inventada."""
    status = p.status.lower()
    if status in INJURED:
        return 0.0
    base = p.avg_points if p.avg_points > 0 else 0.5
    recent = (form or {}).get(p.id)
    if recent is not None and p.avg_points > 0:
        base = 0.6 * base + 0.4 * recent
    if status in ("doubtful", "duda"):
        base *= 0.55
    return round(base, 2)


def squad_value(players: list[Player], form: dict[str, float] | None = None, *, complete_bonus: bool = True) -> float:
    """Lo que vale una plantilla para puntuar: el mejor once legal + un poco de banquillo, y
    un bonus enorme si el once está completo (si no, la jornada entera puntúa cero)."""
    cands = [lineup.Candidate(p, 1.0, xpts(p, form)) for p in players if p.position_id in FIELD_POSITIONS]
    _, eleven, total = lineup.best_eleven(cands)
    starters = {id(c) for c in eleven}
    bench = sorted((c.xpts for c in cands if id(c) not in starters), reverse=True)[:BENCH_SLOTS]
    bonus = COMPLETE_XI_BONUS if complete_bonus and len(eleven) == 11 else 0.0
    return max(total, 0.0) + BENCH_WEIGHT * sum(bench) + bonus


@dataclass
class Move:
    kind: str                       # "clause" | "bid" | "invest" | "invest_clause" (comprar para revender, no para el once)
    player: Player
    cost: int
    gain: float = 0.0
    slot: SquadSlot | None = None   # cláusula: el hueco del rival
    item: MarketItem | None = None  # puja: el anuncio de LaLiga
    unlock_at: datetime | None = None  # cláusula que aún no se ha liberado: solo reserva saldo
    penalized: bool = False
    bonus: bool = False             # jugador del líder a precio justo (ver LEADER_FAIR_RATIO)
    rival_loss: float = 0.0         # pts/jornada que pierde el líder si se lo quitamos (ver leader_loss)
    score: float = 0.0              # solo "invest": fuerza del momentum (d3 + d7)
    drift: float = 0.0              # revalorización esperada a ~7 días (0,17 = +17%), ver expected_drift

    @property
    def executable_now(self) -> bool:
        return self.unlock_at is None


def clause_moves(
    rival_slots: list[SquadSlot], now: datetime, *, lookahead_hours: float = 24,
    freeze: tuple[datetime, datetime] | None = None,
    avoid_team_ids: frozenset[str] = frozenset(), leader_team_id: str = "",
    short_positions: frozenset[int] = frozenset(),
) -> list[Move]:
    """Cláusulas lógicas de rivales: pagables ya, o que se liberan dentro de `lookahead_hours`
    (esas no se ejecutan todavía, pero reservan su dinero para no gastarlo en otra cosa)."""
    frozen_now = bool(freeze and freeze[0] <= now < freeze[1])
    out = []
    for sl in rival_slots:
        p = sl.player
        if p.position_id not in FIELD_POSITIONS or not p.market_value or sl.clause <= 0:
            continue
        limit = SHORT_CLAUSE_RATIO if p.position_id in short_positions else MAX_CLAUSE_RATIO
        if sl.clause / p.market_value > limit or p.status.lower() in INJURED:
            continue
        if sl.clause_open(now):
            unlock = freeze[1] if frozen_now and freeze else None
        else:
            unlock = max((d for d in (sl.clause_locked_until, sl.shielded_until) if d), default=None)
            if unlock is None:
                continue
            if freeze and freeze[0] <= unlock < freeze[1]:
                unlock = freeze[1]
        if unlock is not None and (unlock - now).total_seconds() > lookahead_hours * 3600:
            continue
        fair_leader = bool(leader_team_id) and sl.owner_team_id == leader_team_id \
            and sl.clause <= p.market_value * LEADER_FAIR_RATIO
        if fair_leader and freeze and not frozen_now:
            strike = freeze[0] - STRIKE_MARGIN
            if now < strike and (strike - now).total_seconds() <= STRIKE_HORIZON_H * 3600 and (unlock is None or unlock <= strike):
                unlock = strike  # golpe justo antes de que se congelen las cláusulas
        out.append(Move("clause", p, sl.clause, slot=sl, unlock_at=unlock, bonus=fair_leader,
                        penalized=sl.owner_team_id in avoid_team_ids and not fair_leader))
    return out


def bid_moves(market: list[MarketItem], skip_player_ids: frozenset[str] = frozenset()) -> list[Move]:
    """Anuncios de LaLiga pujables (los de otros mánagers no son pujables entre nosotros)."""
    out = []
    for it in market:
        p = it.player
        if it.seller != "LaLiga" or not it.market_id or it.price <= 0 or it.my_bid:
            continue
        if p.position_id not in FIELD_POSITIONS or p.status.lower() in INJURED or p.id in skip_player_ids:
            continue
        out.append(Move("bid", p, it.price, item=it))
    return out


# Pujar al final (8/10/2026): el número de pujas de cada anuncio lo ven todos, así que pujar pronto
# avisa a los rivales (Aitor Fdez: el líder pagó +70% sobre un jugador en el que ya habíamos pujado).
# La pasada que arranca en los últimos 25 min antes del cierre espera dentro del mismo job y puja a
# falta de `LATE_BID_LEAD_S` (como las cláusulas al segundo). Si a falta de `BID_FALLBACK_S` aún no
# hay ninguna pasada en esa ventana (cron caído), se puja igualmente: mejor pronto que nunca.
LATE_BID_WINDOW_S = 25 * 60
LATE_BID_LEAD_S = 150
BID_FALLBACK_S = 0  # 0 = sin puja anticipada; ver `bid_timing`


def bid_timing(item: MarketItem, now: datetime) -> str:
    """"now" (pujar ya), "late" (esperar en este job hasta el último minuto) o "wait" (aún es pronto)."""
    if item.expires is None:
        return "now"
    left = (item.expires - now).total_seconds()
    if left <= LATE_BID_LEAD_S + 30:
        return "now"
    if left <= LATE_BID_WINDOW_S:
        return "late"
    return "now" if left <= BID_FALLBACK_S else "wait"


# Portero de reserva PROTEGIDO (10/10/2026). Sin portero no hay once legal y la jornada puntúa 0; hay gente
# que quita hasta tres porteros para dejar a un rival sin jugar (decisión del usuario: tener siempre uno de
# reserva aunque sea barato y no juegue, y renovarlo antes de que se pueda clausular). Una compra bloquea la
# cláusula del jugador 14 días, así que un portero comprado hace poco no se puede quitar: "protegido" = su
# cláusula sigue bloqueada (o blindada) cuando se congelen las cláusulas de la próxima jornada. Hace falta
# tener ≥2 porteros disponibles y ≥1 protegido; al acercarse el fin de su bloqueo se compra otro (rotación).
# Se elige el MÁS BARATO (no juega: la calidad no importa) y con paciencia: hasta 36 h antes de la congelación solo se compra si
# cuesta ≤0,8M (el mercado de LaLiga suele sacar algún portero de ~0,5M cada pocos días); a partir de ahí, el más barato de ≤3M.
# (10/10/2026: se pagaron 1,6M por Szczesny, que vale 0,94M y baja, habiendo un portero de 0,61M en el mercado.)
MIN_KEEPERS = 2
BACKUP_GK_MAX = 3_000_000        # coste máximo del portero de reserva (cláusula o puja), sea cual sea su ratio
CHEAP_KEEPER = 800_000
KEEPER_PATIENCE_H = 36


def keeper_cover(slots: list[SquadSlot], incoming: list[Player], freeze_start: datetime) -> tuple[int, int]:
    """(porteros disponibles, de ellos protegidos de un clausulazo hasta la congelación). Los que están
    en una puja viva cuentan como disponibles y protegidos (si se ganan, se bloquean 14 días)."""
    avail = prot = 0
    for sl in slots:
        if sl.player.position_id != 1 or not sl.player.available:
            continue
        avail += 1
        until = max((d for d in (sl.clause_locked_until, sl.shielded_until) if d), default=None)
        if until and until >= freeze_start:
            prot += 1
    for p in incoming:
        if p.position_id == 1 and p.available:
            avail += 1
            prot += 1
    return avail, prot


def backup_keeper_move(
    slots: list[SquadSlot], incoming: list[Player], market: list[MarketItem], rival_slots: list[SquadSlot],
    now: datetime, freeze: tuple[datetime, datetime] | None, budget: int,
) -> Move | None:
    """Fichaje de un portero barato si falta reserva o ninguno está protegido. Primero cláusulas abiertas
    (inmediatas; no se pueden pagar con las cláusulas congeladas) y el mercado de LaLiga: gana el MÁS BARATO."""
    freeze_start = freeze[0] if freeze else now + timedelta(days=7)
    avail, prot = keeper_cover(slots, incoming, freeze_start)
    if avail >= MIN_KEEPERS and prot >= 1:
        return None
    hours_left = (freeze_start - now).total_seconds() / 3600
    cap = min(BACKUP_GK_MAX, budget)
    if avail >= 1 and hours_left > KEEPER_PATIENCE_H:
        cap = min(cap, CHEAP_KEEPER)          # hay tiempo: se espera a un portero barato (sin ninguno, no se espera)
    owned = {sl.player.id for sl in slots} | {p.id for p in incoming}
    frozen_now = bool(freeze and freeze[0] <= now < freeze[1])
    options: list[tuple[int, float, int, Move]] = []
    if not frozen_now:
        for sl in rival_slots:
            p = sl.player
            if p.position_id == 1 and p.available and p.id not in owned and sl.clause_open(now) and 0 < sl.clause <= cap:
                options.append((-sl.clause, p.avg_points, 0, Move("clause", p, sl.clause, slot=sl)))
    for it in market:
        p = it.player
        if it.seller == "LaLiga" and it.market_id and not it.my_bid and p.position_id == 1 and p.available \
                and p.id not in owned and 0 < it.price <= cap:
            cost = min(bid_amount(it, 0.0), cap)
            options.append((-cost, p.avg_points, 0, Move("bid", p, cost, item=it)))
    return max(options, key=lambda o: o[:3])[3] if options else None


# Permutas (10/10/2026): "vender A para fichar B". Hasta ahora el bot solo liberaba capital vendiendo suplentes que no suben
# (`liquidity`) o plazas (`free_slot`), sin COMPARAR lo que rinde A con lo que rinde B. Aquí se compara con los mismos pesos del
# planificador: puntos del once durante GAIN_HORIZON jornadas + subida esperada, menos la prima y los márgenes de ida y vuelta.
# De momento solo AVISA (kv `swap_log` + Telegram, sin ejecutar): se activará cuando sus propuestas se vean razonables.
SWAP_MARGIN_M = 0.5            # la permuta debe ganar al menos 0,5M esperados
SWAP_SELL_SPREAD = 0.03        # coste de vender a una oferta típica (~0,97× el valor)


@dataclass
class Swap:
    sell: Player
    buy: Move
    edge_m: float                # ventaja esperada de la permuta (M€)
    keep_m: float                # lo que se pierde por no conservar a `sell` (puntos + subida)
    buy_net_m: float             # beneficio neto del fichaje


def swap_candidates(
    slots: list[SquadSlot], wanted: list[Move], trends: dict, form: dict[str, float] | None, free_cash: int, *,
    protected_ids: frozenset[str] = frozenset(), limit: int = 3,
) -> list[Swap]:
    """Mejores permutas: fichajes interesantes que no caben en el saldo libre, pagados vendiendo uno de los nuestros.
    El efecto en puntos sale de comparar el mejor once con y sin la permuta (así un titular o el único portero casi
    nunca sale, y un suplente que no puntúa y no sube, sí)."""
    mine = [sl.player for sl in slots]
    base = squad_value(mine, form)
    out: list[Swap] = []
    for m in wanted:
        if m.cost <= free_cash or not m.player.market_value:
            continue
        for sl in slots:
            a = sl.player
            if a.id in protected_ids or a.market_value + free_cash < m.cost or a.position_id not in FIELD_POSITIONS:
                continue
            roster = [x for x in mine if x.id != a.id] + [m.player]
            gain = squad_value(roster, form) - base                      # cambio TOTAL del once (incluye perder a `a`)
            tr = trends.get(a.id)
            drift_a = expected_drift(tr.d3, tr.d7, (form or {}).get(a.id)) if tr else 0.0
            keep_m = drift_a * a.market_value / 1e6 + SWAP_SELL_SPREAD * a.market_value / 1e6
            buy_net = net_value_m(gain, m.cost, m.player.market_value, m.drift, m.rival_loss)
            edge = buy_net - keep_m
            if edge >= SWAP_MARGIN_M:
                out.append(Swap(a, m, round(edge, 2), round(keep_m, 2), round(buy_net, 2)))
    out.sort(key=lambda s: -s.edge_m)
    seen_sell, seen_buy, picked = set(), set(), []
    for s in out:                                                        # una sola permuta por jugador vendido y por fichaje
        if s.sell.id in seen_sell or s.buy.player.id in seen_buy:
            continue
        seen_sell.add(s.sell.id); seen_buy.add(s.buy.player.id); picked.append(s)
    return picked[:limit]


def add_reserve_keeper(plan: list[Move], keeper: Move | None, n_mine: int, max_squad: int) -> tuple[list[Move], int]:
    """Pone el portero de reserva el PRIMERO del plan. Si no hay plaza, quita los últimos fichajes del plan (los
    menos eficientes; se volverán a plantear cuando haya hueco). Devuelve (plan, plazas que faltan): con eso
    `_resolve_offers` libera plazas vendiendo suplentes baratos (ver `offer_decision(free_slot=…)`)."""
    plan = list(plan)
    if keeper is None:
        return plan, 0
    missing = 0
    while n_mine + len(plan) + 1 > max_squad and plan:
        plan.pop()
        missing += 1
    if n_mine + len(plan) + 1 > max_squad:       # la plantilla ya está llena sin nada que quitar del plan
        return plan, missing + 1
    return [keeper] + plan, missing


@dataclass(frozen=True)
class RivalPremium:
    """Cuánto por encima del valor de mercado pagan los rivales en las pujas que ganan
    (1.09 = +9%), aprendido de la actividad de la liga (ver service.rival_bid_premium)."""
    median: float
    p75: float


def bid_amount(item: MarketItem, gain: float, rivals: RivalPremium | None = None) -> int:
    """Pujar para ganar sin regalar dinero: casi todos los anuncios tienen 0 pujas, así que el
    empuje fuerte solo se paga cuando YA hay otra puja compitiendo; entonces, al menos lo que
    suelen pagar los rivales (mediana). Techo: +12% (lo que pagas de más sobre el valor es
    pérdida inmediata: al revender, lo máximo que se saca es ~el valor)."""
    overbid = PARAMS["bid_base_premium"]
    if gain >= 3.0:
        overbid += 0.03
    if item.bids > 0:
        overbid += 0.05
        if rivals and gain >= 1.5:
            overbid = max(overbid, rivals.median - 1)
    return round(item.price * (1 + min(overbid, MAX_OVERBID)))


def is_falling(d3: float, d7: float) -> bool:
    """Valor de mercado en caída (cambio % a 3 y 7 días): no se ficha, porque mañana valdrá
    menos de lo que pagas (Gueye: -9,5% en una semana)."""
    return d3 <= -3 or d7 <= -6


FORM_GOOD = 6.0   # pts/jornada de media en las últimas jornadas: buena forma
FORM_BAD = 2.0


def drift_tier(d3: float, d7: float, form: float | None) -> str | None:
    """En qué nivel de "va a subir" está un jugador (cada nivel tiene su revalorización esperada)."""
    if d3 >= 4 and d7 >= 6:
        if form is None:
            return "strong_mid"
        return "strong_good" if form >= FORM_GOOD else "strong_bad" if form < FORM_BAD else "strong_mid"
    if d3 >= 1.5 and form is not None and form >= FORM_GOOD:
        return "early"
    return None


# Revalorización esperada de un jugador que baja algo en 7 días sin llegar a "en caída" (`is_falling`).
# Datos de la liga (8/10/2026, las 83 compras de los 4 mánagers con 14 días de recorrido): con la
# semana previa en negativo, el valor a 14 días cae un 9% (mediana) y solo el 18% acaba ganando;
# entre 0 y +10%, +1,5%; desde +10%, +23% y más. Se usa la mitad de esa caída, por prudencia.
DRIFT_DECLINING = -0.05


def expected_drift(d3: float, d7: float, form: float | None = None) -> float:
    """Revalorización esperada a ~7 días (valores de fábrica de la prueba histórica del 4/10/2026,
    300 jugadores y 4 jornadas; el bot los recalibra cada semana, ver learn.calibrate_drift):
    - subida fuerte (≥4%/3d y ≥6%/7d) con buena forma: +30% (gana el 95%); sin forma: +16%; con
      forma floja (<2 pts): +8%.
    - subida suave (≥1,5%/3d) pero con buena forma: +8% — entrada anticipada, "dos o tres
      partidos buenos y el precio aún no ha saltado" (con precio plano y sin subida, solo +3%).
    - subida suave sin forma que la respalde: nada.
    - bajando en la semana (sin llegar a caída): `DRIFT_DECLINING` (−5%), coste para el fichaje."""
    tier = drift_tier(d3, d7, form)
    if tier:
        return PARAMS[f"drift_{tier}"]
    return DRIFT_DECLINING if d7 < 0 else 0.0


def net_value_m(gain: float, cost: int, value: int, drift: float, rival_loss: float = 0.0) -> float:
    """Beneficio neto esperado (M€) de un fichaje: lo que suma al once durante `GAIN_HORIZON` jornadas (+ lo que le quita al
    líder) + lo que se espera que se revalorice, menos lo que se pierde de ida y vuelta (prima pagada + margen al revender)."""
    cost_m = cost / 1_000_000
    premium = max(0.0, cost / value - 1) if value else 0.0
    return (gain * GAIN_HORIZON + rival_loss) * POINT_VALUE_M + drift * cost_m - (premium + RESALE_SPREAD) * cost_m


# Tope de prima en cláusulas (10/10/2026). La cláusula de un rival es lo que él pagó (o el valor): si pagó de más, pagas de más.
# Nuestras compras con prima ≥13% (Johnny +19%, Terrats +14%, Deossa +13%) subieron un 13–15% desde el día de compra y aun así
# quedaron en −4%/0%/0% frente a lo pagado; las de prima 0% dieron +3% a +22%. En ligas simuladas con todos los jugadores, el
# punto de equilibrio de pagar prima incluso por jugadores en subida está en ~1,14×. Solo se acepta más del 10% si suma ≥3 pts.
MAX_CLAUSE_PREMIUM = 0.10
PREMIUM_OVERRIDE_GAIN = 3.0


def plan_acquisitions(
    mine: list[Player], moves: list[Move], budget: int, *,
    form: dict[str, float] | None = None, max_squad: int = 16, rivals: RivalPremium | None = None,
) -> list[Move]:
    """Cartera de compras: en cada paso elige la que más puntos suma por recurso gastado (con
    penalización si alimenta al líder o es venganza), la añade a la plantilla simulada y
    vuelve a calcular — así dos delanteros no "mejoran" el mismo hueco dos veces. Para cuando
    no queda saldo, la plantilla está llena o nada mejora al menos `MIN_GAIN`.

    Los recursos son DOS: dinero y plazas de plantilla. Con mucho saldo, lo escaso son las
    plazas: cada plaza libre "cuesta" su parte del presupuesto que queda, para que un jugador
    barato y flojo no ocupe el sitio de uno bueno solo por ser barato.
    Incluye las cláusulas que se liberan pronto: no se ejecutan ahora, pero reservan dinero."""
    roster = list(mine)
    pool = [m for m in moves if m.player.id not in {p.id for p in mine}]
    chosen: list[Move] = []
    left = budget
    while pool and len(roster) < max_squad:
        base = squad_value(roster, form)
        slot_cost = left / 1_000_000 / (max_squad - len(roster))
        best: tuple[float, Move, float, int] | None = None
        for m in pool:
            gain = squad_value(roster + [m.player], form) - base
            if gain + m.rival_loss < MIN_GAIN:
                continue
            cost = bid_amount(m.item, gain, rivals) if m.kind == "bid" and m.item else m.cost
            if cost > left:
                continue
            # Beneficio neto en M: lo que suma al once durante unas jornadas + lo que se revaloriza,
            # menos lo que se pierde de ida y vuelta (prima pagada sobre el valor + margen al revender).
            # Así no se paga un 19% de más (Johnny) por +0,6 pts/jornada.
            cost_m, value = cost / 1_000_000, m.player.market_value
            premium = max(0.0, cost / value - 1) if value else 0.0
            if m.kind == "clause" and premium > MAX_CLAUSE_PREMIUM and gain < PREMIUM_OVERRIDE_GAIN and not m.bonus:
                continue   # prima alta sin una mejora real del once: se la come la prima (ver MAX_CLAUSE_PREMIUM)
            net_m = net_value_m(gain, cost, value, m.drift, m.rival_loss)
            if net_m <= 0:
                continue
            eff = net_m / (cost_m + slot_cost + 0.25) * (PENALTY_FACTOR if m.penalized else 1.0)
            if best is None or eff > best[0]:
                best = (eff, m, gain, cost)
        if best is None:
            break
        _, pick, gain, cost = best
        pick.gain, pick.cost = round(gain, 2), cost
        chosen.append(pick)
        roster.append(pick.player)
        left -= pick.cost
        pool = [m for m in pool if m.player.id != pick.player.id]
    return chosen


# Crédito para inversión (8/10/2026). El saldo solo cuenta al EMPEZAR la jornada (negativo = 0 puntos esa
# jornada; durante la jornada da igual) y el juego deja deber hasta el 20% del valor de la plantilla. Entre
# jornadas normales no compensa (3 días de subida no pagan la ida y vuelta y un fallo cuesta una jornada
# entera), pero en un parón (≥7 días sin jornada) sí: la subida de 7-10 días (+17%/7d en la prueba
# histórica) paga de sobra el ~5-6% de ida y vuelta. Se pide solo con ≥`LEVER_OPEN_H` hasta la jornada y
# se devuelve vendiendo desde `DELEVER_H` antes, cada vez con menos exigencia (`delever_min`).
LEVER_OPEN_H = 7 * 24
DELEVER_H = 72


def credit_room(squad_value: int, cash_after_bids: int, hours_to_start: float | None, pct: float) -> int:
    """Crédito que aún se puede usar para inversión ahora mismo (0 si no es un parón largo)."""
    if pct <= 0 or hours_to_start is None or hours_to_start < LEVER_OPEN_H:
        return 0
    return max(0, int(pct * squad_value - max(0, -cash_after_bids)))


def delever_min(hours_to_start: float | None) -> float | None:
    """Mínimo (× valor) que se acepta por una oferta cuando hay que volver a saldo positivo antes de la
    jornada: nada que hacer lejos de ella; cuanto más cerca, menos exigente (0 puntos es mucho peor)."""
    if hours_to_start is None:
        return 0.94
    if hours_to_start > DELEVER_H:
        return None
    if hours_to_start > 48:
        return 0.98
    if hours_to_start > 24:
        return 0.94
    return 0.85


def leader_loss(leader: list[Player], player_id: str, form: dict[str, float] | None = None) -> float:
    """Puntos por jornada que pierde el líder sin ese jugador (incluye el castigo de quedarse sin
    once completo, `COMPLETE_XI_BONUS`): la otra mitad del "doble efecto" de quitárselo."""
    rest = [p for p in leader if p.id != player_id]
    return round(max(0.0, squad_value(leader, form) - squad_value(rest, form)), 2)


def sale_loss(mine: list[Player], player_id: str, form: dict[str, float] | None = None) -> float:
    """Cuántos pts/jornada pierde tu equipo si se va este jugador (sin el bonus de once
    completo: si romperlo importa o no depende de lo cerca que esté la jornada, ver
    `breaks_eleven` / `offer_decision`)."""
    rest = [p for p in mine if p.id != player_id]
    return round(squad_value(mine, form, complete_bonus=False) - squad_value(rest, form, complete_bonus=False), 2)


def complete_eleven(players: list[Player]) -> bool:
    return _complete(players)


def _complete(players: list[Player]) -> bool:
    cands = [lineup.Candidate(p, 1.0, 1.0) for p in players if p.position_id in FIELD_POSITIONS]
    return len(lineup.best_eleven(cands)[1]) == 11


def breaks_eleven(mine: list[Player], player_id: str) -> bool:
    return _complete(mine) and not _complete([p for p in mine if p.id != player_id])


def hours_until_exposed(slot: SquadSlot, now: datetime) -> float | None:
    """Horas hasta que un rival pueda clausular a tu jugador (0 = ya puede), o None si su
    cláusula es tan alta que no es un objetivo lógico para nadie."""
    p = slot.player
    if not p.market_value or slot.clause <= 0 or slot.clause / p.market_value > MAX_CLAUSE_RATIO:
        return None
    if slot.clause_open(now):
        return 0.0
    opens = max((d for d in (slot.clause_locked_until, slot.shielded_until) if d), default=None)
    return max((opens - now).total_seconds() / 3600, 0.0) if opens else None


def at_risk_min(hours_left: float, key: bool) -> float:
    """Mínimo exigido a una oferta de la liga por un jugador cuya protección acaba pronto:
    baja de 1.03x (a 3 días) a 0.98x (último día), para tener varias oportunidades de una
    buena oferta sin llegar a perderlo gratis por una cláusula."""
    frac = min(1.0, max(0.0, (hours_left - 24) / (AT_RISK_HOURS - 24)))
    need = AT_RISK_OFFER_LAST + (AT_RISK_OFFER_START - AT_RISK_OFFER_LAST) * frac
    return round(need + (AT_RISK_KEY_EXTRA if key else 0.0), 3)


# Salida al frenarse una subida (10/10/2026). Datos de LaLiga Fantasy (476 jugadores, valores diarios): de los que habían
# subido (>+5% en 7 días), si el último día el valor queda plano el valor cae de media un 6% en los 7 días siguientes (y un 12%
# si ese día ya baja); esperar a una oferta de 1,05× (llega el 22% de los días) pierde frente a vender a la primera oferta ≥1,00×
# (+3,7% medio, p10 −0,9%, frente a −6,3% por esperar). La venta por caída de antes (≥4% en 3 días) llegaba tarde.
STALL_D7 = 5.0                  # había subido: ≥+5% en 7 días
STALL_D1 = 0.4                  # y el último día ya no sube (≤ +0,4%)
STALL_EXIT_MIN = 1.00           # se vende a la primera oferta ≥ su valor, sin mirar lo pagado (es dinero ya perdido)
STALL_MIN_VALUE = 3_000_000     # por debajo, los valores se mueven a saltos y "plano" no significa nada


def is_stalled(trend_d1: float | None, trend_d7: float, value: int) -> bool:
    return trend_d1 is not None and value >= STALL_MIN_VALUE and trend_d7 > STALL_D7 and trend_d1 <= STALL_D1


def offer_decision(
    offer: Offer, player: Player, *, loss: float, cut_loss: bool = False, trend_d7: float = 0.0, trend_d3: float = 0.0,
    breaks_xi: bool = False, hours_to_deadline: float | None = None, exposed_in: float | None = None,
    squad_full: bool = False, cost_basis: int | None = None, no_sell: bool = False, liquidity: bool = False,
    injured: bool = False, clause: int = 0, reserve_keeper: bool = False, free_slot: bool = False,
    trend_d1: float | None = None,
) -> tuple[str, str]:
    """("accept" | "reject" | "hold", motivo). "hold" = no hacer nada y dejar que caduque.
    `no_sell`: jugador de una operación en curso (bloqueo al líder): no se vende todavía."""
    value = player.market_value
    if no_sell:
        return "hold", "forma parte de la operación bloqueo: no se vende antes de la jornada"
    ratio = offer.money / value if value else 0.0
    if not offer.is_system:
        if ratio >= RIVAL_OFFER_MIN:
            return "accept", f"oferta de {offer.from_manager} excepcional (x{ratio:.2f} el valor)"
        return "reject", f"oferta de {offer.from_manager} (x{ratio:.2f} el valor): las de rivales casi nunca convienen"
    if reserve_keeper:
        return "hold", "portero de reserva: hace falta para tener siempre un once legal (y rotarlo antes de que se pueda clausular)"
    if breaks_xi and (hours_to_deadline is None or hours_to_deadline < 48):
        return "hold", "venderlo ahora te dejaría sin 11 para la jornada"
    key = loss >= KEY_PLAYER_LOSS
    stalled = is_stalled(trend_d1, trend_d7, value) and not key and not no_sell
    at_risk = exposed_in is not None and exposed_in <= AT_RISK_HOURS
    if at_risk:
        need = max(at_risk_min(exposed_in, key), clause / value if clause and value else 0.0)
        cuando = "ya es clausulable" if exposed_in == 0 else f"su protección acaba en {exposed_in:.0f}h"
        why = f"{cuando}: solo lo vendo si la oferta supera lo que cobraría si me lo clausulan ({clause / 1e6:.2f}M)" if clause \
            else f"{cuando}: mejor venderlo que ver cómo se lo lleva un rival"
    elif injured:
        # Lesionado: no puntúa y su valor puede caer cuando se enfríe lo que hizo antes. Se cobra a
        # ~su valor (siempre sin bajar de lo pagado) en vez de esperar una subida que ya no usa.
        need, why = INJURED_OFFER_MIN, "lesionado (no puntúa): cobro lo ganado"
    elif key:
        need, why = KEY_PLAYER_OFFER_MIN, "jugador clave"
    elif loss >= STARTER_LOSS and hours_to_deadline is not None and hours_to_deadline < 48:
        need, why = KEY_PLAYER_OFFER_MIN, "titular y la jornada empieza en <48h, sin tiempo de reponerlo"
    elif stalled:
        need, why = STALL_EXIT_MIN, f"se ha frenado tras subir (+{trend_d7:.0f}% en 7 días, hoy {trend_d1:+.1f}%): tiende a caer, salgo"
    elif cut_loss:
        need, why = CUT_LOSS_OFFER_MIN, "en caída/lesionado, conviene salir"
    elif liquidity and loss < BENCH_LOSS and trend_d7 <= 5:
        # Rotación de capital: hay una inversión en subida que no se puede pagar. Un suplente que
        # no sube se vende a ~su valor aunque sea por debajo de lo pagado (reinvertido rinde +8-25%).
        return ("accept", f"libero capital para una inversión en subida: x{ratio:.2f} el valor") if ratio >= LIQUIDITY_OFFER_MIN \
            else ("hold", f"x{ratio:.2f} el valor, para liberar capital exijo x{LIQUIDITY_OFFER_MIN:.2f}")
    elif free_slot and loss < BENCH_LOSS:
        # Hace falta una plaza para un fichaje necesario (portero de reserva, defensa para completar el once): se
        # vende un suplente barato aunque esté subiendo (la plaza vale más que su subida), sin bajar de lo pagado.
        need, why = BENCH_OFFER_MIN, "libero una plaza para un fichaje necesario"
    elif squad_full and loss < BENCH_LOSS:
        need, why = BENCH_OFFER_MIN, "suplente con la plantilla llena: libera sitio para un fichaje mejor"
    else:
        need, why = PARAMS["league_offer_min"], "oferta por encima de su valor"
    if trend_d3 > RISING_D3 and trend_d7 > 5 and not injured and not stalled and not (free_slot and loss < BENCH_LOSS):
        # También cerca de que se abra su cláusula (8/10/2026): si un rival lo clausula, cobras su
        # cláusula, que sube con su valor; venderlo antes regala la subida que queda.
        # La técnica (Josinho con Yamal): esperar a que suba. Prueba histórica (4/10/2026): comprar
        # una subida y mantener hasta que se frena rinde +72% de media (mediana +21%, ~19 días);
        # vender a los 7 días, solo +17%. Mientras sigue subiendo no se vende (las ofertas no pasan de ~1,13×).
        need, why = max(need, RISING_HOLD_MIN), f"sigue subiendo ({trend_d3:+.1f}% en 3 días): espero a que se frene"
    if cost_basis and value and not cut_loss and not stalled:
        # Nunca por debajo de lo que costó, tampoco por riesgo de cláusula (decisión del
        # usuario, 4/10/2026: mejor que te paguen la cláusula que vender con pérdida). Solo
        # se sale con pérdida si está lesionado o cayendo (`cut_loss`).
        if cost_basis / value > need:
            need, why = cost_basis / value, f"{why}; no vendo por debajo de lo que pagué ({cost_basis / 1e6:.2f}M)"
    if ratio >= need:
        return "accept", f"{why}: x{ratio:.2f} el valor (mínimo x{need:.2f})"
    return "hold", f"x{ratio:.2f} el valor, exijo x{need:.2f} ({why})"


def fixture_factor(home: bool | None, rival_rank: int | None, n_teams: int = 20, position: int | None = None) -> float:
    """Multiplicador de puntos esperados para la próxima jornada: casa/fuera y lo fuerte que es el
    rival (los 4 primeros de la tabla, ×0,80; del 5.º al último, de ×0,92 a ×1,08). Defensas, 1,5× más sensibles."""
    k = DEFENDER_SENSITIVITY if position == 2 else 1.0
    factor = 1.0
    if home is not None:
        factor *= HOME_FACTOR if home else 2 - HOME_FACTOR
    if rival_rank and n_teams > 1:
        if rival_rank <= TOP_RANK_N:
            factor *= 1 - (1 - TOP_RANK_FACTOR) * k
        else:
            d = RIVAL_DIFFICULTY * k
            factor *= 1 - d + 2 * d * (rival_rank - 1) / (n_teams - 1)
    return round(factor, 3)


# Experimento (4/10/2026): ¿la oferta depende del valor actual, del valor al poner en venta o del
# precio que pides? Dos jugadores baratos se anuncian a otro múltiplo durante una semana y el bot
# registra las ofertas (`python3 -m fantasy_agent offers`). El resto, al múltiplo normal.
ASK_EXPERIMENT = {"3239": 2.0, "2934": 1.5}      # id (Mayol, Freeman) -> múltiplo del valor
EXPERIMENT_UNTIL = datetime(2026, 10, 12, tzinfo=timezone.utc)
RELIST_RISE = 1.10                                # se reanuncia si el valor sube un 10% desde que se anunció
RELIST_TOO_HIGH = 1.40


def ask_multiplier(player_id: str, now: datetime) -> float:
    return ASK_EXPERIMENT.get(player_id, LISTING_MARKUP) if now < EXPERIMENT_UNTIL else LISTING_MARKUP


def listing_price(player: Player, now: datetime | None = None) -> int:
    mult = ask_multiplier(player.id, now or datetime.now(timezone.utc))
    return round(player.market_value * mult)


def needs_relist(ask: int, value_now: int, mult: float) -> bool:
    """El anuncio quedó viejo: el valor ha subido ≥10% desde que se puso (precio/valor < mult/1,1)
    o se ha desplomado (precio/valor > mult×1,4)."""
    if not value_now or ask <= 0:
        return False
    ratio = ask / value_now
    return ratio < mult / RELIST_RISE or ratio > mult * RELIST_TOO_HIGH


LINEUP_VARIANTS = ("flat_snake", "flat", "nested")  # flat_snake: verificada en vivo el 26/09/2026


def lineup_retry_seconds(hours_to_deadline: float | None) -> int:
    """Cuánto esperar para reintentar guardar la alineación tras un fallo: a menos de 12 h del primer
    partido hay que insistir en cada pasada (15 min); lejos del plazo, no hace falta (6 h)."""
    return 900 if hours_to_deadline is not None and 0 < hours_to_deadline <= 12 else 6 * 3600


def lineup_payload(formation: tuple[int, int, int], ids_by_pos: dict[int, list[str]], variant: str) -> dict:
    """Cuerpo del `PUT /teams/{id}/lineup` (ids = `playerTeamId`). Verificada en vivo la
    "flat_snake" (`tactical_formation`); las otras quedan como alternativa por si cambia la API
    — `cli._apply_lineup` las prueba en orden y recuerda la que de verdad guarda."""
    gk = ids_by_pos.get(1, [])
    slots = {"defender": ids_by_pos.get(2, []), "midfield": ids_by_pos.get(3, []), "striker": ids_by_pos.get(4, [])}
    tactical = list(formation)
    if variant == "flat":
        return {"goalkeeper": gk[0] if gk else None, **slots, "tacticalFormation": tactical}
    if variant == "flat_snake":
        return {"goalkeeper": gk[0] if gk else None, **slots, "tactical_formation": tactical}
    if variant == "nested":
        return {"formation": {"goalkeeper": gk, **slots, "tacticalFormation": tactical}}
    raise ValueError(variant)


def lineup_ids(lineup_json: dict) -> set[str]:
    """playerTeamIds alineados según el GET de la alineación."""
    f = (lineup_json or {}).get("formation") or {}
    out = set()
    for key in ("goalkeeper", "defender", "midfield", "striker"):
        for slot in f.get(key) or []:
            if isinstance(slot, dict) and slot.get("playerTeamId"):
                out.add(str(slot["playerTeamId"]))
    return out


# ---------- inversión: comprar lo que sube para revenderlo ----------
# Prueba histórica (4/10/2026, 201 jugadores, ~80 días de valores de mercado): comprar un
# jugador que ha subido ≥4% en 3 días y ≥6% en 7 y revenderlo 7 días después rinde de media
# +17% (gana el 89% de las veces); uno que cae ≥4% en 3 días pierde un -12%. El valor de
# mercado tiene inercia: lo que sube sigue subiendo unos días.
MOMENTUM_D3 = 4.0
MOMENTUM_D7 = 6.0
INVEST_MAX_PRICE_RATIO = 1.06    # el precio de salida debe estar a ≤6% sobre el valor
CLAUSE_INVEST_MAX_RATIO = 1.08   # cláusulas de rivales: la cláusula debe estar a ≤8% sobre el valor
INVEST_FRACTION_NORMAL = 0.25    # parte del saldo libre que se dedica a inversión
INVEST_FRACTION_BREAK = 0.60     # en un parón no hay once que puntuar: más a invertir
INVEST_MAX_SHARE = 0.40          # máximo por jugador, sobre el presupuesto de inversión


def invest_moves(market: list[MarketItem], trends: dict, skip_player_ids: frozenset[str] = frozenset(),
                 form: dict[str, float] | None = None) -> list[Move]:
    """Anuncios de LaLiga de jugadores en subida (`trends`: id -> Trend; `form`: id -> pts de media
    en las últimas jornadas): subida fuerte, o suave pero respaldada por buena forma."""
    out = []
    for it in market:
        p = it.player
        tr = trends.get(p.id)
        if tr is None or it.seller != "LaLiga" or not it.market_id or it.my_bid or it.price <= 0 or not p.market_value:
            continue
        if p.position_id not in FIELD_POSITIONS or p.status.lower() in INJURED or p.id in skip_player_ids:
            continue
        if it.price > p.market_value * INVEST_MAX_PRICE_RATIO:
            continue
        drift = expected_drift(tr.d3, tr.d7, (form or {}).get(p.id))
        net = drift - max(0.0, it.price / p.market_value - 1) - RESALE_SPREAD
        if drift >= 0.08 and net >= 0.03:
            out.append(Move("invest", p, it.price, item=it, drift=drift, score=round(net * 100 + (tr.d3 + tr.d7) / 10, 1)))
    return sorted(out, key=lambda m: -m.score)


def clause_invest_moves(
    rival_slots: list[SquadSlot], trends: dict, now: datetime, *, freeze: tuple[datetime, datetime] | None = None,
    lookahead_hours: float = 24, avoid_team_ids: frozenset[str] = frozenset(),
    skip_player_ids: frozenset[str] = frozenset(), form: dict[str, float] | None = None, leader_team_id: str = "",
) -> list[Move]:
    """Cláusulas de rivales (abiertas o que se abren en <24 h) de jugadores en subida:
    es lo que han hecho los rivales para hacer dinero (Josinho +76M sin vender nada). La cláusula
    acompaña al valor, así que la ganancia viene solo de la inercia: se compra lo que ya sube."""
    out = []
    for m in clause_moves(rival_slots, now, lookahead_hours=lookahead_hours, freeze=freeze, avoid_team_ids=avoid_team_ids,
                          leader_team_id=leader_team_id):
        p, tr = m.player, trends.get(m.player.id)
        if tr is None or p.id in skip_player_ids or m.cost > p.market_value * CLAUSE_INVEST_MAX_RATIO:
            continue
        drift = expected_drift(tr.d3, tr.d7, (form or {}).get(p.id))
        net = drift - max(0.0, m.cost / p.market_value - 1) - RESALE_SPREAD
        if drift >= 0.08 and net >= 0.03:
            m.kind, m.drift = "invest_clause", drift
            m.score = round(net * 100 + (tr.d3 + tr.d7) / 10 - (10 if m.penalized else 0) + (5 if m.bonus else 0), 1)
            out.append(m)
    return sorted(out, key=lambda m: -m.score)


def plan_investments(moves: list[Move], budget: int, slots: int) -> list[Move]:
    """Las de más momentum primero, sin pasar de INVEST_MAX_SHARE del presupuesto por jugador
    ni de las plazas libres de la plantilla."""
    chosen: list[Move] = []
    left, cap = budget, int(budget * INVEST_MAX_SHARE)
    for m in sorted(moves, key=lambda m: -m.score):
        if len(chosen) >= slots:
            break
        cost = bid_amount(m.item, 0.0) if m.item else m.cost
        if cost > left or cost > cap:
            continue
        m.cost = cost
        chosen.append(m)
        left -= cost
    return chosen
