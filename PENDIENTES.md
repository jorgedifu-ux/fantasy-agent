# Pendientes — solo lo abierto

> Actualizado el **24/10/2026**. Lo hecho y verificado está en `ESTADO.md`; la evidencia y las ideas antiguas, en `ARCHIVO_PENDIENTES.md`.
> Orden de prioridades del bot (cerrado el 18/10): 1) once legal siempre · 2) no regalar un titular en subida a un rival · 3) puntos · 4) dinero.

## Calendario
- **Jue 29/10 21:00 → vie 30/10 21:00** congelación de cláusulas; **vie 30/10 21:00** empieza la J11 (Aitor Fdez y Gulácsi, porteros de Josinho, quedan libres; ver `siege`).
- **Sáb 31/10 19:42** se abre la cláusula de Lamine Yamal (Josinho, 194,7M).
- **5/11** probar `tick --dry-run` / `_delever` antes del parón; **8–22/11** parón: crédito hasta el 20% solo para pujas de inversión.

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
**Reglas confirmadas el 26/10.** (1) Los puntos de un jugador vendido DESPUÉS de empezar la jornada siguen contando para el once registrado (J10: Unai López y G. Villar, vendidos el 24/10, sumaron sus 4 y 1 pts: 40 = suma exacta). (2) Las ofertas de LaLiga valen 24 h (llegan a las 20:53): la de las 20:53 del viernes se puede aceptar después de empezar la jornada sin perder esos puntos. (3) **La API deja subir la cláusula propia mucho más del 20%**: Bil Nsongo +3M (×1,34), cobró la mitad (1,5M). Tope real sin averiguar (probar con un jugador de verdad antes de contar con él).
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
