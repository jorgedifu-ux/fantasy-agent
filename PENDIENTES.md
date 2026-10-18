# Pendientes y puntos de fuga — para retomar con datos

> Aquí solo va lo ABIERTO. Lo ya hecho y la evidencia están en `ESTADO.md` ("Registro del 8–10/10/2026").

Actualizado el **10/10/2026** (lo hecho, en `ESTADO.md`). Complementa a `ESTADO.md` (qué hace el bot y qué está verificado). Aquí
está lo que **todavía puede mejorar** y cómo comprobarlo la próxima vez.

## Calendario hasta la revisión (martes 20/10) — lo que el bot hace solo
- **Esta noche 01–08 h**: primera recalculación de la tabla de cohortes (avisa por Telegram).
- **Reserva de portero**: no se compra nada mientras tengamos dos porteros; Herrero está protegido hasta el 27/10 (su cláusula se abre el 27/10 por la mañana). Solo si nos quitan a Soria Y le queda poco a Herrero se fichará una barata (≤0,8M; ≤1,5M en las últimas 24 h).
- **Mié 14/10 21:00**: desde aquí no se vende a nadie que deje el once ilegal hasta que empiece la jornada.
- **Jue 15/10 20:57 / 21:00**: golpes al líder antes de la congelación de cláusulas (si son viables); 21:00 empieza la congelación.
- **Vie 16/10 21:00**: empieza la J9 (primer partido); se reabren las cláusulas.
- **Dom 19/10**: el autoajuste (modo `shadow`) deja sus propuestas semanales.
- **Lun 19/10 21:00 → mar 20/10 03:00**: termina la J9 y cierra la semana; poco después, la tabla de cohortes se recalcula con los datos de la J9.
- **Mar 20/10**: revisión conjunta.

## LISTA DE PENDIENTES (resumen, 13/10/2026)

**Vigilar (primeras ejecuciones reales de lo nuevo; cada paso está aislado y avisa por Telegram si falla)**
1. Puja con el suelo del valor actual y reintento (mañana ~20:50: primera puja del último minuto con el código nuevo).
2. Primera permuta ejecutada (si llega alguna) y cómo sale; `kv.swap_log`.
3. Recalculación de cohortes (esta noche) y salidas de 3 días.
4. Cuarto defensa (Salinas, 1M, ya comprado); la reserva de portero NO se compra mientras tengamos dos porteros.
5. Golpes al líder del jueves; `kv.errors`.
6. Mirar si LaLiga Fantasy rehace puntos cuando se juegue el resto del Rayo–Athletic (sin fecha).

**Para la revisión del martes 20/10**
A. Calibrar pesos y umbrales con J8–J10 (umbral de venta 1,05×, "clave" 1,25×, "subiendo" 1,25×, suplentes 0,97×, rivales 1,30×, salida al frenarse 1,00×, techo de puja +12%, subida esperada de las tablas).
B. Permutas: ¿salieron rentables? afinar umbrales (2M y 4%). Ver I2.
C. Fichar pensando en la probabilidad de ser titular y en que un 0 puede ser "no jugó" (caso Giménez).
D. Pujas de inversión con prima y tasa de victoria (hacen falta ~15 pujas); comprar para revender ("flip"); cuánto dinero a inversión (25%) y saldo reservado para las 20:53.
E. Efecto del rival al fichar (solo se usa para elegir el once); usar los puntos absolutos y relativos.
F. Planificador: relleno barato del once; fichaje de emergencia ya sin caídas.
F2. Titulares caros "clave" por tener un banquillo flojo (Terrats 19M y Deossa 14M: su recambio, Mayol, rinde 2,8 y la pérdida sale ≥3): la salida al frenarse no los suelta aunque se frenen. Mantenerlos es coherente con los puntos que dan
   (3,9 pts por jornada ≈ 3,5M a 3 jornadas frente a −1,3M de caída), pero para poder soltarlos hace falta un recambio de calidad o una permuta por cláusula. Revisado el 13/10: bajar el umbral de venta de los que suben de 1,25× a 1,06–1,10× no mejora (±1%;
   las ofertas no pasan de 1,10×), así que ese umbral se queda.
