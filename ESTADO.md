# Estado del proyecto — fantasy-agent

Documento de contexto para retomar esto en cualquier momento, aunque se pierda la
conversación con Claude. Última actualización: **26/09/2026**.

## Qué es esto

Un **piloto automático** para tu equipo de LaLiga Fantasy (liga "Liga Fantasía", id
`018221573`, equipo "The Iberian One", id `39057665`): ficha, clausula, vende, acepta y
rechaza ofertas y monta la alineación **sin pedirte confirmación**. Corre solo en GitHub
Actions, sin coste (repo público, Python puro, sin tokens de Claude) y te cuenta por
Telegram lo que ha hecho. Repo: `github.com/jorgedifu-ux/fantasy-agent`.

**No necesita a Claude para funcionar.** Solo haría falta si LaLiga cambia su API o si
quieres cambiar la estrategia.

**Regla de oro**: no tener 11 alineados o tener saldo negativo cuando arranca la jornada es
**jornada entera a cero puntos**. Todo el diseño gira en torno a evitarlo.

## Cómo hablar con él

- **Telegram**: bot "Mi Fantasy Bot" (`@Vk_fantasia_bot`). Un único mensaje "🤖 PILOTO
  AUTOMÁTICO" por pasada con todo lo hecho (nada si no ha pasado nada), más un parte de
  situación corto cada ~90 min (silencio de 23h a 7h).
- **Terminal** (en esta carpeta): `python3 -m fantasy_agent <comando>`:
  - `tick --dry-run` — **"¿qué harías ahora?"**: lee todo de verdad y lo imprime, sin escribir
    nada en la API, Telegram ni la base de datos. Úsalo antes de cambiar reglas.
  - `tick` — una pasada real (lo mismo que hace GitHub).
  - `plan --refresh --telegram`, `lineup`, `market`, `standing`... — informes.
- **El Plan de equipo**: mensaje FIJADO en Telegram, se regenera 1 vez por semana.

## Qué hace solo (todo sin confirmación)

Los límites son **económicos**, no de número de operaciones (quitados los "2 al día").

| Acción | Regla |
|---|---|
| Fichar (puja) y clausular | Cartera en `autopilot.plan_acquisitions`: elige lo que más **puntos por jornada suma a tu once** por recurso gastado (dinero Y plaza de plantilla, para no llenarla de baratos flojos). Completar el once va siempre primero. Solo cláusulas "lógicas" (≤1,2× valor). Sobrepuja +5% a +20% según cuánto mejora el once y si hay competencia |
| Saldo | Nunca gasta más que saldo − 5% de colchón − pujas vivas − dinero reservado para cláusulas que se liberan en <24h. Nunca puede quedar en negativo |
| Cláusula que se libera pronto | Reserva su dinero; si se libera dentro de la misma pasada (≤25 min), espera al segundo exacto y paga |
| Líder / venganza | Clausular al líder o a quien te acaba de clausular se puede, pero con menos prioridad (×0,6) |
| Poner a la venta | **Todos tus jugadores siempre en venta** (a 1,1× su valor): así la liga manda una oferta diaria por cada uno. Estar en venta no obliga a vender |
| Ofertas de la liga | Acepta desde **1,05× el valor**; 0,97× si está en caída/lesionado; **1,25× si es clave** (quitarlo baja el once ≥3 pts/jornada). Nunca si te deja sin 11 a <48h de la jornada |
| Venta antes de perder la protección | Si la cláusula de un jugador tuyo es atractiva (≤1,2× valor), empieza a intentar venderlo **3 días antes** de que acabe su protección: exige 1,03× a 3 días y baja hasta 0,98× el último día (+7% si es clave) |
| Ofertas de rivales | Se rechazan, salvo que paguen ≥1,3× el valor |
| Alineación | El mejor once por puntos esperados × probabilidad de titularidad; se guarda y se **verifica releyéndola**. No se toca con la jornada en juego |
| Blindaje | Se intenta, pero **la API no lo aplica** (en la app requiere ver un anuncio): el bot te avisa para que lo hagas tú si quieres |
| Fichaje a crédito | Último recurso a <24h de la jornada con plantilla incompleta (tope 20% del valor) |
| Te clausulan a alguien | Te avisa (compara la plantilla entre pasadas) |

Todas las cifras están como constantes al principio de `fantasy_agent/autopilot.py`.

## Verificado en vivo (26/09/2026)

- **Leer ofertas**: `GET /league/{liga}/playerTeam/{playerTeamId}/offer` → `{id, money, status,
  isFromMarket, expirationDate}`. `isFromMarket: true` = oferta de la liga. (La ruta la sacamos
  del proyecto de la comunidad LaLiga-Fantasy-Builder.)
