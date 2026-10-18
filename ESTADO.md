# Estado del proyecto — fantasy-agent

Documento de contexto para retomar esto en cualquier momento, aunque se pierda la
conversación con Claude. Última actualización: **04/10/2026**.

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

- **Telegram** (rediseñado el 18/10/2026): bot "Mi Fantasy Bot" (`@Vk_fantasia_bot`).
  - **Urgente, al momento** (🔴): lo que impide jugar la jornada (sin once, saldo negativo), que te clausulen a un jugador, fallos al guardar la alineación.
  - **Resumen agrupado** a las 9, 14, 19 y 22 h (solo si hay novedades) o con `/resumen`; el resto de avisos se acumula en la bandeja (`kv.inbox`), sin repetidos.
  - **Panel de misiones**: UN mensaje fijado que se edita en el sitio (como mucho cada 30 min y solo si cambia): jornada y once, caja, pujas en curso, jugadores que se abren, bloqueo al líder, brecha, parón.
  - **Consultas** (se contestan en la pasada siguiente, ≤15 min): `/misiones`, `/resumen`, `/brecha [aleix|pep]` (texto + 3 gráficas de QuickChart.io), `/jornada`, `/plantilla`, `/porque <jugador>` (lee `kv.decisions`), `/ayuda`. Solo hace caso a tu chat.
  - **Respuestas casi al instante**: tras cada pasada el mismo job se queda escuchando Telegram (4 min, o 11 si le has hablado en los últimos 45 min; nunca más de 13 min desde que empezó) y contesta en cuanto escribes (long-poll). Es el mismo job, no uno aparte, porque dos jobs con la misma
    caché de estado se pisarían al guardarla. Si escribes en frío puede tardar hasta 15 min en la primera respuesta.
  - **Chat ordenado**: lo único que se queda es el panel fijado; el resto de lo que manda el bot se borra a las 24 h y tus órdenes ya contestadas a la hora (`tidy.py`; Telegram solo deja borrar lo que tenga menos de 48 h). El plan semanal ya no se manda ni se fija: `/plan`.
    Si borras todo el chat, escribe `/misiones` y el panel se vuelve a crear y fijar.
  - Un corte pasajero de Telegram no avisa, y si falla el envío el parte se guarda y sale en la pasada siguiente (`kv.outbox`).
  - Parón: aviso 48 h antes, uno al empezar y una línea en el panel mientras dura.
  - Patrimonio de los cuatro: histórico sembrado hasta el 18/10 (`seed_patrimonio.json`, ±10M) y una foto diaria desde entonces (`kv.wealth_league`).
- **Terminal** (en esta carpeta): `python3 -m fantasy_agent <comando>`:
  - `learn-rivals` — cómo opera cada mánager (prima, tendencia previa, resultado a 14 días)
  - `tick --dry-run` — **"¿qué harías ahora?"**: lee todo de verdad y lo imprime, sin escribir
    nada en la API, Telegram ni la base de datos. Úsalo antes de cambiar reglas.
  - `tick` — una pasada real (lo mismo que hace GitHub).
  - `plan --refresh --telegram`, `lineup`, `market`, `standing`... — informes.
- **El Plan de equipo**: mensaje FIJADO en Telegram, se regenera 1 vez por semana.

## Qué hace solo (todo sin confirmación)

Los límites son **económicos**, no de número de operaciones (quitados los "2 al día").

| Acción | Regla |
|---|---|
| Fichar (puja) y clausular | Cartera en `autopilot.plan_acquisitions`: elige lo que más **puntos por jornada suma a tu once** por recurso gastado (dinero Y plaza de plantilla, para no llenarla de baratos flojos). Completar el once va siempre primero. Solo cláusulas "lógicas" (≤1,2× valor) |
| Cuánto pujar | **+3%** sobre el precio de salida (+6% si mejora el once ≥3 pts). Solo si ya hay otra puja compitiendo, sube a lo que suelen pagar los rivales (mediana de sus pujas ganadas, recalculada a diario). **Techo +12%** (antes +20%: se pagó Soria un 18% sobre su valor y Gueye un 15%, ~15M perdidos al instante) |
| No fichar lo que cae | Se descarta a quien ha caído ≥3% en 3 días o ≥6% en 7 (Gueye cayó un 9,5% en una semana). Excepción: si falta un jugador en esa posición para completar el once |
| No vender con pérdida | Salvo lesión o caída fuerte, **nunca se vende por debajo de lo pagado**, tampoco por riesgo de cláusula (decisión tuya 4/10: mejor que te paguen la cláusula) |
| Inversión (comprar para revender) | Jugadores de LaLiga con subida sostenida (≥4% en 3 días y ≥6% en 7) y precio ≤1,06× valor. **Prueba histórica con 201 jugadores y ~80 días**: comprar así y revender a los 7 días rinde de media **+17%** (gana el 89%); comprar algo que cae ≥4% en 3 días pierde un 12%. Dedica el 25% del saldo libre (el **60% en un parón**), máx. 40% por jugador |
| Calendario | Detecta parones (≥10 días sin partidos) con el calendario real y avisa del actual y del siguiente. Hoy: parón 21/9–9/10. Próximos: 8–22 nov, 20 dic–3 ene, 21 mar–4 abr, 21 abr–2 may |
| Avisos de fallo | Si el bot falla, Telegram 🔴 con el error (máx. 1 cada 3 h). Y si faltan ≤30 h para la jornada y no puedes alinear 11, 🚨 |
| Pujas por lesionados | Si un jugador por el que has pujado se lesiona antes de resolverse, se cancela la puja |
| Saldo | Nunca gasta más que saldo − 5% de colchón − pujas vivas − dinero reservado para cláusulas que se liberan en <24h. Nunca puede quedar en negativo |
| Cláusula que se libera pronto | Reserva su dinero; si se libera dentro de la misma pasada (≤25 min), espera al segundo exacto y paga |
| Líder / venganza | Clausular al líder o a quien te acaba de clausular se puede, pero con menos prioridad (×0,6) |
| Poner a la venta | **Todos tus jugadores siempre en venta** (a 1,1× su valor): así la liga manda una oferta diaria por cada uno. Estar en venta no obliga a vender |
| Ofertas de la liga | Acepta desde **1,05× el valor**; 0,97× si está en caída/lesionado o es un suplente con la plantilla llena; **1,25× si es clave** (quitarlo baja el once ≥3 pts/jornada) o si es titular y faltan <48h para la jornada. Nunca si te deja sin 11 a <48h |
| Venta antes de perder la protección | Si la cláusula de un jugador tuyo es atractiva (≤1,12× valor), empieza a intentar venderlo **3 días antes** de que acabe su protección: exige 1,03× a 3 días y baja hasta 1,00× el último día (+3% al principio si es clave), y nunca menos de lo que subiría hasta que se abra (`at_risk_min`, 18/10). **Dentro de ese tramo ya no se espera a que suba más** (eso dejó pasar a Yoel Lago el 17/10) |
| Ofertas de rivales | Se rechazan, salvo que paguen ≥1,3× el valor |
| Alineación | El mejor once por puntos esperados × probabilidad de titularidad × **partido** (casa +5% / fuera −5%, rival del 1º al último de LaLiga −10% a +10%, con la tabla real calculada de los resultados); se guarda y se **verifica releyéndola**. No se toca con la jornada en juego |
| Blindaje | Gratis, **24 h**, máx. **2 por jornada** (desde que acaba una hasta que acaba la siguiente) y solo con la cláusula ya abierta. Solo para quien al irse nos quita ≥2 pts/jornada y tiene la cláusula ≤1,12× su valor (`ap.shield_target`); si es mayor, que la paguen nos favorece. Las horas de blindaje valen para tener **una oferta más** de la liga con la que venderlo. Se pregunta antes a `check-shield` (400 «limit reached» = sin blindajes; 400 «protected» = aún no se abre) y se verifica después |
| Subir tu cláusula (último recurso) | Si un jugador nuestro que importa (quita ≥2 pts) o sube (≥1%/día y ≥8M) se abre en ≤6 h, no se ha vendido (ya no queda oferta diaria antes de abrirse) y no quedan blindajes: cláusula a **×1,20** su valor (pagas la mitad de la subida, máx. 12% del valor y sin bajar de 2M de caja). Se verifica releyendo (`_protect_exposed`) |
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
  4 = blindaje (user1 = quien blinda; `playerMasterId` = el blindado), 6 = premio de jornada. user1Id/user2Id son manager_id.
