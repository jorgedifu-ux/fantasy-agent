"""Cohortes de valor tras un partido (puro, testeable): ¿qué le pasa al valor según los puntos del partido y si el jugador subía antes?

Hallazgos del 13/10/2026 (463 jugadores, J1–J8, 1.794 partidos): el valor tarda ~2 días en reaccionar a los puntos; con 0 puntos (sin jugar) el valor
cae ~1% diario (−5,8% de D+2 a D+7, el 83% baja); pero si el jugador YA subía (≥+5% en los 3 días previos) sigue subiendo aunque sague 0 (+3,7%).
Uso: `python3 -m fantasy_agent cohorts` (tarda ~4 min la primera vez; cachea en data/analysis/hdated.json).
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta

Z_BUCKETS = ("0", "<=0.4", "0.4-1", "1-1.8", ">=1.8")
Z_LABELS = {"0": "0 puntos (sin jugar)", "<=0.4": "≤0,4× su media", "0.4-1": "0,4–1,0×", "1-1.8": "1,0–1,8×", ">=1.8": "≥1,8×"}
RISING = 0.05          # "subía": ≥+5% en los 3 días previos al partido


def z_bucket(z: float, pts: int) -> str:
    return "0" if pts == 0 else "<=0.4" if z <= .4 else "0.4-1" if z < 1.0 else "1-1.8" if z < 1.8 else ">=1.8"


def observations(players: dict, cal: dict, min_norm: float = 2.0) -> list[dict]:
    """Una observación por jugador y partido jugado: puntos relativos a su media en las demás jornadas, si subía antes y su serie de valores."""
    out = []
    for pid, p in players.items():
        w = {int(k): v for k, v in p["w"].items()}
        values = {date.fromisoformat(k): v for k, v in p["v"].items()}
        for wk, pts in w.items():
            md = cal.get(f"{wk}:{p['team']}")
            others = [x for k, x in w.items() if k != wk and x != 0]
            if md is None or len(others) < 3:
                continue
            norm = statistics.mean(others)
            if norm < min_norm:
                continue
            d = date.fromisoformat(md)
            if not all(values.get(d + timedelta(days=k)) for k in range(-4, 1)):
                continue
            z = 0.0 if pts == 0 else pts / norm
            out.append({"pid": pid, "wk": wk, "pts": pts, "norm": norm, "z": z, "zb": z_bucket(z, pts), "D": d, "V": values,
                        "pre": values[d - timedelta(days=1)] / values[d - timedelta(days=4)] - 1})
    return out


def cohort(obs: list[dict], zb: str, rising: bool, k: int, h: int = 5) -> dict | None:
    """Cambio del valor de D+k a D+k+h para los jugadores con ese tipo de partido (`rising`: subían antes o no)."""
    xs = []
    for o in obs:
        if o["zb"] != zb or ((o["pre"] >= RISING) != rising):
            continue
        a, b = o["V"].get(o["D"] + timedelta(days=k)), o["V"].get(o["D"] + timedelta(days=k + h))
        if a and b:
            xs.append(b / a - 1)
    if len(xs) < 8:
        return None
    return {"n": len(xs), "mean": statistics.mean(xs), "median": statistics.median(xs), "down": sum(x < 0 for x in xs) / len(xs)}


def report(obs: list[dict]) -> str:
    lines = [f"Cambio medio del valor tras el partido, de D+2 a D+7 (observaciones: {len(obs)})", ""]
    for title, flt in (("Todos", lambda o: True), ("Subían antes (≥+5% en 3 días)", lambda o: o["pre"] >= RISING),
                       ("No subían (<+1%)", lambda o: o["pre"] < .01)):
        lines.append(title)
        for zb in Z_BUCKETS:
            rs = [o for o in obs if o["zb"] == zb and flt(o)]
            xs = [o["V"][o["D"] + timedelta(days=7)] / o["V"][o["D"] + timedelta(days=2)] - 1 for o in rs
                  if o["V"].get(o["D"] + timedelta(days=7)) and o["V"].get(o["D"] + timedelta(days=2))]
            if len(xs) < 8:
                lines.append(f"  {Z_LABELS[zb]:22} n={len(xs)} (pocos datos)")
                continue
            lines.append(f"  {Z_LABELS[zb]:22} n={len(xs):4d}  media {statistics.mean(xs):+6.1%}  mediana {statistics.median(xs):+6.1%}  bajan {sum(x < 0 for x in xs) / len(xs):.0%}")
        lines.append("")
    return "\n".join(lines)
