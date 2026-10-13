"""Cohortes de valor tras un partido (puro, testeable): ¿qué le pasa al valor según los puntos del partido y si el jugador subía antes?

Hallazgos del 13/10/2026 (463 jugadores, J1–J8, 1.794 partidos): el valor tarda ~2 días en reaccionar a los puntos; con 0 puntos (sin jugar) el valor
cae ~1% diario (−5,8% de D+2 a D+7, el 83% baja); pero si el jugador YA subía (≥+5% en los 3 días previos) sigue subiendo aunque sague 0 (+3,7%).
Uso: `python3 -m fantasy_agent cohorts` (tarda ~4 min la primera vez; cachea en data/analysis/hdated.json).
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta
from typing import Any

# Tramos de puntos relativos a su media. Finos alrededor de 1,0×: con tramos grandes, un 6 de un jugador de media 6,2 (0,97×) se contaba
# como "partido flojo" (−3%) cuando en realidad es neutro (−0,5%); el valor cambia de signo entre 0,9× y 1,1× (13/10/2026).
Z_BUCKETS = ("0", "<=0.4", "0.4-0.7", "0.7-0.9", "0.9-1.1", "1.1-1.4", "1.4-1.8", ">=1.8")
Z_LABELS = {"0": "0 puntos (sin jugar)", "<=0.4": "≤0,4× su media", "0.4-0.7": "0,4–0,7×", "0.7-0.9": "0,7–0,9×", "0.9-1.1": "0,9–1,1×",
            "1.1-1.4": "1,1–1,4×", "1.4-1.8": "1,4–1,8×", ">=1.8": "≥1,8×"}
BAD_BUCKETS = ("0", "<=0.4", "0.4-0.7", "0.7-0.9")   # partido flojo: por debajo de 0,9× su media
RISING = 0.05          # "subía": ≥+5% en los 3 días previos al partido


def z_bucket(z: float, pts: int) -> str:
    if pts == 0:
        return "0"
    for hi, key in ((.4, "<=0.4"), (.7, "0.4-0.7"), (.9, "0.7-0.9"), (1.1, "0.9-1.1"), (1.4, "1.1-1.4"), (1.8, "1.4-1.8")):
        if z <= hi if key == "<=0.4" else z < hi:
            return key
    return ">=1.8"


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


# ---------------------------------------------------------------------------------------------
# Tabla viva: el bot la RECALCULA solo cada semana con todos los datos (cli._refresh_cohorts). Esta es solo la de partida
# (J1–J8, 13/10/2026), que se usa mientras no haya una recalculada y para rellenar las celdas con pocos casos.
# Clave "tramo|subía|días tras el partido" → [cambio medio del valor en los 5 días siguientes, nº de casos].
# ---------------------------------------------------------------------------------------------
PRIOR: dict[str, list] = {
    "0.4-0.7|0|1": [-0.0418, 241],
    "0.4-0.7|0|2": [-0.0395, 241],
    "0.4-0.7|0|3": [-0.0358, 241],
    "0.4-0.7|0|4": [-0.0315, 241],
    "0.4-0.7|1|1": [0.1307, 71],
    "0.4-0.7|1|2": [0.1174, 71],
    "0.4-0.7|1|3": [0.1069, 71],
    "0.4-0.7|1|4": [0.1043, 71],
    "0.7-0.9|0|1": [-0.0361, 117],
    "0.7-0.9|0|2": [-0.0355, 117],
    "0.7-0.9|0|3": [-0.0348, 117],
    "0.7-0.9|0|4": [-0.0328, 117],
    "0.7-0.9|1|1": [0.2075, 39],
    "0.7-0.9|1|2": [0.1873, 39],
    "0.7-0.9|1|3": [0.1682, 39],
    "0.7-0.9|1|4": [0.1535, 39],
    "0.9-1.1|0|1": [-0.005, 108],
    "0.9-1.1|0|2": [-0.0051, 108],
    "0.9-1.1|0|3": [-0.0071, 108],
    "0.9-1.1|0|4": [-0.0079, 108],
    "0.9-1.1|1|1": [0.1783, 34],
    "0.9-1.1|1|2": [0.1704, 34],
    "0.9-1.1|1|3": [0.162, 34],
    "0.9-1.1|1|4": [0.1561, 34],
    "0|0|1": [-0.0834, 250],
    "0|0|2": [-0.082, 250],
    "0|0|3": [-0.0788, 250],
    "0|0|4": [-0.0743, 250],
    "0|1|1": [0.0503, 62],
    "0|1|2": [0.0369, 62],
    "0|1|3": [0.027, 62],
    "0|1|4": [0.0224, 62],
    "1.1-1.4|0|1": [0.0357, 86],
    "1.1-1.4|0|2": [0.0381, 86],
    "1.1-1.4|0|3": [0.0373, 86],
    "1.1-1.4|0|4": [0.0368, 86],
    "1.1-1.4|1|1": [0.2133, 34],
    "1.1-1.4|1|2": [0.1914, 34],
    "1.1-1.4|1|3": [0.1704, 34],
    "1.1-1.4|1|4": [0.1549, 34],
    "1.4-1.8|0|1": [0.0555, 108],
    "1.4-1.8|0|2": [0.0558, 108],
    "1.4-1.8|0|3": [0.051, 108],
    "1.4-1.8|0|4": [0.047, 108],
    "1.4-1.8|1|1": [0.2632, 40],
    "1.4-1.8|1|2": [0.2463, 40],
    "1.4-1.8|1|3": [0.2183, 40],
    "1.4-1.8|1|4": [0.1912, 40],
    "<=0.4|0|1": [-0.0767, 235],
    "<=0.4|0|2": [-0.0732, 235],
    "<=0.4|0|3": [-0.0673, 235],
    "<=0.4|0|4": [-0.06, 235],
    "<=0.4|1|1": [0.0799, 95],
    "<=0.4|1|2": [0.0675, 95],
    "<=0.4|1|3": [0.0584, 95],
    "<=0.4|1|4": [0.0525, 95],
    ">=1.8|0|1": [0.1169, 223],
    ">=1.8|0|2": [0.1143, 223],
    ">=1.8|0|3": [0.105, 223],
    ">=1.8|0|4": [0.0939, 223],
    ">=1.8|1|1": [0.3435, 51],
    ">=1.8|1|2": [0.3172, 51],
    ">=1.8|1|3": [0.2861, 51],
    ">=1.8|1|4": [0.2618, 51]
}
MIN_N = 20             # casos mínimos para fiarse de una celda
HORIZON_DAYS = 5
MAX_SIGNAL_DAYS = 6    # más de 6 días tras el partido, el partido ya no cuenta como señal


def cell_key(zb: str, rising: bool, k: int) -> str:
    return f"{zb}|{int(rising)}|{k}"


def table_from_obs(obs: list[dict]) -> dict[str, list]:
    out: dict[str, list] = {}
    for zb in Z_BUCKETS:
        for rising in (False, True):
            for k in (1, 2, 3, 4):
                c = cohort(obs, zb, rising, k, HORIZON_DAYS)
                if c:
                    out[cell_key(zb, rising, k)] = [round(c["mean"], 4), c["n"]]
    return out


def merge_tables(new: dict[str, list], prior: dict[str, list] | None = None, shrink_n: int = 30) -> dict[str, list]:
    """Tabla nueva sobre la de partida: las celdas con muchos casos mandan; las de pocos casos se mezclan con la de partida."""
    prior = PRIOR if prior is None else prior
    out = dict(prior)
    for key, (mean, n) in new.items():
        if key in prior and n < shrink_n:
            pm, pn = prior[key]
            w = n / (n + shrink_n)
            out[key] = [round(w * mean + (1 - w) * pm, 4), n]
        else:
            out[key] = [mean, n]
    return out


def lookup(table: dict[str, list], zb: str, rising: bool, k: int) -> tuple[float, int] | None:
    cell = table.get(cell_key(zb, rising, k))
    if not cell or cell[1] < MIN_N or not 1 <= k <= 4:
        return None
    return cell[0], cell[1]


def match_dates(calendars: dict[int, list[dict]]) -> dict[tuple[int, str], date]:
    """(jornada, id de equipo) → día del partido, solo de los terminados (matchState 7)."""
    out: dict[tuple[int, str], date] = {}
    for wk, matches in calendars.items():
        for m in matches:
            if int(m.get("matchState") or 0) != 7 or not m.get("matchDate"):
                continue
            d = date.fromisoformat(str(m["matchDate"])[:10])
            out[(wk, str(m["localId"]))] = d
            out[(wk, str(m["visitorId"]))] = d
    return out


def signal(raw: dict[str, Any], dates: dict[tuple[int, str], date], values: dict[date, int], today: date) -> tuple[str, bool, int] | None:
    """Señal del ÚLTIMO partido de un jugador: (tramo de puntos, si subía antes, días desde el partido) o None si no hay una fiable
    (poca historia, media <2, partido hace más de `MAX_SIGNAL_DAYS` días o sin valores)."""
    w = {int(x["weekNumber"]): x["points"] for x in (raw.get("weekPoints") or []) if x.get("points") is not None}
    played = [(dates[(wk, str(raw.get("teamId")))], wk) for wk in w if (wk, str(raw.get("teamId"))) in dates
              and dates[(wk, str(raw.get("teamId")))] < today]
    if not played:
        return None
    d, wk = max(played)
    k = (today - d).days
    others = [x for j, x in w.items() if j != wk and x != 0]
    if k < 1 or k > MAX_SIGNAL_DAYS or len(others) < 3:
        return None
    norm = statistics.mean(others)
    if norm < 2.0:
        return None
    a, b = values.get(d - timedelta(days=1)), values.get(d - timedelta(days=4))
    if not a or not b:
        return None
    pts = w[wk]
    z = 0.0 if pts == 0 else pts / norm
    return z_bucket(z, pts), a / b - 1 >= RISING, k
