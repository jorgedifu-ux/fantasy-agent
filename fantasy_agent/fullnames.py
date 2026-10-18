"""Nombre completo de los jugadores («Dávid Hancko», no «Hancko») para lo que se muestra en Telegram. La API de la lista solo trae el apodo; el nombre
entero está en la ficha de cada jugador, así que se pide una vez y se guarda (`kv.full_names`)."""
from __future__ import annotations

import json

from .storage import Store

KEY = "full_names"


def load(store: Store) -> dict[str, str]:
    return json.loads(store.get(KEY) or "{}")


def ensure(store: Store, api, ids, budget: int = 24) -> dict[str, str]:
    """Devuelve id -> nombre completo, pidiendo a la API los que falten (como mucho `budget` por vez, para no alargar la pasada)."""
    names = load(store)
    missing = [str(i) for i in ids if str(i) not in names][:budget]
    if missing:
        for pid in missing:
            try:
                full = (api.player(pid) or {}).get("name")
            except Exception:
                full = None
            if full:
                names[pid] = full
        store.set(KEY, json.dumps(names, ensure_ascii=False))
    return names
