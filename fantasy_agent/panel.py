"""Panel de misiones: UN mensaje fijado en Telegram que se edita en el sitio con el estado de lo importante, para poder mirarlo cuando quieras
sin que te llegue nada nuevo. Se actualiza como mucho cada 30 minutos y solo si ha cambiado algo."""
from __future__ import annotations

import hashlib
import html
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


def _c(x: float, nd: int = 1) -> str:
    """Número con coma decimal, como se escribe en España."""
    return f"{x:.{nd}f}".replace(".", ",")


def _m(x: float) -> str:
    return f"{_c(x / 1e6)}M"


def clean_name(name: str) -> str:
    """Quita palabras repetidas seguidas del nombre completo de la API («Moriba Kourouma Kourouma» → «Moriba Kourouma»)."""
    out: list[str] = []
    for w in name.split():
        if not out or out[-1].lower() != w.lower():
            out.append(w)
    return " ".join(out)


def _visible_len(text: str) -> int:
    return len(html.unescape(re.sub(r"<[^>]+>", "", text)))


BUTTONS = [("🏟 Partidos", "cmd:partidos"), ("📈 Brecha", "cmd:brecha"), ("📬 Resumen", "cmd:resumen"), ("🔄 Actualizar y limpiar", "cmd:misiones")]
MAX_CHARS = 3950
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
    """La jornada en juego, completa: tu once registrado (con puntos o con la hora y el rival del partido que falta), los que están fuera del once, los que ya se
    han ido (vendidos o clausulados, con el motivo) y el total real de la clasificación. Una sola fuente para el panel y para `/jornada`."""
    try:
        wk = api.current_week() or {}
        cur = int(wk.get("weekNumber") or 0)
        opening = models.parse_dt(wk.get("openingWeekDate"))
        lu = api.lineup(world.my_team_id)
        raw = {str(p["id"]): p for p in api.players()}
        week_rows = api.standing_week(world.league_id, cur)
    except Exception:
        return None
    try:
        sched = {}
        for m in models.as_list(api.calendar(cur), "matches", "elements", "calendar"):
            when = models.parse_dt(m.get("matchDate") or m.get("date"))
            lo, vi = str(m.get("localId")), str(m.get("visitorId"))
            sched[lo] = (when, vi, True)
            sched[vi] = (when, lo, False)
    except Exception:
        sched = {}
    now = datetime.now(timezone.utc)
    pos_label = {1: "POR", 2: "DEF", 3: "CEN", 4: "DEL"}
    rows, seen = [], set()

    def points(pid: str):
        r = raw.get(pid, {})
        return next((x.get("points") for x in (r.get("weekPoints") or []) if x.get("weekNumber") == cur), None)

    def match(pid: str, pts):
        """(hora, rival) del partido de la jornada si aún no se ha jugado; ('jugado', rival) si ya pasó sin puntos."""
        info = sched.get(str(raw.get(pid, {}).get("teamId")))
        if not info or pts is not None or not info[0]:
            return None, None, False
        rival = world.team_names.get(info[1], "")
        vs = (f"vs {rival}" if info[2] else f"en {rival}") if rival else ""
        return info[0], vs, info[0] < now - timedelta(hours=2)

    for key, label in POS_LABEL:
        for e in (lu.get("formation") or {}).get(key) or []:
            if not isinstance(e, dict):
                continue
            pm = e.get("playerMaster") or {}
            pid = str(pm.get("id"))
            r = raw.get(pid, {})
            pts = points(pid)
            when, vs, missed = match(pid, pts)
            rows.append({"pid": pid, "pos": label, "name": pm.get("nickname") or r.get("nickname") or "?", "pts": pts, "when": when, "vs": vs,
                         "missed": missed, "avg": r.get("averagePoints"), "gone": None})
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
                     "vs": "", "missed": False, "avg": r.get("averagePoints"), "gone": f"{how[0]}{(' · ' + how[1]) if how[1] else ''}"})
        seen.add(pid)
    # los que siguen en la plantilla pero no están en el once
    bench = []
    for sl in world.my_slots:
        if sl.player.id not in seen:
            bench.append({"pid": sl.player.id, "pos": pos_label.get(sl.player.position_id, "—"), "name": sl.player.name, "avg": sl.player.avg_points,
                          "status": sl.player.status})
    order = {"POR": 0, "DEF": 1, "CEN": 2, "DEL": 3}
    rows.sort(key=lambda x: (order.get(x["pos"], 9), x["gone"] is not None, -(x["pts"] if x["pts"] is not None else -99)))
    bench.sort(key=lambda x: (order.get(x["pos"], 9), -(x["avg"] or 0)))
    # huecos del once registrado: la formación dice cuántos de cada posición eran
    form = (lu.get("formation") or {}).get("tacticalFormation") or []
    want = {"POR": 1, "DEF": form[0] if len(form) > 0 else 0, "CEN": form[1] if len(form) > 1 else 0, "DEL": form[2] if len(form) > 2 else 0}
    here = {k: sum(1 for r in rows if r["pos"] == k and not r["gone"]) for k in want}
    mine = next((x for x in week_rows if str(x["team"]["id"]) == str(world.my_team_id)), None)
    total = int(mine["points"]) if mine else sum(r["pts"] or 0 for r in rows)
    accounted = sum(r["pts"] or 0 for r in rows if r["gone"] is None or r["pts"] is not None)
    return {"week": cur, "live": bool(wk.get("isLive")), "total": total, "rows": rows, "bench": bench, "formation": form,
            "missing": {k: want[k] - here[k] for k in want if want[k] - here[k] > 0}, "sold": max(0, total - accounted),
            "managers": sorted(((x["team"]["manager"]["managerName"], int(x["points"])) for x in week_rows), key=lambda z: -z[1])}


