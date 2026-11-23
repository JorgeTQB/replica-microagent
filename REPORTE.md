# Réplica de MicroAgent con Claude Code: reporte de resultados

**Artículo replicado:** Su, Z., Huang, J., Shan, S., Chen, X., Zeng, H., Su, Y., Wang, Y. y Lyu, M. R. (2026).
*MicroAgent: Context-Augmented Multi-agent Framework for Automatic Microservice Decomposition*. ASE '26.
doi:10.1145/3832783.3834441. Artefacto: doi:10.5281/zenodo.19250602.

**Fecha de las corridas:** 2026-11-20 a 2026-11-22. **Autor de la réplica:** Jorge Quispe (Universidad de Lima).

- Cómo ejecutar cada fase: `README.md`.
- Registro de decisiones: `DECISIONES.md` (D1 a D60).
- Datos: `evaluation/results.csv` y `evaluation/error_analysis.md`.

---

## 1. Resumen

- **PartsUnlimitedMRP reproduce el paper.** MicroAgent obtiene un WS de 99,56 ± 0,76 % (paper ≈ 100 %) y supera a
  la línea base zero-shot por 33,0 puntos (paper: unos 20,5).
- **JPetStore no reproduce la ventaja de MicroAgent.** En 10 corridas, MicroAgent obtiene 85,55 ± 7,96 % (mediana
  86,26 %), frente a 84,20 % de la línea base. El paper reporta ≈ 93 % frente a ≈ 81,5 %. 4 de las 10 corridas llegan
  al 92,66 %, que coincide con el paper, pero en promedio las dos configuraciones no se distinguen.
- **La variabilidad de JPetStore se concentra en la Etapa 4 (Common Class Agent).** Repetida 5 veces con una
  entrada idéntica byte a byte, da tres resultados distintos. La explicación más simple es que Claude Code envía
  `temperature: 1` y no permite cambiarla, mientras que el original usa 0.
- Todas las corridas de la tabla principal usan la misma versión de Claude Code (2.1.330).
- La réplica mantiene literales los prompts, la lógica de las herramientas, el orden de las etapas y los scripts
  de métricas del artefacto. `MicroAgent/` no se modificó.

---

## 2. Configuración de la réplica y diferencias con el original

| Aspecto | Original (artefacto) | Réplica | Tipo |
|---|---|---|---|
| Orquestación | CrewAI 1.8.1, `main.py` secuencial | `run_pipeline.py` reproduce la lógica de `main.py`; cada agente es una llamada `claude -p` independiente | **Cambio aprobado** |
| LLM | DeepSeek-V3.2 (principal), GPT-5.2, Claude Sonnet 4.5; temperatura 0 | `claude-sonnet-4-6` en todas las llamadas, esfuerzo `high`, sin razonamiento extendido (`MAX_THINKING_TOKENS=0`). Claude Code envía `temperature: 1` y no permite cambiarla (D3, D4, D35) | **Cambio aprobado** |
| Aplicaciones | 10 | JPetStore (24 clases, 1 409 LOC, 3 servicios) y PartsUnlimitedMRP (53 clases, 4 407 LOC, 5 servicios) | **Cambio aprobado** |
| Repeticiones | 1 corrida (implícita) | Tabla principal: MicroAgent 10 corridas en JPetStore (D58) y 3 en PartsUnlimitedMRP; línea base 3 por app. Aparte: 5 repeticiones aisladas de la Etapa 4 (D41) y 6 corridas anteriores con otra versión de Claude Code (D60) | Consecuencia del cambio |
| Llamada a herramientas | Plantilla ReAct de CrewAI | Llamada nativa por MCP; el bloque ReAct se excluye del system prompt (D28) | Consecuencia del cambio |
| Prompts de agentes | `agents.yaml` + `tasks.yaml` + texto de `main.py` | Mensaje de usuario idéntico carácter por carácter al que enviaba CrewAI 1.8.1, comprobado contra capturas del original (D24–D30) | Igual |
| Herramientas | `custom_tools.py` | Copia con 2 líneas de importación cambiadas, sin tocar ningún `_run`, expuesta por un servidor MCP (D18–D21) | Igual |
| Herramientas por agente y límite de iteraciones | `crew.py` | Las mismas listas por agente; `max_iter` → `--max-turns`, con respuesta final forzada como en CrewAI (D39) | Igual |
| Contexto de JPetStore | Publicado por los autores | Reutilizado byte a byte; JPetStore fijado en el commit `a37c02f` (D6) | Igual |
| Contexto de PartsUnlimitedMRP | No publicado | Generado con el mismo analizador y los mismos prompts; los resúmenes los escribe Claude (D7–D11) | Parcial |
| Línea base | Prompt no publicado | Prompt reconstruido a partir de la descripción del paper (D45) | Parcial |
| Métricas | `json_similarity.py`, `common_metrics.py` | Los mismos scripts, importados sin modificar (D51) | Igual |
| `common_dict` | Publicado solo para JPetStore | PartsUnlimitedMRP: reconstruido con una regla que reproduce el de JPetStore (D50) | Parcial |
| CMod, CiD, BCP | Repositorio de Wang et al. | Fuera de alcance | Recorte |

