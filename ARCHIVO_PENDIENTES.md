# Archivo de pendientes (copia íntegra del 18/10/2026)

> Versión anterior de PENDIENTES.md, guardada tal cual por si hace falta la evidencia. Lo vigente está en PENDIENTES.md.

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
X. **Telegram** (18/10, montado; falta afinarlo con el usuario): resumen a las 9/14/19/22 h, panel fijado, consultas y gráficas (ver ESTADO «Cómo hablar con él»). Pendiente de decidir con él: horas del resumen, qué es urgente, más consultas (`/ofertas`, `/valor <jugador>`),
   preguntas con botones («¿quieres enterarte ya?»), gráficas por jugador. Las consultas tardan hasta 15 min en contestarse (no hay servidor).
Y. **Alineación probable de futbolfantasy** (18/10, HECHO la misma noche: `ap.xpts` y la alineación la usan; el 80% es un titular normal, factor entre ×0,2 y ×1,15, provisional, revisar el 20/10; cubre pocos jugadores hasta que se publican las alineaciones): hoy solo se usa en el informe `--news`. Para Real Madrid–Sevilla da a Diomande «titular 60%» y no incluye a Vinicius (sancionado); la API solo dice `playerStatus` (`suspended` hasta que cumple). Enlaza con C (probabilidad de ser titular al fichar) y N
   (efecto suplente). El bot NO modela a quién sustituye cada uno: valora por puntos medios y tendencia.
Z. **¿Podemos alcanzar al líder?** (18/10, a revisar cada jornada): brecha de 217 pts con 29 jornadas por jugar (J10–J38). Modelo simple (jornada ≈ N(μ, 22)): igualando su media solo ganamos ~3%; hace falta +7,5 pts/jornada sobre él para el 50%. Cada bloqueo de portero vale ~50 pts (sin once legal la jornada puntúa 0; lo
   comprobamos en J5–J7): con 3 bloqueos y media igual, ~28%; con 3 bloqueos y +3 pts/jornada, ~57%. Bloqueos: parado mientras nuestro once esté incompleto; Josinho tiene 2 porteros (Aitor Fdez libre desde dom 18 20:53; Gulácsi, 10,4M, bloqueado hasta mar 27 20:53), así que la primera ventana real es la J11
   (congelación ~jue 29/10). Palancas: (1) no volver a puntuar 0 (once siempre legal); (2) más puntos por jornada (alineación probable ya integrada, recambios de calidad); (3) bloqueos (`python3 -m fantasy_agent siege`); (4) clausulazos a sus titulares cuando la cuenta salga.
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

---

# Volcado del 8/11/2026: PENDIENTES.md tal como estaba antes de la limpieza

## (contenido anterior de PENDIENTES.md)

> Actualizado el **1/11/2026**. Lo hecho y verificado está en `ESTADO.md`; la evidencia y las ideas antiguas, en `ARCHIVO_PENDIENTES.md`.
> Orden de prioridades del bot (cerrado el 18/10): 1) once legal siempre · 2) no regalar un titular en subida a un rival · 3) puntos · 4) dinero.

## Calendario
- **Jue 29/10 21:00 → vie 30/10 21:00** congelación de cláusulas; **vie 30/10 21:00** empieza la J11 (Aitor Fdez y Gulácsi, porteros de Josinho, quedan libres; ver `siege`).
- **Sáb 31/10 19:42** se abre la cláusula de Lamine Yamal (Josinho, 194,7M).
- **5/11** probar `tick --dry-run` / `_delever` antes del parón; **8–22/11** parón: crédito hasta el 20% solo para pujas de inversión.

