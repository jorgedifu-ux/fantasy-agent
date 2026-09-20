"""Línea de comandos: `python -m fantasy_agent <comando>`."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime

from . import analysis, auth, confirm, digest, notify, service
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


def _emergency_buy(store: Store, s, api: FantasyAPI, world) -> str | None:
    """Red de seguridad: si no puedes alinear 11 legales, ficha del mercado LIBRE (nunca
    clausulazos) sin pedirte confirmación — tope de precio y de operaciones por semana en
    .env (EMERGENCY_BUY_CAP_PCT, EMERGENCY_BUYS_PER_WEEK). Ver STRATEGY.md §punto 4."""
    shortage = analysis.position_shortage(world.my_slots)
    if not any(shortage.values()):
        return None
    if len(store.auto_buys_this_week()) >= s.emergency_buys_per_week:
        return None
    already = {b["player_id"] for b in store.auto_buys_this_week()}
    candidates = [
        o for o in analysis.emergency_candidates(world.my_slots, world.market, world.my_cash, s.emergency_buy_cap_pct)
        if o.item.player.id not in already
    ]
    if not candidates:
        return None
    pick = candidates[0]
    name = notify.esc(pick.item.player.name)
    cap = int(world.my_cash * s.emergency_buy_cap_pct) if world.my_cash else pick.item.price
    money = analysis.bid_amount(pick.item, pick.score, world.my_cash, cap_price=cap)
    try:
        api.bid(world.league_id, pick.item.market_id, money)
    except Exception as exc:
        return f"❌ Fichaje de emergencia fallido para <b>{name}</b>: {notify.esc(str(exc))}"
    store.record_auto_buy(pick.item.player.id, money)
    expires_at = pick.item.expires.timestamp() if pick.item.expires else None
    store.add_market_bid(pick.item.player.id, name, money, expires_at)
    return (
        f"🚨 <b>FICHAJE DE EMERGENCIA</b> (sin confirmar — plantilla incompleta)\n"
        f"Puja <b>enviada</b> (pendiente de resolverse) por <b>{name}</b> ({pick.item.player.position}), "
        f"{service.m(money)}\n"
        f"Motivo: {notify.esc('; '.join(pick.reasons))}\n"
        f"Te aviso en cuanto se sepa si la ganas."
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


def _sell_proposals(store: Store, s, world) -> None:
    """Recomendaciones de venta: dos motivos distintos, nunca en automático (a diferencia de
    los fichajes de emergencia, vender sí necesita siempre tu sí, ver STRATEGY.md).
    1) Aprovechar máximo: vender EN GANANCIA antes de que empiece a bajar.
    2) Cortar pérdidas: caída sostenida o lesión larga sin visos de recuperación — vender
       aunque sea perdiendo, porque esperar solo empeora las cosas."""
    mine_ids = {sl.player.id for sl in world.my_slots}
    for p, t in analysis.sell_high_candidates(world.trends, mine_ids)[:2]:
        if store.alert_is_new(f"sell_profit:{p.id}", ttl_hours=48):
            confirm.propose(
                s, store, "sell",
                {"league_id": world.league_id, "player_id": p.id, "sale_price": p.market_value, "player_name": p.name},
                f"Venta recomendada — {p.name}\n"
                f"En máximo ({t.d7:+.0f}% en 7 días, ya frenando) — va a empezar a bajar.\n"
                f"Vender ahora: {service.m(p.market_value)}",
                label="💰 APROVECHAR MÁXIMO",
            )
    for sl in analysis.cut_loss_candidates(world.my_slots, world.trends)[:2]:
        p = sl.player
        if store.alert_is_new(f"sell_loss:{p.id}", ttl_hours=72):
            confirm.propose(
                s, store, "sell",
                {"league_id": world.league_id, "player_id": p.id, "sale_price": p.market_value, "player_name": p.name},
                f"Venta recomendada (cortar pérdidas) — {p.name}\n"
                f"Estado: {p.status} · no parece que vaya a recuperarse pronto.\n"
                f"Mejor liquidar ya: {service.m(p.market_value)}",
                label="🩸 CORTAR PÉRDIDAS",
            )


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

    events: list[str] = []
    emergency = _emergency_buy(store, s, api, world)
    if emergency:
        events.append(emergency)
        world = _world(api, s, trends=True)  # recalcular: acabas de gastar, quiero que se note ya

    _, alerts = service.clauses_report(world, s)
    fresh = [a for a in alerts if store.alert_is_new(a.key)]
    actionable = [a for a in fresh if a.kind == "open_affordable"][:3]  # nunca más de 3 a la vez
    for a in actionable:
        ratio = a.slot.clause / a.slot.player.market_value if a.slot.player.market_value else 1.0
        confirm.propose(
            s, store, "clause",
            {
                "league_id": world.league_id, "player_id": a.slot.player.id, "amount": a.slot.clause,
                "player_name": a.slot.player.name,
            },
            f"Clausulazo — {a.slot.player.name} (de {a.slot.owner_name})\n"
            f"Cláusula: {service.m(a.slot.clause)} · Valor de mercado: {service.m(a.slot.player.market_value)}",
            label=analysis.clause_urgency_label(ratio, a.penalty),
        )

    recovered = _recovered_ids(store, [sl.player for sl in world.my_slots] + [i.player for i in world.market])
    for o in service.top_bid_candidates(world, s, recovered_ids=recovered):
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

    _sell_proposals(store, s, world)

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
