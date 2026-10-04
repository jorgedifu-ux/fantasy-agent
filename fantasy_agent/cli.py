"""Línea de comandos: `python -m fantasy_agent <comando>`."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timedelta, timezone

from . import analysis, auth, autopilot as ap, confirm, digest, lineup, models, notify, plan as plan_mod, service, siege
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
    """Último recurso, a <24h de la jornada y con la plantilla incompleta sin nada pagable
    con tu saldo: permite endeudarte hasta el tope REAL del juego
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
    store.add_market_bid(pick.item.player.id, pick.item.player.name, pick.item.price, expires_at)
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
    """Blindaje (gratis, 1 por equipo y jornada, solo sobre una cláusula ya abierta) del
    jugador tuyo más fácil de clausular. Antes se pregunta a `check_shield` (400 = el equipo
    ya gastó el suyo, no se insiste) y después se verifica releyendo la plantilla: el 26/09
    la API respondió bien sin blindar (en la app pasa por ver un anuncio)."""
    now = datetime.now(timezone.utc)
    if world.clause_freeze and world.clause_freeze[0] <= now < world.clause_freeze[1]:
        return None, ""  # cláusulas congeladas: nadie puede clausularte ahora
    exposed = [sl for sl in world.my_slots if ap.hours_until_exposed(sl, now) == 0]
    if not exposed:
        return None, ""
    target = min(exposed, key=lambda sl: sl.clause / sl.player.market_value)
    if not store.alert_is_new(f"shield:{target.player.id}", ttl_hours=96):
        return None, ""
    name = notify.esc(target.player.name)
    try:
        api.check_shield(world.league_id, target.player_team_id)
    except Exception:
        return None, ""  # ahora no se puede blindar (límite de la jornada gastado, etc.)
    try:
        api.shield_player(world.league_id, target.player_team_id)
    except Exception as exc:
        return f"🛡️ Intento de blindaje fallido para <b>{name}</b>: {notify.esc(str(exc))}", ""
    squad = models.parse_squad(api.team(world.league_id, world.my_team_id), world.my_team_id, "")
    if not any(sl.player_team_id == target.player_team_id and sl.shielded_until for sl in squad):
        return (
            f"🛡️ No he podido blindar a <b>{name}</b>: la API no lo aplica sin ver el anuncio de la "
            f"app. Si quieres protegerlo, blíndalo tú desde la app (es gratis)."
        ), ""
    return f"🛡️ <b>BLINDADO</b>: {name} protegido de clausulazos (gratis, automático).", target.player.id


def _auto_increase_clause(store: Store, s, api: FantasyAPI, world, skip_player_id: str = "") -> str | None:
    """Protección DE PAGO para tus mejores jugadores (media ≥5) cuya cláusula queda al alcance
    de los rivales en <24h y no se han vendido antes (ver la venta por riesgo en
    `autopilot.offer_decision`): la sube a 1.5x su valor, por encima de lo que es un objetivo
    lógico. Se paga la mitad de lo que sube; solo si cabe sin tocar el colchón. Se verifica
    releyendo la plantilla."""
    now = datetime.now(timezone.utc)
    if world.clause_freeze and world.clause_freeze[0] <= now < world.clause_freeze[1]:
        return None
    candidates = []
    for sl in world.my_slots:
        exposed = ap.hours_until_exposed(sl, now)
        if sl.player.id != skip_player_id and exposed is not None and exposed <= 24 and sl.player.avg_points >= 5.0:
            candidates.append((exposed, sl))
    if not candidates:
        return None
    _, target = min(candidates, key=lambda t: t[0])
    p = target.player
    if not store.alert_is_new(f"raise_clause:{p.id}", ttl_hours=96):
        return None
    increase = round(p.market_value * 1.5) - target.clause
    cost = round(increase / 2)
    reserve = world.my_cash * s.budget_reserve_pct if world.my_cash else 0
    if increase <= 0 or not world.my_cash or cost > (world.my_cash - reserve):
        return None
    name = notify.esc(p.name)
    try:
        api.increase_buyout_clause(world.league_id, target.player_team_id, increase)
    except Exception as exc:
        return f"❌ Intento de subir la cláusula de <b>{name}</b> fallido: {notify.esc(str(exc))}"
    squad = models.parse_squad(api.team(world.league_id, world.my_team_id), world.my_team_id, "")
    after = next((sl.clause for sl in squad if sl.player_team_id == target.player_team_id), 0)
    if after < target.clause + increase * 0.9:
        return f"⚠️ Pedí subir la cláusula de <b>{name}</b> pero no ha cambiado ({service.m(after)})."
    return (
        f"⬆️ <b>CLÁUSULA SUBIDA</b>: <b>{name}</b> de {service.m(target.clause)} a {service.m(after)} "
        f"(coste ~{service.m(cost)}): ya no es un objetivo lógico para ningún rival."
    )


