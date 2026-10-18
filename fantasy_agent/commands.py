"""Consultas por Telegram: escribes `/brecha`, `/misiones`, `/porque Terrats`... (o pulsas un botón) y el bot lo contesta en la siguiente pasada
(≤15 min: no hay servidor, solo la pasada de GitHub). Solo hace caso al chat configurado."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from . import autopilot as ap, charts, confirm, inbox, notify, panel, wealth
from .storage import Store

HELP = (
    "🤖 <b>Qué puedes pedirme</b>\n"
    "/misiones — estado de lo importante (también está fijado arriba)\n"
    "/resumen — las novedades pendientes, ya\n"
    "/brecha — diferencia con el líder (dinero y puntos) con gráficas; /brecha aleix o /brecha pep para otro rival\n"
    "/jornada — puntos de la jornada en juego\n"
    "/plantilla — tu plantilla, con su valor, cláusula y protección\n"
    "/porque Terrats — por qué se hizo (o no) algo con un jugador\n\n"
    "Respondo en la siguiente pasada (como mucho 15 min)."
)


def _days(day: str, offset: int) -> str:
    from datetime import date, timedelta
    return str(date.fromisoformat(day) - timedelta(days=offset))


def _managers(world) -> dict[str, str]:
    return {str(r.manager_id): r.manager_name for r in world.standing}


def _my_manager_id(world) -> str:
    return next((str(r.manager_id) for r in world.standing if r.team_id == world.my_team_id), "")


def _pick_rival(world, arg: str) -> str:
    names = _managers(world)
    me = _my_manager_id(world)
    arg = (arg or "").strip().lower()
    if arg:
        for mid, name in names.items():
            if mid != me and arg in name.lower():
                return mid
    top = max(world.standing, key=lambda r: r.points)
    if str(top.manager_id) != me:
        return str(top.manager_id)
    return next(mid for mid in names if mid != me)


def gap_lines(ser: dict[str, dict[str, float]], me: str, rival: str, offsets=(5, 10, 20, 30)) -> list[str]:
    days = sorted(ser)
    today = days[-1]
    gap_now = ser[today].get(rival, 0) - ser[today].get(me, 0)
    lines = []
    for off in offsets:
        d = _days(today, off)
        if d in ser:
            g = ser[d].get(rival, 0) - ser[d].get(me, 0)
            lines.append(f"hace {off:>2} días: {g:6.0f}M → {gap_now:6.0f}M ({gap_now - g:+.0f}M)")
    return lines


def brecha(settings, store: Store, api, world, arg: str = "") -> None:
    names = _managers(world)
    me, rival = _my_manager_id(world), _pick_rival(world, arg)
    my_name, rival_name = names.get(me, "Tú"), names.get(rival, "Rival")
    my_row = next(r for r in world.standing if str(r.manager_id) == me)
    ri_row = next(r for r in world.standing if str(r.manager_id) == rival)
    ser = wealth.series(store)
    today = sorted(ser)[-1] if ser else None
    lines = [f"📈 <b>Brecha con {notify.esc(rival_name)}</b>",
             f"Puntos: {my_row.points} contra {ri_row.points} → <b>{my_row.points - ri_row.points:+d}</b>"]
    if today:
        a, b = ser[today].get(me, 0), ser[today].get(rival, 0)
        lines.append(f"Patrimonio: {a:.0f}M contra {b:.0f}M → <b>{a - b:+.0f}M</b> (tienes el {a / b * 100:.0f}% del suyo)")
        lines.append("<b>La diferencia de patrimonio, antes y ahora</b>")
        lines += [f"<code>{l}</code>" for l in gap_lines(ser, me, rival)]
    buttons = [(f"vs {n.split()[0][:10]}", f"cmd:brecha:{n.split()[0].lower()[:8]}") for mid, n in names.items() if mid not in (me, rival)]
    buttons.insert(0, (f"vs {rival_name.split()[0][:10]}", f"cmd:brecha:{rival_name.split()[0].lower()[:8]}"))
    notify.send_all(settings, "\n".join(lines), html=True, buttons=buttons[:3])
    if today:
        days = sorted(ser)
        me_s = [ser[d].get(me) for d in days]
        ri_s = [ser[d].get(rival) for d in days]
        url = charts.render_url(charts.wealth_config(days, me_s, ri_s, rival_name, my_name))
        notify.send_photo(settings, url, "Patrimonio de cada uno (la parte anterior al 18/10 es una reconstrucción, ±10M).")
        gap = [round((ser[d].get(rival, 0) - ser[d].get(me, 0)), 1) for d in days]
        notify.send_photo(settings, charts.render_url(charts.gap_config(days, gap, rival_name)), "Diferencia de patrimonio.")
    cur = int((api.current_week() or {}).get("weekNumber") or 0)
    cached = json.loads(store.get("pts_weeks") or "{}")
    if cached.get("w") != cur or time.time() - cached.get("at", 0) > 2 * 3600:
        cached = {"at": time.time(), "w": cur, "d": wealth.points_by_week(api, world.league_id, cur)}
        store.set("pts_weeks", json.dumps(cached))
    pts = cached["d"]
    if me in pts and rival in pts and cur:
        weeks = list(range(1, cur + 1))
        def cum(lst):
            out, t = [], 0
            for x in lst[:cur]:
                t += x
                out.append(t)
            return out
        url = charts.render_url(charts.points_config(weeks, cum(pts[me]), cum(pts[rival]), rival_name, my_name))
        last = [f"J{w}: {pts[me][w - 1] - pts[rival][w - 1]:+d}" for w in weeks[-4:]]
        notify.send_photo(settings, url, "Puntos acumulados. Diferencia por jornada: " + " · ".join(last))


def misiones(settings, store: Store, api, world) -> None:
    from . import cli
    text = panel.render(world, store, hours_to_deadline=cli._hours_to_deadline(world), week=api.current_week())
    notify.send_all(settings, text, html=True)
    panel.sync(store, settings, text, force=True)


def resumen(settings, store: Store) -> None:
    text = inbox.flush_text(store)
    notify.send_all(settings, text or "📭 Nada nuevo desde el último resumen.", html=True)


def jornada(settings, store: Store, api, world) -> None:
    wk = api.current_week() or {}
    cur = int(wk.get("weekNumber") or 0)
    raw = {str(p["id"]): p for p in api.players()}
    ptid = {sl.player_team_id: sl.player for sl in world.my_slots}
    try:
        ids = ap.lineup_ids(api.lineup(world.my_team_id))
    except Exception:
        ids = set()
    rows = []
    for tid in ids:
        p = ptid.get(tid)
        if not p:
            continue
        pts = next((x.get("points") for x in (raw.get(p.id, {}).get("weekPoints") or []) if x.get("weekNumber") == cur), None)
        rows.append((p.name, pts))
    rows.sort(key=lambda r: -(r[1] if r[1] is not None else -99))
    total = sum(r[1] for r in rows if r[1] is not None)
    lines = [f"⚽ <b>Jornada {cur}</b>{' · en juego' if wk.get('isLive') else ''} · tu once lleva <b>{total}</b> pts"]
    lines.append(", ".join(f"{notify.esc(n)} {pts if pts is not None else '–'}" for n, pts in rows) or "No encuentro la alineación guardada.")
    try:
        week_rows = api.standing_week(world.league_id, cur)
        lines.append("Jornada: " + " · ".join(f"{notify.esc(r['team']['manager']['managerName'].split()[0][:10])} {r['points']}"
                                                for r in sorted(week_rows, key=lambda r: -r['points'])))
    except Exception:
        pass
    notify.send_all(settings, "\n".join(lines), html=True)


def plantilla(settings, world) -> None:
    now = datetime.now(timezone.utc)
    lines = ["👥 <b>Plantilla</b>"]
    for sl in sorted(world.my_slots, key=lambda x: (x.player.position_id, -x.player.market_value)):
        p = sl.player
        if sl.shielded_until and sl.shielded_until > now:
            prot = f"blindado hasta {sl.shielded_until.astimezone():%a %H:%M}"
        elif sl.clause_locked_until and sl.clause_locked_until > now:
            prot = f"protegido hasta {sl.clause_locked_until.astimezone():%a %d %H:%M}"
        else:
            prot = "cláusula abierta"
        ratio = sl.clause / p.market_value if p.market_value else 0
        lines.append(f"{('POR', 'DEF', 'CEN', 'DEL')[p.position_id - 1]} {notify.esc(p.name)} · {p.market_value / 1e6:.1f}M · cláusula ×{ratio:.2f} · {prot} · {p.avg_points:.1f} pts")
    notify.send_all(settings, "\n".join(lines), html=True)


def porque(settings, store: Store, arg: str) -> None:
    arg = arg.strip().lower()
    if not arg:
        notify.send_all(settings, "Dime de quién: por ejemplo <code>/porque Terrats</code>", html=True)
        return
    rows = [d for d in store.decisions() if arg in str(d.get("who", "")).lower()][-6:]
    if not rows:
        notify.send_all(settings, f"No tengo decisiones guardadas sobre «{notify.esc(arg)}» (la bitácora empezó el 18/10).", html=True)
        return
    lines = [f"🔎 <b>Por qué: {notify.esc(arg)}</b>"]
    for d in rows:
        when = datetime.fromtimestamp(d["at"]).strftime("%a %d %H:%M")
        extra = f" (×{d['ratio']})" if d.get("ratio") else ""
        lines.append(f"{when} · {notify.esc(str(d['kind']))}: <b>{notify.esc(str(d['do']))}</b>{extra} — {notify.esc(str(d['why']))}")
    notify.send_all(settings, "\n".join(lines), html=True)


def run(settings, store: Store, api, world, text: str) -> bool:
    """Ejecuta un comando de texto (`/brecha aleix`) o de botón (`cmd:brecha:aleix`). True si era uno nuestro."""
    t = text.strip()
    if t.startswith("cmd:"):
        t = "/" + t[4:].replace(":", " ")
    if not t.startswith("/"):
        return False
    cmd, _, arg = t[1:].partition(" ")
    cmd = cmd.split("@")[0].lower()
    if cmd in ("start", "ayuda", "help"):
        notify.send_all(settings, HELP, html=True)
    elif cmd == "misiones":
        misiones(settings, store, api, world)
    elif cmd == "resumen":
        resumen(settings, store)
    elif cmd == "brecha":
        brecha(settings, store, api, world, arg)
    elif cmd == "jornada":
        jornada(settings, store, api, world)
    elif cmd == "plantilla":
        plantilla(settings, world)
    elif cmd == "porque":
        porque(settings, store, arg)
    else:
        notify.send_all(settings, f"No conozco «/{notify.esc(cmd)}». Prueba con /ayuda.", html=True)
    return True


def poll(settings, store: Store, api, world) -> list[str]:
    """Lee lo que hayas escrito o pulsado: comandos nuevos y, como antes, los botones de Confirmar/Cancelar antiguos."""
    results: list[str] = []
    if not notify.telegram_enabled(settings):
        return results
    store.expire_pending()
    last_id = store.get("telegram_last_update_id")
    updates = notify.get_telegram_updates(settings, offset=int(last_id) + 1 if last_id else None)
    pending = {p["id"]: p for p in store.get_pending()}
    mine = str(settings.telegram_chat_id)
    for upd in updates:
        store.set("telegram_last_update_id", str(upd["update_id"]))     # primero: un update raro no se reprocesa en bucle
        try:
            cq = upd.get("callback_query")
            msg = (cq or {}).get("message") or upd.get("message") or {}
            if str((msg.get("chat") or {}).get("id")) != mine:
                continue                                              # solo hago caso a tu chat
            text = (cq or {}).get("data") if cq else (upd.get("message") or {}).get("text", "")
            if cq:
                notify.answer_callback(settings, cq["id"])
            if text and run(settings, store, api, world, text):
                continue
            confirm._process_update(settings, store, api, pending, results, upd)
        except Exception as exc:
            from .storage import redact
            store.log_error("comando", redact(str(exc)))
            notify.send_all(settings, f"⚠️ No he podido atender ese mensaje: {notify.esc(redact(str(exc)))[:300]}", html=True)
    return results
