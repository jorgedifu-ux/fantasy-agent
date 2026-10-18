"""Consultas por Telegram: escribes `/brecha`, `/misiones`, `/porque Terrats`... (o pulsas un botón) y el bot lo contesta en la siguiente pasada
(≤15 min: no hay servidor, solo la pasada de GitHub). Solo hace caso al chat configurado."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from . import autopilot as ap, charts, confirm, fullnames, inbox, matches, notify, panel, reval, tidy, wealth
from .storage import Store

HELP = (
    "🤖 <b>Qué puedes pedirme</b>\n\n"
    "<blockquote>/misiones · pone al día el panel fijado y borra lo demás (botón 🔄)\n"
    "/ayer · lo que subió o bajó cada plantilla en la última actualización de valores\n"
    "/partidos · los partidos de la jornada: qué se ha jugado, qué falta y qué jugadores tiene cada uno\n"
    "/resumen · las novedades pendientes, ya\n"
    "/brecha · diferencia con el líder; /brecha aleix o /brecha pep para otro rival\n"
    "/revision · balance de las operaciones\n"
    "/porque Terrats · por qué se hizo (o no) algo con un jugador\n"
    "/plan · el plan de equipo de la semana\n"
    "/grafica · las gráficas en imagen</blockquote>\n\n"
    "<i>La jornada y la plantilla están en el panel fijado, plegadas. Contesto en cuanto estoy escuchando (casi al instante si acabas de hablar "
    "conmigo); si no, en la siguiente pasada (máx. 15 min).</i>"
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
            lines.append(f"Hace {off} días: {g:.0f}M → hoy {gap_now:.0f}M ({gap_now - g:+.0f}M)")
    return lines


BAR = 10


def _bars(values: list[float], icons: list[str]) -> list[str]:
    """Barras de emojis a la misma escala (lo más largo, BAR casillas): se ven igual de alineadas en cualquier móvil."""
    top = max(values) or 1
    out = []
    for v, icon in zip(values, icons):
        n = max(0, min(BAR, round(v / top * BAR)))
        out.append(icon * n + "⬜" * (BAR - n))
    return out


def _week_points(settings, store: Store, api, world) -> tuple[int, dict]:
    cur = int((api.current_week() or {}).get("weekNumber") or 0)
    cached = json.loads(store.get("pts_weeks") or "{}")
    if cached.get("w") != cur or time.time() - cached.get("at", 0) > 2 * 3600:
        cached = {"at": time.time(), "w": cur, "d": wealth.points_by_week(api, world.league_id, cur)}
        store.set("pts_weeks", json.dumps(cached))
    return cur, cached["d"]


def brecha(settings, store: Store, api, world, arg: str = "") -> None:
    """Brecha con un rival en texto visual (barras de emojis y una línea de evolución): se lee de un vistazo y no ocupa como una imagen."""
    names = _managers(world)
    me, rival = _my_manager_id(world), _pick_rival(world, arg)
    rival_name = panel.short_name(names.get(rival, "Rival"))
    my_row = next(r for r in world.standing if str(r.manager_id) == me)
    ri_row = next(r for r in world.standing if str(r.manager_id) == rival)
    ser = wealth.series(store)
    days = sorted(ser)
    pb = _bars([my_row.points, ri_row.points], ["🟦", "🟧"])
    rn = notify.esc(rival_name)
    lines = [f"📈 <b>Brecha con {rn}</b>", "",
             "⚽ <b>Puntos</b>",
             f"<blockquote>{pb[0]} Tú · {my_row.points}\n{pb[1]} {rn} · {ri_row.points}\nDiferencia: <b>{my_row.points - ri_row.points:+d}</b></blockquote>"]
    if days:
        a, b = ser[days[-1]].get(me, 0), ser[days[-1]].get(rival, 0)
        wb = _bars([a, b], ["🟦", "🟧"])
        lines += ["", "💰 <b>Patrimonio</b>",
                  f"<blockquote>{wb[0]} Tú · {a:.0f}M\n{wb[1]} {rn} · {b:.0f}M\nDiferencia: <b>{a - b:+.0f}M</b> · tienes el {a / b * 100:.0f}% del suyo</blockquote>"]
        hist = gap_lines(ser, me, rival)
        if hist:
            lines += ["", "🕓 <b>La diferencia de patrimonio, antes y ahora</b>", "<blockquote expandable>" + "\n".join(hist) + "</blockquote>"]
    try:
        cur, pts = _week_points(settings, store, api, world)
        if me in pts and rival in pts and cur:
            rows = []
            for w in range(1, cur + 1):
                m = pts[me][w - 1] if w <= len(pts[me]) else 0
                r = pts[rival][w - 1] if w <= len(pts[rival]) else 0
                if m or r:
                    rows.append(f"J{w}{' (en juego)' if w == cur else ''}: tú {m} · {rn} {r} → <b>{m - r:+d}</b>")
            if rows:
                lines += ["", "🗓 <b>Puntos por jornada</b>", "<blockquote expandable>" + "\n".join(rows) + "</blockquote>"]
    except Exception:
        pass
    buttons = [(f"vs {panel.short_name(n)}", f"cmd:brecha:{panel.short_name(n).lower()}") for mid, n in names.items() if mid != me]
    buttons.append(("📊 Gráficas", "cmd:grafica"))
    notify.send_all(settings, "\n".join(lines), html=True, buttons=buttons[:4])


def grafica(settings, store: Store, api, world, arg: str = "") -> None:
    """Las dos imágenes (patrimonio y puntos por jornada), solo si las pides: ocupan mucho."""
    names = _managers(world)
    me, rival = _my_manager_id(world), _pick_rival(world, arg)
    rival_name = panel.short_name(names.get(rival, "Rival"))
    ser = wealth.series(store)
    if ser:
        days = sorted(ser)
        url = charts.render_url(charts.wealth_config(days, [ser[d].get(me) for d in days], [ser[d].get(rival) for d in days], rival_name, "Tú"))
        notify.send_photo(settings, url, "Patrimonio. Hasta el 18/10 es una reconstrucción (±10M); desde entonces, foto diaria.")
    cur, pts = _week_points(settings, store, api, world)
    if me in pts and rival in pts and cur:
        weeks = [w for w in range(1, cur + 1) if (pts[me][w - 1] if w <= len(pts[me]) else 0) or (pts[rival][w - 1] if w <= len(pts[rival]) else 0)]
        url = charts.render_url(charts.points_config(weeks, [pts[me][w - 1] for w in weeks], [pts[rival][w - 1] for w in weeks], rival_name, "Tú", live_week=cur))
        notify.send_photo(settings, url, "Puntos de cada jornada (la última, en juego).")


def _full_names(store: Store, api, world, jornada: dict | None) -> dict[str, str]:
    ids = [sl.player.id for sl in world.my_slots] + [r["pid"] for r in (jornada or {}).get("rows", []) if r.get("pid")]
    return fullnames.ensure(store, api, list(dict.fromkeys(ids)))


def review_lines(settings, store: Store, api, world) -> list[str]:
    """Líneas de la revisión (operaciones cerradas, lo que sigue sin vender...), guardadas 6 h: cuesta ~30 llamadas a la API."""
    from . import cli
    cached = json.loads(store.get("review_cache") or "{}")
    if cached.get("lines") and time.time() - cached.get("at", 0) < 6 * 3600:
        return cached["lines"]
    try:
        lines = cli._review_text(api, store, world).splitlines()
    except Exception:
        return cached.get("lines", [])
    store.set("review_cache", json.dumps({"at": time.time(), "lines": lines}, ensure_ascii=False))
    return lines


def refresh_panel(settings, store: Store, api, world, force: bool = False) -> bool:
    from . import cli
    jd = panel.jornada_data(world, api, store)
    text = panel.render(world, store, hours_to_deadline=cli._hours_to_deadline(world), week=api.current_week(), jornada=jd,
                        full=_full_names(store, api, world, jd), review=review_lines(settings, store, api, world))
    return panel.sync(store, settings, text, force=force)


def in_panel(settings, store: Store, api, world, section: str) -> None:
    """Jornada y plantilla ya están en el panel fijado, plegadas: se pone al día y se avisa en una línea (no se manda otro tocho)."""
    refresh_panel(settings, store, api, world, force=True)
    notify.send_all(settings, f"📌 Está en el panel fijado, plegado en <b>{section}</b>. Acabo de actualizarlo.", html=True)


def revision(settings, store: Store, api, world) -> None:
    lines = review_lines(settings, store, api, world)
    if not lines:
        notify.send_all(settings, "No he podido preparar la revisión ahora mismo.")
        return
    summary = [l for l in lines[1:4]]
    notify.send_all(settings, "📊 <b>Revisión</b>\n" + "\n".join(summary) + "\n" + panel._fold([l.strip() for l in lines[4:]]), html=True)


def misiones(settings, store: Store, api, world) -> None:
    """«Actualizar y limpiar»: borra los mensajes anteriores del bot y pone al día el panel fijado en el sitio (lo recrea si lo borraste)."""
    tidy.purge(store, settings)
    refresh_panel(settings, store, api, world, force=True)


def resumen(settings, store: Store) -> None:
    """Las novedades pendientes y, si no hay ninguna, lo de las últimas 24 h (siempre se puede repasar)."""
    text = inbox.flush_text(store)
    if not text:
        items = inbox.recent(store, 24)
        text = inbox.render_digest(items, since=items[0]["t"], now=datetime.now(), recap=True) if items else \
            "📭 No ha pasado nada en las últimas 24 h."
    notify.send_all(settings, text, html=True)


def ayer(settings, store: Store, api, world) -> None:
    """Lo que subió o bajó cada plantilla en la última actualización de valores, con los mayores movimientos de todos."""
    data = reval.load(store) or reval.compute(world, api)
    if not data:
        notify.send_all(settings, "No he podido calcular la revalorización ahora mismo.")
        return
    text = panel.reval_section(data, detail=True)
    notify.send_all(settings, text or "Sin datos de revalorización.", html=True)


def partidos(settings, store: Store, api, world) -> None:
    d = matches.collect(world, api)
    if not d:
        notify.send_all(settings, "No he podido leer los partidos de la jornada ahora mismo.")
        return
    notify.send_all(settings, matches.render(d), html=True)


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
        when = f"{panel.DAYS[datetime.fromtimestamp(d['at']).weekday()]} {datetime.fromtimestamp(d['at']):%d %H:%M}"
        extra = f" (×{d['ratio']})" if d.get("ratio") else ""
        lines += ["", f"<b>{when} · {notify.esc(str(d['kind']))} · {notify.esc(str(d['do']))}</b>{extra}", f"<blockquote>{notify.esc(str(d['why']))}</blockquote>"]
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
        if cmd == "start":
            refresh_panel(settings, store, api, world, force=True)       # tras vaciar el chat, vuelve a crear y fijar el panel
    elif cmd in ("misiones", "limpiar"):
        misiones(settings, store, api, world)
    elif cmd == "resumen":
        resumen(settings, store)
    elif cmd == "brecha":
        brecha(settings, store, api, world, arg)
    elif cmd in ("ayer", "revalorizacion"):
        ayer(settings, store, api, world)
    elif cmd in ("partidos", "enfrentamientos"):
        partidos(settings, store, api, world)
    elif cmd == "grafica":
        grafica(settings, store, api, world, arg)
    elif cmd == "jornada":
        in_panel(settings, store, api, world, "Jornada")
    elif cmd == "plantilla":
        in_panel(settings, store, api, world, "Plantilla")
    elif cmd == "revision":
        revision(settings, store, api, world)
    elif cmd == "plan":
        from . import plan as plan_mod
        notify.send_all(settings, plan_mod.render_plan_text(plan_mod.load_plan(store)), html=True)
    elif cmd == "porque":
        porque(settings, store, arg)
    else:
        notify.send_all(settings, f"No conozco «/{notify.esc(cmd)}». Prueba con /ayuda.", html=True)
    return True


def _handle(settings, store: Store, api, world, updates: list[dict]) -> list[str]:
    results: list[str] = []
    pending = {p["id"]: p for p in store.get_pending()}
    mine = str(settings.telegram_chat_id)
    for upd in updates:
        store.set("telegram_last_update_id", str(upd["update_id"]))     # primero: un update raro no se reprocesa en bucle
        try:
            cq = upd.get("callback_query")
            msg = (cq or {}).get("message") or upd.get("message") or {}
            if str((msg.get("chat") or {}).get("id")) != mine:
                continue                                              # solo hago caso a tu chat
            store.set("last_user_at", str(time.time()))
            text = (cq or {}).get("data") if cq else (upd.get("message") or {}).get("text", "")
            if cq:
                notify.answer_callback(settings, cq["id"], "Actualizado y limpio ✅" if text == "cmd:misiones" else "Voy…")
            if text and run(settings, store, api, world, text):
                mid = (upd.get("message") or {}).get("message_id")
                if not cq and mid:
                    if text.strip().lower().startswith(("/misiones", "/limpiar")):
                        notify.delete_message(settings, mid)                # «actualizar y limpiar» no deja ni tu orden
                    else:
                        tidy.track(store, [mid], ttl_s=tidy.USER_TTL_S)    # tu orden, ya contestada, se borra en 1 h
                continue
            confirm._process_update(settings, store, api, pending, results, upd)
        except Exception as exc:
            from .storage import redact
            store.log_error("comando", redact(str(exc)))
            notify.send_all(settings, f"⚠️ No he podido atender ese mensaje: {notify.esc(redact(str(exc)))[:300]}", html=True)
    return results


def poll(settings, store: Store, api, world) -> list[str]:
    """Lee lo que hayas escrito o pulsado: comandos nuevos y, como antes, los botones de Confirmar/Cancelar antiguos."""
    if not notify.telegram_enabled(settings):
        return []
    store.expire_pending()
    last_id = store.get("telegram_last_update_id")
    return _handle(settings, store, api, world, notify.get_telegram_updates(settings, offset=int(last_id) + 1 if last_id else None))


def listen(settings, store: Store, api, world, until: float, wait: int = 25) -> int:
    """Se queda escuchando hasta `until` (timestamp): Telegram avisa en cuanto escribes y se contesta al momento, sin esperar a la pasada
    siguiente. Devuelve cuántos mensajes atendió."""
    if not notify.telegram_enabled(settings):
        return 0
    n = 0
    while time.time() + wait + 5 < until:
        last_id = store.get("telegram_last_update_id")
        updates = notify.get_telegram_updates(settings, offset=int(last_id) + 1 if last_id else None, wait=wait)
        if updates:
            _handle(settings, store, api, world, updates)
            n += len(updates)
    return n