SNIPE_WINDOW_S = 25 * 60  # dentro del mismo job de GitHub (timeout 28 min)
SIEGE_WINDOW_S = 20 * 60  # el bloqueo espera menos: tras la espera aún relee todo y ejecuta


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


def _rival_premium(store: Store, api: FantasyAPI, world) -> ap.RivalPremium | None:
    """Sobreprecio típico de los rivales al ganar pujas, recalculado una vez al día."""
    cached = json.loads(store.get("rival_premium") or "null")
    if not cached or time.time() - cached["at"] > 86400:
        my_manager = next((r.manager_id for r in world.standing if r.team_id == world.my_team_id), "")
        ratios = sorted(service.rival_bid_premiums(api, world.league_id, my_manager))
        cached = {"at": time.time()}
        if len(ratios) >= 5:
            cached.update(median=ratios[len(ratios) // 2], p75=ratios[int(len(ratios) * 0.75)])
        store.set("rival_premium", json.dumps(cached))
    return ap.RivalPremium(cached["median"], cached["p75"]) if "median" in cached else None


def _prune_bids(store: Store, api: FantasyAPI, world) -> list[str]:
    """Cancela pujas vivas por jugadores que se han lesionado/sancionado antes de resolverse."""
    events = []
    for it in world.market:
        if not (it.my_bid and it.my_bid_id and it.player.status.lower() in ap.INJURED):
            continue
        name = notify.esc(it.player.name)
        try:
            api.cancel_bid(world.league_id, it.market_id, it.my_bid_id)
        except Exception as exc:
            events.append(f"❌ No he podido cancelar la puja por <b>{name}</b> ({it.player.status}): {notify.esc(str(exc))}")
            continue
        for b in store.unresolved_market_bids("buy"):
            if b["player_id"] == it.player.id:
                store.resolve_market_bid(b["id"], "cancelled")
        events.append(f"🚫 Puja cancelada por <b>{name}</b>: ahora está {notify.esc(it.player.status)}.")
    return events


def _acquire(store: Store, s, api: FantasyAPI, world, extra_reserved: int = 0) -> tuple[list[str], list[ap.Move]]:
    """Fichajes y clausulazos autónomos (ver autopilot.plan_acquisitions). Devuelve también
    las cláusulas que se liberan pronto y ya tienen su dinero reservado (para `_snipe`)."""
    now = datetime.now(timezone.utc)
    committed, incoming = _committed_bids(store, world)
    budget = int((world.my_cash or 0) * (1 - s.budget_reserve_pct)) - committed - extra_reserved
    if budget <= 0:
        return [], []
    mine = [sl.player for sl in world.my_slots] + incoming
    avoid = frozenset(t for t in (world.leader_team_id, world.revenge_against_team_id) if t)
    moves = ap.clause_moves(world.rival_slots, now, freeze=world.clause_freeze, avoid_team_ids=avoid) + \
        ap.bid_moves(world.market, skip_player_ids=frozenset(pl.id for pl in incoming))
    short = {pos for pos, n in analysis.position_shortage(world.my_slots).items() if n}
    moves = [
        m for m in moves
        if m.player.position_id in short or not ap.is_falling(
            *(lambda tr: (tr.d3, tr.d7))(world.trends.get(m.player.id, (None, analysis.Trend(0, 0, 0)))[1])
        )
    ]
    plan = ap.plan_acquisitions(mine, moves, budget, form=world.recent_form, max_squad=s.max_squad,
                                rivals=_rival_premium(store, api, world))
    events: list[str] = []
    spent = sum(m.cost for m in plan)
    trends = {pid: tr for pid, (_, tr) in world.trends.items()}
    invest_budget = int((budget - spent) * (
        ap.INVEST_FRACTION_BREAK if world.outlook.in_break else ap.INVEST_FRACTION_NORMAL))
    slots_left = s.max_squad - len(mine) - len(plan)
    if invest_budget > 0 and slots_left > 0 and trends:
        plan += ap.plan_investments(
            ap.invest_moves(world.market, trends, skip_player_ids=frozenset(pl.id for pl in mine) | {m.player.id for m in plan}),
            invest_budget, slots_left)
    for mv in plan:
        name, pos = notify.esc(mv.player.name), mv.player.position
        if mv.kind == "invest":
            try:
                api.bid(world.league_id, mv.item.market_id, mv.cost)
                expires = mv.item.expires.timestamp() if mv.item.expires else None
                store.add_market_bid(mv.player.id, mv.player.name, mv.cost, expires)
                tr = trends[mv.player.id]
                events.append(
                    f"📈 <b>Inversión</b>: {name} ({pos}) {service.m(mv.cost)} · ha subido {tr.d3:+.1f}% en 3 días y "
                    f"{tr.d7:+.1f}% en 7: se compra para revender, no para el once"
                )
            except Exception as exc:
                events.append(f"❌ Inversión fallida por <b>{name}</b>: {notify.esc(str(exc))}")
            continue
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
    paid: dict[str, int] | None = None  # lo que pagué por cada uno: se consulta solo si hay ofertas
    for sl in world.my_slots:
        it = listed.get(sl.player.id)
        if not it or it.offers_count <= 0:
            continue
        if paid is None:
            my_manager = next((r.manager_id for r in world.standing if r.team_id == world.my_team_id), "")
            paid = service.purchase_prices(api, world.league_id, my_manager)
        name, pid = notify.esc(sl.player.name), sl.player.id
        try:
            offers = models.parse_player_offers(api.player_team_offers(world.league_id, sl.player_team_id))
        except Exception as exc:
            events.append(f"❌ No he podido leer las ofertas por <b>{name}</b>: {notify.esc(str(exc))}")
            continue
        trend = world.trends.get(pid, (None, analysis.Trend(0, 0, 0)))[1]
        done = False
        in_siege = pid in _siege_ids(store)
        released = in_siege and hours is not None and hours <= 0  # jornada ya empezada: se puede vender
        for o in sorted(offers, key=lambda o: -o.money):
            decision, why = ap.offer_decision(
                o, sl.player, loss=ap.sale_loss(mine, pid, world.recent_form), cut_loss=(pid in cut) or released,
                no_sell=in_siege and not released,
                trend_d7=trend.d7, breaks_xi=ap.breaks_eleven(mine, pid), hours_to_deadline=hours,
                exposed_in=ap.hours_until_exposed(sl, now), squad_full=len(world.my_slots) >= s.max_squad,
                cost_basis=None if in_siege else paid.get(pid),
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
    store.set("sold_ids", json.dumps(sorted(sold)))
    return events


def _list_for_sale(store: Store, api: FantasyAPI, world) -> list[str]:
    """Todos tus jugadores siempre en venta: así la liga manda una oferta diaria por cada uno
    y `_resolve_offers` decide. Estar en venta no obliga a vender nada."""
    listed = {it.player.id for it in world.market if it.seller_team_id == world.my_team_id}
    done: list[str] = []
    hours = _hours_to_deadline(world)
    for sl in world.my_slots:
        p = sl.player
        if p.id in _siege_ids(store) and (hours is None or hours > 0):
            continue  # los porteros de la operación bloqueo no se ponen a la venta antes de la jornada
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
        fx = world.fixtures.get(sl.player.team_id)
        factor = ap.fixture_factor(fx.home if fx else None, world.laliga_rank.get(fx.rival_id) if fx else None,
                                   len(world.laliga_rank) or 20)
        cands.append(lineup.Candidate(sl.player, prob, round(ap.xpts(sl.player, world.recent_form) * prob * factor, 2)))
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


# ---------------------------------------------------------------------------------------------
# Operación bloqueo (ver siege.py): dejar sin portero al líder
# ---------------------------------------------------------------------------------------------
def _siege_ids(store: Store) -> set[str]:
    return set(json.loads(store.get("siege_ids") or "[]"))


def _siege_add(store: Store, player_id: str) -> None:
    store.set("siege_ids", json.dumps(sorted(_siege_ids(store) | {player_id})))


def _siege_state(store: Store, key: str) -> dict:
    st = json.loads(store.get("siege_state") or "{}")
    return st if st.get("jornada") == key else {"jornada": key}


def _siege_plan(store: Store, s, api: FantasyAPI, world, max_hours: float = 7 * 24) -> siege.SiegePlan | None:
    out = world.outlook
    hours = out.hours_to_next
    if out.next_first is None or hours is None or hours <= 0 or hours > max_hours:
        return None
    others = [r for r in world.standing if r.team_id != world.my_team_id]
    if not others:
        return None
    target = max(others, key=lambda r: r.points)
    if world.leader_team_id != target.team_id:
        return None  # el líder soy yo: no hay a quién bloquear
    try:
        current = models.to_int(models.pick(api.current_week(), "weekNumber"), default=0)
    except Exception:
        current = 0
    committed, incoming = _committed_bids(store, world)
    mine = [sl.player for sl in world.my_slots] + incoming
    free_cash = int((world.my_cash or 0) * (1 - s.budget_reserve_pct)) - committed
    freeze_start = world.clause_freeze[0] if world.clause_freeze else out.next_first - timedelta(hours=24)
    return siege.evaluate(
        target_slots=[sl for sl in world.rival_slots if sl.owner_team_id == target.team_id],
        other_slots=[sl for sl in world.rival_slots if sl.owner_team_id != target.team_id],
        my_slots=world.my_slots, market=world.market, now=datetime.now(timezone.utc),
        first_match=out.next_first, freeze_start=freeze_start, free_cash=free_cash,
        target_cash=service.estimate_cash(api, world.league_id, target.manager_id),
        target_points=service.recent_points(api, world.league_id, target.team_id, current),
        shields_used=service.shields_used_since(api, world.league_id, target.manager_id, out.prev_last),
        jornada=current, squad_slots_free=s.max_squad - len(mine), my_xi_ok=ap.complete_eleven(mine),
        target_name=target.manager_name, target_team_id=target.team_id,
    )


def _siege_tick(store: Store, s, api: FantasyAPI, world) -> tuple[list[str], int]:
    """Evalúa la operación en cada pasada. Devuelve (avisos, dinero a reservar). Cuando es viable
    y faltan ≤96 h, se anuncia, se reserva el dinero (para que las compras normales no lo
    gasten) y se pujan ya los porteros del mercado que se resuelven antes de la ejecución."""
    plan = _siege_plan(store, s, api, world)
    if plan is None:
        return [], 0
    key = world.outlook.next_first.isoformat()
    st = _siege_state(store, key)
    if st.get("done"):
        return [], 0
    events: list[str] = []
    hours_to_exec = (plan.exec_at - datetime.now(timezone.utc)).total_seconds() / 3600
    armed = plan.feasible and hours_to_exec <= siege.ARM_HOURS
    if armed and not st.get("armed"):
        st["armed"] = True
        events.append("🎯 <b>OPERACIÓN BLOQUEO ARMADA</b>\n" + notify.esc(siege.render(plan)))
    elif st.get("armed") and not plan.feasible:
        st["armed"] = False
        events.append("❎ <b>Operación bloqueo descartada</b>:\n" + notify.esc("\n".join(plan.reasons)))
    store.set("siege_state", json.dumps(st))
    if not armed:
        return events, 0
    for step in plan.steps:
        if step.kind == "block_bid" and step.when == "pre" and step.cost and step.item and not step.item.my_bid:
            try:
                api.bid(world.league_id, step.item.market_id, step.cost)
                store.add_market_bid(step.player.id, step.player.name, step.cost,
                                     step.item.expires.timestamp() if step.item.expires else None)
                _siege_add(store, step.player.id)
                events.append(f"🎯 Bloqueo: puja de {service.m(step.cost)} por el portero <b>{notify.esc(step.player.name)}</b> "
                              f"para que {notify.esc(plan.target_name)} no lo fiche.")
            except Exception as exc:
                events.append(f"❌ Bloqueo: no he podido pujar por {notify.esc(step.player.name)}: {notify.esc(str(exc))}")
    return events, plan.outlay


def _siege_go(store: Store, s, api: FantasyAPI, world) -> list[str]:
    """Ejecuta la operación en el último momento (3 min antes de congelarse las cláusulas):
    espera dentro de este mismo job (máx. 25 min, como `_snipe`), relee todo, reevalúa y, si
    sigue siendo viable, quita los porteros del líder y cierra las vías de reposición."""
    out = world.outlook
    if out.next_first is None or not world.clause_freeze:
        return []
    key = out.next_first.isoformat()
    st = _siege_state(store, key)
    if not st.get("armed") or st.get("done"):
        return []
    freeze_start = world.clause_freeze[0]
    t_exec = freeze_start - siege.EXEC_MARGIN
    now = datetime.now(timezone.utc)
    if now >= freeze_start or (t_exec - now).total_seconds() > SIEGE_WINDOW_S:
        return []
    wait = (t_exec - now).total_seconds()
    if wait > 0:
        time.sleep(wait)
    api.clear_cache()  # datos frescos tras la espera: el mercado se acaba de resolver
    fresh = _world(api, s, trends=False)
    plan = _siege_plan(store, s, api, fresh)
    st["done"] = True
    store.set("siege_state", json.dumps(st))
    if plan is None or not plan.feasible:
        why = "\n".join(plan.reasons) if plan else "ya no hay jornada que bloquear"
        return ["❎ <b>Operación bloqueo cancelada en el último momento</b>:\n" + notify.esc(why)]
    events = [f"🎯 <b>Ejecutando el bloqueo a {notify.esc(plan.target_name)}</b>"]
    order = {"kill_clause": 0, "block_clause": 1, "block_bid": 2}
    for step in sorted(plan.steps, key=lambda x: (order[x.kind], -x.cost)):
        if step.cost == 0:
            continue
        name = notify.esc(step.player.name)
        try:
            if step.kind == "block_bid":
                api.bid(fresh.league_id, step.item.market_id, step.cost)
                store.add_market_bid(step.player.id, step.player.name, step.cost,
                                     step.item.expires.timestamp() if step.item.expires else None)
            else:
                api.pay_buyout_clause(fresh.league_id, step.slot.player_team_id, step.cost)
                store.record_auto_op("siege", step.player.id, step.cost)
            _siege_add(store, step.player.id)
            events.append(f"  ✅ {name}: {service.m(step.cost)} ({notify.esc(step.note)})")
        except Exception as exc:
            events.append(f"  ❌ {name}: {notify.esc(str(exc))}")
            if step.kind == "kill_clause":
                events.append("  Paro aquí: sin quitarle los porteros el resto no sirve de nada.")
                break
    try:
        team = models.parse_squad(api.team(fresh.league_id, plan.target_team_id), plan.target_team_id, plan.target_name)
        gks = [sl.player.name for sl in team if sl.player.position_id == siege.GK and sl.player.available]
        events.append(f"Resultado: {notify.esc(plan.target_name)} se queda con {len(gks)} portero(s)" + (f": {notify.esc(', '.join(gks))}" if gks else " 🎉"))
    except Exception:
        pass
    return events


def cmd_siege(args, s) -> None:
    """Analiza ahora mismo si el bloqueo al líder sería viable (no escribe nada)."""
    api = FantasyAPI(s)
    store = Store(s.db_file)
    world = _world(api, s, trends=False)
    plan = _siege_plan(store, s, api, world, max_hours=24 * 30)
    if plan is None:
        print("No hay jornada próxima, o el líder eres tú: nada que analizar.")
        return
    out = world.outlook
    print(f"Próxima jornada: {out.next_first.astimezone():%a %d/%m %H:%M}\n")
    print(siege.render(plan))


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

    pruned = _prune_bids(store, api, world)
    events += pruned
    if pruned:
        world = _world(api, s, trends=True)

    siege_events, siege_reserve = _siege_tick(store, s, api, world)
    events += siege_events
    bought, reserved = _acquire(store, s, api, world, extra_reserved=siege_reserve)
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
    out = world.outlook
    if out.in_break and store.alert_is_new(f"break_on:{out.next_first:%Y%m%d}", ttl_hours=24 * 30):
        events.append(
            f"📅 <b>Parón en curso</b> hasta el {out.next_first.astimezone():%d/%m %H:%M}: no hay once que "
            f"puntuar, así que dedico el {int(ap.INVEST_FRACTION_BREAK * 100)}% del saldo libre a inversión "
            f"(jugadores en subida sostenida que se revenden)."
        )
    if out.next_break and store.alert_is_new(f"break_next:{out.next_break[0]:%Y%m%d}", ttl_hours=24 * 30):
        a, b = out.next_break
        events.append(
            f"📅 Próximo parón: del {a.astimezone():%d/%m} al {b.astimezone():%d/%m} "
            f"({(b - a).days} días sin partidos): modo inversión."
        )
    hours = _hours_to_deadline(world)
    if hours is not None and 0 < hours <= 30 and not ap.complete_eleven([sl.player for sl in world.my_slots]) \
            and store.alert_is_new("xi_incomplete", ttl_hours=5):
        events.append(
            f"🚨 <b>No puedes alinear 11 jugadores</b> y la jornada empieza en {hours:.0f}h: "
            f"sin 11 completos puntuarías 0. Tienes {len(world.my_slots)} jugadores y {service.m(world.my_cash)}."
        )

    if events:
        notify.send_all(s, "🤖 <b>PILOTO AUTOMÁTICO</b>\n\n" + "\n\n".join(events), html=True)
    if digest.due(store, s):
        notify.send_all(s, service.situational_briefing(world, s))
        digest.mark_sent(store)

    sniped = _siege_go(store, s, api, world) + _snipe(store, api, world, reserved)
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
    store = Store(s.db_file)
    try:
        print(_watch_once(store, s))
    except Exception as exc:
        if store.alert_is_new("tick_failed", ttl_hours=3):  # como mucho un aviso cada 3 h
            try:
                notify.send_all(s, f"🔴 <b>El bot ha fallado</b>: {notify.esc(str(exc))[:600]}", html=True)
            except Exception:
                pass
        raise


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
    sub.add_parser("siege", help="Analiza si dejar sin portero al líder sería viable ahora").set_defaults(func=cmd_siege)
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
