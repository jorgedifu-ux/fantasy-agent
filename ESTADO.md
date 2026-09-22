# Estado del proyecto — fantasy-agent

Documento de contexto para retomar esto en cualquier momento, aunque se pierda la
conversación con Claude. Última actualización: **22/09/2026**.

## Qué es esto

Un agente que gestiona tu equipo de LaLiga Fantasy (liga "Liga Fantasía", id `018221573`,
equipo "The Iberian One", id `39057665`) de forma semi-automática: corre solo en GitHub
Actions cada ~30 min, sin coste (repo público, sin tokens de Claude de por medio — es Python
puro), y te avisa por Telegram. Repo: `github.com/jorgedifu-ux/fantasy-agent`.

**Regla de oro del proyecto**: no tener 11 alineados o tener saldo negativo en el momento en
que arranca la jornada son **jornada entera a cero puntos** — no un mal menor. Toda la lógica
de emergencia gira en torno a evitar esos dos escenarios.

## Cómo hablar con él

- **Telegram**: bot "Mi Fantasy Bot" (`@Vk_fantasia_bot`). Los avisos llegan ahí, con botones
  reales "✅ Confirmar" / "❌ Cancelar" en las propuestas.
- **Terminal** (en esta carpeta): `python3 -m fantasy_agent <comando>` — `pending` (propuestas
  vivas), `plan --refresh --telegram` (regenerar y fijar el plan), `tick` (una pasada manual,
  útil para probar), `leagues`/`standing` (estado crudo).
- **El Plan de equipo**: un mensaje FIJADO en el chat de Telegram (no busques uno nuevo cada
  vez, se edita en el sitio) con fichajes objetivo, prioridad de venta, y vigilancia de
  rivales. Se regenera solo 1 vez por semana.

## Qué hace solo, SIN pedirte confirmación

| Acción | Tope | Motivo |
|---|---|---|
| Fijar alineación | — | **Bloqueado, ver "Pendiente" abajo** |
| Fichaje de emergencia (plantilla incompleta) | Hasta 3/semana, se amplía (x1.5–x3) cerca de la jornada | Evitar el cero por plantilla incompleta |
| Fichaje a crédito (deuda) | Solo si no hay otra forma, tope 20% del valor de plantilla | Último recurso, emparejado con una venta del plan — no es garantía |
| Compra autónoma (oportunidad muy buena, score≥18) | 2/día | Pediste no depender de que confirmes todo |
| Venta autónoma (según el Plan: cortar pérdidas / aprovechar máximo) | 2/día | Igual que arriba |
| Aceptar ofertas del SISTEMA sobre tus ventas | **De momento NO** — solo avisa con el umbral, ver abajo | La API no deja leer el importe exacto, decides tú viendo la app |
| Rechazar ofertas de RIVALES de tu liga | Casi siempre | Rara vez convienen |
| Blindaje (proteger tu jugador más vulnerable) | 1 intento / 4 días, gratis | Nueva funcionalidad, sin coste |
| Subir tu propia cláusula (pago) | Solo si blindaje no disponible, pieza valiosa | Alternativa de pago al blindaje |

## Qué SIEMPRE pide tu confirmación (botones en Telegram)

- **Clausulazos** (pagar la cláusula de un rival) — máx. 3 propuestas a la vez.
- Cualquier operación "fuera de plan" que no encaje en las autónomas de arriba.

## Umbral de aceptar ofertas de venta (tu pregunta del %)

| Motivo de la venta | Acepta desde |
|---|---|
| 🩸 Cortar pérdidas | 90% del precio puesto |
| 💰 Aprovechar máximo (ganancia) | 100% |
| Cualquier otro caso | 110% |

**Por qué de momento lo aceptas tú a mano**: la API expone `numberOfOffers` (cuántas ofertas
hay) pero no el importe exacto de una oferta sobre un anuncio "marketPlayerTeam" — se
comprobó en vivo (Musso/Tárrega, 22/09) que el JSON del mercado nunca trae el array `offers`
con detalle, y el único endpoint candidato para leer/aceptar
(`POST /market/{id}/offer`) devuelve **403 Forbidden** (probado en vivo con Musso, importe
2,024,749 — no es un bloqueo temporal, es que ese no es el endpoint correcto, probablemente
es el lado "comprador" de una oferta, no el "vendedor"). Mientras no aparezca la ruta
correcta: en cuanto llega una oferta nueva (el contador sube), Telegram te avisa con el
umbral que deberías exigir para que decidas tú mirando la cifra real en la app.

## Decisiones y políticas acordadas contigo (con el motivo)

- **Colchón de saldo**: 20% siempre sin tocar (`BUDGET_RESERVE_PCT`).
- **Sobrepuja según calidad de la oportunidad**: 0% si es "a valorar", +8% "buena opción",
  +17% "chollo", +5% extra si ya hay competencia — nunca por encima del saldo.
- **No alimentar al líder de la liga** ni **clausular por venganza** al que te acaba de
  clausular a ti — se despriorizan, no se descartan del todo.
