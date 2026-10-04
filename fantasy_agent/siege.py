"""Operación bloqueo: dejar al líder sin portero para que no puntúe esa jornada.

Sin once legal (11 jugadores con un portero) la jornada entera puntúa 0. El portero es la
única posición donde compensa: hay pocos y son baratos. Hay que quitarle TODOS sus porteros
por cláusula y, a la vez, cerrarle las vías de reposición: porteros del mercado de LaLiga y
cláusulas abiertas de otros mánagers. Todo se ejecuta en el último momento antes de la
congelación de cláusulas (24 h antes del primer partido), para que no tenga tiempo de reaccionar.

Este módulo es puro (sin red): `evaluate` decide si la operación es viable, cuánto cuesta, con
qué certeza y si compensa. La ejecución está en `cli._siege_*`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import lineup
from .models import MarketItem, Player, SquadSlot

GK = 1
EXEC_MARGIN = timedelta(minutes=3)   # se ejecuta 3 min antes de que se congelen las cláusulas
ARM_HOURS = 96                       # desde 4 días antes se reserva el dinero y se prepara
MARKET_BLOCK_FACTOR = 1.35           # puja a +35%: por encima de lo que suelen pagar los rivales
CASH_MARGIN = 10_000_000             # incertidumbre de la estimación del dinero del rival
RESALE_FACTOR = 0.95                 # al revender lo comprado se saca ~95% del valor
OPPORTUNITY_COST = 0.10              # coste de tener el dinero parado una semana (la inversión da ~+8%/sem)
POINT_VALUE_M = 0.30                 # lo que vale (en M) un punto que no suma el líder: 0,1M de premio + posición
MIN_CERTAINTY = 0.60
BASE_FRACTION = 0.70                 # parte máxima del saldo libre que se arriesga (los jugadores se conservan)
SHIELDS_PER_JORNADA = 2              # observado: tope de blindajes por equipo y jornada


@dataclass
class Step:
    kind: str                        # "kill_clause" | "block_clause" | "block_bid"
    player: Player
    cost: int
    when: str = "go"                 # "pre" = puede hacerse ya (puja que se resuelve antes) | "go" = al ejecutar
    certainty: float = 1.0
    slot: SquadSlot | None = None
    item: MarketItem | None = None
    note: str = ""


@dataclass
class SiegePlan:
    target_name: str = ""
    target_team_id: str = ""
    exec_at: datetime | None = None
    steps: list[Step] = field(default_factory=list)
    outlay: int = 0                  # dinero que falta por gastar (sin pujas ya hechas)
    certainty: float = 0.0
    benefit_m: float = 0.0
    expected_loss_m: float = 0.0
    max_outlay: int = 0
    feasible: bool = False
    reasons: list[str] = field(default_factory=list)  # por qué NO es viable (o avisos)
    info: list[str] = field(default_factory=list)

    @property
    def pending_steps(self) -> list[Step]:
        return self.steps


def stage_factor(jornada: int, total: int = 38) -> float:
    """Cuánto se arriesga según el momento de la liga: al principio el dinero rinde más
    invertido (se arriesga menos); al final ya no hay para qué guardarlo."""
    if jornada >= total - 8:
        return 1.4
    if jornada < 6:
        return 0.6
    return 1.0


def clause_open_at(sl: SquadSlot, t: datetime) -> bool:
    if sl.clause <= 0:
        return False
    if sl.clause_locked_until and sl.clause_locked_until > t:
        return False
    if sl.shielded_until and sl.shielded_until > t:
        return False
    return True


def blocked_until(sl: SquadSlot) -> datetime | None:
    return max((d for d in (sl.clause_locked_until, sl.shielded_until) if d), default=None)


def can_field(players: list[Player]) -> bool:
    cands = [lineup.Candidate(p, 1.0, 1.0) for p in players if p.position_id in (1, 2, 3, 4) and p.available]
    return len(lineup.best_eleven(cands)[1]) == 11


def evaluate(
    *, target_slots: list[SquadSlot], other_slots: list[SquadSlot], my_slots: list[SquadSlot],
    market: list[MarketItem], now: datetime, first_match: datetime, freeze_start: datetime,
    free_cash: int, target_cash: int, target_points: float, shields_used: int, jornada: int,
    squad_slots_free: int, my_xi_ok: bool, target_name: str = "", target_team_id: str = "",
    total_jornadas: int = 38,
) -> SiegePlan:
    plan = SiegePlan(target_name=target_name, target_team_id=target_team_id)
    plan.exec_at = freeze_start - EXEC_MARGIN
    t_exec = plan.exec_at
    if now >= freeze_start:
        plan.reasons.append("las cláusulas ya están congeladas hasta que empiece la jornada")
        return plan
    if not my_xi_ok:
        plan.reasons.append("tu propio once no está completo: primero tus puntos")
        return plan

    kills = [sl for sl in target_slots if sl.player.position_id == GK and sl.player.available]
    plan.info.append(f"{target_name} tiene {len(kills)} portero(s) disponible(s)")
    certainty = 1.0

    for sl in kills:
        if not clause_open_at(sl, t_exec):
            until = blocked_until(sl)
            if until and until > t_exec:
                plan.reasons.append(
                    f"{sl.player.name} (su portero) está bloqueado hasta el {until.astimezone():%a %d/%m %H:%M}"
                    + (", ya con la jornada empezada" if until > first_match else ""))
            else:
                plan.reasons.append(f"{sl.player.name} (su portero) no tiene la cláusula abierta")
            continue
        plan.steps.append(Step("kill_clause", sl.player, sl.clause, certainty=1.0, slot=sl,
                               note=f"cláusula de {target_name}"))
    if shields_used < SHIELDS_PER_JORNADA and any(not sl.shielded_until for sl in kills):
        certainty *= 0.85
        plan.info.append("aún puede blindar un portero (riesgo del 15%)")
    elif kills:
        plan.info.append(f"ya gastó sus {SHIELDS_PER_JORNADA} blindajes de esta jornada: no puede blindar")

    reach = target_cash + CASH_MARGIN
    for sl in other_slots:
        p = sl.player
        if p.position_id != GK or not p.available or not clause_open_at(sl, freeze_start):
            continue
        if sl.clause > reach:
            plan.info.append(f"{p.name} (de {sl.owner_name}) no se lo puede permitir")
            continue
        plan.steps.append(Step("block_clause", p, sl.clause, certainty=0.93, slot=sl,
                               note=f"portero de {sl.owner_name} con la cláusula abierta"))
        certainty *= 0.93
    for sl in my_slots:
        p = sl.player
        if p.position_id == GK and clause_open_at(sl, freeze_start) and 0 < sl.clause <= reach:
            plan.reasons.append(f"tu portero {p.name} sería clausulable por {target_name}")

    for it in market:
        p = it.player
        if it.seller != "LaLiga" or p.position_id != GK or not p.available or not it.market_id:
            continue
        if it.expires and it.expires > first_match:
            continue                                  # se resuelve ya con la jornada en juego
        if it.price > reach:
            continue
        done = bool(it.my_bid)
        cost = 0 if done else round(it.price * MARKET_BLOCK_FACTOR)
        plan.steps.append(Step(
            "block_bid", p, cost, when="pre" if it.expires and it.expires <= t_exec else "go",
            certainty=0.90, item=it, note="portero del mercado" + (" (ya pujado)" if done else "")))
        certainty *= 0.90
    if (t_exec - now) > timedelta(hours=2):
        certainty *= 0.85
        plan.info.append("pueden salir más porteros al mercado antes del cierre: se reevalúa al ejecutar")
    certainty *= 0.95  # ofertas directas entre mánagers: no controlables
    plan.certainty = round(certainty, 2)

    rest = [sl.player for sl in target_slots if sl not in kills]
    if kills and can_field(rest):
        plan.reasons.append("aun sin sus porteros podría alinear un once (revisa su plantilla)")
    if not kills and not plan.steps:
        plan.reasons.append("ya está sin portero y no puede reponerlo: no hay nada que hacer")
        return plan

    plan.outlay = sum(s.cost for s in plan.steps)
    if len(plan.steps) - sum(1 for s in plan.steps if s.cost == 0) > squad_slots_free:
        plan.reasons.append(f"no caben en tu plantilla ({squad_slots_free} plazas libres)")
    if plan.outlay > free_cash:
        plan.reasons.append(f"faltan {(plan.outlay - free_cash) / 1e6:.1f}M: necesitas {plan.outlay / 1e6:.1f}M y tienes {free_cash / 1e6:.1f}M libres")

    plan.max_outlay = int(max(free_cash, 0) * min(1.0, BASE_FRACTION * stage_factor(jornada, total_jornadas)
                                                 * (0.5 + 0.5 * plan.certainty)))
    if plan.outlay > plan.max_outlay:
        plan.reasons.append(
            f"gasto de {plan.outlay / 1e6:.1f}M por encima del que me permito arriesgar ahora "
            f"({plan.max_outlay / 1e6:.1f}M según tu saldo, la jornada {jornada} y la certeza)")

    plan.benefit_m = round(target_points * POINT_VALUE_M, 1)
    loss = OPPORTUNITY_COST * plan.outlay / 1e6
    for s in plan.steps:
        if s.cost:
            loss += max(0.0, (s.cost - RESALE_FACTOR * s.player.market_value) / 1e6)
    plan.expected_loss_m = round(loss, 1)
    if plan.certainty < MIN_CERTAINTY:
        plan.reasons.append(f"certeza {plan.certainty:.0%} < mínimo {MIN_CERTAINTY:.0%}")
    if plan.benefit_m * plan.certainty < plan.expected_loss_m:
        plan.reasons.append(
            f"no compensa: quitarle ~{target_points:.0f} pts vale ~{plan.benefit_m:.1f}M (×{plan.certainty:.0%} de "
            f"certeza) y el coste esperado es {plan.expected_loss_m:.1f}M")
    plan.feasible = not plan.reasons
    return plan


def render(plan: SiegePlan, *, html: bool = False) -> str:
    b = (lambda s: f"<b>{s}</b>") if html else (lambda s: s)
    lines = [b(f"Operación bloqueo contra {plan.target_name}")]
    if plan.exec_at:
        lines.append(f"Ejecución: {plan.exec_at.astimezone():%a %d/%m %H:%M} (justo antes de congelarse las cláusulas)")
    for s in plan.steps:
        etiqueta = {"kill_clause": "quitarle", "block_clause": "quitar a otro rival", "block_bid": "pujar en el mercado"}[s.kind]
        lines.append(f"  · {etiqueta}: {s.player.name} — {s.cost / 1e6:.2f}M ({s.note})")
    lines.append(f"Gasto bruto {plan.outlay / 1e6:.1f}M (casi todo recuperable: son jugadores) · certeza {plan.certainty:.0%}")
    lines.append(f"Beneficio ~{plan.benefit_m:.1f}M · coste esperado ~{plan.expected_loss_m:.1f}M")
    lines += [f"ℹ️ {i}" for i in plan.info]
    if plan.reasons:
        lines.append("No viable:")
        lines += [f"  ✖ {r}" for r in plan.reasons]
    else:
        lines.append("✅ VIABLE")
    return "\n".join(lines)
