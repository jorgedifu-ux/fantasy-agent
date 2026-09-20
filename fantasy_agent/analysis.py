"""Análisis puro (sin red): tendencias, oportunidades de mercado y alarmas de cláusula."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import MarketItem, Player, SquadSlot


# ---------- tendencias de valor ---------------------------------------------
@dataclass
class Trend:
    d1: float  # variación porcentual a 1 día
    d3: float
    d7: float

    @property
    def label(self) -> str:
        if self.d3 >= 3:
            return "🚀 subiendo fuerte"
        if self.d3 >= 0.5:
            return "📈 subiendo"
        if self.d3 <= -3:
            return "🔻 cayendo fuerte"
        if self.d3 <= -0.5:
            return "📉 bajando"
        return "➖ estable"


def trend_from_history(history: list[tuple[datetime, int]]) -> Trend:
    if len(history) < 2:
        return Trend(0.0, 0.0, 0.0)
    values = [v for _, v in history]
    last = values[-1]

    def pct(days: int) -> float:
        base = values[-1 - days] if len(values) > days else values[0]
        return round((last - base) / base * 100, 2) if base else 0.0

    return Trend(pct(1), pct(3), pct(7))


# ---------- oportunidades de mercado ----------------------------------------
@dataclass
class Opportunity:
    item: MarketItem
    trend: Trend
    score: float
    reasons: list[str]


def score_market_item(
    item: MarketItem, trend: Trend, my_cash: int | None, *,
    recently_recovered: bool = False, recent_form: float | None = None,
) -> Opportunity:
    """Puntúa como FICHAJE (para tu once): importa lo que va a rendir de aquí en adelante
    (media de puntos por partido), no lo que ya sumó — esos puntos ya no te los llevas.

    `recent_form` (opcional): media de puntos en las últimas jornadas COMPLETADAS (no toda la
    temporada) — un jugador que lleva 3 jornadas mejor (o peor) que su media anual pesa más
    esa racha reciente que el arrastre de meses atrás."""
    p = item.player
    reasons: list[str] = []
    score = 0.0

    millions = max(item.price, 1) / 1_000_000
    ppm = p.avg_points / millions  # media de puntos por partido, por millón invertido
    score += min(ppm, 15) * 2

    if p.market_value and item.price < p.market_value:
        gap = (p.market_value - item.price) / p.market_value * 100
        score += min(gap, 20)

    score += min(p.avg_points, 10) * 1.5

    if recent_form is not None and p.avg_points > 0:
        delta = recent_form - p.avg_points
        score += max(-5.0, min(5.0, delta * 1.5))
        if delta >= 1.5:
            reasons.append(f"📈 en racha: {recent_form:.1f} pts/partido últimas jornadas (media anual {p.avg_points:.1f})")
        elif delta <= -1.5:
            reasons.append(f"📉 de capa caída: {recent_form:.1f} pts/partido últimas jornadas (media anual {p.avg_points:.1f})")

    if recently_recovered:
        # Ha vuelto de lesión/duda/sanción hace poco: su precio y su media aún no reflejan
        # el nivel real — es la ventana en la que suele estar más barato de lo que va a valer.
        score += 8
        reasons.append("🩹 recuperado hace poco, precio aún no ajustado")

    if not p.available:
        score -= 25
        reasons.append(f"⚠️ estado: {p.status}")
    if my_cash is not None and item.price > my_cash:
        score -= 15
        reasons.append("no te llega el saldo")

    return Opportunity(item, trend, round(score, 1), reasons)


# ---------- asignación de presupuesto (cartera, no fichajes sueltos) ------------------------
def allocate_budget(
    opportunities: list[Opportunity], cash: int | None, *, reserve_pct: float = 0.2, max_picks: int = 3,
) -> list[Opportunity]:
    """Elige la mejor combinación (por score) que quepa de verdad en tu saldo — nunca una
    lista que en conjunto no puedas pagar. Reserva `reserve_pct` del saldo sin tocar (colchón
    para cláusulas, ver STRATEGY.md §1: no gastar hasta dejar el saldo a 0). Greedy por score,
    ordenando aquí mismo (no asume que ya venga ordenada): no es óptimo matemático (eso sería
    un knapsack), pero es simple, predecible, y coincide con "coge lo mejor primero" que es
    como razona un jugador."""
    ordered = sorted(opportunities, key=lambda o: -o.score)
    if cash is None:
        return ordered[:max_picks]
    budget = cash * (1 - reserve_pct)
    picks: list[Opportunity] = []
    spent = 0
    for o in ordered:
        if len(picks) >= max_picks:
            break
        if o.item.price <= 0 or spent + o.item.price > budget:
            continue
        picks.append(o)
        spent += o.item.price
    return picks


def score_investment(item: MarketItem, trend: Trend) -> float | None:
    """Puntuación centrada solo en potencial de revalorización (comprar barato, vender caro)."""
    p = item.player
    if not p.available or not p.market_value or item.price > p.market_value * 1.05:
        return None
    if trend.d3 < 1.5:
        return None
    return round(trend.d3 * 2 + max(trend.d1, 0) * 1.5, 1)


def project_value(current: int, trend: Trend, days: int = 14) -> int:
    """Cuánto podría valer dentro de `days` días si sigue el ritmo reciente.
    Por defecto 14 días: es lo que tarda en liberarse la cláusula tras comprar a alguien,
    así que ese es tu horizonte real para poder revenderlo. Usa el ritmo a 7 días (más
    estable que el de 3) para no disparar la proyección por un pico de un par de días."""
    daily_rate = trend.d7 / 7 if trend.d7 else trend.d3 / 3
    return round(current * (1 + daily_rate / 100) ** days)


def sell_high_candidates(trends: dict[str, tuple[Player, Trend]], mine: set[str]) -> list[tuple[Player, Trend]]:
    """Jugadores tuyos que llevan una buena subida a 7 días pero ya se están frenando: venderlos ya."""
    out = [(p, t) for pid, (p, t) in trends.items() if pid in mine and t.d7 >= 8 and t.d1 <= 0.5]
    return sorted(out, key=lambda x: -x[1].d7)[:5]


# ---------- alarmas de cláusulas --------------------------------------------
# Umbrales para avisar más de una vez de la misma cláusula según se acerca su liberación
# (24h, 6h, 1h): cada uno dispara una alerta nueva la primera vez que se cruza.
UNLOCK_ALERT_TIERS_HOURS = (24, 6, 1)


@dataclass
class ClauseAlert:
    kind: str  # "unlock_soon" | "open_affordable" | "my_risk"
    slot: SquadSlot
    message: str
    tier: str = ""  # p.ej. "6h": para que la misma cláusula pueda avisar varias veces al acercarse
    penalty: float = 0.0  # >0: alimenta al líder o es venganza directa — se manda igual, pero
    # más abajo en prioridad (ver clause_alerts)

    @property
    def key(self) -> str:
        lock = self.slot.clause_locked_until.isoformat() if self.slot.clause_locked_until else "open"
        return f"{self.kind}:{self.tier}:{self.slot.owner_team_id}:{self.slot.player.id}:{self.slot.clause}:{lock}"


def clause_urgency_label(ratio: float, penalty: float) -> str:
    """4 niveles, como pidió el usuario: cuánto de bueno es el precio (ratio cláusula/valor)
    matizado por si alimenta al líder o es venganza (penalty > 0 baja el nivel)."""
    if penalty > 0:
        return "🟡 RECOMENDABLE" if ratio <= 1.1 else "⚪ NO URGENTE"
    if ratio <= 1.0:
        return "🔴 MUY URGENTE"
    if ratio <= 1.1:
        return "🟠 URGENTE"
    return "🟡 RECOMENDABLE"


def player_quality_label(score: float) -> str:
    """Mismo estilo que usan las guías de fantasy en español: chollo > buena opción > a valorar."""
    if score >= 22:
        return "🔥 CHOLLO"
    if score >= 16:
        return "✅ BUENA OPCIÓN"
    return "🤔 A VALORAR"


def _fmt_m(amount: int) -> str:
    return f"{amount / 1_000_000:.2f}M"


def _fmt_delta(delta: timedelta) -> str:
    hours = int(delta.total_seconds() // 3600)
    minutes = int(delta.total_seconds() % 3600 // 60)
    return f"{hours}h {minutes:02d}min"


def _fmt_when(until: datetime, now: datetime) -> str:
    """Cuenta atrás si es pronto; fecha y hora exactas si falta mucho (Xh no se lee bien a 13 días)."""
    delta = until - now
    if delta <= timedelta(hours=48):
        return f"en {_fmt_delta(delta)}"
    return f"el {until.astimezone().strftime('%d/%m %H:%M')}"


def clause_alerts(
    rival_slots: list[SquadSlot],
    my_cash: int | None,
    now: datetime,
    window_hours: int = 24,
    min_quality_avg: float = 3.0,
    max_ratio: float = 1.2,
    freeze: tuple[datetime, datetime] | None = None,
    leader_team_id: str | None = None,
    revenge_against_team_id: str | None = None,
) -> list[ClauseAlert]:
    """Solo cláusulas "lógicas": el precio de la cláusula no puede estar muy por encima del valor
    de mercado real del jugador (si no, aunque sea una estrella, no compensa pagarla). Solo mira
    rivales — lo tuyo (blindar, arriesgarte) lo decides tú, no hace falta que te lo repitamos.
    `freeze` es la ventana en la que la propia liga bloquea TODAS las cláusulas (24h antes del
    primer partido de la jornada): un jugador "libre" según su cláusula puede seguir sin ser
    pagable si caemos dentro de esa ventana.

    `leader_team_id` despriorriza (no excluye) clausulazos que pagarían directamente al líder
    de la liga — pagarle su cláusula es darle el dinero que necesita para reponerse.
    `revenge_against_team_id` despriorriza clausular de vuelta al rival que te acaba de
    clausular a ti: la venganza inmediata casi siempre le hace un favor (recupera parte del
    dinero y consigue el jugador que quería) — ver STRATEGY.md §2."""
    alerts: list[ClauseAlert] = []
    tiers = [h for h in UNLOCK_ALERT_TIERS_HOURS if h <= window_hours] or [window_hours]
    frozen_now = bool(freeze and freeze[0] <= now < freeze[1])

    for slot in rival_slots:
        p = slot.player
        if p.position_id == 5 or not p.market_value:
            continue
        ratio = slot.clause / p.market_value
        if ratio > max_ratio or p.avg_points < min_quality_avg:
            continue
        until = slot.clause_locked_until
        tier = ""
        if until and until > now:
            hours_left = (until - now).total_seconds() / 3600
            matched = next((h for h in sorted(tiers) if hours_left <= h), None)
            if matched is None:
                continue
            estado = f"se libera {_fmt_when(until, now)}"
            tier = f"{matched}h"
        elif slot.clause_open(now) and not frozen_now and (my_cash is None or slot.clause <= my_cash):
            estado = "pagable ya"
        else:
            continue
        penalty = 0.0
        avisos = []
        if leader_team_id and slot.owner_team_id == leader_team_id:
            penalty += 1.0
            avisos.append("🥇 es del líder — le das el dinero que necesita para reponerse")
        if revenge_against_team_id and slot.owner_team_id == revenge_against_team_id:
            penalty += 1.0
            avisos.append("🔁 sería venganza directa — probablemente le hace un favor, no un daño")
        estado_txt = estado + ("\n" + "\n".join(avisos) if avisos else "")
        alerts.append(ClauseAlert(
            "open_affordable" if slot.clause_open(now) else "unlock_soon", slot,
            f"{p.name}\n"
            f"Dueño: {slot.owner_name}\n"
            f"Valor de mercado: {_fmt_m(p.market_value)}\n"
            f"Cláusula: {_fmt_m(slot.clause)} (x{ratio:.2f} el valor)\n"
            f"Estado: {estado_txt}",
            tier=tier,
            penalty=penalty,
        ))

    # Primero las que ya puedes pagar; dentro de cada grupo, las no penalizadas antes que las
    # que alimentan al líder o son venganza directa; luego por cercanía a liberarse.
    alerts.sort(key=lambda a: (a.kind != "open_affordable", a.penalty, a.slot.clause_locked_until or now))
    return alerts


def top_movers(trends: dict[str, tuple[Player, Trend]], n: int = 5) -> tuple[list, list]:
    ordered = sorted(trends.values(), key=lambda t: t[1].d3)
    fallers = [t for t in ordered[:n] if t[1].d3 < 0]
    risers = [t for t in reversed(ordered[-n:]) if t[1].d3 > 0]
    return risers, fallers


# ---------- red de seguridad: plantilla incompleta para la jornada -----------------------
# Mínimo exigido por posición en CUALQUIER formación legal (ver lineup.FORMATIONS):
# 1 portero, 3 defensas, 3 centrocampistas, 1 delantero. Si no llegas a eso, ninguna
# formación es alineable, da igual cuál elijas.
MIN_PER_POSITION = {1: 1, 2: 3, 3: 3, 4: 1}


def position_shortage(my_slots: list[SquadSlot]) -> dict[int, int]:
    """Cuántos jugadores DISPONIBLES faltan en cada posición para poder alinear algún 11 legal."""
    have = dict.fromkeys(MIN_PER_POSITION, 0)
    for sl in my_slots:
        if sl.player.position_id in have and sl.player.available:
            have[sl.player.position_id] += 1
    return {pos: max(0, MIN_PER_POSITION[pos] - have[pos]) for pos in have}


def emergency_candidates(
    my_slots: list[SquadSlot], market: list[MarketItem], cash: int | None, cap_pct: float = 0.15,
) -> list[Opportunity]:
    """Fichajes de MERCADO LIBRE (nunca clausulazos — esos le quitan algo a un rival, siguen
    necesitando tu sí) para tapar huecos críticos, ordenados por urgencia real: primero la
    posición más corta, dentro de ella el que más rinda sin pasarse del tope de gasto.
    Pensados para ejecutarse SIN confirmación cuando no hay margen para esperar."""
    shortage = position_shortage(my_slots)
    needed = {pos for pos, n in shortage.items() if n > 0}
    if not needed or not cash or cash <= 0:
        return []
    cap = cash * cap_pct
    ranked: list[tuple[int, float, MarketItem]] = []
    for item in market:
        p = item.player
        if p.position_id not in needed or not p.available:
            continue
        if item.seller != "LaLiga" or not item.market_id:
            continue  # solo mercado libre
        if item.price <= 0 or item.price > cap or item.price > cash:
            continue
        score = p.avg_points * 10 - item.price / 1_000_000  # rinde mucho, cuesta poco
        ranked.append((shortage[p.position_id], score, item))
    ranked.sort(key=lambda t: (-t[0], -t[1]))
    return [
        Opportunity(item, Trend(0, 0, 0), round(score, 1),
                    [f"🚨 fichaje de emergencia: hueco crítico en {item.player.position}"])
        for _, score, item in ranked
    ]
