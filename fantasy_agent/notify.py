"""Envío de notificaciones por Telegram (avisos, propuestas de puja/cláusula y confirmaciones)."""
from __future__ import annotations

from .config import Settings
from .http import request_json

TELEGRAM_CHUNK = 4000


def telegram_enabled(settings: Settings) -> bool:
    return bool(settings.telegram_token and settings.telegram_chat_id)


def any_enabled(settings: Settings) -> bool:
    return telegram_enabled(settings)


def _chunks(text: str, size: int) -> list[str]:
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > size:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks


def send_telegram(settings: Settings, text: str) -> None:
    if not telegram_enabled(settings):
        raise RuntimeError("Configura TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en el .env")
    url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
    for chunk in _chunks(text, TELEGRAM_CHUNK):
        request_json("POST", url, json_body={
            "chat_id": settings.telegram_chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        })


def get_telegram_updates(settings: Settings, offset: int | None = None) -> list[dict]:
    """Mensajes nuevos recibidos por el bot (para leer confirmaciones). Long-poll corto:
    no bloquea, solo devuelve lo que ya haya llegado desde `offset`."""
    if not telegram_enabled(settings):
        return []
    url = f"https://api.telegram.org/bot{settings.telegram_token}/getUpdates"
    params: dict[str, int] = {"timeout": 0}
    if offset is not None:
        params["offset"] = offset
    resp = request_json("GET", url, params=params)
    return resp.get("result", [])


def send_all(settings: Settings, text: str) -> None:
    if telegram_enabled(settings):
        send_telegram(settings, text)


def send_report(settings: Settings, sections: list[str], *, telegram: bool | None = None) -> None:
    """Manda cada especialidad (alineación, mercado, cláusulas...) como un mensaje aparte.

    Sin `telegram` explícito, usa lo que esté configurado en el .env (así lo llaman
    `watch`/`tick`); los comandos puntuales pasan el flag de CLI.
    """
    use_telegram = telegram_enabled(settings) if telegram is None else telegram
    for section in sections:
        if section.strip() and use_telegram:
            send_telegram(settings, section)
