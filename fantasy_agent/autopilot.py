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
from datetime import datetime

from . import lineup
from .models import MarketItem, Offer, Player, SquadSlot

FIELD_POSITIONS = (1, 2, 3, 4)
MAX_CLAUSE_RATIO = 1.2       # cláusula "lógica": ≤1.2x el valor de mercado
MIN_GAIN = 0.5               # pts/jornada que como mínimo debe sumar una compra
COMPLETE_XI_BONUS = 15.0     # completar el once pesa más que cualquier fichaje
BENCH_WEIGHT = 0.15          # los suplentes cuentan algo (lesiones, rotaciones)
BENCH_SLOTS = 4
PENALTY_FACTOR = 0.6         # clausular al líder o por venganza: se puede, con menos prioridad
MAX_OVERBID = 0.20           # nunca pujar más de +20% sobre el precio de salida

LEAGUE_OFFER_MIN = 1.05      # oferta de la liga: vender desde +5% sobre el valor
CUT_LOSS_OFFER_MIN = 0.97    # jugador en caída/lesionado: salir aunque sea a ~valor
KEY_PLAYER_OFFER_MIN = 1.25  # jugador clave: solo por una oferta muy alta
KEY_PLAYER_LOSS = 3.0        # "clave" = quitarlo baja el once ≥3 pts/jornada
STARTER_LOSS = 1.0           # titular: a <48h de la jornada solo se vende por mucho
BENCH_LOSS = 0.5             # suplente que apenas suma
BENCH_OFFER_MIN = 0.97       # con la plantilla llena, un suplente se vende a ~su valor
HOME_FACTOR = 1.05           # jugar en casa suma algo, fuera resta algo
RIVAL_DIFFICULTY = 0.10      # ±10% según la posición del rival en la tabla de LaLiga
RIVAL_OFFER_MIN = 1.30       # ofertas de rivales: casi nunca convienen
AT_RISK_HOURS = 72           # se empieza a intentar vender 3 días antes de que acabe su
# protección: la liga genera una oferta al día (~20:53), así hay 3 oportunidades
AT_RISK_OFFER_START = 1.03   # a 3 días: solo una buena oferta...
AT_RISK_OFFER_LAST = 0.98    # ...el último día: ~su valor, antes que perderlo por cláusula
AT_RISK_KEY_EXTRA = 0.07     # un jugador clave exige un poco más en todo el tramo
LISTING_MARKUP = 1.10        # precio al que se ponen a la venta los tuyos

INJURED = ("injured", "suspended", "lesionado", "sancionado")


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
    kind: str                       # "clause" | "bid"
    player: Player
    cost: int
    gain: float = 0.0
    slot: SquadSlot | None = None   # cláusula: el hueco del rival
    item: MarketItem | None = None  # puja: el anuncio de LaLiga
    unlock_at: datetime | None = None  # cláusula que aún no se ha liberado: solo reserva saldo
    penalized: bool = False

    @property
    def executable_now(self) -> bool:
        return self.unlock_at is None


def clause_moves(
    rival_slots: list[SquadSlot], now: datetime, *, lookahead_hours: float = 24,
    freeze: tuple[datetime, datetime] | None = None,
    avoid_team_ids: frozenset[str] = frozenset(),
) -> list[Move]:
    """Cláusulas lógicas de rivales: pagables ya, o que se liberan dentro de `lookahead_hours`
    (esas no se ejecutan todavía, pero reservan su dinero para no gastarlo en otra cosa)."""
    frozen_now = bool(freeze and freeze[0] <= now < freeze[1])
    out = []
    for sl in rival_slots:
        p = sl.player
        if p.position_id not in FIELD_POSITIONS or not p.market_value or sl.clause <= 0:
            continue
        if sl.clause / p.market_value > MAX_CLAUSE_RATIO or p.status.lower() in INJURED:
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
        out.append(Move("clause", p, sl.clause, slot=sl, unlock_at=unlock,
                        penalized=sl.owner_team_id in avoid_team_ids))
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


@dataclass(frozen=True)
class RivalPremium:
    """Cuánto por encima del valor de mercado pagan los rivales en las pujas que ganan
    (1.09 = +9%), aprendido de la actividad de la liga (ver service.rival_bid_premium)."""
    median: float
    p75: float