POS_ICON = {"POR": "🧤", "DEF": "🛡️", "CEN": "🧠", "DEL": "⚽"}


def jornada_blocks(d: dict, full: dict[str, str] | None = None) -> dict[str, list[str]]:
    """La jornada en tres bloques que se abren por separado, una línea por jugador con su icono de posición y de estado (✅ jugó y sus puntos · ⏳ aún no, con
    hora y rival · ➖ no jugó): «once» (los que siguen en tu once y los huecos), «fuera» (en la plantilla pero fuera del once) y «ya_no» (se han ido)."""
    full = full or {}
    nm = lambda r: notify.esc(clean_name(full.get(str(r.get("pid")), r["name"])))        # noqa: E731
    here = [r for r in d["rows"] if not r.get("gone")]
    once: list[str] = []
    for pos in ("POR", "DEF", "CEN", "DEL"):
        for r in [r for r in here if r["pos"] == pos]:
            if r["pts"] is not None:
                state = f"✅ <b>{r['pts']} pts</b>"
            elif r.get("missed"):
                state = "➖ no jugó"
            else:
                state = "⏳ " + (_when(r["when"]) if r.get("when") else "sin jugar") + (f" · {notify.esc(r['vs'])}" if r.get("vs") else "")
            once.append(f"{POS_ICON[pos]} {nm(r)} — {state}")
        gap = (d.get("missing") or {}).get(pos, 0)
        if gap:
            once.append(f"{POS_ICON[pos]} <i>{gap} hueco(s): ya no están</i>")
    fuera = []
    for b in d.get("bench") or []:
        hurt = " · ⚠️ " + notify.esc(b["status"]) if (b.get("status") or "ok").lower() not in ("ok", "") else ""
        fuera.append(f"{POS_ICON.get(b['pos'], '•')} {notify.esc(clean_name(full.get(str(b['pid']), b['name'])))} — media {_c(b['avg'] or 0)}{hurt}")
    ya_no = []
    for r in [r for r in d["rows"] if r.get("gone")]:
        res = f"<b>{r['pts']} pts</b>" if r["pts"] is not None else "sin jugar"
        ya_no.append(f"{POS_ICON.get(r['pos'], '•')} {nm(r)} — {res} · {notify.esc(r['gone'])}")
    if ya_no:
        ya_no.append("<i>Lo que puntuó antes de irse cuenta.</i>")
    if d["sold"] > 0:
        ya_no.append(f"<i>+ {d['sold']} pts más de jugadores que ya no están en tu once.</i>")
    return {"once": once, "fuera": fuera, "ya_no": ya_no}


