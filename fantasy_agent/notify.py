"""Envío de notificaciones por Telegram (avisos, propuestas de puja/cláusula y confirmaciones)."""
from __future__ import annotations

from .config import Settings
from .http import request_json

TELEGRAM_CHUNK = 4000
SENT_IDS: list[int] = []     # ids de lo mandado en esta pasada: `tidy` los apunta para borrarlos pasado un tiempo


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
        if message_id:
            SENT_IDS.append(int(message_id))
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


def send_photo(settings: Settings, photo_url: str, caption: str = "", *, buttons: list[tuple[str, str]] | None = None) -> int | None:
    """Manda una imagen por URL (Telegram la descarga). Devuelve el message_id."""
    if not telegram_enabled(settings):
        return None
    url = f"https://api.telegram.org/bot{settings.telegram_token}/sendPhoto"
    body = {"chat_id": settings.telegram_chat_id, "photo": photo_url, "caption": caption[:1000], "parse_mode": "HTML"}
    if buttons:
        body["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in buttons]]}
    resp = request_json("POST", url, json_body=body)
    message_id = (resp or {}).get("result", {}).get("message_id")
    if message_id:
        SENT_IDS.append(int(message_id))
    return message_id


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
    """Quita el "cargando..." del botón que se acaba de pulsar en Telegram. Puramente
    cosmético — si Telegram la rechaza (p.ej. "query is too old" cuando ha pasado tiempo
    desde que se pulsó, algo que descubrimos en vivo), NUNCA debe tumbar el resto del
    proceso: silenciarlo aquí es intencional, no un descuido."""
    if not telegram_enabled(settings):
        return
    url = f"https://api.telegram.org/bot{settings.telegram_token}/answerCallbackQuery"
    try:
        request_json("POST", url, json_body={"callback_query_id": callback_query_id, "text": text})
    except Exception:
        pass


def get_telegram_updates(settings: Settings, offset: int | None = None, wait: int = 0) -> list[dict]:
    """Mensajes nuevos recibidos por el bot. Con `wait=0` no bloquea (solo lo que ya haya llegado desde `offset`); con `wait>0` Telegram
    mantiene la petición abierta hasta que llegue algo o pasen esos segundos (así se contesta casi al instante mientras la pasada escucha)."""
    if not telegram_enabled(settings):
        return []
    url = f"https://api.telegram.org/bot{settings.telegram_token}/getUpdates"
    params: dict[str, int] = {"timeout": wait}
    if offset is not None:
        params["offset"] = offset
    resp = request_json("GET", url, params=params, timeout=wait + 20, retries=0 if wait else 2)
    return resp.get("result", [])


def delete_message(settings: Settings, message_id: int) -> bool:
    """Borra un mensaje del bot (Telegram solo deja si tiene menos de 48 h). True si ya no está."""
    if not telegram_enabled(settings):
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_token}/deleteMessage"
    try:
        request_json("POST", url, json_body={"chat_id": settings.telegram_chat_id, "message_id": message_id})
        return True
    except Exception as exc:
        text = str(exc)
        return "message to delete not found" in text or "can't be deleted" in text or "message can't be deleted" in text


def pinned_message_id(settings: Settings) -> int | None:
    """Id del mensaje fijado ahora mismo en el chat (el panel), preguntándoselo a Telegram."""
    if not telegram_enabled(settings):
        return None
    url = f"https://api.telegram.org/bot{settings.telegram_token}/getChat"
    try:
        resp = request_json("POST", url, json_body={"chat_id": settings.telegram_chat_id})
        return ((resp or {}).get("result") or {}).get("pinned_message", {}).get("message_id")
    except Exception:
        return None


def unpin_message(settings: Settings, message_id: int) -> None:
    if not telegram_enabled(settings):
        return
    url = f"https://api.telegram.org/bot{settings.telegram_token}/unpinChatMessage"
    try:
        request_json("POST", url, json_body={"chat_id": settings.telegram_chat_id, "message_id": message_id})
    except Exception:
        pass


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
