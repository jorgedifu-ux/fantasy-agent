# Pendientes — solo lo abierto

> Actualizado el **22/10/2026**. Lo hecho y verificado está en `ESTADO.md`; la evidencia y las ideas antiguas, en `ARCHIVO_PENDIENTES.md`.
> Orden de prioridades del bot (cerrado el 18/10): 1) once legal siempre · 2) no regalar un titular en subida a un rival · 3) puntos · 4) dinero.

## Calendario
- **Lun 19 21:02** se abre Fofana · **mar 20 20:53** Zabiri · **mié 21 20:53** Deossa · **vie 23 21:03** Ilaix (el bot vende con la oferta de las 20:53 y, si no llega, blinda o sube la cláusula a ×1,20).
- **Mar 20/10 03:00** cierra la J9 · **mar 20** revisión conjunta.
- **Jue 22 21:00 → vie 23 21:00** congelación de cláusulas; **vie 23 21:00** empieza la J10 (hay que tener once legal: hoy faltan defensas).
- **Mar 27 20:53** queda libre Gulácsi, portero de Josinho → primera ventana real del bloqueo (J11).
- **8–22/11** parón: crédito hasta el 20% solo para pujas.

## 0) Hecho el 19/10 16:50 (manual, con OK del usuario)
- **Diomande fichado por cláusula (80,14M, a Josinho)**: su blindaje de 24 h había expirado a las 16:16. Caja 3,7M, plantilla 13. Protegido 14 días.
- Las ventas de la noche (Fofana, Herrero, Luismi, Abel, Salinas ≈72M) salieron de reglas independientes, no de ahorrar para él; el planificador lo daba por «inalcanzable» (presupuesto 95% de caja y tope de inversión 25%).
- Abel: la pérdida se produjo al pagar su cláusula (×1,27) el domingo, no al venderlo; con Luismi y Nsongo, ≈2,9M.
- **Pendiente derivado**: reconstruir la J10 sin caja (defensas: Hancko + Salinas + Rockson; vender si hace falta, p. ej. Zabiri 37M) y programar el modo «estrella» (sección B) para que el bot lo haga solo.

## 0b) Revisión del 22/10 (datos de la nube de las 12:01)
- Patrimonio **320,3M** (+32,9M en 7 días; caja 23,7M). Puntos 183 contra 396 de Josinho (brecha 213, era 222). Diomande ya +7,7M (87,8M).
- Ventas buenas: Zabiri +11,1M, Fofana +7,1M. Operaciones cerradas: **por cláusula +47,2M (24), por puja −6,4M (17)**: las pujas pierden dinero de media; revisar antes de pujar más fuerte (A6).
- **Soria sin blindaje (21/10)**: `shield_target` descartaba a quien tuviera la cláusula >×1,12 (Soria ×1,19, 7,4 pts/jornada). Arreglado: a un jugador clave (≥3 pts/jornada) se le blinda hasta ×1,25 (`KEY_SHIELD_RATIO`). Rivales: de 27 cláusulas pagadas por rivales, solo 4 por encima de ×1,12 y ninguna a un jugador de ≥20M por encima de ×1,15.
- Nota: los puntos de una jornada cuentan para quien tenía al jugador en el once al empezar; un clausulazo tras el inicio no quita puntos de esa jornada, solo las siguientes. El hueco peligroso es entre el inicio de una jornada y la congelación de la siguiente.

## A) Para la revisión del 20/10
1. **Los que se abren** (Terrats vendido a 20,9M; faltan Fofana, Zabiri, Deossa, Ilaix): ¿ventas con la oferta diaria?, ¿cláusula a ×1,20 y su coste?, ¿alguien la pagó? Pendiente: comprobar que la API deja subir tanto (solo probado +10%).
2. **Bitácora** (`kv.decisions`): que explique cada venta; comprobar «recambio previsto» y la forma con la jornada en curso (Deossa debe bajar al confirmarse sus puntos).
3. **Reconstruir J10**: 46M en caja; candidatos Navarro (27,5M, se abre lun 22:27) e Ibañez (18,8M, mar 20:53); no hay defensas/porteros buenos disponibles. Decidir qué compra el bot.
4. **Umbrales** con J8–J10: venta 1,05×, «clave» 1,25×, rivales 1,30×, techo de puja +12%, factor de alineación probable (80% = titular normal, ×0,2–×1,15, provisional).
5. **Permutas**: Giménez→Barrenetxea prometía +6,9M y lleva +0,8M: calibrar el cálculo; valorar más permutas del mismo tipo.
6. **Pujas**: 9 pérdidas (el ganador pagó de media +10%); propuesta sin aplicar: pujar el p75 de los rivales (tope +12%) por objetivos de ≥3 pts. Decidir con ~15 pujas.
7. **Titulares de relleno**: tres de los once de J9 tenían 3,3–4,0 de media; ver cómo evitarlo (planificador).
8. **Crédito del parón** (8/11): dejar al 10%, subir al 20% o apagar; probar antes `tick --dry-run`/`_delever`.

## B) Alcanzar a Josinho (brecha 217 pts, 29 jornadas)
- Palancas: no volver a puntuar 0 · más puntos por jornada · bloqueos de portero (`python3 -m fantasy_agent siege`; parado mientras nuestro once esté incompleto) · clausulazos a sus titulares cuando salga la cuenta.
- Sin bloqueos y con media igual, ~3% de alcanzarlo; con 3 bloqueos y +3 pts/jornada, ~57% (modelo simple, revisar cada jornada).
- Idea: **modo «ahorrar para una estrella»** (caso Diomande, +12,5% en 5 días que no pudimos comprar).
- **Financiar clausulazos del líder vendiendo titulares que ya no suben** (hoy solo suplentes) y ejecutarlos justo antes de la congelación.
- **Permutas con deuda** (diseño acordado, sin programar): deuda máx. 10% del valor de plantilla, >48 h de margen, una operación a la vez, saldo positivo antes de la jornada.

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
