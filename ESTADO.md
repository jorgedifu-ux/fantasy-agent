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

- **Telegram**: bot "Mi Fantasy Bot" (`@Vk_fantasia_bot`). Un único mensaje "🤖 PILOTO
  AUTOMÁTICO" por pasada con todo lo hecho (nada si no ha pasado nada), más un parte de
  situación corto cada ~90 min (silencio de 23h a 7h).
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
| Venta antes de perder la protección | Si la cláusula de un jugador tuyo es atractiva (≤1,2× valor), empieza a intentar venderlo **3 días antes** de que acabe su protección: exige 1,03× a 3 días y baja hasta 0,98× el último día (+7% si es clave) |
| Ofertas de rivales | Se rechazan, salvo que paguen ≥1,3× el valor |
| Alineación | El mejor once por puntos esperados × probabilidad de titularidad × **partido** (casa +5% / fuera −5%, rival del 1º al último de LaLiga −10% a +10%, con la tabla real calculada de los resultados); se guarda y se **verifica releyéndola**. No se toca con la jornada en juego |
| Blindaje | Pregunta antes a `check-shield` (si el equipo ya gastó el de la jornada, no insiste) y verifica después. El 26/09 la API respondió bien sin blindar (en la app pide ver un anuncio): si vuelve a pasar, te avisa para que lo hagas tú |
| Subir tu cláusula (pago) | Tus jugadores de media ≥5 cuya protección acaba en <24h y no se han vendido: cláusula a 1,5× su valor (pagas la mitad de la subida), solo si cabe sin tocar el colchón; se verifica releyendo |
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
