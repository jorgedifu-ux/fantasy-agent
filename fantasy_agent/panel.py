"""Panel de misiones: UN mensaje fijado en Telegram que se edita en el sitio con el estado de lo importante, para poder mirarlo cuando quieras
sin que te llegue nada nuevo. Se actualiza como mucho cada 30 minutos y solo si ha cambiado algo."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone

from . import analysis, autopilot as ap, inbox, models, notify, service, wealth
from .storage import Store

PANEL_ID_KEY = "panel_message_id"
REFRESH_S = 10 * 60
DAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def short_name(name: str, me: bool = False) -> str:
    """Nombre corto y legible de un mánager: «JosinhoPermanbucano» → Josinho, «ALEIX VIDEL» → Aleix, «The Iberian One» → Iberian (o «Tú»)."""
    if me:
        return "Tú"
    n = name.strip()
    if n.lower().startswith("the "):
        n = n[4:]
    first = re.split(r"[ _]", n)[0]
    parts = re.findall(r"[A-Z][a-z]+|[A-Z]+(?![a-z])|[a-z]+|\d+", first)
    return (parts[0] if parts else first).capitalize()


def _when(dt: datetime) -> str:
    d = dt.astimezone()
    return f"{DAYS[d.weekday()]} {d:%d %H:%M}"


def _m(x: float) -> str:
    return f"{x / 1e6:.1f}M"


BUTTONS = [("📈 Gráficas", "cmd:brecha"), ("⚽ Jornada", "cmd:jornada"), ("📬 Resumen", "cmd:resumen"), ("🔄 Actualizar y limpiar", "cmd:misiones")]
MAX_CHARS = 3900
POS_LABEL = (("goalkeeper", "POR"), ("defender", "DEF"), ("midfield", "CEN"), ("striker", "DEL"))


def _fold(rows: list[str]) -> str:
    """Bloque plegable (se abre con un toque, sin depender del bot) con una línea por fila."""
    return "<blockquote expandable>" + "\n".join(rows) + "</blockquote>" if rows else ""


def _departures(world, api, opening) -> dict[str, tuple[str, str]]:
    """pid -> (cómo se fue, a qué hora) de los jugadores que han salido de tu plantilla desde que empezó la jornada: vendidos a LaLiga o clausulados."""
    try:
        rows = service._all_activity(api, world.league_id, max_pages=2)
    except Exception:
        return {}
    names = {str(r.manager_id): short_name(r.manager_name) for r in world.standing}
    me = next((str(r.manager_id) for r in world.standing if r.team_id == world.my_team_id), "")
    out: dict[str, tuple[str, str]] = {}
    for a in rows:
        when = models.parse_dt(models.pick(a, "createdAt"))
        if not when or (opening and when < opening):
            continue
        kind = models.to_int(models.pick(a, "activityTypeId"))
        u1, u2 = str(models.pick(a, "user1Id", default="")), str(models.pick(a, "user2Id", default=""))
        pid = str(models.pick(a, "playerMasterId", default=""))
        if kind == 33 and u1 == me:
            out[pid] = ("vendido", f"{when.astimezone():%d/%m %H:%M}")
        elif kind == 1 and u2 == me:
            out[pid] = (f"clausulado por {names.get(u1, 'un rival')}", f"{when.astimezone():%d/%m %H:%M}")
    return out


def jornada_data(world, api, store: Store | None = None) -> dict | None:
    """Puntos de la jornada en juego: los de tu once (con su partido, si aún no se ha jugado), los de quien ya se ha ido (vendido o clausulado, con
    el motivo) y el total real de la clasificación. Una sola fuente para el panel y para `/jornada`."""
    try:
        wk = api.current_week() or {}
        cur = int(wk.get("weekNumber") or 0)
        closing = models.parse_dt(wk.get("closingWeekDate"))
        opening = models.parse_dt(wk.get("openingWeekDate"))
        lu = api.lineup(world.my_team_id)
        raw = {str(p["id"]): p for p in api.players()}
        week_rows = api.standing_week(world.league_id, cur)
    except Exception:
        return None
    pos_label = {1: "POR", 2: "DEF", 3: "CEN", 4: "DEL"}
    rows, seen = [], set()

    def points(pid: str):
        r = raw.get(pid, {})
        return next((x.get("points") for x in (r.get("weekPoints") or []) if x.get("weekNumber") == cur), None)

    for key, label in POS_LABEL:
        for e in (lu.get("formation") or {}).get(key) or []:
            if not isinstance(e, dict):
                continue
            pm = e.get("playerMaster") or {}
            pid = str(pm.get("id"))
            r = raw.get(pid, {})
            pts = points(pid)
            fx = world.fixtures.get(str(r.get("teamId")))
            when = fx.when if (pts is None and fx and fx.when and (closing is None or fx.when <= closing)) else None
            rows.append({"pid": pid, "pos": label, "name": pm.get("nickname") or r.get("nickname") or "?", "pts": pts, "when": when, "gone": None})
            seen.add(pid)
    # los que estaban en el once al empezar (guardado por el piloto) o se han ido desde entonces
    snap = json.loads(store.get("xi_snapshot") or "{}") if store is not None else {}
    gone = _departures(world, api, opening)
    candidates = {**{x["pid"]: x for x in (snap.get("ids") or []) if snap.get("week") == cur}, **{pid: {} for pid in gone}}
    for pid in candidates:
        if pid in seen or pid not in raw:
            continue
        r = raw[pid]
        how = gone.get(pid)
        if how is None and snap.get("week") != cur:
            continue
        pts = points(pid)
        if how is None:
            how = ("fuera de tu plantilla", "")
        rows.append({"pid": pid, "pos": pos_label.get(models.to_int(r.get("positionId")), "—"), "name": r.get("nickname") or "?", "pts": pts, "when": None,
                     "gone": f"{how[0]}{(' · ' + how[1]) if how[1] else ''}"})
    order = {"POR": 0, "DEF": 1, "CEN": 2, "DEL": 3}
    rows.sort(key=lambda x: (order.get(x["pos"], 9), x["gone"] is not None, -(x["pts"] if x["pts"] is not None else -99)))
    mine = next((x for x in week_rows if str(x["team"]["id"]) == str(world.my_team_id)), None)
    total = int(mine["points"]) if mine else sum(r["pts"] or 0 for r in rows)
    accounted = sum(r["pts"] or 0 for r in rows if r["gone"] is None or r["pts"] is not None)
    return {"week": cur, "live": bool(wk.get("isLive")), "total": total, "rows": rows, "sold": max(0, total - accounted),
            "managers": sorted(((x["team"]["manager"]["managerName"], int(x["points"])) for x in week_rows), key=lambda z: -z[1])}


def jornada_lines(d: dict, full: dict[str, str] | None = None) -> list[str]:
    full = full or {}
    lines = []
    for r in d["rows"]:
        name = notify.esc(full.get(str(r.get("pid")), r["name"]))
        pts = f"<b>{r['pts']}</b>" if r["pts"] is not None else "–"
        when = f" ({_when(r['when'])})" if r.get("when") and r["pts"] is None else ""
        gone = f" · 🚪 {notify.esc(r['gone'])}" if r.get("gone") else ""
        lines.append(f"{r['pos']} {name} · {pts}{when}{gone}")
    if d["sold"] > 0:
        lines.append(f"+ {d['sold']} más (de jugadores que ya no están en tu once)")
    if any(r.get("gone") for r in d["rows"]):
        lines.append("🚪 = ya no está en tu plantilla; lo que puntuó antes de irse cuenta.")
    return lines


def render(world, store: Store, *, hours_to_deadline: float | None, week: dict | None = None, now: datetime | None = None,
           jornada: dict | None = None, full: dict[str, str] | None = None) -> str:
    """Panel para leer en el móvil: una sección por tema, separadas por una línea en blanco y líneas cortas. Los datos (jornada, brecha, rivales, plantilla,
    pendientes) van dentro, plegados: se consultan sin esperar al bot, tal y como se guardaron en la última actualización."""
    now = now or datetime.now(timezone.utc)
    esc = notify.esc
    full = full or {}
    nm = lambda p: esc(full.get(str(p.id), p.name))      # noqa: E731  nombre completo si se conoce
    mine = [sl.player for sl in world.my_slots]
    local = now.astimezone()
    sections: list[str] = [f"🎯 <b>MISIONES</b>\n<i>actualizado {DAYS[local.weekday()]} {local:%d/%m %H:%M}</i>"]
    names = {str(r.manager_id): r.manager_name for r in world.standing}
    me_id = next((str(r.manager_id) for r in world.standing if r.team_id == world.my_team_id), "")
    top = max(world.standing, key=lambda r: r.points) if world.standing else None
    my_name = names.get(me_id, "")

    # --- jornada en juego
    if jornada and jornada["rows"] is not None:
        rivals_wk = " · ".join(f"{esc(short_name(n, n == my_name))} {p}" for n, p in jornada["managers"])
        sections.append(f"⚽ <b>Jornada {jornada['week']}</b>{' · en juego' if jornada['live'] else ''}\n   llevas <b>{jornada['total']}</b> pts · {rivals_wk}\n"
                        + _fold(jornada_lines(jornada, full)))

    # --- próxima jornada y once
    short = [f"{n} {('portero', 'defensa', 'centrocampista', 'delantero')[pos - 1]}" for pos, n in analysis.position_shortage(world.my_slots).items() if n > 0]
    xi_ok = ap.complete_eleven(mine)
    nxt = world.outlook.next_first if world.outlook and world.outlook.next_first else None
    lines = []
    if hours_to_deadline is not None and hours_to_deadline > 0 and nxt:
        lines.append(f"📋 <b>Próxima jornada</b>\n   empieza {_when(nxt)}")
        if world.clause_freeze:
            lines.append(f"   cláusulas congeladas desde {_when(world.clause_freeze[0])}")
    else:
        lines.append("📋 <b>Once</b>")
    lines.append("   ✅ once legal" if xi_ok else "   ⚠️ <b>once incompleto</b>" + (f": falta {', '.join(short)}" if short else ""))
    sections.append("\n".join(lines))

    # --- dinero y pujas
    bids = [b for b in store.unresolved_market_bids("buy") if not b.get("expires_at") or b["expires_at"] > time.time() - 600]
    sections.append(f"💰 <b>Caja</b> {_m(world.my_cash)}\n   {len(world.my_slots)} jugadores · valen {_m(sum(p.market_value for p in mine))}")
    if bids:
        rows = [f"{esc(b['player_name'])} {_m(b['price'])}" + (f" · resuelve {datetime.fromtimestamp(b['expires_at']):%d/%m %H:%M}" if b.get("expires_at") else "")
                for b in bids[:6]]
        sections.append(f"🛒 <b>Pujas en curso</b> ({len(bids)})\n" + _fold(rows))
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
        rows = [f"{nm(sl.player)} · " + ("ya abierta" if h == 0 else _when(now + timedelta(hours=h))) for h, sl in exposed[:5]]
        rows.append("Plan: vender con la oferta de las 20:53; si no llega, blindar (24 h) o subir la cláusula a ×1,20.")
        sections.append(f"🛡️ <b>Se abren pronto</b> ({len(exposed)})\n" + _fold(rows))
    if deliberate:
        rows = [f"{nm(sl.player)} ×{sl.clause / sl.player.market_value:.2f}" for sl in deliberate]
        rows.append("Si un rival la paga, ganamos dinero: ni se blinda ni se vende barato.")
        sections.append("👑 <b>Cláusula alta a propósito</b>\n" + _fold(rows))

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
        sections.append(f"🎯 <b>Bloqueo a {esc(short_name(name))}</b>\n   {state}")

    # --- brecha y rivales (datos guardados)
    ser = wealth.series(store)
    days = sorted(ser)
    my = next((r for r in world.standing if r.team_id == world.my_team_id), None)
    if my and top and top.team_id != my.team_id:
        rows = [f"Puntos: tú {my.points} · {esc(short_name(top.manager_name))} {top.points} → {my.points - top.points:+d}"]
        if days and me_id in ser[days[-1]] and str(top.manager_id) in ser[days[-1]]:
            a, b = ser[days[-1]][me_id], ser[days[-1]][str(top.manager_id)]
            rows.append(f"Patrimonio: tú {a:.0f}M · él {b:.0f}M → {a - b:+.0f}M ({a / b * 100:.0f}% del suyo)")
            for off in (5, 10, 20):
                d0 = (datetime.fromisoformat(days[-1]) - timedelta(days=off)).date().isoformat()
                if d0 in ser and me_id in ser[d0] and str(top.manager_id) in ser[d0]:
                    g0 = ser[d0][str(top.manager_id)] - ser[d0][me_id]
                    rows.append(f"   hace {off} días la diferencia era {g0:.0f}M")
        sections.append(f"📈 <b>Brecha</b> {my.points - top.points:+d} pts\n" + _fold(rows))
    if days and len(world.standing) > 1:
        rows = []
        for r in sorted(world.standing, key=lambda r: -r.points):
            mid = str(r.manager_id)
            cur = ser[days[-1]].get(mid)
            d5 = (datetime.fromisoformat(days[-1]) - timedelta(days=5)).date().isoformat()
            prev = ser.get(d5, {}).get(mid)
            delta = f" ({cur - prev:+.0f}M en 5 días)" if cur is not None and prev is not None else ""
            rows.append(f"{esc(short_name(r.manager_name, mid == me_id))} · {r.points} pts" + (f" · {cur:.0f}M{delta}" if cur is not None else ""))
        sections.append("🏆 <b>Todos</b>\n" + _fold(rows))

    # --- plantilla
    rows = []
    for sl in sorted(world.my_slots, key=lambda x: (x.player.position_id, -x.player.market_value)):
        p = sl.player
        if sl.shielded_until and sl.shielded_until > now:
            prot = f"🛡️ {sl.shielded_until.astimezone():%d/%m %H:%M}"
        elif sl.clause_locked_until and sl.clause_locked_until > now:
            prot = f"🔒 {sl.clause_locked_until.astimezone():%d/%m}"
        else:
            prot = "🔓"
        rows.append(f"{('POR', 'DEF', 'CEN', 'DEL')[p.position_id - 1]} {nm(p)} · {p.market_value / 1e6:.1f}M · {prot}")
    sections.append(f"👥 <b>Plantilla</b> ({len(world.my_slots)})\n" + _fold(rows))

    # --- novedades pendientes del resumen
    pend = inbox.pending(store)
    if pend:
        sections.append(f"📬 <b>Pendientes del resumen</b> ({len(pend)})\n" + _fold([inbox._label(x["text"], 90) for x in pend[-8:]]))

    # --- parón
    out = world.outlook
    if out and out.in_break and out.next_first:
        sections.append(f"📅 <b>Parón</b> hasta el {out.next_first.astimezone():%d/%m}\n   inversión a crédito permitida (hasta el 20%)")
    elif out and out.next_break and (out.next_break[0] - now) <= timedelta(days=3):
        a, b = out.next_break
        sections.append(f"📅 <b>Parón en {max(0, (a - now).days)} día(s)</b>\n   del {a.astimezone():%d/%m} al {b.astimezone():%d/%m}")
    sections.append("<i>Lo plegado se abre con un toque. Los botones los atiendo en cuanto estoy escuchando (a veces hasta 15 min).</i>")
    text = "\n\n".join(sections)
    if len(text) > MAX_CHARS:      # Telegram corta a 4096: se quitan primero los pendientes y la plantilla plegada
        text = "\n\n".join(s for s in sections if not s.startswith(("📬", "👥")))
    return text[:4090]


def sync(store: Store, settings, text: str, force: bool = False) -> bool:
    """Edita el panel fijado (o lo crea y lo fija la primera vez). Devuelve True si se tocó Telegram. Como mucho cada 10 min, y solo si ha cambiado
    algo, pero al menos cada 30 min: si lo borras, vuelve a aparecer solo."""
    last = float(store.get("panel_at") or 0)
    body_hash = hashlib.sha1("\n".join(text.splitlines()[1:]).encode()).hexdigest()[:12]      # la hora no cuenta
    if not force:
        if time.time() - last < REFRESH_S:
            return False
        if store.get("panel_hash") == body_hash and time.time() - last < 30 * 60:
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