### Corridas incluidas y versión de Claude Code

| Grupo | Corridas | Claude Code | Uso |
|---|---|---|---|
| MicroAgent, JPetStore | `claude-run4` a `run13` | 2.1.330 | Tabla principal |
| MicroAgent, PartsUnlimitedMRP | `claude-run4` a `run6` | 2.1.330 | Tabla principal |
| Línea base, las dos apps | `baseline-run1` a `run3` | 2.1.330 | Tabla principal |
| MicroAgent, las dos apps | `claude-run1` a `run3` | 2.1.327 | Aparte (§7) |
| Etapa 4 aislada, JPetStore | `claude-run1-e4-r01` a `r05` | 2.1.327 | Aparte (§7) |

Las primeras corridas de MicroAgent se hicieron con Claude Code 2.1.327. Entre sesiones, la instalación se
actualizó a 2.1.330, que ya usaban la línea base y JPetStore `claude-run4` a `run10`. Para que la tabla principal
tuviera una sola versión, se repitieron con 2.1.330 las corridas hechas con 2.1.327, con `run_id` nuevos:
JPetStore `claude-run11` a `run13` y PartsUnlimitedMRP `claude-run4` a `run6` (D60). Las corridas con 2.1.327 no se
borraron: quedan en `output/` y en `results.csv` como la configuración `microagent_cc2.1.327`.

Ninguna corrida falló. Todas terminaron con estado `completa`. Hay una observación que se repite en cada
configuración, y ninguna de las dos es un fallo:

- **MicroAgent:** los agentes no escriben la etiqueta `Final Answer:`. En ese caso se toma el texto completo, como
  hace CrewAI (D31).
- **Línea base:** el modelo entrega el JSON entre cercas de código, y `clean_json_output` las recorta (D48).

---

## 3. Métricas

- **WS (Weighted Similarity):** cada servicio producido se compara con la partición de referencia más parecida
  (similitud = |intersección| / máx. de los tamaños), ponderando por tamaño. Se calcula en las dos direcciones y se
  combina con media armónica. Excluye las clases `uncounted`. Corresponde a `metrics_m2.weighted_average`.
- **c2c@50/75/90:** porcentaje de servicios cuya mejor coincidencia supera el 50, 75 o 90 %. El script usa `>` y el
  paper dice `≥`; se reporta como el script (D52). Con `≥` solo cambian dos valores de la tabla de §4:
  - el c2c@90 de JPetStore / MicroAgent pasaría de 26,7 a 60,0 %, porque la similitud Catalog ↔ catalog es
    exactamente 0,900 en las 10 corridas;
  - el c2c@50 de PartsUnlimitedMRP / línea base pasaría de 86,7 a 93,3 %, porque uno de sus servicios tiene
    similitud 0,500.

  Esos valores se recalcularon con las similitudes guardadas en `evaluation/raw/`, en las dos direcciones y
  combinadas como hace el script.
- **F1 de clases comunes:** compara en qué servicios quedó cada clase común con los servicios en que "debería"
  estar según el `common_dict`. Se reportan micro y macro porque el paper no dice cuál usó (D53). En las tablas se
  muestra el micro. En las medias, el macro difiere en menos de 0,2 puntos.