## 00000) REVISIÓN CONTINUA DEL MODELO (a petición del usuario, 8/11): repetir con cada jornada que pase y más datos, para TODO
Reejecutar y comparar con lo anotado en ESTADO (8/11): (1) predicción de puntos: media vs forma (`FORM_WEIGHT`), encogimiento por valor, efecto del rival (goles a favor del rival en sus últimos 5 partidos: −1,1 pts frente a ataques fuertes), casa/fuera (hoy sin efecto), P(≥60 min); (2) inercia de la subida a 5 días por tramo (`DRIFT_5D`, `TIER_MULT`); (3) ofertas de LaLiga (umbral ×1,05, mediana ×0,997); (4) pujas vs cláusulas (resultado por origen); (5) umbrales de blindaje, estrella en subida (2M€) y oferta mínima ×1,08; (6) cuánto se paga de más en cláusulas y pujas; (7) calidad del once elegido frente al mejor posible; (8) `star_log` (frecuencia de estrellas en el mercado) y `exposure_log` (qué cláusulas se pagan según múltiplo, tendencia y blindaje: base para decidir si subir cláusulas compensa); (9) modo inversión (resultado de las compras con origen «inversión»). Cada revisión se anota aquí con fecha y se cambia una cosa cada vez.

## 0000001) Modo estrella: ¿cuándo compensa? (estudio del 8/11, 12 jornadas: repetir con más datos)
- Prueba: con cada presupuesto se monta el mejor once 4-4-2 usando solo la media anterior (precios de hoy) y se mide lo que puntuó en las 2 jornadas siguientes (4 pruebas). **Hasta ~350M el mejor once no lleva estrellas (obligar a una resta ~3 pts); a 450M lleva siempre una; a 600M, dos.** Nuestro patrimonio es ~430M: justo en el umbral.
- Hoy comprar a Mbappé (181M) vendiendo cuatro titulares deja el once esperado en 67,1 frente a 67,8 (o 63,3 si rinde 9): no compensa. Sí compensará cuando el patrimonio suba (~480–500M) o si se rehace el once entero con el mercado.
- Propuesta (pendiente del OK del usuario): el modo estrella monta cada día el mejor once posible con el patrimonio total (descontando ~5% de fricción por compras/ventas) y compra la estrella solo si mejora ≥3 pts/jornada, vendiendo lo que haga falta (opción B). Registro actual: `star_log`.

## 000001) Plazas libres y tamaño de plantilla (reflexión pedida por el usuario el 8/11, a partir de Cepeda)
- Cepeda: comprado por cláusula a Pep el 7/11 15:01 (3,57M) y vendido el 8/11 00:31 (3,62M, +0,04M) a la primera oferta, probablemente por la regla «plantilla llena → liberar sitio» (el bot cuenta 16 como llena y tenemos 17–18). Sin coste real, pero es un vaivén.
- `MAX_SQUAD=16` es un objetivo del bot, no el límite del juego: una guía lo da como **24** (sin confirmar; mirar en las reglas de la app). Hay que decidir si el 16 sigue teniendo sentido ahora que el modo inversión necesita plazas (varias compras a la vez) y que empieza a haber dinero: opciones (a) mantener 16 como disciplina (pocos suplentes parados), (b) subirlo a ~20 y reservar 2 plazas libres para inversiones/estrellas, (c) plazas libres según caja.
- Medir en unos días: cuántas compras se pierden por falta de plaza y cuántos suplentes se venden «para hacer sitio».

## 00001) Mejorar la elección del once (anotado el 8/11; revisar en unos días con más jornadas)
- Hoy el rival cuenta por su posición en la tabla (los 4 primeros: ×0,80; el resto, ajuste lineal, `autopilot.fixture_factor`). El usuario duda de que «los primeros cuatro» sea la mejor forma de medirlo.
- Alternativas a comparar con backtest: goles a favor del rival en sus últimos 5 partidos (con 12 jornadas: titulares 4,0 pts frente a ataques fuertes y 5,2 frente a flojos), goles en contra por posición del jugador (defensas frente a delanteros), puntos que concede cada rival a cada posición, y mezclas. Medir con el once elegido en plantillas aleatorias (ver ESTADO 8/11) y con nuestras alineaciones reales.
- Solo se decide el once del pitido inicial del primer partido (con la jornada en juego no se puede cambiar).

