"""Línea de comandos: `python -m fantasy_agent <comando>`."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone

from . import analysis, auth, confirm, digest, notify, plan as plan_mod, service
from .api import FantasyAPI
from .attendance import estimate_titularidad
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


def _recovered_ids(store: Store, players) -> frozenset:
    return frozenset(p.id for p in players if store.recently_recovered(p.id))


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


def _emergency_buy(store: Store, s, api: FantasyAPI, world) -> str | None:
    """Red de seguridad: si no puedes alinear 11 legales, ficha del mercado LIBRE (nunca
    clausulazos) sin pedirte confirmación. No tener 11 en el momento en que se guarda la
    alineación es JORNADA ENTERA A CERO, no un mal menor (confirmado con la ayuda oficial de
    LaLiga Fantasy) — por eso el tope de gasto y el límite semanal se relajan cuanto más cerca
    esté el cierre. Nunca llega a endeudarse solo: eso sigue necesitando tu confirmación."""
    shortage = analysis.position_shortage(world.my_slots)
    if not any(shortage.values()):
        return None
    hours_left = _hours_to_deadline(world)
    critical = hours_left is not None and hours_left <= s.lineup_lock_hours
    urgent = hours_left is not None and hours_left <= 6
    if not critical and len(store.auto_buys_this_week()) >= s.emergency_buys_per_week:
        return None
    cap_pct = s.emergency_buy_cap_pct * (3 if urgent else 1.5 if critical else 1)
    already = {b["player_id"] for b in store.auto_buys_this_week()}
    candidates = [
        o for o in analysis.emergency_candidates(world.my_slots, world.market, world.my_cash, min(cap_pct, 1.0))
        if o.item.player.id not in already
    ]
    if not candidates:
        return None
    pick = candidates[0]
    name = notify.esc(pick.item.player.name)
    cap = int(world.my_cash * min(cap_pct, 1.0)) if world.my_cash else pick.item.price
    money = analysis.bid_amount(pick.item, pick.score, world.my_cash, cap_price=cap)
    try:
        api.bid(world.league_id, pick.item.market_id, money)
    except Exception as exc:
        return f"❌ Fichaje de emergencia fallido para <b>{name}</b>: {notify.esc(str(exc))}"
    store.record_auto_buy(pick.item.player.id, money)
    expires_at = pick.item.expires.timestamp() if pick.item.expires else None
    store.add_market_bid(pick.item.player.id, name, money, expires_at)
    urgencia = " · ⏰ ÚLTIMA HORA, tope de gasto ampliado" if urgent else " · tope ampliado, jornada cerca" if critical else ""
    return (
        f"🚨 <b>FICHAJE DE EMERGENCIA</b> (sin confirmar — plantilla incompleta{urgencia})\n"
        f"Puja <b>enviada</b> (pendiente de resolverse) por <b>{name}</b> ({pick.item.player.position}), "
        f"{service.m(money)}\n"
        f"Motivo: {notify.esc('; '.join(pick.reasons))}\n"
        f"Te aviso en cuanto se sepa si la ganas."
    )


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


def _auto_buy(store: Store, s, api: FantasyAPI, world, recovered_ids: frozenset) -> str | None:
    """Fichaje autónomo normal (sin confirmar), tope AUTO_BUYS_PER_WEEK — a diferencia del de
    emergencia, este no espera a que falte plantilla: es simplemente "esta oportunidad es tan
    buena que no hace falta preguntar", igual que ya decidiste que hiciéramos con los
    fichajes de emergencia. Nunca se endeuda (solo `_emergency_debt_buy` lo hace, y solo
    cuando de verdad hace falta) — respeta el mismo colchón de saldo que las propuestas
    normales (`BUDGET_RESERVE_PCT`)."""
    if len(store.auto_ops_today("auto_buy")) >= s.auto_buys_per_day:
        return None
    already = {b["player_id"] for b in store.auto_ops_today("auto_buy")}
    picks = [
        o for o in service.top_bid_candidates(world, s, min_score=18, recovered_ids=recovered_ids)
        if o.item.player.id not in already
    ]
    if not picks:
        return None
    pick = picks[0]
    name = notify.esc(pick.item.player.name)
    money = analysis.bid_amount(pick.item, pick.score, world.my_cash)
    if money > (world.my_cash or 0):
        return None
    try:
        api.bid(world.league_id, pick.item.market_id, money)
    except Exception as exc:
        return f"❌ Fichaje autónomo fallido para <b>{name}</b>: {notify.esc(str(exc))}"
    store.record_auto_op("auto_buy", pick.item.player.id, money)
    expires_at = pick.item.expires.timestamp() if pick.item.expires else None
    store.add_market_bid(pick.item.player.id, name, money, expires_at)
    return (
        f"🛒 <b>FICHAJE AUTÓNOMO</b> (sin confirmar — oportunidad muy buena, score {pick.score})\n"
        f"Puja <b>enviada</b> (pendiente de resolverse) por <b>{name}</b> ({pick.item.player.position}), "
        f"{service.m(money)}\nMotivo: {notify.esc('; '.join(pick.reasons)) or 'buena oportunidad'}\n"
        f"Te aviso en cuanto se sepa si la ganas."
    )


def _auto_sell(store: Store, s, api: FantasyAPI, world, team_plan: plan_mod.Plan) -> str | None:
    """Venta autónoma (sin confirmar), tope AUTO_SELLS_PER_WEEK — de la lista de venta ya
    decidida en el Plan (no se improvisa en el momento), tal y como pediste: "que vaya
    haciendo... tres ventas [por semana]"."""
    if len(store.auto_ops_today("auto_sell")) >= s.auto_sells_per_day:
        return None
    already = {b["player_id"] for b in store.auto_ops_today("auto_sell")}
    mine_ids = {sl.player.id for sl in world.my_slots}
    candidates = [
        i for i in plan_mod.sell_priority_ids(team_plan)
        if i.player_id in mine_ids and i.player_id not in already
    ]
    if not candidates:
        return None
    pick = candidates[0]
    slot = next(sl for sl in world.my_slots if sl.player.id == pick.player_id)
    price = slot.player.market_value
    name = notify.esc(pick.player_name)
    try:
        api.sell_player(world.league_id, slot.player_team_id, price)
    except Exception as exc:
        return f"❌ Venta autónoma fallida para <b>{name}</b>: {notify.esc(str(exc))}"
    store.record_auto_op("auto_sell", pick.player_id, price)
    store.add_market_bid(pick.player_id, name, price, None, direction="sell", sell_kind=pick.sell_kind)
    return (
        f"💸 <b>VENTA AUTÓNOMA</b> (según el plan, sin confirmar)\n"
        f"<b>{name}</b> puesto a la venta por {service.m(price)}\n"
        f"Motivo: {notify.esc(pick.reason)}\nTe aviso en cuanto se venda de verdad."
    )


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
            store.resolve_market_bid(b["id"], "sold")
            results.append(f"💰 <b>Vendido</b>: {notify.esc(b['player_name'])} por {service.m(b['price'])}.")
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