- **Mercado**: se resuelve cada día a las ~20:53 (pujas y ofertas nuevas).
- **Blindaje**: `PUT /shield/player` responde bien pero no blinda; `check-shield` → 400
  "Player team shield limit reached".

## Sin probar todavía (rutas del cliente Externoak/LaLigaApp, la referencia más cuidada)

- **Rechazar una oferta**: `POST .../offer/{id}/reject` sin cuerpo ni Content-Type (si no, 400).
- **Subir tu cláusula**: `PUT .../buyout/player` con `{factor: 2, playerId, valueToIncrease}` (la
  ruta que teníamos antes era incorrecta).
- **Cancelar una puja**: `DELETE .../market/{marketId}/bid/{bidId}/cancel`.
- **Fase económica→competitiva**: descartada — tu directriz es ir a por puntos ("jugadores buenos").

> **Antes de seguir, lee `PENDIENTES.md`**: puntos de fuga por prioridad, evidencia y cómo retomar con los datos del bot (`pull`).

## Autoajuste (5/10/2026): modo `shadow` — el bot propone, NO aplica

`fantasy_agent/learn.py` (puro) + `cli._tune`. **Una vez al día** (ligero) y **los domingos** (recalibración pesada, ~250 peticiones). Solo toca 7 números, siempre dentro de límites fijos (`autopilot.BOUNDS`). **Por defecto (`AUTOTUNE=shadow`) calcula y guarda propuestas pero NO las aplica**: se revisan con los datos (`tune --cloud`) y se decide aquí. `AUTOTUNE=on` las aplica (a medio camino de lo aprendido, con motivo registrado); `AUTOTUNE=off` lo apaga.

| Parámetro | Fábrica | Límites | Cómo aprende | Muestra mínima |
|---|---|---|---|---|
| Umbral de venta de ofertas | 1,05× | 1,02–1,10 | Parada óptima con las ofertas reales que ha visto (coste de esperar 0,8%/día) | 40 ofertas |
| Prima base de puja | 3% | 1–8% | Sube 1 punto si gana <50% de las últimas pujas, baja 1 si gana >85% (máx. 1 cambio/3 días) | 12 pujas resueltas |
| Dinero a inversión | ×1 | ×0,3–1,5 | Rendimiento de sus propias inversiones (cerradas o a valor de hoy), encogido hacia ×1 con pocas | 12 operaciones |
| Subida esperada por nivel (4) | 25/15/8/8% | ver BOUNDS | Recalibra con el histórico de valores, mezclado con el valor de fábrica y rebajado un 15% | ~40 observaciones **independientes** (n/7: las diarias se solapan) |

**Por qué es razonable (y qué NO es)**: (1) Validación temporal: lo aprendido con la 1.ª mitad del histórico se cumple en la 2.ª (fuerte+forma +30%→+23%; fuerte +17%→+18%; anticipada +5%→+6%), así que los valores de fábrica eran buenos y la recalibración solo los mueve unos puntos. (2) El umbral de venta tiene poco en juego: pasar de 1,05 al óptimo vale ~0,2% del valor del jugador (hasta ~1% si esperar fuera barato). (3) No decide **qué comprar** ni reescribe reglas: solo afina números. Con la muestra actual **casi no ajusta nada todavía**; empezará a hacerlo a medida que haya semanas de datos. La entrada anticipada (subida suave + forma) rinde ~+5,6% a 7 días, menos que el coste de ida y vuelta (~5% + prima): la recalibración la deja prácticamente desactivada, que es lo correcto.

## Dinero: lo que sabemos (4/10/2026)

- **Estimación del dinero de cada rival**: 100M iniciales − gastos + ingresos de `/activity` + premios de jornada (tipo 6, ≈0,1M por punto). Acierta a ~1M en el nuestro (estimado 20,7M, real 21,8M). Hoy: Josinho ≈84M, Pep ≈85M, Aleix ≈32M.
- **El dinero entra sobre todo por puntos** (0,1M por punto de jornada): J5, J6 y J7 sacamos 0 (no se guardaba la alineación) = ~13M perdidos más las posiciones.
- Operaciones cerradas: +10,1M en 16 (la gran ganancia fue Lamine Yamal: +9,9M). Las compradas con el piloto: −1,0M realizado y −5,7M sin realizar (Gueye −8,5M y Soria −7,2M por pagar de más y comprar a la baja): corregido.
- **De dónde sacan el dinero los rivales** (4/10): Josinho +76M sin vender nada, solo con cláusulas pagadas a jugadores que ya estaban subiendo (Roberto +77% en 21 días, Marc Bernal +55%, Lamine Yamal +35%). La cláusula acompaña al valor (ratio ≈1,00), así que no hay "precio viejo": la ganancia es la **inercia** (lo que sube sigue subiendo, +17% a 7 días de media). El bot ya lo hace: **inversión por cláusula** (rivales con cláusula ≤1,08× valor, ≥4% en 3 días y ≥6% en 7, abierta o que se abre en <24 h: reserva el dinero y paga al segundo) y por puja de mercado.
- **Cómo son las ofertas de la liga** (99 ventas reales + 11 ofertas de hoy): aleatorias, ~0,87–1,13× el valor, **sin relación** con la tendencia ni el precio del jugador (correlación ≈ −0,1). Las aceptadas tienen mediana 1,055 (sesgo: se aceptan las altas); las del día, media 0,97. El bot **registra cada oferta** que ve (`python3 -m fantasy_agent offers` muestra la distribución real) para afinar el umbral de venta. Con un descuento del 1%/día, el umbral óptimo ronda 1,06×.
- **"Dos o tres partidos buenos y el precio salta"** (prueba con 300 jugadores y 4 jornadas, retorno a 7 días): subida fuerte + buena forma (≥6 pts de media) **+30%, gana el 95%**; subida fuerte sin forma +16%; subida fuerte con forma floja (<2) +8%; **entrada anticipada**: subida suave (≥1,5%/3d) + buena forma +8% (gana el 78%); buena forma con precio plano solo +3% (gana el 34%); forma floja −6%. El bot usa la forma para puntuar y para la entrada anticipada (`autopilot.expected_drift`).
- **Rotación de capital**: si hay una inversión en subida que no se puede pagar (o no cabe en la plantilla), durante las siguientes 3 h el bot acepta ofertas de ≥0,97× el valor por suplentes que no suben (aunque sea por debajo de lo pagado: lo reinvertido rinde +8–25%). Nunca vende titulares ni jugadores que suben.
- **¿De qué depende la oferta?** (5/10) Idea tuya: se calcula sobre el valor *al poner el jugador en venta*, no sobre el actual. Con los datos de hoy no se puede distinguir (nuestros anuncios se renuevan cada 3 días y el valor se movió ±7%, menos que el ruido de las ofertas). Experimento en marcha hasta el 12/10: Mayol se anuncia a ×2,0 su valor y Freeman a ×1,5 (el resto ×1,1); el bot registra ask y valor al anunciar en cada oferta, y `python3 -m fantasy_agent offers` muestra la media de oferta según lo pedido y según cuánto subió el valor desde el anuncio. Además, **se reanuncia** cualquier jugador cuyo valor suba ≥10% desde que se anunció (por si tienes razón).
- **Revisión con datos (5/10)**: `python3 -m fantasy_agent review` (y un resumen automático cada domingo por Telegram). Desde el 26/09 las compras por puja perdían −11,7M (8 operaciones: pujas de hasta +18% sobre el valor) y las de cláusula ganaban +5,2M. Cambios: (1) un fichaje solo se hace si su beneficio neto es positivo: puntos que suma durante ~3 jornadas + revalorización esperada − (prima pagada sobre el valor + 5% de margen al revender); Johnny (+0,6 pts/jornada, 19% de prima) ya no pasaría; (2) las inversiones exigen que la subida esperada supere prima + margen; (3) un **lesionado** se vende a ≥1,00× el valor (sin bajar de lo pagado) aunque esté subiendo (Koski: +6,8M sobre lo pagado y sin puntuar); (4) el workflow usa `ubuntu-24.04` fijo (`ubuntu-latest` pasa a Ubuntu 26 el 19/10).
- **Fallos de GitHub (5/10)**: 3 ejecuciones fallaron con "The job was not acquired by Runner": incidencia de GitHub, no del código; la siguiente ya funcionó. El correo de GitHub avisa de cada fallo de Actions; se puede desactivar en github.com/settings/notifications (Actions).
- **La técnica de fondo (Josinho con Yamal): comprar lo que va a subir y esperar a que suba.** Prueba histórica de la salida (comprando en subida fuerte): vender a los 7 días **+17%** de media; **mantener hasta que la subida se frena (≥1% en 3 días) +72%** de media (mediana +21%, ~19 días); da igual la regla exacta de frenado (d3≤0, 2–4% bajo el máximo...). El bot ya lo hace: mientras un jugador siga ganando >1% en 3 días (y >5% en 7) **no vende** (exige ×1,25, fuera del rango de ofertas ~0,87–1,13), y en cuanto se frena vende a la primera oferta ≥1,05× el valor (sin bajar de lo pagado). El rendimiento medio viene de unos pocos grandes ganadores: hay que dejarlos correr.
- **Vender antes lo que cae**: ≥4% de caída en 3 días ya cuenta como "cortar pérdidas" (otro −8% en los 3 días siguientes).
- **Recompensa diaria (100K por ver un anuncio)**: no hay endpoint conocido (15 rutas probadas, todas 404) y el servidor valida el anuncio. No automatizable por ahora.

