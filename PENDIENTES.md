# Pendientes y puntos de fuga — para retomar con datos

Actualizado el **8/10/2026** (revisión completa en `ESTADO.md`, "Revisión del 8/10"). Complementa a `ESTADO.md` (qué hace el bot y qué está verificado). Aquí
está lo que **todavía puede mejorar**, con la evidencia que hay y cómo comprobarlo la próxima vez.

## Próximas revisiones (fechas)
- **Revisión principal acordada con el usuario: lunes 20/10.** Si antes llega un 🔴 o muchos ❌ por Telegram, antes.
- **Lunes 13/10** (tras la J8 y el fin del experimento de precio): puntos reales de la J8 vs esperados; ¿se pujó en
  el último minuto y se ganó con menos prima? (`market_bids`); resultado de `clause_raise_test`; quitar `ASK_EXPERIMENT`.
- **Lunes 20/10** (tras la J9; primeras compras del bot con 14 días: Yoel Lago 17/10, Terrats y Fofana 19/10): decidir
  % a inversión, saldo reservado para cláusulas de las 20:53, política de "cláusula tentadora" y si vender para
  financiar jugadores del líder (punto 15).

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
Rechazar oferta de rival (`.../reject`), subir cláusula propia (`PUT /buyout/player`), cancelar puja por lesión, cláusula pagada al segundo,
operación de bloqueo (casi nunca viable; es lo esperado). Si alguno falla, saldrá como ❌ en Telegram.

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

### 14. Verificar pujas al final y portero suplente
¿Ganamos más pujas y con menos prima desde el 8/10 (`market_bids`)? ¿Se ha fichado un segundo portero? Si un cron se cae
entre las 19:20 y las 20:50 se pierden las pujas de ese día: mirar en `errors` y en las ejecuciones de esa franja.

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

### 20. Exploración del 9/10 (sin cambios de código) — decidir el 20/10
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