def _auto_shield(store: Store, s, api: FantasyAPI, world) -> str | None:
    """Blindaje automático: protege GRATIS a tu jugador más vulnerable a que un rival te lo
    clausule (misma regla de "riesgo propio" ≤1.25x el valor). Sin coste ni riesgo de dinero
    — si falla (ya blindado, límite de 1 vez por jornada ya usado, o el servidor exige de
    verdad ver el anuncio — sin confirmar en vivo todavía), no pasa nada, solo se avisa."""
    now = datetime.now(timezone.utc)
    risky = []
    for sl in world.my_slots:
        p = sl.player
        if not p.market_value or sl.clause <= 0 or not sl.clause_open(now):
            continue
        ratio = sl.clause / p.market_value
        if ratio <= 1.25:
            risky.append((ratio, sl))
    if not risky:
        return None
    risky.sort(key=lambda t: t[0])
    _, target = risky[0]
    if not store.alert_is_new(f"shield:{target.player.id}", ttl_hours=20):
        return None
    name = notify.esc(target.player.name)
    try:
        api.shield_player(world.league_id, target.player_team_id)
    except Exception as exc:
        return (
            f"🛡️ Intento de blindaje fallido para <b>{name}</b>: {notify.esc(str(exc))}\n"
            f"Sin coste — puede que haga falta activarlo a mano desde la app la primera vez."
        )
    return f"🛡️ <b>BLINDADO</b>: {name} protegido de clausulazos (gratis, automático)."