## Operación bloqueo: dejar sin portero al líder (construida el 4/10/2026)

Sin once legal la jornada entera puntúa 0. Solo se hace con el **portero** (barato y escaso).
El código está en `fantasy_agent/siege.py` (decisión, pura) y `cli._siege_*` (ejecución).
Para ver ahora mismo si sería viable: `python3 -m fantasy_agent siege` (no escribe nada).

**Cómo decide** (todo lo que se mira, con datos reales):
- **Objetivo**: el líder por puntos (si eres tú, no hace nada).
- **Qué hay que quitarle**: TODOS sus porteros disponibles, con la cláusula abierta (sin bloqueo de 14 días ni blindaje) en el momento de ejecutar.
- **Cómo repone**: porteros del mercado de LaLiga que se resuelven antes del primer partido (se puja un +35% por encima, para ganarle) y porteros de otros mánagers con la cláusula abierta (se clausulan también) siempre que **pueda pagarlos** (su caja se estima con `/activity`, error ~1M). Si uno de TUS porteros es clausulable por él, no se hace.
- **Blindaje**: el tope observado es 2 por equipo y jornada; si ya los gastó, no puede protegerse (certeza sube).
- **Momento**: 3 min antes de que se congelen las cláusulas (24 h antes del primer partido); espera dentro del job (máx. 20 min). Las pujas del mercado que se resuelven antes se hacen ya.
- **Certeza**: producto de riesgos (blindaje posible 0,85; cada portero del mercado 0,90; cada cláusula ajena 0,93; porteros nuevos antes del cierre 0,85; ofertas directas 0,95). Mínimo **60%**.
- **Cuánto gasta**: bruto ≤ 70% del saldo libre × etapa de la liga (×0,6 antes de J6, ×1 después, ×1,4 en las últimas 8 jornadas) × (0,5 + 0,5·certeza). Casi todo se recupera: son jugadores.
- **Si compensa**: beneficio = puntos que suele sacar el líder (media de sus últimas 3 jornadas) × 0,3M; coste esperado = lo pagado por encima del 95% del valor + 10% de coste del dinero parado. Se hace solo si beneficio × certeza ≥ coste.
- **Arma** (reserva el dinero y avisa por Telegram) a ≤96 h de ejecutar; si deja de ser viable, avisa de que se descarta. **Reevalúa justo antes de ejecutar** y cancela si algo cambió. Si el primer paso (quitarle el portero) falla, no sigue.
- Los porteros adquiridos **no se venden ni se ponen a la venta antes de la jornada** (volverían al mercado); después se liberan.

**Estado a 4/10 para la J8**: no viable (Herrero está bloqueado hasta el sáb 10 12:20, después de que empiece). Se reevalúa cada pasada.

## Cron fiable (hecho el 4/10/2026: cron-job.org cada 15 min, token hasta el 14/06/2027)

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

## Revisión del 8/10/2026 (Opus 5.5)

- **Cláusulas: nunca se ha pagado más de lo que marcaba la cláusula.** En los 15 clausulazos, lo enviado y lo
  cobrado coinciden. Lo que sí pasa es que algunas cláusulas estaban por encima del valor de mercado (Johnny
  +19%, Herrero +15%, Terrats +14%, Deossa +13%): eso ya lo descuenta `plan_acquisitions` (la prima resta del
  beneficio neto). Nuevo: `cli._pay_clause` **relee la cláusula en el mismo instante** de pagar (sin caché),
  paga lo que vale ahora y **no paga si ha subido** más de un 1% sobre lo planeado, o si se ha blindado o ya no
  está. Se usa en compras, inversión por cláusula, cláusulas al segundo (20:53) y bloqueo.
- **Fallos del cron**: en 3 días, 290 ejecuciones bien y 7 mal: 5 eran de GitHub ("not acquired by Runner"),
  2 eran del bot de madrugada (6/10 01:15 UTC, 7/10 03:01 UTC) sin causa visible (los registros de GitHub piden
  sesión). Cambios: (1) cada paso de la pasada va aislado (`_step`): si falla uno (Telegram, publicar datos…),
  los demás se hacen igual y te llega un aviso con qué paso falló; (2) los cortes pasajeros (5xx, 429, red,
  reintentos agotados) ya no marcan la ejecución como fallida (la siguiente, a los 15 min, lo reintenta);
  (3) toda traza se guarda en `kv.errors` y se exporta en `state.json` **sin secretos** (`storage.redact`
  tacha el token del bot de Telegram, Bearer y tokens). Para ver la causa: `pull` y mirar `errors`.
- **Zona horaria**: la máquina de GitHub va en UTC; ahora `TZ: Europe/Madrid` en el workflow (horas de
  silencio, resumen del domingo, fecha del patrimonio y del autoajuste).
- **Datos (exportación del 7/10)**: patrimonio 253,9M (5/10) → 256,4M → 259,0M (7/10). 48 ofertas: mediana
  0,999× valor, p10 0,911, p90 1,065, máx 1,096. **Experimento de precio pedido**: Mayol ×2,0 y Freeman ×1,5 no
  recibieron ofertas más altas → el precio pedido **no** ancla la oferta (descartado). Valor-al-anunciar: sin
  datos suficientes aún.

## Regla de la cláusula, pujas al final y portero suplente (8/10/2026)

