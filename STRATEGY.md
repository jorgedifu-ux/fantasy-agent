# Estrategia — LaLiga Fantasy

Reglas que usa el motor de decisión (`analysis.py`, `lineup.py`) para puntuar oportunidades
de mercado, clausulazos y alineación. Objetivo declarado del usuario: **empezamos por detrás**
(otros managers ya llevan jornadas jugadas), así que la prioridad durante la mayor parte de la
temporada es **acumular dinero** (fase económica); solo en las últimas jornadas el dinero deja
de importar y todo pasa a ser puntuar/ganar (fase competitiva).

## 1. Las dos fases de la temporada

- **Fase económica (mayoría de la temporada):** cada operación se juzga por si genera
  plusvalía o mejora el equipo sin descapitalizar. Preferir jugadores infravalorados en
  subida sobre estrellas caras. Guardar colchón de saldo para poder clausular cuando surja
  la oportunidad (ver §2) — no gastar hasta dejar el saldo a 0.
- **Fase competitiva (últimas ~3-5 jornadas, configurable):** el dinero deja de importar.
  Cambiar el criterio de puntuación a maximizar puntos esperados de la jornada, sin mirar
  ya revalorización ni ahorro. `analysis.py` debe leer una fecha/jornada de corte
  (`SEASON_PHASE_CUTOFF`) y cambiar de función de puntuación a partir de ahí.

## 2. Clausulazos a rivales

Fuente: guías de jornadaperfecta.com, futbolfantasy.com, analiticafantasy.com, asesoriasfantasy.com
(ver conversación). Resumen aplicable:

- **Solo compensa si la cláusula está por debajo de su valor real.** Umbral ya usado en el
  proyecto: cláusula ≤ ~1.2× el valor de mercado actual (`analysis.clause_alerts`,
  `max_ratio`). No subir de ahí aunque el jugador sea muy bueno.
  - Motivo: una cláusula pagada de más nunca se recupera — es la operación más irreversible
    del juego.
- **El mejor momento es tras una racha del jugador que el rival aún no ha ajustado** (la
  cláusula del rival no sube tan rápido como el valor de mercado cuando el jugador está en
  buena forma) — objetivo: jugadores en tendencia alcista con cláusula todavía barata.
- **Ataca cuando el rival no puede responder**: si pagar la cláusula te dejaría el equipo
  bien pero al rival sin saldo para reemplazar al jugador (su cuenta de saldo estimado <
  precio de mercado de un sustituto razonable en su misma posición), es mejor objetivo que
  uno que el rival puede reponer sin problema. Requiere estimar el saldo de rivales
  (ver TODO en README: "Estimar el saldo de los rivales a partir del historial de fichajes").
- **Prioriza piezas clave e insustituibles del rival** (su único delantero en racha, su
  portero titular) sobre piezas de rotación — el golpe estratégico pesa tanto como el
  económico.
- **Deja "cebos" propios**: no blindar jugadores tuyos prescindibles y fáciles de reponer;
  si un rival te los clausula, cobras y repones barato. No subir cláusulas propias salvo en
  jugadores de muy bajo valor ("parches") que no van a revalorizarse mucho igualmente.
- **Congelación de jornada** (ya modelado en `service.clause_freeze_window`): todas las
  cláusulas se bloquean 24h antes del primer partido de la jornada. Planea los clausulazos
  fuera de esa ventana.
- **Blindaje** (`isShielded`): un jugador recién comprado por el rival queda blindado 14
  días — no es objetivo aunque su cláusula parezca barata; comprobar `SquadSlot.clause_open`
  antes de proponer nada.

## 3. Cuándo fijar el once (timing, no solo contenido)

El once final **no se fija en automático hasta el día antes de que arranque la jornada**
(ventana configurable, por defecto las últimas 24h antes del primer partido — la misma
ventana que ya usa `service.clause_freeze_window` para las cláusulas). Fijarlo antes no
compensa: la información de titularidad, lesiones y sanciones sigue cambiando hasta último
momento, y un once "final" puesto con una semana de antelación puede quedar obsoleto sin que
nadie lo corrija. Mientras estemos fuera de esa ventana, el once solo se **muestra** en el
informe diario (para que sepas cómo pinta la cosa), pero no se envía a la API. Dentro de la
ventana, cada `tick` puede refinarlo con la información más fresca hasta que cierre el plazo.

`LINEUP_LOCK_HOURS` (nueva variable, por defecto 24) controla el tamaño de esta ventana —
ver `config.py` y el punto correspondiente en `cli._watch_once()`.