- **Control de cordura:** cada referencia evaluada contra sí misma da 1,0 en todas las métricas
  (`evaluation/sanity_check.json`).

---

## 4. Resultados por aplicación

Media ± desviación estándar muestral, en %. n = número de corridas. Todas las corridas usan Claude Code 2.1.330.

| App | Configuración | n | WS | Mediana WS | Mín.–máx. WS | c2c@50 | c2c@75 | c2c@90 | F1 comunes |
|---|---|---|---|---|---|---|---|---|---|
| JPetStore | MicroAgent | 10 | 85,55 ± 7,96 | 86,26 | 70,71–92,66 | 100 ± 0 | 83,3 ± 28,3 | 26,7 ± 34,4 | 100 ± 0 |
| JPetStore | Línea base | 3 | 84,20 ± 0,00 | 84,20 | 84,20 | 100 ± 0 | 100 ± 0 | 33,3 ± 0 | 100 ± 0 |
| PartsUnlimitedMRP | MicroAgent | 3 | 99,56 ± 0,76 | 100,00 | 98,68–100,00 | 100 ± 0 | 100 ± 0 | 100 ± 0 | 100 ± 0 |
| PartsUnlimitedMRP | Línea base | 3 | 66,58 ± 0,52 | 66,44 | 66,13–67,15 | 86,7 ± 11,5 | 40,0 ± 0 | 0 ± 0 | 95,52 ± 0 |

WS de cada corrida:

| App | Configuración | WS por corrida |
|---|---|---|
| JPetStore | MicroAgent (run4 a run13) | 86,26 · 92,66 · 92,66 · 70,71 · 74,35 · 92,66 · 86,26 · 86,26 · 92,66 · 80,99 |
| JPetStore | Línea base | 84,20 · 84,20 · 84,20 |
| PartsUnlimitedMRP | MicroAgent (run4 a run6) | 100,00 · 98,68 · 100,00 |
| PartsUnlimitedMRP | Línea base | 67,15 · 66,44 · 66,13 |

En todas las corridas se cumplió lo siguiente:
- se asignaron todas las clases del universo (24 y 53);
- no quedaron clases sin asignar ni aparecieron clases inventadas;
- se generó el número de servicios pedido.

### Costo y esfuerzo por corrida (media)

| App | Configuración | Llamadas a `claude` | Turnos | Peticiones a la API | Duración (reloj) | Tokens | Costo nominal |
|---|---|---|---|---|---|---|---|
| JPetStore | MicroAgent | 8 | 99 | 54 | 6,5 min | 654 mil | USD 1,09 |
| JPetStore | Línea base | 1 | 1 | 1 | 7 s | 23 mil | USD 0,06 |
| PartsUnlimitedMRP | MicroAgent | 8 | 138 | 64 | 7,8 min | 954 mil | USD 1,42 |
| PartsUnlimitedMRP | Línea base | 1 | 1 | 1 | 19 s | 49 mil | USD 0,14 |

- **Turnos:** suma del campo `num_turns` que devuelve Claude Code. En cada llamada equivale a las llamadas a
  herramientas + 1 (D54). No es lo que limita `--max-turns`; por eso se agregan las peticiones a la API.
- **Costo:** es el que informa Claude Code (`total_cost_usd`); el plan Pro no cobra por llamada. En la línea base
  depende de la caché de prompts: la primera corrida de cada app cuesta mucho más que las dos siguientes. En
  JPetStore, USD 0,14 frente a 0,02; en PartsUnlimitedMRP, 0,32 frente a 0,05 (D48). De ahí salen las medias de la
  tabla.
- **Tokens:** MicroAgent consume unas 19 a 28 veces más que la línea base (28 en JPetStore, 19 en PartsUnlimitedMRP).
- **Costo total de la réplica:** unos USD 25,7. Contexto de PartsUnlimitedMRP, 0,82; pruebas del orquestador, 0,48;
  las 19 corridas de MicroAgent, 23,15; repeticiones de la Etapa 4, 0,63; línea base, 0,59. No incluye una primera
  generación de contexto con Sonnet 4.5 y razonamiento extendido, que se descartó y costó USD 1,13 (D12).

---

## 5. Comparación con el paper