def plantilla_lines(world, now: datetime, full: dict[str, str] | None = None) -> list[str]:
    """Plantilla, una línea por jugador con su icono de posición: nombre — valor · protección (🔒 hasta cuándo, 🔓 abierta con su ×, 🛡️ blindado)."""
    full = full or {}
    icon = {1: "🧤", 2: "🛡️", 3: "🧠", 4: "⚽"}
    lines: list[str] = []
    for sl in sorted(world.my_slots, key=lambda x: (x.player.position_id, -x.player.market_value)):
        p = sl.player
        ratio = sl.clause / p.market_value if p.market_value else 0
        if sl.shielded_until and sl.shielded_until > now:
            prot = f"🛡️ hasta {_when(sl.shielded_until)}"
        elif sl.clause_locked_until and sl.clause_locked_until > now:
            prot = f"🔒 hasta el {sl.clause_locked_until.astimezone():%d/%m}"
        else:
            prot = f"🔓 abierta ×{_c(ratio, 2)}"
        lines.append(f"{icon.get(p.position_id, '•')} {notify.esc(clean_name(full.get(str(p.id), p.name)))} — {_m(p.market_value)} · {prot}")
    return lines


def _es(text: str) -> str:
    """Decimales a la española y a 1 cifra: «301.29M» → «301,3M»."""
    return re.sub(r"([+-]?\d+\.\d+)M", lambda m: (("+" if m.group(1).startswith("+") else "") + f"{float(m.group(1)):.1f}M").replace(".", ","), text)


def results_section(review_lines: list[str] | None) -> str | None:
    """«Resultados»: una línea con el balance de las operaciones y, plegado, el detalle ordenado por categorías (patrimonio, operaciones cerradas, sin vender)."""
    if not review_lines:
        return None
    summary = next((l for l in review_lines if l.startswith("Operaciones cerradas")), None)
    head = "📊 <b>Resultados</b>"
    if summary:
        m = re.search(r":\s*(\d+) · (\d+) con ganancia · resultado ([+-][\d.]+M)", summary)
        head += f"\n{m.group(1)} operaciones · {m.group(2)} con ganancia · {_es(m.group(3))}" if m else ""
    body: list[str] = []
    for l in review_lines[1:]:
        if l.startswith("Puntos:"):
            continue
        icon = "💰 " if l.startswith("Patrimonio") else "🔁 " if l.startswith("Operaciones") else "📦 " if l.startswith("Sin vender") else ""
        if l.startswith("  vs "):
            body.append("• " + _es(l.strip()))
        elif l.startswith("  "):
            body.append("• " + _es(l.strip()))
        else:
            body.append(icon + _es(l.strip()))
    return head + "\n" + _fold(body)


MEDALS = ("🥇", "🥈", "🥉")


def _bar(n: int, total: int, on: str = "🟩", off: str = "⬜", width: int = 6) -> str:
    """Barra de emojis: n de total, a `width` casillas."""
    if total <= 0:
        return off * width
    k = max(0, min(width, round(n / total * width)))
    return on * k + off * (width - k)


