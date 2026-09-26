# Contexto para Claude Code

Agente de análisis para LaLiga Fantasy. Python 3.10+, **solo librería estándar**.

## Reglas del proyecto
- **Piloto automático, sin confirmaciones** (decisión explícita del usuario, 26/09/2026: "no
  voy a usar el fantasy apenas"). Pujas, cláusulas, ventas, ofertas, alineación y blindaje se
  ejecutan solos en `cli._watch_once`. Las DECISIONES viven en `autopilot.py` (puro,
  testeable); `cli.py` solo ejecuta y avisa. Los límites son económicos, nunca de nº de
  operaciones: no gastar más que saldo − colchón − pujas vivas − cláusulas reservadas (nunca
  en negativo), cláusula ≤1.2x valor, sobrepuja ≤+20%, no romper el once a <48h de la jornada.
  Cualquier escritura nueva: verifícala releyendo la API (la API puede responder 200 sin
  aplicar nada, visto con el blindaje) y prueba antes con `tick --dry-run`.
  `confirm.py` queda solo para responder a botones antiguos.
- La API de LaLiga Fantasy NO es pública ni documentada. Rutas y campos vienen de
  ingeniería inversa de la comunidad y pueden cambiar. Antes de tocar `models.py`,
  mira el JSON real con `python -m fantasy_agent probe <ruta>`.
- Mantener un ritmo de peticiones moderado (`REQUEST_DELAY_S`); no paralelizar contra la API.
- Nunca imprimir ni commitear `data/tokens.json` ni `.env`.

## Reglas del juego que el código ya modela
- **Solo son pujables los anuncios con `seller == "LaLiga"`.** Lo que "vende" otro entrenador
  de la liga privada no es pujable entre nosotros: a esos solo se llega pagando su cláusula.
- **Cláusula "lógica"** = precio de cláusula ≤ ~1.2x el valor de mercado real (si no, aunque
  sea una estrella, no compensa — ver `analysis.clause_alerts`, `max_ratio`).
- **Blindaje**: un jugador puede estar `isShielded` con `shieldedEndDate` — mientras dure, su
  cláusula NO es pagable aunque `buyoutClauseLockedEndTime` ya haya pasado. Ver `SquadSlot.clause_open`.
- **Congelación de jornada**: la liga bloquea TODAS las cláusulas desde 24h antes del primer
  partido de la jornada hasta que arranca ese partido. Ver `service.clause_freeze_window`.
- **Horizonte de inversión**: comprar (puja o cláusula) blinda al jugador 14 días — las
  proyecciones de reventa (`analysis.project_value`) usan ese horizonte, no unos pocos días.
- **TOP de liga** (`service.league_top_ids`, top 3 por posición en puntos totales de TODA
  LaLiga): son fichajes prioritarios, no oportunidades de inversión — se excluyen de
  `investment_report` y aparecen siempre en `market_report` aunque su score sea bajo.

## Mapa
- `auth.py`     login Azure B2C (PKCE) y refresh de tokens
- `api.py`      rutas de la API (lectura y escritura)
- `models.py`   normalización defensiva del JSON (claves alternativas por campo)
- `autopilot.py` decisiones autónomas (puro, testeable): cartera de fichajes/cláusulas por puntos
  que suman al once, ofertas (aceptar/rechazar/esperar), venta antes de que acabe la protección,
  cuerpo de la alineación
- `analysis.py` tendencias, puntuación de oportunidades (once vs inversión), alarmas de cláusula (puro, testeable)
- `lineup.py`   mejor once legal por puntos esperados
- `attendance.py` estima % de titularidad por histórico de jornadas jugadas (gratis, sin APIs externas)
- `service.py`  construye el estado de la liga (incl. próximos partidos vía `calendar`) y los informes de texto;
  `report_sections()` devuelve un mensaje por especialidad (no un solo tocho)
- `notify.py`   envío y lectura de Telegram (vía `http.request_json`, sin dependencias);
  `watch`/`tick` mandan si hay credenciales en `.env`, los comandos puntuales solo con
  `--telegram` explícito. `get_telegram_updates` (long-poll corto) lee las confirmaciones.
- `confirm.py`  antigua cola de "Confirmar/Cancelar": ya no se crean propuestas; solo responde a botones viejos
- `cli.py`      comandos, bucle `watch`, `tick` (una pasada del piloto automático) y `tick --dry-run`
  (simulación: lee todo de verdad, no escribe nada en la API, Telegram ni la base de datos)
- `.github/workflows/watch.yml` ejecuta `tick` en GitHub Actions (repo público, estado en `actions/cache`);
  GitHub no garantiza la hora de los cron — ver ESTADO.md "Cron fiable"
- `tests/`      `python -m unittest discover -s tests -v` (sin red, API falsa)

## Primeros pasos tras el login real
1. `probe /v1/competition/1/leagues`, `probe /v1/competition/1/leagues/<id>/standing`,
   `probe /v1/competition/1/league/<id>/market` y `probe /v1/competition/1/leagues/<id>/teams/<teamId>`.
2. Comparar con las claves de `models.py` y ajustar las que no coincidan.
3. Actualizar los fixtures de `tests/test_offline.py` con la forma real.
