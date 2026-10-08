"""Línea de comandos: `python -m fantasy_agent <comando>`."""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone

from . import analysis, auth, autopilot as ap, confirm, digest, export, learn, lineup, models, notify, plan as plan_mod, service, siege
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


def _clause_raise_probe(store: Store, s, api: FantasyAPI, world, skip_player_id: str = "") -> str | None:
    """Prueba ÚNICA y barata de la subida de cláusula (ruta sin probar): sube un 10% la de un
    jugador barato (≤2,5M, coste ~50-125K) y anota cuánto subió y cuánto se cobró de verdad, en
    `kv.clause_raise_test` (se exporta). Con eso se decide la política de "cláusula tentadora".
    Sustituye a la antigua protección a 1,5x: costaba el 25% del valor y, como la cláusula ya es
    lo que pagaste o más, que te clausulen nunca es perder dinero (decisión del usuario)."""
    if store.get("clause_raise_test"):
        return None
    now = datetime.now(timezone.utc)
    if world.clause_freeze and world.clause_freeze[0] <= now < world.clause_freeze[1]:
        return None
    options = [sl for sl in world.my_slots if sl.player.id != skip_player_id and sl.player_team_id
               and 500_000 <= sl.player.market_value <= 2_500_000 and sl.player.status.lower() == "ok"]
    if not options or not world.my_cash:
        return None
    target = min(options, key=lambda sl: sl.player.market_value)
    increase = max(100_000, round(target.player.market_value * 0.10))
    if increase > world.my_cash * 0.5:
        return None
    name = notify.esc(target.player.name)
    result = {"at": time.time(), "player": target.player.name, "value": target.player.market_value,
              "clause_before": target.clause, "increase": increase, "cash_before": world.my_cash}
    try:
        api.increase_buyout_clause(world.league_id, target.player_team_id, increase)
    except Exception as exc:
        result["error"] = str(exc)[:300]
        store.set("clause_raise_test", json.dumps(result))
        return f"🧪 Prueba de subir cláusula ({name}): la API ha dicho que no — {notify.esc(str(exc))[:150]}"
    api.clear_cache()
    squad = models.parse_squad(api.team(world.league_id, world.my_team_id), world.my_team_id, "")
    result["clause_after"] = next((sl.clause for sl in squad if sl.player_team_id == target.player_team_id), 0)
    result["cash_after"] = service.resolve_league(api, s)[2]
    store.set("clause_raise_test", json.dumps(result))
    paid = (result["cash_before"] - (result["cash_after"] or 0))
    return (f"🧪 <b>Prueba de subir cláusula</b>: {name} de {service.m(target.clause)} a {service.m(result['clause_after'])} "
            f"pidiendo +{service.m(increase)}; me han cobrado {service.m(paid)}. Con esto se decide cuánto subir las demás.")


SNIPE_WINDOW_S = 25 * 60  # dentro del mismo job de GitHub (timeout 40 min)
SIEGE_WINDOW_S = 20 * 60  # el bloqueo espera menos: tras la espera aún relee todo y ejecuta


# ---------------------------------------------------------------------------------------------
# Robustez: cada paso por separado y pago de cláusulas releyendo el importe
# ---------------------------------------------------------------------------------------------
def _step(store: Store, errors: list[str], name: str, fn, *args, default=None, **kwargs):
    """Ejecuta un paso de la pasada; si falla, lo registra (con traza) y sigue con los demás.
    Un corte de Telegram o de la API en un paso no debe dejar sin hacer la alineación."""
    import traceback
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        store.log_error(name, traceback.format_exc())
        from .storage import redact
        errors.append(redact(f"{name}: {exc}"))
        print(redact(f"[{name}] error: {exc}"))
        return default


def _is_transient(exc: BaseException) -> bool:
    """Cortes pasajeros (red, 5xx, 429, reintentos agotados): no son fallos del bot."""
    import socket
    import urllib.error
    from .http import HttpError
    if isinstance(exc, HttpError):
        return exc.status >= 500 or exc.status == 429
    if isinstance(exc, (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError)):
        return True
    return isinstance(exc, RuntimeError) and str(exc).startswith("Fallo tras reintentos")