Los valores por aplicación del paper solo aparecen en su Figura 3 (WS con DeepSeek-V3.2). Se leyeron del gráfico,
con un error aproximado de ±1 punto.

| App | MicroAgent: paper | MicroAgent: réplica | Línea base: paper | Línea base: réplica | Ventaja: paper | Ventaja: réplica |
|---|---|---|---|---|---|---|
| JPetStore | ≈ 93 | 85,55 (mediana 86,26; máx. 92,66) | ≈ 81,5 | 84,20 | ≈ +11,5 | +1,4 (mediana +2,1; máx. +8,5) |
| PartsUnlimitedMRP | ≈ 100 | 99,56 | ≈ 79,5 | 66,58 | ≈ +20,5 | +33,0 |

**¿Se mantiene la mejora de MicroAgent sobre la línea base?**

- **PartsUnlimitedMRP: sí.** MicroAgent queda en el mismo nivel que el paper. La ventaja es incluso mayor, porque
  la línea base de la réplica rinde 13 puntos menos que la del paper. Esa diferencia de unos 33 puntos es mucho
  mayor que la dispersión de cualquiera de las dos configuraciones (≤ 0,8 puntos).
- **JPetStore: no.** La media de MicroAgent queda solo 1,4 puntos por encima de la línea base, y su desviación es de
  8,0 puntos, así que las dos configuraciones no se distinguen. El paper reporta una ventaja de unos 11,5 puntos. El
  mejor resultado de la réplica (92,66 %) sí coincide con el ≈ 93 % del paper, y se repitió en 4 de las 10 corridas.
- **Línea base:** la de JPetStore (84,20 %) es algo mejor que la del paper (≈ 81,5 %), y la de PartsUnlimitedMRP
  (66,58 %) bastante peor (≈ 79,5 %). Como el prompt de la línea base es una reconstrucción y el modelo es otro, esas
  diferencias no se pueden atribuir a una sola causa.

Promedios del paper sobre sus 10 aplicaciones, solo como referencia, porque no son comparables con 2 aplicaciones:
WS 89,2 %; c2c@50/75/90 = 94,5 / 75,7 / 53,0 %; F1 de clases comunes 93,4 %. El paper no publica c2c ni F1 por
aplicación, así que para esas métricas de la réplica no hay un valor del paper con el que compararlas.

---

## 6. Análisis de errores

Cada servicio producido se asocia a la partición de referencia más parecida. Una clase está "de más" si aparece en
un servicio cuya partición de referencia no la contiene. Una clase "falta" si ningún servicio asociado a su
partición la contiene. Detalle por corrida en `evaluation/error_analysis.md`.

### 6.1 JPetStore, MicroAgent (run4 a run13)

En la referencia hay tres particiones: `account`, `catalog` y `order`. La única clase común es `AbstractActionBean`,
que está en las tres.

| Error | Corridas | Servicio afectado | Origen |
|---|---|---|---|
| `CartActionBean` está en Order y falta en Catalog | 10 de 10 | Catalog → Order | Etapa 1: el Domain Agent crea un dominio "Shopping Cart" propio, que después se fusiona con Order (D43) |
| `CatalogService` también en Account y Order | 6 de 10 (run4, 7, 8, 10, 11, 13) | Account, Order | Etapa 4: se declara común |
| `Item` e `ItemMapper` de más | 3 de 10: run7 y run8 (en Account y Order), run13 (solo en Order) | Account, Order | Etapa 4 + propagación |
| `Account` también en Order | 2 de 10 (run7, 8) | Order | Etapa 4 |
| `Product` también en Account y Order | 1 de 10 (run7) | Account, Order | Etapa 4 + propagación |

Las corridas se agrupan en cuatro niveles según las clases que la Etapa 4 declara comunes:

| Clases comunes en `result.json` | Corridas | WS |
|---|---|---|
| Solo `AbstractActionBean`, como en la referencia | run5, 6, 9, 12 | 92,66 |
| `AbstractActionBean` + `CatalogService` | run4, 10, 11 | 86,26 |
| Además `Item` e `ItemMapper` | run13 | 80,99 |
| Además `Account` (y `Product` en run7) | run7, 8 | 70,71 / 74,35 |