## 0000) Para el 20/11 (J13) — anotado a petición del usuario
- **Comprobar el once final.** El bot debe esperar hasta las 20:58 (2 min antes del primer partido, 21:00), releer la plantilla y guardar el once. Mirar en la bitácora y en el chat que salió el aviso «⏱️ Once revisado a 2 min del primer partido».
- **Comprobar las alineaciones confirmadas.** futbolfantasy publica ~1 h antes quién es titular y quién suplente (sección «Alineaciones confirmadas»). Hay que ver que el bot lo lee bien: un jugador confirmado suplente debe salir del once y otro entrar. Hasta ahora no se ha visto esa página en un partido de LaLiga antes de empezar.
- Solo vale para el primer partido: una vez empezada la jornada el once no se toca.

## 000) Del 7/11 (J12 en juego; patrimonio 428,1M, +57M en 7 días; J11 ganada 63–53 a Josinho)
- Hecho: once final a 2 min del primer partido; alineaciones confirmadas leídas como 97%/3%. **Verificar el 20/11** (J13) en la bitácora y el chat que a las 20:58 el bot relee y guarda el once.
- **Modo inversión** (decidido por el usuario el 7/11: se activa ya, sin esperar al parón, y se mantiene el crédito al 20%): 60% del saldo libre y hasta ~80M de crédito desde que el siguiente primer partido queda a ≥7 días (`cli._invest_mode`). Sin historial real (0 compras con origen «inversión»): revisar cada día los resultados.
- Una sola portera de verdad (Dituro, pérdida 6,4 pts) y suplente de 0,6M; su cláusula se abre el jue 12/11 (blindaje al segundo). Comprar un portero de reserva antes del 20/11.
- Margen mínimo (≥1,5 pts esperados) para sustituir a un titular: sigue pendiente de decidir.
- **Estudio: ¿compensa subir la cláusula de un jugador clave?** (pedido por el usuario el 8/11, con Yamal/Josinho y Mbappé/Pep como referencia; coste = la mitad de lo subido, sin tope). Falta saber con qué probabilidad paga un rival según el múltiplo; `exposure_log` lo irá midiendo (≥2 semanas). Dato suelto: Josinho pagó ×1,34 por Nsongo (12M, subida nuestra) el 4/11.

## 00) Revisión del 1/11 (J11 en juego: 30 pts contra 38; J10: 40 contra 59; brecha 247)
- **Dinero**: patrimonio 384,3M (+54,8M en 7 días, +51% desde el 5/10; caja 54,2M, plantilla 330,1M); hemos recortado a todos en dinero; en puntos no (Josinho 500, nosotros 253). Yamal le aporta ~11 pts/jornada.
- **Qué falló en la J11**: (1) se vendieron titulares antes de empezar (Hancko +9 pts, Bryan +9, Soria +4, Ibañez 0, Agoumé 1) y el once registrado llevó rellenos (Belocian 0, Gayá 0, Requena 3); los refuerzos (Yoel Lago, Germán V.) llegaron el sábado, ya empezada la jornada, y solo suman desde la J12. (2) Los fichados por forma (Dituro 14→0, Pepelu 9→1, Germán 11→−1, Freeman 13→2, Javi R. 8→1) se desinflaron: la forma reciente pesaba demasiado. (3) Soria (media 6,6) se vendió porque el recambio recién comprado (Dituro, forma inflada) hacía que «perderlo» costara poco: círculo vicioso por la forma.
- **Cambios hechos**: `FORM_WEIGHT` 0,40→0,15; estrella en subida no se vende por menos de ×1,08; lectura de ofertas con reintento. Ver ESTADO 1/11.
- **Vigilar**: Diomande se abre lun 2/11 16:57; el blindaje al segundo lo cubre 24 h. Decidir si subir su cláusula (a ×1,3 cuesta ~16M) para cubrir el resto de la semana. Mbappé (Pep) se abre vie 6/11 20:53.
- **Idea abierta**: exigir un margen mínimo (≥1,5 pts esperados) para sustituir a un titular, porque el error de predicción por jugador es ~1,2 pts: cada permuta con menos margen es ruido más rozamiento.