G. Autoajuste `shadow`; bloqueo al líder (viable como pronto en la J10).
H. Política de cláusulas ("tentadora"): futuro, a petición del usuario.
S. **Bitácora de decisiones** (18/10): leer `kv.decisions` (rama `data`): ofertas aceptadas/retenidas con su motivo y su mínimo, blindajes (sí/no y por qué) y subidas de cláusula. Comprobar que explican cada venta de la jornada; ajustar lo que no.
T. **Los que se abren** (18/10, ver ESTADO «Cambios del 18/10»): comprobar cómo salieron Terrats (lun 19 00:16), Fofana (lun 19 21:02), Zabiri (mar 20 20:53), Deossa (mié 21 20:53) e Ilaix (vie 23 21:03): ¿vendidos con la oferta diaria?, ¿cláusula subida a ×1,20 y
   cuánto costó?, ¿la pagó algún rival? Si la subida a ×1,20 se queda corta (alguien paga ×1,20) o es cara, decidir otro nivel. Pendiente de probar: que la API deje subir la cláusula tanto (solo se ha probado +10%).
U. **Pujas perdidas** (18/10, 9 pérdidas en la liga desde el 22/9): el ganador pagó +3% a +36% más que nuestra puja (Deossa +36%, H. González +22%, Román +14%, Ilaix +10%, Giménez +10%, Luismi +5%, Barrenetxea +4%, Ibañez +3%; mediana +10%); las 11 ganadas
   fueron sin competencia (+3–6% sobre la salida). Pagar más tarde por cláusula costó más (Barrenetxea: puja perdida a 24,1M, cláusula a 29,9M; Giménez: 14,9M frente a 21,0M). Propuesta, sin aplicar: para objetivos de ≥3 pts/jornada pujar el p75 de los rivales (tope +12%) aunque aún no
   haya pujas. Decidir con más datos (hacen falta ~15 pujas y la bitácora).
V. **Primera permuta** (Giménez → Barrenetxea, vie 16 21:01, 1 min después de empezar el partido de Giménez; sus 6 pts cuentan): a los 2 días Barrenetxea +4,2% (+1,26M) y Giménez +2,3% (+0,49M). La ventaja esperada (6,9M) parece inflada (el modelo daba +0,65M a conservar a Giménez, que sube
   un 1,2%/día): calibrar con J9–J10.
W. **Patrimonio frente a Josinho** (reconstruido con `/activity` + valores diarios, ±10M): 5/10 nosotros 253M, él 457M · 13/10 282M / 499M · 18/10 298M / 522M. Brecha 204M → 217M → 223M: crece ~1,5M/día en dinero, pero nuestro ritmo relativo es algo mayor (+1,1%/día frente a +0,9%).
   Con ~3,3M/día lineales llegaríamos a 700M en ~120 días; compuesto al 1,1%/día, ~80.
X. **Telegram: misiones, consultas y gráficas** (18/10, a diseñar con el usuario): hoy llega un único mensaje «PILOTO AUTOMÁTICO» por pasada con todo mezclado, un parte cada ~90 min y el plan fijado. Propuesta: (a) *misiones* con estado que se **editan en el sitio**
   (once legal J10, proteger a los que se abren, fichajes en curso, brecha con Josinho) en vez de mensajes nuevos; (b) comandos de consulta (`/misiones`, `/estado`, `/brecha`, `/porque <jugador>` leyendo `kv.decisions`, `/ofertas`, `/plantilla`), respondidos en la pasada siguiente (≤15 min,
   no hay servidor); (c) gráficas bajo demanda: imagen desde QuickChart.io (gratis, sin clave; los datos viajan en la URL) o PNG propio en Python puro (privado, más trabajo) o una página en GitHub Pages con Chart.js leyendo la rama `data` (pública). Corregido ya: los cortes pasajeros de
   Telegram («the read operation timed out», casi cada noche ~03:15 en el paso de botones antiguos) ya no avisan, y si falla el envío del parte se guarda en `kv.outbox` y sale en la pasada siguiente.
Y. **Usar la alineación probable de futbolfantasy en las decisiones** (18/10): hoy solo se usa en el informe `--news`. Para Real Madrid–Sevilla da a Diomande «titular 60%» y no incluye a Vinicius (sancionado); la API solo dice `playerStatus` (`suspended` hasta que cumple). Enlaza con C (probabilidad de ser titular al fichar) y N
   (efecto suplente). El bot NO modela a quién sustituye cada uno: valora por puntos medios y tendencia.