El criterio de la tabla son las clases que quedan en varios servicios en `result.json`, no las que el agente pasa a
`assign_common_class_list`. Las dos cosas coinciden en todas las corridas salvo run12. En run12, el agente llamó a
`assign_common_class_list` con `CatalogService`, `Item` e `ItemMapper` además de `AbstractActionBean`, pero después
cambió de idea y solo escribió `AbstractActionBean` en el resultado. Lo explica en su respuesta final.

Salvo `CartActionBean`, todos los errores son clases **duplicadas de más**; ninguna falta. La Etapa 5 (Review) no
cambió nada en ninguna corrida de JPetStore.

El F1 de clases comunes da 100 % en todas las corridas. El `common_dict` publicado de JPetStore solo evalúa
`AbstractActionBean`, y todas las corridas la reparten bien, así que esta métrica no detecta los duplicados que
introduce la Etapa 4.

### 6.2 JPetStore, línea base (3 corridas idénticas)

| Clase | En la referencia | De más en |
|---|---|---|
| `Account` | account | Order |
| `Item`, `ItemMapper` | catalog | Order |
| `Cart`, `CartItem` | order | Catalog |

No falta ninguna clase. Las 3 corridas dan exactamente la misma partición, aunque usan `temperature: 1`.

### 6.3 PartsUnlimitedMRP, MicroAgent (run4 a run6)

- run4 y run6: **ningún error**. Los 5 servicios coinciden al 100 % con la referencia.
- run5: `OrderStatus` está de más en Shipment; en la referencia solo está en order. Las Etapas 1 a 3 la dejan solo
  en Order, así que el error nace en la Etapa 4. No viene de la propagación: el agente la agregó a Shipment
  directamente con `write_result_to_json`.
- Las Etapas 1 a 3 dieron el mismo contenido en las 3 corridas, y también en las 3 anteriores con 2.1.327: 5
  dominios, sin fusión.
- A diferencia de JPetStore, aquí la Etapa 5 (Review) sí corrigió algo. En run4 y run6, la Etapa 4 dejó
  `PostgresqlProperties` sin asignar, y la Etapa 5 la agregó a los 5 servicios. Lo mismo había pasado en `claude-run2`
  con 2.1.327 (D44).
- Las 7 clases `uncounted` (configuración e infraestructura) quedan en los 5 servicios. El WS no las cuenta.

### 6.4 PartsUnlimitedMRP, línea base (3 corridas)

Entre 21 y 24 clases de más por corrida, sin clases que falten. El patrón general se repite en las tres:

| Grupo de clases | Partición de referencia | De más en |
|---|---|---|
| Modelos y repositorios de Dealer (`Dealer`, `DealerInfo`, `DealersRepository`, `MockDealersRepository`, `MongoDealersRepository`) | dealer | Order, Quote y Shipment. Excepciones: `DealerInfo` en run1 y run2, y `DealersRepository` en run2, que solo están de más en Quote |
| Modelos y repositorios de Quote (`Quote`, `QuoteDetails`, `QuoteItemInfo`, `QuoteRepository`, `MockQuoteRepository`, `MongoQuoteRepository`) | quote | Order, Shipment |
| Modelos y repositorios de Order (`Order`, `OrderDetails`, `OrderStatus`, `OrderEventInfo`, `OrderUpdateInfo`, `OrderRepository`, `MockOrderRepository`, `MongoOrderRepository`) | order | Shipment |
| Excepciones (`BadRequestException`, `ConflictingRequestException`) | order, quote, shipment | Catalog, Dealer (y Quote) |
| Solo en run2: clases de catálogo (`CatalogItem`, `CatalogItemsRepository`, `MockCatalogItemsRepository`) | catalog | Quote |

La línea base copia en cada servicio las clases de dominio que ese servicio usa, en lugar de asignarlas a uno solo.
Por eso el c2c@75 baja al 40 % y el c2c@90 al 0 %. El servicio de envíos (Shipment) es el más afectado, con una
similitud de 0,49 a 0,51.

---

## 7. Variabilidad entre corridas

### Dónde está

En las dos aplicaciones, las corridas de MicroAgent divergen sobre todo en la Etapa 4.

- **PartsUnlimitedMRP:** las Etapas 1 a 3 dieron el mismo contenido en las 6 corridas (las 3 de la tabla y las 3 con
  2.1.327).