> ⚠️ **Regla crítica, confirmada con la ayuda oficial de LaLiga Fantasy**: si en el momento en
> que se guarda la alineación (justo antes del primer partido de la jornada) **no tienes 11
> jugadores alineados, O tienes saldo negativo, NO PUNTÚAS NADA esa jornada — cero, no "lo que
> puedas alinear"**. Las dos cosas son igual de graves y tienen el mismo nivel de urgencia
> máxima: ni la plantilla incompleta ni la deuda son un "mal menor", son una jornada entera
> perdida. Todo lo de §8 (red de seguridad) y la política de deuda deben tratarse con esta
> urgencia — más agresivos cuanto más cerca esté el cierre, incluso si eso significa relajar
> topes normales de gasto.

## 4. Titularidad, rotación, rival y campo

Fuentes: futbolfantasy.com (seguimiento de titularidad), tuayudantefantasy.com (predictor por
rival/campo), calculadorafantasy.com, lacabrafantasy.com.

Factores a ponderar en la puntuación esperada de cada jugador (`lineup.py`,
`attendance.py`), por orden de peso orientativo:

1. **% de titularidad reciente** (ya implementado vía `weekPoints` de las últimas 5 jornadas
   como proxy — `attendance.estimate_titularidad`). Pondera fuerte: un crack que no juega,
   0 puntos.
2. **Estado real** (`playerStatus` de la propia API: lesión, sanción, duda) — tiene
   prioridad sobre el proxy histórico; si `playerStatus` dice lesionado, ignora el
   histórico y pondera a 0 (ya está así en `analysis.py`, mantenerlo).
3. **Entrenador rotador vs no rotador**: equipos con competición europea entre semana
   (Champions/Europa League) rotan más los fines de semana siguientes — penalizar
   ligeramente la titularidad estimada de esos jugadores en esas jornadas si el histórico
   de rotación del equipo lo confirma. (Fuente externa manual por ahora: no hay endpoint
   fiable; revisar prensa antes de fichajes grandes en semanas de competición europea.)
4. **Dificultad del rival de la próxima jornada**: jugadores de equipos que se enfrentan a
   rivales de la parte baja de la tabla puntúan más de media — usar la clasificación actual
   del rival como proxy de dificultad si no hay una métrica mejor. Ya se muestra el rival con
   🏠/✈️ en `lineup --news`; falta ponderar por posición en tabla del rival.
5. **Campo (local/visitante)**: bonus histórico a favor del local — aplicar un pequeño
   multiplicador (p.ej. ×1.05–1.10) a la puntuación esperada si juega en casa, penalizar
   ligeramente si es fuera contra un rival fuerte.
6. **Racha reciente de puntos** (media de las últimas 3-5 jornadas, no solo la temporada
   completa) — un jugador "en forma" pesa más que su media anual.

## 5. Mercado (fichajes/ventas, fuera de clausulazos)

Ya modelado en el proyecto (`analysis.py`): puntos por millón + tendencia a 3 días +
descuento sobre valor + media de puntos, separando "oportunidad para el once" de
"oportunidad de inversión" (comprar barato en subida para revender, sin mirar si es buen
jugador). Reglas adicionales de esta investigación:

- No pujar por jugadores con duda/lesión salvo que el descuento sea tan grande que compense
  el riesgo y el horizonte de reventa (14 días de blindaje tras comprar) permita esperar a
  que se recupere.
- Evitar pujar por encima de valor salvo en fase competitiva final, donde ya no importa
  revalorizar — ahí sí se puede pagar de más por puntos inmediatos.

## 6. Umbrales a mantener sincronizados con el código

| Regla | Dónde vive en el código |
|---|---|
| Cláusula lógica ≤ 1.2× valor | `analysis.py::clause_alerts`, `max_ratio` |
| Riesgo propio: tu cláusula ≤ 1.25× valor | `analysis.py` |
| Horizonte de reventa: 14 días de blindaje | `analysis.py::project_value` |
| Congelación de cláusulas: 24h antes de la jornada | `service.py::clause_freeze_window` |
| Once no se aplica en automático hasta 24h antes de la jornada | `config.py::LINEUP_LOCK_HOURS` (**pendiente de añadir**) |
| Corte fase económica → competitiva | descartado: el usuario prioriza puntos siempre |
| Bonus local/visitante y dificultad del rival | `autopilot.py::fixture_factor` (en la alineación) |
| Penalización por rotación europea | **pendiente** (dato externo, no hay endpoint fiable) |

## 7. Cartera de presupuesto, no fichajes sueltos