def _pay_clause(api: FantasyAPI, league_id: str, slot, planned: int) -> int:
    """Relee la cláusula en ese mismo instante y paga EXACTAMENTE lo que vale ahora. Si ha subido
    por encima de lo planeado (+1%), no paga. Devuelve lo pagado. (Comprobado con los 15
    clausulazos reales: lo enviado y lo cobrado coinciden; esto cubre el caso de que cambie
    entre que se decide y se paga, p. ej. en una cláusula "al segundo" que espera minutos.)"""
    fresh = models.parse_squad(api.team_fresh(league_id, slot.owner_team_id), slot.owner_team_id, slot.owner_name)
    cur = next((x for x in fresh if x.player_team_id == slot.player_team_id), None)
    if cur is None:
        raise RuntimeError(f"{slot.player.name} ya no está en el equipo de {slot.owner_name}")
    if not cur.clause_open(datetime.now(timezone.utc)):
        raise RuntimeError(f"la cláusula de {slot.player.name} aún está bloqueada o blindada")
    if cur.clause > planned * 1.01:
        raise RuntimeError(f"la cláusula de {slot.player.name} ha subido de {planned / 1e6:.2f}M a {cur.clause / 1e6:.2f}M: no pago")
    api.pay_buyout_clause(league_id, slot.player_team_id, cur.clause)
    return cur.clause


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
    credit = ap.credit_room(sum(sl.player.market_value for sl in world.my_slots), (world.my_cash or 0) - committed - extra_reserved,
                            _hours_to_deadline(world), s.leverage_pct)
    if budget <= 0 and credit <= 0:
        return [], []
    budget = max(0, budget)
    mine = [sl.player for sl in world.my_slots] + incoming
    avoid = frozenset(t for t in (world.leader_team_id, world.revenge_against_team_id) if t)
    moves = ap.clause_moves(world.rival_slots, now, freeze=world.clause_freeze, avoid_team_ids=avoid,
                            leader_team_id=world.leader_team_id or "") + \
        ap.bid_moves(world.market, skip_player_ids=frozenset(pl.id for pl in incoming))
    trends = {pid: tr for pid, (_, tr) in world.trends.items()}
    # Tendencia de las cláusulas de rivales con precio razonable (no están en `world.trends`).
    for m in moves:
        if m.kind == "clause" and m.player.id not in trends and m.cost <= m.player.market_value * ap.CLAUSE_INVEST_MAX_RATIO:
            try:
                trends[m.player.id] = analysis.trend_from_history(models.parse_value_history(api.market_value_history(m.player.id)))
            except Exception:
                pass
    short = {pos for pos, n in analysis.position_shortage(world.my_slots).items() if n}
    leader_players = [sl.player for sl in world.rival_slots if sl.owner_team_id == world.leader_team_id]
    kept = []
    for m in moves:
        tr = trends.get(m.player.id, analysis.Trend(0, 0, 0))
        if m.player.position_id not in short and ap.is_falling(tr.d3, tr.d7):
            continue
        m.drift = ap.expected_drift(tr.d3, tr.d7, world.recent_form.get(m.player.id))
        if m.bonus:
            m.rival_loss = ap.leader_loss(leader_players, m.player.id, world.recent_form)
        kept.append(m)
    moves = kept
    plan = ap.plan_acquisitions(mine, moves, budget, form=world.recent_form, max_squad=s.max_squad,
                                rivals=_rival_premium(store, api, world))
    events: list[str] = []
    spent = sum(m.cost for m in plan)
    invest_budget = int((budget - spent) * ap.PARAMS["invest_mult"] * (
        ap.INVEST_FRACTION_BREAK if world.outlook.in_break else ap.INVEST_FRACTION_NORMAL)) + credit
    slots_left = s.max_squad - len(mine) - len(plan)
    taken = frozenset(pl.id for pl in mine) | {m.player.id for m in plan}
    candidates = (ap.invest_moves(world.market, trends, skip_player_ids=taken, form=world.recent_form)
                  + ap.clause_invest_moves(world.rival_slots, trends, now, freeze=world.clause_freeze, avoid_team_ids=avoid,
                                           skip_player_ids=taken, form=world.recent_form,
                                           leader_team_id=world.leader_team_id or "")) if trends else []
    if invest_budget > 0 and slots_left > 0 and candidates:
        plan += ap.plan_investments(candidates, invest_budget, slots_left)
    # Rotación de capital: si hay inversiones buenas que no se han podido pagar (o no caben en la
    # plantilla), se anota para que `_resolve_offers` venda antes algún suplente que no suba.
    gk = ap.backup_keeper(mine + [m.player for m in plan], world.market, budget - sum(m.cost for m in plan))
    if gk is not None and s.max_squad - len(mine) - len(plan) > 0:
        cost = min(ap.bid_amount(gk, 0.0), budget - sum(m.cost for m in plan))
        plan.append(ap.Move("bid", gk.player, cost, item=gk, score=0.0))
    funded = {m.player.id for m in plan}
    # Sin dinero para un buen golpe al líder (le quita ≥2 pts): también se libera capital vendiendo suplentes.
    unfunded = [m for m in candidates if m.player.id not in funded] + \
        [m for m in moves if m.bonus and m.rival_loss >= 2 and m.player.id not in funded]
    store.set("liquidity", json.dumps({"at": time.time(), "n": len(unfunded),
                                       "best": unfunded[0].player.name if unfunded else ""}))
    if credit > 0 and any(m.kind in ("invest", "invest_clause") for m in plan) and store.alert_is_new(
            f"credit:{world.clause_freeze[1]:%Y%m%d}" if world.clause_freeze else "credit", ttl_hours=24 * 10):
        events.append(f"💳 <b>Parón largo: invierto también a crédito</b> (hasta {service.m(credit)}). Se devuelve "
                      f"vendiendo desde {ap.DELEVER_H} h antes de la jornada: con saldo negativo al empezar no se puntúa.")
    for mv in plan:
        name, pos = notify.esc(mv.player.name), mv.player.position
        if mv.kind in ("bid", "invest") and ap.bid_timing(mv.item, now) != "now":
            continue  # se puja en el último minuto (ver autopilot.bid_timing y `_timed_actions`)
        if mv.kind == "invest":
            try:
                api.bid(world.league_id, mv.item.market_id, mv.cost)
                expires = mv.item.expires.timestamp() if mv.item.expires else None
                store.add_market_bid(mv.player.id, mv.player.name, mv.cost, expires, ask=mv.item.price)
                store.log_purchase(mv.player.id, "inversion", mv.cost)
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
                motivo = (f"inversión: ha subido {trends[mv.player.id].d3:+.1f}% en 3 días y {trends[mv.player.id].d7:+.1f}% en 7"
                          if mv.kind == "invest_clause" else f"+{mv.gain} pts/jornada")
                if mv.bonus:
                    motivo += (f" · al líder le quita {mv.rival_loss:.1f} pts; se paga justo antes de que se congelen "
                               f"las cláusulas para que no pueda reponerlo")
                events.append(
                    f"⏳ Reservo {service.m(mv.cost)} para clausular a <b>{name}</b> ({pos}, de "
                    f"{notify.esc(mv.slot.owner_name)}) cuando se libere el {when} · {motivo}"
                )
            continue
        if mv.kind == "invest_clause":
            try:
                paid = _pay_clause(api, world.league_id, mv.slot, mv.cost)
                store.record_auto_op("clause", mv.player.id, paid)
                store.log_purchase(mv.player.id, "inversion", paid)
                tr = trends[mv.player.id]
                events.append(
                    f"📈 <b>Inversión por cláusula</b>: {name} ({pos}, de {notify.esc(mv.slot.owner_name)}) por "
                    f"{service.m(paid)} · ha subido {tr.d3:+.1f}% en 3 días y {tr.d7:+.1f}% en 7: se compra para revender"
                )
            except Exception as exc:
                events.append(f"❌ Inversión por cláusula fallida por <b>{name}</b>: {notify.esc(str(exc))}")
            continue
        try:
            if mv.kind == "clause":
                paid = _pay_clause(api, world.league_id, mv.slot, mv.cost)
                store.record_auto_op("clause", mv.player.id, paid)
                store.log_purchase(mv.player.id, "puntos", paid)
                events.append(
                    f"⚡ <b>Clausulazo</b>: {name} ({pos}, de {notify.esc(mv.slot.owner_name)}) por "
                    f"{service.m(paid)} · +{mv.gain} pts/jornada al once"
                )
            else:
                api.bid(world.league_id, mv.item.market_id, mv.cost)
                expires = mv.item.expires.timestamp() if mv.item.expires else None
                store.add_market_bid(mv.player.id, mv.player.name, mv.cost, expires, ask=mv.item.price)
                store.log_purchase(mv.player.id, "puntos", mv.cost)
                cierre = mv.item.expires.astimezone().strftime("%H:%M") if mv.item.expires else "?"
                motivo = "portero suplente (solo tienes uno)" if mv.player.position_id == 1 and not mv.gain else f"+{mv.gain} pts/jornada"
                events.append(
                    f"🛒 <b>Puja</b>: {name} ({pos}) {service.m(mv.cost)} (salida {service.m(mv.item.price)}) "
                    f"· {motivo} · se resuelve a las {cierre}"
                )
        except Exception as exc:
            events.append(f"❌ {'Clausulazo' if mv.kind == 'clause' else 'Puja'} fallido por <b>{name}</b>: {notify.esc(str(exc))}")
    late = [mv for mv in plan if mv.kind in ("bid", "invest") and ap.bid_timing(mv.item, now) == "late"]
    return events, [mv for mv in plan if not mv.executable_now] + late