- **Cláusula = lo máximo entre lo que pagó su dueño y su valor actual** (mínimo 1M). Comprobado en 49 de 55
  jugadores de la liga; los 6 restantes son cláusulas de menos de 1M o subidas a mano (Ryan, Ángel Pérez, I. Romero).
  Consecuencia: si un rival te clausula, cobras **al menos lo que pagaste** y al menos su valor. Por eso la venta
  "antes de que se abra la cláusula" ya no acepta nada por debajo de la cláusula (`offer_decision(clause=…)`): vender
  más barato es perder dinero frente a que te lo quiten (caso David Soria: pagado 46,6M, vale 38,3M, cláusula 46,6M =
  1,22×; nadie la pagará y el bot lo mantiene; no se vende por debajo de lo pagado salvo lesión o caída fuerte, y al
  ser el titular, solo con una oferta ≥1,25×).
- **Pujas en el último minuto**: el número de pujas de cada anuncio lo ven todos. Los anuncios de LaLiga cierran a
  las 20:53; la pasada que arranca en los 25 min previos espera dentro del job y puja a las ~20:50:30, releyendo el
  anuncio (`cli._timed_actions`, junto con las cláusulas al segundo, en orden de hora). Disparo extra recomendado en
  cron-job.org a las 20:27 (hora de Madrid) para asegurar que hay una pasada en esa ventana.
- **Subida aguantada hasta el final**: un jugador que sigue subiendo (≥1%/3d y ≥5%/7d) no se vende por menos de
  1,25× aunque su cláusula esté a punto de abrirse: si un rival lo clausula, cobramos la cláusula, que sube con él.
- **Golpe al líder (general, cada jornada)**: cada fichaje suma, además de lo que mejora nuestro once, los puntos que
  pierde el líder si se lo quitamos (`autopilot.leader_loss`: cuánto empeora su mejor once; si se queda sin once
  completo, +15). Solo con cláusula ≤1,05× su valor (no le regalamos dinero). Si la congelación de cláusulas llega
  en <24 h, el pago se hace **3 min antes de la congelación** (no puede reponerlo por cláusula; solo le queda el
  mercado de ese día). Si no hay saldo y el golpe le quita ≥2 pts, se activa la venta de suplentes que no suben.
  Ranking del 8/10 (pts/jornada que le quitaría): Kang-In Lee 5,4 (85M), Herrero 4,2 (21M, su portero), Hancko 4,2
  (47M), Giuliano 4,1 (57M), Navarro 3,9, Ilaix 2,9, H. González 2,5 (¡4,9M!), Barrenetxea 2,2, Diomande 2,2.
  La operación "sin portero" (dejarle a 0) no es viable de momento: tiene 3 porteros (solo Herrero es bueno) y Aitor Fdez está bloqueado hasta el 18/10 (corregido el 9/10; antes decía 4).
- **Crédito solo en parones largos** (`LEVERAGE_PCT`, 10% del valor de la plantilla ≈ 26M; 0 lo apaga). El saldo solo
  cuenta al empezar la jornada (negativo = 0 puntos; fuente: ayuda de Fantasy MARCA) y el juego deja deber hasta el 20%.
  Con ≥7 días hasta la siguiente jornada, el dinero de inversión puede ir a crédito; desde 72 h antes, `_delever` acepta
  ofertas de la liga (primero de suplentes; ≥0,98× a 72–48 h, ≥0,94× a 48–24 h, ≥0,85× a <24 h; nunca rompe el once)
  hasta volver a positivo, con aviso 🔴 si no llega. Primera vez: parón del 8 al 22/11. Entre jornadas normales NO se usa:
  3 días de subida no pagan la ida y vuelta (~5–6%) y un fallo cuesta una jornada entera.
- **Subir cláusulas**: se quita la "protección a 1,5×" (costaba el 25% del valor). Una prueba única y barata
  (`_clause_raise_probe`, ~55K con Mayol) mide qué sube y qué cobra la API; queda en `clause_raise_test`.
  Datos para la política: los rivales han pagado como mucho ~1,10–1,15× el valor por una cláusula.
- **Portero suplente**: con un solo portero disponible, el bot puja por el mejor portero de LaLiga ≤1,5M que tenga
  puntos esta temporada (`autopilot.backup_keeper`). El líder lleva 4 porteros.
- Otros bots revisados (8/10): Ramos-SportsData/fantasybot (pujas al final, Python stdlib, LLM opcional),
  menaweb/laliga-fantasy-bot (GitHub Actions; fases de escritura y "kill switch"), PlatanosVerdes/laliga-fantasy
  (Go; cruza con futbolfantasy.com: % de titularidad, puntos de la temporada pasada al inicio, rivales ±12%,
  casa ±4%), Kickbase-Trading-Advisor (alemán: predice la subida de mañana con puntos, minutos, valor y subidas
  recientes — lo mismo que nuestros niveles de subida + forma).
- **¿Se puede ganar la liga?** Tras J7: −190 puntos con 31 jornadas → hacen falta +6,1 pts/jornada sobre el
  líder. Mejor once con la media de la temporada de cada jugador (8/10): nosotros 63,0, Josinho 55,7, Aleix 50,4,
  Pep sin once completo. Viable pero ajustado: depende de no perder ninguna jornada más, de seguir creciendo en
  dinero y de quitarle jugadores al líder a precio justo.
- **Revalorización de la plantilla actual** (8/10): nosotros +11,4% en 7 días (+26,5M), Josinho +9,7%, Aleix +7,6%,
  Pep +3,6%. La cartera ya crece al mejor ritmo de la liga; la diferencia de dinero viene de antes del piloto.

## Lo que enseñan los rivales (8/10/2026, `learn-rivals`)

Liga de 4, empezó en la J3. Clasificación tras la J7: Josinho 279 pts (43, 99, 48, 42, 47), Aleix 160, Pep 122,
nosotros 89 (49 y 40 en J3–J4; **0 en J5–J7 por no tener once guardable**). Cuando alineamos, puntuamos cerca del
líder. La diferencia grande está en el **dinero**: Josinho ~393M de plantilla + ~80M de saldo estimado; Aleix
316M + 74M; Pep 315M + 52M; nosotros 259M + 1,4M.

| Mánager | Operaciones cerradas | Beneficio | Pujas: prima / subida previa 7d / valor a 14d |
|---|---|---|---|
| Josinho | 26 | **+151M** | +3,9% / **+15%** / +10% |
| Aleix | 24 | +102M | +7,6% / +9% / +13% |
| Pep | 12 | +89M | +16,5% / +4% / +54% |
| Nosotros | 20 | +11,5M | +9,2% / **−0,4%** / −4% |

- **El líder compra jugadores que ya suben** (+15% en 7 días), grandes (89% del gasto en jugadores ≥15M), con poca
  prima, y los mantiene ~14 días: muchas salidas son **que le paguen la cláusula** al acabar la protección (le han
  pagado 441M en cláusulas; Pep 234M de ellos). Mejores: Lamine +30%, Roberto +75%, Fermín +22%, Koski +171%.
- **Toda la liga (83 compras con 14 días de recorrido)**, según la subida en la semana previa a comprar:
  <0% → valor −9% a 14 días, neto con prima y venta −17%, gana el 18%; 0–10% → +1,5% / −6% / 39%;
  10–25% → +23% / +14% / 74%; ≥25% → +70% / +36% / 75%. Coincide con la prueba histórica del 4/10.
- Nuestras pérdidas eran **fichajes por puntos de jugadores planos o en bajada con prima alta** (Gueye −7M, Dani
  Lorenzo, Dolan, Nacho Pérez, Rafita, Gayá), casi todos antes de la regla de beneficio neto (4–5/10). Desde el 3/10
  todas las compras del bot son de jugadores en subida (Yoel Lago, Terrats, Fofana, Zabiri, Deossa: todos en positivo).