def render(world, store: Store, *, hours_to_deadline: float | None, week: dict | None = None, now: datetime | None = None,
           jornada: dict | None = None, full: dict[str, str] | None = None, review: list[str] | None = None) -> str:
    """Panel visual para el móvil: medallas, barras de emojis y líneas cortas; el detalle va plegado. Los datos se consultan sin esperar al bot, tal y como se
    guardaron en la última actualización."""
    now = now or datetime.now(timezone.utc)
    esc = notify.esc
    full = full or {}
    nm = lambda p: esc(clean_name(full.get(str(p.id), p.name)))      # noqa: E731  nombre completo si se conoce
    mine = [sl.player for sl in world.my_slots]
    local = now.astimezone()
    sections: list[str] = [f"🎯 <b>MISIONES</b>\n<i>actualizado {DAYS[local.weekday()]} {local:%d/%m %H:%M}</i>"]
    names = {str(r.manager_id): r.manager_name for r in world.standing}
    me_id = next((str(r.manager_id) for r in world.standing if r.team_id == world.my_team_id), "")
    my_name = names.get(me_id, "")
    ranking = sorted(world.standing, key=lambda r: -r.points)
    top = ranking[0] if ranking else None
    my = next((r for r in world.standing if r.team_id == world.my_team_id), None)
    ser = wealth.series(store)
    days = sorted(ser)

    # --- clasificación: cada uno en su línea; lo plegado es OTRA información (el patrimonio y la brecha)
    if ranking:
        pods = [f"{MEDALS[i] if i < 3 else f'{i + 1}º'} {esc(short_name(r.manager_name, str(r.manager_id) == me_id))} · <b>{r.points} pts</b>" for i, r in enumerate(ranking)]
        rows = []
        for r in ranking:
            mid = str(r.manager_id)
            cur = ser[days[-1]].get(mid) if days else None
            if cur is None:
                continue
            d5 = (datetime.fromisoformat(days[-1]) - timedelta(days=5)).date().isoformat()
            prev = ser.get(d5, {}).get(mid)
            rows.append(f"💰 {esc(short_name(r.manager_name, mid == me_id))} — {cur:.0f}M" + (f" ({cur - prev:+.0f} en 5 días)" if prev is not None else ""))
        if my and top and top.team_id != my.team_id:
            rn = esc(short_name(top.manager_name))
            rows += ["", f"📈 <b>Brecha con {rn}</b>", f"Puntos {my.points - top.points:+d}"]
            if days and me_id in ser[days[-1]] and str(top.manager_id) in ser[days[-1]]:
                a, b = ser[days[-1]][me_id], ser[days[-1]][str(top.manager_id)]
                rows.append(f"Patrimonio {a - b:+.0f}M · tienes el {a / b * 100:.0f}% del suyo")
                hist = []
                for off in (5, 10, 20):
                    d0 = (datetime.fromisoformat(days[-1]) - timedelta(days=off)).date().isoformat()
                    if d0 in ser and me_id in ser[d0] and str(top.manager_id) in ser[d0]:
                        hist.append(f"hace {off} días {ser[d0][str(top.manager_id)] - ser[d0][me_id]:.0f}M")
                if hist:
                    rows.append("Diferencia de patrimonio: " + " · ".join(hist))
        sections.append("🏆 <b>CLASIFICACIÓN</b>\n" + "\n".join(pods) + (f"\n<i>Patrimonio y brecha ▾</i>\n" + _fold(rows) if rows else ""))

    # --- jornada en juego: resumen visible y tres bloques que se abren por separado
    if jornada and jornada["rows"] is not None:
        here = [r for r in jornada["rows"] if not r.get("gone")]
        played = sum(1 for r in here if r["pts"] is not None or r.get("missed"))
        others = " · ".join(f"{esc(short_name(n, n == my_name))} {p}" for n, p in jornada["managers"] if n != my_name)
        blocks = jornada_blocks(jornada, full)
        form = "-".join(str(x) for x in jornada.get("formation") or [])
        miss = sum((jornada.get("missing") or {}).values())
        sec = (f"⚽ <b>JORNADA {jornada['week']}</b>{' · en juego' if jornada['live'] else ''}\n"
               f"{_bar(played, len(here))} {played} de {len(here)} han jugado\n"
               f"Llevas <b>{jornada['total']} pts</b>  <i>({others})</i>")
        if blocks["once"]:
            sec += f"\n\n🧩 <b>Tu once{f' ({form})' if form else ''}</b> · {len(here)} de {len(here) + miss}\n" + _fold(blocks["once"])
        if blocks["fuera"]:
            sec += f"\n\n🪑 <b>Fuera del once</b> ({len(blocks['fuera'])}) · no puntúan\n" + _fold(blocks["fuera"])
        if blocks["ya_no"]:
            sec += f"\n\n🚪 <b>Ya no están</b> ({len([r for r in jornada['rows'] if r.get('gone')])})\n" + _fold(blocks["ya_no"])
        sections.append(sec)

    # --- próxima jornada y once
    shortage = {pos: n for pos, n in analysis.position_shortage(world.my_slots).items() if n > 0}
    xi_ok = ap.complete_eleven(mine)
    count = {pos: sum(1 for p in mine if p.position_id == pos) for pos in (1, 2, 3, 4)}
    squad_line = " · ".join(f"{('🧤', '🛡️', '🧠', '⚽')[pos - 1]}{count[pos]}{'⚠️' if pos in shortage else ''}" for pos in (1, 2, 3, 4))
    nxt = world.outlook.next_first if world.outlook and world.outlook.next_first else None
    head = "📋 <b>PRÓXIMA JORNADA</b>" + (f" · {_when(nxt)}" if hours_to_deadline is not None and hours_to_deadline > 0 and nxt else "")
    lines = [head, squad_line + ("   ✅ once legal" if xi_ok else "   ⚠️ <b>once incompleto</b>")]
    if hours_to_deadline is not None and hours_to_deadline > 0 and world.clause_freeze:
        lines.append(f"🧊 cláusulas congeladas desde {_when(world.clause_freeze[0])}")
    sections.append("\n".join(lines))

    # --- dinero y pujas
    bids = [b for b in store.unresolved_market_bids("buy") if not b.get("expires_at") or b["expires_at"] > time.time() - 600]
    money = f"💰 <b>CAJA {_m(world.my_cash)}</b>\n{len(world.my_slots)} jugadores · valen {_m(sum(p.market_value for p in mine))}"
    if bids:
        rows = [f"• {esc(b['player_name'])} {_m(b['price'])}" + (f" · resuelve {datetime.fromtimestamp(b['expires_at']):%d/%m %H:%M}" if b.get("expires_at") else "")
                for b in bids[:6]]
        money += f"\n🛒 <b>{len(bids)} puja(s) en curso</b>\n" + "\n".join(rows)
    sections.append(money)

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
        rows = [f"• {nm(sl.player)} — " + ("ya abierta" if h == 0 else _when(now + timedelta(hours=h))) for h, sl in exposed[:5]]
        sections.append(f"🛡️ <b>SE ABREN PRONTO</b> ({len(exposed)})\n" + "\n".join(rows) +
                        "\n<i>Plan: vender con la oferta de las 20:53; si no llega, blindar (24 h) o subir la cláusula a ×1,20.</i>")
    if deliberate:
        rows = [f"• {nm(sl.player)} ×{_c(sl.clause / sl.player.market_value, 2)}" for sl in deliberate]
        sections.append("👑 <b>CLÁUSULA ALTA A PROPÓSITO</b>\n" + "\n".join(rows) + "\n<i>Si un rival la paga, ganamos dinero: ni se blinda ni se vende barato.</i>")

    # --- bloqueo al líder
    leader = world.leader_team_id
    if leader and leader != world.my_team_id:
        gks = [sl for sl in world.rival_slots if sl.owner_team_id == leader and sl.player.position_id == 1 and sl.player.available]
        locked = [sl for sl in gks if sl.clause_locked_until and sl.clause_locked_until > now]
        free_from = max((sl.clause_locked_until for sl in locked), default=None)
        name = next((r.manager_name for r in world.standing if r.team_id == leader), "el líder")
        if not xi_ok:
            state = "⏸ en pausa: antes hay que completar nuestro once"
        elif free_from and world.clause_freeze and free_from > world.clause_freeze[0]:
            state = f"⏳ no antes de la jornada siguiente\n   (su portero queda libre el {_when(free_from)})"
        else:
            state = f"✅ posible en la próxima congelación ({len(gks)} portero(s) suyo(s))"
        sections.append(f"🎯 <b>BLOQUEO A {esc(short_name(name).upper())}</b>\n{state}")

    # --- resultados de las operaciones
    res = results_section(review)
    if res:
        sections.append(res)

    # --- plantilla
    sections.append(f"👥 <b>PLANTILLA</b> ({len(world.my_slots)})\n" + _fold(plantilla_lines(world, now, full)))

    # --- novedades pendientes del resumen
    pend = inbox.pending(store)
    if pend:
        sections.append(f"📬 <b>PENDIENTES DEL RESUMEN</b> ({len(pend)})\n" + _fold([inbox._label(x["text"], 90) for x in pend[-8:]]))

    # --- parón
    out = world.outlook
    if out and out.in_break and out.next_first:
        sections.append(f"📅 <b>PARÓN</b> hasta el {out.next_first.astimezone():%d/%m}\ninversión a crédito permitida (hasta el 20%)")
    elif out and out.next_break and (out.next_break[0] - now) <= timedelta(days=3):
        a, b = out.next_break
        sections.append(f"📅 <b>PARÓN EN {max(0, (a - now).days)} DÍA(S)</b>\ndel {a.astimezone():%d/%m} al {b.astimezone():%d/%m}")
    sections.append("<i>Lo plegado se abre con un toque. Los botones los atiendo en cuanto estoy escuchando (a veces hasta 15 min).</i>")
    text = "\n\n".join(sections)
    for drop in (("📊",), ("📬",), ("👥",)):      # Telegram admite 4096 caracteres de texto (sin contar las etiquetas): si no cabe, se quita primero lo menos importante
        if _visible_len(text) <= MAX_CHARS:
            break
        sections = [s for s in sections if not s.startswith(drop)]
        text = "\n\n".join(sections)
    return text


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
            if msg_id:
                notify.delete_message(settings, int(msg_id))        # que no queden dos paneles
    store.set("panel_hash", body_hash)
    store.set("panel_at", str(time.time()))
    return True
