"""Bandeja de avisos: lo urgente sale al momento; el resto se junta y sale en resúmenes a horas fijas.

Antes cada pasada (cada 15 min) mandaba su propio «PILOTO AUTOMÁTICO» con todo lo que hubiera pasado, más un parte cada ~90 min: muchos
mensajes que decían casi lo mismo. Ahora:
- **Urgente** (se manda ya): lo que impide jugar la jornada (sin once legal, saldo negativo), que te clausulen a un jugador, y los fallos al
  guardar la alineación. Todo lo demás es informativo.
- **Informativo**: va a la bandeja (`kv.inbox`) y sale agrupado en el resumen de las 9, 14, 19 y 22 h (hora de Madrid) si hay novedades, o cuando
  lo pides con `/resumen`.
"""
from __future__ import annotations

import html
import json
import re
import time
from datetime import datetime, timedelta

from .storage import Store

DIGEST_HOURS = (9, 14, 19, 22)
URGENT_PREFIXES = ("🔴", "🚨")
URGENT_CONTAINS = ("No he podido guardar la alineación",)
DROP_PREFIXES = ("🏷️ En venta",)          # «todos tus jugadores en venta»: siempre es verdad, no informa de nada
INBOX_MAX = 120

# (prefijos, título del grupo), en el orden en que salen en el resumen
GROUPS = (
    (("💰", "💳"), "Ventas"),
    (("🛒", "✅", "📨", "🎯"), "Fichajes y bloqueo"),
    (("🛡️", "🙅"), "Protección y ofertas"),
    (("🔁",), "Permutas posibles"),
    (("🧩",), "Alineación"),
    (("❌", "🚫", "⚠️"), "Fallos y pujas perdidas"),
    (("📅", "📊", "🔧", "🧪", "❎"), "Calendario y ajustes"),
)


def is_urgent(text: str) -> bool:
    t = text.lstrip()
    return t.startswith(URGENT_PREFIXES) or any(s in t for s in URGENT_CONTAINS)


def split(events: list[str]) -> tuple[list[str], list[str]]:
    """(urgentes, informativos); lo que no informa se descarta."""
    urgent, info = [], []
    for e in events:
        if not e or e.lstrip().startswith(DROP_PREFIXES):
            continue
        (urgent if is_urgent(e) else info).append(e)
    return urgent, info


def _load(store: Store) -> list[dict]:
    return json.loads(store.get("inbox") or "[]")


def add(store: Store, items: list[str], now: float | None = None) -> None:
    if not items:
        return
    box = _load(store)
    t = now or time.time()
    for text in items:
        if box and box[-1]["text"] == text:
            continue
        box.append({"t": round(t), "text": text})
    store.set("inbox", json.dumps(box[-INBOX_MAX:], ensure_ascii=False))


def pending(store: Store) -> list[dict]:
    return _load(store)


def clear(store: Store, now: float | None = None) -> None:
    store.set("inbox", "[]")
    store.set("inbox_last_digest", str(now or time.time()))


def last_slot(now: datetime) -> datetime:
    """El último resumen programado que ya debería haber salido (hoy o, si aún no ha llegado el de las 9, el de las 22 de ayer)."""
    today = [now.replace(hour=h, minute=0, second=0, microsecond=0) for h in DIGEST_HOURS]
    passed = [d for d in today if d <= now]
    return passed[-1] if passed else now.replace(hour=DIGEST_HOURS[-1], minute=0, second=0, microsecond=0) - timedelta(days=1)


def digest_due(store: Store, now: datetime) -> bool:
    if not _load(store):
        return False
    last = float(store.get("inbox_last_digest") or 0)
    return last < last_slot(now).timestamp()


NOUNS = {"Ventas": "venta(s)", "Fichajes y bloqueo": "fichaje(s)", "Protección y ofertas": "protección(es)", "Permutas posibles": "permuta(s)",
         "Alineación": "alineación", "Fallos y pujas perdidas": "fallo(s)/puja(s) perdida(s)", "Calendario y ajustes": "aviso(s)", "Otros": "otro(s)"}
ICONS = {"Ventas": "💰", "Fichajes y bloqueo": "🛒", "Protección y ofertas": "🛡️", "Permutas posibles": "🔁", "Alineación": "🧩",
         "Fallos y pujas perdidas": "❌", "Calendario y ajustes": "📅", "Otros": "•"}
DAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
MAX_CHARS = 3600        # Telegram corta a 4096: se recorta el detalle antes que dejar un mensaje roto


def _label(text: str, limit: int = 78) -> str:
    """Una línea corta y legible en el móvil: sin etiquetas, sin el «por qué» (lo que va detrás de « — ») ni el «(valor ...)»."""
    plain = html.unescape(re.sub(r"<[^>]+>", "", text))
    plain = plain.split(" — ")[0]
    plain = re.sub(r"\s*\((?:valor|salida)[^)]*\)", "", plain)
    plain = re.sub(r"^[^\w¿¡(]+", "", plain)            # el emoji de delante sobra: ya está en el título del grupo
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) > limit:
        plain = plain[: limit - 1].rsplit(" ", 1)[0] + "…"
    return html.escape(plain, quote=False)


def _detail(text: str) -> str:
    """El texto completo (con su motivo), en varias líneas cortas en vez de un párrafo pegado."""
    body = re.sub(r"[ \t]+", " ", text).strip()
    body = body.replace(" — ", "\n↳ ")
    return body


def _group(items: list[dict]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {title: [] for _, title in GROUPS}
    other: list[str] = []
    for it in items:
        text = it["text"]
        for prefixes, title in GROUPS:
            if text.lstrip().startswith(prefixes):
                groups[title].append(text)
                break
        else:
            other.append(text)
    for title in ("Alineación", "Permutas posibles"):
        groups[title] = groups[title][-1:]
    groups["Otros"] = other
    return {k: v for k, v in groups.items() if v}


def render_digest(items: list[dict], since: float | None = None, now: datetime | None = None) -> str:
    """Resumen pensado para el móvil: arriba una línea con los totales; luego cada grupo con sus etiquetas cortas y, plegado
    (`<blockquote expandable>`, se despliega con un toque), el detalle con el porqué. Sin repetidos."""
    now = now or datetime.now()
    groups = _group(items)
    counts = " · ".join(f"{ICONS[t]} {len(v)} {NOUNS[t]}" for t, v in groups.items())
    head = f"📬 <b>Resumen</b> · {DAYS[now.weekday()]} {now:%d/%m %H:%M}" + (f"\n<i>desde las {datetime.fromtimestamp(since):%H:%M}</i>" if since else "")
    blocks = []
    for title, rows in groups.items():
        uniq, seen = [], set()
        for r in rows:
            k = _label(r)
            if k not in seen:
                seen.add(k)
                uniq.append(r)
        shown = uniq[-8:]
        lines = [f"<b>{ICONS[title]} {title}</b>"] + [f"• {_label(r)}" for r in shown]
        if len(uniq) > len(shown):
            lines.append(f"  … y {len(uniq) - len(shown)} más antes")
        details = [_detail(r) for r in shown if " — " in r or len(re.sub(r"<[^>]+>", "", r)) > len(_label(r)) + 12]
        blocks.append((lines, details))
    footer = "\n<i>Toca ▾ para ver el porqué · /misiones /brecha /porque nombre</i>"

    def build(with_details: bool) -> str:
        parts = [head, f"<i>{counts}</i>"]
        for lines, details in blocks:
            parts.append("\n".join(lines))
            if with_details and details:
                parts.append("<blockquote expandable>" + "\n\n".join(details) + "</blockquote>")
        return "\n\n".join(parts) + footer

    text = build(True)
    return text if len(text) <= MAX_CHARS else build(False)


def render_urgent(events: list[str]) -> str:
    """Aviso urgente: título corto y, plegado, el detalle."""
    parts = ["🔴 <b>URGENTE</b>"]
    for e in events:
        parts.append(f"<b>{_label(e, 110)}</b>")
        d = _detail(e)
        if len(re.sub(r"<[^>]+>", "", d)) > len(_label(e, 110)) + 5:
            parts.append("<blockquote expandable>" + d + "</blockquote>")
    return "\n\n".join(parts)[:MAX_CHARS]


def flush_text(store: Store, now: datetime | None = None) -> str | None:
    """Texto del resumen con todo lo pendiente (y vacía la bandeja); None si no hay nada."""
    items = _load(store)
    if not items:
        return None
    now = now or datetime.now()
    text = render_digest(items, since=items[0]["t"], now=now)
    clear(store, now.timestamp())
    return text