- Cambio hecho: `autopilot.DRIFT_DECLINING` = −5%: un jugador que baja en la semana (sin llegar a "en caída") ya
  no cuenta como revalorización 0 sino como pérdida esperada en el beneficio neto del fichaje.

## Lección del 10/10: el plazo de la jornada
La API sigue llamando "actual" a la jornada hasta que cierra (isLive, hasta la madrugada del martes). Todo lo que dependa del plazo (alineación,
saldo positivo, congelación de cláusulas) debe usar `service.upcoming_week` (primer partido de la jornada SIGUIENTE cuando la actual ya empezó).
Con la jornada en juego se puede vender o que te quiten a cualquiera sin miedo al once ni a perder sus puntos de esa jornada (regla confirmada por el usuario el 10/10).

## Registro del 8–10/10/2026: lo hecho y la evidencia (movido desde PENDIENTES.md)

### Hecho
**Hecho el 10/10 (noche)**
1. Puja de 21,8M por Marcos Alonso: cancelada a mano (ruta `DELETE .../bid/{id}/cancel` verificada: la API devuelve `status: canceled`; el mercado tarda unos segundos
   en reflejarlo). El bot no la quitó solo porque nada revisaba las pujas ya hechas; ahora (a) las pujas de emergencia se cancelan solas cuando la jornada no está a <36 h,
   (b) el registro deja de contar como comprometida una puja que ya no aparece en el mercado (antes seguía reservando 21,8M y una plaza hasta que caducaba).
2. Portero de reserva protegido (decisión del usuario): siempre ≥2 porteros disponibles y ≥1 PROTEGIDO (su cláusula sigue bloqueada cuando se congelen las
   cláusulas de la próxima jornada; una compra bloquea 14 días). Se compra por cláusula abierta (sin límite de ratio, ≤3M) o del mercado, el de más media; se
   renueva solo antes de que acabe el bloqueo ("rotación"); no se vende mientras haga falta. Si no hay plaza, se quita lo último del plan y se vende el suplente
   más barato (aunque suba, sin bajar de lo pagado) para hacer hueco. Hoy: Szczesny (1,6M) y Javi Rueda (5,3M); la plantilla de 10 centrocampistas que suben deja pocas plazas.

**Hecho el 10/10 (tarde-noche)**: salida al frenarse una subida: si un jugador que subía (>+5% en 7 días, valor ≥3M) deja de subir (hoy ≤+0,4%), se vende a la primera
oferta ≥1,00× su valor, sin mirar lo pagado. Datos: esperar 7 días tras frenarse da −6,3% (−11,9% si ya baja el primer día); vender a la 1.ª oferta ≥1,00× da +3,7%. Los
clave (Soria) y los titulares a <48 h de la jornada quedan fuera.

**Corregido el 10/10 (noche), a raíz de tus dudas**
- Portero de reserva: se compró a Szczesny por 1,6M (valor 0,94M y bajando) habiendo en el mercado a Rafa Romero por 0,61M. La regla elegía la cláusula inmediata y, entre
  las opciones, la de más media (0,125 frente a 0,0). Ahora gana el MÁS BARATO (de reserva no importa la calidad) y se espera: hasta 36 h antes de la congelación solo se
  compra si cuesta ≤0,8M; después, el más barato de ≤3M. Szczesny se queda (venderlo y fichar a otro cuesta lo mismo); ya no hay que comprar otro hasta la rotación (24/10).
- Prima en cláusulas: Johnny (+19%), Terrats (+14%) y Deossa (+13%) subieron un 13–15% desde el día de compra y quedaron en −4%/−0,2%/+0,2% frente a lo pagado;
  las de prima 0% dieron +3% a +22%. El error de Johnny fue de COMPRA (la prima), no de venta ni de predicción (subió lo esperado). Ahora solo se paga más de un 10% de prima
  si la compra suma ≥3 pts/jornada al once. Pendiente: revisar el peso de la subida esperada (`drift_strong_good` 0,25 frente a ~+17% medio a 7 días observado).

- Los puntos de un partido tardan ~2 días en notarse en el valor (10/10, 1.473 partidos): con ≥1,8× su media, el valor pasa de +0,1% (D+1) a +2,6% (D+2) y +3,1% (D+3) diarios; con ≤0,4×,
  de +0,4% a −0,4%, −0,6%, −0,7%. En jugadores que ya subían (≥5% en 4 días), un partido malo no los frena de golpe, solo desacelera: +13,7% acumulado a 5 días (normal +20%, bueno +26%);
  tipo Johnny (≤3 pts, media ≤4): +8,4% a 5 días. Por eso mantener a los que suben hasta que se frenen es correcto, y `trend_d1` (la salida al frenarse) reacciona al valor ya movido.

- (10/10, noche) **Permutas, en modo aviso**: `autopilot.swap_candidates` compara vender A para fichar B con los mismos pesos del planificador (puntos del once durante 3 jornadas +
  subida esperada − prima y márgenes de ida y vuelta; el efecto en el once sale de comparar el mejor once con y sin la permuta). Solo propone cuando el fichaje no cabe en el saldo
  libre; no vende al único portero ni a los protegidos. Avisa por Telegram una vez al día por pareja y guarda `kv.swap_log` (se exporta). NO ejecuta: se activará cuando sus propuestas se vean razonables.
- (10/10, noche) Cláusulas de una posición que falta cubrir: se admite hasta 1,35× el valor (antes 1,2×; Ryan, 1,22×, quedaba fuera). El fichaje a crédito de emergencia descarta a los que caen.

### Revisión de la J8 (13/10/2026, tras cerrar la jornada)
- Resultado J8: Josinho 62, nosotros 57, Aleix 45, Pep 28. Total: 341 / 205 / 150 / **146** (brecha con el líder 195). Esperábamos 61,9 con el once de salida y sacamos 57 (−4,9); un partido suelto de un titular tiene
  desviación 3,6 puntos, la de un once ~12: **no es un fallo de estimación**. Freeman marcó 7 DESPUÉS de que se lo llevaran (21:02, al empezar su partido) y entra en los 57 (7+4+8+7+0+7+1+10+2+8+3):
  **confirmado que lo que pierdes tras empezar la jornada puntúa igualmente para ti**.
- Golpes al líder ejecutados solos: Giménez 21,01M (12/10 20:53), Hancko 47,12M (13/10 00:32), Herrero 21,19M (13/10 04:31, su portero). Con la plantilla de hoy el once esperado del líder para la J9 baja a 41,5 pts
  (12 jugadores, un solo portero: Aitor Fdez) y el nuestro es 64,8 (si no los repone; tiene ~170M). Ventas para financiarlos: Marc Roca 24,01M, Rueda 5,38M, Szczesny 0,99M, Johnny 6,10M. Nos clausulan: Yuri y Freeman (10/10),
  Agoumé (17,69M) y Pepelu (17,10M) (12/10).
- Últimos fichajes frente a lo pagado: Ilaix +13,6%, H. González +9,8%, Deossa +9,7%, Giménez +0,6%, Rueda −4,4% (se vendió a 5,38M, +2%), Hancko y Herrero 0,0% el primer día. Hancko (47M) y Herrero (21M) NO subían y venían de un partido
  mediocre (0,64× y 0,97× su media): los datos de jugadores en su situación dan −3% a 5 días (el 75% baja). Giménez sacó 0 (no jugó) pero subía (+7%): +5% esperado.
- `python3 -m fantasy_agent cohorts` (nuevo) repite la tabla de cohortes (cohorts.py). Con 0 puntos (sin jugar) el valor baja ~1% diario desde D+2 (−5,8% de D+2 a D+7; el 83% baja); si el jugador YA subía, sigue subiendo
  (+3,7%). Para los que subían, aguantar y vender al frenarse ≥1,00× (lo que hace el bot) da +9,4% a ≤6 días incluso tras un mal partido; para los que NO subían, aguantar da −6% y vender a la 1.ª oferta ≥1,00× da +3,4%.