- **Aceptar oferta**: `POST /league/{liga}/market/{marketId}/offer/{offerId}/accept` con
  `{"offerMoney": importe}` → venta inmediata (Sangante 6,62M e Iván Martín 7,36M).
- **Alineación**: `PUT /teams/{equipo}/lineup` con `{"goalkeeper": id, "defender": [...],
  "midfield": [...], "striker": [...], "tactical_formation": [d, m, f]}` (ids = `playerTeamId`;
  ojo, `tactical_formation` en snake_case: la variante camelCase no funcionó).
- **Puja**: el mercado devuelve tu puja en `bid: {id, money, status}` de cada anuncio.
- **Cláusula** (`/buyout/{playerTeamId}/pay`) y **poner a la venta** (`/market/sell`).
- **`/activity`**: lista plana `{activityTypeId, user1Id, user2Id, playerMasterId, amount,
  createdAt}`; 1 = cláusula (user1 paga, user2 la sufre), 33 = venta, 31 = puja ganada,
  4 = puesto a la venta. user1Id/user2Id son manager_id.
- **Mercado**: se resuelve cada día a las ~20:53 (pujas y ofertas nuevas).
- **Blindaje**: `PUT /shield/player` responde bien pero no blinda; `check-shield` → 400
  "Player team shield limit reached".

## Sin probar todavía

- **Rechazar una oferta** (`.../offer/{id}/reject`): ruta de la comunidad, aún no ha llegado
  ninguna oferta de un rival.
- **Subir tu cláusula** (`/buyout/{id}/increase`): nunca se ha dado el caso.
- Fase económica→competitiva y bonus local/visitante (`STRATEGY.md`): documentado, sin implementar.

## Cron fiable (recomendado)

GitHub **no respeta** la frecuencia de los cron gratuitos: con `*/30` se ejecutaba cada 3-5
horas. El workflow ya lo intenta 4 veces por hora, pero para puntualidad real (ofertas, el
cierre de las 20:53, cláusulas que se liberan) lo fiable es dispararlo desde fuera, gratis:

1. En GitHub (tu cuenta personal) → Settings → Developer settings → Fine-grained tokens →
   nuevo token **solo para el repo fantasy-agent** con permiso **Actions: Read and write**.
2. En [cron-job.org](https://cron-job.org) (gratis) → nuevo cron cada 15 min:
   - URL: `https://api.github.com/repos/jorgedifu-ux/fantasy-agent/actions/workflows/watch.yml/dispatches`
   - Método POST, cuerpo `{"ref":"main"}`
   - Cabeceras: `Authorization: Bearer <tu token>`, `Accept: application/vnd.github+json`
3. Hazlo tú: el token no debe pasar por ninguna conversación ni fichero del repo.

## Decisiones y políticas acordadas contigo

- **Autonomía total** (26/09): "no voy a usar el fantasy apenas" — nada pide confirmación.
- **Ir a por jugadores buenos, no ser conservador**: colchón bajado del 20% al 5%.
- **Vender antes de que acabe la protección** de un jugador (idea tuya, 26/09), empezando 3
  días antes para tener varias ofertas donde elegir.
- **Ofertas de rivales**: casi nunca convienen → rechazar.
- **Gemini u otra IA gratuita**: descartado por ahora — las decisiones son cálculos sobre datos
  de la API y una regla fija las hace mejor y de forma predecible. Revisar solo si se ve que
  ficha a gente que las noticias ya daban por lesionada.
- **Coste**: cero en el día a día (Python puro en GitHub Actions).

## Lecciones

- **Hacer `git push` después de cada tanda de commits** (22/09: 9 commits sin subir y la nube
  corría código viejo en silencio).
- **La API puede responder 200 sin hacer nada** (visto con el blindaje): toda escritura
  nueva se verifica releyendo el estado.

## Próximos pasos

1. Montar el cron fiable (arriba) — lo tienes que hacer tú, son 5 minutos.
2. Revisar el primer rechazo real de una oferta de rival y la primera subida de cláusula.
3. Estimar el saldo de los rivales a partir de `/activity` para priorizar clausulazos donde no
   puedan reponerse.

## Dónde está todo

- `fantasy_agent/autopilot.py` — **las reglas de decisión** (puro, testeable).
- `fantasy_agent/cli.py` — ejecuta: `_watch_once` es el ciclo completo.
- `service.py`/`models.py`/`api.py` (datos y escritura), `plan.py` (el Plan), `lineup.py` (once).
- `STRATEGY.md` — razonamiento estratégico. `CLAUDE.md` — normas de desarrollo.
- `tests/` — sin red (`python3 -m unittest discover -s tests -v`).
- `.env` — tus credenciales (nunca se sube a git).
