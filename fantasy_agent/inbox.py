"""Bandeja de avisos: lo urgente sale al momento; el resto se junta y sale en resúmenes a horas fijas.

Antes cada pasada (cada 15 min) mandaba su propio «PILOTO AUTOMÁTICO» con todo lo que hubiera pasado, más un parte cada ~90 min: muchos
mensajes que decían casi lo mismo. Ahora:
- **Urgente** (se manda ya): lo que impide jugar la jornada (sin once legal, saldo negativo), que te clausulen a un jugador, y los fallos al
  guardar la alineación. Todo lo demás es informativo.
- **Informativo**: va a la bandeja (`kv.inbox`) y sale agrupado en el resumen de las 9, 14, 19 y 22 h (hora de Madrid) si hay novedades, o cuando
  lo pides con `/resumen`.
"""
from __future__ import annotations

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


def _clean(text: str, limit: int = 260) -> str:
    one = re.sub(r"\s+", " ", text).strip()
    return one if len(one) <= limit else one[: limit - 1].rstrip() + "…"


def render_digest(items: list[dict], since: float | None = None, now: datetime | None = None) -> str:
    """Resumen agrupado, sin repetidos; de «Alineación» y «Permutas posibles» solo lo último."""
    now = now or datetime.now()
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
    head = f"📬 <b>Resumen</b> · {now:%a %d/%m %H:%M}"
    if since:
        head += f" · desde las {datetime.fromtimestamp(since):%H:%M}"
    lines = [head]
    for title, rows in list(groups.items()) + [("Otros", other)]:
        seen, uniq = set(), []
        for r in rows:
            c = _clean(r)
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        if uniq:
            lines.append(f"\n<b>{title}</b>")
            lines += [f"• {u}" for u in uniq[:8]]
            if len(uniq) > 8:
                lines.append(f"  … y {len(uniq) - 8} más")
    lines.append("\n<i>/misiones · /brecha · /porque nombre · /resumen · /ayuda</i>")
    return "\n".join(lines)


def flush_text(store: Store, now: datetime | None = None) -> str | None:
    """Texto del resumen con todo lo pendiente (y vacía la bandeja); None si no hay nada."""
    items = _load(store)
    if not items:
        return None
    now = now or datetime.now()
    text = render_digest(items, since=items[0]["t"], now=now)
    clear(store, now.timestamp())
    return text
