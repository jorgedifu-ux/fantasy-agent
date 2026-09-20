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

## 3. Titularidad, rotación, rival y campo

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

## 4. Mercado (fichajes/ventas, fuera de clausulazos)

Ya modelado en el proyecto (`analysis.py`): puntos por millón + tendencia a 3 días +
descuento sobre valor + media de puntos, separando "oportunidad para el once" de
"oportunidad de inversión" (comprar barato en subida para revender, sin mirar si es buen
jugador). Reglas adicionales de esta investigación:

- No pujar por jugadores con duda/lesión salvo que el descuento sea tan grande que compense
  el riesgo y el horizonte de reventa (14 días de blindaje tras comprar) permita esperar a
  que se recupere.
- Evitar pujar por encima de valor salvo en fase competitiva final, donde ya no importa
  revalorizar — ahí sí se puede pagar de más por puntos inmediatos.

## 5. Umbrales a mantener sincronizados con el código

| Regla | Dónde vive en el código |
|---|---|
| Cláusula lógica ≤ 1.2× valor | `analysis.py::clause_alerts`, `max_ratio` |
| Riesgo propio: tu cláusula ≤ 1.25× valor | `analysis.py` |
| Horizonte de reventa: 14 días de blindaje | `analysis.py::project_value` |
| Congelación de cláusulas: 24h antes de la jornada | `service.py::clause_freeze_window` |
| Corte fase económica → competitiva | **pendiente de añadir** (`SEASON_PHASE_CUTOFF`) |
| Bonus local/visitante | **pendiente de añadir** en `lineup.py` |
| Penalización por rotación europea | **pendiente** (dato externo, no hay endpoint fiable) |

## Próximos pasos de implementación

1. Añadir a `lineup.py` el multiplicador local/visitante y el ajuste por dificultad del
   rival (posición en tabla).
2. Añadir `SEASON_PHASE_CUTOFF` (jornada o fecha) en `.env`/`config.py` y una segunda función
   de puntuación en `analysis.py` para la fase competitiva.
3. Estimar saldo de rivales a partir de `/activity` (ya apuntado en el README original) para
   priorizar clausulazos donde el rival no pueda responder.
