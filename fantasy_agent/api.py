"""Cliente de la API interna de LaLiga Fantasy.

Rutas documentadas por la comunidad para la temporada 26/27. Ojo con la inconsistencia
de la propia app: clasificación y plantillas cuelgan de /leagues/{id}/..., mercado de /league/{id}/...
Si algo cambia, usa `fantasy probe <ruta>` para ver el JSON crudo y ajusta este archivo.

Los métodos de escritura (puja, cláusula, venta, alineación) modifican el juego de verdad y
gastan dinero de forma irreversible en algunos casos. Nunca se llaman directamente desde el
motor de análisis: pasan por `confirm.py`, que exige tu confirmación explícita antes de
ejecutarlas (excepto la alineación, ver `confirm.py`). Sus rutas siguen el mismo patrón que
otros clientes de este backend, pero no se han probado aún en vivo — antes de fiarte del todo,
compara con `fantasy probe /v1/competition/1/teams/<teamId>/lineup` (o la ruta que corresponda)
la primera vez que uses cada una.
"""
from __future__ import annotations

import time
from typing import Any

from . import auth
from .config import Settings
from .http import request_json

BASE = "https://fantasy-api.llt-services.com/api"
COMP = "/v1/competition/1"


class FantasyAPI:
    def __init__(self, settings: Settings):
        self.s = settings
        self._last_call = 0.0
        self._cache: dict[str, Any] = {}

    # --- infraestructura -------------------------------------------------
    def get(self, path: str, *, authed: bool = True, params: dict | None = None, cache: bool = False) -> Any:
        key = f"{path}?{params}"
        if cache and key in self._cache:
            return self._cache[key]
        wait = self.s.request_delay_s - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)  # ritmo humano: no machacar la API
        headers = {"x-lang": "es", "x-app": "Fantasy"}
        if authed:
            headers["Authorization"] = f"Bearer {auth.bearer(self.s)}"
        data = request_json("GET", BASE + path, headers=headers, params=params)
        self._last_call = time.time()
        if cache:
            self._cache[key] = data
        return data

    # --- públicas ---------------------------------------------------------
    def players(self) -> list[dict]:
        return self.get(f"{COMP}/players", authed=False, cache=True)

    def player(self, player_id: str | int) -> dict:
        return self.get(f"{COMP}/player/{player_id}", authed=False, cache=True)

    def market_value_history(self, player_id: str | int) -> list[dict]:
        return self.get(f"{COMP}/player/{player_id}/market-value", authed=False, cache=True)

    def current_week(self) -> dict:
        return self.get(f"{COMP}/week/current", authed=False, cache=True)

    def calendar(self, week: int) -> Any:
        return self.get(f"{COMP}/calendar", authed=False, params={"weekNumber": week}, cache=True)

    # --- con sesión ---------------------------------------------------------
    def me(self) -> dict:
        return self.get("/v4/user/me", cache=True)

    def leagues(self) -> list[dict]:
        return self.get(f"{COMP}/leagues", cache=True)

    def standing(self, league_id: str) -> list[dict]:
        return self.get(f"{COMP}/leagues/{league_id}/standing", cache=True)

    def team(self, league_id: str, team_id: str) -> dict:
        return self.get(f"{COMP}/leagues/{league_id}/teams/{team_id}", cache=True)

    def market(self, league_id: str) -> list[dict]:
        return self.get(f"{COMP}/league/{league_id}/market", cache=True)

    def activity(self, league_id: str, index: int = 0) -> Any:
        return self.get(f"{COMP}/leagues/{league_id}/activity/{index}", cache=True)

    def lineup(self, team_id: str) -> dict:
        """GET de tu alineación actual. Úsala con `probe` para ver la forma exacta del JSON
        antes de fiarte de `update_lineup` en automático (ver aviso en la cabecera del módulo)."""
        return self.get(f"{COMP}/teams/{team_id}/lineup")

    def clear_cache(self) -> None:
        self._cache.clear()

    # --- escritura: solo se llaman desde confirm.py, nunca desde el análisis ---
    def _write(self, method: str, path: str, body: dict | None = None) -> Any:
        wait = self.s.request_delay_s - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)  # mismo ritmo humano que las lecturas
        headers = {"x-lang": "es", "x-app": "Fantasy", "Authorization": f"Bearer {auth.bearer(self.s)}"}
        data = request_json(method, BASE + path, headers=headers, json_body=body)
        self._last_call = time.time()
        self._cache.clear()  # el estado del juego acaba de cambiar
        return data

    def bid(self, league_id: str, market_id: str, money: int) -> Any:
        return self._write("POST", f"{COMP}/league/{league_id}/market/{market_id}/bid", {"money": money})

    def cancel_bid(self, league_id: str, market_id: str, bid_id: str) -> Any:
        return self._write("DELETE", f"{COMP}/league/{league_id}/market/{market_id}/bid/{bid_id}/cancel")

    def sell_player(self, league_id: str, player_id: str, sale_price: int) -> Any:
        return self._write("POST", f"{COMP}/league/{league_id}/market/sell",
                            {"playerId": player_id, "salePrice": sale_price})

    def accept_offer(self, league_id: str, market_id: str, offer_id: str, money: int) -> Any:
        """⚠️ Sin verificar en vivo todavía (no ha llegado ninguna oferta real que probar) —
        misma ruta que usan otros clientes de este backend. Compara con `probe` en cuanto
        `numberOfOffers` de un anuncio tuyo sea > 0."""
        return self._write("POST", f"{COMP}/league/{league_id}/market/{market_id}/offer/{offer_id}/accept",
                            {"offerMoney": money})

    def decline_offer(self, league_id: str, market_id: str, offer_id: str) -> Any:
        return self._write("POST", f"{COMP}/league/{league_id}/market/{market_id}/offer/{offer_id}/reject")

    def pay_buyout_clause(self, league_id: str, player_id: str, amount: int) -> Any:
        return self._write("POST", f"{COMP}/league/{league_id}/buyout/{player_id}/pay",
                            {"buyoutClauseToPay": amount})

    def check_shield(self, league_id: str, player_team_id: str) -> Any:
        """GET: si el jugador ya está blindado (null si no lo está)."""
        return self.get(f"{COMP}/league/{league_id}/player-team/{player_team_id}/check-shield")

    def shield_player(self, league_id: str, player_team_id: str) -> Any:
        """Blindaje: protege a uno de tus jugadores de que le claususlen. GRATIS, 1 vez por
        jornada, solo funciona sobre una cláusula que esté abierta ahora mismo. ⚠️ Sin
        verificar en vivo todavía — en la app real pasa por ver un anuncio (rewarded ad); no
        sabemos si el servidor exige esa parte o basta con esta llamada. Si falla, no pasa
        nada (no gasta dinero), solo avisa y prueba en la app la primera vez."""
        return self._write("PUT", f"{COMP}/league/{league_id}/shield/player",
                            {"playerId": player_team_id, "rewardedAdType": "Blindaje", "rewardedAd": 1})

    def increase_buyout_clause(self, league_id: str, player_team_id: str, new_clause: int) -> Any:
        """Sube tu propia cláusula pagando — alternativa de PAGO al blindaje (gratis). Preferir
        siempre blindaje si está disponible."""
        return self._write("POST", f"{COMP}/league/{league_id}/buyout/{player_team_id}/increase",
                            {"buyoutClause": new_clause})

    def update_lineup(self, team_id: str, lineup_data: dict) -> Any:
        """⚠️ Payload sin verificar en vivo todavía — ver aviso en la cabecera del módulo.
        No la llames en automático hasta comparar `lineup_data` con un `probe` real."""
        return self._write("PUT", f"{COMP}/teams/{team_id}/lineup", lineup_data)
