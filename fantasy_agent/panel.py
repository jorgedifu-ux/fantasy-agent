"""Panel de misiones: UN mensaje fijado en Telegram que se edita en el sitio con el estado de lo importante, para poder mirarlo cuando quieras
sin que te llegue nada nuevo. Se actualiza como mucho cada 30 minutos y solo si ha cambiado algo."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone

from . import analysis, autopilot as ap, notify
from .storage import Store

PANEL_ID_KEY = "panel_message_id"
REFRESH_S = 30 * 60
DAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def _when(dt: datetime) -> str:
    d = dt.astimezone()
    return f"{DAYS[d.weekday()]} {d:%d %H:%M}"


def _m(x: float) -> str:
    return f"{x / 1e6:.1f}M"


def render(world, store: Store, *, hours_to_deadline: float | None, week: dict | None = None, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    esc = notify.esc
    mine = [sl.player for sl in world.my_slots]
    lines = [f"🎯 <b>MISIONES</b> · {DAYS[now.astimezone().weekday()]} {now.astimezone():%d/%m %H:%M}"]

    # --- jornada y once
    live = bool((week or {}).get("isLive"))
    n_week = (week or {}).get("weekNumber")
    if live:
        lines.append(f"⚽ <b>Jornada {n_week} en juego</b> · ver /jornada")
    short = [f"{n} {('portero', 'defensa', 'centrocampista', 'delantero')[pos - 1]}" for pos, n in analysis.position_shortage(world.my_slots).items() if n > 0]
    if ap.complete_eleven(mine):
        xi = "✅ once legal"
    else:
        xi = "⚠️ <b>once incompleto</b>" + (f" (faltan {', '.join(short)})" if short else "")
    if hours_to_deadline is not None and hours_to_deadline > 0:
        nxt = world.outlook.next_first if world.outlook and world.outlook.next_first else None
        lines.append(f"📋 Próxima jornada: {_when(nxt) if nxt else '—'} · {xi}")
        if world.clause_freeze:
            lines.append(f"   Congelación de cláusulas: {_when(world.clause_freeze[0])} → {_when(world.clause_freeze[1])}")
    else:
        lines.append(f"📋 {xi}")
    lines.append(f"💰 Caja {_m(world.my_cash)} · plantilla {len(world.my_slots)} jugadores · valor {_m(sum(p.market_value for p in mine))}")

    # --- fichajes en curso
    bids = [b for b in store.unresolved_market_bids("buy") if not b.get("expires_at") or b["expires_at"] > time.time() - 600]
    if bids:
        lines.append("🛒 <b>Pujas en curso</b>: " + ", ".join(
            f"{esc(b['player_name'])} {_m(b['price'])}" + (f" (resuelve {datetime.fromtimestamp(b['expires_at']):%a %H:%M})" if b.get("expires_at") else "")
            for b in bids[:6]))
    else:
        lines.append("🛒 Pujas en curso: ninguna")

    # --- proteger a los que se abren
    exposed, deliberate = [], []
    for sl in world.my_slots:
        h = ap.hours_until_exposed(sl, now)
        if h is None or h > 120 or sl.player.market_value < ap.RAISE_MIN_VALUE:
            continue
        if sl.clause / sl.player.market_value > ap.ATTRACTIVE_RATIO:
            if h == 0:
                deliberate.append(sl)       # cláusula por encima de ×1,12: abierta a propósito, si la pagan ganamos
            continue
        exposed.append((h, sl))
    exposed.sort(key=lambda x: x[0])
    if exposed:
        rows = []
        for h, sl in exposed[:5]:
            when = "ya abierta" if h == 0 else _when(now + timedelta(hours=h))
            rows.append(f"{esc(sl.player.name)} ({when})")
        lines.append("🛡️ <b>Se abren pronto</b>: " + " · ".join(rows) + "\n   Plan: vender con la oferta de las 20:53; si no, blindar o subir la cláusula a ×1,20")

    if deliberate:
        lines.append("👑 Cláusula alta, abierta a propósito (si la pagan, ganamos): " + ", ".join(
            f"{esc(sl.player.name)} ×{sl.clause / sl.player.market_value:.2f}" for sl in deliberate))

    # --- bloqueo al líder
    leader = world.leader_team_id
    if leader and leader != world.my_team_id:
        gks = [sl for sl in world.rival_slots if sl.owner_team_id == leader and sl.player.position_id == 1 and sl.player.available]
        locked = [sl for sl in gks if sl.clause_locked_until and sl.clause_locked_until > now]
        free_from = max((sl.clause_locked_until for sl in locked), default=None)
        name = next((r.manager_name for r in world.standing if r.team_id == leader), "el líder")
        if not ap.complete_eleven(mine):
            lines.append(f"🎯 Bloqueo a {esc(name)}: parado hasta completar nuestro once")
        elif free_from and world.clause_freeze and free_from > world.clause_freeze[0]:
            lines.append(f"🎯 Bloqueo a {esc(name)}: no antes de la jornada siguiente (su portero queda libre el {_when(free_from)})")
        else:
            lines.append(f"🎯 Bloqueo a {esc(name)}: posible en la próxima congelación ({len(gks)} portero(s) suyo(s))")

    # --- brecha
    my = next((r for r in world.standing if r.team_id == world.my_team_id), None)
    top = max(world.standing, key=lambda r: r.points) if world.standing else None
    if my and top and top.team_id != my.team_id:
        lines.append(f"📈 Brecha con {esc(top.manager_name)}: {my.points - top.points:+d} pts ({my.points} contra {top.points}) · /brecha para la gráfica")

    # --- calendario
    out = world.outlook
    if out and out.in_break and out.next_first:
        lines.append(f"📅 <b>Parón</b> hasta el {out.next_first.astimezone():%d/%m} · inversión a crédito permitida hasta el 20%")
    elif out and out.next_break and (out.next_break[0] - now) <= timedelta(days=3):
        a, b = out.next_break
        lines.append(f"📅 <b>Parón en {max(0, (a - now).days)} día(s)</b>: del {a.astimezone():%d/%m} al {b.astimezone():%d/%m}")
    return "\n".join(lines)


def sync(store: Store, settings, text: str, force: bool = False) -> bool:
    """Edita el panel fijado (o lo crea y lo fija la primera vez). Devuelve True si se tocó Telegram."""
    digest = hashlib.sha1(text.encode()).hexdigest()[:12]
    last = float(store.get("panel_at") or 0)
    # la hora cambia en cada versión: se compara sin la primera línea
    body_hash = hashlib.sha1("\n".join(text.splitlines()[1:]).encode()).hexdigest()[:12]
    if not force and store.get("panel_hash") == body_hash and time.time() - last < 6 * 3600:
        return False
    if not force and time.time() - last < REFRESH_S:
        return False
    msg_id = store.get(PANEL_ID_KEY)
    ok = notify.edit_message(settings, int(msg_id), text) if msg_id else False
    if not ok:
        new_id = notify.send_all(settings, text, html=True)
        if new_id:
            store.set(PANEL_ID_KEY, str(new_id))
            notify.pin_message(settings, new_id)
    store.set("panel_hash", body_hash)
    store.set("panel_at", str(time.time()))
    return True