N. **Efecto suplente** (idea del usuario, 13/10): cuando un titular habitual está fuera (lesión, sanción, rotación), su suplente puntúa y puede subir de valor. Datos J4–J8 (33 casos, `data/analysis/subs.py`): el mercado NO lo anticipa (el valor del
   suplente no sube antes del partido), pero solo compensa con suplentes baratos: <4M → +14,7% de media a 5 días (mediana +6,7%, sube el 62%; sin los 3 mejores casos +3,3%); ≥4M → −8,6% aunque puntúen (Rüdiger 9 pts: +1%). Si el suplente NO juega, −13% a 5 días.
   Con el suplente "más probable" solo juega 30 de 61 veces: sin saber la alineación es cara o cruz (+5,9% de media, −8% de mediana en <4M). Hace falta confirmación (alineación probable de futbolfantasy ≥75%) y, aun así, el dinero es pequeño
   (~4 casos baratos por jornada × ~0,4M). Decidir el 20/10: registrar en sombra, cada jornada, los suplentes <4M con titular fuera (probabilidad de futbolfantasy, quién lo tiene, qué pasó) antes de programar nada. Caso Vinicius→Diomande:
   Diomande es de José (solo cláusula, y congelada de jueves 21:00 a viernes 21:00), y un jugador caro rinde mal en esta estadística.
O. **Lesiones y sanciones por tipo** (consulta 13/10): la API solo da `playerStatus` (ok, injured, doubtful, suspended); no hay tipo ni duración y nuestro historial de estados solo tiene 3 semanas (9 cambios), así que "corta/larga" no se puede
   leer. Hoy: lesionado/sancionado = 0 pts y no se ficha, dudoso ×0,55, y al nuestro lesionado se le vende a ≥1,0×. Mejoras posibles: clasificar por días en estado no-ok (cuando haya historial); no vender a un sancionado de una sola jornada;
   subir la probabilidad de titular del compañero de posición cuando falta un titular (ver N); probar si futbolfantasy da tipo/duración (la consulta de prueba del 13/10 no devolvió ninguno de los lesionados: repetir con las páginas de la J9).
Q. **Diomande (Real Madrid, de Josinho, el líder)** — a decidir ANTES del jueves 15/10 por la noche (idea del usuario, 13/10: con Vinicius sancionado en la J9 y titular reciente, "pegará un pelotazo").
   Datos: no es un suplente sino un titular en alza: 8, 11, 4 y 11 pts en J5–J8; su valor pasó de 49,4M (J6) a 69,6M y sube ahora (+3,6% en 3 días). En jugadores de ≥25M que YA subían y puntúan ≥7 el valor sube de media +14,9% en 5 días
   (mediana +12,7%, p10 +7,8%, n=50); con 4–6 pts, +7%; con ≤3, +4%; si no subían y puntúan ≥7, solo +3%. Es decir: lo que paga es la tendencia, no el hueco que deja Vinicius (los suplentes de equipo grande, aparte, no suben de forma fiable: 8 casos ≥10M, −9% medio).
   Ventana: su cláusula (69,56M = su valor, ratio 1,00) se desbloquea el viernes 16/10 20:53, la congelación acaba a las 21:00 y el Real Madrid juega el domingo 18/10 a las 21:00: unas 48 h para clausularlo antes de su partido.
   Obstáculos: hace falta tener ~70M en caja (hoy 14,8M; las cláusulas no admiten deuda) y vender ~55M antes sin romper el once; el líder puede blindarlo (máx. 2 por jornada) y ya no sería comprable; sería un golpe al líder además de una inversión.
   Calcular a mitad de semana: qué se vendería (ofertas del 20:53 de martes a viernes) y si el neto sale (+10M esperados en 5 días a 1,0× contra la fricción de las ventas). Si no hay forma limpia de reunir el dinero, anotarlo como caso de estudio para la J10.
P. **Capital y jugadores caros** (consulta 13/10): con más patrimonio hay que pasar a jugadores más caros (solo 16 plazas; hoy ~14M de media por plantilla, a 700M serían ~44M). Vigilar con datos: las ofertas de ≥30M parecen peores (mediana 0,96×, n=15) y los
   suplentes caros no suben (ver N). Patrimonio: 253,9M el 5/10 → ~284M el 13/10 (caja 14,8M + plantilla 269,6M; la última fila de la tabla `wealth` es una foto de primera hora y sale más baja), unos +2,6M/día (+1,0%/día; últimos 4 días +3,4M/día). Llegar a 700M: ~69 días al 1,3%/día compuesto, ~90 al 1,0%, ~122 al ritmo lineal de 3,4M/día, ~185 al 0,5%.

