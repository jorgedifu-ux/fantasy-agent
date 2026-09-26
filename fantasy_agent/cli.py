"""Línea de comandos: `python -m fantasy_agent <comando>`."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone

from . import analysis, auth, autopilot as ap, confirm, digest, lineup, models, notify, plan as plan_mod, service
from .api import FantasyAPI
from .attendance import estimate_start_probability, estimate_titularidad
from .config import load_settings
from .storage import Store


def _out(settings, text: str, telegram: bool) -> None:
    print(text)
    if telegram:
        notify.send_telegram(settings, text)


def cmd_auth(args, s) -> None:
    if args.step == "url":
        print("1) Abre Chrome → DevTools (F12) → pestaña Network → marca 'Preserve log'.")
        print("2) Pega esta URL e inicia sesión con tu cuenta de LaLiga Fantasy:\n")
        print(auth.build_login_url(s))
        print("\n3) La página se quedará en blanco (es normal). En Network, la última fila '(canceled)'")
        print("   empieza por ?state=...&code=... → clic derecho → Copy link address.")
        print("4) Ejecuta: python -m fantasy_agent auth code 'authredirect://...'")
    elif args.step == "code":
        if not args.url:
            sys.exit("Falta la URL: auth code 'authredirect://...'")
        tokens = auth.exchange_code(s, args.url)
        mins = int((tokens["expires_at"] - time.time()) / 60)
        print(f"✅ Sesión guardada. Caduca en {mins} min · refresh: {'sí' if tokens['refresh_token'] else 'no'}")
    elif args.step == "status":
        t = auth.load_tokens(s)
        if not t:
            print("Sin sesión.")
        else:
            mins = int((t["expires_at"] - time.time()) / 60)
            print(f"Token caduca en {mins} min · refresh token: {'sí' if t.get('refresh_token') else 'no'}")
    elif args.step == "refresh":
        auth.refresh(s)
        print("✅ Token renovado.")


def cmd_probe(args, s) -> None:
    api = FantasyAPI(s)
    data = api.get(args.path, authed=not args.public)
    print(json.dumps(data, indent=2, ensure_ascii=False)[: args.max_chars])


def cmd_leagues(args, s) -> None:
    api = FantasyAPI(s)
    league_id, team_id, _ = service.resolve_league(api, s)
    print(json.dumps(api.leagues(), indent=2, ensure_ascii=False)[:3000])
    print(f"\nLiga seleccionada: {league_id} · equipo detectado: {team_id or '(no viene en la respuesta)'}")


def cmd_standing(args, s) -> None:
    api = FantasyAPI(s)
    league_id, _, _ = service.resolve_league(api, s)
    from .models import parse_standing
    for r in parse_standing(api.standing(league_id)):
        print(f"team_id={r.team_id:<10} manager_id={r.manager_id:<12} {r.manager_name:<20} {r.points:>5} pts  {service.m(r.team_value)}")


def _world(api, s, trends=True):
    return service.build_world(api, s, with_trends=trends)


def cmd_section(args, s) -> None:
    api = FantasyAPI(s)
    world = _world(api, s, trends=args.cmd in ("market", "trends", "report"))
    news = None
    if args.cmd in ("lineup", "report") and getattr(args, "news", False):
        news = estimate_titularidad(api, [sl.player for sl in world.my_slots if sl.player.position_id != 5])
    if args.cmd == "report":
        sections = service.report_sections(world, s, news)
        print("\n\n".join(sections))
        if args.telegram:
            notify.send_report(s, sections, telegram=args.telegram)
        return
    text = {
        "market": lambda: service.market_report(world),
        "trends": lambda: service.trends_report(world),
        "rivals": lambda: service.rivals_report(world),
        "clauses": lambda: service.clauses_report(world, s)[0],
        "lineup": lambda: service.lineup_report(world, news),
    }[args.cmd]()
    _out(s, text, args.telegram)


def _record_status_history(store: Store, world) -> None:
    for sl in (*world.my_slots, *world.rival_slots):
        store.record_status(sl.player.id, sl.player.status)
    for item in world.market:
        store.record_status(item.player.id, item.player.status)


def _hours_to_deadline(world) -> float | None:
    """Horas hasta el primer partido de la jornada (mismo instante en que se congelan las
    cláusulas y se guarda la alineación) — None si no lo sabemos."""
    if not world.clause_freeze:
        return None
    return (world.clause_freeze[1] - datetime.now(timezone.utc)).total_seconds() / 3600


def _emergency_debt_buy(store: Store, s, api: FantasyAPI, world, team_plan: plan_mod.Plan) -> str | None:
    """Último recurso, solo si `_emergency_buy` ya no encuentra nada que puedas pagar sin
    deuda y la plantilla sigue incompleta: permite endeudarte hasta el tope REAL del juego
    (20% del valor de tu plantilla), emparejado SIEMPRE con poner a la venta ya mismo el
    primer candidato de la lista de venta del plan, para intentar saldarlo antes de que
    arranque la jornada.

    OJO — esto no es una garantía: una venta no es instantánea (alguien tiene que comprarla,
    ver STRATEGY.md §10), puede no resolverse a tiempo. Aun así compensa intentarlo: si la
    venta no llega a tiempo, el resultado (cero puntos esa jornada) es EXACTAMENTE el mismo
    que si te hubieras quedado sin fichar — nunca es peor que no hacer nada, y si la venta sí
    llega a tiempo, sí puntúas. Se avisa siempre de que esto ha pasado, nunca en silencio."""
    shortage = analysis.position_shortage(world.my_slots)
    if not any(shortage.values()) or not world.my_cash:
        return None
    squad_value = sum(sl.player.market_value for sl in world.my_slots)
    debt_room = int(squad_value * s.debt_ceiling_pct)
    with_debt = analysis.emergency_candidates(world.my_slots, world.market, world.my_cash + debt_room, 1.0)
    only_with_debt = [o for o in with_debt if o.item.price > world.my_cash]
    if not only_with_debt:
        return None
    pick = only_with_debt[0]
    name = notify.esc(pick.item.player.name)
    try:
        api.bid(world.league_id, pick.item.market_id, pick.item.price)
    except Exception as exc:
        return f"❌ Fichaje a crédito fallido para <b>{name}</b>: {notify.esc(str(exc))}"
    store.record_auto_op("emergency_debt_buy", pick.item.player.id, pick.item.price)
    expires_at = pick.item.expires.timestamp() if pick.item.expires else None
    store.add_market_bid(pick.item.player.id, name, pick.item.price, expires_at)
    debe = pick.item.price - world.my_cash
    msg = (
        f"🆘 <b>FICHAJE A CRÉDITO</b> (sin confirmar — última opción para no quedarte sin 11)\n"
        f"<b>{name}</b> ({pick.item.player.position}) por {service.m(pick.item.price)} "
        f"— esto te deja {service.m(debe)} en NEGATIVO.\n"
    )
    mine_ids = {sl.player.id for sl in world.my_slots}
    sell_pick = next((i for i in plan_mod.sell_priority_ids(team_plan) if i.player_id in mine_ids), None)
    if sell_pick:
        slot = next((sl for sl in world.my_slots if sl.player.id == sell_pick.player_id), None)
        try:
            api.sell_player(world.league_id, slot.player_team_id, slot.player.market_value)
            store.add_market_bid(sell_pick.player_id, sell_pick.player_name, slot.player.market_value, None, direction="sell")
            msg += (
                f"💸 Para saldarlo, puesto a la venta ya (según el plan): "
                f"<b>{notify.esc(sell_pick.player_name)}</b> por {service.m(slot.player.market_value)}.\n"
            )
        except Exception as exc:
            msg += f"⚠️ No he podido poner nada a la venta para saldarlo: {notify.esc(str(exc))} — hazlo tú.\n"
    else:
        msg += "⚠️ No hay ningún candidato de venta en el plan — revísalo tú para saldar antes de la jornada.\n"
    msg += "No es una garantía: si la venta no se resuelve a tiempo, no puntuarás esta jornada igualmente."
    return msg


def _check_bid_resolutions(store: Store, world) -> list[str]:
    """Una puja "enviada" no es una puja "ganada". Compara lo pendiente con tu plantilla
    actual: si el jugador ya está en tu equipo, la ganaste; si ya pasó de sobra su hora de
    cierre y sigue sin estar, la perdiste (otro mánager pujó más)."""
    my_ids = {sl.player.id for sl in world.my_slots}
    now = time.time()
    results: list[str] = []
    for b in store.unresolved_market_bids("buy"):
        if b["player_id"] in my_ids:
            store.resolve_market_bid(b["id"], "won")
            results.append(f"✅ <b>Puja ganada</b>: {notify.esc(b['player_name'])} ya es tuyo.")
        elif b["expires_at"] and now > b["expires_at"] + 600:  # 10 min de margen tras el cierre
            store.resolve_market_bid(b["id"], "lost")
            results.append(
                f"❌ <b>Puja perdida</b>: {notify.esc(b['player_name'])} — otro mánager habrá "
                f"pujado más. No se ha gastado nada."
            )
    for b in store.unresolved_market_bids("sell"):
        if b["player_id"] not in my_ids:
            store.resolve_market_bid(b["id"], "gone")  # el aviso lo da _resolve_offers / _squad_changes
    return results


def _sync_plan(store: Store, s, world) -> plan_mod.Plan:
    """Regenera el plan si toca (una vez por semana, no cada tick — ver plan.py) y mantiene
    un ÚNICO mensaje fijado en Telegram con el plan actual, editándolo en el sitio en vez de
    mandar uno nuevo cada vez. Siempre devuelve el plan vigente (aunque no toque regenerar),
    para que el resto del tick pueda consultar targets/sell_priority/watchlist."""
    if plan_mod.due_for_refresh(store):
        plan = plan_mod.generate_plan(world, s, store)
        plan_mod.save_plan(store, plan)
        text = plan_mod.render_plan_text(plan)
        msg_id = store.get(plan_mod.PLAN_MESSAGE_ID_KEY)
        edited = notify.edit_message(s, int(msg_id), text) if msg_id else False
        if not edited:
            new_id = notify.send_all(s, text, html=True)
            if new_id:
                store.set(plan_mod.PLAN_MESSAGE_ID_KEY, str(new_id))
                notify.pin_message(s, new_id)
        return plan
    return plan_mod.load_plan(store)


def _auto_shield(store: Store, s, api: FantasyAPI, world) -> tuple[str | None, str]:
    """Blindaje automático: protege GRATIS a tu jugador más vulnerable a que un rival te lo
    clausule (misma regla de "riesgo propio" ≤1.25x el valor). Límites reales del juego
    (investigados, no en vivo): dura 24h (48h si premium), solo 1 vez por jornada, y solo
    sobre una cláusula abierta ahora mismo — según las guías, solo tiene sentido activarlo en
    la ventana entre el cierre de la jornada anterior y el inicio de la siguiente (justo
    cuando las cláusulas vuelven a ser pagables). Dos salvaguardas por la incertidumbre real
    de dónde cae exactamente esa ventana:
    1) Nunca se intenta DURANTE la congelación de cláusulas (`world.clause_freeze`) — si están
       congeladas, nadie puede clausularte de todos modos, no hace falta blindar ahí.
    2) Cooldown de 4 días (no 20h): más conservador que "una vez por jornada" real, para no
       arriesgarnos a superar el límite del juego por un cálculo nuestro de más.
    Sin coste ni riesgo de dinero si falla (servidor exige de verdad ver el anuncio, sin
    confirmar en vivo todavía) — no pasa nada, solo se avisa."""
    now = datetime.now(timezone.utc)
    if world.clause_freeze and world.clause_freeze[0] <= now < world.clause_freeze[1]:
        return None, ""  # cláusulas congeladas: nadie puede clausularte ahora, no hace falta
    risky = []
    for sl in world.my_slots:
        p = sl.player
        if not p.market_value or sl.clause <= 0 or not sl.clause_open(now):
            continue
        ratio = sl.clause / p.market_value
        if ratio <= 1.25:
            risky.append((ratio, sl))
    if not risky:
        return None, ""
    risky.sort(key=lambda t: t[0])
    _, target = risky[0]
    if not store.alert_is_new(f"shield:{target.player.id}", ttl_hours=96):
        # En cooldown, no protegido de verdad: no lo excluimos de _auto_increase_clause.
        return None, ""
    name = notify.esc(target.player.name)
    try:
        api.shield_player(world.league_id, target.player_team_id)
    except Exception as exc:
        # Ha fallado, no está protegido de verdad: tampoco lo excluimos del fallback de pago.
        msg = (
            f"🛡️ Intento de blindaje fallido para <b>{name}</b>: {notify.esc(str(exc))}\n"
            f"Sin coste — puede que haga falta activarlo a mano desde la app la primera vez."
        )
        return msg, ""
    # La API puede responder bien sin blindar de verdad (visto en vivo el 26/09: en la app
    # pasa por ver un anuncio). Solo se da por hecho si la plantilla lo refleja.
    squad = models.parse_squad(api.team(world.league_id, world.my_team_id), world.my_team_id, "")
    if not any(sl.player_team_id == target.player_team_id and sl.shielded_until for sl in squad):
        return (
            f"🛡️ No he podido blindar a <b>{name}</b>: la API no lo aplica sin ver el anuncio de la "
            f"app. Si quieres protegerlo, blíndalo tú desde la app (es gratis)."
        ), ""
    return f"🛡️ <b>BLINDADO</b>: {name} protegido de clausulazos (gratis, automático).", target.player.id


def _auto_increase_clause(store: Store, s, api: FantasyAPI, world, skip_player_id: str = "") -> str | None:
    """Alternativa DE PAGO al blindaje (solo cuando este está en cooldown/no disponible):
    sube tu propia cláusula a 1.5x el valor de mercado — por encima del umbral "lógico"
    (1.2x) que usamos nosotros mismos para juzgar cláusulas de rivales, así que deja de ser
    un objetivo razonable. Criterio conservador a propósito, porque cuesta dinero de verdad:
    - Solo piezas realmente valiosas (media ≥5 pts/partido) — no merece la pena pagar por
      proteger a alguien mediocre.
    - Solo si la cláusula está MUY barata (≤1.15x), no cualquier "riesgo propio" normal.
    - Coste investigado (no confirmado en la API): aproximadamente la mitad del incremento,
      cargado a tu saldo — solo se intenta si cabe dentro del colchón normal (BUDGET_RESERVE_PCT)."""
    now = datetime.now(timezone.utc)
    if world.clause_freeze and world.clause_freeze[0] <= now < world.clause_freeze[1]:
        return None
    candidates = []
    for sl in world.my_slots:
        p = sl.player
        if p.id == skip_player_id or not p.market_value or sl.clause <= 0 or not sl.clause_open(now):
            continue
        ratio = sl.clause / p.market_value
        if ratio <= 1.15 and p.avg_points >= 5.0:
            candidates.append((ratio, sl))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    _, target = candidates[0]
    p = target.player
    if not store.alert_is_new(f"raise_clause:{p.id}", ttl_hours=96):
        return None
    new_clause = round(p.market_value * 1.5)
    est_cost = round((new_clause - target.clause) / 2)  # ratio 1:2 investigado, sin confirmar
    reserve = world.my_cash * s.budget_reserve_pct if world.my_cash else 0
    if not world.my_cash or est_cost > (world.my_cash - reserve):
        return None  # no tocamos el colchón por esto
    name = notify.esc(p.name)
    try:
        api.increase_buyout_clause(world.league_id, target.player_team_id, new_clause)
    except Exception as exc:
        return f"❌ Intento de subir la cláusula de <b>{name}</b> fallido: {notify.esc(str(exc))}"
    return (
        f"⬆️ <b>CLÁUSULA SUBIDA</b> (sin confirmar — blindaje no disponible)\n"
        f"<b>{name}</b>: cláusula a {service.m(new_clause)} (~{service.m(est_cost)} de coste estimado)\n"
        f"Ya no es un objetivo lógico para ningún rival."
    )


SNIPE_WINDOW_S = 25 * 60  # dentro del mismo job de GitHub (timeout 28 min)


def _committed_bids(store: Store, world) -> tuple[int, list]:
    """Dinero ya comprometido en pujas vivas (si las ganas, se cobran) y los jugadores que
    llegarían con ellas — cuentan para el saldo y para la plantilla simulada del planificador."""
    now = time.time()
    market = {it.player.id: it for it in world.market}
    by_player: dict[str, tuple[int, object]] = {
        it.player.id: (it.my_bid, it.player) for it in world.market if it.my_bid
    }
    for b in store.unresolved_market_bids("buy"):
        it = market.get(b["player_id"])
        if it and b["player_id"] not in by_player and (not b["expires_at"] or b["expires_at"] > now):
            by_player[b["player_id"]] = (b["price"], it.player)
    return sum(v for v, _ in by_player.values()), [pl for _, pl in by_player.values()]


def _acquire(store: Store, s, api: FantasyAPI, world) -> tuple[list[str], list[ap.Move]]:
    """Fichajes y clausulazos autónomos (ver autopilot.plan_acquisitions). Devuelve también
    las cláusulas que se liberan pronto y ya tienen su dinero reservado (para `_snipe`)."""
    now = datetime.now(timezone.utc)
    committed, incoming = _committed_bids(store, world)
    budget = int((world.my_cash or 0) * (1 - s.budget_reserve_pct)) - committed
    if budget <= 0:
        return [], []
    mine = [sl.player for sl in world.my_slots] + incoming
    avoid = frozenset(t for t in (world.leader_team_id, world.revenge_against_team_id) if t)
    moves = ap.clause_moves(world.rival_slots, now, freeze=world.clause_freeze, avoid_team_ids=avoid) + \
        ap.bid_moves(world.market, skip_player_ids=frozenset(pl.id for pl in incoming))
    plan = ap.plan_acquisitions(mine, moves, budget, form=world.recent_form, max_squad=s.max_squad)
    events: list[str] = []
    for mv in plan:
        name, pos = notify.esc(mv.player.name), mv.player.position
        if not mv.executable_now:
            if store.alert_is_new(f"reserve:{mv.player.id}:{mv.cost}", ttl_hours=24):
                when = mv.unlock_at.astimezone().strftime("%d/%m %H:%M")
                events.append(
                    f"⏳ Reservo {service.m(mv.cost)} para clausular a <b>{name}</b> ({pos}, de "
                    f"{notify.esc(mv.slot.owner_name)}) cuando se libere el {when} · +{mv.gain} pts/jornada"
                )
            continue
        try:
            if mv.kind == "clause":
                api.pay_buyout_clause(world.league_id, mv.slot.player_team_id, mv.cost)
                store.record_auto_op("clause", mv.player.id, mv.cost)
                events.append(
                    f"⚡ <b>Clausulazo</b>: {name} ({pos}, de {notify.esc(mv.slot.owner_name)}) por "
                    f"{service.m(mv.cost)} · +{mv.gain} pts/jornada al once"
                )
            else:
                api.bid(world.league_id, mv.item.market_id, mv.cost)
                expires = mv.item.expires.timestamp() if mv.item.expires else None
                store.add_market_bid(mv.player.id, mv.player.name, mv.cost, expires)
                cierre = mv.item.expires.astimezone().strftime("%H:%M") if mv.item.expires else "?"
                events.append(
                    f"🛒 <b>Puja</b>: {name} ({pos}) {service.m(mv.cost)} (salida {service.m(mv.item.price)}) "
                    f"· +{mv.gain} pts/jornada · se resuelve a las {cierre}"
                )
        except Exception as exc:
            events.append(f"❌ {'Clausulazo' if mv.kind == 'clause' else 'Puja'} fallido por <b>{name}</b>: {notify.esc(str(exc))}")
    return events, [mv for mv in plan if not mv.executable_now]


def _snipe(store: Store, api: FantasyAPI, world, reserved: list[ap.Move]) -> list[str]:
    """Cláusulas con dinero ya reservado que se liberan dentro de este mismo job: espera al
    segundo exacto y paga, antes de que otro rival se adelante."""
    events: list[str] = []
    now = datetime.now(timezone.utc)
    soon = sorted(
        (mv for mv in reserved if mv.kind == "clause" and 0 < (mv.unlock_at - now).total_seconds() <= SNIPE_WINDOW_S),
        key=lambda mv: mv.unlock_at,
    )
    for mv in soon:
        name = notify.esc(mv.player.name)
        wait = (mv.unlock_at - datetime.now(timezone.utc)).total_seconds() + 2
        if wait > 0:
            time.sleep(wait)
        last_exc = None
        for _ in range(3):
            try:
                api.pay_buyout_clause(world.league_id, mv.slot.player_team_id, mv.cost)
                store.record_auto_op("clause", mv.player.id, mv.cost)
                events.append(
                    f"⚡ <b>Clausulazo al segundo</b>: {name} ({mv.player.position}) por {service.m(mv.cost)} "
                    f"nada más liberarse · +{mv.gain} pts/jornada"
                )
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                time.sleep(5)
        if last_exc:
            events.append(f"❌ No he podido clausular a <b>{name}</b> al liberarse: {notify.esc(str(last_exc))}")
    return events


def _resolve_offers(store: Store, s, api: FantasyAPI, world) -> list[str]:
    """Ofertas recibidas por tus jugadores en venta: aceptar, rechazar o dejar caducar según
    `autopilot.offer_decision` (incluida la regla de vender antes de que acabe su protección)."""
    now = datetime.now(timezone.utc)
    mine = [sl.player for sl in world.my_slots]
    listed = {it.player.id: it for it in world.market if it.seller_team_id == world.my_team_id}
    cut = {sl.player.id for sl, _ in analysis.cut_loss_candidates(world.my_slots, world.trends)}
    hours = _hours_to_deadline(world)
    sold = set(json.loads(store.get("sold_ids") or "[]"))
    events: list[str] = []
    for sl in world.my_slots:
        it = listed.get(sl.player.id)
        if not it or it.offers_count <= 0:
            continue
        name, pid = notify.esc(sl.player.name), sl.player.id
        try:
            offers = models.parse_player_offers(api.player_team_offers(world.league_id, sl.player_team_id))
        except Exception as exc:
            events.append(f"❌ No he podido leer las ofertas por <b>{name}</b>: {notify.esc(str(exc))}")
            continue
        trend = world.trends.get(pid, (None, analysis.Trend(0, 0, 0)))[1]
        done = False
        for o in sorted(offers, key=lambda o: -o.money):
            decision, why = ap.offer_decision(
                o, sl.player, loss=ap.sale_loss(mine, pid, world.recent_form), cut_loss=pid in cut,
                trend_d7=trend.d7, breaks_xi=ap.breaks_eleven(mine, pid), hours_to_deadline=hours,
                exposed_in=ap.hours_until_exposed(sl, now),
            )
            if decision == "accept" and not done:
                try:
                    api.accept_offer(world.league_id, it.market_id, o.id, o.money)
                except Exception as exc:
                    events.append(f"❌ No he podido aceptar la oferta por <b>{name}</b>: {notify.esc(str(exc))}")
                    continue
                done = True
                sold.add(pid)
                mine = [pl for pl in mine if pl.id != pid]
                events.append(
                    f"💰 <b>Vendido</b> {name} a {notify.esc(o.from_manager)} por {service.m(o.money)} "
                    f"(valor {service.m(sl.player.market_value)}) — {notify.esc(why)}"
                )
            elif decision == "reject" or decision == "accept":
                if store.alert_is_new(f"offer_rejected:{o.id}", ttl_hours=72):
                    try:
                        api.decline_offer(world.league_id, it.market_id, o.id)
                        events.append(f"🙅 Rechazada oferta por <b>{name}</b> ({service.m(o.money)}): {notify.esc(why)}")
                    except Exception as exc:
                        events.append(f"❌ No he podido rechazar una oferta por <b>{name}</b>: {notify.esc(str(exc))}")
            elif store.alert_is_new(f"offer_hold:{o.id}", ttl_hours=72):
                events.append(f"⏸️ Oferta por <b>{name}</b> de {service.m(o.money)}: no la acepto — {notify.esc(why)}")
    store.set("sold_ids", json.dumps(sorted(sold)))
    return events


def _list_for_sale(store: Store, api: FantasyAPI, world) -> list[str]:
    """Todos tus jugadores siempre en venta: así la liga manda una oferta diaria por cada uno
    y `_resolve_offers` decide. Estar en venta no obliga a vender nada."""
    listed = {it.player.id for it in world.market if it.seller_team_id == world.my_team_id}
    done: list[str] = []
    for sl in world.my_slots:
        p = sl.player
        if p.id in listed or not p.market_value or not sl.player_team_id or p.position_id not in ap.FIELD_POSITIONS:
            continue
        price = ap.listing_price(p)
        try:
            api.sell_player(world.league_id, sl.player_team_id, price)
            done.append(f"{notify.esc(p.name)} ({service.m(price)})")
        except Exception as exc:
            if store.alert_is_new(f"list_fail:{p.id}", ttl_hours=24):
                done.append(f"{notify.esc(p.name)} ❌ {notify.esc(str(exc))[:120]}")
    if not done:
        return []
    return ["🏷️ En venta (solo se vende si llega una buena oferta): " + ", ".join(done)]


def _squad_changes(store: Store, world) -> list[str]:
    """Jugadores que han desaparecido de tu plantilla sin que el bot los vendiera: casi
    siempre, un rival te ha pagado la cláusula."""
    now_ids = {sl.player.id: sl.player.name for sl in world.my_slots}
    prev = json.loads(store.get("squad_snapshot") or "{}")
    sold = set(json.loads(store.get("sold_ids") or "[]"))
    events = []
    for pid, name in prev.items():
        if pid in now_ids:
            continue
        if pid in sold:
            sold.discard(pid)
        else:
            events.append(f"🚨 <b>{notify.esc(name)}</b> ya no está en tu plantilla: te lo han clausulado.")
    store.set("squad_snapshot", json.dumps(now_ids))
    store.set("sold_ids", json.dumps(sorted(sold)))
    return events


def _apply_lineup(store: Store, api: FantasyAPI, world) -> str | None:
    """Guarda el mejor once (gratis y reversible hasta que empieza la jornada). La forma del
    cuerpo no está documentada: prueba las variantes de `autopilot.lineup_payload`, vuelve a
    leer la alineación y solo da por buena la que de verdad se ha guardado (y la recuerda)."""
    try:
        if (api.current_week() or {}).get("isLive"):
            return None  # jornada en juego: no tocar
    except Exception:
        pass
    if time.time() < float(store.get("lineup_retry_after") or 0):
        return None
    slots = [sl for sl in world.my_slots if sl.player.position_id in ap.FIELD_POSITIONS and sl.player_team_id]
    if not slots:
        return None
    probs = estimate_start_probability(api, [sl.player for sl in slots])
    cands = []
    for sl in slots:
        prob = float(probs.get(sl.player.id, {}).get("start_probability", 70)) / 100
        cands.append(lineup.Candidate(sl.player, prob, round(ap.xpts(sl.player, world.recent_form) * prob, 2)))
    formation, eleven, total = lineup.best_eleven(cands)
    if not eleven or not formation:
        return None
    ptid = {sl.player.id: sl.player_team_id for sl in slots}
    ids_by_pos = {pos: [ptid[c.player.id] for c in eleven if c.player.position_id == pos] for pos in ap.FIELD_POSITIONS}
    desired = {ptid[c.player.id] for c in eleven}
    current = api.lineup(world.my_team_id)
    current_formation = tuple((current.get("formation") or {}).get("tacticalFormation") or ())
    if ap.lineup_ids(current) == desired and current_formation == tuple(formation):
        return None
    learned = store.get("lineup_variant")
    variants = ([learned] if learned else []) + [v for v in ap.LINEUP_VARIANTS if v != learned]
    errors = []
    for v in variants:
        try:
            api.update_lineup(world.my_team_id, ap.lineup_payload(formation, ids_by_pos, v))
        except Exception as exc:
            errors.append(f"{v}: {str(exc)[:150]}")
            continue
        if ap.lineup_ids(api.lineup(world.my_team_id)) == desired:
            store.set("lineup_variant", v)
            aviso = "" if len(eleven) == 11 else f" · ⚠️ solo {len(eleven)} jugadores: faltan fichajes"
            return f"🧩 <b>Alineación guardada</b> {'-'.join(map(str, formation))} · {total} pts esperados{aviso}"
        errors.append(f"{v}: la API respondió bien pero no se guardó")
    store.set("lineup_retry_after", str(time.time() + 6 * 3600))
    return "⚠️ No he podido guardar la alineación (reintento en 6h): " + notify.esc(" | ".join(errors))[:700]


def _watch_once(store: Store, s) -> str:
    """Una pasada del piloto automático, sin pedir confirmación a nadie: ofertas recibidas,
    fichajes/clausulazos, poner a la venta, protección, alineación — y un único mensaje de
    Telegram con lo que se ha hecho (nada si no ha pasado nada)."""
    now = datetime.now()
    api = FantasyAPI(s)
    store.retire_all_pending()
    confirm.poll_and_execute(s, store, api)  # botones antiguos: responde que ya no aplican

    world = _world(api, s, trends=True)
    _record_status_history(store, world)
    team_plan = _sync_plan(store, s, world)
    events: list[str] = _squad_changes(store, world)
    events += _check_bid_resolutions(store, world)

    sold = _resolve_offers(store, s, api, world)
    events += sold
    if sold:
        world = _world(api, s, trends=True)

    bought, reserved = _acquire(store, s, api, world)
    events += bought
    if bought:
        world = _world(api, s, trends=True)

    hours = _hours_to_deadline(world)
    if any(analysis.position_shortage(world.my_slots).values()) and hours is not None and hours <= s.lineup_lock_hours:
        debt = _emergency_debt_buy(store, s, api, world, team_plan)  # último recurso, ver docstring
        if debt:
            events.append(debt)
            world = _world(api, s, trends=True)

    events += _list_for_sale(store, api, world)
    shielded, shielded_player_id = _auto_shield(store, s, api, world)
    if shielded:
        events.append(shielded)
    raised_clause = _auto_increase_clause(store, s, api, world, skip_player_id=shielded_player_id)
    if raised_clause:
        events.append(raised_clause)
    lineup_msg = _apply_lineup(store, api, world)
    if lineup_msg:
        events.append(lineup_msg)

    if events:
        notify.send_all(s, "🤖 <b>PILOTO AUTOMÁTICO</b>\n\n" + "\n\n".join(events), html=True)
    if digest.due(store, s):
        notify.send_all(s, service.situational_briefing(world, s))
        digest.mark_sent(store)

    sniped = _snipe(store, api, world, reserved)
    if sniped:
        notify.send_all(s, "🤖 <b>PILOTO AUTOMÁTICO</b>\n\n" + "\n\n".join(sniped), html=True)
    return f"[{now:%H:%M}] ok · {len(events) + len(sniped)} acciones/avisos"


def cmd_pending(args, s) -> None:
    store = Store(s.db_file)
    rows = store.get_pending()
    if not rows:
        print("Sin propuestas pendientes.")
        return
    for r in rows:
        print(f"[{r['id']}] {r['kind']}\n{r['description']}\n")


def cmd_plan(args, s) -> None:
    store = Store(s.db_file)
    api = FantasyAPI(s)
    world = _world(api, s, trends=True)
    if args.refresh:
        team_plan = plan_mod.generate_plan(world, s, store)
        plan_mod.save_plan(store, team_plan)
    else:
        team_plan = plan_mod.load_plan(store)
    text = plan_mod.render_plan_text(team_plan)
    # Quita las etiquetas HTML para la Terminal (Telegram sí las interpreta, la consola no).
    import re
    print(re.sub(r"</?[bi]>", "", text))
    if args.telegram:
        msg_id = store.get(plan_mod.PLAN_MESSAGE_ID_KEY)
        if not (msg_id and notify.edit_message(s, int(msg_id), text)):
            new_id = notify.send_all(s, text, html=True)
            if new_id:
                store.set(plan_mod.PLAN_MESSAGE_ID_KEY, str(new_id))
                notify.pin_message(s, new_id)


def cmd_tick(args, s) -> None:
    """Una sola pasada de vigilancia (pensado para cron / GitHub Actions)."""
    if args.dry_run:
        _dry_run(s)
        return
    if not notify.any_enabled(s):
        sys.exit("tick necesita Telegram configurado")
    print(_watch_once(Store(s.db_file), s))


def _dry_run(s) -> None:
    """Lee todo de verdad pero no escribe nada: ni en la API (pujas, ventas, cláusulas,
    alineación), ni en Telegram, ni en tu base de datos (trabaja sobre una copia)."""
    import re
    import shutil
    import tempfile
    from pathlib import Path

    db = Path(tempfile.mkdtemp()) / "fantasy.sqlite3"
    if s.db_file.exists():
        shutil.copy(s.db_file, db)
    FantasyAPI._write = lambda self, method, path, body=None: print(
        f"[simulado] {method} {path} {json.dumps(body, ensure_ascii=False)}"
    )
    notify.send_all = lambda settings, text, **kw: print(re.sub(r"</?[bi]>", "", text) + "\n")
    notify.get_telegram_updates = lambda *a, **kw: []
    notify.edit_message = lambda *a, **kw: True
    notify.pin_message = lambda *a, **kw: None
    print(_watch_once(Store(db), s))


def cmd_watch(args, s) -> None:
    """Bucle local: alarmas de cláusula cada X minutos e informe completo una vez al día."""
    if not notify.any_enabled(s):
        sys.exit("El modo watch necesita Telegram configurado en el .env")
    store = Store(s.db_file)
    print(f"👀 Vigilando cada ~{s.watch_interval_min} min. Informe diario a las {s.report_hour}:00. Ctrl+C para salir.")
    while True:
        try:
            print(_watch_once(store, s))
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"[{datetime.now():%H:%M}] error: {exc}")
        # Intervalo con algo de aleatoriedad para no pegar peticiones a hora fija.
        time.sleep(s.watch_interval_min * 60 * random.uniform(0.85, 1.15))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="fantasy", description="Analista de LaLiga Fantasy (solo lectura)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("auth", help="Login y sesión")
    p.add_argument("step", choices=["url", "code", "status", "refresh"])
    p.add_argument("url", nargs="?")
    p.set_defaults(func=cmd_auth)

    p = sub.add_parser("probe", help="Ver JSON crudo de una ruta de la API")
    p.add_argument("path", help="p.ej. /v1/competition/1/leagues")
    p.add_argument("--public", action="store_true", help="sin token")
    p.add_argument("--max-chars", type=int, default=6000)
    p.set_defaults(func=cmd_probe)

    sub.add_parser("leagues", help="Tus ligas").set_defaults(func=cmd_leagues)
    sub.add_parser("standing", help="Clasificación con ids").set_defaults(func=cmd_standing)

    for name, help_ in [
        ("market", "Oportunidades de mercado"),
        ("trends", "Tus jugadores: cuáles conviene vender ya"),
        ("rivals", "Resumen de rivales"),
        ("clauses", "Alarmas de cláusulas"),
        ("lineup", "Once recomendado"),
        ("report", "Informe completo"),
    ]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("--telegram", action="store_true", help="enviar también por Telegram")
        if name in ("lineup", "report"):
            p.add_argument("--news", action="store_true", help="estima titularidad por histórico de jornadas jugadas")
        p.set_defaults(func=cmd_section)

    sub.add_parser("watch", help="Vigilancia continua con alertas por Telegram").set_defaults(func=cmd_watch)
    p = sub.add_parser("tick", help="Una pasada del piloto automático (para cron / GitHub Actions)")
    p.add_argument("--dry-run", action="store_true", help="simular: no escribe nada en la API ni en Telegram")
    p.set_defaults(func=cmd_tick)
    sub.add_parser("pending", help="Propuestas (pujas/cláusulas) esperando tu confirmación").set_defaults(func=cmd_pending)

    p = sub.add_parser("plan", help="Plan de equipo: fichajes objetivo, venta priorizada, vigilancia de rivales")
    p.add_argument("--refresh", action="store_true", help="regenerar ahora (por defecto, una vez por semana)")
    p.add_argument("--telegram", action="store_true", help="fijar/actualizar el panel en Telegram")
    p.set_defaults(func=cmd_plan)

    args = parser.parse_args(argv)
    settings = load_settings()
    try:
        args.func(args, settings)
    except KeyboardInterrupt:
        print("\nHasta luego.")
    except RuntimeError as exc:
        sys.exit(f"❌ {exc}")


if __name__ == "__main__":
    main()