### Cambios del 13/10/2026 (R1 y R2, decididos con el usuario)
- **R1 — subida esperada según el último partido, con tabla que se recalcula sola**: `expected_drift(..., player_id)` usa la tabla de cohortes (`cohorts.py`) cuando hay señal fiable del último partido
  (puntos relativos a su media en las demás jornadas, si subía ≥5% en los 3 días previos, días desde el partido 1–4); si no, la subida por tendencia de siempre. La tabla NO es fija:
  `cli._refresh_cohorts` la recalcula con todos los datos (463 jugadores, ~4 min) una vez por jornada, de madrugada (01–08 h), y la guarda en `kv.cohort_table` (se exporta); las celdas con pocos
  casos se mezclan con la de partida (J1–J8). Efecto hoy: Terrats +25% → +5,8%, Deossa +25% → +6,8%, H. González +25% → +3,7%, Hancko/Herrero/Soria negativos (−3%).
- **R2 — salida de 3 días**: un jugador que NO subía y sacó un partido mediocre o malo hace 1–6 días (<1,0× su media) se vende a la primera oferta ≥1,00× su valor (sin mirar lo pagado);
  pasadas 72 h, a ≥0,97×. No aplica a los clave (Hancko, Soria), a los que suben ni a quien rompe el once a <48 h de la jornada. (`autopilot.exit_candidate`, `offer_decision(exit_mode=…)`, `kv.exit_since`.)
  Simulado: aceptar la primera oferta que llegue al precio de cuando se empieza a vender da +0,8% de media y se consigue en el 70% de los casos (p10 −9%); mantener da −6,5%. Las ofertas siguen al
  valor del día, no al valor con el que se lista (β=0,01 con 114 ofertas; sin casos de jugadores cayendo en la muestra, así que lo del "precio al listar" queda como ~70% de las veces, no "siempre").
- Un portero de reserva CARO y de banquillo (Herrero, 21M) no cuenta como reserva protegida: se compra una barata antes de poder soltarlo.
- **R3 (rentabilidad mínima por fichaje) NO se aplica**: los golpes al líder valen por los puntos que le quitan (`rival_loss`) y, si el jugador sube mucho, por su subida esperada.

### Cambios del 13/10/2026 (noche): pujas, Herrero, permutas
- **Pujas**: la puja mínima válida es el MAYOR entre el precio de salida y el valor ACTUAL (`autopilot.bid_floor`). El anuncio conserva el valor de las 20:53 del día anterior y el valor se actualiza a las 00:00:
  Gulácsi subió un 3,6% (8,60M → 8,91M) y nuestra puja de +3% (8,86M) quedó por debajo del valor → HTTP 400 `is not a valid money quantity` (dos avisos: el trabajo de las 20:30 y el de las 20:45). Ahora
  las pujas parten del suelo y `cli._bid_robust` reintenta con +1–5% (techo +12% sobre el valor) si la API las rechaza por importe. Las pujas de INVERSIÓN iban al precio de salida exacto: con jugadores que suben
  (los que se buscan) siempre quedaban por debajo del valor → por eso no se ha cerrado ninguna puja de inversión. Ahora van un 1% por encima del suelo.
- **Herrero (no debía venderse)**: sube y sacó 6 con media 6,2. Dos fallos míos: (1) los tramos de puntos eran demasiado gruesos (0,4–1,0× metía un 0,97× como "partido flojo"; ahora 8 tramos, flojo = <0,9×); (2) no se miraba
  si el valor sigue subiendo hoy (si sube hoy, después no cae: +4,7% a 5 días, 84 casos; plano o bajando: −7%). La salida de 3 días exige ambas cosas. Los puntos absolutos predicen igual que los relativos (3–4 pts: −3%; 5–6: +2%).
- **Permutas ejecutables** (antes solo aviso; solo con la compra por CLÁUSULA abierta: una puja de mercado puede perderse y nos quedaríamos sin el titular vendido y sin el fichaje): se ejecuta la mejor si, con la plantilla de ESE instante: ventaja esperada ≥2M y ≥4% del coste del fichaje (ya neta de prima, 5% de ida y vuelta del fichaje y 3% de venta), existe una oferta por el
  jugador a vender de ≥1,00× su valor, el once queda legal, faltan ≥30 h para la jornada, no hay otras compras ni pujas en esa pasada y no se ha hecho otra en 24 h (`autopilot.swap_is_safe`, `cli._execute_swap`).
  El motivo de la comprobación en el momento: la propuesta Hancko → Fer Niño (+7,3M) dejó de valer 14 minutos después, cuando otra regla vendió al tercer defensa de relleno y vender a Hancko dejaba el once ilegal.

- **Cuarto defensa** (13/10, noche): con 3 defensas y sin recambio, `sale_loss` de cada uno es igual a sus puntos esperados (Giménez, media 3,0 → 3,0 = "clave") y ninguna regla de salida (frenarse, caída) lo soltaba:
  con "clave" el bot mantiene aunque el valor baje. Con un recambio la pérdida baja (3,0 → 0,5) y la salida al frenarse sí funciona. `autopilot.depth_defender_move`: se compra el defensa más barato (media ≥1,5;
  ≤1M mientras haya tiempo, ≤3M cerca de la congelación) y no se vende mientras sea el cuarto. Giménez: valor +2,5%, +2,4%, +2,5%, +2,0%, +2,0%, +1,2%, +0,6% al día (se frena); 'subía y sacó 0': +2% a +3% en los 3 días siguientes pero baja el 40–52%.

- **Portero de reserva, regla afinada (13/10 noche, con el usuario)**: cualquier portero protegido (bloqueado por una compra reciente) cuenta, también uno caro (Herrero, 21M, golpe al líder). La reserva barata se compra SOLO cuando se dan
  las dos cosas: (1) nos quedamos con un único portero (p. ej. nos quitan a Soria; antes el planificador busca un titular) Y (2) la protección de ese portero está a punto de acabarse (<48 h) o no hay ninguno protegido en la congelación.
  Con dos porteros no se compra, aunque el segundo esté a punto de poder clausularse. Es general (por posición y tiempos, no por nombres). Techo 1,5M (antes 3M; lo normal 0,5–0,6M), con paciencia: hasta 24 h antes del momento
  crítico (congelación o fin de la protección) solo ≤0,8M. Cuarto defensa: ≤1M, o ≤1,5M cerca de la congelación.

- **Porteros sobrantes** (13/10 noche): solo juega un portero; uno CARO (>1,5M) de banquillo que se frena o cae (salida al frenarse, salida de 3 días o caída ≥4%) se suelta aunque sea la "reserva" (`autopilot.hold_as_reserve`); la
  regla de reserva comprará uno barato si hace falta. Uno barato o que sube se queda. Con 3 porteros sobra uno. Prioridad al comprar: primero un titular (el planificador); si no, la reserva barata.
  Corregido de paso: la salida de 3 días no estaba pasando el dato de "su valor sigue subiendo hoy" (la llamada no lo incluía): con Herrero subiendo no habría salido por otro motivo, pero la protección no actuaba.

