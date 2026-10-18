"""Gráficas bajo demanda: se construye la configuración de Chart.js (con etiquetas de datos y tipografía grande para el móvil) y QuickChart.io (gratis, sin
clave) devuelve una imagen que Telegram descarga. Solo viajan números de la liga (patrimonios y puntos), nunca credenciales."""
from __future__ import annotations

import json

from .http import request_json

QUICKCHART = "https://quickchart.io/chart/create"
ME, RIVAL = "#2a78d6", "#eb6834"


def render_url(config: str, width: int = 900, height: int = 520) -> str:
    resp = request_json("POST", QUICKCHART, json_body={"chart": config, "width": width, "height": height, "backgroundColor": "white",
                                                         "version": "4", "format": "png", "devicePixelRatio": 2})
    url = (resp or {}).get("url")
    if not url:
        raise RuntimeError("QuickChart no devolvió imagen")
    return url


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def wealth_config(days: list[str], me: list[float], rival: list[float], rival_name: str, my_name: str) -> str:
    """Dos líneas gruesas con el último valor escrito al final y la diferencia de hoy en el título."""
    labels = [f"{d[8:10]}/{d[5:7]}" for d in days]
    gap = (rival[-1] or 0) - (me[-1] or 0)
    title = f"Patrimonio · diferencia hoy {gap:.0f}M"
    return f"""{{
 type:'line',
 data:{{labels:{_j(labels)},datasets:[
  {{label:{_j(rival_name)},data:{_j(rival)},borderColor:'{RIVAL}',backgroundColor:'{RIVAL}',borderWidth:5,pointRadius:0,tension:0.3}},
  {{label:{_j(my_name)},data:{_j(me)},borderColor:'{ME}',backgroundColor:'{ME}',borderWidth:5,pointRadius:0,tension:0.3,borderDash:[12,7]}}]}},
 options:{{
  layout:{{padding:{{right:60,top:6,left:6,bottom:4}}}},
  plugins:{{
   title:{{display:true,text:{_j(title)},font:{{size:22,weight:'bold'}},padding:{{bottom:14}}}},
   legend:{{position:'bottom',labels:{{font:{{size:18}},usePointStyle:true,padding:18}}}},
   datalabels:{{display:function(c){{return c.dataIndex===c.dataset.data.length-1}},align:'right',anchor:'end',offset:4,
     font:{{size:17,weight:'bold'}},formatter:function(v){{return Math.round(v)+'M'}},color:function(c){{return c.dataset.borderColor}}}}
  }},
  scales:{{
   x:{{grid:{{display:false}},ticks:{{font:{{size:15}},maxTicksLimit:7}}}},
   y:{{grid:{{color:'#e4e4e4'}},ticks:{{font:{{size:15}},callback:function(v){{return v+'M'}},maxTicksLimit:6}}}}
  }}
 }}
}}"""


def points_config(weeks: list[int], me_pts: list[int], rival_pts: list[int], rival_name: str, my_name: str, live_week: int | None = None) -> str:
    """Barras por jornada de cada uno, con el número encima; la jornada en juego, marcada."""
    labels = [f"J{w}" + (" (en juego)" if live_week == w else "") for w in weeks]
    title = f"Puntos por jornada · tú {sum(me_pts) - sum(rival_pts):+d} en total"
    return f"""{{
 type:'bar',
 data:{{labels:{_j(labels)},datasets:[
  {{label:{_j(rival_name)},data:{_j(rival_pts)},backgroundColor:'{RIVAL}',borderRadius:6}},
  {{label:{_j(my_name)},data:{_j(me_pts)},backgroundColor:'{ME}',borderRadius:6}}]}},
 options:{{
  layout:{{padding:{{top:26,left:6,right:6,bottom:4}}}},
  plugins:{{
   title:{{display:true,text:{_j(title)},font:{{size:22,weight:'bold'}},padding:{{bottom:14}}}},
   legend:{{position:'bottom',labels:{{font:{{size:18}},usePointStyle:true,padding:18}}}},
   datalabels:{{anchor:'end',align:'end',offset:-2,font:{{size:16,weight:'bold'}},color:'#333'}}
  }},
  scales:{{
   x:{{grid:{{display:false}},ticks:{{font:{{size:15}}}}}},
   y:{{beginAtZero:true,grid:{{color:'#e4e4e4'}},ticks:{{font:{{size:15}},maxTicksLimit:6}}}}
  }}
 }}
}}"""