**Más adelante**
I. Crédito en parones largos: HECHO el 13/10 (hasta el 20% en pujas; primera vez en el parón del 8 al 22/11): vigilar que se devuelva a tiempo (aviso 🔴 si no).
I2. **Permutas con deuda** (idea del usuario, 13/10; no urgente, queda para pendientes): comprar PRIMERO con una puja de mercado financiada con deuda y vender después la otra pierna (caso Camello/Hancko). Diseño acordado: deuda máxima del 10% del valor de la plantilla
   (el límite del juego es el 20% y no vale para cláusulas); solo con más de 48 h hasta el primer partido; vender la otra pierna debe dejar el saldo en positivo y el once legal; una sola operación a la vez; el saldo tiene que estar en positivo justo antes
   de empezar la jornada (si no, no se puntúa), así que no se hace si queda un único ciclo de ofertas para vender; estreno con margen de varios días.
J. Estrategia de las últimas ~8 jornadas.

**Dependen de ti**
K. Disparo extra de las 20:32 en cron-job.org (opcional; es un job aparte).
L. Recompensa diaria de 100K (sin ruta conocida).
M. Token de cron-job.org caduca el 14/06/2027; los datos del bot están en una rama pública (`EXPORT_DATA=0` para dejar de publicar).

## Cómo retomar (primeros 10 minutos de la próxima sesión)

```bash
python3 -m fantasy_agent pull                  # descarga el estado que publica el bot (rama `data`, cada 6 h)
python3 -m fantasy_agent review --cloud        # patrimonio, operaciones cerradas por origen, posiciones abiertas
python3 -m fantasy_agent offers --cloud        # distribución de ofertas + experimento de precio pedido (hasta el 12/10)
python3 -m fantasy_agent tune --cloud --deep   # parámetros y propuestas del autoajuste (modo shadow: NO aplica)
python3 -m fantasy_agent siege                 # ¿habría sido viable el bloqueo al líder?
python3 -m fantasy_agent learn-rivals          # cómo operan los rivales y qué rinde en esta liga (tarda ~1 min)
```

Y mirar: `errors` dentro de `data/state.json` tras el `pull` (trazas de los pasos que fallaron), `git log --oneline -15`, las ejecuciones de GitHub Actions (fallos "not acquired by Runner" =
incidencia de GitHub, no del código) y los puntos reales de la jornada 8 (viernes 9/10).
**Antes de tocar reglas, compara con estos números** (referencia del 5/10, `review`): patrimonio 253,8M
(saldo 29,6M + plantilla 224,2M); compras por puja desde el 26/09 −11,7M (8 operaciones), por cláusula +5,2M (4);
sin vender: +1,1M sobre lo pagado.

## Puntos de fuga, por prioridad

### 1. Pagar prima al comprar y perderla al revender  — *medir primero*
Evidencia: pujas hasta +18% sobre el valor (Soria 46,65M por 39,5M; Gueye 39,8M por 34,6M) → −11,7M. Cambios ya hechos
(4–5/10): techo de puja +12%, base +3%, y un fichaje solo se hace si `puntos×3 jornadas×0,3M + subida esperada − (prima + 5%)×coste > 0`.
**Verificar**: en `market_bids` (con `ask`) la prima media pagada y el % de pujas ganadas desde el 4/10; resultado de las compras
posteriores. **Decidir**: ¿pujar al precio exacto cuando no hay otra puja? (el autoajuste ya recoge el porcentaje de victorias).

### 2. Capital inmovilizado en jugadores que no rinden en proporción — *hipótesis, sin probar*
Evidencia: David Soria (portero) 39,2M de valor y −7,5M sobre lo pagado; un portero barato (Aitor Fdez 0,8M) puntúa menos pero la
diferencia de puntos no parece justificar 39M parados (la inversión en subida rinde ~+8%/semana en el histórico).
**Idea**: meter el coste de oportunidad del capital en `plan_acquisitions` (hoy solo hay `slot_cost`). **Verificar** con puntos
reales de la J8–J10: puntos por millón de cada jugador de la plantilla.

