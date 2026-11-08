# Pendientes — solo lo abierto

> Actualizado el **8/11/2026**. Lo hecho y verificado está en `ESTADO.md`; las revisiones y estudios antiguos, íntegros, en `ARCHIVO_PENDIENTES.md`.
> **Prioridades del bot** (cerradas el 18/10; mandan sobre cualquier regla): 1) once legal siempre · 2) no regalar a un rival un jugador que sube y puntúa · 3) puntos · 4) dinero. **La liga se gana a puntos**: el dinero es un medio.

## 1. Dónde estamos (8/11)
- **Dinero**: patrimonio ~434M (caja 35M, plantilla ~400M); +57M en 7 días, +70% desde el 5/10. Hemos recortado a todos en dinero.
- **Puntos**: 300 contra 539 de Josinho (brecha ~239, J12 a medias). La J11 la ganamos 63–53 (primera vez). Con 26 jornadas por delante hay que puntuar unos 9 más por jornada que él: la palanca es tener estrellas y no regalar puntos.
- **Calendario**: la J12 acaba hoy a las 21:00; **parón sin partidos hasta la J13 (vie 20/11)**.
- **Qué hace el bot ahora** (para situarse): vende con la oferta diaria de las 20:53 · blinda (gratis, 24 h, 2 por jornada) a quien más se pierde en puntos o en subida, al segundo de abrirse su cláusula · **modo inversión** (desde que el siguiente partido queda a ≥7 días: 60% del saldo libre en jugadores que suben y hasta ~80M de crédito para pujas) · **modo estrella** (cada día mira si fichar a una estrella por cláusula mejora el once ≥3 pts/jornada; si sí, vende lo necesario y la compra solo) · plantilla de hasta **23** (el juego permite 24) · guarda el once definitivo a 2 min del primer partido.

## 2. Calendario de lo que viene
| Cuándo | Qué |
|---|---|
| Dom 8/11 20:53 | Ofertas de LaLiga del día; acaba la J12 (21:00). Primer día completo con modo inversión y modo estrella. |
| Jue 12/11 | Se abre la cláusula de **Dituro**, nuestro único portero de verdad (quitarlo cuesta 6,4 pts): debe blindarse al segundo. |
| Mar 17/11 ~21:00 | El bot empieza a devolver el crédito (vende desde 72 h antes de la J13): hay que estar en saldo positivo al empezar la jornada o se puntúa 0. |
| Jue 19/11 21:00 → vie 20/11 21:00 | Congelación de cláusulas. |
| **Vie 20/11 21:00** | **J13.** Comprobar el once final de las 20:58 (ver sección 3). |
| 14/06/2027 | Caduca el token de cron-job.org. |

## 3. Comprobaciones con fecha (qué mirar y dónde)
- **9/11 · Rafita**: se vendió a mano el 8/11 (7,22M, ×1,04, oferta viva) porque la regla «peso muerto» la aceptaba y el bot no lo hizo en las ejecuciones de la noche. **Averiguar por qué** mirando `kv.decisions` en la próxima publicación de datos (`python3 -m fantasy_agent pull`).
- **9/11 · Primer informe de los modos nuevos**: compras con origen «inversión» (resultado y crédito usado, `review --cloud`), decisiones «estrella» y «plazas» (`kv.decisions`). Sin historial real todavía: revisar cada día.
- **12/11 · Dituro**: ¿blindado al segundo (decisión «blindaje … al segundo» en la bitácora)? Si no quedan blindajes, decidir si subir su cláusula.
- **17–19/11 · Crédito**: saldo ≥ 0 antes de la J13; probar con `tick --dry-run` el mismo 17/11.
- **20/11 · Once final** (primera vez real): a las 20:58 debe salir el aviso «⏱️ Once revisado a 2 min del primer partido»; si ganamos un jugador a las 20:53, tiene que estar en el once.
- **20/11 · Alineaciones confirmadas**: futbolfantasy publica ~1 h antes quién es titular y quién suplente («Alineaciones confirmadas»); el bot las lee como 97%/3%. Hay que ver con un partido real que un confirmado-suplente sale del once. Solo sirve para el primer partido: con la jornada empezada el once no se toca (se puntúa con el del primer pitido).