def _late_bid(store: Store, api: FantasyAPI, world, mv: ap.Move) -> str | None:
    """Puja del último minuto: relee el anuncio (sigue ahí, sin puja nuestra) y puja lo planeado."""
    api.clear_cache()
    market = models.parse_market(api.market(world.league_id))
    it = next((x for x in market if x.market_id == mv.item.market_id), None)
    name = notify.esc(mv.player.name)
    if it is None or it.my_bid:
        return None
    if it.player.status.lower() in ap.INJURED:
        return f"🚫 No pujo por <b>{name}</b>: ahora está {notify.esc(it.player.status)}."
    api.bid(world.league_id, it.market_id, mv.cost)
    expires = it.expires.timestamp() if it.expires else None
    store.add_market_bid(mv.player.id, mv.player.name, mv.cost, expires, ask=it.price)
    store.log_purchase(mv.player.id, "inversion" if mv.kind == "invest" else "puntos", mv.cost)
    motivo = ("inversión (en subida)" if mv.kind == "invest" else
              "portero suplente" if mv.player.position_id == 1 and not mv.gain else f"+{mv.gain} pts/jornada")
    return (f"🛒 <b>Puja en el último minuto</b>: {name} ({mv.player.position}) {service.m(mv.cost)} "
            f"(salida {service.m(it.price)}) · {motivo} · los rivales no la han visto venir")


def _timed_actions(store: Store, api: FantasyAPI, world, reserved: list[ap.Move]) -> list[str]:
    """Lo que hay que hacer al segundo dentro de este job, en orden de hora: pujas a falta de
    `LATE_BID_LEAD_S` del cierre y cláusulas nada más liberarse (`_snipe`)."""
    now = datetime.now(timezone.utc)
    jobs = []
    for mv in reserved:
        if mv.kind in ("bid", "invest") and mv.item and mv.item.expires:
            jobs.append((mv.item.expires - timedelta(seconds=ap.LATE_BID_LEAD_S), "bid", mv))
        elif mv.kind in ("clause", "invest_clause") and mv.unlock_at and 0 < (mv.unlock_at - now).total_seconds() <= SNIPE_WINDOW_S:
            jobs.append((mv.unlock_at, "clause", mv))
    events: list[str] = []
    for when, kind, mv in sorted(jobs, key=lambda j: j[0]):
        if kind == "clause":
            events += _snipe(store, api, world, [mv])
            continue
        wait = (when - datetime.now(timezone.utc)).total_seconds()
        if wait > SNIPE_WINDOW_S:
            continue
        if wait > 0:
            time.sleep(wait)
        try:
            msg = _late_bid(store, api, world, mv)
        except Exception as exc:
            msg = f"❌ Puja del último minuto fallida por <b>{notify.esc(mv.player.name)}</b>: {notify.esc(str(exc))}"
        if msg:
            events.append(msg)
    return events