## 0) Revisión del 24/10 (datos de la nube de las 18:02) — decisiones tomadas
- **Estado**: patrimonio **329,5M** (+34,9M en 7 días, +29,8% desde el 5/10; caja 58,9M, plantilla 270,7M). Puntos 200 contra 410 (brecha 210; J9: 37 contra 55). Sin los tres ceros de J5–J7 estaríamos a la par; ahora faltan ~11 pts/jornada.
- **Los que se abrían** (A1, cerrado): Fofana 31,3M (+7,1M), Zabiri 39,1M (+11,1M), Deossa ×1,10, Ilaix 29,2M (+8,6M), Mayol ×1,09: todo vendido por encima de su valor con la oferta de las 20:53; nadie fue clausulado y no hizo falta subir cláusulas.
- **Bitácora** (A2, cerrado): explica cada venta y cada «hold»; «recambio previsto» y forma con la jornada en curso funcionan.
- **J10** (A3, cerrado): once legal con 14 plazas, portero suplente (Marrero) y 4 defensas.
- **Umbrales** (A4, cerrado, sin cambios): 289 ofertas, mediana ×0,998, p90 ×1,08, máximo ×1,10; umbral óptimo ×1,042 frente a nuestro ×1,05 (diferencia irrelevante). El autoajuste propone bajar la «subida esperada» (0,25→0,227, 0,15→0,145, 0,08→0,065): diferencias dentro del ruido, no se aplica.
- **Pujas** (A6): las 19 pujas cerradas desde el 26/9 suman −6,3M y las 27 por cláusula +57,0M, pero casi todas las pujas son anteriores a la prima p75 y a la escalera de tiempos; las compras «puntos» registradas desde entonces van +12,3%. Se mantiene la regla y se revisa con las pujas que lleguen.
- **Bloqueo J11** (`siege`, 24/10): no viable. Nuestro portero Soria sería clausulable por Josinho, faltan plazas, certeza 55% < 60% y no compensa (~16M de beneficio frente a 17M de coste). Ver B.
- **Crédito del parón** (A8, decidido): se mantiene el 20% (`LEVERAGE_PCT`) solo para pujas de inversión en subida ≥25% (neto a 14 días +28%, 82% aciertan) y se prueba `_delever` con `tick --dry-run` el 5/11.
- **Revalorización a cero** (24/10): el panel «AYER» podía salir con todos a +0,0M si a las 00:20 solo parte de los jugadores tenía ya el valor del día nuevo. Arreglado: un día solo cuenta con ≥90% de los jugadores, un resultado a cero no se guarda y se recalcula cada 30 min. `reval` y `wealth_league` ya se exportan para poder verificarlo.
- **Soria** (21/10): `shield_target` descartaba cláusulas >×1,12. Ahora a un jugador clave (≥3 pts/jornada) se le blinda hasta ×1,25 (`KEY_SHIELD_RATIO`). De 27 cláusulas pagadas por rivales solo 4 pasaron de ×1,12, ninguna en un jugador de ≥20M por encima de ×1,15.
- **Diomande** (19/10): comprado a mano por cláusula (80,1M); hoy vale 91,8M (+11,7M). Lamine Yamal (Josinho, 194,7M, 14 pts/jornada) se abre el sáb 31/10 19:42, tras la congelación y la J11; fuera de alcance y sin tendencia.
- Los puntos de una jornada cuentan para quien tenía al jugador en el once al empezar: un clausulazo tras el inicio solo quita las siguientes. El hueco peligroso va del inicio de una jornada a la congelación de la siguiente.