### 3. Rotación excesiva (spread)  — *medir*
Cada vuelta completa cuesta ~5% (ofertas medias 0,97× valor) + prima. Contar operaciones/semana y coste total en `review`.
**Idea**: tiempo mínimo de tenencia o umbral de venta que crezca con la prima pagada.

### 4. La inversión por momentum: ¿se cumple en real?
Backtest (201–300 jugadores, ~80 días): comprar subida fuerte y mantener hasta que se frena +72% de media (mediana +21%, ~19 días);
con buena forma +30% a 7 días. Validación temporal: se mantiene en la 2.ª mitad. **Aún no hay operaciones reales cerradas** (Johnny −1,0M,
Terrats −2,2M sin vender). **Verificar** en `review --cloud` el retorno por origen `inversion`. **Si el real es peor que el coste de
ida y vuelta (~5% + prima)**: bajar `INVEST_FRACTION_*` o apagarlo. Ojo: la media del histórico viene de pocos grandes ganadores.

### 5. Puntos: primera jornada con once válido (J8, 9–12/10)
Hasta J7 se sumaron 0 en J5–J7 (sin alineación guardable). **Verificar**: puntos reales vs `xpts`; alineación elegida vs la mejor a
posteriori; si 4-4-2 fue buena elección; peso del banquillo (`BENCH_WEIGHT`), de la forma reciente y de casa/fuera (`fixture_factor`).

### 6. Recompensa diaria de 100K — *depende del usuario*
~23M hasta mayo. No hay endpoint conocido (15 rutas, 404). Pasos para capturar la petición en `ESTADO.md`/conversación del 4/10.
Si la petición lleva firma del anuncio, no se puede automatizar.

### 7. Experimento: ¿de qué depende la oferta? (hasta el 12/10) — (c) descartada el 8/10
Mayol anunciado a ×2,0 su valor y Freeman a ×1,5; el resto a ×1,1. `offers --cloud` agrupa la oferta media por precio pedido y por
cuánto subió el valor desde el anuncio. Hipótesis: (a) valor actual, (b) valor al anunciar (idea del usuario), (c) precio pedido.
**Si (b)**: la reanunciación de risers (ya implementada) cobra más sentido. 8/10: Mayol (×2) y Freeman (×1,5) no recibieron
ofertas mayores que el resto → **(c) descartada**. Al acabar (12/10) quitar `ASK_EXPERIMENT` y decidir (a) vs (b).

### 8. Autoajuste en modo `shadow`
Calcula y guarda propuestas pero no aplica nada (`AUTOTUNE=on` para aplicarlas, `off` para apagarlo). **Decidir** con los datos si alguna
merece aplicarse. Hoy proponía: "fuerte+forma" 25%→24%, "anticipada" 8%→6,8% (la deja casi desactivada: rinde +5,6% a 7 días, menos que el coste).

### 9. Fiabilidad de GitHub Actions — 8/10: pasos aislados, cortes pasajeros no fallan, trazas exportadas
5/10: 4 ejecuciones fallaron con "The job was not acquired by Runner of type hosted" (infraestructura de GitHub). El disparo externo
(cron-job.org cada 15 min) ya compensa la mayoría; el riesgo es perder la ventana de las 20:53. Sin alternativa gratuita equivalente
evaluada. El token de cron-job.org caduca el **14/06/2027**.

### 10. Sin probar en real
Rechazar oferta de rival (`.../reject`), cláusula pagada al segundo, operación de bloqueo (casi nunca viable; es lo esperado). Si alguno falla,
saldrá como ❌ en Telegram. (Verificados el 10/10: subir cláusula propia y cancelar puja.)

### 11. Privacidad de los datos publicados
La rama `data` del repositorio (público) contiene ofertas vistas, pujas, compras y saldo diario; **no** contiene tokens ni datos de
Telegram. Desactivar con `EXPORT_DATA=0` en el workflow si no se quiere.

### 12. Copiar al líder: más capital a jugadores grandes en subida — *decidir con datos de la J8–J10*
Evidencia (8/10, `learn-rivals`): comprar con subida previa ≥10% en 7 días rinde +14% a +36% neto a 14 días (74–75% ganan);
el líder pone casi todo su dinero ahí y tiene 1,8× nuestro patrimonio. Hoy dedicamos a inversión el 25% del saldo libre (60% en
parón) y los fichajes por puntos solo cuentan la subida si el jugador ya está en subida fuerte. **Ideas**: (a) subir
`INVEST_FRACTION_NORMAL`; (b) que entre dos fichajes con puntos parecidos gane el que sube; (c) mantener ~10–15M de saldo
para las cláusulas que se abren a las 20:53 (los rivales tienen 50–80M; nosotros 1,4M y no podemos aprovecharlas).
**Medir antes**: el resultado real de las inversiones del bot (Yoel Lago, Terrats, Fofana, Zabiri, Deossa, Marc Roca) a 14 días.