- **JPetStore:** las 10 corridas de la tabla tuvieron 4 dominios en la Etapa 1, ejecutaron la fusión y llegaron a 3
  dominios. En 8 de ellas los dominios fusionados tienen el mismo contenido. En run7 y run8, en cambio, la Etapa 2
  puso también `AbstractActionBean` en Account (D59). Por eso la Etapa 4 de esas dos corridas recibe otra entrada, y
  la herramienta `rank_dependency_entropy` devuelve otros valores: por ejemplo, la entropía saliente de
  `CartActionBean` pasa de 0,97 a 1,38. Las dos están en el nivel más bajo (70,71 y 74,35 %). Con solo dos casos, es
  un posible factor, no una causa demostrada.

### Repetición aislada de la Etapa 4

Se repitió solo esa etapa 5 veces con la entrada de `claude-run1`, idéntica byte a byte (D41, D43; Claude Code
2.1.327). Los WS fueron 92,66 · 76,36 · 86,26 · 86,26 · 92,66 % (media 86,84 %): tres resultados distintos con la
misma entrada.

### Causas probables (D57, D58)

1. **Muestreo** (`temperature: 1`): es la explicación más simple, aunque las demás no están descartadas del todo.
   - En las 8 ejecuciones de la Etapa 4 que se compararon en detalle (D57), las salidas de las tres primeras
     herramientas son idénticas byte a byte.
   - La divergencia empieza en la primera decisión libre del agente: qué candidatas evaluar y cuáles declarar
     comunes.
   - Quedan abiertas dos influencias posibles en pasos posteriores: el orden de los `set` de Python
     (`PYTHONHASHSEED`, D41, D57) y el texto libre de la fusión que recibe la Etapa 4 como contexto (D27, D58).
   - A eso se suma la entrada distinta de run7 y run8.
2. **La propagación de `assign_common_class_list` agranda el error.** Cuando se declara común `CatalogService`, las
   clases de las que depende y que también se declaran comunes heredan sus tres dominios. En `claude-run2`, por
   ejemplo, el WS baja de 76,4 a 72,6 % por la propagación (D57).
3. **La métrica castiga mucho los duplicados.** Sin ninguna clase común, el WS sería 84,9 %; con solo
   `AbstractActionBean`, 92,7 % (D57).

**Hipótesis descartadas** (D58): que pasar 6 candidatas a `get_more_potential_common_classes` lleve al mal
resultado, y que el texto de la fusión que menciona `ItemMapper` lo decida. Tampoco se encontraron diferencias de
herramientas, de modelo ni errores de evaluación.

### Versión de Claude Code

Las corridas con 2.1.327, que quedaron fuera de la tabla principal, dan:
- JPetStore (n = 3): WS 79,87 ± 11,11 %, con 92,66 · 72,59 · 74,35;
- PartsUnlimitedMRP (n = 3): WS 99,13 ± 1,50 %.

En JPetStore están dentro del rango de las corridas con 2.1.330. En PartsUnlimitedMRP, una de ellas (97,40 %) queda
1,3 puntos por debajo del mínimo con 2.1.330 (98,68 %). Con 3 corridas no hay evidencia de que la versión cambie el
resultado: en las dos versiones aparecen los mismos niveles de la Etapa 4 y el mismo error de `CartActionBean`.

### Línea base

La línea base es casi determinista, aunque también usa `temperature: 1`. En JPetStore las 3 corridas son idénticas.
En PartsUnlimitedMRP las particiones cambian algo entre corridas (D48), pero el WS tiene una desviación de 0,52
puntos y un rango de 1,0 (66,13–67,15). Una sola respuesta es mucho más estable que una cadena de 8 llamadas con
decenas de llamadas a herramientas cada una.

### El paper

El paper no publica repeticiones ni dispersión. Solo dice que fijó la temperatura en 0 para que los resultados
fueran lo más deterministas posible. Por eso no se puede saber si su ≈ 93 % en JPetStore es un resultado típico o
uno bueno de una distribución parecida a la de la réplica.

---

## 8. Amenazas a la validez

1. **Otro modelo.** Claude Sonnet 4.6 no es ninguno de los tres modelos del paper. La comparación directa es con
   su Figura 3, hecha con DeepSeek-V3.2.
