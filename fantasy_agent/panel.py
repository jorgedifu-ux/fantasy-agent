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
REFRESH_S = 10 * 60
DAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def _when(dt: datetime) -> str:
    d = dt.astimezone()
    return f"{DAYS[d.weekday()]} {d:%d %H:%M}"


def _m(x: float) -> str:
    return f"{x / 1e6:.1f}M"


BUTTONS = [("📈 Brecha", "cmd:brecha"), ("⚽ Jornada", "cmd:jornada"), ("👥 Plantilla", "cmd:plantilla"), ("📬 Resumen", "cmd:resumen")]


def render(world, store: Store, *, hours_to_deadline: float | None, week: dict | None = None, now: datetime | None = None) -> str:
    """Panel para leer en el móvil: una sección por tema, separadas por una línea en blanco, líneas cortas y las explicaciones plegadas."""
    now = now or datetime.now(timezone.utc)
    esc = notify.esc
    mine = [sl.player for sl in world.my_slots]
    local = now.astimezone()
    sections: list[str] = [f"🎯 <b>MISIONES</b>\n<i>{DAYS[local.weekday()]} {local:%d/%m %H:%M}</i>"]

    # --- jornada y once
    live = bool((week or {}).get("isLive"))
    n_week = (week or {}).get("weekNumber")
    short = [f"{n} {('portero', 'defensa', 'centrocampista', 'delantero')[pos - 1]}" for pos, n in analysis.position_shortage(world.my_slots).items() if n > 0]
    xi_ok = ap.complete_eleven(mine)
    head = [f"⚽ <b>Jornada {n_week}</b>" + (" · en juego" if live else "")] if live else []
    nxt = world.outlook.next_first if world.outlook and world.outlook.next_first else None
    lines = []
    if hours_to_deadline is not None and hours_to_deadline > 0 and nxt:
        lines.append(f"📋 <b>Próxima jornada</b>\n   empieza {_when(nxt)}")
        if world.clause_freeze:
            lines.append(f"   cláusulas congeladas desde {_when(world.clause_freeze[0])}")
    else:
        lines.append("📋 <b>Once</b>")
    lines.append("   ✅ once legal" if xi_ok else "   ⚠️ <b>once incompleto</b>" + (f": falta {', '.join(short)}" if short else ""))
    sections.append("\n".join(head + lines))

    # --- dinero
    sections.append(f"💰 <b>Caja</b> {_m(world.my_cash)}\n   {len(world.my_slots)} jugadores · valen {_m(sum(p.market_value for p in mine))}")

    # --- fichajes en curso
    bids = [b for b in store.unresolved_market_bids("buy") if not b.get("expires_at") or b["expires_at"] > time.time() - 600]
    if bids:
        rows = [f"   • {esc(b['player_name'])} {_m(b['price'])}" + (f" · resuelve {datetime.fromtimestamp(b['expires_at']):%d/%m %H:%M}" if b.get("expires_at") else "")
                for b in bids[:6]]
        sections.append("🛒 <b>Pujas en curso</b>\n" + "\n".join(rows))
    else:
        sections.append("🛒 <b>Pujas en curso</b>\n   ninguna")

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
        rows = [f"   • {esc(sl.player.name)} · " + ("ya abierta" if h == 0 else _when(now + timedelta(hours=h))) for h, sl in exposed[:5]]
        sections.append("🛡️ <b>Se abren pronto</b>\n" + "\n".join(rows) +
                        "\n<blockquote expandable>Plan: vender con la oferta de las 20:53; si no llega, blindar (24 h) o subir la cláusula a ×1,20.</blockquote>")
    if deliberate:
        sections.append("👑 <b>Cláusula alta a propósito</b>\n" + "\n".join(
            f"   • {esc(sl.player.name)} ×{sl.clause / sl.player.market_value:.2f}" for sl in deliberate) +
            "\n<blockquote expandable>Si un rival la paga, ganamos dinero: ni se blinda ni se vende barato.</blockquote>")

    # --- bloqueo al líder
    leader = world.leader_team_id
    if leader and leader != world.my_team_id:
        gks = [sl for sl in world.rival_slots if sl.owner_team_id == leader and sl.player.position_id == 1 and sl.player.available]
        locked = [sl for sl in gks if sl.clause_locked_until and sl.clause_locked_until > now]
        free_from = max((sl.clause_locked_until for sl in locked), default=None)
        name = next((r.manager_name for r in world.standing if r.team_id == leader), "el líder")
        if not xi_ok:
            state = "parado hasta completar nuestro once"
        elif free_from and world.clause_freeze and free_from > world.clause_freeze[0]:
            state = f"no antes de la jornada siguiente\n   (su portero queda libre el {_when(free_from)})"
        else:
            state = f"posible en la próxima congelación\n   ({len(gks)} portero(s) suyo(s))"
        sections.append(f"🎯 <b>Bloqueo a {esc(name)}</b>\n   {state}")

    # --- brecha
    my = next((r for r in world.standing if r.team_id == world.my_team_id), None)
    top = max(world.standing, key=lambda r: r.points) if world.standing else None
    if my and top and top.team_id != my.team_id:
        sections.append(f"📈 <b>Brecha</b> {my.points - top.points:+d} pts\n   tú {my.points} · {esc(top.manager_name)} {top.points}")

    # --- calendario
    out = world.outlook
    if out and out.in_break and out.next_first:
        sections.append(f"📅 <b>Parón</b> hasta el {out.next_first.astimezone():%d/%m}\n   inversión a crédito permitida (hasta el 20%)")
    elif out and out.next_break and (out.next_break[0] - now) <= timedelta(days=3):
        a, b = out.next_break
        sections.append(f"📅 <b>Parón en {max(0, (a - now).days)} día(s)</b>\n   del {a.astimezone():%d/%m} al {b.astimezone():%d/%m}")
    return "\n\n".join(sections)


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
    ok = notify.edit_message(settings, int(msg_id), text, buttons=BUTTONS) if msg_id else False
    if not ok:
        new_id = notify.send_all(settings, text, html=True, buttons=BUTTONS)
        if new_id:
            store.set(PANEL_ID_KEY, str(new_id))
            notify.pin_message(settings, new_id)
    store.set("panel_hash", body_hash)
    store.set("panel_at", str(time.time()))
    return True
