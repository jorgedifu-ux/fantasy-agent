"""Envío de notificaciones por Telegram (avisos, propuestas de puja/cláusula y confirmaciones)."""
from __future__ import annotations

from .config import Settings
from .http import request_json

TELEGRAM_CHUNK = 4000


def telegram_enabled(settings: Settings) -> bool:
    return bool(settings.telegram_token and settings.telegram_chat_id)


def any_enabled(settings: Settings) -> bool:
    return telegram_enabled(settings)


def esc(text: str) -> str:
    """Escapa texto dinámico (nombres de jugador/mánager) antes de meterlo en un mensaje con
    parse_mode HTML, para que un '&' o '<' sueltos no rompan el formato."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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


def send_telegram(
    settings: Settings, text: str, *, buttons: list[tuple[str, str]] | None = None, html: bool = False,
) -> int | None:
    """`buttons`: lista de (texto_botón, callback_data), p.ej. [("✅ Confirmar", "confirm:a1b2")].
    Se pone en el ÚLTIMO trozo si el mensaje se corta en varios (los botones van pegados al
    texto que los explica). `html=True`: interpreta `<b>`/`<i>`/`<code>` como formato en vez
    de texto literal — el llamador es responsable de escapar cualquier dato dinámico con
    `esc()` antes de meterlo en el mensaje (si no, un '&' o '<' sueltos rompen el envío).
    Devuelve el `message_id` del último trozo mandado (para poder editarlo/fijarlo luego)."""
    if not telegram_enabled(settings):
        raise RuntimeError("Configura TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en el .env")
    url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
    chunks = _chunks(text, TELEGRAM_CHUNK)
    message_id = None
    for i, chunk in enumerate(chunks):
        body = {
            "chat_id": settings.telegram_chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        }
        if html:
            body["parse_mode"] = "HTML"
        if buttons and i == len(chunks) - 1:
            body["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in buttons]]}
        resp = request_json("POST", url, json_body=body)
        message_id = (resp or {}).get("result", {}).get("message_id")
    return message_id


def edit_message(
    settings: Settings, message_id: int, text: str, *, buttons: list[tuple[str, str]] | None = None,
    html: bool = True,
) -> bool:
    """Edita un mensaje ya mandado (para un panel "vivo" que se actualiza en el sitio, como el
    Plan de equipo, en vez de mandar uno nuevo cada vez). Devuelve False si el mensaje ya no
    se puede editar (borrado, demasiado antiguo) — en ese caso el llamador debe mandar uno
    nuevo con `send_telegram` normal."""
    if not telegram_enabled(settings):
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_token}/editMessageText"
    body = {"chat_id": settings.telegram_chat_id, "message_id": message_id, "text": text[:TELEGRAM_CHUNK]}
    if html:
        body["parse_mode"] = "HTML"
    if buttons:
        body["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in buttons]]}
    try:
        request_json("POST", url, json_body=body)
        return True
    except Exception:
        return False


def pin_message(settings: Settings, message_id: int) -> None:
    if not telegram_enabled(settings):
        return
    url = f"https://api.telegram.org/bot{settings.telegram_token}/pinChatMessage"
    try:
        request_json("POST", url, json_body={
            "chat_id": settings.telegram_chat_id, "message_id": message_id, "disable_notification": True,
        })
    except Exception:
        pass  # fijar es un extra de comodidad, no crítico — si falla, seguimos sin más


def answer_callback(settings: Settings, callback_query_id: str, text: str = "") -> None:
    """Quita el "cargando..." del botón que se acaba de pulsar en Telegram."""
    if not telegram_enabled(settings):
        return
    url = f"https://api.telegram.org/bot{settings.telegram_token}/answerCallbackQuery"
    request_json("POST", url, json_body={"callback_query_id": callback_query_id, "text": text})


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


def send_all(
    settings: Settings, text: str, *, buttons: list[tuple[str, str]] | None = None, html: bool = False,
) -> int | None:
    if telegram_enabled(settings):
        return send_telegram(settings, text, buttons=buttons, html=html)
    return None


def send_report(settings: Settings, sections: list[str], *, telegram: bool | None = None) -> None:
    """Manda cada especialidad (alineación, mercado, cláusulas...) como un mensaje aparte.

    Sin `telegram` explícito, usa lo que esté configurado en el .env (así lo llaman
    `watch`/`tick`); los comandos puntuales pasan el flag de CLI.
    """
    use_telegram = telegram_enabled(settings) if telegram is None else telegram
    for section in sections:
        if section.strip() and use_telegram:
            send_telegram(settings, section)