### Cambios del 18/10/2026: no regalar a un rival un jugador que importa (tras perder a Yoel Lago)
**Qué pasó (J9).** El sábado 17 a las 23:14 Josinho pagó la cláusula de Yoel Lago (19,72M = su valor): era nuestro titular en subida (4,8 pts/jornada, 8 pts en la J8).
Cadena: (1) el martes 13 se blindó a Mayol (1,1M, 0,5 pts) y el viernes 16 a Soria (cláusula ×1,19: si la pagan, ganamos 7M) → los **2 blindajes de la jornada**
(desde que acaba la J8 hasta que acaba la J9) estaban gastados; el sábado `check-shield` respondió «Player team shield limit reached» (comprobado en vivo con Soria y Mayol).
(2) El viernes a las 21:01 había una oferta de 1,098× por Yoel Lago (a ~23 h de abrirse su cláusula) y no se aceptó: la regla «sigue subiendo, espero» (hasta 1,25×) mandaba
también dentro del tramo de riesgo. (3) Los rivales cobran en cuanto se abre cualquier jugador atractivo: en la liga hay 44 cláusulas pagadas y, cuando el jugador sube, caen a las
0,1–2 h de abrirse (Freeman 0,1; Yuri 0,1; Pepelu 0,4; Yoel Lago 1,0; Agoumé 2,0 h). Pagan casi siempre ×1,00 el valor (mediana 1,00, p75 1,03, máx. 1,15 con jugadores en subida);
con ×1,19 (Soria, 148 h expuesto) o ×1,2 (Gueye) nadie ha pagado.
**Reglas confirmadas** (ayuda oficial de LaLiga y comprobación en vivo): las cláusulas se cierran 24 h antes del primer partido de la jornada; «doble blindaje» = 2 por jornada,
24 h cada uno (48 h en ligas Premium), solo sobre jugadores con la cláusula ya activa, gratis (con anuncio en la app; por API ha funcionado el 23/09, 24/09, 13/10 y 16/10). Blindar no quita el clausulazo, lo retrasa.
Subir la cláusula: la ayuda oficial no lo documenta; nuestra prueba del 7/10 (Mayol) lo confirma: se paga **la mitad** de lo que sube.
**Qué ha cambiado:**
- `at_risk_min`: 1,03× a 72 h → 1,00× el último día; el «clave» pide +3% solo al principio (antes +7% todo el tramo); y nunca menos de lo que subiría el jugador hasta que se abra
  (lo que pagaría el clausulazo). Dentro del tramo ya no se aplica el «espero a que suba» si la cláusula es ≤1,12× el valor.
- Blindaje (`shield_target`): solo a quien quita ≥2 pts/jornada y con cláusula ≤1,12×. Se sigue sin gastar en Mayol ni en Soria. El fallo de `check-shield` ya no bloquea 96 h el reintento.
- Último recurso (`_protect_exposed` / `raise_plan`): si no se vendió y no quedan blindajes, se sube la cláusula a ×1,20 en las últimas horas (después de la última oferta diaria
  antes de abrirse); cuesta ~10% del valor y deja de salirle a cuenta a un rival. Si la paga igualmente, cobramos 20% más que su valor.
- **Bitácora de decisiones** (`kv.decisions`, exportada): cada oferta (aceptada/retenida/rechazada con su motivo, ratio, mínimo, tendencia, horas hasta abrirse), cada blindaje (sí/no y por qué)
  y cada subida de cláusula. Antes no quedaba rastro del porqué de nada.
**Lo que viene esta semana (jugadores que se abren):** Terrats (lun 19 00:16), Fofana (lun 19 21:02), Zabiri (mar 20 20:53), Deossa (mié 21 20:53), Ilaix (vie 23 21:03). Esta noche y mañana no hay
blindajes (hasta el martes 20 a las 03:00), así que se resuelven con la oferta diaria o, si no llega, con la subida de cláusula.

### Reglas de la deuda (comprobadas el 13/10/2026 con la ayuda oficial de LaLiga Fantasy y una guía de Comuniate)
- Límite: **20% del valor de la plantilla** (no del patrimonio con saldo; hoy 269,6M → 53,9M; con saldo serían 56,9M). Puja máxima = saldo + ese 20% (hoy 68,7M).
- **No se puede endeudar para pagar una cláusula ni para subir la propia**: las cláusulas se pagan solo con saldo (el bot ya trabaja así). Las pujas de mercado sí pueden usar deuda.
- Con saldo negativo (o sin 11) al registrarse la alineación, esa jornada no suma puntos. Una puja por encima del saldo se acepta al hacerla (comprobado el 10/10 con la de Marcos Alonso); falta ver cómo se resuelve con saldo negativo.
- Hoy el bot usa deuda solo en parones largos (`LEVERAGE_PCT` 10%) y en el fichaje de emergencia (hasta el 20%). Idea en estudio: permutas comprando PRIMERO con deuda (puja de mercado) y vendiendo la otra pierna después (evita el riesgo de vender y perder la puja).

- **Deuda en parones: hasta el 20% (decidido el 13/10 con el usuario)**: en los parones largos (≥7 días hasta el primer partido; suelen ser de 2 semanas, con tiempo de sobra para revertirlo) el crédito de inversión sube del 10% al 20% del valor de la plantilla
  (`LEVERAGE_PCT` 0,20 = el tope del juego). Solo para PUJAS de mercado: el juego no deja endeudarse para pagar una cláusula (`autopilot.plan_investments_with_credit`; antes el crédito podía asignarse a una cláusula y habría fallado). Se deja de abrir
  crédito a 7 días de la jornada y desde las 72 h `_delever` vende hasta volver a positivo (con aviso 🔴 si no llega): con saldo negativo al empezar, esa jornada no puntúa.

### Hallazgos y notas de la J8 (evidencia)
#### Exploración del 9/10 (sin cambios de código) — decidir el 20/10
**Cron**: 16 ejecuciones seguidas OK cada 15 min (última 20:45). Prueba de subir cláusula OK: Mayol 1.112.342 → 1.223.576
(+111.234) y la API cobró la mitad (55.617). La ruta `PUT /buyout/player` funciona con factor 2.

**A. Hueco real: si nos clausulan a Soria (único portero) no hay recambio automático.** Su cláusula (46,65M = 1,23× su valor) se
abre el dom 11/10 20:53 y J9 empieza el vie 16/10 21:00 (congelación jue 15/10 21:00). Simulado sin Soria: el bot solo considera a
Herrero (21M, del líder; con 1,5M de saldo no llega); los porteros baratos se descartan por la regla cláusula ≤1,2× (Galdin 1,87×,
Szczesny 1,68×, Ryan 1,21×) y en el mercado de LaLiga no hay ningún portero. `_auto_shield` tampoco lo cubre (no es "exposed" por el
1,2×, y la API no blinda). Sin portero no hay once legal = 0 puntos. **Arreglo propuesto**: con 1 solo portero disponible, permitir
clausulazo de un portero barato (≤3M) sin límite de ratio (Galdin 1,0M cuesta ~0,5M de "sobrecoste"), y con 0 porteros cualquier
cláusula pagable (liberando suplentes si hace falta). Valor esperado: ~0,5M frente a p×~18M (p = prob. de quedarnos sin portero en la
jornada; con p≥3% compensa). Ventana: antes del dom 11/10 20:53 si se quiere cubrir J9.

**B. Pagar más por jugadores caros (130M por uno de 120M)** — simulación con TODOS los jugadores de LaLiga (sin sesgo de elegir por
valor actual), venta a la 1.ª oferta de la liga ≥1,05× (máx. 14 días): pagando 1,00× +5,9% medio (79% gana); 1,03× +2,6%; 1,05× +0,7%;
1,083× −2,4% (35% gana). Solo con subida previa ≥10% en 7 días: 1,00× +14,4%; 1,05× +8,6%; 1,083× +5,4%; 1,10× +3,9%; 1,15× −0,8%. Las
ofertas de la liga no pasan de 1,10× (≥1,05× en el 22% de los días; ≥1,08× en el 10%) y no son mayores en los primeros 3 días tras la
compra (mediana 0,99 frente a 1,00). Conclusión: la prima solo compensa en jugadores con subida clara y siempre por debajo de ~8%.

