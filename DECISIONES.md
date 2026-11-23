# DECISIONES.md — registro de desviaciones y decisiones de la réplica

Réplica de MicroAgent (ASE '26) con Claude Code. Cada entrada indica fecha, qué decía el original o la
especificación (`INSTRUCCIONES-REPLICA-MICROAGENT-CLAUDE-CODE.md`), qué se hizo y por qué.
Las evidencias citadas están en `logs/`.

Estado: **Fase 1 (preparación del contexto) completada y revisada el 2026-11-14** (D15). Ese mismo día Jorge
respondió a las decisiones abiertas (D16), el contexto de PartsUnlimitedMRP se regeneró con la configuración
definitiva, **Claude Sonnet 4.6 sin razonamiento extendido**, y la regeneración pasó una segunda revisión
(D17). **Fase 2 (servidor MCP de herramientas) completada y revisada el 2026-11-14** (D18 a D23). **Fase 3
(prompts literales) completada y revisada el 2026-11-16** (D24 a D30), con tres correcciones a §6 y §7
decididas por Jorge (D25 a D27). **Fase 4 (orquestador `run_pipeline.py`) programada, probada sin cupo y con
la prueba de humo de la Etapa 1 hecha el 2026-11-16** (D33 a D37), **y revisada ese mismo día por un agente
independiente, con sus hallazgos corregidos** (D38). Todavía **no se ha hecho ninguna corrida completa**. Las 6 corridas completas de MicroAgent se hicieron después (D43, D44). **Fase 5 (línea base zero-shot, `run_baseline.py`) programada, probada sin cupo y revisada el 2026-11-21** (D45 a D47); sus 6 corridas se hicieron el mismo día (D48). **Fase 6 (evaluación con los scripts originales) hecha y revisada el 2026-11-22** (D49 a D56); `REPORTE.md` y `README.md` quedan pendientes. Análisis de la variabilidad de la Etapa 4 en JPetStore y
de sus posibles remedios: D57. JPetStore ampliado a 10 corridas de MicroAgent: D58.

**Decidido por Jorge el 2026-11-16 (D39):** cuando un agente agota su límite de turnos se hace como el
original, que pide la respuesta final en una llamada más; ya está programado, probado y revisado.
**Pendiente de Jorge antes de las corridas completas:** si se mantiene `_sandbox/` dentro de la carpeta del
proyecto (D37, punto 2; si no dice otra cosa, se mantiene). Los tres
puntos que venían abiertos de fases anteriores (insumo del resumen de BD, D11; carpetas `target/`, D14; fuga
por rutas de archivo, D23) se cerraron el 2026-11-16 (D32).

**Decidido por Jorge para la Fase 4 (D31), ya aplicado (D33):** la respuesta final de un agente se toma como
en el original (lo que sigue al último `Final Answer:`), y el desajuste de dominios omitidos de `main.py` se
reproduce y se documenta.

**Cerrado en la Fase 4:** D22 (comprobación del `init`, auditoría de rutas, `--max-turns` corta), D23 (borrado
de `RESULT_FILE` antes de cada etapa; primero el archivo y después la respuesta), D29 (entrega sin
alteraciones, nombres de archivo), D31 (regla de `Final Answer:` y desajuste de dominios) y D32 (huella del
contexto).

---

## Fase 1 — Preparación del contexto

### D1. Entorno (2026-11-14)
- **Especificación (§4.1):** Python 3.10 a 3.13, Java 11+, Maven, Git, Claude Code con plan Pro.
- **Entorno real:** Python **3.14.0** (único intérprete instalado), OpenJDK Temurin 25.0.4.1, Maven 3.10.0,
  Git 2.51.2, Claude Code **2.1.325**, Windows 11.
- **Desviación:** Python 3.14 queda fuera del rango indicado. Los paquetes ya instalados funcionan en 3.14
  (`sentence-transformers` 5.6.0, `scikit-learn` 1.8.0, `numpy` 2.4.0, `PyYAML` 6.0.3). `pydantic` y `mcp`
  todavía no están instalados; se instalarán en la Fase 2. Si alguno fallara en 3.14, se creará un entorno
  virtual con Python 3.13 y se anotará aquí.
- Graphviz (`dot`) no está instalado. No hizo falta: el analizador generó `.dot` y `.jpg` con el motor V8
  embebido de `graphviz-java` (ver D8).

### D2. Opciones de la CLI de Claude Code (2026-11-14)
- **Especificación (§4.1):** confirmar con `claude --help` los nombres exactos de las opciones.
- **Resultado en la versión 2.1.325:** existen `-p/--print`, `--output-format json|stream-json`, `--model`,
  `--mcp-config`, `--strict-mcp-config`, `--allowedTools/--allowed-tools`,
  `--disallowedTools/--disallowed-tools`, `--tools` (con `""` desactiva todas las herramientas integradas),
  `--system-prompt` y `--append-system-prompt`.
- **`--max-turns` no aparece en `claude --help`**, pero la CLI lo acepta: las 54 llamadas de contexto se
  ejecutaron con `--max-turns 1` (campo `_cmd` de cada JSON en `logs/partsunlimited_context/`) y terminaron
  con código de salida 0. La llamada de prueba `logs/cli_checks/check1_sonnet45_stream.jsonl` también lo
  llevaba, pero ese archivo no registra la línea de comandos. Se usará tal como indica la especificación.
  Pendiente para la Fase 4: comprobar que realmente corta la ejecución al alcanzar el límite (la Fase 1 solo
  demuestra que se acepta).
- Otras opciones usadas que la especificación no menciona (para aislar el contexto, ver D5):
  `--disable-slash-commands` y `--setting-sources ""`.

### D3. Modelo único de la réplica: `claude-sonnet-4-6` (2026-11-14, decisión de Jorge)
- **Especificación (§1, §10):** un solo modelo Claude, fijado con `--model`, para todo (incluidos los
  resúmenes de PartsUnlimitedMRP). No indica cuál.
- **Decisión vigente:** `--model claude-sonnet-4-6`. Es el ID completo: Sonnet 4.6 no tiene variante con
  fecha. La API responde con `claude-sonnet-4-6` en las 54 llamadas de contexto
  (`python scripts/check_context_calls.py partsunlimited`).
- **Historia:** la primera versión de esta decisión, tomada por Claude Code, fue `claude-sonnet-4-5`
  (resuelto a `claude-sonnet-4-5-20250929`), por ser uno de los tres LLM del paper (DeepSeek-V3.2, GPT-5.2,
  Claude Sonnet 4.5). Jorge indicó que en su plan solo aparecen los modelos desde Sonnet 4.6 y decidió usar
  **Claude Sonnet 4.6** (D16).
- **Comprobación:** Sonnet 4.5 todavía respondía por ID el 2026-11-14, pero la página oficial de Anthropic
  (`https://platform.claude.com/docs/en/about-claude/model-deprecations`, consultada el 2026-11-14) lista
  `claude-sonnet-4-5-20250929` como *Deprecated* desde el 2026-09-30, con retiro el **2026-11-30**, y
  `claude-sonnet-4-6` como *Active*, con retiro "not sooner than February 17, 2027". Las corridas de las
  fases 4 y 5 se repartirán en varias ventanas de cupo, así que con Sonnet 4.5 había riesgo de quedarse sin
  modelo a mitad del experimento (§10.1 exige un solo modelo). Sonnet 4.6 no tiene ese riesgo.
- **Desviación respecto al paper:** Claude Sonnet 4.6 **no** es ninguno de los tres LLM que evaluó el paper.
  Es el modelo Claude disponible más cercano a Claude Sonnet 4.5. Se reportará como amenaza a la validez.
- **Límite de la comparación:** los valores por aplicación de la Figura 3 del paper son de DeepSeek-V3.2.
- El contexto generado con Sonnet 4.5 quedó descartado y archivado en `logs/_archivo_sonnet45_thinking/`
  (D16). No se usa en ninguna corrida.

### D4. Contexto residual y parámetros de muestreo que impone Claude Code (2026-11-14)
- **Original:** llamada directa a la API con temperatura 0; el prompt de preparación de contexto es un único
  mensaje de usuario, sin system prompt documentado.
- **Réplica:** con `--system-prompt ""`, Claude Code sigue enviando (transcripción de la llamada de prueba,
  sesión `abd67f67-9a82-4d41-8f19-50bbd37eabf0`):
  - un system prompt fijo: `You are a Claude agent, built on Anthropic's Claude Agent SDK.`;
  - bloques `<system-reminder>` antepuestos al mensaje de usuario: entorno (directorio de trabajo,
    plataforma, sistema operativo), identidad del modelo, tokens restantes, correo de la cuenta y fecha.
    Son unos 590 tokens de entrada.
  - **razonamiento extendido activado** por defecto (`thinking: enabled, budget_tokens: 31999` en la llamada
    de prueba con Sonnet 4.5), `max_tokens: 32000`, sin parámetro de temperatura.
- **Qué se hizo con el system prompt y los `<system-reminder>`:** no se pueden quitar desde la CLI, así que
  se aceptan como consecuencia del cambio aprobado "agentes con Claude Code" y se reportarán como amenaza a
  la validez.
- **Razonamiento extendido: desactivado (decisión de Jorge, D16).**
  - *Original:* `MicroAgent/microagent/src/microagent/crew.py`, líneas 12 a 20, crea el LLM con
    `LLM(model=..., api_key=..., base_url=..., temperature=0.0, stream=False, timeout=600, max_retries=5)`.
    No pasa `thinking`, `reasoning_effort` ni nada equivalente, y no hay otra configuración del LLM en
    `microagent/src`. El paper solo menciona la temperatura 0 (§4.1.3). Es decir, **el original no solicita
    razonamiento extendido**.
  - *Alcance de esa afirmación:* para Claude Sonnet 4.5, que es el modelo del paper comparable con la
    réplica, no pedirlo equivale a no usarlo, porque en la API de Anthropic el razonamiento extendido solo
    se activa si se pide (y no admite temperatura 0). Para DeepSeek-V3.2 y GPT-5.2 **no se puede saber**: el
    artefacto no publica el `.env` (`MODEL`, `OPENAPI_API_BASE`), y esos proveedores pueden razonar por
    defecto según el identificador del modelo. La certeza es "el original no lo configura", no "ningún
    modelo del original razonó".
  - *Réplica:* todas las llamadas `claude -p` llevan la variable de entorno **`MAX_THINKING_TOKENS=0`**
    (`EXTRA_ENV` en `scripts/claude_cli.py`; queda registrada en el campo `_env` de cada JSON de `logs/`).
  - *Comprobación:* mismo prompt (`smpl.ordering.Utility`) con Sonnet 4.6. Sin la variable:
    1 bloque `thinking` y 450 tokens de salida (`logs/cli_checks/check2_sonnet46_default_stream.jsonl`).
    Con la variable: 0 bloques `thinking` y 202 tokens de salida
    (`logs/cli_checks/check3_sonnet46_nothinking_stream.jsonl`). En las 54 llamadas de contexto vigentes hay
    0 bloques `thinking` en las transcripciones y `thinking_tokens: 0` en `usage`
    (`scripts/check_context_calls.py`).
- **Temperatura: sigue sin poder fijarse.** Claude Code no tiene opción para la temperatura, así que la
  réplica usa la que envíe por defecto y no la temperatura 0 del original. Se reportará como amenaza a la
  validez; las 3 corridas por configuración (§10) miden esa variabilidad.

### D5. Configuración de las llamadas `claude -p` de preparación de contexto (2026-11-14)
- **Especificación (§4.3.3):** `claude -p` sin herramientas y con el mismo `--model`.
- **Comando efectivo** (`scripts/claude_cli.py`):
  `claude -p --model claude-sonnet-4-6 --system-prompt "" --tools "" --strict-mcp-config
  --disable-slash-commands --setting-sources "" --max-turns 1 --output-format json`, con la variable de
  entorno `MAX_THINKING_TOKENS=0` (D4). La primera generación, ya descartada, usó `claude-sonnet-4-5` sin esa
  variable (D16).
- El prompt se pasa por **stdin**, no como argumento: evita el límite de longitud de la línea de comandos de
  Windows (unos 32 000 caracteres) y los problemas de comillas. El texto enviado es el mismo.
- Directorio de trabajo: `_sandbox/` vacío, sin `CLAUDE.md`.
- Comprobado en el mensaje `init` de la llamada de prueba: `tools: []`, `mcp_servers: []`,
  `slash_commands: []`, `skills: []`.
- Claude Code guarda la transcripción de cada llamada en
  `~/.claude/projects/C--Jorge-Quispe-Bendezu-ULima-Tesis-Replica-de-Paper-replica-claude-code--sandbox/`.
  No se desactivó (`--no-session-persistence`) porque sirve de evidencia.

### D6. JPetStore: commit usado y conciliación de clases (2026-11-14)
- **Especificación (§4.2):** clonar `mybatis/jpetstore-6`, reutilizar el contexto de los autores y verificar
  que el `file_path` de las 24 clases exista en el clon; si no, hacer checkout de un commit anterior.
- **Problema:** en el HEAD actual (`c3dbf6f`, 2026-11-07) **faltan 5 de las 24 clases**
  (`org.mybatis.jpetstore.web.actions.*ActionBean`). El commit `53e4499` (fecha de autor 2026-08-09,
  "Migrate stripes to spring webmvc") eliminó `web/actions/` y creó `web/controllers/`.
- **Decisión:** checkout de **`a37c02f8f004b4b83dc32c5330b2d0026c1c3e00`** (2025-06-16), que era el HEAD de
  `master` el 2025-06-20, fecha del archivo `decomposition/jpetstore.json` dentro del zip del artefacto.
- **Evidencia (control de §4.2 paso 4):** se regeneró el grafo con el analizador original en varios commits y
  se comparó con el `class_info_dependency.json` de los autores (`scripts/compare_graph.py`,
  `logs/jpetstore_control/`):

  | Commit | Fecha | Clases | Entradas idénticas a las de los autores |
  |---|---|---|---|
  | `a37c02f` (**elegido**) | 2025-06-16 | 24 | **24 / 24** |
  | `4ea1856` | 2026-01-24 | 24 | 24 / 24 |
  | `5a81f2f` | 2026-01-25 | 24 | 24 / 24 |
  | `3c44603` | 2026-07-08 | 24 | 24 / 24 |
  | `5bcf409` | 2026-07-24 | 24 | 23 / 24 (`Item` pierde el campo `productId`) |
  | `6b0ac6a` | 2026-08-09 | 24 | 23 / 24 (igual) |

- **Ambigüedad entre commits y cómo se resolvió:** entre `a37c02f` y `3c44603` solo cambia un archivo de
  `src/main/java`: `CartActionBean.java` (commit `5a81f2f`, 13 líneas añadidas y 2 eliminadas). El grafo no
  distingue esas versiones y el resumen de los autores tampoco, y los archivos del contexto dentro del zip
  tienen fecha 2026-03-27. Lo que sí distingue es el tamaño que reporta el paper: su tabla de aplicaciones da
  **1 409 líneas de código** para JPetStore. Contando las líneas de `src/main/java` sin comentarios ni líneas
  en blanco se obtienen 1 409 en `a37c02f`, 1 417 en `5a81f2f` y `3c44603`, y 1 415 en `5bcf409` (dato
  aportado por el revisor, D15, y recalculado para `a37c02f`). Esto respalda el commit elegido.
  `src/main/resources` (incluido el esquema SQL) es idéntico en todos esos commits.
- **Conciliación (`scripts/verify_context.py jpetstore-6`):** 24 clases en ambos JSON con las mismas claves;
  los 24 `file_path` existen en el clon; universo = las 24 clases de `decomposition/jpetstore.json`.
- Los tres archivos de contexto copiados son idénticos byte a byte a los de los autores (SHA-256).

### D7. Formato de salida del analizador: se usa el objeto `classes` (2026-11-14)
- **Original:** el README dice que el analizador produce `class_info_dependency.json` y que se coloca en
  `microagent/context`.
- **Problema:** el analizador publicado exporta `{"metadata": {...}, "classes": {...}}`, mientras que el
  `class_info_dependency.json` publicado para JPetStore es un objeto plano `{FQCN: {...}}`, y así lo leen
  las herramientas (`class_info[class_name]`).
- **Decisión:** el `class_info_dependency.json` de la réplica es el contenido de `classes`, sin `metadata`
  (`scripts/extract_classes.py`). La salida cruda se conserva en
  `logs/partsunlimited_context/analyzer_raw_output.json`.
- **Por qué es fiel:** con JPetStore, el objeto `classes` regenerado coincide 24/24 con el archivo de los
  autores (D6), lo que indica que ellos hicieron esa misma extracción. El archivo de los autores conserva
  además la sangría propia de un objeto anidado.
- Diferencia sin efecto: el archivo extraído se escribe con `json.dump` (separador `": "`), no con el formato
  de Jackson (`" : "`). Las herramientas lo cargan con `json.load`.

### D8. Analizador compilado desde una copia (2026-11-14)
- **Especificación (§4.3.2):** `cd MicroAgent/graph (o una copia en replica-claude-code/graph)`.
- **Decisión:** se copió `pom.xml` y `src/` a `replica-claude-code/graph/` y se compiló ahí con
  `mvn clean package`, porque compilar en `MicroAgent/graph` habría escrito dentro de `MicroAgent/`
  (regla de §2). No se cambió ninguna línea del analizador: `graph/pom.xml` y `graph/src/` son idénticos a
  los de `MicroAgent/graph/`. La carpeta `MicroAgent/graph/target/` que existe en disco no es del artefacto
  (ver D14).
- La compilación con JDK 25 (`source/target` 11) terminó sin errores.
- La generación de `.dot` y `.jpg` funcionó a la primera con `--json --dot --jpg`
  (`logs/partsunlimited_context/diagram.dot`, `diagram.jpg`).
- Detalle del analizador a tener en cuenta: excluye cualquier ruta que contenga la cadena `tmp`. Ninguna
  ruta de la réplica la contiene.

### D9. PartsUnlimitedMRP: ruta Java y conciliación de clases (2026-11-14)
- **Clon:** `microsoft/PartsUnlimitedMRP`, commit `026821869397703dbcb4858df76e73ddea948ec1` (2023-06-27,
  HEAD actual; el repositorio no cambia desde entonces).
- **Ruta analizada:** `resources/partsunlimited/src/Backend/OrderService/src/main/java` (contiene
  `smpl/ordering`). No se incluyeron `src/test/java` (24 archivos) ni `IntegrationService` (22 archivos,
  paquete `integration`), porque la referencia solo contiene clases `smpl.ordering...` de `main`.
- **Resultado:** 53 archivos `.java`, 53 clases de nivel superior, una por archivo. El paper reporta 53
  clases y **4 407 líneas de código**; el conteo de líneas sin comentarios ni blancos de esta ruta da
  exactamente 4 407 (con las pruebas daría 6 259 y con todo `Backend`, 7 073, según el revisor). Esto confirma
  de forma independiente la ruta y las exclusiones.
- **Conciliación con `MicroAgent/decomposition/partsunlimited.json`**
  (`scripts/reconcile_partsunlimited.py`):
  - 46 clases distintas en particiones + 7 distintas en `uncounted` (la lista trae 8 elementos porque
    `AppInsightsFilter` está repetida) = 53.
  - universo − referencia = ∅; referencia − universo = ∅.
  - 8 clases aparecen en más de una partición, y son las que lista §9.2: `RepositoryFactory`,
    `SimpleCORSFilter`, `TestPath`, `Utility`, `OrderingConfiguration`, `OrderingInitializer`,
    `BadRequestException`, `ConflictingRequestException`.
- Dos clases no tienen ninguna relación en el grafo: `smpl.ordering.PostgresqlProperties` y
  `smpl.ordering.SimpleCORSFilter`. Esta última es una de las clases comunes de la referencia; se tendrá en
  cuenta al reconstruir el `common_dict` (§9.2), porque su lista de dependientes saldrá vacía.
- `APP_CONFIG["java_paths"]` vale `["src/main/java"]` en el original, y en esta app el código está en
  `src/Backend/OrderService/src/main/java`. No afecta: en `custom_tools.py` ese campo solo lo lee
  `_get_class_source_code` (líneas 2185–2217), que pertenece a una herramienta que no está entre las 14 de
  §5.2. `get_class_relation_and_code` toma el `file_path` de `class_summaries.json` y lo resuelve desde
  `WORKING_DIR`; los 53 + 24 `file_path` existen relativos a `replica-claude-code/`.

### D10. Resúmenes de clase de PartsUnlimitedMRP (2026-11-14)
- **Especificación (§4.3.3):** "Class Summary Prompt" literal, un `.java` por llamada, `claude -p` sin
  herramientas, mismo modelo.
- **Qué se hizo** (`scripts/gen_class_summaries.py`):
  - El prompt se extrae del bloque de código de `MicroAgent/prompt/context_preparation_prompt.md` y se usa
    tal cual, incluida su sangría de cuatro espacios (`logs/partsunlimited_context/summaries/_prompt_template_literal.txt`).
  - Sustituciones: `{{`/`}}` → `{`/`}` en la plantilla **antes** de insertar el código (para no alterar las
    llaves del Java) y `{java_class_content}` → contenido del archivo.
  - 53 llamadas válidas, 1 turno cada una, con Sonnet 4.6 y sin razonamiento extendido (regeneración del
    2026-11-14, D16). Prompt y JSON completo de cada llamada en
    `logs/partsunlimited_context/summaries/<FQCN>.prompt.txt` y `<FQCN>.json`.
  - **Intentos fallidos:** la regeneración se cortó por el límite de 5 horas del plan Pro cuando llevaba 38
    resúmenes. Las 15 llamadas restantes devolvieron `is_error: true` con HTTP 429 ("You've hit your 5-hour
    limit"); quedaron registradas en `<FQCN>.json.failed` y no se usaron. Tras el reinicio del cupo se volvió
    a ejecutar el script, que reanuda: reutilizó los 38 válidos y completó los 15 pendientes sin fallos.
- **Conciliación de claves:** las 53 respuestas traen exactamente una clave, igual al FQCN del grafo. No hubo
  renombrados, entradas descartadas ni clases internas con entrada propia.
- **`file_path`:** el prompt solo recibe el código, así que el modelo no conoce la ruta y devuelve una
  relativa al paquete (p. ej. `smpl/ordering/BadRequestException.java`). El script la **reemplaza** por
  `resources/partsunlimited/src/Backend/OrderService/src/main/java/<paquete>/<Clase>.java`, que es el
  formato que piden las herramientas. Las 53 sustituciones están en
  `logs/partsunlimited_context/summaries/_conciliacion.txt`. El texto de `summary` no se toca.
- Las respuestas vienen envueltas en una cerca ` ```json `; se quita antes de parsear.
- Los resúmenes son más largos que los de los autores para JPetStore (1 413 frente a 695 caracteres de
  media; con Sonnet 4.5 eran 893) y 17 de los 53 usan Markdown (`**`). No se editaron.
- Los archivos fuente tienen finales de línea CRLF en el clon de Windows (`core.autocrlf=true`); se leen en
  modo texto, por lo que el prompt lleva LF.

### D11. Resumen de base de datos de PartsUnlimitedMRP: hay SQL (2026-11-14)
- **Especificación (§4.3.4):** buscar scripts `*.sql`, scripts de inicialización de MongoDB o, en su defecto,
  los modelos `mongodb.models`. "Si hay SQL, usa literalmente el Database Summary Prompt. Si solo hay MongoDB
  (lo esperable) [...] guárdalo como `mongodb-summary.json`".
- **Hallazgo:** no hay archivos `*.sql`, pero **sí hay un esquema SQL**:
  `src/Backend/OrderService/scripts/schema.psql` (DDL de PostgreSQL con 10 tablas del servicio de órdenes,
  presente desde el commit `0d6a9b1`, "initial repo commit", de 2015-05-01). También existe
  `deploy/MongoRecords.js` (con una copia idéntica en `deploy/docker/Database/drop/`), que solo inserta datos
  de ejemplo en las colecciones `catalog`, `dealers`, `quotes`, `orders` y `shipments`. No hay ningún otro
  DDL en el repositorio.
- **Decisión:** se aplicó la regla "si hay SQL": "Database Summary Prompt" **literal**, con `{sql_content}` →
  contenido de `schema.psql` (`scripts/gen_db_summary.py`). El resultado se guardó como
  **`database/partsunlimited/sql-summary.json`** (no `mongodb-summary.json`), el mismo nombre que usa
  JPetStore; termina en `-summary.json`, que es lo que busca `get_database_summary`.
- **Por qué:** es lo que manda la especificación cuando hay SQL, no exige modificar el prompt (que dice "SQL
  Schema to analyze") y es el único DDL del repositorio.
- **No se sabe qué insumo usaron los autores.** El paper (§3, "Database Summary") dice: "Database
  definitions in monolithic applications can vary from SQL schema to non-SQL document". PartsUnlimitedMRP es
  la candidata natural a "non-SQL document" entre sus 10 aplicaciones, así que es posible que resumieran los
  documentos de MongoDB y no `schema.psql`.
- **Advertencia:** en ejecución el servicio usa MongoDB (`ordering.storage: mongodb`) y no hay código JDBC;
  `schema.psql` es un esquema heredado que el código no usa. Difiere de los modelos de MongoDB en algunos
  puntos (p. ej. no tiene `inventory` ni `leadTime` en el catálogo). `MongoRecords.js` y los modelos
  `mongodb.models` no se usaron como insumo. Solo hay un archivo `*-summary.json` en la carpeta, porque la
  herramienta concatena todos los que encuentre.
- **Respuesta de Jorge (2026-11-14, D16):** "Si el paper no menciona ninguna SQL y en su carpeta [...] no ves
  ningún SQL, entonces sigue tal cual como lo hicieron los autores."
- **Lo que se comprobó para aplicarla:**
  - El paper sí menciona SQL: "Database definitions in monolithic applications can vary from SQL schema to
    non-SQL document" (§3.1.1). No dice qué archivo se usó en cada aplicación.
  - El artefacto sí trabaja con SQL: el prompt se llama "Database Summary Prompt", recibe `{sql_content}` y
    dice "SQL Schema to analyze"; el único resumen publicado es
    `MicroAgent/microagent/database/jpetstore-6/sql-summary.json`.
  - En el artefacto no hay ningún archivo de base de datos de PartsUnlimitedMRP (ni resumen, ni esquema, ni
    el código fuente de la aplicación), así que no se puede saber qué insumo usaron los autores para ella.
- **Decisión vigente (interpretación de Claude Code de la respuesta de Jorge):** seguir el procedimiento que
  los autores sí documentan, es decir, archivo de definición de la base de datos → "Database Summary Prompt"
  literal → `sql-summary.json`. Se mantiene `schema.psql` como insumo, por ser el único archivo de definición
  de base de datos del repositorio. La alternativa descartada (resumir `MongoRecords.js` o los modelos
  `mongodb.models` y guardarlo como `mongodb-summary.json`) obligaría a usar el prompt con un insumo que no
  es un esquema. Las 10 tablas y las 5 colecciones nombran las mismas cinco áreas (catálogo, distribuidores,
  cotizaciones, órdenes y envíos), por lo que se supone que el efecto de la diferencia es pequeño; **es una
  suposición, no se midió**. Se reportará como amenaza a la validez.
- **Estado: pendiente de confirmación explícita de Jorge.** Su respuesta era condicional y sus dos premisas
  no se cumplen del todo (el paper sí menciona SQL y sí existe un esquema SQL), así que lo anterior es una
  interpretación y no un mandato. Pregunta abierta: ¿se mantiene `schema.psql` (SQL heredado, no usado en
  ejecución) o se usa el insumo de MongoDB con `mongodb-summary.json`? Hay que cerrarla antes de la primera
  corrida de la Fase 4; cambiarla cuesta una llamada.
- **Regeneración:** el resumen se volvió a generar el 2026-11-14 con Sonnet 4.6 y sin razonamiento extendido
  (D16). El primer intento de esa regeneración falló por el límite de cupo (HTTP 429); su registro
  `db_summary.json` se sobrescribió con el de la llamada válida al reintentar.
- **Envoltura del archivo:** se imitó la del `sql-summary.json` de los autores:
  `{"schema": {"schema_summary": {...}, "file_path": "<ruta del SQL>"}}`. La respuesta del modelo aporta
  `schema_summary`; `file_path` lo añade el script con la ruta real del esquema.
- **Resultado:** 10 tablas y 10 relaciones, que coinciden con las 10 sentencias `CREATE TABLE` y las 10
  claves foráneas del esquema. Prompt y salida en `logs/partsunlimited_context/database/`.
- Nota para la Fase 5: el "esquema de BD crudo" de la línea base será este mismo `schema.psql`
  (PartsUnlimitedMRP) y `src/main/resources/database/jpetstore-hsqldb-schema.sql` (JPetStore).

### D12. Uso de cupo de la Fase 1 (2026-11-14)
- **Primera generación (Sonnet 4.5, descartada):** 54 llamadas de contexto (53 resúmenes + 1 resumen de BD)
  más 1 llamada de prueba de la CLI. Costo nominal que reporta `claude` (`total_cost_usd`, no es un cobro en
  el plan Pro): USD 1,13.
- **Generación vigente (Sonnet 4.6, sin razonamiento extendido):** 2 llamadas de prueba, 54 llamadas válidas
  (costo nominal USD 0,82) y 16 llamadas rechazadas por el límite de 5 horas, que no produjeron salida del
  modelo: 15 resúmenes (registrados en `*.json.failed`) y el resumen de BD. De esta última solo queda
  constancia en la salida de consola de la sesión, porque su registro se sobrescribió al reintentar (D11).
- El contexto vigente se reutilizará sin cambios en todas las corridas (§10.3).

### D13. Archivos añadidos que no figuran en la estructura de §3 (2026-11-14)
- `graph/` (copia del analizador, D8), `scripts/` (utilidades de la Fase 1), `logs/` en la raíz
  (evidencias) y `_sandbox/` (directorio de trabajo vacío para `claude -p`).
- `scripts/check_microagent_untouched.py` comprueba la regla de §2 comparando `MicroAgent/` con
  `MicroAgent.zip` (ver D14).

### D14. Incidente: carpetas `target/` dentro de `MicroAgent/` que no son del artefacto (2026-11-14)
- **Regla (§2):** no editar nada dentro de `MicroAgent/`.
- **Qué pasó:** `MicroAgent.zip` contiene 1128 archivos y la carpeta `MicroAgent/` tiene 2295. Los 1128 del
  artefacto están presentes e idénticos (SHA-256). Los 1167 adicionales están todos en seis carpetas
  `target/`: `graph/` (11), `monolith/goodsKill-monolith/` (154), `monolith/gulimall-monolith/` (398),
  `monolith/PassJava-Platform-monolith/passjava-monolith/` (83), `monolith/youlai-mall-mono/` (410) y
  `monolith/zlt-platform-monolith/` (111).
- **Causa:** no las creó la réplica. Según el revisor (D15), las generó a las 00:30 la compilación
  automática del servidor de lenguaje Java de VS Code (extensión `redhat.java`), que tenía abierta la carpeta
  `MicroAgent/`. Ninguna está en las rutas que usa la réplica.
- **Error propio corregido:** la primera versión de la comprobación usaba una línea base de hashes tomada a
  las 00:34, después de que aparecieran esas carpetas, así que las daba por parte del artefacto. Se reemplazó
  por la comparación directa con el zip y se eliminó `logs/microagent_sha256_baseline.txt`.
- **Estado al cierre de la Fase 1:** `python scripts/check_microagent_untouched.py` → 0 faltantes, 0
  modificados, 1167 adicionales solo en `target/` (resultado `AVISO`).
- **Pendiente de Jorge:** no se borró nada porque está dentro de `MicroAgent/`. Para dejar la carpeta igual
  al zip hay que cerrar VS Code sobre `MicroAgent/` (o desactivar `java.autobuild.enabled`) y borrar las seis
  carpetas `target/`. Mientras el servidor Java siga activo puede volver a generarlas.

### D15. Revisión independiente de la Fase 1 (2026-11-14)
- Un agente revisor de solo lectura auditó la fase (sin llamadas al LLM). Veredicto: **aprobado con
  observaciones**, sin hallazgos bloqueantes.
- Comprobó por su cuenta, entre otras cosas: los 53 prompts enviados son literales (plantilla más el `.java`
  correspondiente); los 53 `summary` son el texto que devolvió el modelo; las 54 llamadas usaron 1 turno, sin
  herramientas y el mismo modelo resuelto; el analizador vuelto a ejecutar reproduce byte a byte ambos
  grafos; el `sql-summary.json` coincide con el DDL.
- Observaciones atendidas: H1 (D14); H2 (D11, ahora marcada como pendiente de confirmación); M1 (D3); M2
  (D2); M3 (D6 y D9, líneas de código del paper); M4 (fechas en D6 y D11); M5 (D9, `java_paths`); M6 (lectura
  UTF-8 estricta y registro parcial con `--only` en los scripts).
- Observación abierta: H3, el razonamiento extendido (D4), que depende de Jorge.
- Observación de M6 que se dejó sin cambiar: el modo caché de `gen_class_summaries.py` no revalida que el
  `.prompt.txt` guardado corresponda al código actual. No afecta al resultado ya generado, que el revisor
  verificó archivo por archivo.
- Lo que el revisor no pudo verificar: que `MicroAgent.zip` sea idéntico al registro de Zenodo, y qué insumo
  de BD usaron los autores.
- **Alcance:** esta revisión auditó la primera generación del contexto (Sonnet 4.5). La regeneración con la
  configuración definitiva se describe en D16 y su revisión en D17.

### D16. Decisiones de Jorge sobre los puntos abiertos y regeneración del contexto (2026-11-14)
- **Respuestas de Jorge** a las decisiones que quedaron pendientes al cierre de la Fase 1:
  1. *Modelo:* "solo tengo desde el claude sonnet 4.6 para adelante, entonces solo nos quedaría utilizar
     claude sonnet 4.6" → **`claude-sonnet-4-6`** (D3).
  2. *Razonamiento extendido:* "si estás seguro que el original no usa razonamiento extendido entonces yo
     tampoco lo usaré" → comprobado en `crew.py` y **desactivado** con `MAX_THINKING_TOKENS=0` (D4).
  3. *Insumo del resumen de BD:* "sigue tal cual como lo hicieron los autores" → se mantiene `schema.psql`
     con el prompt literal. Es una interpretación de Claude Code de una respuesta condicional, **no una
     decisión cerrada**: queda pendiente de confirmación explícita (D11).
  4. *Carpetas `target/`:* sin respuesta; sigue pendiente (D14).
- **Consecuencia:** el contexto de PartsUnlimitedMRP generado con Sonnet 4.5 y razonamiento extendido dejó
  de ser válido (§10.1: un solo modelo y una sola configuración para todo). Se movió, sin borrar nada, a
  `logs/_archivo_sonnet45_thinking/` (`summaries/`, `database_logs/`, `context/class_summaries.json` y
  `database/sql-summary.json`) y **no se usa en ninguna corrida**.
- **Regeneración:** mismos scripts, mismos prompts literales y mismos archivos fuente; solo cambian el modelo
  y la variable `MAX_THINKING_TOKENS=0` (`scripts/claude_cli.py`). Resultado: 53 resúmenes de clase con las
  mismas 53 claves y en el mismo orden que antes, y `sql-summary.json` con 10 tablas y 10 relaciones.
- **Comprobaciones tras regenerar:**
  - `python scripts/check_context_calls.py partsunlimited` → 54 llamadas, 54 con transcripción, 0 bloques
    `thinking`, modelo `claude-sonnet-4-6` en las 54, 1 turno, sin errores: `RESULTADO: OK`.
  - `python scripts/verify_context.py partsunlimited --reference ../MicroAgent/decomposition/partsunlimited.json`
    → `RESULTADO: OK`.
  - `python scripts/verify_context.py jpetstore-6` → `RESULTADO: OK`.
- **JPetStore no cambia:** su contexto es el publicado por los autores (D6) y no se generó con ningún modelo
  de la réplica. El paper no indica con qué LLM lo generaron.
- Archivos nuevos: `scripts/check_context_calls.py` y `logs/_archivo_sonnet45_thinking/`.

### D17. Revisión independiente de la regeneración del contexto (2026-11-14)
- Un segundo agente revisor de solo lectura (sin llamadas al LLM) auditó la regeneración. Veredicto:
  **aprobado con observaciones**, sin hallazgos bloqueantes ni altos.
- Comprobó por su cuenta: los 53 prompts de clase y el de BD son literales e idénticos byte a byte a los de
  la primera generación; las 54 llamadas usaron `claude-sonnet-4-6`, 1 turno, sin herramientas, con
  `MAX_THINKING_TOKENS=0`, `thinking_tokens: 0` y 0 bloques `thinking` en las transcripciones; los 53
  `summary` son el texto que devolvió el modelo y ninguno coincide con la generación archivada; los 15
  registros `.failed` son HTTP 429 y ninguno entra en el contexto; `sql-summary.json` es fiel al DDL; el
  contexto de JPetStore sigue idéntico al de los autores; `MicroAgent/` intacto y `_sandbox/` vacío.
- Observaciones atendidas:
  - M1: D4 afirmaba más de lo que se puede probar. Se acotó: el original no solicita razonamiento
    extendido, pero no se sabe si DeepSeek-V3.2 o GPT-5.2 razonaban por defecto en su proveedor.
  - M2: esta entrada y la cabecera del documento.
  - D11: la respuesta de Jorge era condicional; se marcó como interpretación pendiente de confirmación y se
    rotuló como suposición que el efecto sea pequeño.
  - B1: `scripts/check_context_calls.py` ahora comprueba también `thinking_tokens == 0` y `--tools ""`.
  - B3: D12 aclara que la llamada de BD rechazada no dejó registro en disco.
  - B4: la fecha de retiro de Sonnet 4.5 se verificó en la página oficial de Anthropic (D3).
- Observación que se dejó sin cambiar (B2): el modo caché de `gen_class_summaries.py` no revalida que el
  `.prompt.txt` guardado corresponda al código actual. El revisor verificó que los 53 prompts son correctos.
- Lo que el revisor no pudo verificar: la configuración real de LLM de los autores, el registro de la
  llamada de BD rechazada y que `MicroAgent.zip` sea idéntico al registro de Zenodo.

---

## Fase 2 — Herramientas (servidor MCP)

### D18. Copia de `custom_tools.py` y shim (2026-11-14)
- **Especificación (§5.1):** copiar `custom_tools.py`, reemplazar solo las importaciones de CrewAI y de
  `config` por un shim mínimo, y no tocar ningún `_run`.
- **Qué se hizo:** `tools/custom_tools.py` es la copia del original con **exactamente dos líneas cambiadas**
  (`diff` contra `MicroAgent/microagent/src/microagent/tools/custom_tools.py`):
  - línea 8: `from crewai.tools import BaseTool` → `from microagent_shim import BaseTool`
  - línea 17: `from ..config.config import APP_CONFIG, WORKING_DIR` → `from microagent_shim import APP_CONFIG, WORKING_DIR`
- **Desviación de forma:** el shim está en un archivo aparte, `tools/microagent_shim.py`, y no dentro de
  `custom_tools.py`. Así la copia conserva la numeración de líneas del original y la diferencia se comprueba
  con un `diff` de dos líneas. La estructura de §3 no lista ese archivo.
- **Contenido del shim:**
  - `BaseTool(pydantic.BaseModel)` con los campos `name`, `description` y `args_schema`. Los atributos con
    guion bajo (`_model`, `_class_info`, `_inverted_deps`, etc.) son atributos privados de pydantic, como en
    la clase de CrewAI.
  - `APP_CONFIG = {"app_name": os.environ["APP_NAME"], "model_name": os.environ["RUN_ID"], "java_paths": ["src/main/java"]}`.
  - `WORKING_DIR` = ruta absoluta de `replica-claude-code/`, calculada desde la ubicación del archivo. El
    original usa `os.getcwd()`; aquí no sirve porque `claude -p` lanza el servidor desde `_sandbox/`.
- Ningún método `_run` se modificó y todo compila sin más cambios.
- Python crea `tools/__pycache__/` al importar estos módulos; tampoco figura en §3 y no es parte de la réplica.

### D19. Versión del SDK de MCP (2026-11-14)
- **Especificación (§4.1, §5.2):** SDK `mcp`, "que incluye FastMCP".
- **Problema:** `pip install mcp` instaló `mcp` 2.3.0, donde `FastMCP` ya no existe (se renombró a
  `MCPServer` y cambió la API).
- **Decisión:** fijar `mcp>=1.30,<2` en `requirements.txt` (instalado: 1.30.0), que es la línea que tiene
  FastMCP. Funciona en Python 3.14 junto con `pydantic` 2.14.3, así que no hizo falta el entorno con Python
  3.13 previsto en D1.

### D20. Diseño del servidor `tools/mcp_server.py` (2026-11-14)
- **Especificación (§5.2):** servidor FastMCP por stdio llamado `microagent`, con el mismo `name`, la misma
  `description` y los mismos argumentos que cada clase, que devuelva la cadena de `_run`.
- **Registro de herramientas:** no se reescribieron a mano. El servidor instancia las 14 clases y publica
  cada una con `name=tool.name`, `description=tool.description` y una firma generada a partir de
  `tool.args_schema` (nombre, tipo, descripción y obligatoriedad de cada argumento). La función registrada
  solo llama a `tool._run(**argumentos)` y devuelve su cadena. Se usa `structured_output=False` para que el
  resultado sea solo el texto, sin una copia estructurada.
- **Diferencias inevitables frente a CrewAI** (consecuencia del cambio aprobado, §1):
  - El modelo ve cada herramienta como `mcp__microagent__<nombre>` (prefijo que añade Claude Code), y los
    prompts la nombran sin prefijo.
  - Los argumentos llegan al modelo como esquema JSON de MCP y no en el formato de texto de CrewAI.
- **`print` de las herramientas:** varios `_run` escriben por la salida estándar, que en stdio es el canal
  del protocolo. El servidor desvía esa salida a stderr mientras se ejecuta `_run` y durante la importación.
  No cambia lo que devuelve la herramienta.
- **Modo UTF-8 obligatorio (`python -X utf8`):** algunos `_run` abren archivos sin indicar codificación
  (líneas 573, 623 y 846 de `custom_tools.py`, entre ellas la lectura de `class_summaries.json` para la
  búsqueda semántica). En Linux o macOS eso es UTF-8; en Windows no. El servidor se niega a arrancar si no
  está en modo UTF-8, para reproducir el comportamiento del original sin tocar el código. Hay otros `open`
  sin codificación (líneas 1192, 1626 y 1658), pero están en herramientas que no son de las 14.
- **`write_result_to_json`** (§5.2):
  - Al arrancar, el servidor llama a `WriteResultToJson.reset()` y, si existe la variable `RESULT_FILE`, a
    `WriteResultToJson.set_output_file(RESULT_FILE)`. Es lo mismo que hace `main.py` (líneas 346-347 y
    436-437) antes de las tareas de clases comunes y de revisión. Sin `reset()` el `_run` original falla
    (`'ModelPrivateAttr' object does not support item assignment`), comprobado.
  - Antes de cada llamada, el servidor lee `RESULT_FILE` si existe y lo fusiona, dominio por dominio, con lo
    acumulado en memoria (lo de memoria tiene prioridad). Después `_run` escribe el archivo completo. Probado
    con un archivo previo y con dos procesos del servidor: el resultado conserva los dominios anteriores y
    permite sobrescribir uno.
  - Añadido tras la revisión (D23): `RESULT_FILE` es obligatoria y absoluta si el proceso publica la
    herramienta, y un `RESULT_FILE` inutilizable se copia a `<archivo>.descartado-<fecha>` antes de que `_run`
    lo sobrescriba.
- **Registro del servidor (`MICROAGENT_LOG`, añadido tras la revisión):** archivo JSONL opcional donde el
  servidor anota cada llamada que recibe (herramienta, argumentos, longitud de la respuesta, segundos) y sus
  avisos. Claude Code no guarda el stderr del servidor. No cambia nada de lo que ve el modelo.
- **Filtro `MICROAGENT_TOOLS` (añadido, no está en la especificación):** variable de entorno con los nombres
  de las herramientas que publica el proceso. Motivo: con las 14 publicadas y `--allowedTools` limitado a
  una, el modelo **ve las 14** en su contexto y solo se le deniega la llamada
  (`logs/cli_checks/check4_mcp_all_stream.jsonl`: 14 herramientas visibles, `permission_denials` para
  `get_database_summary`). Con el filtro ve solo las suyas (`check5_mcp_filtered_stream.jsonl`: 1 visible).
  Eso es lo que hace `crew.py`, donde cada agente recibe solo su lista, y lo que exige §5.3 ("cada agente
  debe tener solo sus herramientas MCP"). El orquestador pasará esta variable además de `--allowedTools`.
- **Tiempos de espera de Claude Code:** `custom_tools.py` importa `sentence_transformers` al cargarse, y el
  servidor tarda hasta unos 60 s en arrancar en frío. Con el valor por defecto, Claude Code marcó el servidor
  como `failed` (primer intento de `check4`, sobrescrito por el segundo; ver D22). Las llamadas con MCP
  llevan `MCP_TIMEOUT=300000` y `MCP_TOOL_TIMEOUT=600000` (`MCP_ENV` en `scripts/claude_cli.py`).

### D21. Prueba de humo de las herramientas (2026-11-14)
- **Especificación (§5.2):** probar cada herramienta con JPetStore y guardar las salidas en
  `logs/tool_smoke_test.txt`.
- **Qué se hizo** (`python -X utf8 scripts/smoke_test_tools.py`): se lanza el servidor por stdio con un
  cliente MCP, igual que lo hará `claude -p`, y para cada una de las 14 herramientas se compara lo publicado
  (nombre, descripción, argumentos) con la clase original y la salida por MCP con la de llamar a `_run`
  directamente. Resultado de la primera versión: 17 llamadas, 0 problemas. Tras la revisión (D23) la prueba
  cubre además el `RESULT_FILE` inutilizable, tres arranques que deben abortar y el registro del servidor:
  **18 llamadas, 0 problemas** (`logs/tool_smoke_test.txt`; lo que las herramientas imprimen está en
  `logs/tool_smoke_test_stderr.txt` y el registro del servidor en `logs/tool_smoke_test_server.jsonl`).
- **Orden no determinista heredado del original:** `get_more_potential_common_classes` y
  `assign_common_class_list` construyen listas a partir de conjuntos (`set`) de Python, cuyo orden cambia de
  un proceso a otro. El contenido es el mismo; solo cambia el orden. No se corrigió, porque está en `_run`.
- **Datos de la prueba:** `rank_dependency_entropy` y `codebase_semantic_search` leen
  `output/<app>/<run_id>/domains/`. Para la prueba se creó `output/jpetstore-6/smoke-test/` con una partición
  **artificial** (un dominio por paquete Java). No es la referencia ni el resultado de ningún agente, y
  ninguna corrida usará el identificador `smoke-test`.
- `codebase_semantic_search` descarga el modelo `all-MiniLM-L6-v2` de Hugging Face la primera vez; después
  usa la copia local.

### D22. Comprobación con `claude -p` y puntos que quedan para la Fase 4 (2026-11-14)
- Tres llamadas reales (`scripts/check_mcp_with_claude.py`, Sonnet 4.6, sin razonamiento extendido,
  `--tools ""`, `--strict-mcp-config`, desde `_sandbox/`):
  1. Servidor con arranque lento → `mcp_servers: failed`, ninguna herramienta visible. **El modelo no falló:
     escribió llamadas a herramientas inventadas dentro del texto y `claude` devolvió `success`.** Su registro
     se sobrescribió al repetir la prueba; queda la descripción aquí.
  2. Con `MCP_TIMEOUT` y las 14 publicadas → servidor `connected`, llamada permitida correcta, llamada no
     permitida denegada (`check4_mcp_all_*`).
  3. Con `MICROAGENT_TOOLS` → el modelo ve solo su herramienta (`check5_mcp_filtered_*`).
  En las tres: 0 herramientas integradas, 0 bloques `thinking`, `_sandbox/` vacío al terminar.
- **Pendiente para el orquestador (Fase 4):**
  - Comprobar en el mensaje `init` de cada etapa que `mcp_servers` está `connected` y que la lista de
    herramientas es exactamente la del agente; si no, la etapa es fallida aunque `claude` diga `success`.
    El mismo síntoma aparece si el servidor aborta al arrancar (un nombre mal escrito en `MICROAGENT_TOOLS`,
    falta de `RESULT_FILE`, falta del modo UTF-8).
  - Auditar las rutas que piden `search_file` y `get_class_relation_and_code`. Resuelven rutas relativas a
    `WORKING_DIR`, y en la réplica `evaluation/references/` (descomposiciones de referencia) y las salidas de
    otras corridas están dentro de esa carpeta. En el original, `decomposition/` queda fuera de la carpeta de
    trabajo (`microagent/`). No se puede impedir sin tocar `_run`, así que se verificará en los logs que
    ningún agente lee fuera de `resources/<app>/`.
  - Comprobar que `--max-turns` corta la ejecución (pendiente desde D2).
- Archivos nuevos de la fase: `tools/custom_tools.py`, `tools/microagent_shim.py`, `tools/mcp_server.py`,
  `scripts/smoke_test_tools.py`, `scripts/check_mcp_with_claude.py`, `logs/tool_smoke_test.txt`,
  `logs/tool_smoke_test_stderr.txt`, `logs/cli_checks/check4_*` y `check5_*`,
  `output/jpetstore-6/smoke-test/`.

### D23. Revisión independiente de la Fase 2 (2026-11-14)
- **Quién y cómo:** agente revisor (Claude Sonnet, solo lectura sobre la réplica, sin llamadas a `claude -p`),
  con su propio cliente MCP y sus propios scripts. **Veredicto: aprobado con observaciones, sin bloqueantes.**
- **Lo que confirmó:** el `diff` de dos líneas de `custom_tools.py`; 14 herramientas con nombre, descripción
  y argumentos idénticos a las clases originales; salida por MCP igual a `_run` en 13 de 13 llamadas (salvo el
  orden de una lista construida con `set`); recalculó por su cuenta la entropía de `rank_dependency_entropy`
  y obtuvo los mismos valores; las cinco listas de herramientas y los `max_iter` de §5.3 coinciden con
  `crew.py`; `requirements.txt` coherente con lo instalado.
- **Incidente del revisor dentro de `MicroAgent/`:** para comparar con el original lo importó desde un script
  suyo, y Python creó `MicroAgent/microagent/src/microagent/tools/__pycache__/`. El revisor lo borró. Después
  se volvió a ejecutar `scripts/check_microagent_untouched.py`: 0 faltantes, 0 modificados, 1167 adicionales,
  todos en `target/` (igual que en D14). El artefacto está intacto.
- **Observaciones y qué se hizo:**
  - **H1 (medio), fuga por rutas de archivo.** `search_file` y `get_class_relation_and_code` resuelven rutas
    relativas a `WORKING_DIR` y aceptan rutas absolutas sin restricción (también en el original). En la
    réplica, `WORKING_DIR` contiene `logs/`, `DECISIONES.md`, `prompts/`, `evaluation/` y las salidas de todas
    las corridas; en el original contiene `context/`, `database/`, `output/` (de todos los modelos),
    `resources/` y `src/`. **Decisión: no se añade ninguna restricción de rutas al servidor**, porque cambiaría
    la lógica de las herramientas (§1: "misma lógica de herramientas"). Medidas que no tocan las herramientas:
    1. `evaluation/references/` se llena solo después de terminar las 12 corridas (hoy está vacía).
    2. El orquestador audita cada corrida con `MICROAGENT_LOG` y con el flujo de `claude`: toda ruta pedida
       fuera de `resources/<app>/` queda en el log de la corrida y se informa en `REPORTE.md`. Una corrida que
       haya leído la salida de otra corrida, `logs/` o `evaluation/` se marca como contaminada; no se descarta
       en silencio (§10).
    Esto detecta la fuga, no la impide. La alternativa (que el servidor rechace rutas fuera de
    `resources/<app>/` y `output/<app>/<run_id>/`) es una desviación del original y queda **a decisión de
    Jorge**.
  - **H2 (medio), `RESULT_FILE` ausente daba éxito sin guardar.** Corregido en `mcp_server.py`: el servidor
    aborta al arrancar si publica `write_result_to_json` sin `RESULT_FILE` o con una ruta relativa.
  - **H3 (medio), archivo de resultados inutilizable.** Antes se ignoraba y `_run` lo sobrescribía, con aviso
    solo por stderr. Ahora el servidor guarda una copia `<archivo>.descartado-<fecha>` y anota el aviso en
    `MICROAGENT_LOG`. La escritura de `_run` sigue sin ser atómica (es del original).
  - **H4 (bajo):** añadido a D22 que un servidor que aborta al arrancar da el mismo síntoma que uno que no
    conecta. El registro del primer intento de `check4` (el modelo inventando llamadas) se sobrescribió, así
    que esa observación de D22 **no es verificable con los logs**; el orquestador la tratará igualmente.
  - **H5 (bajo):** nota de D20 sobre los `open` sin codificación, completada.
  - **H8 (bajo):** desinstalado `mcp-types 2.3.0`, resto de la instalación de `mcp` 2.x (D19). `pip check` sin
    problemas.
  - **H9, H10 (bajo):** `tools/__pycache__/` anotado en D18. `check_mcp_with_claude.py` guarda ahora su
    configuración MCP en `logs/cli_checks/`, porque la prueba de humo borra `output/jpetstore-6/smoke-test/`
    (los `*_mcp_config.json` de `check4` y `check5` se perdieron; quedan sus `.jsonl`).
  - **H6, H7 (bajo), sin cambios:** el orden variable de dos listas y el valor `Infinity` que puede emitir
    `rank_dependency_entropy` son del original.
- **Pendiente para el orquestador (Fase 4), además de lo de D22:**
  - `main.py` hace `reset()` antes de la tarea de clases comunes (archivo `common_result.json`, líneas
    345-347) y antes de la de revisión (`result.json`, líneas 435-437). En la réplica el servidor fusiona con
    lo que haya en `RESULT_FILE`, así que el orquestador debe **borrar o apartar ese archivo antes de cada
    etapa y de cada reintento**; si no, dominios de un intento anterior quedarían en el resultado.
  - `main.py` vuelca al final lo acumulado y, si está vacío, intenta leer el JSON de la respuesta del agente
    (líneas 377-391 y 466-488). El orquestador debe reproducir ese orden: primero el archivo, después la
    respuesta.
- **Lo que el revisor no pudo verificar:** la equivalencia exacta con `crewai.tools.BaseTool` (CrewAI no está
  instalado; comparó contra un sustituto suyo) y el comportamiento real de `--tools ""`, `--allowedTools` y
  `--max-turns` (no ejecutó `claude`; se basó en `check4` y `check5`).
- **Comprobación tras los cambios:** `python -X utf8 scripts/smoke_test_tools.py` → 18 llamadas, 0 problemas;
  `_sandbox/` vacío.

---

## Fase 3 — Prompts literales

### D24. Cómo se comprobó qué enviaba el original: captura con CrewAI 1.8.1 real (2026-11-16)
- **Especificación (§6):** armar los prompts desde `agents.yaml`, `tasks.yaml` y el texto dinámico de `main.py`,
  con la plantilla de CrewAI. "Si en la versión 1.8.1 de CrewAI [...] el texto difiere, usa el de esa versión y
  anótalo." La lista de §13 exige que los prompts coincidan carácter por carácter.
- **Problema:** §6 describe la plantilla de CrewAI de forma aproximada. El artefacto fija `crewai[tools]==1.8.1`
  (`MicroAgent/microagent/pyproject.toml` y `uv.lock`) y esa versión arma los mensajes de otra forma en tres
  puntos (D25, D26 y D27).
- **Qué se hizo:** en lugar de fiarse de la lectura del código, se ejecutó el original.
  `scripts/capture_crewai_prompts.py` copia `MicroAgent/microagent/src/microagent` (`main.py`, `crew.py`, los
  YAML y `custom_tools.py`) a una carpeta temporal y lo ejecuta con **CrewAI 1.8.1 real** y un **LLM simulado**
  que solo registra los mensajes que recibe y devuelve respuestas guionizadas. No llama a ningún servicio y no
  gasta cupo.
- **Entorno de la captura (no es el de la réplica):** CrewAI 1.8.1 exige Python < 3.14 y la réplica usa 3.14
  (D1). Se creó un entorno temporal con `uv venv --python 3.12` y `uv pip install crewai==1.8.1 pyyaml`, fuera
  del proyecto. `requirements.txt` no cambia: la réplica sigue sin instalar CrewAI.
- **Lo único que se cambia en la copia** (nunca en `MicroAgent/`): los tres valores que el original manda
  editar a mano para cambiar de aplicación (`'number'` y `'num'` en `main.py`, `"app_name"` en `config.py`) y
  el LLM (`crewai.LLM` devuelve el simulado). `sentence_transformers` y `sklearn` se sustituyen por módulos
  vacíos, porque el LLM simulado solo llama a `write_result_to_json`. Cada sustitución queda en el JSON.
- **Escenarios** (textos artificiales, con apóstrofos, comillas, saltos de línea y llaves):

  | Captura (`logs/prompts_golden/`) | App, n | Dominios | Ejecuciones de agente |
  |---|---|---|---|
  | `jpetstore_sin_fusion.json` | jpetstore-6, 3 | 3 | 6 (sin Merging) |
  | `jpetstore_con_fusion.json` | jpetstore-6, 3 | 4 | 8 |
  | `partsunlimited_sin_fusion.json` | partsunlimited, 5 | 5 | 8 (sin Merging) |
  | `partsunlimited_con_fusion.json` | partsunlimited, 5 | 6 | 10 |
  | `jpetstore_variable_en_descripcion.json` | jpetstore-6, 3 | 3 | 1 (el original aborta, D29) |
  | `jpetstore_num_en_nombre.json` | jpetstore-6, 3 | 3, un nombre con `{num}` | 6 (sin Merging) |
  | `jpetstore_fusion_domain_cluster.json` | jpetstore-6, 3 | 4, fusión envuelta en `Domain_Cluster` y con un dominio por capas | 8 |

  Los dos últimos se añadieron tras la revisión (D30). Tras la revisión de la Fase 4 se añadieron dos más,
  `jpetstore_dominios_omitidos.json` (6 ejecuciones) y `jpetstore_fusion_json_invalido.json` (8), descritas en
  D38; con ellas `check_prompts.py` hace 355 comprobaciones.
- **Resultado** (`python -X utf8 scripts/check_prompts.py`, salida en `logs/prompts_check.txt`): 279
  comprobaciones, 0 problemas. En las 47 ejecuciones de agente capturadas, el mensaje de usuario que arma
  `prompts/build_prompts.py` es **idéntico** al del original, y el system prompt del original es el de la
  réplica más el bloque de herramientas y ReAct (D28) y nada más. Pruebas de control: quitando `Thought:` de la
  plantilla, la comprobación falla en todos los mensajes de usuario; dejando sin interpolar el
  `expected_output`, falla en `jpetstore_num_en_nombre`.
- **Alcance de "idéntico":** se refiere al texto que la réplica entrega a la CLI de Claude Code. Lo que recibe
  el modelo lleva además lo que Claude Code añade por su cuenta (su system prompt fijo y los bloques
  `<system-reminder>` antepuestos al mensaje de usuario, D4). La Fase 4 debe registrarlo con la transcripción
  de cada llamada (D29).
- **Límite de la captura:** registra los mensajes que CrewAI entrega a la clase LLM. El revisor (D30) repitió
  la prueba con la clase `LLM` real de CrewAI y el proveedor nativo de OpenAI contra un servidor local: el
  cuerpo HTTP lleva los mismos `[system, user]`, sin cambios. Las rutas por `litellm` y por el proveedor nativo
  de Anthropic no se ejecutaron (solo se leyó su código: Anthropic pasa el system como parámetro aparte), y el
  artefacto no publica su `.env`, así que no se sabe qué ruta usó cada modelo del paper.
- **Residuos fuera del proyecto:** al importarse, CrewAI creó la carpeta `CrewAI` dentro de `AppData/Local`
  del usuario (una clave local y una base SQLite de la captura). No contenía nada de la réplica. Jorge pidió
  borrarla y se borró el 2026-11-16. La réplica no importa CrewAI, así que sus corridas no la vuelven a crear;
  solo reaparecería si se ejecuta de nuevo `scripts/capture_crewai_prompts.py`.

### D25. Las llaves dobles `{{` y `}}` de los YAML no se convierten (2026-11-16, decisión de Jorge)
- **Especificación (§6):** "`{{` → `{` y `}}` → `}` (escapes de CrewAI)".
- **Original:** CrewAI 1.8.1 no hace esa conversión. Su función `interpolate_only`
  (`crewai/utilities/string_utils.py`) solo sustituye `{nombre}` cuando `nombre` es una variable válida, y no
  toca `{{` ni `}}`. El LLM original recibía el ejemplo JSON con llaves dobles (visible en las capturas, etapas
  `domain` y `merging`).
- **Alcance real:** solo afecta a `identification_task.expected_output` (Domain) y a
  `merging_task.expected_output` (Merging). Los `expected_output` de las otras tres tareas no llegan al LLM:
  `main.py` los reemplaza (clustering, líneas 156-172, con un f-string de Python que sí produce llaves simples;
  clases comunes, 364-367; revisión, 453-456).
- **Decisión de Jorge:** enviar las **llaves dobles**, igual que el original. Riesgo aceptado: si el modelo
  copiara `{{` en su salida, el JSON sería inválido y la etapa fallaría; se registraría como corrida fallida
  (§10.4), no se corregiría.

### D26. Envoltura completa del mensaje de usuario, incluido `Thought:` (2026-11-16, decisión de Jorge)
- **Especificación (§6):** user prompt = texto dinámico + `description` + criterio esperado. No menciona
  ninguna envoltura.
- **Original:** el mensaje de usuario es el *slice* `task` de CrewAI con el prompt de la tarea dentro:
  `"\nCurrent Task: {input}\n\nBegin! This is VERY important to you, use the tools available and give your best
  Final Answer, your job depends on it!\n\nThought:"`.
- **Opciones planteadas:** incluirla sin el `Thought:` final (recomendación de Claude Code, por ser la señal de
  inicio del formato ReAct), omitirla (literal §6) o incluirla completa.
- **Decisión de Jorge: incluirla completa.** El mensaje de usuario de la réplica es idéntico, carácter por
  carácter, al del original.
- **Consecuencia a vigilar en la Fase 4:** el mensaje termina en `Thought:` y menciona `Final Answer`, pero el
  system prompt de la réplica no explica el formato ReAct (D28). El modelo puede responder con texto del tipo
  `Thought: ... Final Answer: ...`. Ver D29.

### D27. Contexto de la tarea anterior en Common Class y Review (2026-11-16, decisión de Jorge)
- **Especificación (§7):** los prompts de las etapas 4 y 5 no llevan ningún bloque de contexto.
- **Original:** `crew.py` declara `context=[self.merging_task()]` en la tarea de clases comunes y
  `context=[self.common_class_task()]` en la de revisión. Los métodos `@task` están memoizados, así que esas
  tareas son los mismos objetos que `main.py` ejecuta. CrewAI añade al final del prompt
  `"\n\nThis is the context you're working with:\n" + <respuesta final de la tarea anterior>`:
  - **Review:** siempre recibe la respuesta final del Common Class Agent (su confirmación).
  - **Common Class:** recibe la respuesta final del Merging Agent **solo si la etapa de fusión se ejecutó**. Si
    se saltó, no hay contexto.
  - Domain, Clustering y Merging no reciben contexto (la tarea `clustering_task` del YAML nunca se ejecuta).
- **Decisión de Jorge: reproducirlo.** `common_class_prompts(...)` y `review_prompts(...)` aceptan el parámetro
  `context`; el orquestador se lo pasa (D29).

### D28. System prompt: solo `role_playing`; se excluye el bloque de herramientas y ReAct (2026-11-16)
- **Especificación (§6):** `You are {role}. {backstory}\nYour personal goal is: {goal}`, sin la plantilla ReAct.
- **Qué se hizo:** exactamente eso (*slice* `role_playing` de CrewAI 1.8.1). `role`, `goal` y `backstory` se
  leen de `agents.yaml` con `yaml.safe_load`, igual que CrewAI, y no se recortan: `backstory` y `goal` terminan
  en salto de línea (escalares plegados `>` del YAML), así que el system prompt termina en `\n`.
- **Qué se excluye** (diferencia esperada, §1 y §6): el *slice* `tools`, que en el original va a continuación:
  `"\nYou ONLY have access to the following tools, and should NEVER make up tools that are not listed
  here:\n\n"` + la lista `Tool Name / Tool Arguments / Tool Description` de cada herramienta +
  `"IMPORTANT: Use the following format in your response:"` + el bloque `Thought / Action / Action Input /
  Observation` + el bloque `Final Answer`. Para el Domain Agent son 3 076 de los 5 728 caracteres del system
  prompt original. En la réplica, Claude Code entrega los nombres, descripciones y argumentos de las
  herramientas por la vía nativa (MCP, D20).
- **Control cruzado:** los nombres que CrewAI anunciaba a cada agente coinciden con la tabla de §5.3 en las 47
  ejecuciones.
- **Sustituciones:** `{number}` solo aparece en el `backstory` del Merging Agent ("form EXACTLY 3 clusters").
- Los YAML se leen directamente de `MicroAgent/` (solo lectura); no se copian a la réplica.

### D29. `prompts/build_prompts.py`: diseño y puntos que quedan para la Fase 4 (2026-11-16)
- **Interfaz:** `domain_prompts`, `clustering_prompts`, `merging_prompts`, `common_class_prompts` y
  `review_prompts` devuelven un `Prompt` con `system` y `user`. El texto dinámico está copiado de `main.py`
  (f-strings, `dedent` y `repr` de Python de los diccionarios y listas). La interpolación de `{number}` y
  `{num}` copia la lógica de `interpolate_only` y se aplica, como en `Crew.kickoff`, a la descripción y al
  `expected_output` **completos**, incluido el texto que viene de etapas anteriores.
- **Variable desconocida en un texto de tarea:** si una descripción escrita por el Domain Agent contiene
  `{palabra}` (un identificador entre llaves), el original aborta con `ValueError` al lanzar la tarea
  (comprobado: `jpetstore_variable_en_descripcion.json`). La réplica lanza `PromptInterpolationError` en el
  mismo punto. El orquestador debe registrarlo como corrida fallida (§10.4), no corregir el texto.
- **Archivos de registro:** `save_prompt` escribe `<etapa>_prompt.txt` (mensaje de usuario) y
  `<etapa>_system_prompt.txt`, con los bytes exactos. §6 solo nombra el primero.
- **Vista previa:** `logs/prompts_preview/<app>/` tiene los cinco system prompts y el prompt de la Etapa 1 de
  cada aplicación. Los demás dependen de las salidas de cada corrida.
- **Pendiente para el orquestador (Fase 4):**
  - **Entrega sin alteraciones y registro de lo que recibe el modelo.** El mensaje de usuario empieza con un
    salto de línea y el system prompt termina con otro. Hay que comprobar en la transcripción de la primera
    llamada que `claude -p` (prompt por stdin; `--system-prompt` o `--system-prompt-file`) los entrega sin
    recortar, y dejar constancia de lo que Claude Code añade (system prompt fijo y `<system-reminder>`, D4).
  - **Qué texto es "la respuesta final" de un agente.** En el original es lo que sigue a la **última**
    aparición de `Final Answer:`, sin espacios al inicio ni al final y sin una cerca ``` final desparejada
    (`crewai/agents/parser.py`). Eso es lo que se limpia con `clean_json_output` y lo que se pasa como contexto
    (D27). Si el LLM no escribe ni `Final Answer:` ni `Action:`, CrewAI le devuelve un mensaje de error de
    formato y vuelve a pedirle la respuesta; la réplica no tiene equivalente. En la réplica la respuesta es el
    texto final de `claude -p`. Como el mensaje termina en `Thought:` y el system prompt no explica ReAct
    (D26, D28), Claude puede escribir `Thought: ... Final Answer: ...` o no hacerlo. Hay que decidir si se toma
    el texto completo o lo que sigue a `Final Answer:`. **Decisión de Jorge antes de la primera corrida.**
  - **Dominios omitidos.** `main.py` (líneas 204-205) empareja la tarea `i` con `business_domains[i]`. Si la
    Etapa 1 devolviera un dominio sin nombre o sin descripción (se omite en las líneas 137-142), los nombres
    quedan desplazados: el original busca en cada respuesta el nombre de otro dominio, no lo encuentra y guarda
    una lista vacía. Los resultados de los dominios desplazados se pierden, el último dominio desaparece y la
    fusión puede saltarse porque `len == number`. Comprobado por el revisor con el original: dominios
    [A, B sin descripción, C, D] dan `all_domains = {A: [...], B: [], C: []}`. §7 pide una llamada "para cada
    dominio con nombre y descripción". Hay que decidir si se reproduce el desajuste o se registra como corrida
    fallida. **Decisión de Jorge antes de la primera corrida.**
  - `{tools}` o `{tool_names}` dentro del contexto: el original los reemplazaría por el texto de herramientas
    de ReAct; la réplica no puede reproducirlo y lanza `PromptInterpolationError`. No se probó en el original.
  - **Nombres de archivo.** El original solo reemplaza `/` al guardar `domains/<Dominio>.json`. En Windows un
    nombre con `"`, `:` u otro carácter no permitido falla con `OSError`. El orquestador debe sanear solo la
    ruta del archivo, nunca el nombre dentro de los prompts ni de los JSON.
  - **Sin equivalente en la réplica:** al alcanzar `max_iter`, CrewAI inyecta un mensaje que obliga al LLM a
    dar su respuesta final; `--max-turns` solo corta (D2, D22). *Desde D39 la réplica también pide la
    respuesta final.* Y la tarea de la Etapa 1 escribe además
    `output/<app>/domain_clusters.json` con la salida sin limpiar (`output_file` en `crew.py`), que ninguna
    herramienta lee.
- Python crea `prompts/__pycache__/` y `scripts/__pycache__/` al importar estos módulos; no son parte de la
  réplica (igual que en D18).
- Archivos nuevos de la fase: `prompts/build_prompts.py`, `scripts/capture_crewai_prompts.py`,
  `scripts/check_prompts.py`, `logs/prompts_golden/` (7 capturas), `logs/prompts_check.txt` y
  `logs/prompts_preview/`.

### D30. Revisión independiente de la Fase 3 (2026-11-16)
- **Quién y cómo:** agente revisor (Claude Sonnet, solo lectura sobre la réplica, sin llamadas a `claude -p`
  ni a ningún LLM real). No reutilizó el arnés de la réplica: escribió el suyo, que ejecuta una copia del
  original con la clase `LLM` **real** de CrewAI apuntando a un servidor HTTP local que registra lo que viaja
  por la red, en 8 escenarios (6 de casos límite). **Veredicto: aprobado con observaciones, sin bloqueantes.**
- **Lo que confirmó:** las tres premisas de D25, D26 y D27 (llaves dobles, envoltura, contexto solo con fusión
  en Common Class y siempre en Review); que CrewAI 1.8.1 no añade nada más al primer mensaje (memoria,
  *knowledge*, fecha, razonamiento, esquemas de salida y datos de entrenamiento están desactivados o ausentes,
  y el contexto no se interpola); que los tres parches de la copia son los únicos cambios; que el mensaje de
  usuario de `build_prompts.py` es idéntico al del original en sus 8 escenarios, incluidos nombres con comillas,
  `/`, llaves y `{num}`, `common_result_json` vacío, lista de clases restantes vacía y fusión con
  `Domain_Cluster`; las cifras de D24 y D28; y que `check_prompts.py` es una comprobación real (detectó 8 de 9
  mutaciones). `MicroAgent/` intacto y `_sandbox/` vacío, antes y después.
- **Observaciones y qué se hizo:**
  - **H1 (medio):** D29 describía mal el desajuste de dominios omitidos. Corregido con el resultado de su
    ejecución real.
  - **H2 (medio):** D29 y D24 no decían que Claude Code añade su propio system prompt y los
    `<system-reminder>`. Añadido el alcance de "idéntico" en D24 y el registro pendiente en D29.
  - **H3 (medio):** huecos de cobertura. Añadidos los escenarios `jpetstore_num_en_nombre` y
    `jpetstore_fusion_domain_cluster`; `check_prompts.py` exige ahora CrewAI 1.8.1 en cada captura y
    reconstruye `domain_clusters` y las clases asignadas como `main.py` (líneas 306-310 y 421-428). La mutación
    que sobrevivía (no interpolar `expected_output`) ahora se detecta.
  - **H4 (bajo):** D29 precisa qué es la respuesta final en CrewAI y el reintento por error de formato.
  - **H5, H6 (bajo):** añadidos a los pendientes de la Fase 4 en D29 (nombres de archivo en Windows;
    `max_iter` y `output_file`).
  - **H7 (bajo):** límite de la captura acotado en D24 con su prueba sobre la clase `LLM` real.
  - **H8 (bajo):** `__pycache__` anotado en D29.
- **Lo que el revisor no pudo verificar:** las rutas por `litellm` y por el proveedor nativo de Anthropic, el
  `.env` de los autores, cómo entrega `claude -p` los dos prompts (Fase 4) y el caso de `{tools}` en el
  contexto.
- **Incidente del revisor:** sus ejecuciones de CrewAI crearon dos carpetas en `AppData/Local/CrewAI` y las
  borró. Las de la captura de la réplica (D24) siguen ahí.
- **Comprobación tras los cambios:** `python -X utf8 scripts/check_prompts.py` → 7 capturas, 279
  comprobaciones, 0 problemas; `check_microagent_untouched.py` → `AVISO` (artefacto intacto); `_sandbox/`
  vacío.

### D31. Decisiones de Jorge sobre los dos puntos abiertos de D29 (2026-11-16)
Se aplican en el orquestador (Fase 4); aquí solo se registran.
1. **Respuesta final de un agente: "la réplica debe tomar lo mismo al original".**
   - *Original (`crewai/agents/parser.py`):* la respuesta es el texto que sigue a la **última** aparición de
     `Final Answer:`, sin espacios al inicio ni al final; si termina en una cerca ``` desparejada (número impar
     de cercas), se quita. Ese texto es el que `main.py` limpia con `clean_json_output` y el que se pasa como
     contexto a la tarea siguiente (D27).
   - *Réplica:* el orquestador aplicará esa misma regla al texto final de `claude -p`. Guardará en `logs/` las
     dos versiones: el texto completo y el extraído.
   - *Si el texto final no contiene `Final Answer:`:* CrewAI le devuelve al LLM un mensaje de error de formato
     y vuelve a pedirle la respuesta. La réplica no lo hace. **Decisión de Jorge (2026-11-16):** tomar el texto
     final completo (recortado) y anotar en el log de la etapa que no había `Final Answer:`.
   - *Alternativa descartada: obligar a Claude a escribir `Final Answer:`.* Jorge la planteó ("¿y si hacemos
     que Claude escriba final answer? [...] si no lo puede hacer, entonces hagamos tu propuesta"). Se puede,
     pero solo cambiando lo que recibe el modelo: o se añade al system prompt la parte final del bloque ReAct
     del original ("Once all necessary information is gathered, return the following format: ... Final
     Answer: ..."), que §6 excluye y que sin la parte de `Action` no es ni el original ni la especificación; o
     se le reclama el formato en una segunda llamada, con un mensaje de CrewAI que habla de `Action:` y gasta
     cupo. Ninguna es necesaria: en las etapas 1 a 3 el JSON se extrae con `clean_json_output` esté o no la
     etiqueta, y en las etapas 4 y 5 el resultado sale del archivo que escribe `write_result_to_json`. La
     etiqueta solo cambia el texto que se pasa como contexto (D27). Además, el mensaje de usuario ya termina en
     `Thought:` y pide "your best Final Answer" (D26), así que es probable que Claude la escriba por su cuenta;
     la Fase 4 registrará en cuántas etapas lo hace.
2. **Dominios sin nombre o sin descripción: "hay que seguir el original pero documenta el error".**
   - *Error del original (`main.py`):* las líneas 137-142 omiten la tarea de clustering de un dominio sin
     nombre o sin descripción, pero las líneas 204-205 emparejan la tarea `i` con `business_domains[i]`, sin
     descontar los omitidos. A partir del dominio omitido, cada respuesta se busca bajo el nombre del dominio
     anterior en la lista (línea 230), no se encuentra y se guarda una lista vacía. Efecto: los resultados de
     los dominios desplazados se pierden, el último dominio no aparece en `all_domains.json` y, si con eso
     `len(all_domain_results) == number`, la fusión se salta. Ejemplo comprobado por el revisor con el
     original (D30): dominios [A, B sin descripción, C, D] dan `all_domains = {A: [...], B: [], C: []}`.
   - *Réplica:* el orquestador reproducirá ese emparejamiento tal cual. Si ocurre en una corrida, lo anotará en
     el log de la corrida (dominio omitido, nombres desplazados, resultados perdidos) y se informará en
     `REPORTE.md`. La corrida no se descarta ni se corrige.
   - Solo se activa si el Domain Agent devuelve un dominio incompleto; con la salida esperada de la Etapa 1 no
     tiene efecto.

### D32. Cierre de los tres puntos abiertos de fases anteriores (2026-11-16, decisiones de Jorge)
1. **Insumo del resumen de BD de PartsUnlimitedMRP (D11): "sigue lo que esté utilizando el paper original".**
   - *Lo que el original documenta:* el paper (§3.1.1) dice "we preprocess the database files by requiring an
     LLM to provide metadata summaries based on the database file"; el artefacto da el "Database Summary
     Prompt", que recibe `{sql_content}` y dice "SQL Schema to analyze", y publica un único resumen
     (`database/jpetstore-6/sql-summary.json`). El README pide generar el resumen con un LLM y dejarlo en
     `microagent/database`.
   - *Lo que no se puede saber:* qué archivo de PartsUnlimitedMRP resumieron los autores. Ni el paper ni el
     artefacto lo dicen, y el artefacto no trae ningún archivo de base de datos de esa aplicación.
   - **Decisión (cerrada):** se mantiene lo ya generado: `schema.psql` (el único archivo de definición de base
     de datos del repositorio) → "Database Summary Prompt" literal → `database/partsunlimited/sql-summary.json`.
     Es el procedimiento del original aplicado sin modificar su prompt. No se regenera nada.
   - Sigue siendo una amenaza a la validez (el insumo exacto de los autores es desconocido) y así se informará.
   - **Confirmación de Jorge (2026-11-16):** "utiliza lo que les dio a los autores, que tengo entendido que fue
     el schema.psql". Se mantiene `schema.psql`. Precisión de Claude Code: que los autores usaran ese archivo
     es una inferencia razonable (es el único esquema del repositorio y encaja con su prompt), no un hecho
     comprobado.
2. **Fuga por rutas de archivo (D23, H1): no se bloquea, igual que el original.**
   - *Pregunta de Jorge:* si el original no lo bloqueaba porque CrewAI lo impedía.
   - *Comprobado:* no. CrewAI ejecuta las herramientas como funciones de Python normales, sin aislamiento de
     archivos. En `custom_tools.py`, `search_file` (líneas 265-279) acepta cualquier ruta absoluta y resuelve
     las relativas contra `WORKING_DIR`; `get_class_relation_and_code` (líneas 1449-1466) hace lo mismo con el
     `file_path` de `class_summaries.json`. Nada en el original impide leer fuera de `resources/<app>/`.
   - *Por qué no lo bloquearon:* no consta. Suposición de Claude Code: es un prototipo de investigación y los
     prompts dirigen al agente al código de la aplicación; además sus descomposiciones de referencia
     (`decomposition/`) quedaban fuera de la carpeta de trabajo (`microagent/`).
   - **Decisión (cerrada):** el servidor no restringe rutas. Se mantienen las medidas de D23 que no tocan las
     herramientas: `evaluation/references/` vacía hasta terminar las 12 corridas, y auditoría de las rutas
     pedidas en cada corrida (una lectura fuera de `resources/<app>/` se informa; una corrida que lea salidas
     de otra corrida, `logs/` o `evaluation/` se marca como contaminada, no se descarta en silencio).
   - **Condición de Jorge: "el contexto debe ser el mismo en todas las corridas".** Ya lo exige §10.3. El
     orquestador (Fase 4) lo hará comprobable: antes de cada corrida calculará el SHA-256 de
     `context/<app>/`, `database/<app>/` y del código de `resources/<app>/` que usan las herramientas, lo
     guardará en el log de la corrida y abortará si no coincide con el de la primera corrida de esa aplicación.
3. **Carpetas `target/` dentro de `MicroAgent/` (D14): borradas.**
   - *Condición de Jorge:* "límpialo si solo lo generó VS Code y no el MicroAgent como tal".
   - *Comprobado antes de borrar:* `MicroAgent.zip` tiene 1128 archivos y ninguno bajo `target/`; las seis
     carpetas se crearon el 2026-11-14 entre las 00:28 y las 00:29 (compilación automática de la extensión
     Java de VS Code, D14); no había otros residuos (`.classpath`, `.project`, `.settings`, `bin`,
     `__pycache__`).
   - *Hecho:* se borraron las seis carpetas (1167 archivos). `python scripts/check_microagent_untouched.py` →
     0 faltantes, 0 modificados, 0 adicionales: `RESULTADO: OK (MicroAgent/ identico al zip)`.
   - Pueden reaparecer si se abre `MicroAgent/` en VS Code con la extensión Java activa. No afectan a la
     réplica; el mismo script lo avisaría.

---

## Fase 4 — Orquestador (`run_pipeline.py`)

### D33. Diseño del orquestador y correspondencia con `main.py` (2026-11-16)
- **Especificación (§7):** reproducir la misma lógica y el mismo orden de `main.py`, con una llamada a
  `claude -p` por agente.
- **Qué es copia del original.** `clean_json_output` es copia literal (se comprueba comparando el árbol
  sintáctico con el de `main.py`). El flujo de las cinco etapas copia los bloques de `main.py` (cada bloque
  cita sus líneas): resumen de dominios, omisión de dominios sin nombre o sin descripción, lectura de
  `domain_data[domain_name]`, regla `len(all_domain_results) == number`, desenvoltura de `Domain_Cluster`,
  respaldos de las etapas 4 y 5 y cálculo de las clases restantes. Los prompts los arma
  `prompts/build_prompts.py` (Fase 3).
- **Parámetros:** `--app`, `--run-id`, `--model` (por defecto `claude-sonnet-4-6`, D3), `--number` y `--num`
  (por defecto los de la aplicación; si no coinciden con §4.2 y §4.3, se rechaza), `--only-stage1` (prueba de
  humo) y `--stage-timeout` (3600 s por llamada).
- **Comando efectivo de cada agente:**
  `claude -p --model claude-sonnet-4-6 --effort high --system-prompt "<system>" --tools "" --mcp-config
  <etapa>_mcp_config.json --strict-mcp-config --allowedTools mcp__microagent__<h1>,... --disable-slash-commands
  --setting-sources "" --max-turns <30|45> --output-format stream-json --verbose`, desde `_sandbox/`, con el
  mensaje de usuario por stdin (leído del propio `<etapa>_prompt.txt` ya guardado) y las variables
  `MAX_THINKING_TOKENS=0`, `MCP_TIMEOUT` y `MCP_TOOL_TIMEOUT`. El servidor MCP recibe `APP_NAME`, `RUN_ID`,
  `MICROAGENT_TOOLS` (solo las herramientas del agente, D20), `MICROAGENT_LOG` y, en las etapas 4 y 5,
  `RESULT_FILE`.
- **Desviaciones respecto a la letra de §7 (registran más o siguen al original; ninguna cambia los prompts):**
  1. **`--output-format stream-json --verbose` en lugar de `json`.** El evento final del flujo es el mismo JSON
     que devuelve `--output-format json` (se guarda en `<etapa>_claude.json`: texto final, turnos, duración,
     tokens y costo nominal). El flujo completo (`<etapa>_stream.jsonl`) hace falta para leer el mensaje
     `init` y cada llamada a herramienta (D22).
  2. **`--effort high` y entorno limpio.** No están en §7; ver D35.
  3. **`RESULT_FILE` se borra antes de la etapa, no se "inicializa vacío".** El servidor fusiona con lo que
     haya en el archivo (D20), así que lo seguro es que no exista. Además deja el mismo estado final que el
     original: si el agente no llama a `write_result_to_json` y su respuesta tampoco es JSON, no queda archivo.
  4. **No se "aplanan" los dominios por capas de la fusión para la Etapa 4.** §7 dice "si los valores son dicts
     por capas, aplánalos". El original (líneas 306-330) solo aplana al escribir los archivos por dominio; el
     `domain_clusters` que pasa a la Etapa 4 conserva las capas. Se hace como el original (comprobado con la
     captura `jpetstore_fusion_domain_cluster`).
  5. **Si la salida de la fusión no es JSON, no se escribe `merged_domains.json`.** Es lo que hace el original
     (líneas 332-335): vuelve a `all_domain_results` sin escribir el archivo, y `rank_dependency_entropy`, que
     lo lee, no lo encontrará. Queda como observación de la corrida.
  6. **Una corrida sin `result.json` se registra como fallida.** El original guarda `result.txt` y termina con
     "Workflow Complete". La réplica guarda el mismo `result.txt` y marca la corrida como fallida (§10.4).
- **Respuesta final de un agente (D31).** `extract_final_answer` copia la rama `includes_answer` de
  `crewai/agents/parser.py` (CrewAI 1.8.1, leído de la caché de `uv` de la captura de la Fase 3): lo que sigue
  a la última aparición de `Final Answer:`, recortado y sin una cerca final desparejada. Sin etiqueta, el texto
  completo recortado, con una observación. Se guardan las dos versiones (`<etapa>_raw.txt` y
  `<etapa>_final_answer.txt`). Esa respuesta es la que se limpia con `clean_json_output` y la que se pasa como
  contexto (D27): la del Merging Agent a la Etapa 4 solo si hubo fusión; la del Common Class Agent a la Etapa
  5 siempre.
- **Desajuste de dominios omitidos (D31).** Se reproduce el emparejamiento `business_domains[i]` de la línea
  205 y se anotan el dominio omitido y cada tarea desplazada.
- **Validez de cada llamada (D22).** La corrida queda **fallida**, sin corregir ni reintentar, si: el `init` no
  muestra el servidor `microagent` conectado o las herramientas visibles no son exactamente las del agente (en
  ese caso se corta el proceso sin esperar la respuesta); `claude` no termina con `success` (error de la API,
  cupo agotado; el límite de turnos dejó de ser un fallo en D39); hay una llamada a una herramienta fuera de la lista; hay bloques de
  razonamiento extendido; responde otro modelo; o la transcripción muestra que a la API se enviaron otras
  herramientas, otro modelo u otro `effort`. Tras la revisión (D38) también la invalidan: un system prompt o un
  mensaje de usuario que no llegan idénticos, contexto añadido por Claude Code distinto del habitual (D35) y un
  cambio de versión de Claude Code respecto al inicio de la corrida.
- **Observaciones (se registran en `run_status.json` y se informarán en `REPORTE.md`; no invalidan la
  corrida):** respuesta sin `Final Answer:`, dominio omitido o desajustado, JSON inválido en clustering o
  fusión, uso de los respaldos, rutas pedidas a `search_file` fuera de `resources/<app>/`, corrida
  **contaminada** (lectura de salidas de otra corrida, `logs/` o `evaluation/`; D23 y D32), historial compactado
  por Claude Code, llamadas denegadas y avisos del servidor. (Un prompt no idéntico en la petición era una
  observación; desde D38 invalida la llamada.)
- **Entrega de los prompts (D29).** Claude Code guarda en la transcripción de cada sesión
  (`~/.claude/projects/<carpeta>/<session_id>.jsonl`) el system prompt, las herramientas y los mensajes
  enviados a la API. El orquestador la copia a `<etapa>_transcript.jsonl` y comprueba que un bloque del system
  es **idéntico** al de la réplica y que el último bloque del primer mensaje de usuario es **idéntico** al
  prompt. Deja constancia de lo que añade Claude Code (D35).
- **Contexto igual en todas las corridas (D32).** Antes de cada corrida se calcula el SHA-256 de
  `context/<app>/`, `database/<app>/` y los archivos fuente que cita `class_summaries.json` (27 archivos en
  JPetStore, 56 en PartsUnlimitedMRP). La primera corrida real de cada aplicación lo guarda en
  `logs/context_fingerprint/<app>.json`; las siguientes abortan si no coincide. La de JPetStore la creó la
  prueba de humo (D36).
- **Otras protecciones:** una carpeta de corrida existente nunca se sobrescribe; `smoke-test` está reservado;
  `evaluation/references/` debe estar vacía (D23) salvo `--allow-references`, que queda registrado;
  `_sandbox/` debe estar vacío antes de cada llamada.
- **Sin reanudación.** Una corrida cortada (por ejemplo, por el límite de 5 horas) no se continúa: se registra
  como fallida y se repite con otro `run_id` (§10.4). Una corrida interrumpida con Ctrl+C también queda
  registrada como fallida (D38). Si el proceso del orquestador se mata desde fuera, `run_status.json` se queda
  en `en_curso`; esa corrida se trata igualmente como fallida.
- **Paradas del original que aquí son corrida fallida (añadido tras la revisión, D38).** `main.py` termina sin
  error (`return`) si la Etapa 1 no devuelve JSON, si no devuelve dominios o si no queda ninguna tarea de
  clustering. La réplica se detiene en el mismo punto, sin llamar a ningún agente más, y registra la corrida
  como fallida.
- **Escritura de archivos.** UTF-8 y saltos de línea LF, como escribiría el original en Linux;
  `json.dump(..., indent=2)` como el original. `domains/<Dominio>.json`: `/` → `-` como el original; los
  caracteres que Windows no admite se sustituyen por `_` solo en la ruta y se anota (D29).
- **No se reproduce:** el `output_file` de la tarea de la Etapa 1 (`output/<app>/domain_clusters.json`, D29),
  porque sería un archivo compartido entre corridas y ninguna herramienta lo lee; ni el `NameError` del final
  de `main.py` (§7). El resumen final sale de `run_status.json`.
- **`--max-turns` frente a `max_iter` (corregido tras la revisión, D38).** En el original cada iteración es
  una llamada al LLM con, como mucho, una herramienta, y `max_iter` limita esas iteraciones. `--max-turns N`
  limita las **peticiones a la API**, no las llamadas a herramientas: tras cada petición que termina pidiendo
  herramientas, estas se ejecutan y, si ya van N peticiones, `claude` corta con `error_max_turns`. Se leyó en
  el binario de Claude Code 2.1.325 y se comprobó con `--max-turns 3` (3 peticiones, 9 llamadas a herramientas,
  corte; D36). Los dos límites cuentan llamadas al modelo, así que la correspondencia 30/30/30/45/45 es
  directa. La diferencia es que Claude pide varias herramientas en una misma petición (unas 3 de media en las
  pruebas), de modo que con el mismo límite puede hacer más llamadas a herramientas que el original. El campo
  `num_turns` del resultado **no** es ese contador: en una llamada que termina bien vale, aproximadamente,
  llamadas a herramientas + 1 (20 con 19 llamadas y 7 peticiones). El número de peticiones de cada llamada
  queda en `<etapa>_audit.json` (`entrega.peticiones_api`). Lo que pasa al llegar al límite está en D37.
- Archivos por etapa en `output/<app>/<run_id>/logs/`: `_prompt.txt`, `_system_prompt.txt`, `_mcp_config.json`,
  `_stream.jsonl`, `_claude.json`, `_raw.txt`, `_final_answer.txt`, `_server.jsonl`, `_transcript.jsonl`,
  `_audit.json`, `_stderr.txt`. De la corrida: `run_manifest.json`, `run_status.json` y `pipeline.log`.
- **Privacidad:** las transcripciones copiadas contienen el correo de la cuenta (lo inserta Claude Code en un
  `<system-reminder>`). Conviene tenerlo en cuenta antes de compartir `output/`.

### D34. Prueba del orquestador sin gastar cupo (2026-11-16)
- **Qué se hizo:** `scripts/fake_claude.py` sustituye a `claude` (variable `MICROAGENT_CLAUDE_CMD`): acepta la
  misma línea de comandos, emite un flujo `stream-json` con la forma del real y responde con un guion.
  `scripts/test_pipeline_offline.py` ejecuta el orquestador completo con ese sustituto.
- **Comparación con el original.** Los guiones son los de las capturas de la Fase 3 (D24; 7 al escribir esta entrada, 9 desde
  la revisión, D38), en las que el
  `main.py` original se ejecutó con CrewAI 1.8.1 real. Con las mismas respuestas, el orquestador produce las
  mismas ejecuciones de agente en el mismo orden, el **mismo mensaje de usuario byte a byte** en las 47
  ejecuciones (61 con las dos capturas nuevas) y los **mismos archivos de salida con el mismo contenido** que dejó el original (hasta 12
  archivos por escenario; solo cambia CRLF por LF, porque la captura corrió en Windows). El escenario en el
  que el original aborta al interpolar también deja la corrida fallida en el mismo punto.
- **Además:** desajuste de dominios (`{A: [...], B: [], C: []}`, el resultado que el revisor de la Fase 3
  obtuvo con el original, D30); Etapa 1 vacía o con JSON inválido; respaldos de las etapas 4 y 5; respuesta sin
  `Final Answer:`; ocho fallos de llamada (servidor sin conectar, herramienta de más, sin resultado,
  razonamiento, otro modelo, herramienta fuera de lista, error 429, límite de turnos); una corrida con el
  **servidor MCP real** en las etapas 3 a 5 (`write_result_to_json`, `RESULT_FILE`, registro del servidor y
  auditoría de rutas, incluida una lectura contaminante); y las protecciones de D33.
- **Resultado:** `python -X utf8 scripts/test_pipeline_offline.py` → 0 problemas
  (`logs/pipeline_offline_test.txt`, con el número de comprobaciones). Tarda unos 3 minutos.
- **Separación de lo real:** las corridas simuladas solo pueden usar identificadores `_prueba-...`, las reales
  no pueden usarlos, y las simuladas no crean la línea base del contexto. Se borran al terminar.
- **Límite de esta prueba:** demuestra que el orquestador hace lo mismo que `main.py` con las mismas
  respuestas. No dice nada de cómo responde Claude; eso es la prueba de humo (D36).

### D35. Configuración efectiva de `claude -p`: esfuerzo fijo y entorno limpio (2026-11-16)
- **Hallazgo.** El orquestador se lanzó desde una sesión de la app de escritorio de Claude, y el proceso
  `claude -p` heredaba 33 variables `CLAUDE*`/`ANTHROPIC*` de esa sesión (`CLAUDE_EFFORT=high`,
  `CLAUDE_CODE_ENTRYPOINT=claude-desktop`, `CLAUDE_CODE_SIMPLE`, `CLAUDE_CODE_CHILD_SESSION`, etc.). Con ellas,
  el bloque `<system-reminder>` de entorno que Claude Code antepone al mensaje medía 1 791 caracteres (añade
  la línea del directorio *scratchpad*); en las 54 llamadas de la Fase 1 medía 954. Es decir, **lo que recibe
  el modelo dependía de desde dónde se lanzara la corrida**, lo que choca con §10.1.
- **Decisión de Claude Code (dos cambios, ambos para mantener constante lo ya usado):**
  1. **Entorno limpio.** El orquestador quita del entorno del proceso `claude` todas las variables `CLAUDE*` y
     `ANTHROPIC*` heredadas (salvo `CLAUDE_CONFIG_DIR`) y añade solo las suyas. Los nombres quitados quedan en
     `run_manifest.json` y en cada `<etapa>_claude.json` (sin valores, porque algunas llevan credenciales).
  2. **`--effort high` explícito.** Sin la opción, `claude` toma el esfuerzo de la sesión que lo lanza. `high`
     es el valor que llevaron las 54 llamadas de la Fase 1 (lo dicen sus transcripciones) y el valor por
     defecto de la API. El original no tiene este parámetro.
- **Precisiones tras la revisión (D38):** en las pruebas con el entorno heredado el esfuerzo ya era `high`,
  así que fijarlo es una precaución; lo único que cambiaba en lo enviado al modelo era la línea del directorio
  *scratchpad*, que lleva una ruta distinta en cada sesión. El entorno limpio se amplió a las variables sin
  prefijo `CLAUDE` que `claude` también lee y se fijaron cinco valores más (D38).
- **Comprobación** (`logs/fase4_prueba_humo/comprobacion-entorno-limpio/`, una llamada de 1 turno, y la prueba
  de humo definitiva, D36): con el entorno limpio la autenticación del plan sigue funcionando
  (`apiKeySource: none`), y los bloques que añade Claude Code miden **954, 167, 86, 650 y 65 caracteres, igual
  que en las 54 llamadas de la Fase 1**. Parámetros de todas las peticiones: `model: claude-sonnet-4-6`,
  `max_tokens: 32000`, `thinking: disabled`, `temperature: 1`, `output_config.effort: high`.
- **Corrección a D4:** D4 decía que las peticiones iban "sin parámetro de temperatura". Las transcripciones
  muestran que, con el razonamiento desactivado, Claude Code envía **`temperature: 1`** (también en las 54
  llamadas de la Fase 1). El original usa temperatura 0. La amenaza a la validez es la misma, pero el valor es
  conocido.
- **Lo que Claude Code añade a cada llamada y no se puede quitar (D4):** un primer bloque de system (`You are
  a Claude agent, built on Anthropic's Claude Agent SDK.`, 62 caracteres), seguido del system prompt de la
  réplica en un bloque aparte; y cinco bloques `<system-reminder>` antes del mensaje de usuario: entorno
  (directorio de trabajo, plataforma, shell, sistema operativo y dos avisos genéricos sobre archivos
  descargados y `curl`), modelo, tokens restantes, correo de la cuenta y fecha. La línea de shell dice "Bash
  tool also available" aunque el agente no tiene Bash, y la fecha cambia de un día a otro. Desde D38 la
  auditoría invalida la llamada si aparece cualquier otra cosa.
- **Efecto sobre el orquestador:** si una petición sale con otro modelo u otro `effort`, la llamada es inválida
  (D33).

### D36. Prueba de humo de la Etapa 1 con JPetStore y comprobación de `--max-turns` (2026-11-16)
- **Especificación (§7):** ejecutar solo la Etapa 1 con JPetStore y revisar herramientas llamadas, ausencia de
  herramientas integradas y validez del JSON.
- **Llamadas reales hechas (5; la quinta tras la revisión, D38), todas archivadas en
  `logs/fase4_prueba_humo/`** (se movieron fuera de
  `output/` para que allí solo queden las corridas de verdad; las rutas absolutas dentro de sus registros
  apuntan a la ubicación original):

  | Carpeta | Qué es | Peticiones a la API | `num_turns` | Herramientas | Costo nominal |
  |---|---|---|---|---|---|
  | `prueba-humo-etapa1/` | Etapa 1, **con el entorno heredado** (antes de D35) | 6 | 16 | 15 | USD 0,148 |
  | `comprobacion-max-turns/` | Etapa 1 con `--max-turns 1`, entorno heredado | 1 | 2 | 3 | USD 0,012 |
  | `comprobacion-entorno-limpio/` | Etapa 1 con `--max-turns 1`, entorno limpio y `--effort high` | 1 | 2 | 3 | USD 0,011 |
  | `prueba-humo-etapa1-b/` | Etapa 1, **configuración de D35** | 7 | 20 | 19 | USD 0,148 |
  | `comprobacion-max-turns-3/` | Etapa 1 con `--max-turns 3`, **configuración definitiva (D38)** | 3 | 4 | 9 | USD 0,072 |

  La columna de peticiones se añadió tras la revisión (D38): es lo que limita `--max-turns` (D33).

- **Resultado de la prueba definitiva (`prueba-humo-etapa1-b`):**
  - *Prompts sin recortes:* el system prompt (2 652 caracteres, termina en salto de línea) y el mensaje de
    usuario (2 659 caracteres, empieza con salto de línea y termina en `Thought:`) llegan a la API **idénticos,
    carácter por carácter**.
  - *Solo sus herramientas:* el modelo ve exactamente las 5 del Domain Agent; hizo 19 llamadas
    (`get_all_class_hierarchy` 1, `get_all_class_summaries` 1, `get_database_summary` 1,
    `get_class_basic_info` 16), todas dentro de la lista; el servidor registró las mismas 19; 0 herramientas
    integradas, 0 llamadas denegadas, 0 bloques de razonamiento; `_sandbox/` vacío al terminar.
  - *JSON válido:* 4 dominios (`Account Management`, `Catalog`, `Shopping Cart`, `Order Management`), todos
    con nombre y descripción. Son más que n = 3, así que en una corrida completa **la fusión se ejecutaría**.
    El modelo no copió las llaves dobles del prompt (D25).
  - *Sin `Final Answer:`:* el texto final es un párrafo de análisis seguido del JSON en una cerca ` ```json `.
    `clean_json_output` extrae el JSON. Queda como observación (D31). En la primera prueba pasó lo mismo.
  - 7 peticiones a la API de un máximo de 30 (`num_turns` 20; ver D33); 33 s de API; tokens: 9 de entrada, 2 153 de salida, 15 794 de escritura en
    caché y 69 518 de lectura.
- **`--max-turns` corta de verdad (cierra D2 y D22).** Con `--max-turns 1`, `claude` termina con
  `subtype: error_max_turns`, `is_error: true`, código de salida 1 y sin texto final. En aquella prueba el orquestador dejaba la
  corrida como fallida; desde D39 pide la respuesta final en una petición más. Con `--max-turns 3` corta tras la tercera petición, después de ejecutar sus
  herramientas (9 llamadas en total): el límite cuenta peticiones (D38).
- **Valor de estas pruebas:** las dos carpetas `prueba-humo-*` no son corridas del experimento (solo tienen la
  Etapa 1) y no se evaluarán. La primera se hizo con una configuración que ya no es la vigente.

### D37. Puntos abiertos para Jorge antes de las corridas completas (2026-11-16)
1. **Qué hacer cuando un agente alcanza su límite de turnos.** *Cerrado: Jorge eligió la opción (b), D39.*
   - *Original (CrewAI 1.8.1, `crew_agent_executor.py` líneas 224-233 y `agent_utils.py` líneas 124-181):*
     al llegar a `max_iter` **no falla**. Añade un mensaje con el texto `force_final_answer` ("Now it's time
     you MUST give your absolute best final answer. You'll ignore all previous instructions, stop using any
     tools, and just return your absolute BEST Final answer.") y hace **una llamada más** al LLM, cuya
     respuesta es la respuesta final del agente. Esa respuesta nunca falla por formato: si no se puede
     analizar, `format_answer` la toma completa. El contador de iteraciones incluye los reintentos por error de
     formato.
   - *Réplica, tal como estaba hasta D39:* `--max-turns` corta y la corrida queda fallida (§10.4 lo lista
     como fallo).
   - *Por qué importa (corregido tras la revisión, D38):* esta entrada decía que el Domain Agent había usado
     "16 y 20 de sus 30 turnos". Era un error: el límite cuenta peticiones a la API (D33) y usó **6 y 7 de
     30**. Llegar al límite parece poco probable, aunque no se ha medido en las otras etapas ni en
     PartsUnlimitedMRP. Si ocurre, con la opción (a) esa corrida se descarta y se repite, mientras que el
     original habría producido un resultado: las corridas evaluadas quedarían seleccionadas por no haber
     llegado al límite.
   - *Opciones:* (a) dejarlo así, como dice §10.4; (b) al llegar al límite, continuar la misma sesión
     (`claude --resume`) con ese mismo texto de CrewAI y una sola petición más, y tomar su respuesta. Es lo más
     parecido al original que permite la CLI, con dos diferencias: el original inserta el texto como mensaje
     del asistente y la CLI solo admite mensajes de usuario; y las herramientas seguirían declaradas (el
     historial contiene llamadas a herramientas), como en el original, donde siguen descritas en el system
     prompt y solo se le pide al modelo que deje de usarlas. Si aun así pidiera una herramienta, la llamada
     fallaría. La opción (b) no está programada ni probada; probarla cuesta una llamada corta.
2. **Ubicación de `_sandbox/`.** El bloque de entorno que añade Claude Code muestra al modelo la ruta del
   directorio de trabajo: `...\Tesis\Replica de Paper\replica-claude-code\_sandbox`. No se puede quitar (D4).
   §5.3 pone esa carpeta como ejemplo. Moverla a una ruta neutra (por ejemplo `C:\ma_sandbox`) evitaría que el
   modelo lea las palabras "Replica de Paper", pero las llamadas de la Fase 1 ya se hicieron con la ruta
   actual. Recomendación de Claude Code: dejarla e informarlo como amenaza menor a la validez.

### D38. Revisión independiente de la Fase 4 y correcciones (2026-11-16)
- **Quién y cómo:** un agente revisor distinto del que programó la fase, de solo lectura, sin permiso para
  llamar a `claude` ni tocar `MicroAgent/`. Comparó `run_pipeline.py` con `main.py` línea por línea y con el
  código de CrewAI 1.8.1, repitió las pruebas, recalculó las cifras de D33 a D36 desde los flujos y las
  transcripciones, e hizo 25 mutaciones sobre una copia.
- **Veredicto: aprobado con observaciones.** Sin hallazgos bloqueantes ni altos. Confirmó: fidelidad a
  `main.py` (orden, número de llamadas, contexto de D27, regla de `Final Answer:`); que la prueba sin cupo
  compara de verdad contra el original; las cifras de la prueba de humo; y que las 54 llamadas de la Fase 1
  llevan `effort: high`, `temperature: 1`, razonamiento desactivado y los bloques de 954, 167, 86, 650 y 65
  caracteres. Probó además el servidor MCP real con 8 llamadas simultáneas a `write_result_to_json` (Claude
  agrupa llamadas en una misma petición): quedaron los 8 dominios, sin condición de carrera.
- **Hallazgos medios y qué se hizo:**
  1. **El entorno limpio solo quitaba `CLAUDE*` y `ANTHROPIC*`.** La sesión que lanza la corrida también deja
     variables sin ese prefijo que `claude` lee (`DISABLE_MICROCOMPACT`, `MCP_CONNECTION_NONBLOCKING`,
     `API_TIMEOUT_MS`, `DISABLE_AUTOUPDATER`, `MCP_SERVER_CONNECTION_BATCH_SIZE`, `AI_AGENT`...). *Corregido:*
     `child_env` quita también los prefijos `MCP_`, `DISABLE_`, `ENABLE_`, `MAX_THINKING`, `MAX_MCP`, `OTEL_`,
     `SENTRY` y una lista de nombres, y después fija cinco valores: `DISABLE_AUTOUPDATER=1` (la versión de
     Claude Code no cambia a mitad del experimento), `API_TIMEOUT_MS=900000` (el valor con el que se hizo la
     prueba de humo), `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` y `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` (punto 2) y
     `PYTHONDONTWRITEBYTECODE=1`. `run_manifest.json` guarda los nombres quitados y los nombres de todas las
     variables que recibe `claude` (sin valores). Qué se comprobó en el binario de Claude Code 2.1.325:
     `DISABLE_MICROCOMPACT` no aparece (no la lee esta versión) y `MCP_CONNECTION_NONBLOCKING` vale lo mismo
     ausente que con el valor heredado (`true`), así que las llamadas ya hechas no cambian.
  2. **Nada avisaba si Claude Code añadía contexto nuevo** (por ejemplo, un `CLAUDE.md` creado más adelante en
     `Replica de Paper\` o `Tesis\`, o la memoria automática del proyecto `_sandbox`; `--setting-sources ""` no
     los impide). *Corregido de dos maneras:* se desactivan con las dos variables anteriores, y la auditoría
     **invalida la llamada** si lo enviado no es exactamente lo de siempre: dos bloques de system (el de Claude
     Code y el de la réplica) y los cinco `<system-reminder>` conocidos, sin secciones de más. También invalida
     la llamada si cambia la versión de Claude Code respecto al inicio de la corrida, y comprueba las
     herramientas de cada forma de petición por separado, no su unión.
  3. **La equivalencia entre `--max-turns` y `max_iter` no estaba respaldada.** D33 decía que `num_turns`
     contaba "aproximadamente una unidad por llamada a herramienta". *Verificado y corregido:* el límite cuenta
     **peticiones a la API**. Se leyó en el binario y se comprobó con una llamada real (`--max-turns 3`: 3
     peticiones, 9 llamadas a herramientas, corte con `error_max_turns`; `logs/fase4_prueba_humo/
     comprobacion-max-turns-3/`, USD 0,072). D33, D36 y D37 quedan corregidas. Consecuencia: el Domain Agent no
     usó "16 y 20 de 30", sino **6 y 7 de 30**; el riesgo de llegar al límite es menor de lo que decía D37.
- **Hallazgos bajos y qué se hizo:**
  - *Ramas sin prueba (10 mutaciones sobrevivían).* Se añadieron dos capturas del `main.py` **original**
    (CrewAI 1.8.1 real, LLM simulado): `jpetstore_dominios_omitidos` (un dominio sin descripción y otro sin
    nombre; quedan menos resultados que n y la fusión se ejecuta; fusión con un dominio por capas; el Common
    Class Agent responde sin usar la herramienta) y `jpetstore_fusion_json_invalido` (no se escribe
    `merged_domains.json`). La primera muestra en el original el desajuste de D31: `all_domains.json` queda
    `{"Product Catalog": [...], "Customer's Account": []}`. La prueba compara ahora lo que el proceso `claude`
    recibe **de verdad** (argumentos y entorno) con `crew.py` y `custom_tools.py` originales y con valores
    escritos a mano, no con las constantes de `run_pipeline.py`. `check_prompts.py` (Fase 3) se ajustó para
    seguir a `main.py` en esas dos ramas.
  - *Un prompt no idéntico en la petición solo era una observación.* Ahora invalida la llamada.
  - *Ctrl+C dejaba `run_status.json` en `en_curso`.* Ahora queda como fallida (`interrumpida`). Si el proceso
    se mata desde fuera sigue quedando `en_curso`; esa corrida también se trata como fallida.
  - *D33 no decía* que las tres paradas silenciosas de `main.py` son corrida fallida. Añadido.
  - *D35 sobreestimaba el efecto del esfuerzo heredado* y D37 citaba líneas aproximadas. Corregidas.
- **Resultado tras las correcciones:**
  - `python -X utf8 scripts/test_pipeline_offline.py` → **155 comprobaciones, 0 problemas**, con 9 capturas del
    original (61 ejecuciones de agente con el mensaje de usuario idéntico byte a byte).
  - `python -X utf8 scripts/check_prompts.py` → 355 comprobaciones, 0 problemas.
  - Mutaciones repetidas sobre las 10 que sobrevivían y 2 nuevas del entorno: **12 de 12 detectadas**
    (`--solo-capturas` permite la prueba parcial que se usó para esto).
  - Llamada real con la configuración corregida (`comprobacion-max-turns-3`): autenticación correcta, prompts
    idénticos, los mismos bloques de 954, 167, 86, 650 y 65 caracteres, mismos parámetros, 0 problemas de
    auditoría.
  - `check_microagent_untouched.py` → `MicroAgent/` idéntico al zip.
- **Efectos colaterales:** para las dos capturas nuevas se recreó el entorno temporal de CrewAI 1.8.1 fuera
  del proyecto, y CrewAI volvió a crear la carpeta `CrewAI` en `AppData/Local` (D24). Se borró al terminar.
- **Lo que sigue sin verificar (no se puede sin gastar cupo en corridas largas):**
  - La entrega real de los prompts de las etapas 2 a 5 (solo se ha visto la del Domain Agent). La auditoría la
    comprueba en cada llamada y, si falla, invalida la corrida en esa etapa.
  - Si Claude Code compacta el historial en sesiones largas (etapas 4 y 5). Si ocurre, queda como observación
    `historial_compactado_por_claude_code`. Una petición auxiliar con otros parámetros invalidaría la llamada;
    en las 18 peticiones hechas hasta ahora no hubo ninguna.
  - Cómo termina `claude` cuando se agota el cupo de 5 horas a mitad de una llamada (solo está simulado el
    error 429).
  - Si la única autenticación disponible fuera la variable `CLAUDE_CODE_OAUTH_TOKEN`, el entorno limpio la
    quitaría. Hoy la autenticación sale de `~/.claude/.credentials.json` y funciona.
- **Amenazas menores que quedan anotadas:** los bloques que añade Claude Code incluyen la fecha del día, el
  correo de la cuenta, la plataforma, la ruta de `_sandbox/` y la frase "Bash tool also available", aunque el
  agente no tiene Bash (D35, D37).
- **Gasto de la fase en llamadas reales:** 5 llamadas, USD 0,39 nominales. Ninguna corrida completa.

### D39. Límite de turnos: respuesta final forzada, como en el original (2026-11-16, decisión de Jorge)
- **Decisión de Jorge** sobre el punto 1 de D37: hacerlo **como el original** (opción b). §10.4 lista el límite
  de turnos como motivo de corrida fallida; desde esta entrada ya no lo es por sí solo.
- **Qué hace el original, comprobado ejecutándolo.** Nueva captura `logs/prompts_golden/
  jpetstore_limite_de_iteraciones.json` (`main.py` original, CrewAI 1.8.1 real, LLM simulado): el Common Class
  Agent gasta sus 45 iteraciones (`max_iter`) llamando a la herramienta y CrewAI hace la llamada número **46**
  al modelo. Antes añade un mensaje con rol de asistente que repite el último paso del agente y termina con:
  "Now it's time you MUST give your absolute best final answer. You'll ignore all previous instructions, stop
  using any tools, and just return your absolute BEST Final answer." La respuesta a esa llamada es la respuesta
  final del agente (pasó como contexto a la Etapa 5) y la corrida termina normalmente. En esa llamada no se
  ejecuta ninguna herramienta.
- **Qué hace la réplica.** Si `claude` termina con `error_max_turns`, el orquestador hace **una petición más
  en la misma sesión**: `claude -p --resume <session_id>` con el mismo modelo, esfuerzo, system prompt y
  servidor MCP, `--max-turns 1`, **sin `--allowedTools`**, y ese mismo texto de CrewAI por stdin. Son N
  peticiones más una, igual que las `max_iter` + 1 llamadas del original (D33). La respuesta se trata como
  cualquier otra (regla de `Final Answer:`, D31) y la corrida sigue. El tiempo máximo (`--stage-timeout`)
  vale para cada una de las dos llamadas, así que una etapa que llega al límite puede durar hasta el doble. Queda la observación
  `limite_de_turnos_respuesta_forzada` en `run_status.json`, para informarla en `REPORTE.md`.
- **Diferencias con el original que no se pueden quitar:**
  1. El texto llega como mensaje de **usuario**, en el mismo mensaje que los resultados de las últimas
     herramientas y justo después de ellos; el original lo pone en un mensaje de asistente. La CLI no permite
     escribir mensajes de asistente.
  2. Las herramientas siguen declaradas en la petición (el historial contiene llamadas a herramientas). En el
     original también siguen descritas en el system prompt. Como no se pasa `--allowedTools`, si el modelo
     pidiera una, Claude Code la deniega y el servidor no la ejecuta.
  3. En el original, el mensaje que pide la respuesta final repite antes el texto del último paso del
     agente ("Thought… Action… Observation…", que incluye la guía de herramientas de ReAct de D28). La réplica
     no lo repite: en la sesión de Claude Code ese paso ya está en el historial como llamadas y resultados de
     herramientas, y ReAct no existe (D28).
  4. Si el modelo pide una herramienta en esa respuesta, CrewAI toma el texto de la respuesta tal cual (su
     texto ReAct "Thought… Action…"). La réplica toma el texto que acompañe a la petición y lo anota
     (`respuesta_forzada_pidio_herramientas`). Si no hay ningún texto, la corrida queda fallida
     (`respuesta_forzada_vacia`): el original aborta con una respuesta vacía, pero con ReAct una respuesta que
     pide una herramienta nunca está vacía, así que este caso no tiene equivalente exacto.
- **Validez de la petición forzada (invalida la llamada si falla):** el texto de CrewAI llega idéntico según
  la transcripción; mismo modelo, esfuerzo y razonamiento desactivado; sin bloques ajenos antepuestos; servidor
  conectado y mismas herramientas visibles; y toda herramienta pedida consta como denegada.
- **Contabilidad (corregida en D40).** En una sesión reanudada, `total_cost_usd`, `duration_api_ms` y `modelUsage` son
  **acumulados de la sesión**; `usage`, `num_turns` y `duration_ms` son solo de esa llamada (comprobado: la
  diferencia de costo coincide con los tokens de la petición forzada). `run_status.json` usa el acumulado para
  el costo y suma lo demás; si las cifras no cuadran, queda una observación.
- **Protección añadida de paso.** `write_result_to_json` escribe `result.json` dominio a dominio durante la
  Etapa 5. Si la corrida falla después de alguna escritura, ese archivo queda a medias: ahora se renombra a
  `result_parcial_de_corrida_fallida.json` para que nadie lo evalúe.
- **Pruebas sin cupo** (`scripts/test_pipeline_offline.py`, 183 comprobaciones, 0 problemas; 10 capturas):
  - Con la captura nueva, la réplica hace lo mismo que el original: mismas ejecuciones, mismo mensaje de
    usuario en todas, mismos archivos de salida, respuesta forzada en la misma etapa, y el texto enviado es el
    que el original añadió. La petición forzada lleva `--resume` con la sesión del agente, `--max-turns 1`,
    ningún `--allowedTools` y la misma configuración.
  - Límite en la fusión: la corrida termina y deja las salidas del original.
  - Respuesta forzada que pide una herramienta con texto: no se ejecuta, se toma el texto y pasa de contexto a
    la Etapa 5. Sin texto: corrida fallida. Error de la API en la petición forzada: corrida fallida y
    `result.json` parcial apartado.
- **Pruebas reales (2 llamadas, en `logs/fase4_prueba_humo/`):**
  - `comprobacion-respuesta-forzada/`: Etapa 1 de JPetStore con `--max-turns 3`. Primera llamada: 3
    peticiones, 9 llamadas a herramientas, `error_max_turns`. Petición forzada: **misma sesión**, 1 petición,
    `success`, 0 herramientas pedidas. El texto de CrewAI llegó idéntico, sin bloques antepuestos, en el mismo
    mensaje que los tres últimos resultados de herramientas; la forma de la petición (system y herramientas) no
    cambió y la caché se reutilizó. Respuesta: JSON válido con 4 dominios (`Account Management`, `Catalog
    Management`, `Shopping Cart`, `Order Management`), sin `Final Answer:`. Costo real USD 0,082; el
    `run_status.json` archivado dice 0,138 porque se escribió antes de corregir la contabilidad.
  - `comprobacion-denegacion-sin-allowedtools/`: una petición con la herramienta declarada y sin
    `--allowedTools`, pidiéndole al modelo que la use. Resultado: la llamada consta en `permission_denials`, el
    servidor ejecutó 0 llamadas y `claude` terminó con `error_max_turns`. USD 0,007.
- **Lo que no se ha verificado:** la respuesta forzada en las etapas 2 a 5 con el modelo real, y un caso real
  en el que el modelo pida herramientas dentro de una sesión reanudada (la denegación se comprobó en una
  sesión nueva con las mismas opciones).
- **Gasto de la Fase 4 en llamadas reales hasta aquí:** 7 llamadas, USD 0,48 nominales. Ninguna corrida
  completa.

### D40. Revisión independiente de D39 y correcciones (2026-11-17)
- **Quién y cómo:** un agente revisor, de solo lectura y sin llamar a `claude`, leyó el código de CrewAI 1.8.1
  y el de la réplica, comparó con la copia anterior al cambio, recalculó desde los archivos crudos las cifras
  de las dos llamadas reales de D39 e hizo 14 mutaciones sobre una copia completa del proyecto en una carpeta
  temporal (la borró al terminar). La revisión se cortó una vez por el límite de 5 horas del plan y se retomó
  donde había quedado.
- **Veredicto: aprobado con observaciones.** Sin hallazgos bloqueantes. Confirmó contra CrewAI: `max_iter`
  llamadas más una forzada; el texto es literalmente el de CrewAI; respuesta vacía → `ValueError`; una
  respuesta forzada que pide una acción se toma como respuesta final con su texto. Confirmó con los números
  crudos que costo, tiempo de API y `modelUsage` de la sesión reanudada son acumulados (la diferencia de costo
  coincide con los tokens de la petición forzada a las tarifas de Sonnet 4.6) y todas las cifras de D39 sobre
  las dos llamadas reales. Para las corridas que no llegan al límite, el comportamiento no cambió.
- **Hallazgos y qué se hizo:**
  1. **`turnos` no son peticiones** (medio). Con `error_max_turns`, `num_turns` vale peticiones + 1 (4 con 3
     peticiones); con `success`, llamadas a herramientas + 1 (20 con 7 peticiones). *Corregido:* cada etapa y
     los totales de `run_status.json` registran ahora `peticiones_api`, contadas por los identificadores de
     mensaje distintos del flujo (da 3 + 1 en la comprobación de D39 y 7 en la prueba de humo, igual que las
     transcripciones). `turnos` se mantiene como el dato que da Claude Code.
  2. **El costo se perdía si la petición forzada no devolvía resultado** (medio). *Corregido:* se toma el
     mayor de los acumulados disponibles, así que vale el de la primera llamada si la segunda no trae ninguno.
  3. **Las pruebas no cubrían la contabilidad ni la entrega de la petición forzada** (medio; 4 mutaciones
     sobrevivían). *Corregido:* el `claude` simulado cobra ahora por petición y devuelve costo, tiempo de API y
     `modelUsage` acumulados en la sesión reanudada, como el real; `analyze_forced` se prueba sobre la
     transcripción real archivada (texto idéntico y texto alterado); y hay un caso nuevo en el que la
     respuesta forzada pide una herramienta que no consta como denegada (la llamada queda inválida).
  4. **Tres frases de D29, D36 y D37 seguían diciendo que el límite de turnos deja la corrida fallida** (bajo).
     Corregidas como históricas.
  5. **Diferencia con el original sin declarar** (bajo): el original repite el último paso del agente antes del
     texto que pide la respuesta final. Añadida a D39 como diferencia 3.
  6. **El tiempo máximo vale por llamada** (bajo): anotado en D39.
  7. Sin cambios, por ser casos muy improbables y de efecto conservador: que una respuesta forzada termine en
     `error_max_turns` sin pedir herramientas, y que un fallo posterior a terminar la Etapa 5 aparte un
     `result.json` completo como parcial.
- **Resultado tras las correcciones:** prueba sin cupo completa (`scripts/test_pipeline_offline.py`, con el servidor
  MCP real) → **188 comprobaciones, 0 problemas**; `check_prompts.py` y `check_microagent_untouched.py` → OK.
  Mutaciones repetidas (las 4 que sobrevivían y 1 nueva sobre `peticiones_api`) → **5 de 5 detectadas**. Para
  que la del control de herramientas no denegadas se detecte por sí sola, el `claude` simulado pide en la
  respuesta forzada una herramienta del propio agente (antes pedía una ajena, que otra comprobación ya
  rechazaba). Sin llamadas reales nuevas.
- **Sigue sin verificar (D39):** la respuesta forzada en las etapas 2 a 5 con el modelo real; la denegación
  dentro de una sesión reanudada; una segunda llamada con `init` inválido o tiempo agotado (solo por lectura);
  y si las sesiones largas reanudadas se compactan (quedaría como observación).

### D41. Repetición aislada de la Etapa 4 para medir su variabilidad (2026-11-20, pedido de Jorge)
- **Motivo.** Las tres corridas completas de JPetStore (`claude-run1` a `claude-run3`) salieron idénticas hasta la
  Etapa 3 (mismos 4 dominios, misma fusión) y se separaron en la Etapa 4: WS 92,7 %, 72,6 % y 74,4 %. En run1 el
  Common Class Agent eligió solo `AbstractActionBean`; en run2 y run3 eligió además `CatalogService`, `Item`,
  `ItemMapper`, `Account` (y `Product` en run2), y `assign_common_class_list` propagó esas clases por
  dependencias a otros servicios. Las herramientas deterministas devolvieron lo mismo en las tres (mismo
  SHA-256 de `rank_dependency_entropy`) y el prompt contiene completo el `common_class_task` del original. Para
  separar el efecto del muestreo (Claude Code envía `temperature: 1`, D35; el original usa 0) del de las etapas
  previas, se repite solo la Etapa 4 con la entrada exacta de una corrida completa.
- **Qué se hizo:** `run_stage4.py` (nuevo; no se modificó ningún archivo existente, así que la huella
  `archivos_del_pipeline_sha256` de las corridas completas no cambia).
  - Subclase de `Pipeline`: hereda `prepare` (run_id nuevo, prefijo `_prueba-`, sandbox vacío, referencias,
    línea base de contexto) y usa `call_agent` y el bloque de main.py 340-395 tal como `run_pipeline.py`.
  - Lee del origen (`--desde`) `domain_clusters` (merged_domains.json con `Domain_Cluster` desenvuelto, o
    all_domains.json si no existe) y la respuesta final de la fusión como contexto si hubo fusión (D27).
  - Exige, antes de crear nada, que el mensaje de usuario y el system prompt reconstruidos sean idénticos byte a
    byte a los que recibió la Etapa 4 de origen, y que coincidan con el origen el contexto (D32), los SHA-256 de
    orquestador, prompts, herramientas y YAML del original, esfuerzo, `max_turns`, herramientas por agente,
    entorno de `claude` y la versión de Claude Code. Si algo difiere, aborta sin llamar a `claude`.
  - Copia `domains/` del origen (las herramientas leen `output/<app>/<run_id>/domains`) y comprueba sus SHA-256.
    Deja `logs/origen_etapa4.json` con todo lo comprobado. `run_status.json` lleva `estado: parcial_etapa4` y
    `solo_etapa4_desde`.
  - Nombre de las repeticiones: `claude-runN-e4-rNN`. No son corridas completas: no tienen Etapa 5 ni
    `result.json` y no se evalúan como descomposición final.
- **Segunda fuente de variabilidad, también en el original.** `get_more_potential_common_classes` y
  `assign_common_class_list` recorren `set`s de cadenas (custom_tools.py del original, p. ej. líneas 2314, 2452,
  2474, 2486-2487, 2574; la copia de la réplica es idéntica salvo los `import`). Su respuesta tiene el mismo
  contenido pero **otro orden** según la semilla de hash de cada proceso de Python: con `PYTHONHASHSEED` fijo se
  repite exacta; con 5 semillas salen 5 órdenes distintos. Si hubiera un ciclo de dependencias entre clases
  comunes, el orden podría cambiar también el contenido (`_topological_sort` completa con un `set`); con las
  entradas de JPetStore no ocurre. **No se fija la semilla**, porque el original no la fija; se registra si la
  sesión que lanza la repetición la tiene definida. Diferencia menor: en el original la semilla es una por
  proceso de main.py; en la réplica, una por servidor MCP (para una etapa sola el efecto es el mismo).
- **Lo que no se puede igualar:** la fecha y el contador de tokens restantes que Claude Code antepone o anexa
  (D35; el contador aparece también al final de cada respuesta de herramienta en la transcripción), y las
  variables de la sesión que lanza el proceso (hoy aparece `BUN_ENABLE_CRASH_REPORTING`, que no estaba en
  run1-run3; no afecta a lo que recibe el modelo). La carpeta de la repetición no tiene los logs de las etapas
  1-3; ninguna Etapa 4 de origen usó `search_file`, así que el agente no lo nota.
- **Uso:** una repetición a la vez (`_sandbox` es compartido; `prepare` lo impide):
  `python -X utf8 run_stage4.py --app jpetstore-6 --desde claude-run1 --run-id claude-run1-e4-r01`.
- **Prueba sin cupo:** `scripts/test_stage4_offline.py` (`claude` simulado, servidor MCP real en la Etapa 4) →
  **43 comprobaciones, 0 problemas** (logs/stage4_offline_test.txt): reconstrucción idéntica para run1, run2 y
  run3; con las escrituras del agente de run1, `common_result.json` idéntico al de origen; misma línea de
  comandos, entorno y configuración MCP; las 10 llamadas deterministas de la Etapa 4 de run1 repetidas sobre la
  carpeta nueva devuelven el mismo texto (las dos herramientas con `set`s, el mismo contenido); rechazos con
  su mensaje (origen inexistente, ya repetición, run_id usado, prompt alterado, otra configuración); origenes y
  archivos del orquestador intactos; sin residuos.
- **Sin verificar:** las ramas de fusión saltada, JSON de fusión inválido y `Domain_Cluster` (ninguna corrida
  real las tiene; si fallaran, la comparación byte a byte abortaría la repetición) y el camino de fallo a mitad
  de la llamada con escrituras parciales.

### D42. Revisión independiente de D41 y correcciones (2026-11-20)
- **Quién y cómo:** un agente revisor de solo lectura, sin llamar a `claude`, leyó `run_stage4.py`,
  `run_pipeline.py`, `build_prompts.py`, las dos `custom_tools.py` y main.py 259-395 del original, y ejecutó la
  prueba sin cupo.
- **Veredicto: apto con condiciones.** Sin hallazgos bloqueantes. Confirmó que el bloque de la Etapa 4 es el de
  `run_pipeline.py` y equivale a main.py 340-395, que la reconstrucción cubre todas las ramas de
  `run_pipeline.py`, que los orígenes solo se leen, y que el hallazgo de los `set`s es cierto en el original.
- **Corregido:** (I1) la repetición no comprobaba que orquestador, herramientas, configuración y versión de
  Claude Code fueran las del origen; ahora aborta si difieren. (I3) se matizó que el orden puede cambiar el
  contenido si hay ciclos, y se registra `PYTHONHASHSEED`. (M1) la copia de `domains/` se hace dentro del
  bloque protegido, así que un fallo deja la repetición como fallida y no "en_curso". (M2) un fallo después de
  guardar `common_result.json` ya no lo aparta como parcial. (T1) los rechazos se comprueban por su mensaje.
  (T4) se normaliza también "is depended on by" y se comprueba el número de llamadas. (T5) las copias de
  prueba se borran aunque la prueba aborte. Caso nuevo: origen hecho con otra configuración.
- **Sin cambios:** validar `--desde` contra rutas raras (solo se lee) y que el manifest no lleve el origen
  (está en `run_status.json`, `origen_etapa4.json` y `argv`).

### D43. Resultados: 5 repeticiones de la Etapa 4 con la entrada de `claude-run1` (2026-11-21)
- **Qué se corrió:** `run_stage4.py --desde claude-run1`, run_id `claude-run1-e4-r01` a `r05`, una tras otra. Las 5
  terminaron con `estado: parcial_etapa4`, sin fallos, sin límite de turnos y sin otras observaciones que
  `sin_etiqueta_final_answer`. Costo nominal total: USD 0,63 (entre 0,06 y 0,23 por repetición).
- **Resultados** (WS calculado con `json_similarity.py` del original sobre `common_result.json` contra
  `metrics/test/jpetstore_classes.json`; las repeticiones no tienen Etapa 5, y en las 3 corridas completas la
  Etapa 5 no cambió nada, así que el WS de `common_result.json` es el que habría tenido `result.json`):

  | Corrida | Candidatas probadas | Clases comunes asignadas | WS |
  |---|---|---|---|
  | claude-run1 (completa) | 2 | AbstractActionBean | 92,7 % |
  | e4-r01 | 4 | AbstractActionBean | 92,7 % |
  | e4-r02 | 6 | + CatalogService, Item, Account, Product | 76,4 % |
  | e4-r03 | 6 | + CatalogService | 86,3 % |
  | e4-r04 | 4 | + CatalogService | 86,3 % |
  | e4-r05 | 4 | AbstractActionBean | 92,7 % |
  | claude-run2 (completa) | 6 | + CatalogService, ItemMapper, Item, Account, Product | 72,6 % |
  | claude-run3 (completa) | 6 | + CatalogService, ItemMapper, Item, Account | 74,4 % |

  Promedio de las 5 repeticiones: 86,9 % (corregido en D55: con los valores sin redondear es **86,8 %**). En las 8 ejecuciones de la Etapa 4 (las tres corridas completas
  recibieron los mismos dominios, con otro orden de las listas; corregido en D57: el texto de la fusión que va como
  contexto también es distinto en cada corrida): 3 asignan solo `AbstractActionBean` (como la
  referencia), 2 añaden `CatalogService` y 3 añaden 4 o 5 clases de negocio. El F1 de clases comunes del
  original da 100 % en todas porque `common_dict.json` solo evalúa `AbstractActionBean`.
- **Conclusión:** con entrada idéntica byte a byte, mismo orquestador, herramientas, configuración y versión de
  Claude Code (D41), la Etapa 4 da tres resultados distintos. La variabilidad entre corridas completas no se
  debe a un error de la réplica, sino al muestreo (`temperature: 1`, D35) y al orden de las respuestas de dos
  herramientas del original (`PYTHONHASHSEED`, D41), amplificados por la propagación por dependencias de
  `assign_common_class_list`. Se reporta como amenaza a la validez con estas cifras. El error de
  `CartActionBean` es distinto: aparece en 3 de 3 corridas completas y nace en la Etapa 1 (dominio "Shopping
  Cart" propio).
- **El paper** no publica repeticiones ni dispersión; solo dice que fijó la temperatura en 0 para obtener
  resultados "lo más deterministas posible" (§4.1.3 y Threats to Validity). Su único dato por aplicación es la
  Figura 3: MicroAgent ≈ 93 % de WS en JPetStore (INSTRUCCIONES §9.3). `MicroAgent/decomposition/jpetstore.json`
  no es el resultado de MicroAgent sino la referencia (idéntica a `metrics/test/jpetstore_classes.json`; §9.1).
  Frente a ese ≈ 93 %, claude-run1 (92,7 %) coincide y la media de las corridas queda por debajo.

### D44. Resultados: 3 corridas completas de MicroAgent en PartsUnlimitedMRP (2026-11-21)
- **Qué se corrió:** `run_pipeline.py --app partsunlimited`, run_id `claude-run1` a `claude-run3`, una tras otra. Las
  3 terminaron con `estado: completa`, **5 dominios** en la Etapa 1, **fusión saltada** (`fusion: saltada`, porque
  `len(all_domain_results) == 5`) y **53/53 clases asignadas** en `result.json` (las 53 claves de
  `class_summaries.json`, ninguna desconocida). Sin fallos y sin límite de turnos; la única observación, en las 8
  llamadas de cada corrida, es `sin_etiqueta_final_answer`.
- **Resultados** (WS y c2c con `json_similarity.py` del original contra la referencia `MicroAgent/decomposition/partsunlimited.json`, la que §9.1 copia en `evaluation/references/`, todavía vacía por D23; recalculado el 2026-11-21 con el mismo resultado):

  | Corrida | WS | c2c@50 / @75 / @90 | Costo nominal |
  |---|---|---|---|
  | claude-run1 | 100,00 % | 100 / 100 / 100 % | USD 1,68 |
  | claude-run2 | 97,40 % | 100 / 100 / 100 % | USD 1,35 |
  | claude-run3 | 100,00 % | 100 / 100 / 100 % | USD 1,63 |

  Media de WS: **99,13 %**, desviación estándar muestral **1,50** puntos. Frente al ≈ 100 % de la Figura 3 del paper
  (§9.3), coincide. Costo nominal total: USD 4,66 (lo que `claude` informa en `total_cost_usd`; el plan Pro no
  cobra por llamada).
- **De dónde viene la diferencia de run2.** Comparando las particiones por su contenido (los nombres de los dominios
  cambian de una corrida a otra: "Product Catalog" / "Catalog", "Shipment and Delivery" / "Shipment" /
  "Shipment Management"):
  - `domains/all_domains.json` y `domains/merged_domains.json` tienen **el mismo contenido en las 3 corridas**
    (y, dentro de cada corrida, son iguales entre sí porque la fusión se saltó). Las Etapas 1 a 3 no divergen.
  - La divergencia **nace en la Etapa 4** (`common_result.json`): run1 y run3 son iguales; run2 añade
    `smpl.ordering.BadRequestException` a Catalog y a Dealer y, además, no asigna `smpl.ordering.PostgresqlProperties`
    a ninguno de los 5 servicios (run1 y run3 la ponen en los 5).
  - La Etapa 5 de run2 añade `PostgresqlProperties` a los 5 servicios, así que en `result.json` la única
    diferencia con run1/run3 es **`BadRequestException` de más en Catalog y Dealer**, que es lo que baja el WS a
    97,40 %. Es el mismo patrón que D43 midió en JPetStore: la variabilidad se concentra en la Etapa 4.
- **Observación revisada: "turnos" por encima de `max_turns` en la Etapa 1.** `run_status.json` muestra en
  `1_domain` `turnos` 44/30, 23/30 y 52/30 sin `limite_de_turnos`. Se averiguó sin gastar cupo, leyendo
  `logs/1_domain_claude.json`, `1_domain_stream.jsonl`, `1_domain_transcript.jsonl` y `run_pipeline.py`:
  - `turnos` es el campo `num_turns` que devuelve Claude Code, copiado tal cual (`call_agent`, clave `"turnos"`).
    En una llamada que termina con `success` vale **llamadas a herramientas + 1**: 43 + 1, 22 + 1 y 51 + 1.
  - `--max-turns 30` (presente en `_cmd` de las 3) limita **peticiones a la API**, no llamadas a herramientas
    (D38, D40). Las peticiones fueron **10, 6 y 12**, contadas de dos formas que coinciden: identificadores de
    mensaje de asistente distintos en el flujo y eventos `api-request` de la transcripción.
  - El Domain Agent pide hasta 5 herramientas en paralelo por petición (run1: 3, 5, 5, 5, 5, 5, 5, 5, 5 y 0; casi
    todas `get_class_summary`), por eso hace 43 llamadas en 10 peticiones. **No hubo límite alcanzado** y no hay
    error en el orquestador; el campo que hay que comparar con `max_turns` es `peticiones_api`, no `turnos`
    (ya lo decían D33 y D40). Para la tabla de §9.5 ("turnos totales") se informarán las dos columnas con su
    definición.

---

## Fase 5 — Línea base "LLM base" zero-shot (`run_baseline.py`)

### D45. Prompt reconstruido de la línea base (2026-11-21, decisiones de Jorge)
- **Original:** el paper (§4.1.2) solo dice que al LLM base se le dan el código original, los scripts de base de
  datos y el número objetivo de microservicios, en *zero-shot*. **El artefacto no incluye ese prompt** (no hay
  nada sobre *baseline* ni *zero-shot* en `MicroAgent/`), así que se reconstruyó según §8.
- **Llamada:** una sola `claude -p` por corrida, **sin herramientas**, con la misma configuración efectiva que el
  orquestador (D35, D38): `--model claude-sonnet-4-6 --effort high --system-prompt "" --tools "" --strict-mcp-config
  --disable-slash-commands --setting-sources "" --max-turns 1 --output-format stream-json --verbose`, cwd `_sandbox/`
  vacío, prompt por stdin y el mismo entorno limpio (`child_env()` de `run_pipeline.py`: se quitan las variables
  heredadas y se fijan `PIPELINE_ENV`, `MAX_THINKING_TOKENS=0` y las dos de MCP, que aquí no tienen efecto). Solo
  faltan `--mcp-config` y `--allowedTools`, que no aplican.
- **System prompt (pregunta de Jorge):** `--system-prompt ""`. Sustituye el system prompt por defecto de Claude Code
  (que trae sus propias instrucciones) y deja solo el bloque fijo de 62 caracteres (`You are a Claude agent, built on
  Anthropic's Claude Agent SDK.`), que no se puede quitar (D4). Es lo más neutro que permite la CLI y lo mismo que
  en las 54 llamadas de la Fase 1. Se comprobó en la transcripción del resumen de BD de PartsUnlimitedMRP: un único
  bloque de system, `tools: []`, `thinking: disabled` y una petición. MicroAgent recibe `role_playing` (D28) porque
  es lo que manda CrewAI; la línea base no tiene agente, así que no se le inventa un rol.
- **Texto del prompt** (en inglés, sin ejemplos). `{n}` = 3 (JPetStore) o 5 (PartsUnlimitedMRP); las partes se unen
  con una línea en blanco:
  ````
  Below is the source code of the classes of a monolithic Java application, together with its database schema. Your task is to decompose this application into exactly {n} microservices.

  ## Database schema

  File: {ruta del esquema}
  ```sql
  {esquema crudo}
  ```

  ## Source code
  The application consists of the following {k} classes.

  ### {FQCN}
  File: {file_path}
  ```java
  {código del .java}
  ```
  ... (una sección por clase)

  ## Task
  Decompose the application above into exactly {n} microservices. Assign classes to microservices by their fully qualified class names. A class that is shared by several microservices may appear in more than one microservice.

  Return ONLY a JSON object, with no other text, in the following format:
  {"<ServiceName>": ["<fully.qualified.ClassName>", ...]}
  ````
  El formato de salida es **literalmente el de §8** e incluye la frase de §8 sobre las clases compartidas. Son las
  constantes `INTRO` y `TASK` de `run_baseline.py`.
- **Decisiones de Jorge sobre los puntos dudosos (2026-11-21):**
  1. *Orden de las clases:* el de las claves de `context/<app>/class_summaries.json`. Es determinista y es el orden del
     contexto que ve MicroAgent; uno aleatorio metería una fuente de variación que MicroAgent no tiene. La huella del
     contexto (D32) impide que `class_summaries.json` cambie entre corridas.
  2. *Ruta:* `file_path` tal cual (`resources/<app>/src/...`). Jorge pidió esta opción solo si el artefacto usa
     exactamente ese formato. **Se comprobó** que `MicroAgent/microagent/context/test/class_summaries.json` tiene las
     mismas 24 claves que el de la réplica, en el mismo orden y con el mismo `file_path`
     (`resources/jpetstore-6/src/main/java/...`). El prefijo `resources/<app>/` es del artefacto, no del repositorio
     de la aplicación.
  3. *Extracción del JSON:* `clean_json_output` (copia literal de `main.py` 21-46, la misma que se aplica a la
     salida de los agentes de MicroAgent) y `json.loads`. Así la línea base se trata exactamente igual que MicroAgent.
     Una respuesta que no da un objeto `{str: [str]}` es una **corrida fallida** y se repite con otro `run_id` (§10.4).
  4. *Clases que faltan o sobran, o número de servicios ≠ n:* no se corrige nada (D46). Las métricas del original ya
     penalizan esos errores, y medirlos es para lo que sirve la línea base; MicroAgent llega a n por su etapa de fusión.
  5. *¿Exigir que se asignen todas las clases?* No: ni el paper ni §8 lo dicen. Para que en el reporte se puedan
     separar las clases **omitidas** de las **mal asignadas**, `run_status.json` registra `clases_sin_asignar` (D46).
  6. *Posición de la instrucción y licencias:* una frase al inicio y la tarea completa al final (lo recomendado para
     contextos largos). El código va **tal cual, con las cabeceras de licencia** ("código original" = sin preprocesar).
- **Qué archivos entran (pregunta de Jorge):** solo las clases Java del universo (las 24 y 53 claves de
  `class_summaries.json`) más el esquema crudo. Quedan fuera:
  - los mapeadores XML de MyBatis y los JSP de JPetStore;
  - los `.java` que no son del universo (D6, D9: `src/test/java` e `IntegrationService` de PartsUnlimitedMRP);
  - los datos de ejemplo (`jpetstore-hsqldb-dataload.sql`, `MongoRecords.js`).

  Es lo simétrico con MicroAgent, cuyas herramientas solo devuelven código Java y el resumen de BD, y es lo que dice §8
  ("las claves de `class_summaries.json`, con su ruta"). **Amenaza a la validez:** alguien podría objetar que "el
  código original" incluye los XML y los JSP; en JPetStore, los XML de MyBatis contienen el SQL de cada mapeador. Se
  reportará.
- **Esquemas crudos:**
  - JPetStore → `resources/jpetstore-6/src/main/resources/database/jpetstore-hsqldb-schema.sql`, el DDL del clon. El
    `sql-summary.json` de los autores cita `sql_schemas/schema.sql`, que no está en el artefacto.
  - PartsUnlimitedMRP → `resources/partsunlimited/src/Backend/OrderService/scripts/schema.psql`, el mismo de D11.
- **Saltos de línea:** los 77 `.java` del universo y los dos esquemas tienen CRLF en disco. Se leen en modo texto,
  igual que hacen las herramientas del original, así que llegan al prompt con LF. `run_manifest.json` guarda, por
  archivo, el sha256 de los bytes en disco y el del texto enviado.
- **Tamaño y huella del prompt** (`run_baseline.py --solo-prompt`, sin llamar al modelo):

  | App | Clases | Caracteres (= bytes UTF-8) | Tokens estimados | sha256 |
  |---|---|---|---|---|
  | jpetstore-6 | 24 | 73 851 | ≈ 20 000 | `4aa7c961a464e9e406167b15b0d1b82d66c5f9da2e19b9539d771fe5eca79312` |
  | partsunlimited | 53 | 171 341 | ≈ 46 000 | `31230f37abefba161a9119c8f611901224a68ef1569c0f1448e5e1195352f1ab` |

  Los tokens se estimaron con la relación de las 54 llamadas de la Fase 1 (≈ 3,8 caracteres por token, más unos 530
  fijos). Caben de sobra en la ventana del modelo. La primera corrida real de cada app guarda la huella en
  `logs/baseline_prompt_fingerprint/<app>.json`, y las siguientes abortan si el prompt cambió.

### D46. `run_baseline.py`: salida, validación y registro (2026-11-21)
- **Archivos** en `output/<app>/<run_id>/`: `result.json` y, en `logs/`:
  - `baseline_prompt.txt` (bytes exactos enviados);
  - `baseline_stream.jsonl`;
  - `baseline_claude.json` (evento final: modelo, tokens y costo, más la línea de comandos y los nombres del entorno);
  - `baseline_raw.txt` (respuesta cruda);
  - `baseline_transcript.jsonl`, `baseline_audit.json` y `baseline_stderr.txt`;
  - `run_manifest.json`, `run_status.json` y `baseline.log`.
- **`run_status.json` comparable al del orquestador:**
  - Tiene las mismas claves (`num`, `solo_etapa1: false`, `fusion: "no_aplica"`, `etapas`, `observaciones` y
    `totales`, con `turnos`, `peticiones_api`, `costo_usd`, `tokens`...), más `configuracion: "baseline"`.
  - La entrada de la etapa trae las mismas claves que las de los agentes (`herramientas_usadas: {}`,
    `etiqueta_final_answer: null`, `limite_de_turnos: false`) y además `stop_reason`.
  - `resultado` usa las definiciones de `_result_stats`: `clases_distintas_asignadas` cuenta todas las distintas,
    incluidas las desconocidas, y `clases_sin_asignar` va en orden alfabético. Añade `clases_del_universo_asignadas`,
    `particiones_igual_a_n`, `clases_en_varios_servicios`, `repetidas_dentro_de_un_servicio` y
    `servicio_llamado_uncounted` (`json_similarity.py` ignora esa clave del objetivo).
- **Nada se corrige.** `result.json` es el objeto que da `json.loads(clean_json_output(respuesta))`, escrito con
  `json.dump(..., indent=2)` como en `main.py`. Se registran como observaciones, sin invalidar la corrida:
  - texto o cercas de código alrededor del JSON;
  - un número de servicios distinto de n;
  - clases sin asignar, desconocidas o repetidas;
  - servicios con el mismo nombre (`json.loads` se queda con la última aparición, como en `main.py`; las listas
    perdidas quedan anotadas).
- **Corrida fallida (§10.4)** si ocurre cualquiera de estas cosas:
  - el JSON no es válido o no es `{str: [str]}`;
  - `claude` no devuelve resultado, devuelve error (incluido el 429 del cupo) o sale con un código distinto de 0;
  - se agota el tiempo (`--timeout`, 1 800 s por defecto);
  - el `init` trae herramientas o servidores MCP (se corta en ese momento, sin pagar la llamada);
  - la auditoría del flujo encuentra un modelo distinto, bloques de razonamiento, herramientas pedidas, más de una
    petición o una versión de Claude Code distinta de la de `--version`;
  - la auditoría de la transcripción encuentra un system distinto del bloque fijo, `<system-reminder>` distintos de
    los 5 de siempre, un prompt que no es idéntico, herramientas en la petición, razonamiento, otro `effort` u otro
    modelo, o más de una petición;
  - en una corrida real, **no hay transcripción legible**, porque es la única prueba de lo que recibió la API.
- **Protecciones:**
  - se niega a usar un `run_id` cuya carpeta exista, aunque esté vacía;
  - una corrida real debe llamarse `baseline-...`, usar `claude-sonnet-4-6` y tener la huella del contexto de las
    corridas de MicroAgent (D32);
  - el prefijo `_prueba-` es obligatorio y exclusivo de las corridas simuladas, que además pueden escribir fuera de
    `output/` (`BASELINE_OUTPUT_ROOT`);
  - `--solo-prompt` solo escribe fuera de `Replica de Paper/`;
  - si algo falla después de crear la carpeta (incluido `claude --version`), queda en `run_status.json`.
- **Prueba sin cupo:** `python -B -X utf8 scripts/test_baseline_offline.py` con `scripts/fake_claude_baseline.py`.
  El simulador escribe una transcripción sintética en un `CLAUDE_CONFIG_DIR` temporal y registra su línea de comandos
  y su entorno. La prueba recorre 27 escenarios por app: respuestas válidas, con cercas, con texto alrededor, con
  clases faltantes, con n distinto, con claves repetidas, inválidas o cortadas, errores de `claude`, tiempo agotado,
  corte temprano y 8 mutaciones de la transcripción. Además compara:
  - la línea de comandos, el cwd y el entorno de `claude` con valores escritos a mano (con variables heredadas puestas
    a propósito para comprobar que se quitan);
  - el sha256 del prompt;
  - la negativa a sobrescribir y los rechazos.

  Resultado: **71 comprobaciones, RESULTADO: OK**, y `output/` sin cambios (las corridas simuladas van a una carpeta
  temporal que se borra al terminar).
- **Lo que no se puede probar sin cupo:** la regla "corrida real sin transcripción → fallo" (en simulación solo es
  una observación) y la forma exacta del `init` de `stream-json` sin servidores MCP. Si esa forma trajera algo
  inesperado, la primera corrida fallaría por auditoría sin dar un resultado dudoso; el efecto es conservador.

### D47. Revisión independiente de la Fase 5 y correcciones (2026-11-21)
- Un agente revisor de solo lectura comparó la implementación con §8, §10, §11 y con el orquestador. Ejecutó solo la
  prueba sin cupo y `--solo-prompt` (y, por descuido, un `python -c "print(1)"` inocuo); no llamó a `claude`.
  Confirmó que se cumplen las ocho decisiones de D45 y que la configuración de la CLI es la del orquestador.
- **Hallazgos y qué se hizo** (todos corregidos, salvo donde se indica):
  1. *Claves repetidas en el JSON* (medio): un servicio con nombre repetido se perdía sin registro. → Observación
     `servicios_con_nombre_repetido` con las listas; `result.json` no cambia (igual que en `main.py`).
  2. *Sin transcripción, nada comprobaba el system, el effort ni el prompt* (medio). → En corridas reales es un problema
     que invalida la llamada.
  3. *La prueba no recorría la auditoría de la transcripción ni varios fallos* (medio). → Transcripción sintética y 15
     escenarios nuevos (D46).
  4. *La prueba no comparaba la configuración con valores fijos* (medio; es el mismo fallo que D38 corrigió en el
     orquestador). → El simulador registra argv, cwd y entorno, y la prueba los compara con valores escritos a mano.
  5. *Faltaba registrar el prompt* (medio). → D45 y D46.
  6. *Nada aseguraba el mismo prompt en las 3 corridas*, porque el esquema queda fuera de la huella D32 (medio). →
     sha256 fijo en la prueba y huella en `logs/baseline_prompt_fingerprint/<app>.json`.
  7. *Estadísticas y claves no comparables con las del orquestador* (bajo-medio). → Mismas definiciones y claves.
  8. *`--solo-prompt` podía escribir en `context/<app>/` o en `../MicroAgent/`* (bajo-medio). → Solo escribe fuera de
     `Replica de Paper/`; la prueba lo comprueba con `context/<app>/`.
  9. *Saltos de línea* (bajo). → Se guardan el sha256 de disco y el del texto, y se corrigió el docstring (D45).
  10. *No había corte temprano al ver el `init`* (bajo). → Se corta si trae herramientas o MCP; además, se hace
      `flush` en cada línea.
  11. *No se registraba `stop_reason`* (bajo). → Va en la entrada y en la auditoría, y como observación si no es
      `end_turn`.
  12. *`--model` aceptaba cualquier valor en corridas reales* (bajo). → Ahora solo `claude-sonnet-4-6`. El orquestador
      sigue aceptando otro valor; no se tocó porque ya hizo las 6 corridas.
  13. *Redacción del prompt* (bajo): "Below are the complete source code..." tenía un error de concordancia y decía
      "complete" aunque no van todos los archivos, y el formato añadía `, ...` al de §8. → Se cambió a "Below is the
      source code of the classes of a monolithic Java application, together with its database schema.", y el formato
      quedó literalmente el de §8. **Es un cambio respecto del borrador que vio Jorge**; se le informa (texto final
      en D45).
  14. *Un fallo después de crear `logs/` quedaba sin registro* (bajo). → `run_status.json` se escribe al crear la
      carpeta, y el resto de la preparación queda dentro del manejo de fallos.
  15. *La forma del `init` sin MCP no se ha observado* (sospecha). → Queda anotada en D46; se verá en la primera corrida.
  16. *`repetidas_dentro_de_un_servicio` aparecía en dos escenarios del simulador* (artefacto del simulador). →
      Corregido el simulador.

### D48. Resultados: 6 corridas de la línea base (2026-11-21, confirmadas por Jorge)
- **Qué se corrió:** `run_baseline.py`, run_id `baseline-run1` a `baseline-run3` en JPetStore y después en
  PartsUnlimitedMRP, una tras otra, con el comando acordado. Las 6 terminaron con `estado: completa`. Cada una hizo
  **1 petición**, la auditoría salió sin problemas y respondió `claude-sonnet-4-6`. El `init` no traía herramientas ni
  servidores MCP (se cierra la sospecha 15 de D47). La transcripción fue legible y el prompt llegó idéntico. El system
  fue solo el bloque fijo de 62 caracteres, con los 5 `<system-reminder>` de siempre (954, 167, 86, 650 y 65
  caracteres, los mismos que en las corridas de MicroAgent). Parámetros: `max_tokens 32000`, `thinking: disabled`,
  `temperature: 1`, `effort: high`. La primera corrida de cada app guardó la huella del prompt y las otras dos
  coincidieron. Única observación en las 6: `json_entre_cercas_de_codigo` (el modelo devolvió el JSON entre
  ```` ```json ```` y ```` ``` ````; `clean_json_output` quitó 12 caracteres).
- **Resultados.** WS y c2c con `json_similarity.py` del original (método 2). La referencia es
  `MicroAgent/decomposition/<app>.json`, la misma que §9.1 copia en `evaluation/references/`, que sigue vacía hasta la
  Fase 6 (D23). Control de cordura: referencia contra sí misma = 1,0.

  | App | Corrida | WS | c2c@50 / @75 / @90 | Clases asignadas | Costo nominal |
  |---|---|---|---|---|---|
  | JPetStore | baseline-run1 | 84,20 % | 100 / 100 / 33,3 % | 24/24 | USD 0,143 |
  | JPetStore | baseline-run2 | 84,20 % | 100 / 100 / 33,3 % | 24/24 | USD 0,016 |
  | JPetStore | baseline-run3 | 84,20 % | 100 / 100 / 33,3 % | 24/24 | USD 0,016 |
  | PartsUnlimitedMRP | baseline-run1 | 67,15 % | 80 / 40 / 0 % | 53/53 | USD 0,316 |
  | PartsUnlimitedMRP | baseline-run2 | 66,44 % | 100 / 40 / 0 % | 53/53 | USD 0,048 |
  | PartsUnlimitedMRP | baseline-run3 | 66,13 % | 80 / 40 / 0 % | 53/53 | USD 0,048 |

  - JPetStore: media de WS 84,20 %, desviación estándar muestral 0,00.
  - PartsUnlimitedMRP: media de WS 66,58 %, desviación estándar muestral 0,52.
  - Costo nominal total: USD 0,59 (lo estimado eran USD 0,9 a 1,5).
- **Lo que hizo el modelo base:**
  - Siempre devolvió exactamente n servicios y asignó todas las clases (`clases_sin_asignar` vacía en las 6). En
    estas corridas no hubo clases omitidas: todos los errores son de asignación.
  - En JPetStore, las 3 respuestas son la misma partición (Account / Catalog / Order). Tiene 6 clases compartidas, y
    `AbstractActionBean` está en los 3 servicios.
  - En PartsUnlimitedMRP, las 3 particiones difieren un poco entre sí. En las tres, el modelo pone en los 5 servicios
    13 clases de configuración o utilidad: `AppInsightsFilter`, `OrderingConfiguration`, `PropertyHelper`,
    `PingController`, `MongoOperationsWithRetry`, las de propiedades y las 8 comunes de la referencia. Además reparte
    varios modelos y repositorios entre 2 a 4 servicios. Eso infla los servicios (de 21 a 44 clases) y es lo que baja
    el c2c@75/@90.
- **Comparación con el paper (Figura 3, §9.3) y con MicroAgent:**
  - JPetStore:
    - Línea base: 84,2 % (paper ≈ 81,5 %).
    - MicroAgent: media de las 3 corridas completas 79,9 % (92,7 / 72,6 / 74,4 %, D43; paper ≈ 93 %).
    - **En la réplica, la línea base supera a la media de MicroAgent en JPetStore**, aunque no a su mejor corrida. La
      dispersión de MicroAgent viene de la Etapa 4 (D43).
  - PartsUnlimitedMRP:
    - Línea base: 66,6 % (paper ≈ 79,5 %).
    - MicroAgent: 99,1 % (D44; paper ≈ 100 %).
    - Ventaja de MicroAgent: unos 32,5 puntos.
- **Caché de prompts:** las corridas 2 y 3 de cada app leyeron de la caché de la API el prompt que escribió la
  primera (`cache_read_input_tokens` 22 400 y 47 214, frente a `cache_creation_input_tokens` en la corrida 1). Por eso
  cuestan menos. La caché no cambia lo que recibe el modelo ni el muestreo: el prompt fue idéntico byte a byte (lo
  dice la auditoría) y `temperature` siguió en 1. Que JPetStore diera 3 respuestas iguales es, entonces, un resultado
  del muestreo con este prompt y no un efecto de la caché. Las llamadas de MicroAgent también usan caché entre
  peticiones de una misma sesión.
- **Versión de Claude Code:** las 6 corridas de la línea base usaron **2.1.330**; las 6 corridas completas de
  MicroAgent y las 5 repeticiones de la Etapa 4 usaron **2.1.327** (D58: claude-run4 a run10 de JPetStore usaron
  2.1.330) (`run_manifest.json`, del 2026-11-20 y el
  2026-11-21); la Fase 1 y las pruebas de humo usaron 2.1.325. `DISABLE_AUTOUPDATER=1` solo afecta a los procesos
  `claude` que lanza la réplica; la instalación del usuario se actualizó entre sesiones. Lo que llega a la API fue igual
  en las dos versiones: mismo bloque de system, mismos 5 `<system-reminder>` con los mismos tamaños y mismos
  parámetros de muestreo. Se reporta como desviación menor de §10.1 (una sola configuración); el modelo y las opciones
  no cambiaron.
- **`stop_reason`:** la entrada de `run_status.json` dice `stop_reason: null`. En `stream-json`, Claude Code envía los
  mensajes de asistente con `stop_reason` vacío; el valor real está en el evento final (`baseline_claude.json`) y en
  la transcripción: **`end_turn` en las 6**, así que ninguna respuesta quedó cortada. El script no se cambió después
  de las corridas, para que las 6 se hicieran con el mismo código; si hubiera que repetir alguna, conviene tomar
  `stop_reason` del evento `result`.

---

## Fase 6 — Evaluación con los scripts originales (`evaluation/`)

### D49. Referencias copiadas byte a byte (2026-11-22)
- §9.1: `MicroAgent/decomposition/jpetstore.json` → `evaluation/references/jpetstore-6.json` y
  `MicroAgent/decomposition/partsunlimited.json` → `evaluation/references/partsunlimited.json`, con `cp -p`; `cmp` sin
  diferencias. D23 se cumplió: se copiaron después de terminar las 12 corridas.

  | Archivo | sha256 |
  |---|---|
  | `references/jpetstore-6.json` (= `metrics/test/jpetstore_classes.json`) | `2b4227de0b0b30cd2dcbeae403d85b4394bf5050a83dd56f78466e719e502c46` |
  | `references/partsunlimited.json` | `63ce4f58b6012afcae1d92ff6d26782b2d6292669ed5b37c441afcc7fd482432` |
  | `common_dicts/jpetstore-6.json` (copia de `metrics/test/common_dict.json`) | `84d6ee09ce8d88775b9b8686e3e7844d60f3f22a4870985548b1b82f35944c67` |
  | `common_dicts/partsunlimited.json` (**reconstruido**, D50) | `8d370d36fd967e71d16e3c7ffdafa8a828b99322708fcc01e7a3bc0e83eeabdd` |

- Qué publica el artefacto (se revisaron todos sus JSON fuera de `target/`):
  - las **10 referencias** en `decomposition/`, cuyo número de particiones coincide con la Tabla 2 del paper;
  - **ninguna salida de MicroAgent**, de ninguna app;
  - un solo `common_dict`, el de JPetStore.

  El README menciona `metrics/reference_results/` y `metrics/experiment_results/`, que no están en el artefacto.

### D50. `common_dict` de PartsUnlimitedMRP reconstruido; control con JPetStore (2026-11-22, decisión de Jorge)
- **Qué dice el original.** El paper (§4.1.4, "Common Class Assignment Metrics") define la asignación de referencia:
  un servicio *s* debe contener la clase común *c* si *s* incluye alguna clase que dependa de *c*. **No dice**:
  - cómo se elige el conjunto de clases comunes;
  - si "depende" sale del grafo estático o de una revisión manual;
  - qué hacer con una clase común sin dependientes.

  El artefacto no trae ningún script para construir el diccionario.
- **Regla aplicada** (§9.2, `evaluation/build_common_dict.py`):
  - clases comunes: las que aparecen en más de una partición de la referencia (sin contar `uncounted`);
  - valores: las clases con una relación **directa** hacia la clase común en `context/<app>/class_info_dependency.json`,
    con los tipos de `VALID_RELATIONSHIP_TYPES` (copia literal de `custom_tools.py`, líneas 20-32).
- **Control con JPetStore: coincide.** Sale una sola clase común, `AbstractActionBean`, con `{AccountActionBean,
  OrderActionBean, CartActionBean, CatalogActionBean}`, todas por `EXTENDS`. Es el mismo conjunto que el diccionario
  publicado; solo cambia el orden de la lista, y `calculate_metrics` la trata como conjunto. Con las relaciones inversas
  (`EXTENDED_BY` de la clase común) sale lo mismo.
- **Límite del control:** en JPetStore los dependientes directos y los transitivos coinciden, así que el control no
  distingue entre las dos lecturas. En PartsUnlimitedMRP sí difieren: con transitivos, 6 de las 8 clases tendrían entre
  33 y 35 dependientes. Se usan los directos, como dice §9.2.
- **PartsUnlimitedMRP.** Salen exactamente las 8 clases de §9.2. En 7 de ellas, la asignación ideal que da la regla es
  igual a la de la referencia. El problema es **`SimpleCORSFilter`, que no tiene ninguna relación** en el grafo: es un
  `@Component` que implementa `javax.servlet.Filter` y Spring lo registra solo. Con la lista vacía, su asignación ideal
  no tendría ningún servicio, y la referencia contra sí misma daría F1 de servicio 0,923 (micro) y 0,922 (macro), con 5
  falsos positivos.
- **Opciones presentadas a Jorge, con su efecto en el F1 de servicio (micro):**

  | Opción | Referencia | claude-run1/3 | claude-run2 | baseline 1-3 |
  |---|---|---|---|---|
  | A. Quitarla (7 clases) | 1,000 | 1,000 | 0,968 | 0,955 |
  | B. 8 clases, con su lista vacía (regla literal) | 0,923 | 0,923 | 0,896 | 0,889 |
  | C. 8 clases, con los 5 controladores puestos a mano | 1,000 | 1,000 | 0,972 | 0,961 |

- **Decisión de Jorge (2026-11-22): opción A.**
  - `evaluation/common_dicts/partsunlimited.json` tiene **7 clases comunes** y se registra como **reconstruido**.
  - Es una desviación de §9.2 ("son 8") y se reportará como amenaza a la validez.
  - `build_common_dict.py --check` comprueba que el archivo sigue la regla y que la regla reproduce el diccionario de
    JPetStore.
- **Observaciones que no cambian nada:**
  - `Utility` y `OrderingConfiguration` dependen la una de la otra (`CALLS` en los dos sentidos).
  - La lista de `Utility` incluye 3 clases `uncounted` (`AppInsightsFilter`, `PingController`,
    `MongoOperationsWithRetry`). Se comprobó que quitarlas no cambia el F1 de ninguna de las 6 corridas.
- **En las corridas**, `SimpleCORSFilter` quedó en los 5 servicios en las 6 descomposiciones, igual que en la
  referencia. En MicroAgent ningún Clustering Agent la asignó (está en 0 de 5 dominios en `all_domains.json`). La puso
  en los 5 el Common Class Agent, y no por propagación, porque no tiene dependientes.

### D51. `evaluation/evaluate.py` (2026-11-22)
- **Uso de los scripts originales.**
  - Importa `evaluate_similarity` (`json_similarity.py`) y `calculate_metrics` (`common_metrics.py`) sin modificarlos y
    sin usar sus `__main__`.
  - Pone `sys.dont_write_bytecode = True` y se corre con `python -B -X utf8`; en `MicroAgent/metrics/` no quedó
    `__pycache__`.
  - `json_similarity` no imprime ni escribe. `calculate_metrics` imprime los FP/FN por stdout: se capturan con
    `redirect_stdout` y se guardan en `evaluation/raw/<app>/<run_id>_common_metrics_stdout.txt`. Ninguno de los dos
    escribe archivos.
  - `json_similarity` abre los JSON con la codificación por defecto. Las referencias y los 17 objetivos son ASCII, así
    que da igual (y `-X utf8` la fija de todos modos).
- **Correspondencia con el paper:**
  - WS = `f1.metrics_m2.weighted_average`.
  - c2c@50/75/90 = `f1.metrics_m2.above_0.5/0.75/0.9` (ver D52).
  - F1 de clases comunes = `calculate_metrics(...)["service_level"]`, micro y macro (ver D53). El nivel por clase
    (`utility_level`) queda en `raw/`.
- **Control de cordura.** Las dos referencias contra sí mismas dan 1,0 en todos los valores: `f1.metrics_m1`,
  `f1.metrics_m2` y los de `calculate_metrics` (servicio y clase, micro y macro). Está en `evaluation/sanity_check.json`,
  con `resultado: OK`. A `calculate_metrics` se le pasa la referencia sin la clave `uncounted`, porque no es un servicio:
  `json_similarity` la ignora, pero `calculate_metrics` la trataría como un servicio más (y en PartsUnlimitedMRP contiene
  dependientes de `Utility`). Lo mismo se hace con los objetivos (D55, hallazgo 1).
- **Control contra los valores calculados a mano en D43, D44 y D48:** los 17 coinciden. Si alguno no coincidiera, el
  script abortaría sin escribir `results.csv`.
- **Salidas:**
  - `results.csv`: las 12 corridas más la media y la desviación estándar muestral por app y configuración.
  - `results_e4_repeticiones.csv`: las 5 repeticiones de la Etapa 4, aparte.
  - `sanity_check.json`.
  - `raw/<app>/<run_id>.json`: la salida completa de los dos scripts.
  - `raw/notas_de_coherencia.txt`: vacío.
  - `error_analysis.json` y `error_analysis.md` (ver D56).
- **Fuera de la tabla:**
  - `smoke-test`: prueba de humo, solo con la Etapa 1.
  - `claude-run1-e4-r01..r05`: se evalúan sobre `common_result.json` porque no tienen Etapa 5 (D41, D43). En las 3
    corridas completas de JPetStore la Etapa 5 no cambió nada, así que ese WS es comparable (D43), pero no entra en las
    medias.

### D52. c2c: el script usa `>` y el paper dice `≥` (2026-11-22)
- `calculate_metrics` de `json_similarity.py` cuenta `s > 0.5`, `s > 0.75` y `s > 0.9`, mientras que el paper define el
  c2c con "≥". Se reporta como lo calcula el script, sin cambiarlo.
- **Con estos datos la diferencia sí importa,** porque hay similitudes que caen exactamente en el umbral:
  - **JPetStore, MicroAgent:** `Catalog` ↔ `catalog` vale exactamente 0,9 (9/10) en las dos direcciones, en las 3
    corridas completas y en las 5 repeticiones de la Etapa 4. Con "≥", el c2c@90 pasaría de 66,7 a 100 en run1 y de 0 a
    33,3 en run2 y run3. La media pasaría de 22,2 a 55,6.
  - **PartsUnlimitedMRP, baseline-run1:** `ShipmentService` ↔ `shipment` vale exactamente 0,5. Con "≥", el c2c@50
    pasaría de 80 a 100, y la media de la línea base de 86,7 a 93,3.
- `results.csv` lleva solo los valores del script. Los valores con "≥" se calcularon aparte, a partir de las
  similitudes guardadas en `raw/`, y se informarán en `REPORTE.md` como sensibilidad.

### D53. F1 de clases comunes: micro y macro (2026-11-22)
- El paper dice que evalúa "a nivel de servicio". Para ese nivel, `calculate_metrics` da dos promedios: el micro (suma
  los TP, FP y FN de todos los servicios) y el macro (promedia la P, la R y el F1 de cada servicio). El paper no dice
  cuál reporta (93,4 % de media en 10 apps), así que se reportan los dos.
- **Limitación del `common_dict` publicado de JPetStore:** solo evalúa `AbstractActionBean`.
  - Las 6 corridas (MicroAgent y línea base) la ponen bien en los 3 servicios, así que el F1 da 100 % en todas.
  - Las clases de negocio que la Etapa 4 duplica en run2 y run3 (`CatalogService`, `Item`, `ItemMapper`, `Account`,
    `Product`) no cuentan como falsos positivos, porque no están en el diccionario.
  - En JPetStore, entonces, este F1 no distingue entre MicroAgent y la línea base. No se modifica, porque es el del
    original.

### D54. Definición de "turnos" y demás columnas de costo (2026-11-22)
- **Turnos.** Se usa la misma definición en las dos configuraciones. `turnos_num_turns` es la suma del campo
  `num_turns` que devuelve Claude Code en cada llamada (`totales.turnos` de `run_status.json`). Como se vio en D44, en
  una llamada que termina con `success` vale **llamadas a herramientas + 1**. `evaluate.py` lo comprueba en cada llamada
  de las 17 corridas y se cumple en todas. Por eso la línea base da 1: una llamada, sin herramientas.
- **Otras columnas de actividad.** `num_turns` no es lo que limita `--max-turns` (D38, D40, D44), así que se reportan
  además:
  - `peticiones_api`: las peticiones al modelo;
  - `llamadas_a_herramientas`;
  - `llamadas_claude`: los procesos `claude -p` (8 por corrida de MicroAgent, 1 en la línea base).
- **Duración:**
  - `duracion_llamadas_s`: suma de `duration_ms` de las llamadas;
  - `duracion_api_s`;
  - `duracion_reloj_s`: `fin − inicio` de `run_status.json`, que incluye el tiempo del orquestador.
- **Tokens y costo:**
  - los 4 tipos de token que informa Claude Code, y su suma;
  - `costo_nominal_usd`, que es `total_cost_usd`. El plan Pro no cobra por llamada, y en la línea base el valor
    depende de la caché (D48).
- `evaluate.py` comprueba que los totales sean la suma de las etapas. Guarda también `modelo` (`claude-sonnet-4-6` en
  todas las corridas) y `claude_code_version` (2.1.327 en MicroAgent y 2.1.330 en la línea base, D48).

### D55. Revisión independiente de la Fase 6 y correcciones (2026-11-22)
- **Quién y cómo:** un agente revisor de solo lectura, sin llamar a `claude` y con sus scripts en una carpeta temporal
  fuera del proyecto. Revisó `evaluate.py`, `build_common_dict.py`, los dos `common_dict`, las referencias y las
  salidas. **Veredicto: apto, con 4 observaciones de severidad baja o informativas.**
- **Lo que confirmó:**
  - que las copias son idénticas byte a byte;
  - que se usan los scripts originales sin su `__main__` y sin escribir en `MicroAgent/`;
  - el WS, los c2c y el F1 micro y macro de las 17 descomposiciones, recalculados por su cuenta (0 diferencias);
  - las medias y desviaciones estándar muestrales;
  - las columnas de turnos, duración, tokens y costo, frente a `run_status.json` y `run_manifest.json`;
  - la regla del `common_dict`, también con JPetStore;
  - el análisis de errores, que reimplementó por su cuenta (coincide en las 17);
  - los valores de D43, D44 y D48.
- **Hallazgos y qué se hizo:**
  1. *(baja)* `calculate_metrics` recibía el objetivo sin quitar una posible clave `uncounted`, a diferencia del control
     de cordura. → Corregido: se quita, y si aparece queda una nota. Ninguna de las 17 descomposiciones la tiene;
     `results.csv` salió idéntico byte a byte.
  2. *(baja)* D43 daba un promedio de 86,9 % para las 5 repeticiones, calculado con valores redondeados; el valor exacto
     es **86,84 %**. → Corregido en D43.
  3. *(baja, para documentar)* El F1 de clases comunes de PartsUnlimitedMRP usa 7 clases y no 8, y tres de los
     dependientes de `Utility` son `uncounted`. → Registrado en D50; irá en las amenazas a la validez.
  4. *(informativa)* La diferencia entre `num_turns` y `peticiones_api`, el costo de la línea base por la caché y la
     versión distinta de Claude Code. → Ya estaba registrado (D44, D48, D54); irá en `REPORTE.md`.
- **Lo que el revisor no verificó:**
  - que las 8 clases de §9.2 salgan de un grafo regenerado desde el código (usó el contexto existente);
  - los `logs/*_claude.json` de cada etapa (usó `run_status.json`);
  - al decimal, las medias de todas las columnas de duración y tokens (revisó una parte).
- **Correcciones posteriores a la revisión, propias:** al escribir D52 y D56 se comprobaron dos afirmaciones del
  borrador y había que corregirlas:
  - el efecto de "≥" también alcanza al c2c@50 de baseline-run1 de PartsUnlimitedMRP;
  - `CartActionBean` sí falta en su partición de referencia (catalog).
- Tras las correcciones, `check_microagent_untouched.py` da 0 faltantes, 0 modificados y 4 adicionales, todos en
  `target/` (D14).
- sha256 finales: `evaluate.py` `cdac895e…7097d`, `build_common_dict.py` `74343728…e688`, `results.csv` `c9408b6f…ab37c`,
  `results_e4_repeticiones.csv` `3d29a4b3…a7f`.

### D56. Resultados de la Fase 6 y análisis de errores (2026-11-22)
- **Tabla principal** (media ± desviación estándar muestral, n = 3; en %; c2c con `>`, D52). **La fila de JPetStore /
  MicroAgent queda sustituida por la de n = 10 de D58**; las otras tres no cambian:

  | App | Configuración | WS | c2c@50 | c2c@75 | c2c@90 | F1 comunes micro | F1 comunes macro | Paper (WS, Fig. 3) |
  |---|---|---|---|---|---|---|---|---|
  | JPetStore | MicroAgent | 79,87 ± 11,11 | 100 ± 0 | 55,6 ± 38,5 | 22,2 ± 38,5 | 100 ± 0 | 100 ± 0 | ≈ 93 |
  | JPetStore | Línea base | 84,20 ± 0,00 | 100 ± 0 | 100 ± 0 | 33,3 ± 0 | 100 ± 0 | 100 ± 0 | ≈ 81,5 |
  | PartsUnlimitedMRP | MicroAgent | 99,13 ± 1,50 | 100 ± 0 | 100 ± 0 | 100 ± 0 | 98,92 ± 1,86 | 98,79 ± 2,10 | ≈ 100 |
  | PartsUnlimitedMRP | Línea base | 66,58 ± 0,52 | 86,7 ± 11,5 | 40,0 ± 0 | 0 ± 0 | 95,52 ± 0 | 95,38 ± 0 | ≈ 79,5 |

- **Repeticiones de la Etapa 4** (JPetStore, con la entrada de claude-run1; van aparte): WS 92,66 / 76,36 / 86,26 /
  86,26 / 92,66 %, con media 86,84 %.
- **Análisis de errores** (`evaluation/error_analysis.md`). Cada servicio producido se asocia a la partición de
  referencia más parecida (dirección P→R, método 2).
  - *JPetStore, MicroAgent:* en las 3 corridas, `CartActionBean` está en Order y falta en Catalog; este error nace en
    la Etapa 1 (D43). En run2 y run3 se suman duplicados que vienen de la Etapa 4: `CatalogService`, `Item` e
    `ItemMapper` también en Account y en Order, `Account` también en Order y, en run2, `Product` también en Account.
    Aparte de `CartActionBean`, todos los errores son clases puestas de más.
  - *JPetStore, línea base* (las 3 corridas son iguales): `Account`, `Item` e `ItemMapper` duplicados en Order, y `Cart`
    y `CartItem` duplicados en Catalog. No falta ninguna clase.
  - *PartsUnlimitedMRP, MicroAgent:* run1 y run3 no tienen errores. En run2, `BadRequestException` está de más en
    Catalog y Dealer (D44).
  - *PartsUnlimitedMRP, línea base:* 21, 24 y 21 clases puestas de más (modelos, repositorios y excepciones repartidos
    entre 2 y 4 servicios), sin clases que falten. Las 7 `uncounted` quedan en los 5 servicios en las 6 corridas.
- **Lectura:**
  - En PartsUnlimitedMRP la réplica reproduce lo que dice el paper: MicroAgent ≈ 100 %, con 32,6 puntos de ventaja
    sobre la línea base.
  - En JPetStore, la mejor corrida (92,7 %) coincide con el ≈ 93 % del paper, pero la media queda 4,3 puntos por debajo
    de la línea base, por la variabilidad de la Etapa 4 (D41, D43).
- `REPORTE.md` y `README.md` (§12) quedan pendientes.

### D57. Por qué la Etapa 4 de JPetStore varía tanto y qué se podría hacer (2026-11-22, pedido de Jorge)
- **Nota posterior (D58):** con 7 corridas más, las causas 2 (texto de la fusión que sugiere `ItemMapper`) y la
  correlación con el número de candidatas pasadas a `get_more_potential_common_classes` **no se sostienen**; ver D58.
  La causa 1 (muestreo) y los amplificadores 3 y 4 siguen en pie.
- **Qué se hizo:** se leyeron los `4_common_stream.jsonl` de las 8 ejecuciones de la Etapa 4 (claude-run1 a run3 y
  claude-run1-e4-r01 a r05), se compararon las entradas y salidas de cada herramienta, y se recalculó el WS con
  `json_similarity.py` del original para variantes hipotéticas (con y sin propagación, con y sin `ItemMapper`).
  Ningún archivo del pipeline ni ningún resultado cambió.
- **Dónde se separan.** Las salidas de `get_all_class_hierarchy_complete`, `get_database_summary` y
  `rank_dependency_entropy` son idénticas byte a byte en las 8 (mismo SHA-256). El quiebre está en el paso siguiente:
  - run1, r01, r04 y r05 revisan primero el código de `AbstractActionBean` y pasan 2 a 4 candidatas a
    `get_more_potential_common_classes` → WS 92,7 / 92,7 / 86,3 / 92,7 %.
  - run2, run3, r02 y r03 copian las 6 primeras del ranking → WS 72,6 / 74,4 / 76,4 / 86,3 %.

  Esa decisión se toma antes de que el agente vea la primera salida que depende del orden de un `set`, así que la
  explica el muestreo y no `PYTHONHASHSEED`.
- **Hipótesis descartadas:** herramientas distintas del original (`custom_tools.py` solo cambia 2 `import`); otro
  modelo (las 8 dicen `claude-sonnet-4-6`, y las 5 repeticiones, hechas en 6 minutos, ya dan resultados distintos);
  el orden de los `set`s como causa del quiebre (ver arriba; no se descarta que influya en pasos posteriores);
  error de evaluación (control de cordura 1,0, D55); caché de prompts y límite de turnos.
- **Causas probables, de más a menos peso:**
  1. **Muestreo (`temperature: 1`, D35).** Con la entrada de run1 salen 3 resultados distintos en 5 repeticiones;
     2 de 5 llegan al 92,7 %. Con esa tasa, que dos corridas seguidas salgan mal tiene una probabilidad cercana al
     36 %: lo excepcional es run1, no run2 y run3.
  2. **La entrada de la Etapa 4 no es la misma en las tres corridas completas** (corrige D43). El mensaje de usuario
     lleva los dominios fusionados (mismas clases, otro orden) y, como contexto, la respuesta final del Merging Agent
     (D27), que es texto libre y cambia en cada corrida (MD5 del prompt: run1 `1514…`, run2 `2881…`, run3 `f3fe…`;
     las 5 repeticiones tienen el de run1). El contexto de run2 y run3 dice que `OrderService` usa `ItemMapper`
     ("cross-domain dependency with Catalog"); el de run1 no lo menciona. run2 y run3 declaran común `ItemMapper`;
     ninguna de las 5 repeticiones con la entrada de run1 lo hace, ni siquiera r02, que lo tuvo entre sus candidatas.
     Con n = 2 es una correlación, no una prueba. Peso estimado: unos 2 a 4 puntos de WS.
  3. **La propagación de `assign_common_class_list` agranda el error.** WS real frente a WS con solo los dominios que
     eligió el agente: run2 72,6 frente a 76,4; run3 74,4 frente a 78,7; r02 76,4 frente a 78,6. Además, el agente
     no siempre copia la salida de la herramienta: run2 deja `Product` fuera de Order y r02 deja `Item` fuera de
     Account.
  4. **La métrica castiga mucho los duplicados.** No es causa, pero amplifica: sin clases comunes el WS es 84,9 %;
     con solo `AbstractActionBean`, 92,7 %; con `AbstractActionBean` y `CatalogService` en los 3 servicios, 86,3 %.
- **De qué depende la propagación** (custom_tools.py del original, líneas 2228-2495):
  - Solo actúa **entre las clases que el agente declara comunes**; las demás clases no cuentan. El grafo sale de
    `class_info_dependency.json` y es fijo.
  - `incoming` (utilidad): si una clase común A depende de otra clase común B, B recibe todos los dominios de A.
    `outgoing` (coordinadora): al revés, A recibe los dominios de las clases comunes de las que depende.
  - Es determinista para una misma entrada mientras no haya ciclos; el orden de los `set`s solo cambia el orden de
    las listas (D41).
  - En JPetStore el detonante es declarar `CatalogService` común en los 3 dominios: como depende de `Item`,
    `ItemMapper` y `Product`, cualquiera de esas que también se declare común hereda los 3 dominios. Si el agente
    declara solo `AbstractActionBean`, que no depende de ninguna otra clase común, no hay propagación. Con solo
    `CatalogService` tampoco (r03, r04: 86,3 %).
  - La propagación hace lo que el original diseñó; el error está antes, en qué clases se declaran comunes.
- **Remedios posibles.** Ninguno es fiel al original salvo el primero. Por la regla de fidelidad, ninguno se aplica a
  las corridas principales sin decisión de Jorge; si se prueba alguno, debe ir como variante aparte y rotulada.

  | Remedio | Qué ataca | ¿Fiel al original? | Lectura |
  |---|---|---|---|
  | Más corridas (n = 5 o 10) y reportar la distribución (media, mediana, mejor) | Nada; mide mejor | Sí | Es lo único que no cambia el método. |
  | Temperatura 0 llamando a la API directamente (`claude -p` y el Agent SDK no la exponen) | Causas 1 y 2 | Más cerca del original en este punto, pero cambia el modo de ejecución de toda la réplica | La temperatura 0 tampoco da determinismo total, pero debería reducir mucho la dispersión. Costo por API, fuera del plan. |
  | Fijar `PYTHONHASHSEED` | Orden de las listas | No (el original no lo fija) | Ayuda a reproducir, pero no ataca el quiebre principal. |
  | Ordenar (`sorted`) las listas de los dominios y de las herramientas | Parte de la causa 2 | No | El texto de la fusión seguiría cambiando. |
  | Quitar el contexto de la fusión en la Etapa 4 | Causa 2 | No (contradice D27, que lo reproduce del original) | Iría contra una decisión ya tomada para ser fiel. |
  | Imponer el orden de las herramientas (revisar el código de cada candidata antes de `get_more_potential_common_classes`) | Causa 1 | No (cambia el prompt del original) | La correlación existe (los que revisaron `AbstractActionBean` primero salieron mejor 3 de 4 veces), pero run2 y run3 también revisaron el código y aun así declararon clases de negocio, así que el beneficio no está demostrado. |
  | Votación: repetir la Etapa 4 k veces y quedarse con las clases comunes que aparecen en la mayoría | Causa 1 | No (agrega un paso) | Con las 5 repeticiones de run1, la mayoría habría sido `AbstractActionBean` + `CatalogService` (3 de 5), es decir 86,3 %, no 92,7 %. |

- **Conclusión:** la varianza viene del muestreo y de que la Etapa 4 recibe un texto de la fusión distinto en cada
  corrida, y la propagación y la métrica la agrandan. Dentro de un método fiel al original no se puede eliminar,
  solo medir mejor con más corridas. La causa de fondo, `temperature: 1`, solo se corrige saliendo de `claude -p`.
- **Pendiente de Jorge:** decidir si se agregan corridas de JPetStore, si se prueba alguna variante como experimento
  aparte, o si se reporta como amenaza a la validez con estas cifras.

### D58. JPetStore con n = 10 corridas completas de MicroAgent (2026-11-22, decisión de Jorge)
- **Motivo:** con n = 3, la media de JPetStore dependía de qué camino tomara la Etapa 4 en cada corrida (D57). Jorge
  pidió ampliar a n = 10. La línea base sigue con n = 3 porque sus 3 respuestas son idénticas (D48). PartsUnlimitedMRP
  sigue con n = 3.
- **Qué se corrió:** `run_pipeline.py --app jpetstore-6`, run_id `claude-run4` a `claude-run10`, una tras otra, entre
  las 14:41 y las 15:23. Costo nominal: USD 7,57 (entre 0,97 y 1,17 por corrida).
  - El primer intento se detuvo en `prepare` antes de llamar a `claude`: `evaluation/references/` no estaba vacía
    desde la Fase 6 (protección D23, D32). No se usó `--allow-references`. Los 2 archivos se apartaron a
    `../_referencias_apartadas_lote_run4_10/` y un `trap` los devolvió al terminar; la carpeta ya no existe.
  - Esa carpeta estaba, en teoría, al alcance de las herramientas de archivos (aceptan rutas con `..`), pero ningún
    agente usó una herramienta de rutas: la auditoría no registra ninguna ruta, y en los `*_stream.jsonl` y
    `*_server.jsonl` no aparecen `evaluation/`, `_referencias`, `apartadas` ni `jpetstore_classes`.
- **Validez** (revisada por un agente independiente): las 7 corridas tienen `estado: completa`, sin fallos, sin
  límite de turnos, sin invalidaciones en las auditorías y con las mismas 8 observaciones `sin_etiqueta_final_answer`
  que run1 a run3. El contexto (`335b319a…`), los SHA-256 del pipeline, el entorno, el esfuerzo, `max_turns` y las
  herramientas por agente son los de claude-run1.
- **Desviación: otra versión de Claude Code.** claude-run4 a run10 usaron **2.1.330**; claude-run1 a run3 usaron
  2.1.327 (la instalación del usuario se actualizó entre sesiones; la línea base ya usaba 2.1.330, D48). Lo que llega
  al modelo es igual: los bloques de system tienen el mismo SHA-256 en las 10 corridas y en las 5 etapas, y los
  parámetros de muestreo no cambian. Los WS de las corridas nuevas caen en los mismos tres niveles que los de run1 a
  run3. Se reporta como desviación menor de §10.1, igual que en D48.
- **Cambio en `evaluation/evaluate.py`:** `N_MICROAGENT` y `runs_for(app)` en lugar de una lista fija de 3 corridas,
  y filas de resumen nuevas (mediana, mínimo y máximo). Comparado con el CSV anterior, las filas de la línea base y de
  PartsUnlimitedMRP son idénticas; solo cambian las de JPetStore/MicroAgent. Control de cordura: OK. `EXPECTED` no
  tiene valores a mano para run4 a run10; el revisor recalculó las cifras de forma independiente y coinciden.
- **Resultados por corrida** (WS en %; las clases comunes son las de la última llamada a `assign_common_class_list`;
  run7 la llamó dos veces y la segunda agregó `Product`):

  | Clases comunes declaradas | Corridas | WS |
  |---|---|---|
  | Solo `AbstractActionBean` (como la referencia) | run1, run5, run6, run9 | 92,66 |
  | `AbstractActionBean` + `CatalogService` | run4, run10 | 86,26 |
  | Además clases de negocio (`ItemMapper`, `Item`, `Account`; `Product` en run2 y run7) | run2, run3, run7, run8 | 72,59 / 74,35 / 70,71 / 74,35 |

  En las 10 corridas: 4 dominios en la Etapa 1, fusión ejecutada, mismos 3 dominios fusionados y ningún cambio en la
  Etapa 5. Toda la diferencia sigue estando en la Etapa 4. El error de `CartActionBean` aparece en las 10.
- **Tabla principal actualizada** (en %; c2c con `>`, D52):

  | App | Configuración | n | WS media ± desv. | Mediana | Mín.–máx. | c2c@50 | c2c@75 | c2c@90 | F1 comunes micro | Paper (WS) |
  |---|---|---|---|---|---|---|---|---|---|---|
  | JPetStore | MicroAgent | 10 | 83,52 ± 9,43 | 86,26 | 70,71–92,66 | 100 | 73,3 ± 34,4 | 26,7 ± 34,4 | 100 | ≈ 93 |
  | JPetStore | Línea base | 3 | 84,20 ± 0,00 | 84,20 | 84,20 | 100 | 100 | 33,3 | 100 | ≈ 81,5 |
  | PartsUnlimitedMRP | MicroAgent | 3 | 99,13 ± 1,50 | 100,00 | 97,40–100,00 | 100 | 100 | 100 | 98,92 | ≈ 100 |
  | PartsUnlimitedMRP | Línea base | 3 | 66,58 ± 0,52 | 66,44 | 66,13–67,15 | 86,7 | 40,0 | 0 | 95,52 | ≈ 79,5 |

- **Lectura:**
  - En JPetStore la media de MicroAgent queda 0,7 puntos por debajo de la línea base, y la mediana 2,1 puntos por
    encima. Con esta dispersión, las dos configuraciones no se distinguen; el paper reporta una ventaja de unos 11,5
    puntos que la réplica no reproduce en promedio.
  - 4 de 10 corridas coinciden con el ≈ 93 % del paper. Es la misma proporción que en las 5 repeticiones de la Etapa 4
    (2 de 5, D43).
- **Revisión de D57 con los datos nuevos:**
  - *Número de candidatas:* run5 y run9 pasaron las 6 primeras del ranking a `get_more_potential_common_classes` sin
    revisar código antes, y aun así declararon solo `AbstractActionBean`. Pasar 6 candidatas no lleva siempre al mal
    resultado. **Hipótesis descartada.**
  - *Texto de la fusión que sugiere `ItemMapper`:* 9 de las 10 respuestas de la fusión dicen que `OrderService` usa
    `ItemMapper` (todas salvo run1), pero solo 4 corridas lo declaran común. La correlación de D57 venía de que esa
    mención se buscó con una expresión regular demasiado estricta. **Hipótesis descartada.** Sigue siendo cierto que
    la entrada de la Etapa 4 cambia entre corridas (D27); no hay evidencia de que eso decida el resultado.
  - *Muestreo (`temperature: 1`):* sigue siendo la explicación más simple, con la propagación y la métrica como
    amplificadores (D57, causas 3 y 4).
- **Pendiente de Jorge:** aceptar la diferencia de versión como desviación menor o repetir run4 a run10 con 2.1.327.
  Actualizar con n = 10 el resumen de FASES-DEL-PROYECTO.md (§ Fase 6) y, cuando se escriban, `REPORTE.md` y
  `README.md`.

### D59. `README.md` y `REPORTE.md`; correcciones que salieron de la revisión (2026-11-22)
- Se escribieron `README.md` (cómo correr cada fase) y `REPORTE.md` (§12). Cada uno pasó por un revisor
  independiente, y se aplicaron todas sus correcciones.
- **Corrige D57 y D58: las entradas de la Etapa 4 de JPetStore no son iguales en las 10 corridas.** En claude-run7 y
  claude-run8, la Etapa 2 puso además `AbstractActionBean` en Account Management, y así quedó en
  `domains/all_domains.json` y en `merged_domains.json`. En las otras 8 corridas eso no pasa.
  - Por eso, en esas dos corridas `rank_dependency_entropy` devuelve otros valores. Por ejemplo, la entropía
    saliente de `CartActionBean` pasa de 0,971 a 1,3788.
  - La igualdad byte a byte de las tres primeras herramientas (D57) vale solo para las 8 ejecuciones que se
    compararon en D57, no para las 10 corridas.
  - run7 y run8 están en el nivel bajo de WS (70,71 y 74,35 %). Con dos casos, se reporta como un posible factor y
    no como causa demostrada.
- **c2c con `≥` (lo que pedía D52).** Se recalculó con las similitudes de `evaluation/raw/`, en las dos direcciones
  y combinadas con F1 como hace el script. Solo cambian dos valores:
  - JPetStore / MicroAgent, c2c@90: de 26,7 a 60,0 %, porque Catalog ↔ catalog vale 0,900 en las 10 corridas;
  - PartsUnlimitedMRP / línea base, c2c@50: de 86,7 a 93,3 %.

  `results.csv` sigue con `>`, como el script.
- **Pendiente de Jorge:** sigue abierta la decisión sobre la versión de Claude Code (D58), y falta actualizar la
  sección de la Fase 6 de `FASES-DEL-PROYECTO.md` con n = 10.

### D60. Tabla principal con una sola versión de Claude Code (2.1.330) (2026-11-22, decisión de Jorge)
- **Qué estaba pendiente (D58):** MicroAgent mezclaba dos versiones de Claude Code. JPetStore `claude-run1` a `run3`
  y PartsUnlimitedMRP `claude-run1` a `run3` usaron 2.1.327; JPetStore `claude-run4` a `run10` y la línea base,
  2.1.330.
- **Decisión de Jorge:** repetir con 2.1.330 lo que se había corrido con 2.1.327. La 2.1.330 ya era la última
  versión publicada (`npm view @anthropic-ai/claude-code version`).
- **Qué se corrió:** `run_pipeline.py` sin cambios, una corrida tras otra, entre las 20:19 y las 21:05:
  - JPetStore `claude-run11` a `run13`;
  - PartsUnlimitedMRP `claude-run4` a `run6`.

  Costo nominal: USD 7,54.
  - Las referencias se apartaron **fuera del proyecto**, en la carpeta temporal de la sesión, y un `trap` las
    devolvió al terminar. No se usó `--allow-references`.
  - Resultado: las 6 corridas terminaron con `estado: completa`, `rc=0` y la única observación
    `sin_etiqueta_final_answer`.
  - Fusión: ejecutada en JPetStore y saltada en PartsUnlimitedMRP.
- **Qué cambia en la evaluación** (`evaluation/evaluate.py`):
  - La configuración `microagent` pasa a ser JPetStore `claude-run4` a `run13` (n = 10) y PartsUnlimitedMRP
    `claude-run4` a `run6` (n = 3).
  - Las `claude-run1` a `run3` de cada app no se borran. Pasan a la configuración `microagent_cc2.1.327`, que se
    reporta aparte.
  - `EXPECTED_CC_VERSION` aborta la evaluación si una corrida no tiene la versión de su configuración.
  - Las repeticiones de la Etapa 4 (2.1.327) siguen aparte y no cambian.
  - La lógica de las métricas no cambió.
- **Resultados** (en %; c2c con `>`):

  | App | Configuración | n | WS | Mediana | Mín.–máx. | c2c@75 | c2c@90 | F1 comunes micro |
  |---|---|---|---|---|---|---|---|---|
  | JPetStore | MicroAgent (2.1.330) | 10 | 85,55 ± 7,96 | 86,26 | 70,71–92,66 | 83,3 ± 28,3 | 26,7 ± 34,4 | 100 |
  | JPetStore | MicroAgent (2.1.327, aparte) | 3 | 79,87 ± 11,11 | 74,35 | 72,59–92,66 | 55,6 ± 38,5 | 22,2 ± 38,5 | 100 |
  | PartsUnlimitedMRP | MicroAgent (2.1.330) | 3 | 99,56 ± 0,76 | 100,00 | 98,68–100,00 | 100 | 100 | 100 |
  | PartsUnlimitedMRP | MicroAgent (2.1.327, aparte) | 3 | 99,13 ± 1,50 | 100,00 | 97,40–100,00 | 100 | 100 | 98,92 |

  La línea base no cambia: 84,20 y 66,58.
- **Corridas nuevas.**
  - *JPetStore:*
    Las clases comunes que se indican son las que quedan en varios servicios en `result.json`:
    - run11: `CatalogService`, además de `AbstractActionBean` (86,26 %);
    - run12: solo `AbstractActionBean` (92,66 %);
    - run13: `CatalogService`, `Item` e `ItemMapper`, además de `AbstractActionBean`; queda en un nivel nuevo,
      80,99 %.

    **Excepción en run12 al criterio de D58** ("las de la última llamada a `assign_common_class_list`"):
    - su única llamada a esa herramienta declara `AbstractActionBean`, `CatalogService`, `Item` e `ItemMapper`
      (`logs/4_common_server.jsonl`);
    - después, el agente solo escribe `AbstractActionBean` con `write_result_to_json`, y lo explica en
      `4_common_final_answer.txt`.

    Es la primera de las 19 corridas en que la llamada y el resultado escrito no coinciden. Desde aquí, "clases
    declaradas comunes" significa las que quedan en `common_result.json` y `result.json`. Para las demás corridas,
    los dos criterios dan lo mismo.

    Los dominios fusionados de las tres tienen el mismo contenido que los de run1 a run6, run9 y run10. El error
    de `CartActionBean` aparece en las tres.
  - *PartsUnlimitedMRP:*
    - run4 y run6 no tienen errores; en las dos, la Etapa 5 agrega `PostgresqlProperties`, que la Etapa 4 había
      dejado sin asignar, como ya pasó en la run2 anterior;
    - run5 deja `OrderStatus` de más en Shipment. El error nace en la Etapa 4, pero no por la propagación: el
      agente la escribió directamente con `write_result_to_json`.

    Las Etapas 1 a 3 dan el mismo contenido en las 6 corridas.
- **c2c con `≥`** (D52, D59): JPetStore / MicroAgent pasaría de 26,7 a 60,0 en c2c@90. Los demás valores de MicroAgent
  no cambian.
- **Lectura:**
  - JPetStore: con una sola versión, la media de MicroAgent queda 1,4 puntos por encima de la línea base. Con una
    desviación de 8 puntos, las dos configuraciones no se distinguen.
  - PartsUnlimitedMRP: sigue reproduciendo el paper.
  - Las corridas con 2.1.327 de JPetStore quedan dentro del rango de las de 2.1.330. En PartsUnlimitedMRP, la run2
    anterior (97,40 %) queda 1,3 puntos por debajo del mínimo con 2.1.330 (98,68 %). Con n = 3 no hay evidencia de
    que la versión influya.
- Se actualizaron `REPORTE.md`, `README.md` y `FASES-DEL-PROYECTO.md`. Queda resuelto lo pendiente de D58 y D59.