def _check_and_accept_offers(store: Store, s, api: FantasyAPI, world) -> list[str]:
    """Revisa las ofertas recibidas en tus anuncios de venta pendientes y acepta la mejor si
    supera el umbral mínimo — distinto según por qué se puso en venta, ver
    analysis.min_acceptable_offer (respondiendo a tu pregunta de "cuánto % por encima").

    ⚠️ Forma de la oferta sin confirmar en vivo todavía (nunca ha llegado una real que probar).
    Si esto no detecta nada aun viendo `numberOfOffers > 0` en el mercado, compara con
    `fantasy probe /v1/competition/1/league/<liga>/market` y ajusta `models._parse_offers`."""
    my_listings = {item.player.id: item for item in world.market if item.seller_team_id == world.my_team_id}
    results: list[str] = []
    for b in store.unresolved_market_bids("sell"):
        item = my_listings.get(b["player_id"])
        if not item or not item.offers:
            continue
        best = max(item.offers, key=lambda o: o.money)
        threshold = analysis.min_acceptable_offer(b["price"], b["sell_kind"] or "")
        if best.money < threshold:
            continue
        try:
            api.accept_offer(world.league_id, item.market_id, best.id, best.money)
        except Exception as exc:
            results.append(
                f"❌ No he podido aceptar la oferta por <b>{notify.esc(b['player_name'])}</b>: "
                f"{notify.esc(str(exc))}"
            )
            continue
        store.resolve_market_bid(b["id"], "sold")
        results.append(
            f"💰 <b>Oferta aceptada</b>: {notify.esc(b['player_name'])} vendido a "
            f"{notify.esc(best.from_manager)} por {service.m(best.money)} "
            f"(mínimo exigido: {service.m(threshold)})."
        )
    return results