### 14. Verificar pujas al final y portero de reserva
¿Ganamos más pujas y con menos prima desde el 8/10 (`market_bids`)? Si un cron se cae entre las 19:20 y las 20:50 se pierden las pujas de ese día: mirar en `errors` y en las
ejecuciones de esa franja. Portero de reserva: ¿rota solo antes del 24/10 y compra el más barato (≤0,8M) con paciencia?

### 15. Financiar jugadores del líder vendiendo los nuestros
El plan de compras solo usa el saldo; no contempla vender A para clausular B. El líder abre cláusulas pronto: Giuliano,
Hancko y Giménez (12/10), Barrenetxea (15/10), Kang-In Lee y Diomande (16/10). Con 1,6M no llegamos a ninguno. Idea: que
la rotación de capital (hoy solo suplentes que no suben, para inversiones) cubra también estos objetivos del líder con
cláusula ≤1,05×, y ejecutarlos justo antes de la congelación de jornada (no puede contraatacar por cláusula).

### 17. Golpe al líder antes de cada congelación — *verificar el 20/10*
Programado (ver ESTADO "Golpe al líder"). Verificar: ¿se ejecutó alguno?, ¿cuántos puntos le quitó de verdad (su once de esa
jornada vs el esperado)?, ¿repuso por mercado? Límite real: el saldo. Si nunca hay dinero, decidir si financiarlos vendiendo
titulares que ya no suben (hoy solo suplentes). Idea pendiente: priorizar los baratos con mucho efecto (H. González 2,5 pts por 4,9M).

### 18. Crédito en el parón de noviembre — *decidir el 20/10 si se deja al 10%, se sube al 20% o se apaga*
Se activa solo (8/11). Antes: probar `tick --dry-run` con el reloj del parón o revisar a mano que `_delever` vende bien. Riesgo
principal: que falle la devolución (0 puntos en la J13). Medir después: rendimiento de lo comprado a crédito vs ida y vuelta.

### 19. Estrategia según el momento de la liga
- Ahora (J8–J29): dinero y puntos a la vez; el dinero compra mejores jugadores, que dan más puntos.
- Últimas ~8 jornadas: el dinero vale cada vez menos (no se puede llevar a ningún sitio); pasar a todo puntos: dejar de
  invertir para revender, gastar el saldo en el mejor once posible, más golpes al líder (siege.stage_factor ya sube el riesgo).
- Última jornada: el dinero no vale nada; todo a puntos y a quitárselos al líder.
Pendiente programarlo (lo más sencillo: que INVEST_FRACTION y el peso de POINT_VALUE_M dependan de las jornadas que quedan).

### 16. Cláusula "tentadora"
Idea del usuario: subir nuestras cláusulas hasta donde un rival aún se arriesgue (≈1,10× para jugadores en subida, lo
máximo que han pagado), para que si la paga nos deje +5% neto (pagamos la mitad de la subida). Solo compensa si la
probabilidad de que la paguen es alta. Decidir con `clause_raise_test` y con qué jugadores nuestros intentan clausular.

### 13. Nuestros jugadores salen por cláusula a su valor: no es malo
El líder gana mucho siendo "clausulado" al final de la protección (cobra el valor entero, sin el ~3% de la venta). Encaja con
tu regla ("mejor que nos hagan cláusula a perder dinero"). Pendiente de probar: subir nuestra cláusula (pagas la mitad de lo
que sube) en jugadores que los rivales persiguen — ruta sin probar.

## Ideas descartadas (con motivo)
- Fase "económica vs competitiva": el usuario prioriza puntos siempre.
- IA gratuita (Gemini) para decidir: las decisiones son cálculos sobre números de la API; una regla fija es más predecible.
- Venta por riesgo de cláusula con pérdida: decisión del usuario (4/10): mejor que paguen la cláusula.
- Arbitraje "fichar caro y poner a la venta" sobre jugadores sin tendencia: ~+3% por ciclo, menos que el coste de ida y vuelta.
