# Instrucciones para Claude Code: réplica de MicroAgent (ASE '26)

> **Para Claude Code:** este documento es la especificación completa de la tarea. Léelo entero antes de empezar. Síguelo al pie de la letra. Si algo no está especificado o no se puede hacer como dice, **no improvises en silencio**: registra el problema y la decisión que tomaste en `DECISIONES.md` (ver §11).

---

## 0. Contexto y objetivo

Soy Jorge Quispe, tesista de Ingeniería de Sistemas en la Universidad de Lima. Mi tesis propone un framework multiagente con LLM que descompone monolitos Java en microservicios. Como parte del curso, tengo que **replicar un paper**. Elegí:

> Su, Z., Huang, J., Shan, S., Chen, X., Zeng, H., Su, Y., Wang, Y. y Lyu, M. R. (2026). *MicroAgent: Context-Augmented Multi-agent Framework for Automatic Microservice Decomposition*. ASE '26. doi:10.1145/3832783.3834441. Artefacto: doi:10.5281/zenodo.19250602.

**Qué hace MicroAgent:** recibe el código de un monolito Java, su esquema de base de datos y el número objetivo de microservicios *n*. Cinco agentes LLM trabajan en secuencia y producen una partición de clases (qué clases van en cada microservicio):
1. **Domain Agent:** identifica al menos *n* dominios de negocio y los describe.
2. **Clustering Agents:** se crea uno por dominio, y cada uno reúne las clases de su dominio.
3. **Merging Agent:** solo actúa si hay más de *n* dominios, y los fusiona hasta llegar a *n*.
4. **Common Class Agent:** detecta las clases compartidas (utilidades, DTO, coordinadores) usando entropía de dependencias, y las asigna a varios dominios con un algoritmo de propagación.
5. **Review Agent:** asigna o descarta las clases que quedaron sueltas y corrige inconsistencias.

**Objetivo de esta réplica:** reproducir **la misma metodología** sobre **dos aplicaciones (JPetStore y PartsUnlimitedMRP)** y comparar los resultados con los del paper. El profesor aprobó estas dos modificaciones:
- Los agentes se ejecutan con **Claude Code (plan Pro)**, no por API con CrewAI.
- Basta con **2 de las 10 aplicaciones**.

**Principio rector:** todo lo que no sea una de esas dos modificaciones **debe ser igual al artefacto original**: los mismos prompts (en inglés y literales), las mismas herramientas con la misma lógica, el mismo orden de etapas, el mismo formato de entradas y salidas y los mismos scripts de métricas. No hay que "mejorar" nada. El objetivo es medir si la metodología se sostiene, no optimizarla.

---

## 1. Qué se mantiene y qué cambia