- **Deuda**: nunca automática salvo el último recurso ya descrito; siempre emparejada con una
  venta inmediata para intentar saldarla antes de la jornada — no es garantía (una venta no
  es instantánea).
- **Horas de silencio**: 23h-7h sin el parte de situación rutinario, pero las decisiones
  urgentes (clausulazos, etc.) se mandan siempre, sin esperar.
- **Coste en tokens de Claude**: cero en el día a día — todo lo de la tabla de arriba es
  Python puro en GitHub Actions. Hablar del Plan conmigo es aparte, al ritmo que tú quieras
  (dijiste semanal).

## ⚠️ Sin verificar en vivo todavía (funciona en teoría, no probado con un caso real)

- **Alineación automática**: bloqueada a propósito. El primer intento de guardar el once dio
  error 500 — necesita comparar el JSON real de `probe /v1/competition/1/teams/<id>/lineup`
  antes de activarse. Mientras tanto, la fijas tú a mano en la app.
- **Ofertas de rival vs. del sistema** (`Offer.is_system`): heurística sin confirmar — y en la
  práctica nunca se ejecuta, porque el mercado nunca trae el array `offers` con detalle (ver
  más abajo), así que este código está listo pero inactivo hasta que aparezca esa ruta.
- **Aceptar/rechazar una oferta por API**: **confirmado que NO funciona todavía** —
  `POST /league/{id}/market/{marketId}/offer` da 403 Forbidden (probado en vivo, ver arriba).
  Sigue siendo el mayor hueco funcional: de momento, siempre lo aceptas tú a mano en la app.
- **Blindaje / subir cláusula**: nunca se han disparado contra una situación real.
- Si algo de esto falla o no hace lo que debería, el error de la API suele venir en el propio
  mensaje de Telegram — pégamelo y lo ajustamos con el JSON real.

## ✅ Confirmado en vivo con datos reales (22/09/2026)

- **`/activity`** (para saber quién te clausuló y evitar venganza): es una **lista plana** de
  `{activityTypeId, user1Id, user2Id, playerMasterId, amount, createdAt}` — nada de campos
  anidados. `activityTypeId == 1` es un pago de cláusula (`user1Id` paga, `user2Id` es la
  víctima), `activityTypeId == 33` una venta de mercado resuelta. `user1Id`/`user2Id` son
  **manager_id, no team_id** — `service.recent_clauser_manager_id` ya usa las claves reales, y
  `build_world` convierte el resultado a team_id con el `standing` antes de guardarlo en
  `World.revenge_against_team_id`.
- **Bug de IDs (ya corregido)**: `sell_player`/`pay_buyout_clause` necesitan `playerTeamId`
  (id del hueco en tu plantilla), no el id del jugador — con el id equivocado daba HTTP 400.

## Incidente de hoy (22/09) — ya resuelto

Se acumularon **9 commits sin subir a GitHub** durante toda una sesión de trabajo intensivo —
la automatización en la nube corría con código de ayer, por eso parecía que "había vuelto
atrás" y no salían botones (esa versión no los tenía todavía). Ya subido y sincronizado.
También se limpiaron 5 propuestas duplicadas/obsoletas que se habían acumulado en Telegram, y
se arregló la causa (`confirm.propose()` ahora retira automáticamente cualquier propuesta
anterior del mismo jugador antes de crear una nueva).

**Lección para el futuro**: como agente, recuerda hacer `git push` después de cada tanda de
commits, no solo `git commit` — si no, la nube se queda desactualizada en silencio.

## Próximos pasos (pendientes, sin empezar)

1. **Encontrar la ruta real de aceptar/rechazar una oferta** (la única candidata da 403) — sin
   esto, la venta con oferta nunca puede ser 100% autónoma, solo avisar con el umbral como
   ahora. Si algún día se localiza (p.ej. viendo las peticiones de la app con un proxy), es el
   cambio de mayor impacto pendiente.
2. Verificar en vivo la alineación automática (necesita tu sesión logueada + un `probe`).
3. Bonus local/visitante y corte de fase económica→competitiva en `STRATEGY.md` (documentado,
   no implementado).
4. Estimar el saldo de los rivales a partir de `/activity` para priorizar clausulazos donde no
   puedan reponerse.
5. La primera vez que se dispare blindaje/subir cláusula/una oferta de rival de verdad,
   revisar que el resultado sea el esperado.

## Dónde está todo

- `fantasy_agent/` — el código. `analysis.py` (puntuación, puro/testeable), `plan.py` (el
  Plan), `confirm.py` (cola de confirmación), `cli.py` (orquesta todo, `_watch_once` es el
  corazón), `service.py`/`models.py`/`api.py` (datos y escritura).
- `STRATEGY.md` — el razonamiento estratégico detallado, sección por sección.
- `CLAUDE.md` — normas de desarrollo del proyecto (para cuando se edite el código).
- `tests/` — 73 tests, todos sin red (`python3 -m unittest discover -s tests -v`).
- `.env` — tus credenciales (Telegram, nunca se sube a git).