def _watch_once(store: Store, s) -> str:
    """Una pasada: ejecuta lo ya aprobado que caiga en esta ventana (al segundo exacto),
    responde a tus confirmaciones, cubre huecos críticos sin preguntar (dentro del tope),
    propone lo nuevo (máx. unas pocas decisiones, nunca un tocho), y manda como mucho un
    parte de situación corto por franja horaria en vez de todo de golpe."""
    now = datetime.now()
    api = FantasyAPI(s)

    confirm.run_scheduled(s, store, api)  # lo confirmado con antelación, si toca ya

    world = _world(api, s, trends=True)
    _record_status_history(store, world)
    confirm.poll_and_execute(s, store, api)
    team_plan = _sync_plan(store, s, world)

    events: list[str] = []
    emergency = _emergency_buy(store, s, api, world)
    if not emergency:
        emergency = _emergency_debt_buy(store, s, api, world, team_plan)  # último recurso, ver docstring
    if emergency:
        events.append(emergency)
        world = _world(api, s, trends=True)  # recalcular: acabas de gastar, quiero que se note ya

    recovered = _recovered_ids(store, [sl.player for sl in world.my_slots] + [i.player for i in world.market])
    auto_bought = _auto_buy(store, s, api, world, recovered)
    if auto_bought:
        events.append(auto_bought)
        world = _world(api, s, trends=True)

    auto_sold = _auto_sell(store, s, api, world, team_plan)
    if auto_sold:
        events.append(auto_sold)
        world = _world(api, s, trends=True)

    shielded = _auto_shield(store, s, api, world)
    if shielded:
        events.append(shielded)

    _, alerts = service.clauses_report(world, s)
    fresh = [a for a in alerts if store.alert_is_new(a.key)]
    actionable = [a for a in fresh if a.kind == "open_affordable"][:3]  # nunca más de 3 a la vez
    watch_ids = plan_mod.watchlist_ids(team_plan)
    for a in actionable:
        ratio = a.slot.clause / a.slot.player.market_value if a.slot.player.market_value else 1.0
        en_plan = "\n📐 Según el plan de vigilancia." if a.slot.player.id in watch_ids else \
            "\n⚠️ Fuera de plan — surge ahora, no estaba previsto."
        confirm.propose(
            s, store, "clause",
            {
                "league_id": world.league_id, "player_id": a.slot.player_team_id, "amount": a.slot.clause,
                "player_name": a.slot.player.name,
            },
            f"Clausulazo — {a.slot.player.name} (de {a.slot.owner_name})\n"
            f"Cláusula: {service.m(a.slot.clause)} · Valor de mercado: {service.m(a.slot.player.market_value)}"
            f"{en_plan}",
            label=analysis.clause_urgency_label(ratio, a.penalty),
        )

    bought_autonomously = {b["player_id"] for b in store.auto_ops_today("auto_buy")}
    for o in service.top_bid_candidates(world, s, recovered_ids=recovered):
        if o.item.player.id in bought_autonomously:
            continue  # ya se fichó solo por encima del umbral autónomo, no lo propongas también
        key = f"bid:{o.item.player.id}:{o.item.price}"
        if store.alert_is_new(key, ttl_hours=24):
            # Puja de última hora: si sabemos cuándo cierra el anuncio, se propone ya (para que
            # puedas decir que sí con calma) pero se EJECUTA ~60s antes del cierre — no antes,
            # para no revelar la puja pronto y evitar que otro reaccione (ver STRATEGY.md).
            # El importe ya incluye sobrepuja si la oportunidad lo merece (analysis.bid_amount).
            money = analysis.bid_amount(o.item, o.score, world.my_cash)
            execute_at = o.item.expires.timestamp() - 60 if o.item.expires else None
            confirm.propose(
                s, store, "bid",
                {
                    "league_id": world.league_id, "market_id": o.item.market_id, "money": money,
                    "player_id": o.item.player.id, "player_name": o.item.player.name,
                    "expires_at": o.item.expires.timestamp() if o.item.expires else None,
                },
                f"Fichaje — {o.item.player.name} ({o.item.player.position})\n"
                f"Precio de salida: {service.m(o.item.price)} · pujamos {service.m(money)} · score {o.score}\n"
                f"{'; '.join(o.reasons) or 'sin avisos'}",
                execute_at=execute_at,
                label=analysis.player_quality_label(o.score),
            )

    for accepted in _check_and_accept_offers(store, s, api, world):
        notify.send_all(s, accepted, html=True)

    for resolved in _check_bid_resolutions(store, world):
        notify.send_all(s, resolved, html=True)

    confirm.run_scheduled(s, store, api)  # por si algo se confirmó y ya toca, dentro de este mismo tick

    for e in events:
        notify.send_all(s, e, html=True)  # inmediato: acabas de perder saldo, no esperas turno para saberlo

    if digest.due(store, s):
        notify.send_all(s, service.situational_briefing(world, s))
        digest.mark_sent(store)

    return (
        f"[{now:%H:%M}] ok · {len(fresh)} alertas nuevas · {len(actionable)} propuestas de cláusula"
        f"{' · ' + str(len(events)) + ' evento(s) de emergencia' if events else ''}"
    )


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
    if not notify.any_enabled(s):
        sys.exit("tick necesita Telegram configurado")
    print(_watch_once(Store(s.db_file), s))


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
    sub.add_parser("tick", help="Una sola pasada de vigilancia (para cron / GitHub Actions)").set_defaults(func=cmd_tick)
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
