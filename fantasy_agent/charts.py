"""Gráficas bajo demanda: se construye la configuración de Chart.js y QuickChart.io (gratis, sin clave) devuelve una imagen que Telegram descarga.
Solo viajan números de la liga (patrimonios y puntos), nunca credenciales."""
from __future__ import annotations

from .http import request_json

QUICKCHART = "https://quickchart.io/chart/create"
COLORS = {"me": "#2a78d6", "rival": "#eb6834"}


def render_url(config: dict, width: int = 820, height: int = 440) -> str:
    resp = request_json("POST", QUICKCHART, json_body={"chart": config, "width": width, "height": height, "backgroundColor": "white",
                                                         "version": "4", "format": "png"})
    url = (resp or {}).get("url")
    if not url:
        raise RuntimeError("QuickChart no devolvió imagen")
    return url


def _line(label: str, data: list, color: str, dashed: bool = False) -> dict:
    ds = {"label": label, "data": data, "borderColor": color, "backgroundColor": color, "borderWidth": 3, "pointRadius": 0, "tension": 0.25}
    if dashed:
        ds["borderDash"] = [8, 5]
    return ds


def wealth_config(days: list[str], me: list[float], rival: list[float], rival_name: str, my_name: str) -> dict:
    labels = [f"{d[8:10]}/{d[5:7]}" for d in days]
    return {"type": "line", "data": {"labels": labels, "datasets": [_line(rival_name, rival, COLORS["rival"]), _line(my_name, me, COLORS["me"], True)]},
            "options": {"plugins": {"title": {"display": True, "text": f"Patrimonio (M€): {my_name} contra {rival_name}"}},
                        "scales": {"y": {"ticks": {"maxTicksLimit": 7}}, "x": {"ticks": {"maxTicksLimit": 9}}}}}


def gap_config(days: list[str], gap: list[float], rival_name: str) -> dict:
    labels = [f"{d[8:10]}/{d[5:7]}" for d in days]
    return {"type": "line", "data": {"labels": labels, "datasets": [dict(_line(f"Diferencia con {rival_name}", gap, "#6250d6"), fill=True,
                                                                          backgroundColor="rgba(98,80,214,0.12)")]},
            "options": {"plugins": {"title": {"display": True, "text": f"Diferencia de patrimonio con {rival_name} (M€)"}},
                        "scales": {"y": {"min": 0}, "x": {"ticks": {"maxTicksLimit": 9}}}}}


def points_config(weeks: list[int], me_cum: list[int], rival_cum: list[int], rival_name: str, my_name: str) -> dict:
    return {"type": "line", "data": {"labels": [f"J{w}" for w in weeks],
                                     "datasets": [_line(rival_name, rival_cum, COLORS["rival"]), _line(my_name, me_cum, COLORS["me"], True)]},
            "options": {"plugins": {"title": {"display": True, "text": "Puntos acumulados por jornada"}}}}
