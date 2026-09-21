"""El Plan de equipo: por qué existe esta capa (leer antes de tocar nada)

Todo lo demás en este proyecto (`confirm.py`, `cli._watch_once`) es un motor de REACCIÓN:
detecta una situación puntual (una cláusula que se libera, un hueco en la plantilla) y decide
en el momento. Eso está bien para el "qué hacer ahora mismo", pero no basta — las decisiones
del día a día deben responder a un plan ya pensado, no improvisarse cada vez desde cero. Si
hace falta vender a alguien para pagar un fichaje urgente, quién se vende debe estar decidido
de ANTES, no en el mismo segundo de la emergencia.

Este módulo genera y guarda ese plan: objetivos de fichaje (con motivo y prioridad), lista de
venta priorizada (con motivo), vigilancia de cláusulas de rivales con fecha conocida, y
objetivo de colchón de caja. Se genera con reglas Python puras (gratis, sin tokens) —
`generate_plan()` corre en cada `tick`/`watch`. La parte "inteligente" (ajustar prioridades a
mano, añadir un objetivo concreto por criterio propio) pasa por conversación con el usuario
—semanal, no más, para no gastar su cuota de Claude— y ahí es donde se guardan cambios
manuales que `generate_plan()` respeta (ver `merge_manual`).
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from . import analysis
from .storage import Store

PLAN_KEY = "team_plan"
PLAN_MESSAGE_ID_KEY = "team_plan_message_id"


@dataclass
class PlanItem:
    player_id: str
    player_name: str
    reason: str
    priority: str  # "alta" | "media" | "baja"
    added_at: float = field(default_factory=time.time)
    manual: bool = False  # True si lo añadió el usuario en conversación, no el generador
    max_price: int | None = None
    unlock_at: float | None = None  # solo watchlist: cuándo se libera la cláusula del rival


@dataclass
class Plan:
    updated_at: float = field(default_factory=time.time)
    cash_reserve_note: str = ""
    targets: list[PlanItem] = field(default_factory=list)
    sell_priority: list[PlanItem] = field(default_factory=list)
    watchlist: list[PlanItem] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(raw: str) -> "Plan":
        data = json.loads(raw)
        return Plan(
            updated_at=data.get("updated_at", time.time()),
            cash_reserve_note=data.get("cash_reserve_note", ""),
            targets=[PlanItem(**d) for d in data.get("targets", [])],
            sell_priority=[PlanItem(**d) for d in data.get("sell_priority", [])],
            watchlist=[PlanItem(**d) for d in data.get("watchlist", [])],
        )


def load_plan(store: Store) -> Plan:
    raw = store.get(PLAN_KEY)
    return Plan.from_json(raw) if raw else Plan()


def save_plan(store: Store, plan: Plan) -> None:
    plan.updated_at = time.time()
    store.set(PLAN_KEY, plan.to_json())


def due_for_refresh(store: Store, days: float = 7) -> bool:
    """El plan es una foto semanal, no algo que tiemble en cada tick (ver docstring del
    módulo) — True si ya ha pasado una semana desde la última vez, o si no hay plan todavía."""
    raw = store.get(PLAN_KEY)
    if not raw:
        return True
    plan = Plan.from_json(raw)
    return (time.time() - plan.updated_at) >= days * 86400


def targets_ids(plan: Plan) -> set[str]:
    return {i.player_id for i in plan.targets}


def sell_priority_ids(plan: Plan) -> list[PlanItem]:
    return sorted(plan.sell_priority, key=lambda i: i.priority)


def watchlist_ids(plan: Plan) -> set[str]:
    return {i.player_id for i in plan.watchlist}


def _keep_manual(old_items: list[PlanItem]) -> list[PlanItem]:
    """Lo añadido a mano en conversación no se pierde al regenerar — solo se refresca lo
    generado automáticamente."""
    return [i for i in old_items if i.manual]


def generate_plan(world, s, store: Store) -> Plan:
    """Regenera la parte automática del plan (reglas Python, sin tokens); conserva lo que se
    haya añadido a mano en conversación. Pensado para llamarse una vez por semana (o cuando
    cambien mucho las cosas), no en cada tick — el plan es una foto de la estrategia, no algo
    que deba temblar cada 30 minutos."""
    old = load_plan(store)
    plan = Plan(cash_reserve_note=f"Colchón objetivo: {s.budget_reserve_pct:.0%} del saldo sin tocar")

    plan.targets = _keep_manual(old.targets)
    seen_targets = {i.player_id for i in plan.targets}
    for o in analysis.allocate_budget(
        [op for op in _opportunities_for_plan(world) if op.score >= 16], world.my_cash,
        reserve_pct=s.budget_reserve_pct, max_picks=5,
    ):
        if o.item.player.id in seen_targets:
            continue
        plan.targets.append(PlanItem(
            player_id=o.item.player.id, player_name=o.item.player.name,
            reason="; ".join(o.reasons) or f"score {o.score}: buen rendimiento por precio",
            priority="alta" if o.score >= 22 else "media",
            max_price=o.item.price,
        ))

    plan.sell_priority = _keep_manual(old.sell_priority)
    seen_sells = {i.player_id for i in plan.sell_priority}
    mine_ids = {sl.player.id for sl in world.my_slots}
    for p, t in analysis.sell_high_candidates(world.trends, mine_ids):
        if p.id in seen_sells:
            continue
        plan.sell_priority.append(PlanItem(
            player_id=p.id, player_name=p.name,
            reason=f"en máximo ({t.d7:+.0f}% en 7 días), aprovechar antes de que baje",
            priority="media",
        ))
        seen_sells.add(p.id)
    for sl, reason in analysis.cut_loss_candidates(world.my_slots, world.trends):
        if sl.player.id in seen_sells:
            continue
        plan.sell_priority.append(PlanItem(
            player_id=sl.player.id, player_name=sl.player.name,
            reason=f"cortar pérdidas: {reason}",
            priority="alta",
        ))
        seen_sells.add(sl.player.id)

    plan.watchlist = _keep_manual(old.watchlist)
    seen_watch = {i.player_id for i in plan.watchlist}
    now = datetime.now(timezone.utc)
    for slot in world.rival_slots:
        p = slot.player
        if p.id in seen_watch or not p.market_value:
            continue
        ratio = slot.clause / p.market_value if p.market_value else 99
        until = slot.clause_locked_until
        if ratio <= 1.2 and until and until > now:
            plan.watchlist.append(PlanItem(
                player_id=p.id, player_name=p.name,
                reason=f"cláusula de {slot.owner_name} a x{ratio:.2f} el valor — objetivo lógico",
                priority="alta" if ratio <= 1.05 else "media",
                max_price=slot.clause, unlock_at=until.timestamp(),
            ))
            seen_watch.add(p.id)

    return plan


def _opportunities_for_plan(world):
    from .service import _opportunities  # import diferido: evita ciclo service<->plan
    return _opportunities(world)


def render_plan_text(plan: Plan) -> str:
    from .notify import esc

    def fmt_item(i: PlanItem, show_price: bool = True, show_unlock: bool = False) -> str:
        pr = {"alta": "🔴", "media": "🟡", "baja": "⚪"}.get(i.priority, "⚪")
        line = f"{pr} <b>{esc(i.player_name)}</b> — {esc(i.reason)}"
        if show_price and i.max_price:
            line += f" (tope {i.max_price / 1_000_000:.1f}M)"
        if show_unlock and i.unlock_at:
            when = time.strftime("%d/%m %H:%M", time.localtime(i.unlock_at))
            line += f"\n   ⏱️ libera el {when}"
        if i.manual:
            line += " · <i>añadido a mano</i>"
        return line

    stamp = datetime.fromtimestamp(plan.updated_at).strftime("%d/%m/%Y %H:%M")
    parts = [f"📐 <b>PLAN DE EQUIPO</b> · actualizado {stamp}\n<i>{esc(plan.cash_reserve_note)}</i>"]

    parts.append("\n🎯 <b>Fichajes objetivo</b>" + ("" if plan.targets else " — nada por ahora"))
    parts += [fmt_item(i) for i in sorted(plan.targets, key=lambda i: i.priority)[:6]]

    parts.append("\n💸 <b>Prioridad de venta</b>" + ("" if plan.sell_priority else " — nada por ahora"))
    parts += [fmt_item(i, show_price=False) for i in sorted(plan.sell_priority, key=lambda i: i.priority)[:6]]

    parts.append("\n👀 <b>Vigilando a rivales</b>" + ("" if plan.watchlist else " — nada por ahora"))
    parts += [fmt_item(i, show_unlock=True) for i in sorted(plan.watchlist, key=lambda i: i.priority)[:6]]

    return "\n".join(parts)
