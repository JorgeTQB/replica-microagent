# Las fases de la réplica de MicroAgent: qué hace cada una, qué recibe, qué produce y qué salió

Este documento explica el proyecto; no es una guía de pasos. Las instrucciones están en
`INSTRUCCIONES-REPLICA-MICROAGENT-CLAUDE-CODE.md` y el registro detallado de cada decisión en
`replica-claude-code/DECISIONES.md` (D1 a D61). Aquí se cuenta, fase por fase, **para qué sirve**, **qué entra
y qué sale (con nombres de archivo)** y **qué resultados dio**. Estado al 2026-11-22: fases 1 a 6 terminadas, y
`replica-claude-code/REPORTE.md` y `README.md` escritos.

---

## 0. La idea general en una página

**MicroAgent** (Su et al., ASE '26) toma un monolito Java y lo parte en *n* microservicios. No le da todo el
código a un LLM de una vez: usa **cinco agentes en secuencia**, cada uno con poco contexto y con herramientas
propias para consultar solo lo que necesita.

```
 código Java + esquema BD + n
        │
        ▼
 [Fase 1] Contexto ──► grafo de dependencias, resúmenes de clase, resumen de BD
        │
        ▼
 [Fase 2] Herramientas (servidor MCP) ──► 14 herramientas que leen ese contexto
        │
        ▼
 [Fase 3] Prompts literales ──► los textos exactos que recibe cada agente
        │
        ▼
 [Fase 4] Orquestador: 5 etapas de agentes ──► result.json (la descomposición)  ×3 a 13 corridas por app
        │
 [Fase 5] Línea base zero-shot ──► result.json sin agentes                     ×3 corridas por app
        │
        ▼
 [Fase 6] Evaluación con los scripts originales ──► results.csv (WS, c2c, F1, costos)
```

**Qué se cambió frente al original** (aprobado por el profesor): los agentes corren con **Claude Code**
(`claude -p`) en lugar de CrewAI por API, y se usan **2 de las 10 apps**: **JPetStore** (24 clases, n = 3) y
**PartsUnlimitedMRP** (53 clases, n = 5). Todo lo demás (prompts, lógica de las herramientas, orden de las
etapas, formato de entradas y salidas, scripts de métricas) se mantuvo **igual al artefacto**.

**Modelo:** `claude-sonnet-4-6` en todo, sin razonamiento extendido (el original no lo pide). Claude Code no
deja fijar la temperatura y envía `temperature: 1`; el original usa 0. Esta es la principal amenaza a la
validez y la razón de hacer 3 corridas por configuración.

**Regla que atraviesa todo:** `MicroAgent/` (el artefacto descargado) no se toca. Se comprueba con
`scripts/check_microagent_untouched.py`, que compara la carpeta con `MicroAgent.zip`.

---

## Fase 1 — Preparación del contexto

### Qué hace y por qué
Los agentes de MicroAgent nunca leen el repositorio "a ciegas". Trabajan sobre tres representaciones
precalculadas del monolito, de distinta granularidad:

1. **Grafo de dependencias** (`class_info_dependency.json`): para cada clase, sus métodos, campos y relaciones
   con otras clases (`EXTENDS`, `CALLS`, `USES`, `CREATES`… y sus inversas `EXTENDED_BY`, `CALLED_BY`…, con
   cuántas veces ocurre cada una). Lo genera un analizador Java (JavaParser) que viene en `MicroAgent/graph/`.
2. **Resúmenes de clase** (`class_summaries.json`): un párrafo en lenguaje natural por clase y su ruta de
   archivo, escrito por un LLM con el "Class Summary Prompt" del artefacto.
3. **Resumen de base de datos** (`sql-summary.json`): tablas, columnas, claves y relaciones, escrito por un LLM
   con el "Database Summary Prompt".

Esta fase solo prepara datos; no hay agentes todavía.

### Input
| App | Qué entra |
|---|---|
| JPetStore | El clon `resources/jpetstore-6/` en el commit **`a37c02f`** (2025-06-16). El HEAD actual ya no tiene 5 de las 24 clases. El contexto de los autores (`MicroAgent/microagent/context/test/` y `database/jpetstore-6/`). |
| PartsUnlimitedMRP | El clon `resources/partsunlimited/` (commit `0268218`), carpeta Java `src/Backend/OrderService/src/main/java` (53 archivos), y el esquema `src/Backend/OrderService/scripts/schema.psql`. |

### Qué se hizo con cada app
- **JPetStore:** se **reutiliza el contexto de los autores**, copiado byte a byte. Así la réplica aísla la parte
  de agentes. Como control, se regeneró el grafo con el analizador y salieron 24 de 24 entradas idénticas a las
  de los autores. Ese control y las 1 409 líneas de código que reporta el paper permitieron fijar el commit.
- **PartsUnlimitedMRP:** el artefacto no trae su contexto, así que se generó:
  - Grafo: con el analizador original sin modificar (compilado desde una copia, para no escribir en
    `MicroAgent/`). Se usa el objeto `classes` de su salida, que es el formato que leen las herramientas.
  - Resúmenes: 53 llamadas `claude -p`, una por archivo `.java`, con el prompt literal y sin herramientas. Un
    corte por el límite de 5 horas del plan obligó a reanudar; las 15 llamadas rechazadas no se usaron.
  - Resumen de BD: 1 llamada con el prompt literal sobre `schema.psql`. Es el único esquema del repositorio,
    aunque la app use MongoDB en ejecución. Se reporta como amenaza a la validez (D11, D32).

### Output (lo que reciben las fases siguientes)
```
replica-claude-code/
├── context/jpetstore-6/      class_info_dependency.json (24 clases), class_summaries.json (24)
├── context/partsunlimited/   class_info_dependency.json (53 clases), class_summaries.json (53)
├── database/jpetstore-6/     sql-summary.json
└── database/partsunlimited/  sql-summary.json   (10 tablas, 10 relaciones)
```
Las claves de los dos JSON de cada app son los nombres completos de las clases (FQCN) y coinciden entre sí.
Este conjunto de clases es el **universo** que después se reparte entre los microservicios.

### Resultados y datos clave
- PartsUnlimitedMRP: 53 clases, que son exactamente las 46 de las particiones de la referencia más las 7
  `uncounted`. Las 4 407 líneas de código coinciden con las del paper.
- 8 clases de PartsUnlimitedMRP aparecen en más de una partición de la referencia (las "clases comunes").
- Costo nominal: USD 0,82 por las 54 llamadas válidas. Una primera generación con Sonnet 4.5 y razonamiento
  extendido se descartó y está archivada en `logs/_archivo_sonnet45_thinking/`.
- **El contexto se generó una sola vez** y se usó igual en todas las corridas. Hay una huella SHA-256 que lo
  comprueba antes de cada corrida (D32).

---

## Fase 2 — Herramientas (servidor MCP)

### Qué hace y por qué
Las herramientas son el "contexto aumentado" del paper: cada agente puede pedir solo lo que necesita (el resumen
de una clase, su código y sus relaciones, una búsqueda semántica, la entropía de dependencias, etc.). En el
original son clases de CrewAI (`custom_tools.py`). En la réplica se expone **la misma lógica** a Claude Code
mediante un servidor MCP llamado `microagent`.

### Input
- `MicroAgent/microagent/src/microagent/tools/custom_tools.py` (el original).
- El contexto de la Fase 1, que es lo que leen las herramientas.
- La tabla de herramientas por agente de `crew.py`.

### Qué se hizo
- `tools/custom_tools.py` es la copia del original con **solo 2 líneas cambiadas**, las importaciones de CrewAI
  y de la configuración. Se reemplazan por un *shim* en `tools/microagent_shim.py`. Ningún método `_run` se tocó.
- `tools/mcp_server.py` publica las **14 herramientas** con el mismo nombre, descripción y argumentos que el
  original, y devuelve la misma cadena que `_run`.
- Detalles que hubo que resolver:
  - `MICROAGENT_TOOLS`: cada proceso del servidor publica solo las herramientas de su agente. Si no, el modelo
    veía las 14.
  - `RESULT_FILE`: `write_result_to_json` escribe en el archivo de la etapa y fusiona dominio por dominio, porque
    cada `claude -p` arranca su propio servidor.
  - Modo UTF-8 obligatorio, para que Windows lea los archivos igual que Linux.
  - Tiempos de espera de MCP más largos, porque el servidor tarda hasta unos 60 s en cargar el modelo de
    embeddings.

### Output
```
tools/custom_tools.py, tools/microagent_shim.py, tools/mcp_server.py
logs/tool_smoke_test.txt   ← prueba de humo: 18 llamadas, 0 diferencias con el original
```

### Qué recibe cada agente (de `crew.py`)
| Agente | Herramientas | Límite de turnos |
|---|---|---|
| Domain | jerarquía de clases, resumen BD, todos los resúmenes, info básica, resumen de una clase | 30 |
| Clustering | jerarquía completa, resumen BD, búsqueda semántica, clases relacionadas, código y relaciones, buscar en archivo | 30 |
| Merging | jerarquía completa, resumen BD, código y relaciones, buscar en archivo | 30 |
| Common Class | jerarquía completa, resumen BD, **entropía de dependencias**, **más candidatas comunes**, **asignar clases comunes (propagación)**, escribir resultado, código y relaciones, buscar en archivo | 45 |
| Review | jerarquía completa, resumen BD, código y relaciones, buscar en archivo, escribir resultado, clases relacionadas | 45 |

### Datos clave
- Dos herramientas del original devuelven listas en un orden que cambia según la semilla de hash de Python
  (recorren `set`s). Es del original y no se corrigió. Luego resultó ser una de las fuentes de variabilidad
  (D41).
- Las herramientas pueden leer cualquier ruta, también en el original. Por eso las referencias de evaluación se
  apartaron de `evaluation/references/` mientras se hacían las corridas, y cada corrida audita las rutas que pidió.

---

## Fase 3 — Prompts literales

### Qué hace y por qué
Asegura que cada agente reciba **exactamente el mismo texto** que en el original: el system prompt, armado desde
`agents.yaml` (role, goal, backstory), y el mensaje de usuario, armado desde `tasks.yaml` más el texto dinámico
de `main.py` (resumen de dominios, listas de clases, etc.).

### Input
- `MicroAgent/microagent/src/microagent/config/agents.yaml` y `tasks.yaml`.
- El texto dinámico de `main.py`.
- La forma en que CrewAI 1.8.1 los envuelve.

### Qué se hizo
- En lugar de deducir la plantilla de CrewAI leyendo el código, se **ejecutó el original** con CrewAI 1.8.1 real
  y un LLM simulado que solo registra lo que recibe (`scripts/capture_crewai_prompts.py`). Hay 10 capturas en
  `logs/prompts_golden/`.
- `prompts/build_prompts.py` arma los prompts. `scripts/check_prompts.py` compara la salida con las capturas: el
  mensaje de usuario es idéntico byte a byte en todas las ejecuciones capturadas.
- Tres puntos en los que CrewAI difiere de lo que decían las instrucciones (decididos por Jorge):
  - **D25:** las llaves dobles `{{ }}` del YAML **no** se convierten, igual que en CrewAI.
  - **D26:** el mensaje lleva la envoltura completa de CrewAI ("Current Task… Begin!… Thought:").
  - **D27:** Common Class recibe como contexto la respuesta del Merging Agent (solo si hubo fusión), y Review la
    del Common Class Agent.
- Se excluye a propósito el bloque ReAct (Thought / Action / Observation): Claude llama a las herramientas de
  forma nativa (D28).

### Output
```
prompts/build_prompts.py
logs/prompts_golden/*.json   (capturas del original)
logs/prompts_check.txt       (355 comprobaciones, 0 problemas)
logs/prompts_preview/<app>/  (system prompts y prompt de la Etapa 1)
```

### Datos clave
"Idéntico" se refiere a lo que la réplica entrega a Claude Code. Claude Code agrega por su cuenta un system
prompt fijo de 62 caracteres y 5 bloques `<system-reminder>` (entorno, modelo, tokens, cuenta y fecha), que no
se pueden quitar. Se auditan en cada llamada y siempre midieron lo mismo (954, 167, 86, 650 y 65 caracteres).

---

## Fase 4 — Orquestador y corridas de MicroAgent

### Qué hace
`run_pipeline.py` replica `main.py`: ejecuta las 5 etapas en orden, cada agente en una llamada `claude -p`
independiente con solo sus herramientas, desde una carpeta vacía (`_sandbox/`) y sin las herramientas
integradas de Claude Code.

### Las 5 etapas: qué recibe y qué produce cada una

| Etapa | Recibe | Hace | Produce (en `output/<app>/<run_id>/`) |
|---|---|---|---|
| **1. Domain** | El prompt de identificación y `n`. Con herramientas consulta jerarquía, resúmenes y BD. | Identifica al menos *n* dominios de negocio y los describe. | `domains/domain_clusters.json` (`business_domains`: nombre y descripción) |
| **2. Clustering** (un agente por dominio) | Su dominio y su descripción, más el resumen de todos los dominios. | Reúne las clases de su dominio (búsqueda semántica y clases relacionadas). | `domains/<Dominio>.json` y `domains/all_domains.json` (`{dominio: [clases]}`) |
| **3. Merging** (solo si hay más de *n* dominios) | `all_domains` (repr de Python) y la lista de dominios. | Fusiona hasta tener exactamente *n*. | `domains/merged_domains.json`; si se salta, es una copia de `all_domains.json`. |
| **4. Common Class** | Los dominios fusionados y, si hubo fusión, la respuesta del Merging Agent. | Mide la entropía de dependencias, elige las clases comunes y las **propaga** por dependencias a los dominios que las usan. | `common_result.json` (escrito con `write_result_to_json`) |
| **5. Review** | `common_result.json` más la lista de clases que aún no están en ningún dominio. | Asigna o descarta las sueltas y corrige inconsistencias. | **`result.json` = la descomposición final** |

Además, por cada llamada queda en `logs/` el prompt exacto, el flujo `stream-json`, la transcripción, el texto
crudo y la respuesta final, la auditoría y el registro del servidor. Por corrida quedan `run_manifest.json`
(configuración, versiones y huellas) y `run_status.json` (turnos, peticiones, tokens, costo por etapa y
observaciones).

### Decisiones que importan para entender las corridas
- **Respuesta final:** como en CrewAI, es lo que sigue al último `Final Answer:`. Claude casi nunca escribe esa
  etiqueta, y entonces se toma el texto completo (observación `sin_etiqueta_final_answer`, D31).
- **Límite de turnos:** como en el original, al alcanzarlo se pide la respuesta final en una petición más, en
  lugar de fallar (D39). En las corridas reales nunca se alcanzó.
- **`--max-turns` cuenta peticiones a la API, no llamadas a herramientas.** Claude pide varias herramientas por
  petición, así que el campo `num_turns` puede pasar de 30 sin que se haya llegado al límite (D44).
- **Validez:** una llamada se invalida si el servidor MCP no conecta, si el agente ve o usa herramientas que no
  son suyas, si responde otro modelo, si el prompt no llega idéntico, si hay razonamiento extendido o si cambia
  la versión de Claude Code.
- Prueba sin cupo con un `claude` simulado que reproduce las capturas del original: 188 comprobaciones, 0
  problemas.

### Resultados de las corridas (3 por app, todas completas, sin fallos)

**JPetStore** (claude-run1 a run3, 2026-11-20):
- Las 3 corridas coinciden hasta la Etapa 3:
  - Etapa 1: **4 dominios** (Account Management, Catalog, Shopping Cart, Order Management).
  - Etapa 3: **la fusión se ejecuta** y junta Shopping Cart con Order Management, con lo que quedan 3.
- Se separan en la **Etapa 4**:
  - run1 declara común solo `AbstractActionBean`, igual que la referencia.
  - run2 y run3 declaran comunes además clases de negocio (`CatalogService`, `Item`, `ItemMapper`, `Account` y,
    en run2, `Product`). La propagación las copia a otros servicios.
- La Etapa 5 no cambió nada en ninguna corrida. Costo nominal: USD 1,08, 1,19 y 1,11.

**PartsUnlimitedMRP** (claude-run1 a run3, 2026-11-21):
- Etapa 1: **5 dominios** en las 3 (Catalog, Dealer, Quote, Order, Shipment, con nombres algo distintos), así
  que **la fusión se salta**.
- Las Etapas 1 a 3 tienen el mismo contenido en las 3 corridas.
- En la Etapa 4, el Common Class Agent reparte las clases transversales (configuración, utilidades,
  excepciones, filtros) en los 5 dominios. En run2 pone además `BadRequestException` en Catalog y Dealer, que es
  su único error.
- Las 53 clases quedan asignadas. Costo nominal: USD 1,68, 1,35 y 1,63.

**Repeticiones aisladas de la Etapa 4** (`claude-run1-e4-r01` a `r05`):
- Toman la salida de la Etapa 3 de claude-run1 y repiten **solo la Etapa 4**, con una entrada idéntica byte a
  byte. No son corridas completas ni entran en la tabla principal.
- Sirvieron para demostrar que la variabilidad de JPetStore sale del muestreo (`temperature: 1`) y del orden de
  las listas de dos herramientas, y no de un error de la réplica (D41, D43).
- WS: 92,7 / 76,4 / 86,3 / 86,3 / 92,7 %. Costo total: USD 0,63.

---

## Fase 5 — Línea base "LLM base" (zero-shot)

### Qué hace y por qué
Es el punto de comparación del paper: el mismo modelo, **sin agentes ni herramientas**, recibe de una vez todo
el código y el esquema de BD, y se le pide la partición. Sirve para medir cuánto aporta la arquitectura de
MicroAgent.

### Input
- El código de las clases del universo (las 24 o 53 claves de `class_summaries.json`), tal cual, con su ruta.
  Quedan fuera los XML de MyBatis, los JSP, las pruebas y los datos de ejemplo.
- El esquema crudo: `jpetstore-hsqldb-schema.sql` o `schema.psql`.
- *n*.
- El artefacto **no publica el prompt** de la línea base. Se reconstruyó en inglés y sin ejemplos (D45). El
  formato de salida es `{"<Servicio>": ["<FQCN>", ...]}`.
- Tamaño del prompt: unos 74 000 caracteres en JPetStore y unos 171 000 en PartsUnlimitedMRP.

### Qué se hizo
`run_baseline.py`: una sola llamada `claude -p` por corrida, sin herramientas y con la misma configuración que
el orquestador. La respuesta se limpia con la misma `clean_json_output` y **no se corrige nada**: si faltan
clases o sobran servicios, lo penalizan las métricas.

### Output
`output/<app>/baseline-runK/result.json` y sus `logs/` (prompt, respuesta, auditoría, `run_status.json`).

### Resultados (6 corridas, 2026-11-21)
- Las 6 devolvieron exactamente *n* servicios y asignaron todas las clases.
- **JPetStore:** las 3 respuestas son la misma partición (Account / Catalog / Order), con 6 clases duplicadas
  entre servicios.
- **PartsUnlimitedMRP:** las 3 respuestas difieren un poco entre sí. El modelo pone en los 5 servicios 13
  clases de configuración y utilidad, y reparte modelos y repositorios en 2 a 4 servicios.
- Costo total: USD 0,59. Las corridas 2 y 3 aprovecharon la caché de prompts, por eso cuestan menos.

---

## Fase 6 — Evaluación con los scripts originales

### Qué hace
Compara cada `result.json` con la **referencia** (ground truth): la descomposición que los autores sacaron de
la versión real en microservicios de cada app, publicada en `MicroAgent/decomposition/`. Se usan los dos scripts
del artefacto **sin modificarlos**:
- `json_similarity.py` calcula el **WS** (similitud ponderada) y el **c2c**.
- `common_metrics.py` calcula la **P, R y F1 de clases comunes**.

### Input
| Qué | Archivo |
|---|---|
| Referencias (copias byte a byte) | `evaluation/references/jpetstore-6.json`, `partsunlimited.json` |
| `common_dict` (qué servicios deberían tener cada clase común) | `evaluation/common_dicts/jpetstore-6.json` (publicado), `partsunlimited.json` (**reconstruido**) |
| Las 12 descomposiciones | `output/<app>/{claude,baseline}-run{1..3}/result.json` |
| Turnos, tokens, costo | `logs/run_status.json` y `logs/run_manifest.json` de cada corrida |

### Qué mide cada métrica
- **WS (Weighted Similarity):** cada partición producida se empareja con la partición de referencia más
  parecida, con similitud = |intersección| / máx(tamaños), y se promedia ponderando por tamaño. Se calcula en las
  dos direcciones y se combina con media armónica. Excluye las clases `uncounted` (infraestructura que la
  referencia no reparte).
- **c2c@50/75/90:** proporción de particiones cuyo mejor emparejamiento supera el 50, 75 o 90 % de similitud. El
  script usa `>` y el paper dice `≥`. Se reporta como el script, y la diferencia se documenta porque aquí sí
  cambia algunos valores (D52).
- **F1 de clases comunes:** para cada clase común, un servicio "debería" contenerla si contiene alguna clase que
  dependa de ella. Se compara con lo que hizo la descomposición. Se reportan micro y macro, porque el paper no
  dice cuál usó.

### El `common_dict` reconstruido (decisión de Jorge, D50)
- El artefacto solo publica el de JPetStore, con una única clase común (`AbstractActionBean`).
- Para PartsUnlimitedMRP se reconstruyó con la regla: clases comunes = las que están en más de una partición de
  la referencia; dependientes = clases con relación directa hacia ella en el grafo. Aplicada a JPetStore, esa
  regla reproduce exactamente el diccionario publicado.
- En PartsUnlimitedMRP salen las 8 clases esperadas, pero `SimpleCORSFilter` no tiene ningún dependiente en el
  grafo: es un filtro que Spring registra solo. Con una lista vacía, la propia referencia quedaría castigada.
  **Se excluyó (opción A) y quedaron 7 clases.**

### Output
```
evaluation/
├── evaluate.py, build_common_dict.py
├── results.csv                  ← una fila por corrida, más media, desviación, mediana, mín. y máx. por grupo
├── results_e4_repeticiones.csv  ← las 5 repeticiones de la Etapa 4, aparte
├── sanity_check.json            ← referencia contra sí misma = 1,0 en todo
├── error_analysis.md / .json    ← qué clase quedó mal y en qué servicio, por corrida
└── raw/                         ← salida completa de los scripts originales por corrida
```

### Resultados (media ± desviación estándar muestral, en %)

Todas las corridas de esta tabla usan Claude Code 2.1.330. JPetStore / MicroAgent tiene n = 10 (D58) y el resto,
n = 3. Las primeras corridas de MicroAgent, hechas con 2.1.327, se repitieron con 2.1.330 y quedan aparte (D60).

| App | Configuración | n | WS | c2c@50 | c2c@75 | c2c@90 | F1 comunes (micro) | Paper, WS (Fig. 3) |
|---|---|---|---|---|---|---|---|---|
| JPetStore | MicroAgent | 10 | 85,55 ± 7,96 | 100 | 83,3 ± 28,3 | 26,7 ± 34,4 | 100 | ≈ 93 |
| JPetStore | Línea base | 3 | 84,20 ± 0,00 | 100 | 100 | 33,3 | 100 | ≈ 81,5 |
| PartsUnlimitedMRP | MicroAgent | 3 | 99,56 ± 0,76 | 100 | 100 | 100 | 100 | ≈ 100 |
| PartsUnlimitedMRP | Línea base | 3 | 66,58 ± 0,52 | 86,7 ± 11,5 | 40,0 | 0 | 95,52 | ≈ 79,5 |

WS de MicroAgent por corrida:
- JPetStore, run4 a run13: 86,3 / 92,7 / 92,7 / 70,7 / 74,4 / 92,7 / 86,3 / 86,3 / 92,7 / 81,0 %.
- PartsUnlimitedMRP, run4 a run6: 100 / 98,7 / 100 %.

Las corridas aparte, con 2.1.327, dieron 79,87 ± 11,11 % en JPetStore y 99,13 ± 1,50 % en PartsUnlimitedMRP. Las
diferencias con las corridas de 2.1.330 caben en la variabilidad normal entre corridas.

### Qué significan
- **PartsUnlimitedMRP reproduce el paper:** MicroAgent queda en ≈ 100 % y supera a la línea base por unos 33
  puntos.
- **JPetStore no reproduce la ventaja.** La mejor corrida (92,7 %, en 4 de 10 corridas) coincide con el ≈ 93 % del
  paper. La media, en cambio, queda solo 1,4 puntos por encima de la línea base, con una desviación de 8 puntos.
  La causa es la Etapa 4, que a veces declara comunes clases de negocio. Las 5 repeticiones aisladas lo confirman.
- **Error constante de MicroAgent en JPetStore:** `CartActionBean` termina en Order y no en Catalog. Nace en la
  Etapa 1, cuando se crea un dominio "Shopping Cart" propio.
- **Error típico de la línea base:** duplica clases en varios servicios (entre 21 y 24 de más en
  PartsUnlimitedMRP), y eso hunde el c2c@75 y el c2c@90.
- **En JPetStore el F1 de clases comunes no distingue entre configuraciones:** el diccionario publicado solo
  mira `AbstractActionBean` y todas las corridas la ponen bien.
- El control de cordura da 1,0, los 17 valores coinciden con los calculados a mano antes, y un revisor
  independiente recalculó todo sin encontrar diferencias.

---

## Resumen del gasto (costo nominal que informa Claude Code; el plan Pro no cobra por llamada)

| Qué | USD |
|---|---|
| Fase 1: contexto de PartsUnlimitedMRP (54 llamadas válidas) | 0,82 |
| Fase 4: pruebas reales del orquestador (7 llamadas) | 0,48 |
| MicroAgent JPetStore, tabla principal (10 corridas, 2.1.330) | 10,87 |
| MicroAgent PartsUnlimitedMRP, tabla principal (3 corridas, 2.1.330) | 4,24 |
| MicroAgent, corridas aparte con 2.1.327 (3 + 3) | 3,38 + 4,66 |
| Repeticiones de la Etapa 4 (5) | 0,63 |
| Línea base (6 corridas) | 0,59 |

---

## Amenazas a la validez que hay que tener presentes al leer los resultados
1. **Otro modelo** (Claude Sonnet 4.6, que no es ninguno de los tres del paper) y **`temperature: 1`** en lugar
   de 0. Esto explica gran parte de la variabilidad entre corridas.
2. **Solo 2 de 10 apps.** Los promedios del paper (WS 89,2 %, F1 93,4 %) no se pueden comparar directamente.
3. **Contexto de PartsUnlimitedMRP regenerado** con Claude, con un resumen de BD hecho sobre `schema.psql`
   (no se sabe qué insumo usaron los autores).
4. **`common_dict` de PartsUnlimitedMRP reconstruido**, con 7 clases en lugar de 8.
5. **Lo que añade Claude Code** a cada llamada: un system prompt fijo y bloques con la fecha, el entorno y la
   cuenta. La tabla principal usa una sola versión de la CLI (2.1.330); con 2.1.327 quedan solo las repeticiones
   de la Etapa 4 y las corridas aparte (D60).
6. **Prompt de la línea base reconstruido**, porque el artefacto no lo publica. Incluye una frase de la
   especificación (no del paper) que permite repetir clases compartidas, y repetir clases es justo el error
   principal de la línea base en PartsUnlimitedMRP (D61).
7. **Posible contaminación de datos:** las dos apps son públicas y el modelo pudo haberlas visto al entrenarse.
8. **`>` frente a `≥`** en el c2c: con `≥`, el c2c@90 de JPetStore / MicroAgent sería 60,0 % y el c2c@50 de
   la línea base de PartsUnlimitedMRP, 93,3 % (D52, D59). El paper usa las dos formas.
9. **Más llamadas a herramientas que en el original:** `--max-turns` cuenta peticiones y Claude pide varias
   herramientas por petición. El Domain Agent de PartsUnlimitedMRP hizo 32 a 48 llamadas, más de las 30 que
   permitía `max_iter` (D61).
10. **Otras versiones de las bibliotecas** de la búsqueda semántica (sentence-transformers, transformers, torch)
    que las del `uv.lock` del artefacto; ahora fijadas en `requirements.txt` (D61).