| Aspecto | Original (artefacto) | Réplica | Tipo |
|---|---|---|---|
| Orquestación | CrewAI 1.8.1, `main.py` secuencial | Script Python que replica `main.py` y llama a `claude -p` en cada etapa | **Cambio aprobado** |
| LLM | DeepSeek-V3.2 (principal), GPT-5.2, Claude Sonnet 4.5; temperatura 0 | Un solo modelo Claude vía Claude Code Pro, **fijado con `--model`**; sin control de temperatura | **Cambio aprobado** |
| Repeticiones | 1 corrida (implícita) | **3 corridas** por aplicación y configuración; se reportan media y desviación estándar | Consecuencia del cambio |
| Formato de llamada a herramientas | Plantilla ReAct de CrewAI (Thought/Action/Observation) | Llamada a herramientas nativa de Claude (vía MCP) | Consecuencia del cambio |
| Aplicaciones | 10 | **JPetStore (n = 3) y PartsUnlimitedMRP (n = 5)** | **Cambio aprobado** |
| Prompts de agentes | `agents.yaml` + `tasks.yaml` + texto dinámico de `main.py` | **Idénticos, literales** | Igual |
| Herramientas | `custom_tools.py` | **La misma lógica `_run`**, expuesta por un servidor MCP | Igual |
| Herramientas por agente y límite de iteraciones | `crew.py` | Igual (§5.3); límite → `--max-turns` | Igual |
| Contexto (grafo, resúmenes, BD) | `graph/` (JavaParser) + prompts de `prompt/context_preparation_prompt.md` | Igual. JPetStore: **se reutiliza el contexto que publican**. PartsUnlimitedMRP: se genera con el mismo analizador y los mismos prompts, y los resúmenes los hace Claude | Igual o parcial |
| Métricas | `metrics/json_similarity.py`, `metrics/common_metrics.py` | **Los mismos scripts**, sin modificar su lógica | Igual |
| Métricas arquitectónicas (CMod, CiD, BCP) | Repositorio de Wang et al. (ASE '24) | **Fuera de alcance** (opcional, §9.4) | Recorte |

---

## 2. Ubicación de los archivos

Carpeta base (en mi computadora): `C:\Jorge Quispe Bendezu\ULima\Tesis\Replica de Paper\`

```
Replica de Paper/
├── MicroAgent/                         ← artefacto original (SOLO LECTURA, no modificar)
│   ├── graph/                          ← analizador Java (JavaParser) → class_info_dependency.json
│   ├── microagent/
│   │   ├── context/test/               ← contexto de JPetStore ya preparado por los autores
│   │   ├── database/jpetstore-6/       ← sql-summary.json de JPetStore
│   │   └── src/microagent/
│   │       ├── main.py                 ← orquestación original (a replicar)
│   │       ├── crew.py                 ← agentes, herramientas por agente, max_iter, temperatura
│   │       ├── config/agents.yaml      ← system prompts (role, goal, backstory)
│   │       ├── config/tasks.yaml       ← task prompts (description, expected_output)
│   │       └── tools/custom_tools.py   ← implementación de las herramientas
│   ├── metrics/                        ← json_similarity.py, common_metrics.py, test/
│   ├── decomposition/                  ← **DESCOMPOSICIONES DE REFERENCIA (ground truth)**, no resultados
│   └── prompt/                         ← prompts de preparación de contexto
├── MicroAgent Conference Paper.pdf
└── replica-claude-code/                ← **AQUÍ trabajas tú** (créala)
```

**Regla:** nunca edites nada dentro de `MicroAgent/`. Copia a `replica-claude-code/` lo que necesites.

---

## 3. Estructura de trabajo que debes crear

```
replica-claude-code/
├── DECISIONES.md                 ← registro de toda desviación o decisión (§11)
├── README.md                     ← cómo correr todo, al final
├── requirements.txt
├── resources/
│   ├── jpetstore-6/              ← código fuente clonado
│   └── partsunlimited/           ← código fuente clonado
├── context/
│   ├── jpetstore-6/              ← class_info_dependency.json, class_summaries.json
│   └── partsunlimited/
├── database/
│   ├── jpetstore-6/sql-summary.json
│   └── partsunlimited/<algo>-summary.json
├── tools/
│   ├── custom_tools.py           ← copia del original + shim (§5.1)
│   └── mcp_server.py             ← servidor MCP "microagent"
├── prompts/
│   └── build_prompts.py          ← arma los prompts literales desde agents.yaml/tasks.yaml
├── run_pipeline.py               ← orquestador (réplica de main.py)
├── run_baseline.py               ← LLM base zero-shot (§8)
├── output/<app>/<run_id>/        ← salidas, con la misma estructura que el original
│   ├── domains/domain_clusters.json, <Dominio>.json, all_domains.json, merged_domains.json
│   ├── common_result.json
│   ├── result.json               ← DESCOMPOSICIÓN FINAL
│   └── logs/                     ← prompt enviado, salida cruda y JSON de claude por etapa
├── evaluation/
│   ├── references/               ← copia de decomposition/jpetstore.json y partsunlimited.json
│   ├── common_dicts/             ← common_dict por app (§9.2)
│   ├── evaluate.py               ← invoca los scripts originales
│   └── results.csv               ← tabla final
└── REPORTE.md                    ← resultados y comparación con el paper
```

---

## 4. Fase 1: preparación del contexto

### 4.1 Entorno
- Python 3.10 a 3.13, Java 11 o superior, Maven y Git.
- Paquetes Python: `sentence-transformers>=4.1.0`, `scikit-learn`, `numpy`, `pyyaml` y el SDK de MCP para Python (`mcp`, que incluye FastMCP). **No** hace falta instalar CrewAI (ver el shim en §5.1).
- Claude Code CLI con sesión iniciada en el plan Pro. **Antes de escribir el orquestador, ejecuta `claude --help`** y confirma los nombres exactos de estas opciones en la versión instalada: `-p/--print`, `--output-format json`, `--model`, `--max-turns`, `--mcp-config`, `--strict-mcp-config`, `--allowedTools`/`--allowed-tools`, `--disallowedTools`, `--tools` (para desactivar las herramientas integradas) y `--system-prompt`/`--append-system-prompt`. Si alguna no existe, anota la alternativa en `DECISIONES.md`.

### 4.2 JPetStore (`app_name = "jpetstore-6"`, n = 3, num = "THREE")
1. Clona `https://github.com/mybatis/jpetstore-6` en `resources/jpetstore-6/`.
2. **Reutiliza el contexto de los autores** (así la réplica aísla la etapa de agentes):
   - `MicroAgent/microagent/context/test/class_info_dependency.json` → `context/jpetstore-6/`
   - `MicroAgent/microagent/context/test/class_summaries.json` → `context/jpetstore-6/`
   - `MicroAgent/microagent/database/jpetstore-6/sql-summary.json` → `database/jpetstore-6/`
3. **Verificación obligatoria:** los dos JSON tienen **24 clases** con las mismas claves. Para cada clase, el `file_path` de `class_summaries.json` (formato `resources/jpetstore-6/src/main/java/...`) debe existir en tu clon. Si alguna clase no existe (el repositorio pudo cambiar), haz checkout de un commit anterior en el que coincidan las 24 y anota el commit en `DECISIONES.md`.
4. (Opcional, como control) Regenera el grafo con el analizador (§4.3, paso 2) y compara las claves con las de los autores. Anota las diferencias, pero **usa el de los autores**.

### 4.3 PartsUnlimitedMRP (`app_name = "partsunlimited"`, n = 5, num = "FIVE")
1. Clona `https://github.com/microsoft/PartsUnlimitedMRP` en `resources/partsunlimited/`. Localiza la raíz Java que contiene el paquete `smpl/ordering` (es el servicio de órdenes). Esa es la ruta de código a analizar.
2. **Grafo de dependencias**, con el analizador original y sin modificarlo:
   ```
   cd MicroAgent/graph   (o una copia en replica-claude-code/graph)
   mvn clean package
   java -jar target/java-class-analyzer.jar <ruta_java_de_smpl_ordering> --json <...>/context/partsunlimited/class_info_dependency.json --dot <...>/diagram.dot --jpg <...>/diagram.jpg
   ```
   Si Maven o Graphviz fallan por la salida `.dot`/`.jpg`, prueba primero solo con `--json`. Anota cualquier problema.
3. **Resúmenes de clase** (`class_summaries.json`): usa **literalmente** el prompt "Class Summary Prompt" de `MicroAgent/prompt/context_preparation_prompt.md`, **un archivo `.java` por llamada** (reemplaza `{java_class_content}` por el contenido; `{{`/`}}` → `{`/`}`). Hazlo con `claude -p` sin herramientas y con el mismo `--model` que el resto. Une los JSON. Requisitos:
   - Las claves son nombres de clase completos (FQCN) y deben coincidir **exactamente** con las claves de `class_info_dependency.json`. Si hay clases en un JSON y no en el otro, regístralo y concilia.
   - `file_path` en formato `resources/partsunlimited/<ruta relativa al .java>` (las herramientas lo resuelven desde la raíz de trabajo).
   - Las clases internas no llevan entrada propia (lo dice el prompt).
4. **Resumen de base de datos:** busca en el repositorio la definición de datos del servicio de órdenes: scripts `*.sql`, scripts de inicialización de MongoDB o, en su defecto, las clases de `smpl.ordering.repositories.mongodb.models`. Si hay SQL, usa literalmente el "Database Summary Prompt". Si solo hay MongoDB (lo esperable), usa el mismo prompt cambiando únicamente el insumo (documentos o modelos en vez de SQL) y conservando el formato de salida `schema_summary.tables/relationships`. Guárdalo como `database/partsunlimited/mongodb-summary.json`; el nombre debe terminar en `-summary.json` porque la herramienta busca con ese patrón. Registra la decisión.
5. **Verificación:** la referencia (`MicroAgent/decomposition/partsunlimited.json`) tiene **46 clases distintas en particiones** y **7 clases distintas en `uncounted`** (la lista trae `AppInsightsFilter` repetida). El paper reporta 53 clases. Compara tu universo de clases con esas listas y anota las diferencias.

---

## 5. Fase 2: herramientas (servidor MCP)

### 5.1 Reutilizar `custom_tools.py` sin cambiar su lógica
1. Copia `MicroAgent/microagent/src/microagent/tools/custom_tools.py` a `tools/custom_tools.py`.
2. El archivo importa `from crewai.tools import BaseTool` y `from ..config.config import APP_CONFIG, WORKING_DIR`. Reemplaza **solo esas importaciones** por un *shim* mínimo:
   - Una clase `BaseTool(pydantic.BaseModel)` con los campos `name`, `description` y `args_schema`, que permita atributos privados (`_model`, `_class_info`, etc.).
   - `APP_CONFIG = {"app_name": os.environ["APP_NAME"], "model_name": os.environ["RUN_ID"], "java_paths": ["src/main/java"]}` y `WORKING_DIR = <ruta absoluta de replica-claude-code>`.
   - **No toques ningún método `_run`.** Si algo no compila sin tocarlo, anota exactamente qué cambiaste.
3. Nota: `APP_CONFIG["model_name"]` se usa en las rutas `output/<app>/<model_name>/domains/...`. En la réplica ese campo lleva el **identificador de la corrida** (p. ej. `claude-run1`), para que cada corrida tenga su propia carpeta.

### 5.2 Servidor MCP
Crea `tools/mcp_server.py` (FastMCP, transporte stdio) llamado **`microagent`**, que exponga cada herramienta con **el mismo `name`, la misma `description` y los mismos argumentos** que su clase original, y que devuelva la cadena que produce `_run`. Las herramientas necesarias son:

| Nombre de la herramienta (exacto) | Clase original | Argumentos |
|---|---|---|
| `get_all_class_hierarchy` | GetAllClassHierarchy | ninguno (marca las clases sin relaciones como "isolated class") |
| `get_all_class_hierarchy_complete` | GetAllClassHierarchyComplete | ninguno |
| `get_database_summary` | GetDatabaseSummary | ninguno |
| `get_all_class_summaries` | GetAllClassSummaries | ninguno |
| `get_class_summary` | GetClassSummary | `class_name` |
| `get_class_basic_info` | GetClassBasicInfo | `class_name` |
| `get_class_relation_and_code` | GetClassRelationAndCode | `class_name` |
| `search_file` | SearchFile | `path`, `term` |
| `codebase_semantic_search` | CodebaseSemanticSearch | `query` |
| `get_related_class_list` | GetRelatedClassList | `class_names: list[str]` |
| `rank_dependency_entropy` | RankDependencyEntropyAndRatio | ninguno. **Ojo:** el nombre real es `rank_dependency_entropy`, aunque el paper diga `rank_dependency_entropy_and_ratio` |
| `get_more_potential_common_classes` | GetMorePotentialCommonClasses | `common_classes: list[str]` |
| `assign_common_class_list` | AssignCommonClassList | `common_class_domains: dict` |
| `write_result_to_json` | WriteResultToJson | `domain_name`, `class_list: list[str]` |

**`write_result_to_json`:** en el original acumula resultados en una variable de clase y escribe en un archivo fijado con `set_output_file`. Como cada llamada a `claude -p` arranca su propio proceso del servidor, el servidor debe leer la ruta de salida de la variable de entorno `RESULT_FILE`, escribir de forma incremental y **fusionar** con lo que ya exista en el archivo (dominio por dominio). El orquestador borra o inicializa ese archivo antes de cada etapa.

**Parámetros que ya trae el código (no cambiarlos):**
- `codebase_semantic_search`: modelo `all-MiniLM-L6-v2`; top_n = max(5, int(nº de clases / nº de dominios)), con el nº de dominios leído de `output/<app>/<run_id>/domains/domain_clusters.json` (6 si no existe); solo devuelve resultados con similitud de coseno > 0,3.
- `rank_dependency_entropy`: lee `domains/merged_domains.json`; solo considera los tipos de relación directos (`EXTENDS, IMPLEMENTS, CALLS, USES, REFERENCES, INJECTS, ASSOCIATES, ANNOTATED_WITH, CREATES, PERSISTS, DEPENDS_ON`); cuenta un evento por cada par (tipo de relación, clase destino); devuelve el **tercio superior** por entropía (con empates) y solo las que tienen entropía > 0, para entrante y saliente, con sus ratios.
- `assign_common_class_list`: ordenamiento topológico y propagación para `incoming` (de dependientes a dependencias) y `outgoing`.

Antes de seguir, prueba cada herramienta con JPetStore (por ejemplo, `get_class_summary("org.mybatis.jpetstore.domain.Cart")`) y guarda las salidas en `logs/tool_smoke_test.txt`.

### 5.3 Herramientas y límite de turnos por agente (de `crew.py`)

| Agente | Herramientas permitidas (exactamente estas) | max_iter → `--max-turns` |
|---|---|---|
| Domain | `get_all_class_hierarchy`, `get_database_summary`, `get_all_class_summaries`, `get_class_basic_info`, `get_class_summary` | 30 |
| Clustering | `get_all_class_hierarchy_complete`, `get_database_summary`, `codebase_semantic_search`, `get_related_class_list`, `get_class_relation_and_code`, `search_file` | 30 |
| Merging | `get_all_class_hierarchy_complete`, `get_database_summary`, `get_class_relation_and_code`, `search_file` | 30 |
| Common Class | `get_all_class_hierarchy_complete`, `get_database_summary`, `rank_dependency_entropy`, `assign_common_class_list`, `get_more_potential_common_classes`, `write_result_to_json`, `get_class_relation_and_code`, `search_file` | 45 |
| Review | `get_all_class_hierarchy_complete`, `get_database_summary`, `get_class_relation_and_code`, `search_file`, `write_result_to_json`, `get_related_class_list` | 45 |

**Aislamiento del contexto (crítico, es la idea central del paper):**
- Cada agente debe tener **solo** sus herramientas MCP. **Desactiva todas las herramientas integradas de Claude Code** (Read, Grep, Glob, Bash, Edit, Write, WebFetch, Task, etc.) con `--tools ""` o, si no existe, con `--disallowedTools`. Permite solo `mcp__microagent__<herramienta>` según la tabla, y usa `--strict-mcp-config` para que no se cargue ningún otro servidor MCP.
- Ejecuta cada `claude -p` desde un **directorio de trabajo vacío** (p. ej. `replica-claude-code/_sandbox/`), sin `CLAUDE.md`, para que no se cuele contexto del proyecto.
- Verifica en el log de la primera corrida que el agente **no** llamó a ninguna herramienta fuera de su lista.

---

## 6. Fase 3: prompts (literales)

`prompts/build_prompts.py` debe cargar `MicroAgent/microagent/src/microagent/config/agents.yaml` y `tasks.yaml` y armar los prompts así:

- **System prompt de cada agente** = `role` + `goal` + `backstory` del YAML, en este formato, que es el que usa CrewAI:
  ```
  You are {role}. {backstory}
  Your personal goal is: {goal}
  ```
  Pásalo con `--system-prompt`. Si esa opción no existe, usa `--append-system-prompt` y anótalo: Claude Code añade su propio system prompt.
- **User prompt de cada tarea** = el texto dinámico que antepone `main.py` (§7) + `description` + `"\n\nThis is the expected criteria for your final answer: "` + `expected_output` + `"\nyou MUST return the actual complete content as the final answer, not a summary."`. Esta es la plantilla de tarea de CrewAI. Si en la versión 1.8.1 de CrewAI (puedes revisarla en PyPI o GitHub) el texto difiere, usa el de esa versión y anótalo.
- **Sustituciones:** `{number}` → `"3"` o `"5"`; `{num}` → `"THREE"` o `"FIVE"`; `{{` → `{` y `}}` → `}` (escapes de CrewAI).
- El backstory del Merging Agent contiene `{number}`: sustitúyelo también.
- **No traduzcas, no resumas y no "mejores" ningún prompt.** Guarda el prompt final exacto de cada llamada en `output/<app>/<run_id>/logs/<etapa>_prompt.txt`.
- **No incluyas** la plantilla ReAct (Thought/Action/Observation) de `prompt/agent_prompt_template.md`: Claude usa llamadas a herramientas nativas. Regístralo como diferencia esperada.

---

## 7. Fase 4: orquestador `run_pipeline.py` (réplica de `main.py`)

Reproduce **la misma lógica y el mismo orden** de `MicroAgent/microagent/src/microagent/main.py`. Léelo antes de programar. Resumen de lo que debe hacer:

**Parámetros:** `--app {jpetstore-6|partsunlimited}`, `--number {3|5}`, `--num {THREE|FIVE}`, `--run-id claude-runK`, `--model <id>`.
**Cada llamada a un agente:** `claude -p "<user_prompt>" --system-prompt "<system_prompt>" --model <id> --max-turns <N> --output-format json --mcp-config <json generado> --strict-mcp-config <restricción de herramientas>`, con el entorno del servidor MCP `APP_NAME`, `RUN_ID`, `RESULT_FILE`. Guarda en `logs/` el JSON completo que devuelve `claude`: texto final, número de turnos, duración, uso de tokens y costo estimado si lo reporta.
**Limpieza de JSON:** copia literalmente la función `clean_json_output` de `main.py` y aplícala a cada salida textual.

**Etapa 1 — Domain:** user prompt = `identification_task`. Limpia la salida y guárdala en `domains/domain_clusters.json`. Parsea `business_domains`. Si viene vacía, detén la ejecución con error.

**Etapa 2 — Clustering:** arma `all_domains_summary` **exactamente** como `main.py`:
```
"Summary of all business domains:\n\n" + "{idx}. {domain_name}: {description}\n" por dominio
+ "\nYou are responsible for analyzing ONLY your assigned domain, but understanding the boundaries between domains is important for proper classification."
```
Para cada dominio con nombre y descripción, crea una **llamada independiente** (un agente nuevo por dominio). El user prompt es:
```
"You are analyzing the '{domain_name}' domain. The description of this domain is: {domain_description}\n\n{all_domains_summary}\n\n{clustering_task.description}"
```
y el `expected_output` es el bloque dinámico de `main.py` (el JSON plano `{"<domain_name>": [ ... ]}`, con su advertencia de no anidar por capas). Parsea `domain_data[domain_name]`. Si falla el parseo, deja una lista vacía (igual que el original) y regístralo. Guarda `domains/<Dominio>.json` (reemplazando `/` por `-` en el nombre) y `domains/all_domains.json`.

**Etapa 3 — Merging (condicional):** si `len(all_domain_results) == number`, **sáltala** y copia `all_domains.json` a `merged_domains.json`. Si no, el user prompt es:
```
"You need to merge the business domains into {number} clusters. You have been provided with the class structures for the following business domains: {domain_list_str}. The details of each domain data is as follows: {all_domain_results}. {merging_task.description}"
```
donde `domain_list_str` = `", ".join("'{name}' -- description: '{desc}'")`. Usa el repr de Python del dict para `{all_domain_results}`, igual que el original. Parsea la salida (si trae la clave `Domain_Cluster`, usa su contenido; si los valores son dicts por capas, aplánalos) y guarda `merged_domains.json` y los archivos por dominio. Si el parseo falla, vuelve a `all_domain_results`.

**Etapa 4 — Common Class:** `RESULT_FILE = output/<app>/<run_id>/common_result.json` (inicialízalo vacío). El user prompt es:
```
"You have been provided with the merged domain clusters: {domain_clusters}. This file contains the domains for classes after the merging phase. {common_class_task.description}\n\nIMPORTANT: To avoid output token limit issues, you MUST use the 'write_result_to_json' tool to save results. Call the tool ONCE for EACH domain ({k} domains total: {domain_names}). After calling the tool for all domains, simply confirm that all domains have been saved."
```
El `expected_output` se reemplaza, igual que en `main.py`, por: "Use the 'write_result_to_json' tool to save the class list for each of the {k} domains. After saving all domains, confirm completion with a brief summary of how many domains and classes were saved."
Si `common_result.json` queda vacío, intenta parsear la salida textual (respaldo del original).

**Etapa 5 — Review:** calcula `remaining_classes` = claves de `context/<app>/class_summaries.json` que no están en ningún dominio de `common_result`. `RESULT_FILE = output/<app>/<run_id>/result.json`. El user prompt es:
```
"You have been provided with the domain clusters with assigned common classes: {common_result_json}. This contains the domain assignments for classes after identifying common classes.\n\nAdditionally, there are {len(remaining)} classes that haven't been assigned to any domain yet: {remaining}.\n\n{review_task.description}\n\nIMPORTANT: To avoid output token limit issues, you MUST use the 'write_result_to_json' tool to save results. Call the tool ONCE for EACH domain ({k} domains total: {names}). After calling the tool for all domains, simply confirm that all domains have been saved."
```
con el `expected_output` análogo. Respaldo: si el archivo queda vacío, parsea la salida textual o guarda `result.txt`.

**No reproduzcas** el error del final de `main.py` (`final_result_raw` puede no estar definido). Imprime un resumen correcto.

**Prueba de humo:** antes de las corridas completas, ejecuta solo la Etapa 1 con JPetStore y revisa el log: herramientas llamadas, que no haya herramientas integradas y que el JSON sea válido.

---

## 8. Fase 5: línea base "LLM base" (zero-shot)

El paper la describe así (§4.1.2): se le da al modelo **el código original, los scripts de base de datos y el número objetivo de microservicios**, en *zero-shot*, para que genere la descomposición. **El artefacto no incluye su prompt**, así que hay que reconstruirlo (regístralo en `DECISIONES.md`):
- Una sola llamada `claude -p` **sin herramientas**, con el mismo `--model`.
- Contenido: el código de todas las clases del universo (las claves de `class_summaries.json`, con su ruta), el esquema de BD crudo (SQL de JPetStore; definición de datos de PartsUnlimitedMRP) y la instrucción de dividirlo en exactamente *n* microservicios, devolviendo **solo** JSON con el formato `{"<ServiceName>": ["<fully.qualified.ClassName>", ...]}`, en el que una clase puede aparecer en varios servicios si es compartida.
- Sin ejemplos (zero-shot) y en inglés, como el resto.
- Guárdala en `output/<app>/baseline-runK/result.json`.

---

## 9. Fase 6: evaluación (con los scripts originales)

### 9.1 Similitud (WS y c2c): `metrics/json_similarity.py`
- `reference` = `evaluation/references/<app>.json` (copia de `MicroAgent/decomposition/jpetstore.json` o `partsunlimited.json`); `target` = `output/<app>/<run_id>/result.json`.
- Llama a `evaluate_similarity(reference, target)` importando el módulo. No modifiques su lógica; su `__main__` tiene rutas fijas, así que usa tu propio `evaluate.py`.
- **Correspondencia con el paper:**
  - **WS** = `f1.metrics_m2.weighted_average` (método 2 = excluye las clases `uncounted`; media armónica de P→R y R→P).
  - **c2c@50 / @75 / @90** = `f1.metrics_m2.above_0.5 / above_0.75 / above_0.9`. Nota: el script usa `>` y el paper dice `≥`. Repórtalo tal como lo calcula el script y menciónalo.
- **Control de cordura:** evaluar la referencia contra sí misma debe dar 1,0 en todo.

### 9.2 Clases comunes (precisión, recall, F1): `metrics/common_metrics.py`
- Usa `calculate_metrics(common_dict, services)` importando el módulo; `services` = `result.json`.
- **JPetStore:** `common_dict` = `MicroAgent/metrics/test/common_dict.json` (los autores solo publicaron este).
- **PartsUnlimitedMRP:** no hay `common_dict` publicado. Constrúyelo con la misma regla del paper: las **clases comunes** son las que aparecen en más de una partición de la referencia (son 8: `RepositoryFactory`, `SimpleCORSFilter`, `TestPath`, `Utility`, `OrderingConfiguration`, `OrderingInitializer`, `BadRequestException`, `ConflictingRequestException`, todas en `smpl.ordering...`). Para cada una, la lista de valores son **las clases que dependen de ella** según `class_info_dependency.json` (clases con una relación directa hacia ella). Guárdalo en `evaluation/common_dicts/partsunlimited.json` y regístralo como **reconstruido**.
- El paper reporta F1 "a nivel de servicio". El script calcula micro y macro: **reporta ambos** y señala que el paper no aclara cuál usó.

### 9.3 Valores del paper con los que hay que comparar
Los valores por aplicación solo aparecen en la **Figura 3** del paper (WS por aplicación, con DeepSeek-V3.2). Leídos del gráfico, aproximadamente ±1 punto:

| Aplicación | MicroAgent (paper) | LLM base (paper) |
|---|---|---|
| JPetStore | ≈ 93 % | ≈ 81,5 % |
| PartsUnlimitedMRP | ≈ 100 % | ≈ 79,5 % |

Promedios del paper sobre 10 apps (solo como referencia, **no** son comparables directamente): WS 89,2 %; c2c@50/75/90 = 94,5 / 75,7 / 53,0 %; F1 de clases comunes 93,4 %. El paper no publica los c2c ni el F1 por aplicación.

### 9.4 Métricas arquitectónicas (opcional)
CMod, CiD y BCP se calculan con el repositorio de Wang et al. (ASE '24), según el README del artefacto. **Quedan fuera del alcance** salvo que sobre tiempo; si se intentan, BCP necesita casos de uso o trazas que probablemente no estén disponibles.

### 9.5 Tabla final `evaluation/results.csv`
Una fila por (app, configuración ∈ {microagent, baseline}, run_id) con: WS, c2c@50, c2c@75, c2c@90, P/R/F1 de clases comunes (micro y macro), nº de particiones, nº de clases asignadas, nº de clases sin asignar, turnos totales, duración y tokens/costo si `claude` los reporta. Al final, agrega filas con la media y la desviación estándar por (app, configuración).

---

## 10. Protocolo de corridas

1. Fija **un** modelo (`--model`) para todo, incluidos los resúmenes de PartsUnlimitedMRP, y registra el ID exacto que devuelve `claude` en el JSON de salida, junto con la versión de Claude Code (`claude --version`) y la fecha.
2. **3 corridas de MicroAgent** por app (`claude-run1..3`) y **3 corridas de la línea base** por app (`baseline-run1..3`). Total: 12 descomposiciones.
3. El contexto (grafo, resúmenes, BD) se genera **una sola vez** por app y se reutiliza en todas las corridas.
4. Si una corrida falla (JSON inválido, se alcanza el límite de turnos o se agota el cupo del plan), **no la descartes en silencio**: regístrala, reintenta con un `run_id` nuevo e informa ambas.
5. Vigila el cupo del plan Pro: corre una app completa antes de lanzar las demás.

---

## 11. `DECISIONES.md` (obligatorio)

Registra cada punto con fecha, qué decía el original, qué hiciste y por qué. Como mínimo:
- Modelo, versión de Claude Code y opciones de la CLI efectivamente usadas.
- Cómo se desactivaron las herramientas integradas y cómo se pasó el system prompt.
- Ausencia de la plantilla ReAct.
- Commit de JPetStore usado y conciliación de clases.
- Ruta Java de PartsUnlimitedMRP, conciliación de clases y origen del resumen de BD (SQL o MongoDB).
- Cambios del shim en `custom_tools.py`.
- Implementación de `write_result_to_json` con `RESULT_FILE`.
- Prompt reconstruido de la línea base.
- `common_dict` reconstruido de PartsUnlimitedMRP.
- `>` frente a `≥` en c2c; micro frente a macro en F1.
- Cualquier fallo de corrida.

---

## 12. Entregables

1. `replica-claude-code/` funcional, con un `README.md` que explique cómo correr cada fase.
2. `output/` con las 12 descomposiciones y sus logs.
3. `evaluation/results.csv`.
4. `REPORTE.md` (en español), con:
   - Configuración de la réplica y diferencias con el original (tabla de §1 actualizada).
   - Resultados por app: media ± desviación de MicroAgent y de la línea base.
   - Comparación con los valores del paper (§9.3) y si la mejora de MicroAgent sobre la línea base se mantiene.
   - Análisis de errores: qué clases quedaron mal asignadas frente a la referencia, por servicio.
   - Variabilidad entre corridas.
   - Amenazas a la validez de la réplica: otro modelo, sin temperatura 0, 2 apps, contexto de PartsUnlimitedMRP regenerado, `common_dict` reconstruido y posible contaminación de datos (las apps son públicas).

---

## 13. Lista de verificación final

- [ ] No se modificó nada dentro de `MicroAgent/`.
- [ ] Las herramientas devuelven lo mismo que el original (prueba de humo guardada).
- [ ] Ningún agente usó herramientas fuera de su lista ni herramientas integradas de Claude Code.
- [ ] Los prompts enviados coinciden carácter por carácter con YAML + `main.py` (salvo las sustituciones de §6).
- [ ] La etapa de Merging se saltó o ejecutó según la regla `len == number`.
- [ ] La referencia evaluada contra sí misma da 1,0.
- [ ] 12 descomposiciones evaluadas; `results.csv` y `REPORTE.md` completos.
- [ ] `DECISIONES.md` cubre todos los puntos de §11.