## 4. Decisiones que esperan al usuario
- **Margen mínimo para sustituir a un titular** (propuesta: ≥1,5 pts esperados). Motivo: el error de predicción por jugador ronda 1,2 pts; cada cambio con menos margen es ruido más rozamiento (comprar a ×1,0 y vender a ×0,95–1,0).
- **Subir la cláusula de un jugador clave** (sin tope; cuesta la mitad de lo subido). Falta saber con qué probabilidad paga un rival según el múltiplo: `exposure_log` lo mide; decidir con ≥2 semanas de datos. Dato suelto: Josinho pagó ×1,34 por Nsongo (12M, subida nuestra) el 4/11.
- **Disparo extra de las 20:32** en cron-job.org (opcional): da margen al once final si GitHub retrasa el pase de las 20:46.

## 5. Datos que el bot va recogiendo (estudios en marcha)
| Registro (`kv`) | Qué guarda | Para qué |
|---|---|---|
| `star_log` | Estrellas visibles (mercado o cláusula abierta; media ≥7,5, ≥15M) con forma, tendencia, precio y si podíamos pagarla | Frecuencia y precio de las estrellas; afinar el modo estrella |
| `exposure_log` | Cada día, cláusulas abiertas o recién blindadas de toda la liga (múltiplo, subida, blindaje) | Probabilidad de que se pague una cláusula según múltiplo → ¿compensa subirla? |
| `decisions` | Cada venta/hold, blindaje, plan estrella, «sin plaza» | Explicar y auditar cualquier decisión |
| `swap_log` | Permutas propuestas (solo avisa, no ejecuta) | Backtest: prometían +92,9M, realizaron +16,7M (18%); ejecutar solo con promesa en dinero ≥5% del coste |

## 6. Revisión continua del modelo (a petición del usuario: repetir con cada jornada y más datos, para TODO)
Cambiar **una cosa cada vez** y anotar aquí fecha y resultado. Valor de referencia del 8/11 (12 jornadas):

| Tema | Ahora | Referencia 8/11 | Qué mirar |
|---|---|---|---|
| Predicción de puntos | `FORM_WEIGHT` 0,15 (antes 0,40) | Media y mezcla acierta igual (MAE ~3,5); la forma sobrevalora a los «calientes» (7,1 pred. → 6,0 real) | Reentrenar con más jornadas; encogimiento por valor |
| Rival en el once | Posición en la tabla (top-4 ×0,80) | Titulares: 4,0 pts ante ataques fuertes vs 5,2 ante flojos; casa/fuera sin efecto | Goles a favor del rival (últimos 5), puntos que concede por posición |
| Quién juega | Prob. de futbolfantasy; confirmados 97%/3% | Titular fijo juega ≥60' el 76% de las veces; rotación 54%; suplente 16% | Backtest de probabilidades |
| Inercia de la subida | `DRIFT_5D`, `TIER_MULT` | +1–2%/día → +5,7% a 5 días (83% suben); ≥3% → +23%; los caros suben menos en % pero más en € | Recalibrar tablas |
| Ofertas de LaLiga | Umbral ×1,05 | Mediana ×0,997, p90 ×1,077, máx ×1,10 (485 ofertas); óptimo ×1,04 | Umbral y oferta mínima por estrella (×1,08) |
| Compras | Pujas con prima p75, cláusulas ≤×1,12 | Cláusulas +57M; pujas −6,3M (casi todas antiguas) | Resultado por origen con cada tanda de compras |
| Blindaje y estrella en subida | Se miden en euros (`expected_5d_gain`): blindar ≥1M€; estrella ≥2M€ | Hancko, Diomande y Freeman acertados en orden de magnitud | Umbrales de 1M€ y 2M€ |
| Once elegido | Mejor 4-4-2/… por puntos esperados | Todos los modelos ~49–50 pts en plantillas aleatorias; el mejor posible, 57 | Más información (quién juega) mejora más que más modelo |
| Modo inversión | 60% del saldo libre + crédito 20% | Ligas: ≥25% en 7 días → +28% a 14 días (82% aciertan) | Resultado real de las compras «inversión» |
| Modo estrella | Umbral +3 pts/jornada, fricción 5% | Con ~400M el mejor once ya lleva una estrella; con ~600M, dos | Umbrales con más jornadas |