## A) Pequeñas — cerradas el 26/10
1. **Permutas** (decidido: siguen en sombra, no se ejecutan). Backtest de las 14 propuestas únicas del `swap_log` a 7 días: prometían +92,9M y el valor realizó +16,7M (18%); las promesas gordas (Deossa→Castrín «+15,2M» sobre 11,6M de coste) son puntos × `POINT_VALUE_M`, no dinero, y no se comprueban. Ejecutar solo con una promesa en dinero ≥ 5% del coste y viendo dos semanas más de resultados.
2. **Titulares de relleno** (cerrado): en la J9 faltaban defensas y caja; con caja y plantilla completa el planificador ya no los necesita. Se vigila con la bitácora.
3. **Peores ventas** (cerrado): Gueye −7,1M, Lorenzo −2,5M, Dolan, Musso y Gayá son de septiembre y principios de octubre: pujas con prima alta y salida anterior a las reglas del 10/10 y 18/10. Nada que cambiar.

## B) Alcanzar a Josinho (brecha 210 pts el 24/10, 28 jornadas)
- Palancas: no volver a puntuar 0 · más puntos por jornada · bloqueos de portero (`python3 -m fantasy_agent siege`; parado mientras nuestro once esté incompleto) · clausulazos a sus titulares cuando salga la cuenta.
- Sin bloqueos y con media igual, ~3% de alcanzarlo; con 3 bloqueos y +3 pts/jornada, ~57% (modelo simple, revisar cada jornada).
- Idea: **modo «ahorrar para una estrella»** (caso Diomande, +12,5% en 5 días que no pudimos comprar).
- **Financiar clausulazos del líder vendiendo titulares que ya no suben** (hoy solo suplentes) y ejecutarlos justo antes de la congelación.
- **Permutas con deuda** (diseño acordado, sin programar): deuda máx. 10% del valor de plantilla, >48 h de margen, una operación a la vez, saldo positivo antes de la jornada.

## B2) Modo «estrella» — estudio del 26/10 (decidido: oportunista, no por defecto; hoy en sombra)
**Datos.** Puntos por partido según precio: <3M 1,6 · 3–8M 3,0 · 8–15M 3,6 · 15–30M 4,6 · 30–60M 5,7 · **60–100M 6,6 (peor tramo)** · **≥100M 11,5** (Raphinha 14,2, Yamal 12,7, Mbappé 12,0, Bellingham 9,3, Güler 9,1). Los de media ≥ 7,4 casi todos sin dueño en la liga: solo salen si LaLiga los pone en el mercado.
**Reglas confirmadas el 26/10.** (1) Los puntos de un jugador vendido DESPUÉS de empezar la jornada siguen contando para el once registrado (J10: Unai López y G. Villar, vendidos el 24/10, sumaron sus 4 y 1 pts: 40 = suma exacta). (2) Las ofertas de LaLiga valen 24 h (llegan a las 20:53): la de las 20:53 del viernes se puede aceptar después de empezar la jornada sin perder esos puntos. (3) **La API deja subir la cláusula propia mucho más del 20%**: Bil Nsongo +3M (×1,34), cobró la mitad (1,5M). Según el usuario no hay tope (se puede subir sin límite); coste siempre la mitad de lo que sube.
**Caso Yamal (se abre sáb 31/10 18:42, 196M): NO.** Para pagar 196M habría que vender Diomande + Hancko + Barrenetxea (~180M + 31M de caja). Para nosotros el once esperado pasa de 62,5 a 60,2 pts (−2,3); para Josinho de 69,0 a 58,0 (−11,0): balance +8,7 pts/jornada, pero (a) el bloqueo de 14 días acaba el 14/11, en el parón, y Josinho recupera 196M de caja para recomprarlo a ×1,00 salvo que subamos su cláusula: con lo que sobra solo llegaríamos a ~×1,15, que es lo que ya pagan; (b) solo lo tendríamos en la J12 (6–8/11), un único +9 pts; (c) se pierden la subida de Diomande (+17M en 7 días) y ~5–10M de diferencia en las ventas. Coste estimado 15–45M por ~9 pts.
**Valles (portero, 55M, hoy)**: media 9,3 pero forma reciente 4,7 y −8,8% en 7 días: no es estrella. Lección: la media de temporada engaña; contar siempre con forma y tendencia.
**Diseño acordado.** Una estrella se compra solo si (a) el dinero libre + lo que se vende sin romper el once cubre el precio, (b) el balance de puntos del once (`squad_value` antes/después) es ≥ +3 pts/jornada y mejor si quita puntos al líder, (c) forma reciente ≥ 8 y sin caída de 7 días, (d) se puede proteger tras comprar (blindaje al segundo + subir la cláusula con lo que sobre), (e) quedan ≥ 15 jornadas. Canjear Diomande (97M, media 6,1) por una estrella de ≥ 100M es la conversión eficiente. Próximas oportunidades a vigilar: Mbappé (Pep, 180M, se abre vie 6/11 21:53) y lo que salga al mercado (registro `star_log`, ya en marcha).
**Hecho**: `stars.py` registra cada estrella visible (mercado o cláusula abierta, media ≥ 7,5 y valor ≥ 15M) con forma, tendencia, precio y si la podíamos pagar. A mediados de noviembre habrá datos de frecuencia para fijar los umbrales.