def bid_amount(item: MarketItem, gain: float, rivals: RivalPremium | None = None) -> int:
    """Pujar para ganar, sin pagar disparates: más empuje cuanto más mejora tu once y si ya
    hay otras pujas compitiendo. Para los fichajes que más mejoran el once, al menos lo que
    suelen pagar los rivales (mediana; percentil 75 si mejora ≥3 pts). Techo: +20%."""
    overbid = 0.05
    if gain >= 1.5:
        overbid += 0.05
    if gain >= 3.0:
        overbid += 0.05
    if item.bids > 0:
        overbid += 0.05
    if rivals and gain >= 1.5:
        overbid = max(overbid, (rivals.p75 if gain >= 3.0 else rivals.median) - 1)
    return round(item.price * (1 + min(overbid, MAX_OVERBID)))


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
            if gain < MIN_GAIN:
                continue
            cost = bid_amount(m.item, gain, rivals) if m.kind == "bid" and m.item else m.cost
            if cost > left:
                continue
            eff = gain / (cost / 1_000_000 + slot_cost + 0.25) * (PENALTY_FACTOR if m.penalized else 1.0)
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


def sale_loss(mine: list[Player], player_id: str, form: dict[str, float] | None = None) -> float:
    """Cuántos pts/jornada pierde tu equipo si se va este jugador (sin el bonus de once
    completo: si romperlo importa o no depende de lo cerca que esté la jornada, ver
    `breaks_eleven` / `offer_decision`)."""
    rest = [p for p in mine if p.id != player_id]
    return round(squad_value(mine, form, complete_bonus=False) - squad_value(rest, form, complete_bonus=False), 2)


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


def offer_decision(
    offer: Offer, player: Player, *, loss: float, cut_loss: bool = False, trend_d7: float = 0.0,
    breaks_xi: bool = False, hours_to_deadline: float | None = None, exposed_in: float | None = None,
    squad_full: bool = False,
) -> tuple[str, str]:
    """("accept" | "reject" | "hold", motivo). "hold" = no hacer nada y dejar que caduque."""
    value = player.market_value
    ratio = offer.money / value if value else 0.0
    if not offer.is_system:
        if ratio >= RIVAL_OFFER_MIN:
            return "accept", f"oferta de {offer.from_manager} excepcional (x{ratio:.2f} el valor)"
        return "reject", f"oferta de {offer.from_manager} (x{ratio:.2f} el valor): las de rivales casi nunca convienen"
    if breaks_xi and (hours_to_deadline is None or hours_to_deadline < 48):
        return "hold", "venderlo ahora te dejaría sin 11 para la jornada"
    key = loss >= KEY_PLAYER_LOSS
    at_risk = exposed_in is not None and exposed_in <= AT_RISK_HOURS
    if at_risk:
        need = at_risk_min(exposed_in, key)
        cuando = "ya es clausulable" if exposed_in == 0 else f"su protección acaba en {exposed_in:.0f}h"
        why = f"{cuando}: mejor venderlo que ver cómo se lo lleva un rival"
    elif key:
        need, why = KEY_PLAYER_OFFER_MIN, "jugador clave"
    elif loss >= STARTER_LOSS and hours_to_deadline is not None and hours_to_deadline < 48:
        need, why = KEY_PLAYER_OFFER_MIN, "titular y la jornada empieza en <48h, sin tiempo de reponerlo"
    elif cut_loss:
        need, why = CUT_LOSS_OFFER_MIN, "en caída/lesionado, conviene salir"
    elif squad_full and loss < BENCH_LOSS:
        need, why = BENCH_OFFER_MIN, "suplente con la plantilla llena: libera sitio para un fichaje mejor"
    else:
        need, why = LEAGUE_OFFER_MIN, "oferta por encima de su valor"
    if trend_d7 > 5 and not at_risk:
        need += min(trend_d7 / 100, 0.15)  # si está subiendo rápido, en días vale más que la oferta
    if ratio >= need:
        return "accept", f"{why}: x{ratio:.2f} el valor (mínimo x{need:.2f})"
    return "hold", f"x{ratio:.2f} el valor, exijo x{need:.2f} ({why})"


def fixture_factor(home: bool | None, rival_rank: int | None, n_teams: int = 20) -> float:
    """Multiplicador de puntos esperados para la próxima jornada: casa/fuera y lo fuerte que
    es el rival (1º de la tabla → -10%, último → +10%)."""
    factor = 1.0
    if home is not None:
        factor *= HOME_FACTOR if home else 2 - HOME_FACTOR
    if rival_rank and n_teams > 1:
        factor *= 1 - RIVAL_DIFFICULTY + 2 * RIVAL_DIFFICULTY * (rival_rank - 1) / (n_teams - 1)
    return round(factor, 3)


def listing_price(player: Player) -> int:
    return round(player.market_value * LISTING_MARKUP)


LINEUP_VARIANTS = ("flat_snake", "flat", "nested")  # flat_snake: verificada en vivo el 26/09/2026


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