def _snipe(store: Store, api: FantasyAPI, world, reserved: list[ap.Move]) -> list[str]:
    """Cláusulas con dinero ya reservado que se liberan dentro de este mismo job: espera al
    segundo exacto y paga, antes de que otro rival se adelante."""
    events: list[str] = []
    now = datetime.now(timezone.utc)
    soon = sorted(
        (mv for mv in reserved if mv.kind in ("clause", "invest_clause") and 0 < (mv.unlock_at - now).total_seconds() <= SNIPE_WINDOW_S),
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
                paid = _pay_clause(api, world.league_id, mv.slot, mv.cost)
                store.record_auto_op("clause", mv.player.id, paid)
                store.log_purchase(mv.player.id, "inversion" if mv.kind == "invest_clause" else "puntos", paid)
                events.append(
                    f"⚡ <b>Clausulazo al segundo</b>: {name} ({mv.player.position}) por {service.m(paid)} "
                    f"nada más liberarse · " + ("inversión (en subida)" if mv.kind == "invest_clause" else f"+{mv.gain} pts/jornada")
                )
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                time.sleep(5)
        if last_exc:
            events.append(f"❌ No he podido clausular a <b>{name}</b> al liberarse: {notify.esc(str(last_exc))}")
    return events


def _delever(store: Store, s, api: FantasyAPI, world) -> list[str]:
    """Volver a saldo positivo antes de que empiece la jornada (si no, esa jornada puntúa 0): acepta
    ofertas de la liga, primero de quien menos aporta al once, con un mínimo cada vez menor según se
    acerca el primer partido (`autopilot.delever_min`). Nunca deja el once incompleto."""
    committed, _ = _committed_bids(store, world)
    need = committed - (world.my_cash or 0)
    hours = _hours_to_deadline(world)
    floor = ap.delever_min(hours)
    if need <= 0 or floor is None:
        return []
    need = int(need * 1.03) + 100_000  # margen: el valor puede moverse antes de la jornada
    mine = [sl.player for sl in world.my_slots]
    listed = {it.player.id: it for it in world.market if it.seller_team_id == world.my_team_id}
    options = []
    for sl in world.my_slots:
        it = listed.get(sl.player.id)
        if not it or it.offers_count <= 0 or not sl.player.market_value or sl.player.id in _siege_ids(store):
            continue
        try:
            offers = models.parse_player_offers(api.player_team_offers(world.league_id, sl.player_team_id))
        except Exception:
            continue
        for o in offers:
            if o.is_system and o.money >= sl.player.market_value * floor:
                options.append((ap.sale_loss(mine, sl.player.id, world.recent_form), -o.money / sl.player.market_value, sl, it, o))
    events: list[str] = []
    sold = set(json.loads(store.get("sold_ids") or "[]"))
    for _, _, sl, it, o in sorted(options, key=lambda x: (x[0], x[1])):
        if need <= 0:
            break
        if sl.player.id in sold or ap.breaks_eleven(mine, sl.player.id):
            continue
        try:
            api.accept_offer(world.league_id, it.market_id, o.id, o.money)
        except Exception as exc:
            events.append(f"❌ No he podido aceptar la oferta por <b>{notify.esc(sl.player.name)}</b>: {notify.esc(str(exc))}")
            continue
        need -= o.money
        sold.add(sl.player.id)
        mine = [p for p in mine if p.id != sl.player.id]
        events.append(f"💳 <b>Devuelvo crédito</b>: vendido {notify.esc(sl.player.name)} por {service.m(o.money)} "
                      f"(x{o.money / sl.player.market_value:.2f} el valor) — a {hours:.0f} h de la jornada hay que estar en positivo")
    store.set("sold_ids", json.dumps(sorted(sold)))
    if need > 0 and hours is not None and hours <= 36 and store.alert_is_new(f"delever_short:{int(hours // 6)}", ttl_hours=6):
        events.append(f"🔴 <b>Sigo en negativo</b> (faltan {service.m(need)}) a {hours:.0f} h de la jornada: si empieza así, "
                      f"no puntuamos. Mañana a las 20:53 llegan ofertas nuevas y bajo el mínimo exigido.")
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
        mult = ap.ask_multiplier(pid, now)
        for o in offers:
            store.log_offer(o.id, pid, sl.player.name, sl.player.market_value, o.money, o.is_system,
                            ask=it.price, listed_value=round(it.price / mult))
        trend = world.trends.get(pid, (None, analysis.Trend(0, 0, 0)))[1]
        done = False
        in_siege = pid in _siege_ids(store)
        liq = json.loads(store.get("liquidity") or "{}")
        liquidity = bool(liq.get("n")) and time.time() - liq.get("at", 0) < 3 * 3600
        released = in_siege and hours is not None and hours <= 0  # jornada ya empezada: se puede vender
        for o in sorted(offers, key=lambda o: -o.money):
            decision, why = ap.offer_decision(
                o, sl.player, loss=ap.sale_loss(mine, pid, world.recent_form), cut_loss=(pid in cut) or released,
                no_sell=in_siege and not released, liquidity=liquidity and not in_siege,
                trend_d7=trend.d7, trend_d3=trend.d3, breaks_xi=ap.breaks_eleven(mine, pid), hours_to_deadline=hours,
                exposed_in=ap.hours_until_exposed(sl, now), squad_full=len(world.my_slots) >= s.max_squad,
                cost_basis=None if in_siege else paid.get(pid),
                injured=sl.player.status.lower() in ap.INJURED, clause=sl.clause,
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
    y `_resolve_offers` decide. Estar en venta no obliga a vender. Si el valor de un jugador ha
    subido ≥10% desde que se anunció, se reanuncia al valor nuevo (ver `autopilot.needs_relist`)."""
    now = datetime.now(timezone.utc)
    listed = {it.player.id: it for it in world.market if it.seller_team_id == world.my_team_id}
    done: list[str] = []
    relisted = 0
    hours = _hours_to_deadline(world)
    for sl in world.my_slots:
        p = sl.player
        if p.id in _siege_ids(store) and (hours is None or hours > 0):
            continue  # los porteros de la operación bloqueo no se ponen a la venta antes de la jornada
        if not p.market_value or not sl.player_team_id or p.position_id not in ap.FIELD_POSITIONS:
            continue
        mult = ap.ask_multiplier(p.id, now)
        it = listed.get(p.id)
        if it is not None:
            if relisted >= 4 or not ap.needs_relist(it.price, p.market_value, mult):
                continue
            try:
                api.withdraw_listing(world.league_id, it.market_id)
            except Exception as exc:
                if store.alert_is_new(f"relist_fail:{p.id}", ttl_hours=24):
                    done.append(f"{notify.esc(p.name)} ❌ no he podido retirar el anuncio: {notify.esc(str(exc))[:100]}")
                continue
            relisted += 1
        price = ap.listing_price(p, now)
        try:
            api.sell_player(world.league_id, sl.player_team_id, price)
            done.append(f"{notify.esc(p.name)} ({service.m(price)}{' · reanunciado' if it is not None else ''})")
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
                paid = _pay_clause(api, fresh.league_id, step.slot, step.cost)
                store.record_auto_op("siege", step.player.id, paid)
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


# ---------------------------------------------------------------------------------------------
# Revisión: ¿estamos ganando dinero? (patrimonio diario, operaciones cerradas, resumen semanal)
# ---------------------------------------------------------------------------------------------
PILOT_START = "2026-09-26"  # día en que el piloto automático empezó a operar


def _record_wealth(store: Store, world) -> None:
    day = datetime.now().strftime("%Y-%m-%d")
    store.log_wealth(day, int(world.my_cash or 0), sum(sl.player.market_value for sl in world.my_slots))


def _review_text(api: FantasyAPI, store: Store, world, since: str = PILOT_START, html: bool = True) -> str:
    b = (lambda x: f"<b>{x}</b>") if html else (lambda x: x)
    my_manager = next((r.manager_id for r in world.standing if r.team_id == world.my_team_id), "")
    closed, open_ = service.trade_history(api, world.league_id, my_manager)
    closed = [c for c in closed if c["sold_at"] and c["sold_at"].astimezone().strftime("%Y-%m-%d") >= since]
    value_now = sum(sl.player.market_value for sl in world.my_slots)
    wealth = int(world.my_cash or 0) + value_now
    lines = [b("📊 REVISIÓN"), f"Patrimonio ahora: {service.m(wealth)} (saldo {service.m(world.my_cash)} + plantilla {service.m(value_now)})"]
    today = datetime.now().strftime("%Y-%m-%d")
    for label, days in (("hace 7 días", 7), ("desde que hay registro", None)):
        ref = store.wealth_first() if days is None else store.wealth_on_or_before(
            (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"))
        if ref and ref[0] != today:
            delta = wealth - (ref[1] + ref[2])
            lines.append(f"  vs {label} ({ref[0]}): {delta / 1e6:+.1f}M ({delta / (ref[1] + ref[2]) * 100:+.1f}%)")
    if closed:
        profit = sum(c["got"] - c["paid"] for c in closed)
        wins = sum(1 for c in closed if c["got"] > c["paid"])
        lines.append(f"Operaciones cerradas desde {since}: {len(closed)} · {wins} con ganancia · resultado {profit / 1e6:+.2f}M")
        for kind in ("puja", "cláusula"):
            sel = [c for c in closed if c["how"] == kind]
            if sel:
                lines.append(f"  compradas por {kind}: {len(sel)} · {sum(c['got'] - c['paid'] for c in sel) / 1e6:+.2f}M")
        ordered = sorted(closed, key=lambda c: c["got"] - c["paid"])
        for c in ordered[:2] + ordered[-2:]:
            lines.append(f"  {notify.esc(c['name'])}: pagado {service.m(c['paid'])} → {service.m(c['got'])} ({(c['got'] - c['paid']) / 1e6:+.2f}M, {c['exit']})")
    held = [(sl.player, open_[sl.player.id]) for sl in world.my_slots if sl.player.id in open_]
    if held:
        unreal = sum(p.market_value - o["paid"] for p, o in held)
        lines.append(f"Sin vender aún: {len(held)} jugadores · {unreal / 1e6:+.2f}M sobre lo pagado")
        for p, o in sorted(held, key=lambda x: x[0].market_value - x[1]["paid"]):
            lines.append(f"  {notify.esc(p.name)}: pagado {service.m(o['paid'])} · hoy {service.m(p.market_value)} ({(p.market_value - o['paid']) / 1e6:+.2f}M)")
    pts = next((r.points for r in world.standing if r.team_id == world.my_team_id), 0)
    lines.append(f"Puntos: {pts}")
    return "\n".join(lines)


def _weekly_review(store: Store, s, api: FantasyAPI, world) -> list[str]:
    now = datetime.now()
    key = f"weekly:{now.isocalendar().year}-{now.isocalendar().week}"
    if now.weekday() != 6 or now.hour < 12 or not store.alert_is_new(key, ttl_hours=24 * 8):
        return []
    return [_review_text(api, store, world) + "\n\n" + notify.esc(_params_text(store))]


def cmd_review(args, s) -> None:
    import re
    api = FantasyAPI(s)
    store = _open_store(s, args.cloud)
    world = _world(api, s, trends=False)
    print(re.sub(r"</?[bi]>", "", _review_text(api, store, world, since=args.since, html=False)))


# ---------------------------------------------------------------------------------------------
# Autoajuste (ver learn.py): el bot corrige sus propios parámetros con lo que va viendo
# ---------------------------------------------------------------------------------------------
def _origin_returns(api: FantasyAPI, store: Store, world, origin: str = "inversion") -> list[float]:
    """Rendimiento (cerrado, o a valor de hoy si aún se tiene) de las compras de un origen."""
    my_manager = next((r.manager_id for r in world.standing if r.team_id == world.my_team_id), "")
    closed, open_ = service.trade_history(api, world.league_id, my_manager)
    purchases = store.purchases()
    value_now = {sl.player.id: sl.player.market_value for sl in world.my_slots}

    def origin_of(trade) -> str | None:
        at = trade["at"].timestamp() if trade.get("at") else 0
        near = [p for p in purchases if p["pid"] == trade["pid"] and abs(p["ts"] - at) <= 36 * 3600]
        return min(near, key=lambda p: abs(p["ts"] - at))["origin"] if near else None

    out = []
    for c in closed:
        if c["paid"] and origin_of(c) == origin:
            out.append(c["got"] / c["paid"] - 1)
    for pid, o in open_.items():
        if o["paid"] and pid in value_now and origin_of(o) == origin:
            out.append(value_now[pid] / o["paid"] - 1)
    return out


def _calibrate_drift(api: FantasyAPI) -> dict[str, tuple[float, str]]:
    """Recalibración semanal (pesada: ~250 peticiones): ¿cuánto sube de verdad lo que sube?"""
    players = [p for p in api.players() if models.to_int(p.get("marketValue")) >= 2_000_000]
    players.sort(key=lambda p: -models.to_int(p.get("marketValue")))
    histories = {}
    for p in players[:250]:
        try:
            histories[str(p["id"])] = models.parse_value_history(api.market_value_history(p["id"]))
        except Exception:
            pass
    current = models.to_int(models.pick(api.current_week(), "weekNumber"), default=0)
    ends = {}
    for wk in range(1, current):
        dates = sorted(f.when for f in models.parse_calendar(api.calendar(wk)) if f.when)
        if dates:
            ends[wk] = dates[-1]
    samples = learn.sample_drift(histories, models.week_points_by_id(api.players()), ends)
    return learn.calibrate_drift(samples)


def _tune(store: Store, s, api: FantasyAPI, world, deep: bool = False, dry: bool = False) -> tuple[list[str], dict]:
    """Calcula los ajustes y (si no es `dry`) los aplica y guarda. Devuelve (avisos, cambios).
    Cada parámetro se mueve despacio y siempre dentro de `autopilot.BOUNDS`."""
    live = dict(ap.PARAMS)
    proposed: dict[str, tuple[float, str]] = {}
    try:
        r = learn.optimal_offer_threshold(store.offer_ratios())
        if r:
            proposed["league_offer_min"] = (round(0.5 * live["league_offer_min"] + 0.5 * r[0], 3), f"umbral óptimo x{r[0]:.3f} con {r[1]}")
    except Exception as exc:
        print(f"[autoajuste] ofertas: {exc}")
    try:
        recent_change = max((h["at"] for h in store.param_history() if h["key"] == "bid_base_premium"), default=0)
        r = learn.adjust_bid_premium(live["bid_base_premium"], store.bid_results())
        if r and time.time() - recent_change > 3 * 86400:
            proposed["bid_base_premium"] = (round(r[0], 3), r[1])
    except Exception as exc:
        print(f"[autoajuste] pujas: {exc}")
    try:
        r = learn.invest_multiplier(live["invest_mult"], _origin_returns(api, store, world))
        if r:
            proposed["invest_mult"] = r
    except Exception as exc:
        print(f"[autoajuste] inversión: {exc}")
    if deep:
        try:
            for key, val in _calibrate_drift(api).items():
                proposed[key] = (round(0.5 * live[key] + 0.5 * val[0], 3), val[1])
        except Exception as exc:
            print(f"[autoajuste] inercia: {exc}")
    changes, events = {}, []
    for key, (new, why) in proposed.items():
        lo, hi = ap.BOUNDS[key]
        new = round(min(hi, max(lo, new)), 3)
        if abs(new - live[key]) < (0.004 if key != "invest_mult" else 0.04):
            continue
        changes[key] = (live[key], new, why)
        events.append(f"🔧 <b>Autoajuste</b> · {notify.esc(PARAM_NAMES[key])}: {live[key]:g} → {new:g} ({notify.esc(why)})")
    if changes and not dry:
        ap.apply_params({k: v[1] for k, v in changes.items()})
        store.set_params({k: ap.PARAMS[k] for k in ap.DEFAULTS})
        for k, (old, new, why) in changes.items():
            store.log_param_change(k, old, new, why)
    return events, changes


PARAM_NAMES = {
    "league_offer_min": "umbral de venta (× valor)", "bid_base_premium": "prima base de puja",
    "invest_mult": "dinero a inversión (×)", "drift_strong_good": "subida esperada: fuerte + buena forma",
    "drift_strong_mid": "subida esperada: fuerte", "drift_strong_bad": "subida esperada: fuerte sin forma",
    "drift_early": "subida esperada: entrada anticipada",
}


def _autotune_tick(store: Store, s, api: FantasyAPI, world) -> list[str]:
    """Una vez al día el cálculo ligero; los domingos, además, la recalibración pesada.
    Modo `shadow` (por defecto): calcula y GUARDA lo que cambiaría, pero no lo aplica ni avisa:
    la decisión se toma al revisar los datos. `on`: lo aplica (con límites). `off`: nada."""
    if s.autotune == "off":
        ap.reset_params()
        return []
    now = datetime.now()
    if not store.alert_is_new(f"tune:{now:%Y-%m-%d}", ttl_hours=20):
        return []
    deep = now.weekday() == 6 and store.alert_is_new(f"tune_deep:{now.isocalendar().year}-{now.isocalendar().week}", ttl_hours=24 * 6)
    events, changes = _tune(store, s, api, world, deep=deep, dry=s.autotune != "on")
    if s.autotune != "on":
        if changes:
            store.log_proposal({k: {"old": v[0], "new": v[1], "why": v[2]} for k, v in changes.items()})
        return []
    return events


def _params_text(store: Store) -> str:
    lines = ["Parámetros (fábrica → ahora):"]
    for key, default in ap.DEFAULTS.items():
        mark = "" if abs(ap.PARAMS[key] - default) < 1e-9 else "  ← ajustado"
        lines.append(f"  {PARAM_NAMES[key]}: {default:g} → {ap.PARAMS[key]:g}{mark}")
    props = store.proposals()[-3:]
    if props:
        lines.append("Propuestas del autoajuste (NO aplicadas; decidir al revisar):")
        for pr in props:
            for k, v in pr["changes"].items():
                lines.append(f"  {time.strftime('%d/%m', time.localtime(pr['at']))} {PARAM_NAMES[k]}: {v['old']:g} → {v['new']:g} ({v['why']})")
    recent = store.param_history()[-5:]
    if recent:
        lines.append("Últimos ajustes:")
        for h in recent:
            lines.append(f"  {time.strftime('%d/%m', time.localtime(h['at']))} {PARAM_NAMES[h['key']]}: {h['old']:g} → {h['new']:g} ({h['why']})")
    return "\n".join(lines)


def cmd_tune(args, s) -> None:
    """Qué ajustaría el bot ahora (no guarda nada). Con --deep incluye la recalibración semanal."""
    import re
    api = FantasyAPI(s)
    store = _open_store(s, args.cloud)
    ap.apply_params(store.get_params())
    world = _world(api, s, trends=False)
    print(_params_text(store))
    events, changes = _tune(store, s, api, world, deep=args.deep, dry=True)
    print("\nAjustes que haría ahora:" if changes else "\nNo ajustaría nada ahora (faltan datos o ya está en el valor óptimo).")
    for e in events:
        print(" ", re.sub(r"</?[bi]>", "", e))


# ---------------------------------------------------------------------------------------------
# Exportar el estado para analizarlo fuera de GitHub (ver export.py)
# ---------------------------------------------------------------------------------------------
def _publish_state(store: Store, s) -> list[str]:
    """Cada 6 h publica el estado en la rama `data`. Nunca rompe la pasada: si falla, avisa una vez al día."""
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    now = datetime.now()
    if not (s.export_data and token and repo) or not store.alert_is_new(f"export:{now:%Y-%m-%d}:{now.hour // 6}", ttl_hours=7):
        return []
    try:
        export.publish(export.build_state(store), token=token, repo=repo)
        return []
    except Exception as exc:
        print(f"[export] {exc}")
        if store.alert_is_new(f"export_fail:{now:%Y-%m-%d}", ttl_hours=24):
            return [f"⚠️ No he podido publicar el estado para análisis: {notify.esc(str(exc))[:200]}"]
        return []


def _open_store(s, cloud: bool = False) -> Store:
    """La base de datos local, o (con --cloud) una copia temporal de la que ha publicado el bot en GitHub."""
    if not cloud:
        return Store(s.db_file)
    import tempfile
    from pathlib import Path
    store = Store(Path(tempfile.mkdtemp()) / "cloud.sqlite3")
    state = export.fetch()
    store.import_state(state)
    print(f"[datos de la nube generados el {state['meta'].get('generated_at')}]\n")
    return store


def cmd_pull(args, s) -> None:
    """Descarga el estado que ha publicado el bot y lo guarda en data/cloud_state.json."""
    state = export.fetch()
    path = s.data_dir / "cloud_state.json"
    path.write_text(json.dumps(state, ensure_ascii=False))
    tables = {k: len(v["rows"]) for k, v in state["tables"].items()}
    print(f"Guardado en {path}\nGenerado: {state['meta'].get('generated_at')} (commit {state['meta'].get('commit', '')[:7]})\nFilas: {tables}")
    print("Para analizarlo: python3 -m fantasy_agent offers --cloud · review --cloud · tune --cloud")


def cmd_export(args, s) -> None:
    """Escribe el estado local en data/export.json (y con --publish lo sube a la rama `data`)."""
    store = Store(s.db_file)
    state = export.build_state(store)
    path = s.data_dir / "export.json"
    path.write_text(json.dumps(state, ensure_ascii=False))
    print(f"Escrito {path} ({path.stat().st_size // 1024} KB)")
    if args.publish:
        token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY", export.DEFAULT_REPO)
        if not token:
            sys.exit("Falta GITHUB_TOKEN en el entorno para publicar.")
        print(export.publish(state, token=token, repo=repo))


def cmd_rivals(args, s) -> None:
    """Aprender de los rivales: qué compran, a qué prima, con qué tendencia, y cómo les sale."""
    import re
    from datetime import date
    from . import rivals
    api = FantasyAPI(s)
    league_id, _, _ = service.resolve_league(api, s)
    standing = models.parse_standing(api.standing(league_id))
    managers = {r.manager_id: r.manager_name for r in standing}
    activity = service._all_activity(api, league_id)
    pids = sorted({str(a.get("playerMasterId")) for a in activity if a.get("activityTypeId") in (1, 31)})
    print(f"Leyendo el histórico de {len(pids)} jugadores…", file=sys.stderr)
    hist = {}
    for pid in pids:
        try:
            hist[pid] = models.parse_value_history(api.market_value_history(pid))
        except Exception:
            pass
    names = {str(p.get("id")): p.get("nickname") for p in api.players()}
    since = date.fromisoformat(args.since) if args.since else None
    print(re.sub(r"</?b>", "", rivals.report(activity, hist, managers, names, date.today(), since)))


def cmd_offers(args, s) -> None:
    """Cómo se distribuyen las ofertas de la liga respecto al valor (lo que el bot ha visto)."""
    store = _open_store(s, args.cloud)
    ratios = store.offer_ratios()
    if not ratios:
        print("Aún no hay ofertas registradas.")
        return
    rows = [r for r in store.offer_rows() if r["system"] and r["ask"]]
    if rows:
        print("¿De qué depende la oferta? (oferta / valor actual, según lo que se pedía en el anuncio)")
        for name, lo, hi in (("pedido < 0,95× valor", 0, .95), ("pedido 0,95–1,25×", .95, 1.25), ("pedido 1,25–1,7×", 1.25, 1.7), ("pedido ≥ 1,7×", 1.7, 99)):
            sel = [r["money"] / r["value"] for r in rows if lo <= r["ask"] / r["value"] < hi]
            if sel:
                print(f"  {name:<22} n={len(sel):3d}  oferta media x{sum(sel) / len(sel):.3f} del valor actual")
        for name, lo, hi in (("valor bajó o igual", 0, 1.0), ("valor subió 0–5%", 1.0, 1.05), ("valor subió >5% desde que se anunció", 1.05, 99)):
            sel = [r["money"] / r["value"] for r in rows if r["listed_value"] and lo <= r["value"] / r["listed_value"] < hi]
            if sel:
                print(f"  {name:<36} n={len(sel):3d}  oferta media x{sum(sel) / len(sel):.3f} del valor actual")
        print()
    q = lambda p: ratios[min(len(ratios) - 1, int(len(ratios) * p))]
    print(f"{len(ratios)} ofertas · mín {ratios[0]:.3f} · p10 {q(.1):.3f} · p25 {q(.25):.3f} · mediana {q(.5):.3f} · "
          f"p75 {q(.75):.3f} · p90 {q(.9):.3f} · máx {ratios[-1]:.3f}")
    for lo in [x / 100 for x in range(84, 120, 4)]:
        n = sum(lo <= r < lo + 0.04 for r in ratios)
        print(f"  {lo:.2f}–{lo + .04:.2f}: {'#' * n} {n}")


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
    if s.autotune == "on":
        ap.apply_params(store.get_params())
    else:
        ap.reset_params()  # shadow / off: siempre los valores de fábrica
    errs: list[str] = []
    st = lambda name, fn, *a, default=None, **k: _step(store, errs, name, fn, *a, default=default, **k)  # noqa: E731
    st("propuestas", store.retire_all_pending)
    st("telegram", confirm.poll_and_execute, s, store, api)  # botones antiguos: responde que ya no aplican

    world = _world(api, s, trends=True)  # sin datos no se puede hacer nada: si falla, falla la pasada
    st("historial", _record_status_history, store, world)
    team_plan = st("plan", _sync_plan, store, s, world, default=plan_mod.Plan())
    st("patrimonio", _record_wealth, store, world)
    events: list[str] = st("plantilla", _squad_changes, store, world, default=[])
    events += st("autoajuste", _autotune_tick, store, s, api, world, default=[])
    events += st("pujas resueltas", _check_bid_resolutions, store, world, default=[])

    repaid = st("devolver crédito", _delever, store, s, api, world, default=[])
    events += repaid
    if any("Devuelvo" in e for e in repaid):
        world = _world(api, s, trends=True)
    sold = st("ofertas", _resolve_offers, store, s, api, world, default=[])
    events += sold
    if sold:
        world = _world(api, s, trends=True)

    pruned = st("cancelar pujas", _prune_bids, store, api, world, default=[])
    events += pruned
    if pruned:
        world = _world(api, s, trends=True)

    siege_events, siege_reserve = st("bloqueo", _siege_tick, store, s, api, world, default=([], 0))
    events += siege_events
    bought, reserved = st("compras", _acquire, store, s, api, world, extra_reserved=siege_reserve, default=([], []))
    events += bought
    if bought:
        world = _world(api, s, trends=True)

    hours = _hours_to_deadline(world)
    if any(analysis.position_shortage(world.my_slots).values()) and hours is not None and hours <= s.lineup_lock_hours:
        debt = st("crédito", _emergency_debt_buy, store, s, api, world, team_plan)  # último recurso, ver docstring
        if debt:
            events.append(debt)
            world = _world(api, s, trends=True)

    events += st("en venta", _list_for_sale, store, api, world, default=[])
    shielded, shielded_player_id = st("blindaje", _auto_shield, store, s, api, world, default=(None, ""))
    if shielded:
        events.append(shielded)
    raised_clause = st("subir cláusula", _clause_raise_probe, store, s, api, world, skip_player_id=shielded_player_id)
    if raised_clause:
        events.append(raised_clause)
    lineup_msg = st("alineación", _apply_lineup, store, api, world)
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

    events += st("resumen semanal", _weekly_review, store, s, api, world, default=[])
    events += st("publicar datos", _publish_state, store, s, default=[])
    if errs and store.alert_is_new("step_errors:" + ",".join(sorted(e.split(":")[0] for e in errs)), ttl_hours=6):
        events.append("⚠️ Pasos con error en esta pasada (el resto se hizo): " + notify.esc("; ".join(errs))[:600])
    if events:
        st("enviar", notify.send_all, s, "🤖 <b>PILOTO AUTOMÁTICO</b>\n\n" + "\n\n".join(events), html=True)
    if st("parte", digest.due, store, s, default=False):
        st("enviar parte", notify.send_all, s, service.situational_briefing(world, s))
        digest.mark_sent(store)

    sniped = st("bloqueo (ejecución)", _siege_go, store, s, api, world, default=[]) + \
        st("al segundo", _timed_actions, store, api, world, reserved, default=[])
    if sniped:
        st("enviar", notify.send_all, s, "🤖 <b>PILOTO AUTOMÁTICO</b>\n\n" + "\n\n".join(sniped), html=True)
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
        import traceback
        store.log_error("pasada", traceback.format_exc())
        if _is_transient(exc):
            # Corte pasajero de LaLiga/Telegram/red: la siguiente pasada (15 min) lo reintenta.
            # No se marca la ejecución como fallida (evita correos de GitHub), pero queda registrado.
            from .storage import redact
            print(redact(f"[corte pasajero] {exc}"))
            return
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
    p = sub.add_parser("review", help="¿Estamos ganando dinero? Patrimonio y operaciones cerradas")
    p.add_argument("--since", default=PILOT_START, help="fecha AAAA-MM-DD desde la que contar las operaciones")
    p.add_argument("--cloud", action="store_true", help="usar los datos que ha publicado el bot en GitHub")
    p.set_defaults(func=cmd_review)
    p = sub.add_parser("tune", help="Qué ajustaría el bot ahora en sus propios parámetros (no guarda nada)")
    p.add_argument("--deep", action="store_true", help="incluye la recalibración semanal (≈250 peticiones)")
    p.add_argument("--cloud", action="store_true", help="usar los datos que ha publicado el bot en GitHub")
    p.set_defaults(func=cmd_tune)
    p = sub.add_parser("learn-rivals", help="Aprender de los rivales: qué compran, a qué prima y cómo les sale")
    p.add_argument("--since", help="solo compras desde esta fecha (AAAA-MM-DD)")
    p.set_defaults(func=cmd_rivals)
    p = sub.add_parser("offers", help="Distribución de las ofertas de la liga respecto al valor")
    p.add_argument("--cloud", action="store_true", help="usar los datos que ha publicado el bot en GitHub")
    p.set_defaults(func=cmd_offers)
    sub.add_parser("pull", help="Descarga el estado que ha publicado el bot (rama data) para analizarlo").set_defaults(func=cmd_pull)
    p = sub.add_parser("export", help="Escribe el estado local en data/export.json")
    p.add_argument("--publish", action="store_true", help="y lo sube a la rama data (requiere GITHUB_TOKEN)")
    p.set_defaults(func=cmd_export)
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