**C. Fichar caros a rivales por cláusula y ponerlos a la venta ya (flip)** — con cláusula ≈1,0× el valor, esperar la oferta ≥1,05× da
~+6% medio en ~4–5 días (79% gana, p10 −6%); con subida previa ≥10%: +14%; con 7d previa <0%: +1,5% (no flipar jugadores que bajan).
Hoy el bot ya vende así (acepta ≥1,05× y lista todo cada pasada); lo que falta es COMPRAR para flip sin momentum: `RESALE_SPREAD` (5%)
trata la reventa como coste cuando, con paciencia, es una ganancia. Limitaciones: saldo 1,5M; riesgo de valor sd ~11% a 4 días; las
ofertas por jugadores ≥30M parecen peores (mediana 0,96, n=15). Pendiente: más ofertas (hoy 77) y decidir si financiarlo con crédito entre
jornadas (devolver antes del inicio) o vendiendo titulares que ya no suben.

**D. Pujas desde el 5/10**: 3 intentos y 3 perdidas (Luismi Cruz, Aitor Fdez, Ibañez; los ganadores pagaron +3,4% a +4,7% sobre la nuestra
y hoy los tres valen menos de lo que pagaron: 14,0M vs 12,6M; 1,35M vs 0,92M; 17,0M vs 16,8M, es decir habrían sido pérdidas). No hay más
pujas desde el 6/10 porque el saldo se fue en 7 cláusulas (94M: Johnny, Terrats, Fofana, Zabiri, Roca, Durán, Deossa), no por los criterios.
Idea: las pujas de INVERSIÓN se hacen al precio de salida exacto (`invest` → `it.price`), así que pierden contra cualquier puja rival; para
subidas fuertes tendría sentido +4–5% (sigue dejando +8% de media).

**E. Corrección**: el líder tiene 3 porteros, no 4: Herrero (21M, 37 pts), Aitor Fdez (0,9M, 8 pts) y Szczesny (1M, 1 pt). Sin Herrero
no se queda sin once; le quitaría ~4 pts por jornada. Aitor Fdez está bloqueado hasta el 18/10, así que el bloqueo total solo sería posible
desde J10 y necesitaría muchas plazas de plantilla (hay que tomar también los porteros de otros rivales con cláusula abierta).

#### Jornada 8 (10/10): fallo del plazo, Rayo–Athletic, clausulazos y rival — resuelto o decidir el 20/10
**Fallo corregido (10/10)**: la API llama "jornada actual" a la 8 hasta que cierra (`isLive`; cierra el 13/10 03:00), y el bot calculaba
el plazo (alineación / saldo / congelación) con el primer partido de ESA jornada, ya pasado: −24,6 h. Con la jornada en juego saltó el
"fichaje a crédito" de emergencia (sáb 21:02, puja viva de 21,8M por Marcos Alonso: valor cayendo −7% a 7 días, forma 2,0) y se bloqueaban
ventas "para no quedarte sin 11". Ahora `service.upcoming_week` usa `isLive`/`nextWeek`/`openingWeekDate` (plazo = primer partido de la
jornada siguiente) y una prueba lo cubre. **Decidir**: ¿cancelar la puja de Marcos Alonso (resuelve dom 11/10 20:53)? Con ella viva, el
planificador solo puede completar con un suplente barato (J. Berrocal, 0,7M, media 1,6) porque la plantilla llega a 16. Sin ella compraría a
Javi Rueda (5,3M, +3,3 pts/jornada). La ruta de cancelar puja no está probada.
**Regla del juego (confirmada por el usuario, 10/10)**: una vez empezada la jornada, vender o que te quiten a un alineado NO le quita sus puntos
de esa jornada (puntúa igualmente para ti). Con el plazo bien calculado el bot vende con normalidad durante la jornada. (Por un momento añadí un
bloqueo de ventas de alineados con partido por jugar; estaba mal planteado y se retiró.) Pendiente solo de comprobarlo con datos: Freeman
(clausulado sáb 21:02, jugó después) debería sumar en la J8 si el usuario tiene razón. Si falla guardar la alineación a <12 h del plazo, reintenta cada 15 min.
**Solo puntúan los alineados**: el planificador valora el mejor once + 15% de banquillo (`squad_value`), así que lo que no juega solo cuenta por
su reventa; Johnny (invertido, banquillo) no suma puntos. Mi suma del 10/10 de "15 puntos" era una coincidencia: alineados con partido jugado = Soria 7 +
Terrats 1 + Yuri 4 = 12 (Yuri provisional, partido suspendido); la clasificación marca 15, diferencia sin explicar (¿puntos provisionales revisados?).
**Rayo–Athletic**: no se anuló, se SUSPENDIÓ el sáb 10/10 tras 13–25 minutos (0-0, objetos al campo); los minutos restantes sin fecha (Deia apunta al
mié 5/11, sin confirmar). LaLiga Fantasy no ha publicado nada que hayamos encontrado; Comunio usa puntos provisionales y los rehace si se reanuda después
del cierre. Hay que mirar la app/noticias antes del 13/10 03:00. Nuestros afectados: Yuri (Athletic, ya no es nuestro).
**Rival del partido (decidido el 10/10)**: casa/fuera y puesto del rival solo se usan para ELEGIR EL ONCE, y así se queda (no se usan al fichar: el rival de
una sola jornada pesa poco frente a la inversión a semanas vista). Recalibrado con 1.661 actuaciones (J1–J8, validado jornada a jornada, error −4,2% frente a
ignorar al rival; el ajuste anterior −2,6%; gana en 6 de 8 jornadas): casa ×1,06/fuera ×0,94; contra los 4 primeros ×0,80 (antes ×0,92); resto ±8%;
defensas 1,5× más sensibles (`autopilot.fixture_factor`). Un partido suelto es muy ruidoso (desviación 0,71× la media): Terrats (esperado 5,1, sacó 1) es varianza,
no error. Revisar con más jornadas (la clasificación de LaLiga es ruidosa hasta la J10).
**Clausulazos (55 jugadores que llegaron a tener la cláusula abierta; 30 clausulados, 11 vendidos a la liga, 14 siguen)**: en subida (≥10% 7d)
23 de 31 se los llevan (riesgo 0,18 por día abierto, mediana 1,15 días; 8 de 30 en los primeros 12 min); con bajada previa 3 de 16 (0,02/día).
Cláusulas ≥6% sobre el valor casi no se pagan (1 de 13; riesgo 0,01/día), pero no sirve de mucho porque sin subida casi nadie las paga igual.
Rivales pagan mediana 1,000× el valor (4 de 30 ≥1,05×). Dueño clausulado: +46% medio sobre lo pagado (93% gana); vendido a la liga +17% (55%).
Para los que subían ≥10% y acabaron clausulados (n=23): clausulado = 1,22× el valor de hace 3 días (mediana 1,14×) frente a 1,10× vendiendo a la liga
en los 3 últimos días. Después del clausulazo siguen subiendo (+7,3% mediana a 7 días, el 89% sube): nos los quitan cuando van a subir más.
Yuri y Freeman se vendieron a su valor (20,0M y 2,8M; pagados 18,7M y 2,0M). Conclusión provisional: dejar que clausulen a los que suben es
mejor que venderlos antes; subir la cláusula solo compensaría con subidas muy fuertes (cuesta la mitad de lo que sube); no subir a todos.

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
4. El Plan fijado en Telegram aún usa la puntuación antigua (informativo): que refleje el plan
   real del piloto (cláusulas reservadas, pujas vivas, jugadores en riesgo).

## Dónde está todo

- `fantasy_agent/autopilot.py` — **las reglas de decisión** (puro, testeable).
- `fantasy_agent/cli.py` — ejecuta: `_watch_once` es el ciclo completo.
- `service.py`/`models.py`/`api.py` (datos y escritura), `plan.py` (el Plan), `lineup.py` (once).
- `STRATEGY.md` — razonamiento estratégico. `CLAUDE.md` — normas de desarrollo.
- `tests/` — sin red (`python3 -m unittest discover -s tests -v`).
- `.env` — tus credenciales (nunca se sube a git).
