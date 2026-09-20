"""Reparte los avisos informativos a lo largo del día en vez de mandarlos todos de golpe.

Dos categorías de mensaje, con reglas distintas:
- **Decisiones** (propuestas de puja/cláusula, fichajes de emergencia ejecutados, resultado
  de una confirmación): se mandan EN CUANTO se detectan, nunca esperan turno — son pocas
  (máx. 3 candidatas) y accionables.
- **Informativos** (tendencias, mercado sin traducir en propuesta, avisos de cuenta atrás):
  pasan por esta cola. Como mucho se manda 1 por franja horaria (`briefing_interval_min`),
  el más urgente primero; el resto espera al siguiente turno o se descarta si ya no aplica.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .config import Settings
from .storage import Store

# Niveles de urgencia orientativos (mayor = más prioritario).
URGENT_DEADLINE = 100      # cláusula a punto de congelarse / jornada a punto de cerrar
URGENT_SQUAD = 90          # plantilla incompleta cerca de la jornada
NORMAL_CLAUSE_INFO = 50    # cláusula que se libera pronto (informativo, no accionable aún)
NORMAL_MARKET = 30         # oportunidades de mercado / tendencias
LOW = 10


@dataclass
class Notice:
    key: str     # para no repetir el mismo aviso (se puede pasar a store.alert_is_new)
    urgency: int
    text: str


def rank(notices: list[Notice]) -> list[Notice]:
    return sorted(notices, key=lambda n: -n.urgency)


QUIET_START_HOUR = 23  # no se manda el parte de situación entre estas horas (hora local)...
QUIET_END_HOUR = 7     # ...pero las propuestas de decisión SÍ se mandan siempre, para no
# perder una ventana real (p.ej. una cláusula que se libera a las 2am) — ver STRATEGY.md.


def in_quiet_hours(now: datetime | None = None) -> bool:
    hour = (now or datetime.now()).hour
    return hour >= QUIET_START_HOUR or hour < QUIET_END_HOUR


def due(store: Store, settings: Settings) -> bool:
    """True si toca mandar el parte de situación: ha pasado bastante tiempo desde el último
    Y no estamos en horas de silencio. No marca como "enviado" si se salta por silencio, así
    que en cuanto acaben las horas de silencio se manda el primero que le toque, sin perderlo."""
    if in_quiet_hours():
        return False
    last = store.get("last_digest_sent")
    if not last:
        return True
    elapsed_min = (datetime.now(timezone.utc).timestamp() - float(last)) / 60
    return elapsed_min >= settings.briefing_interval_min


def mark_sent(store: Store) -> None:
    store.set("last_digest_sent", str(datetime.now(timezone.utc).timestamp()))
