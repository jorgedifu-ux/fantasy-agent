"""Autoajuste: el bot corrige sus propios parámetros con lo que va viendo (puro, sin red).

Principios: (1) cada parámetro tiene unos límites fijos de seguridad (`autopilot.BOUNDS`) que
ningún ajuste puede superar; (2) hace falta una muestra mínima antes de tocar nada; (3) los
cambios son graduales (se mezcla lo aprendido con lo anterior), y (4) cada cambio queda
registrado con su motivo y se puede deshacer (`python3 -m fantasy_agent tune --reset`).
"""
from __future__ import annotations

from datetime import timedelta
from statistics import mean

from . import autopilot as ap

DAILY_DISCOUNT = 0.008     # lo que "cuesta" esperar un día con el dinero parado (coste de oportunidad)


def optimal_offer_threshold(ratios: list[float], daily_discount: float = DAILY_DISCOUNT, min_n: int = 40) -> tuple[float, str] | None:
    """Umbral óptimo para aceptar una oferta diaria aleatoria (parada óptima): se acepta si la
    oferta supera lo que vale esperar al sorteo de mañana, V = E[max(X, V)] / (1 + r). Con las
    ofertas reales que ha visto el bot (oferta / valor)."""
    if len(ratios) < min_n:
        return None
    v = 1.0
    for _ in range(500):
        nv = sum(max(x, v) for x in ratios) / len(ratios) / (1 + daily_discount)
        if abs(nv - v) < 1e-7:
            break
        v = nv
    return round(v, 3), f"{len(ratios)} ofertas vistas, mediana x{sorted(ratios)[len(ratios) // 2]:.3f}"


def adjust_bid_premium(current: float, results: list[bool], min_n: int = 12) -> tuple[float, str] | None:
    """Prima base de las pujas: si se pierden demasiadas, sube un punto; si se ganan casi todas, baja uno."""
    recent = results[-15:]
    if len(recent) < min_n:
        return None
    rate = sum(recent) / len(recent)
    if rate < 0.5:
        return current + 0.01, f"solo ganó {rate:.0%} de las últimas {len(recent)} pujas"
    if rate > 0.85:
        return current - 0.01, f"ganó {rate:.0%} de las últimas {len(recent)} pujas: sobra margen"
    return None


def invest_multiplier(current: float, returns: list[float], min_n: int = 12) -> tuple[float, str] | None:
    """Cuánto dinero dedicar a inversión según lo que han rendido las inversiones propias. Con
    pocas operaciones se fía poco del resultado (se encoge hacia el valor neutro, 1): n/(n+10)."""
    if len(returns) < min_n:
        return None
    r = mean(returns)
    trust = len(returns) / (len(returns) + 10)
    target = min(1.5, max(0.3, 1 + trust * r / 0.10))
    new = round(0.5 * current + 0.5 * target, 2)
    if abs(new - current) < 0.05:
        return None
    return new, f"las {len(returns)} inversiones propias llevan un {r:+.1%} de media"


def sample_drift(histories: dict, week_points: dict, week_ends: dict, horizon: int = 7) -> dict[str, list[float]]:
    """Revalorización a `horizon` días tras cada día en que un jugador estaba en cada "nivel"
    (ver `autopilot.drift_tier`), con la forma = media de puntos de las 2 últimas jornadas ya
    terminadas ese día. histories: id -> [(fecha, valor)]; week_points: id -> [(jornada, puntos)];
    week_ends: jornada -> fecha del último partido."""
    out: dict[str, list[float]] = {}
    for pid, hist in histories.items():
        pts = dict(week_points.get(pid, []))
        for t in range(7, len(hist) - horizon):
            day = hist[t][0]
            done = sorted(w for w, end in week_ends.items() if end + timedelta(hours=14) <= day)[-2:]
            form = mean(pts.get(w, 0) for w in done) if done else None
            v0, v3, v7 = hist[t][1], hist[t - 3][1], hist[t - 7][1]
            if not (v0 and v3 and v7):
                continue
            tier = ap.drift_tier((v0 / v3 - 1) * 100, (v0 / v7 - 1) * 100, form)
            if tier:
                out.setdefault(tier, []).append(hist[t + horizon][1] / v0 - 1)
    return out


HORIZON_DAYS = 7


def calibrate_drift(samples: dict[str, list[float]], min_n: int = 40, prior_weight: int = 40,
                    haircut: float = 0.85) -> dict[str, tuple[float, str]]:
    """Nueva revalorización esperada de cada nivel: media de lo observado mezclada con el valor de
    partida (`autopilot.DEFAULTS`) y rebajada un 15% por prudencia. Se parte siempre de los
    valores de fábrica para que el recorte no se acumule.

    Las observaciones son diarias y se solapan (cada una mira 7 días hacia delante), así que la
    muestra independiente real es ~7 veces menor: `min_n` y `prior_weight` se miden en esas
    observaciones efectivas (n / 7), no en filas."""
    out = {}
    for tier, rets in samples.items():
        key = f"drift_{tier}"
        n_eff = len(rets) / HORIZON_DAYS
        if n_eff < min_n or key not in ap.DEFAULTS:
            continue
        post = (n_eff * mean(rets) + prior_weight * ap.DEFAULTS[key]) / (n_eff + prior_weight)
        out[key] = (round(post * haircut, 3), f"{len(rets)} observaciones (~{n_eff:.0f} independientes), media {mean(rets):+.1%} a 7 días")
    return out
