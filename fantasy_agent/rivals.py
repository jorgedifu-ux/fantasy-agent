"""Aprender de los rivales (puro, testeable): qué compran, cuándo, a qué prima y cómo les sale.

Entrada: la actividad de la liga (`/activity`, tipos 1 cláusula, 31 puja ganada, 33 venta) y el
histórico de valor de cada jugador. Lo usa `cli.cmd_rivals`. El hallazgo del 8/10/2026 que lo
motivó: el líder compra casi siempre jugadores que ya suben (+15% en 7 días) con poca prima y los
mantiene ~14 días; nuestras pujas eran de jugadores planos o en bajada, con +9% de prima.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta

BUCKETS = (("<0%", -1e9, 0.0), ("0-10%", 0.0, 0.10), ("10-25%", 0.10, 0.25), ("≥25%", 0.25, 1e9))
SELL_RATIO = 0.97  # salida típica por venta (ofertas ~0,97-1,0× valor)


@dataclass
class Buy:
    manager: str
    player_id: str
    kind: str            # "puja" | "cláusula"
    day: date
    cost: int
    value: int           # valor de mercado ese día
    d7: float | None     # subida en los 7 días previos (0,10 = +10%)
    after14: float | None  # cambio de valor en los 14 días siguientes

    @property
    def premium(self) -> float:
        return self.cost / self.value - 1

    @property
    def net14(self) -> float | None:
        """Resultado si se vende a los 14 días a ~0,97× valor, contando la prima pagada."""
        return None if self.after14 is None else self.value * (1 + self.after14) * SELL_RATIO / self.cost - 1


@dataclass
class Trade:
    manager: str
    player_id: str
    bought: int
    exit: int
    days: int
    how: str             # "venta" | "clausulado"

    @property
    def gain(self) -> int:
        return self.exit - self.bought


def _value_on(series: dict[date, int], day: date) -> int | None:
    for k in range(4):
        v = series.get(day - timedelta(days=k))
        if v:
            return v
    return None


def buys(activity: list[dict], histories: dict[str, list[tuple[datetime, int]]], managers: dict[str, str],
         today: date) -> list[Buy]:
    series = {pid: {dt.date(): v for dt, v in h} for pid, h in histories.items()}
    out = []
    for a in activity:
        kind = int(a.get("activityTypeId") or 0)
        if kind not in (1, 31):
            continue
        pid = str(a.get("playerMasterId", ""))
        s = series.get(pid, {})
        day = datetime.fromisoformat(str(a["createdAt"])).date()
        v0, v7 = _value_on(s, day), _value_on(s, day - timedelta(days=7))
        if not v0:
            continue
        v14 = _value_on(s, day + timedelta(days=14)) if day + timedelta(days=14) <= today else None
        out.append(Buy(managers.get(str(a.get("user1Id")), str(a.get("user1Id"))), pid, "cláusula" if kind == 1 else "puja",
                       day, int(a.get("amount") or 0), v0, v0 / v7 - 1 if v7 else None, v14 / v0 - 1 if v14 else None))
    return out


def trades(activity: list[dict], managers: dict[str, str]) -> list[Trade]:
    """Compra emparejada con su salida (venta o cláusula que le pagan a ese mánager)."""
    rows = sorted(activity, key=lambda a: str(a.get("createdAt", "")))
    open_: dict[tuple[str, str], tuple[int, datetime]] = {}
    out = []
    for a in rows:
        kind = int(a.get("activityTypeId") or 0)
        u1, u2 = str(a.get("user1Id", "")), str(a.get("user2Id", ""))
        pid, money = str(a.get("playerMasterId", "")), int(a.get("amount") or 0)
        when = datetime.fromisoformat(str(a["createdAt"]))
        if kind == 1 and (u2, pid) in open_:
            cost, t0 = open_.pop((u2, pid))
            out.append(Trade(managers.get(u2, u2), pid, cost, money, (when - t0).days, "clausulado"))
        if kind == 33 and (u1, pid) in open_:
            cost, t0 = open_.pop((u1, pid))
            out.append(Trade(managers.get(u1, u1), pid, cost, money, (when - t0).days, "venta"))
        if kind in (1, 31):
            open_[(u1, pid)] = (money, when)
    return out


def bucket_table(items: list[Buy]) -> list[tuple[str, int, float, float, float]]:
    """(tramo de subida previa, n, cambio de valor a 14 d mediano, neto mediano, % que gana)."""
    out = []
    for name, lo, hi in BUCKETS:
        xs = [b for b in items if b.d7 is not None and b.after14 is not None and lo <= b.d7 < hi]
        if xs:
            nets = [b.net14 for b in xs]
            out.append((name, len(xs), statistics.median(b.after14 for b in xs), statistics.median(nets),
                        sum(n > 0 for n in nets) / len(nets)))
    return out


def report(activity: list[dict], histories: dict, managers: dict[str, str], names: dict[str, str], today: date,
           since: date | None = None) -> str:
    bs = buys(activity, histories, managers, today)
    ts = trades(activity, managers)
    pct = lambda x: "-" if x is None else f"{x * 100:+.1f}%"  # noqa: E731
    med = lambda xs: statistics.median(xs) if xs else None  # noqa: E731
    lines = ["<b>Cómo opera cada mánager</b> (toda la actividad visible)"]
    for m in sorted({b.manager for b in bs}):
        mine = [b for b in bs if b.manager == m and (since is None or b.day >= since)]
        tr = [t for t in ts if t.manager == m]
        bids = [b for b in mine if b.kind == "puja"]
        lines.append(
            f"\n<b>{m}</b>: {len(tr)} operaciones cerradas, {sum(t.gain for t in tr) / 1e6:+.1f}M, "
            f"{statistics.mean(t.days for t in tr) if tr else 0:.0f} días de media; "
            f"{sum(t.how == 'clausulado' for t in tr)} salidas por cláusula\n"
            f"  pujas: prima {pct(med([b.premium for b in bids]))}, subida previa 7d {pct(med([b.d7 for b in bids if b.d7 is not None]))}, "
            f"valor a 14 d {pct(med([b.after14 for b in bids if b.after14 is not None]))} · "
            f"{sum(b.cost for b in mine if b.value >= 15e6) / max(1, sum(b.cost for b in mine)):.0%} del gasto en jugadores ≥15M"
        )
    lines.append("\n<b>Toda la liga: resultado a 14 días según la subida previa (7 d)</b>")
    for name, n, chg, net, win in bucket_table(bs):
        lines.append(f"  {name:7} n={n:3}  valor {pct(chg)}  neto (prima y venta) {pct(net)}  ganan {win:.0%}")
    return "\n".join(lines)
