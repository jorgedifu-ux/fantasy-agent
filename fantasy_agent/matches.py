"""Partidos de la jornada y quién tiene a quién: qué se ha jugado, qué falta y qué jugadores de cada mánager intervienen. La alineación de los rivales no es visible
(403 en la API), así que de ellos se muestra su PLANTILLA, no su once."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import models, notify, pts as pts_mod
from .panel import DAYS, clean_name, full_manager

DURATION = timedelta(minutes=115)
TEAM_NOISE = ("C.A. ", "R. ", "RCD ", "RC ", " CF", " FC", " UD", "Club ")


def team_label(name: str) -> str:
    for n in TEAM_NOISE:
        name = name.replace(n, "")
    return name.strip()


def _when(dt: datetime) -> str:
    d = dt.astimezone()
    return f"{DAYS[d.weekday()]} {d:%H:%M}"


def collect(world, api, now: datetime | None = None, store=None) -> dict | None:
    """Los partidos de la jornada en juego, con el estado de cada uno y los jugadores de cada mánager que participan (con sus puntos si ya jugaron)."""
    now = now or datetime.now(timezone.utc)
    try:
        wk = api.current_week() or {}
        cur = int(wk.get("weekNumber") or 0)
        cal = models.as_list(api.calendar(cur), "matches", "elements", "calendar")
        raw = {str(p["id"]): p for p in api.players()}
    except Exception:
        return None
    me_id = next((str(r.manager_id) for r in world.standing if r.team_id == world.my_team_id), "")
    managers = {str(r.manager_id): full_manager(r.manager_name, str(r.manager_id) == me_id) for r in world.standing}
    owner_by_team = {r.team_id: str(r.manager_id) for r in world.standing}
    owners: dict[str, str] = {}
    for sl in list(world.my_slots) + list(world.rival_slots):
        owners[sl.player.id] = owner_by_team.get(sl.owner_team_id, "")
    by_club: dict[str, list[dict]] = {}
    for pid, mid in owners.items():
        r = raw.get(pid)
        if not r or not mid:
            continue
        by_club.setdefault(str(r.get("teamId")), []).append({"pid": pid, "name": clean_name(r.get("nickname") or "?"), "mid": mid, "pts": None, "avg": r.get("averagePoints") or 0,
                                                            "list": next((x.get("points") for x in (r.get("weekPoints") or []) if x.get("weekNumber") == cur), None)})
    matches = []
    for m in cal:
        when = models.parse_dt(m.get("matchDate") or m.get("date"))
        lo, vi = str(m.get("localId")), str(m.get("visitorId"))
        if when is None:
            continue
        state = "jugado" if when + DURATION <= now else "en juego" if when <= now else "pendiente"
        score = f"{m.get('localScore')}–{m.get('visitorScore')}" if m.get("localScore") is not None and state != "pendiente" else None
        matches.append({"when": when, "state": state, "score": score, "local": world.team_names.get(lo, lo), "visitor": world.team_names.get(vi, vi),
                        "players": by_club.get(lo, []) + by_club.get(vi, [])})
    matches.sort(key=lambda x: x["when"])
    for m in matches:
        for p in m["players"]:
            p["pts"] = pts_mod.week_points(store, api, p["pid"], cur, list_value=p.get("list"), started=m["state"] != "pendiente")
    pending_by_manager: dict[str, list[dict]] = {}
    for m in matches:
        if m["state"] != "jugado":
            for p in m["players"]:
                pending_by_manager.setdefault(p["mid"], []).append({**p, "when": m["when"]})
    return {"week": cur, "matches": matches, "managers": managers, "me": me_id, "pending": pending_by_manager}


def _owner_bullets(m: dict, managers: dict[str, str], me: str) -> list[str]:
    """Una viñeta por mánager con sus jugadores de ese partido (y sus puntos si ya jugaron)."""
    out = []
    for mid in [me] + [x for x in managers if x != me]:
        ps = [p for p in m["players"] if p["mid"] == mid]
        if not ps:
            continue
        txt = ", ".join(notify.esc(p["name"]) + (f" <b>{p['pts']}</b>" if p["pts"] is not None else "") for p in sorted(ps, key=lambda x: -(x["avg"] or 0))[:5])
        out.append(f"• {notify.esc(managers[mid])}: {txt}")
    return out


def render(d: dict) -> str:
    """Título de cada bloque y, debajo, su desplegable: partidos (con una viñeta por mánager) y lo que le queda a cada uno."""
    done = [m for m in d["matches"] if m["state"] == "jugado"]
    live = [m for m in d["matches"] if m["state"] == "en juego"]
    todo = [m for m in d["matches"] if m["state"] == "pendiente"]
    lines = [f"🏟 <b>Partidos de la jornada {d['week']}</b>", f"<i>{len(done)} jugados · {len(live)} en juego · {len(todo)} por jugar</i>"]

    def block(title: str, ms: list[dict], icon: str) -> None:
        if not ms:
            return
        rows = []
        for m in ms:
            head = (f"{team_label(m['local'])} {m['score']} {team_label(m['visitor'])}" if m["score"] else f"{team_label(m['local'])} – {team_label(m['visitor'])}")
            when = f"{_when(m['when'])} · " if m["state"] != "jugado" else ""
            rows.append(f"<b>{icon} {when}{notify.esc(head)}</b>")
            rows += _owner_bullets(m, d["managers"], d["me"]) or ["<i>ningún jugador de la liga</i>"]
            rows.append("")
        lines.append(f"\n<b>{title}</b>")
        lines.append("<blockquote expandable>" + "\n".join(rows).rstrip() + "</blockquote>")

    block(f"🔴 En juego ({len(live)})", live, "🔴")
    block(f"⏳ Por jugar ({len(todo)})", todo, "⏳")
    block(f"✅ Jugados ({len(done)})", done, "✅")
    rows = []
    for mid, name in d["managers"].items():
        left = sorted(d["pending"].get(mid, []), key=lambda p: -(p["avg"] or 0))
        rows.append(f"• <b>{notify.esc(name)}</b> — {len(left)} por jugar")
        rows += [f"   – {notify.esc(p['name'])} ({DAYS[p['when'].astimezone().weekday()]} {p['when'].astimezone():%H:%M})" for p in left[:5]]
    lines.append("\n<b>🎯 Qué le queda a cada uno</b>")
    lines.append("<blockquote expandable>" + "\n".join(rows) + "</blockquote>")
    lines.append("<i>De los rivales se ve su plantilla, no su once: la alineación ajena no es visible.</i>")
    return "\n".join(lines)