Nunca se propone una lista que en conjunto no quepa en tu saldo real: `analysis.allocate_budget`
coge las oportunidades ordenadas por score y va eligiendo mientras quepan, reservando
`BUDGET_RESERVE_PCT` (20% por defecto) como colchón para cláusulas — ver §1. El score en sí
ya no es solo precio/rendimiento de hoy: suma "forma reciente" (media de las últimas 2-3
jornadas jugadas, más predictiva que la media de toda la temporada — `service.recent_form`) y
un extra si el jugador se acaba de recuperar de lesión/duda/sanción y su precio aún no lo
refleja (`storage.recently_recovered`, histórico que guardamos nosotros porque la API solo da
el estado de hoy).

## 8. Red de seguridad: plantilla incompleta para la jornada

Si no llegas al mínimo de jugadores DISPONIBLES por posición para alinear ningún 11 legal
(1 portero, 3 defensas, 3 centrocampistas, 1 delantero — `analysis.position_shortage`), el
sistema ficha del **mercado libre** (nunca clausulazos: eso le quita algo a un rival y sigue
necesitando tu sí) **sin pedir confirmación**, priorizando por: (1) qué posición está más
corta, (2) rendimiento, (3) coste. Tope de seguridad: `EMERGENCY_BUY_CAP_PCT` (15% del saldo
por operación) y `EMERGENCY_BUYS_PER_WEEK` (3 por semana).

## 9. Cláusulas: no alimentar al líder, no clausular por venganza

`analysis.clause_alerts` despriorriza (no descarta) dos casos, con aviso explícito en el
mensaje: pagar la cláusula del líder actual de la liga (le das el dinero que necesita para
reponerse), y clausular de vuelta al mismo rival que te acaba de clausular a ti (casi siempre
le hace un favor: recupera parte del dinero y consigue el jugador que quería — confirmado por
varias guías externas, no es solo intuición). El líder se calcula de la clasificación real;
quién te clausuló sale de `/activity` (`service.recent_clauser_against_me` — **sin verificar
en vivo todavía**, mismo aviso que otras rutas nuevas: si nunca detecta nada, comprobar con
`fantasy probe` y ajustar las claves).

## 10. Ejecución al segundo exacto (sin servidor 24/7)

El precio de una cláusula es fijo y conocido de antemano — no es una puja a ciegas. Por eso tu
"Confirmar" vale como aprobación del importe exacto, aunque la cláusula aún no se haya
liberado: `confirm.propose(..., execute_at=...)` guarda esa aprobación, y `run_scheduled()`
la ejecuta ella sola, durmiendo dentro del propio job de GitHub Actions hasta el instante
exacto (por eso el `timeout-minutes` del workflow subió a 28). Las pujas de mercado usan el
mismo mecanismo pero al revés: se ejecutan ~60s **antes** de que cierre el anuncio (no antes,
para no revelar la puja y evitar que otro reaccione — mismo principio que el "last-minute
bidding" de otros bots de este juego).

## 11. Mensajes: parte corto y repartido, no todo de golpe

`digest.py` manda como mucho un parte de situación (`service.situational_briefing`, 4-6
líneas: saldo, huecos, próxima cláusula, posición en la liga) cada `BRIEFING_INTERVAL_MIN`
(90 min por defecto), nunca en horas de silencio (23h-7h, `digest.in_quiet_hours`) — pero las
propuestas de decisión (cláusulas, fichajes) se mandan siempre, sin esperar turno ni respetar
las horas de silencio, para no perder una ventana real. Los botones de Telegram (Confirmar/
Cancelar) van en cada propuesta (`confirm.propose(..., label=...)`), con una etiqueta de
urgencia (`analysis.clause_urgency_label`, 4 niveles) o calidad (`analysis.player_quality_label`).
En cuanto se ejecuta algo (confirmación o fichaje de emergencia), se manda un aviso corto
inmediato con el resultado — no espera al siguiente parte de situación.

## Próximos pasos de implementación

1. Añadir a `lineup.py` el multiplicador local/visitante y el ajuste por dificultad del
   rival (posición en tabla).
2. Añadir `SEASON_PHASE_CUTOFF` (jornada o fecha) en `.env`/`config.py` y una segunda función
   de puntuación en `analysis.py` para la fase competitiva.
3. Estimar saldo de rivales a partir de `/activity` (ya apuntado en el README original) para
   priorizar clausulazos donde el rival no pueda responder — mismo endpoint que §9, aprovechar
   la misma llamada.
4. Verificar en vivo `service.recent_clauser_against_me` (forma del JSON de `/activity`) y el
   payload real de `update_lineup` (bloqueado desde antes, ver README).
5. Probar el primer fichaje de emergencia y la primera cláusula programada contra la cuenta
   real — todo esto está solo probado con datos de mentira (tests), no en vivo todavía.