## C) Mejoras del modelo (con más datos)
- **Efecto suplente** (suplentes baratos <4M cuando falta el titular): registrar casos en sombra con la alineación probable antes de programar.
- **Lesiones por tipo** (corta/larga): la API solo da `playerStatus`; inferir por días en estado no-ok cuando haya historial.
- **Rival**: casa/fuera confirmado (≈0,6 pts); el resto, ruido con 8 jornadas. Probar los goles encajados por el rival en sus últimos 3 partidos en lugar de la tabla (revisar con 15+ jornadas).
- **Capital y jugadores caros** cuando el patrimonio crezca (ofertas de ≥30M parecen peores: mediana ×0,96, n=15).
- **Coste de oportunidad del capital parado** en el planificador (46M sin usar).
- **Estrategia de las últimas ~8 jornadas**: todo a puntos (`INVEST_FRACTION` y `POINT_VALUE_M` según jornadas restantes); programarlo.
- **Autoajuste `shadow`**: decidir si alguna propuesta merece aplicarse.
- **Cláusula «tentadora»** y **cláusula propia a ×1,20** como política (ver A1).

## D) Telegram (aparcado por ahora)
- Decidir horas del resumen (9/14/19/22), qué es urgente y qué consultas faltan (`/ofertas`, `/valor`).
- Preguntas con botones («¿quieres enterarte ya?»); gráficas por jugador.
- Ideas ofrecidas: proyección de la jornada, aviso al cerrar cada jornada, jugadores clave de Josinho que le quedan.

## E) Del lado del usuario
- Disparo extra de las 20:32 en cron-job.org (opcional, job aparte).
- Recompensa diaria de 100K: sin ruta conocida en la API (15 rutas probadas, 404).
- El token de cron-job.org caduca el **14/06/2027**; la rama `data` es pública (`EXPORT_DATA=0` para dejar de publicar).

## Cómo retomar (primeros 10 minutos)
```bash
python3 -m fantasy_agent pull                  # estado que publica el bot (rama `data`, cada 6 h)
python3 -m fantasy_agent review --cloud        # patrimonio, operaciones por origen, posiciones abiertas
python3 -m fantasy_agent offers --cloud        # distribución de ofertas
python3 -m fantasy_agent tune --cloud --deep   # autoajuste (modo shadow: NO aplica)
python3 -m fantasy_agent siege                 # ¿viable el bloqueo al líder?
python3 -m fantasy_agent learn-rivals          # cómo operan los rivales (~1 min)
```
Mirar también `kv.errors` y `kv.decisions` tras el `pull`, `git log --oneline -15` y las ejecuciones de GitHub Actions
(«not acquired by Runner» = incidencia de GitHub). Referencia del 18/10: patrimonio ~301M (caja 46M + plantilla 255M).