## 7. Ideas y mejoras abiertas
**Alineación**
- Mejorar la elección del once: probar el rival por goles a favor/en contra (ver tabla), y la «sofisticación» del criterio de los 4 primeros. Backtest con plantillas aleatorias y con nuestras alineaciones reales.
- Efecto suplente (baratos <4M cuando falta el titular) y lesiones por tipo (corta/larga: la API solo da `playerStatus`; inferir por días en estado no-ok).

**Plantilla y dinero**
- **Plazas**: tope 23 desde el 8/11. Medir cuántas compras se pierden por falta de plaza (decisiones «sin plaza») y cuántos suplentes se venden «para hacer sitio»; reservar 1 plaza libre se mantiene.
- **Peso muerto**: regla activa para suplentes sin puntos con cláusula inalcanzable (se vende a ≥×0,97 si baja, o si lleva ≥7 días por debajo de lo pagado). Vigilar que no haya más casos tipo Rafita.
- Coste de oportunidad del capital parado en el planificador (hoy: caja sin uso).
- Estrategia de las últimas ~8 jornadas: todo a puntos (`INVEST_FRACTION` y `POINT_VALUE_M` según jornadas restantes).
- Autoajuste `shadow`: decidir si alguna propuesta merece aplicarse (hoy ninguna: diferencias dentro del ruido).
- Permutas con deuda (diseño acordado, sin programar): deuda máx. 10% del valor de plantilla, >48 h de margen, una operación a la vez, saldo positivo antes de la jornada.

**Frente al líder**
- Bloqueos de portero (`python3 -m fantasy_agent siege`): no viables el 24/10 (certeza 55% <60%, faltan plazas, no compensa). Repetir cuando Josinho tenga porteros con cláusula libre.
- Financiar clausulazos al líder vendiendo titulares que ya no suben; ejecutarlos justo antes de la congelación.
- Yamal (Josinho): descartado el 26/10 (habría que vender tres titulares y recuperaría su cláusula en el parón); lo cubre el modo estrella si algún día sale a cuenta.

**Protección**
- Hoy solo hay 2 blindajes por jornada y duran 24 h: se reparten por valor entre lo que se abre en las próximas 2 semanas. Subir cláusulas es la defensa duradera pero cuesta dinero: ver sección 4.

**Telegram (aparcado)**
- Horas del resumen (9/14/19/22), qué es urgente, consultas que faltan (`/ofertas`, `/valor`), preguntas con botones, gráficas por jugador, proyección de la jornada, aviso al cerrar cada jornada.

## 8. Del lado del usuario
- Recompensa diaria de 100K: sin ruta conocida en la API (15 rutas probadas, 404).
- La rama `data` es pública (`EXPORT_DATA=0` para dejar de publicar).
- El token de GitHub guardado en el Mac caducó una vez (26/10): si `git push` pide contraseña, crear un token clásico con permiso `repo` y usar la app Terminal de macOS (no el panel integrado).

## 9. Cómo retomar (primeros 10 minutos)
```bash
python3 -m fantasy_agent pull                  # estado que publica el bot (rama `data`, cada 6 h)
python3 -m fantasy_agent review --cloud        # patrimonio, operaciones por origen, posiciones abiertas
python3 -m fantasy_agent offers --cloud        # distribución de ofertas
python3 -m fantasy_agent tune --cloud --deep   # autoajuste (modo shadow: NO aplica)
python3 -m fantasy_agent siege                 # ¿viable el bloqueo al líder?
python3 -m fantasy_agent learn-rivals          # cómo operan los rivales (~1 min)
```
Mirar también `kv.errors`, `kv.decisions`, `kv.star_log` y `kv.exposure_log` tras el `pull`, `git log --oneline -15` y las ejecuciones de GitHub Actions («not acquired by Runner» = incidencia de GitHub). Cuidado con `tick --dry-run` en local: puede tardar varios minutos (espera dentro del job si hay algo programado al segundo y lee futbolfantasy sin caché).

## 10. Hecho recientemente (detalle en `ESTADO.md`)
- 8/11: modo estrella; tope de plantilla 23; peso muerto (Rafita); estrella en subida solo si queda blindaje; blindajes por valor; registros `star_log`/`exposure_log`; once final a 2 min; modo inversión desde ya.
- 7/11: blindaje por subida medido en euros; error de lectura de ofertas con reintento.
- 1/11: forma reciente 0,40→0,15 (backtest de 1.286 jugador-jornada); estrella en subida.
- 26/10: blindaje al segundo; revalorización a cero corregida; Yamal descartado.