2. **Sin temperatura 0.** Claude Code envía `temperature: 1` y no permite cambiarla. Es la causa principal de la
   variabilidad de JPetStore. Para corregirla habría que llamar a la API directamente, fuera de `claude -p` y del
   plan Pro (D57).
3. **Solo 2 de 10 aplicaciones.** Los promedios del paper no son comparables, y el resultado mixto (una app
   reproduce y la otra no) no permite generalizar en ninguna dirección.
4. **Contexto de PartsUnlimitedMRP regenerado.** Los resúmenes de clase los escribió Claude con el prompt literal
   del artefacto. El resumen de base de datos se hizo sobre `schema.psql`, el único esquema del repositorio, aunque
   la aplicación use MongoDB en ejecución. No se sabe qué insumo usaron los autores (D11).
5. **`common_dict` de PartsUnlimitedMRP reconstruido.** La regla reproduce exactamente el diccionario publicado de
   JPetStore. Aun así, quedó con 7 clases en lugar de 8, porque `SimpleCORSFilter` no tiene dependientes en el grafo
   (D50).
6. **Prompt de la línea base reconstruido**, porque el artefacto no lo publica (D45). Puede explicar parte de la
   diferencia con la línea base del paper, sobre todo en PartsUnlimitedMRP.
7. **Lo que añade Claude Code a cada llamada.** Un system prompt fijo ("You are a Claude agent, built on
   Anthropic's Claude Agent SDK.") y bloques `<system-reminder>` con el entorno, la fecha y la cuenta, que suman unos
   590 tokens. No se pueden quitar desde la CLI (D4).
8. **Versión de Claude Code.** La tabla principal usa solo 2.1.330. Usaron otras versiones las 5 repeticiones de la
   Etapa 4 y las 6 corridas aparte (2.1.327), y también la generación de contexto de la Fase 1 (2.1.325). El modelo,
   el esfuerzo y los parámetros que llegan a la API son los mismos en todas (D48, D58, D60).
9. **Posible contaminación de datos.** JPetStore y PartsUnlimitedMRP son repositorios públicos. Es posible que el
   modelo los haya visto durante su entrenamiento, incluidas sus versiones en microservicios, y eso podría favorecer
   sobre todo a la línea base, que recibe el código completo.
10. **`>` frente a `≥` en c2c.** Con `≥`, el c2c@90 de JPetStore / MicroAgent sería 60,0 % en lugar de 26,7 %, y el
    c2c@50 de la línea base de PartsUnlimitedMRP sería 93,3 % en lugar de 86,7 % (§3; D52). WS y F1 no cambian.
11. **El F1 de clases comunes de JPetStore no discrimina.** El diccionario publicado solo evalúa una clase, así que
    da 100 % aunque haya duplicados de más.
12. **Distinto número de corridas.** JPetStore / MicroAgent tiene 10 corridas; las demás configuraciones, 3. La
    desviación de las configuraciones con n = 3 es poco precisa.

---

## 9. Conclusión

**PartsUnlimitedMRP.** La metodología de MicroAgent se sostiene. Con otro modelo y otro orquestador, los mismos
prompts y herramientas producen una descomposición casi idéntica a la referencia, muy por encima de la línea base.

**JPetStore.** MicroAgent puede alcanzar el resultado del paper (4 de 10 corridas), pero con `temperature: 1` su
resultado medio no se distingue del de la línea base. La diferencia se explica casi por completo por la Etapa 4,
que a veces declara comunes clases de negocio, y por la propagación del algoritmo, que agranda ese error. El único
error de MicroAgent que aparece siempre (`CartActionBean` en Order) nace en la Etapa 1 y pesa poco en el WS.

**Lecciones para la tesis:**

- Un pipeline multiagente con LLM tiene que reportarse con varias corridas y su dispersión, no con una sola.
- La identificación de clases comunes es el punto más frágil: concentra la variabilidad, y la métrica la castiga
  con fuerza.
- MicroAgent consume unas 19 a 28 veces más tokens que la línea base. Ese costo hay que ponerlo frente a la mejora
  de calidad, que en esta réplica solo aparece de forma clara en PartsUnlimitedMRP.
