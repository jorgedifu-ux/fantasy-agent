"""Sacar el estado del bot de GitHub para poder analizarlo (y mejorarlo) con datos reales.

El bot guarda lo que aprende (ofertas vistas, resultado de las pujas, origen de cada compra,
patrimonio diario, propuestas de autoajuste...) en una base de datos que vive en la caché de
GitHub Actions, inaccesible desde fuera. Cada 6 horas se publica una copia en JSON en la rama
`data` del propio repositorio; `python3 -m fantasy_agent pull` la descarga en local.

Qué contiene: datos del juego derivados (ofertas, pujas, compras, saldo). NO contiene tokens,
contraseñas, ni el chat de Telegram. Como el repositorio es público, la rama también lo es:
`EXPORT_DATA=0` en el workflow lo desactiva.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.parse
from typing import Any

from .http import request_json, request_text
from .storage import Store

BRANCH = "data"
PATH = "state.json"
DEFAULT_REPO = "jorgedifu-ux/fantasy-agent"
API = "https://api.github.com"


def build_state(store: Store, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    state = store.export_state()
    state["meta"] = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "commit": os.environ.get("GITHUB_SHA", ""), **(meta or {})}
    return state


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def publish(state: dict[str, Any], *, token: str, repo: str) -> str:
    """Escribe `state.json` en la rama `data` (la crea desde `main` si no existe) con la API de
    contenidos de GitHub. Devuelve un texto breve del resultado. Lanza excepción si falla."""
    h = _headers(token)
    ref = f"{API}/repos/{repo}/git/ref/heads/{BRANCH}"
    try:
        request_json("GET", ref, headers=h)
    except Exception:
        main = request_json("GET", f"{API}/repos/{repo}/git/ref/heads/main", headers=h)
        request_json("POST", f"{API}/repos/{repo}/git/refs", headers=h,
                     json_body={"ref": f"refs/heads/{BRANCH}", "sha": main["object"]["sha"]})
    url = f"{API}/repos/{repo}/contents/{PATH}"
    sha = None
    try:
        sha = request_json("GET", f"{url}?{urllib.parse.urlencode({'ref': BRANCH})}", headers=h).get("sha")
    except Exception:
        pass  # el fichero aún no existe
    body = {
        "message": f"estado {state['meta']['generated_at']}",
        "content": base64.b64encode(json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode()).decode(),
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha
    request_json("PUT", url, headers=h, json_body=body)
    return f"publicado en la rama {BRANCH} ({len(body['content']) * 3 // 4 // 1024} KB)"


def fetch(repo: str = DEFAULT_REPO) -> dict[str, Any]:
    """Descarga el último estado publicado (repositorio público: no hace falta token)."""
    raw = request_text(f"https://raw.githubusercontent.com/{repo}/{BRANCH}/{PATH}?t={int(time.time())}")
    return json.loads(raw)
