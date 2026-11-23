# Réplica de MicroAgent con Claude Code

Réplica de **MicroAgent** (Su et al., ASE '26), que descompone un monolito Java en *n* microservicios con cinco
agentes LLM en secuencia. Hay dos cambios frente al original, ambos aprobados por el profesor:

- los agentes corren con **Claude Code** (`claude -p`) en lugar de CrewAI por API;
- se usan **2 de las 10 aplicaciones**: **JPetStore** (24 clases, n = 3) y **PartsUnlimitedMRP** (53 clases, n = 5).

El resto (prompts, lógica de las herramientas, orden de las etapas, formato de entradas y salidas, scripts de
métricas) es igual al artefacto. Hay tres documentos de referencia:

| Documento | Contenido |
|---|---|
| `docs/INSTRUCCIONES-REPLICA-MICROAGENT-CLAUDE-CODE.md` | especificación de la réplica (los § que cita este README) |
| `DECISIONES.md` | registro de cada decisión y desviación (D1 a D60) |
| `docs/FASES-DEL-PROYECTO.md` | explicación de cada fase y de sus resultados |
| `REPORTE.md` | resultados y comparación con el paper |

Este README solo explica **cómo se ejecuta cada fase**.

> **Regla:** `../MicroAgent/` (el artefacto descargado) no se modifica nunca. Para comprobarlo:
> `python scripts/check_microagent_untouched.py` (lo compara con `../MicroAgent.zip`; D14).

**El artefacto no está en este repositorio.** Descárgalo de Zenodo
([doi:10.5281/zenodo.19250602](https://doi.org/10.5281/zenodo.19250602), licencia MIT), guarda el zip como
`MicroAgent.zip` junto a `replica-claude-code/` y descomprímelo en `MicroAgent/` (el zip no trae carpeta raíz):

```
Replica de Paper/
├── MicroAgent.zip
├── MicroAgent/            contenido del zip (decomposition/, graph/, metrics/, microagent/, ...)
└── replica-claude-code/   este repositorio
```

Sin él no funcionan `evaluate.py`, `build_common_dict.py`, `check_microagent_untouched.py` ni la copia del
contexto de JPetStore (§3.2).

**Qué no se versiona** (`.gitignore`): los clones de `resources/` y el jar de `graph/target/` (se regeneran con
§3.1 y §3.3), y las transcripciones `*_transcript.jsonl` de cada corrida, porque Claude Code incluye en ellas
datos de la cuenta. Sí se versionan las auditorías `*_audit.json` que se calculan a partir de ellas.
`.gitattributes` desactiva la conversión de saltos de línea para que las huellas SHA-256 coincidan al clonar.

---

## 1. Requisitos

| Qué | Versión usada | Nota |
|---|---|---|
| Python | 3.14.0 | La especificación pide 3.10–3.13; los paquetes funcionan en 3.14 (D1). |
| Java + Maven | OpenJDK Temurin 25, Maven 3.10 | Solo para regenerar el grafo de dependencias (Fase 1). |
| Git | — | Para clonar las dos aplicaciones. |
| Claude Code | 2.1.325, 2.1.327 y 2.1.330 | Plan Pro. Hace falta que `claude` esté en el `PATH` y con la sesión iniciada. La versión de cada corrida está en §9. |
| Modelo | `claude-sonnet-4-6` | Fijo en todas las llamadas; esfuerzo `high`, sin razonamiento extendido (D3, D4, D35). |

```powershell
pip install -r requirements.txt
```

`requirements.txt` no incluye CrewAI. Las herramientas originales se cargan con un *shim*
(`tools/microagent_shim.py`). CrewAI 1.8.1 solo hace falta para capturar los prompts del original (Fase 3) y se
instala en un entorno aparte con Python 3.12.

**Todos los comandos se ejecutan desde `replica-claude-code/`.** Los scripts que leen o escriben texto en UTF-8
necesitan `-X utf8`; el orquestador se niega a arrancar sin esa opción.

---

## 2. Estructura

```
replica-claude-code/
├── docs/                     especificación de la réplica y explicación de las fases
├── resources/<app>/          clones de las aplicaciones (JPetStore en a37c02f, PartsUnlimitedMRP en 0268218)
├── graph/                    copia del analizador Java del artefacto (pom.xml y src/ idénticos), compilada aquí
├── context/<app>/            class_info_dependency.json y class_summaries.json          (Fase 1)
├── database/<app>/           sql-summary.json                                            (Fase 1)
├── tools/                    custom_tools.py (original con 2 importaciones cambiadas), shim, servidor MCP (Fase 2)
├── prompts/build_prompts.py  prompts literales de cada etapa                             (Fase 3)
├── run_pipeline.py           orquestador de las 5 etapas                                 (Fase 4)
├── run_stage4.py             repetición aislada de la Etapa 4 (D41)
├── run_baseline.py           línea base zero-shot                                        (Fase 5)
├── evaluation/               métricas, referencias, resultados                           (Fase 6)
├── output/<app>/<run_id>/    una carpeta por corrida (result.json + logs/)
├── logs/                     pruebas, controles y huellas de contexto
├── scripts/                  generación de contexto, pruebas sin cupo y comprobaciones
└── _sandbox/                 carpeta vacía desde la que se lanza cada `claude -p`
```

`<app>` es `jpetstore-6` o `partsunlimited`.

---

## 3. Fase 1: preparación del contexto (§4)

El contexto se genera **una sola vez** por aplicación y se reutiliza en todas las corridas. El orquestador
comprueba su huella SHA-256 (`logs/context_fingerprint/`) antes de cada corrida (D32). Este paso **no hace falta
repetirlo** para reproducir las corridas: el contexto ya está en `context/` y `database/`.

### 3.1 Clonar las aplicaciones

```powershell
git clone https://github.com/mybatis/jpetstore-6 resources/jpetstore-6
```
```powershell
git -C resources/jpetstore-6 checkout a37c02f
```
```powershell
git clone https://github.com/microsoft/PartsUnlimitedMRP resources/partsunlimited
```
```powershell
git -C resources/partsunlimited checkout 0268218
```

JPetStore tiene que estar en `a37c02f`: el HEAD actual ya no contiene 5 de las 24 clases (D6). En
PartsUnlimitedMRP, `0268218` es el HEAD actual; el repositorio no cambia desde 2023 (D9).

### 3.2 JPetStore: contexto de los autores

Se copia byte a byte el contexto que publica el artefacto:

| Origen | Destino |
|---|---|
| `../MicroAgent/microagent/context/test/*.json` | `context/jpetstore-6/` |
| `../MicroAgent/microagent/database/jpetstore-6/sql-summary.json` | `database/jpetstore-6/` |

Como control, el grafo regenerado con el analizador coincide 24 de 24 con el de los autores (`logs/jpetstore_control/`).

### 3.3 PartsUnlimitedMRP: contexto generado

El artefacto no trae este contexto, así que se genera con sus mismas herramientas y prompts:

```powershell
cd graph; mvn clean package; cd ..
```
```powershell
java -jar graph/target/java-class-analyzer.jar resources/partsunlimited/src/Backend/OrderService/src/main/java --json logs/partsunlimited_context/analyzer_raw_output.json --dot logs/partsunlimited_context/diagram.dot --jpg logs/partsunlimited_context/diagram.jpg
```
```powershell
python scripts/extract_classes.py logs/partsunlimited_context/analyzer_raw_output.json context/partsunlimited/class_info_dependency.json
```
```powershell
python -X utf8 scripts/gen_class_summaries.py --app partsunlimited --java-root resources/partsunlimited/src/Backend/OrderService/src/main/java
```
```powershell
python -X utf8 scripts/gen_db_summary.py --app partsunlimited --sql resources/partsunlimited/src/Backend/OrderService/scripts/schema.psql --out-name sql-summary.json
```

- El analizador se compila en `graph/`, que es una copia, para no escribir dentro de `MicroAgent/` (D8).
- `gen_class_summaries.py` hace una llamada `claude -p` por archivo `.java`, sin herramientas y con el prompt
  literal. Se puede reanudar: si se corta por el límite del plan, al volver a ejecutarlo salta los resúmenes
  que ya están guardados en `logs/partsunlimited_context/summaries/`.
- `schema.psql` es el único esquema del repositorio, aunque la aplicación use MongoDB en ejecución (D11).

Controles:

```powershell
python -X utf8 scripts/reconcile_partsunlimited.py
```
```powershell
python scripts/verify_context.py partsunlimited --reference ../MicroAgent/decomposition/partsunlimited.json
```
```powershell
python scripts/check_context_calls.py partsunlimited
```

Comprueban que salgan 53 clases (46 en particiones y 7 `uncounted`), que el grafo y los resúmenes tengan las
mismas claves, y que cada llamada haya usado el modelo correcto sin razonamiento extendido.

---

## 4. Fase 2: herramientas (servidor MCP) (§5)

`tools/mcp_server.py` publica las 14 herramientas de `custom_tools.py` con el mismo nombre, descripción y
argumentos, y cada una devuelve la misma cadena que el `_run` original. No se ejecuta a mano. El orquestador
genera en cada etapa un `mcp_config.json` que lo lanza por stdio. `MICROAGENT_TOOLS` limita las herramientas
publicadas a las del agente de esa etapa, y `RESULT_FILE` indica dónde escribe `write_result_to_json`.

Pruebas:

```powershell
python -X utf8 scripts/smoke_test_tools.py
```
```powershell
python -X utf8 scripts/check_mcp_with_claude.py --name check_mcp
```

La primera no gasta cupo: compara cada herramienta servida por MCP con su `_run` y guarda el resultado en
`logs/tool_smoke_test.txt`. La segunda hace **una** llamada real a `claude` y comprueba que el modelo ve solo las
herramientas MCP permitidas y ninguna integrada de Claude Code (`logs/cli_checks/`).

---

## 5. Fase 3: prompts literales (§6)

`prompts/build_prompts.py` arma el system prompt y el mensaje de usuario de cada etapa a partir de los YAML
originales, el texto de `main.py` y las plantillas de CrewAI 1.8.1. La única diferencia es que no incluye el
bloque ReAct de herramientas.

```powershell
python -X utf8 scripts/check_prompts.py
```

Esta comprobación no gasta cupo ni necesita CrewAI. Compara carácter por carácter con las capturas reales del
original en `logs/prompts_golden/` y escribe el resultado en `logs/prompts_check.txt`.

Para regenerar esas capturas (opcional) se necesita un entorno con CrewAI:

```powershell
uv venv --python 3.12 C:\tmp\crewai-venv; uv pip install --python C:\tmp\crewai-venv\Scripts\python.exe crewai==1.8.1 pyyaml
```
```powershell
C:\tmp\crewai-venv\Scripts\python.exe scripts/capture_crewai_prompts.py --workdir C:\tmp\captura
```

Ese script ejecuta una **copia** del `main.py` original con un LLM simulado. No llama a ningún servicio.

Para ver los 5 system prompts y el prompt de la Etapa 1 de una aplicación sin ejecutar nada:
`python -X utf8 prompts/build_prompts.py --app jpetstore-6 --out <carpeta>`. Los prompts de las demás etapas
dependen de las respuestas anteriores y solo se ven en los `logs/` de cada corrida.

---

## 6. Fase 4: orquestador de MicroAgent (§7)

Antes de correr:

1. **Aparta `evaluation/references/`.** Las herramientas no deben poder ver las descomposiciones de referencia
   (D23, D32). Si esa carpeta tiene archivos, `run_pipeline.py` no arranca. Muévela fuera de
   `replica-claude-code/` y devuélvela antes de la Fase 6. `--allow-references` evita esa comprobación, pero
   queda registrado y no debe usarse en corridas que se vayan a reportar.
2. `_sandbox/` tiene que estar vacía.
3. Corre la prueba sin cupo: `python -X utf8 scripts/test_pipeline_offline.py` (resultado en
   `logs/pipeline_offline_test.txt`). También exige que las referencias estén apartadas.

Una corrida completa:

```powershell
python -X utf8 run_pipeline.py --app jpetstore-6 --run-id claude-run1
```

| Etapa | Agente | Salida en `output/<app>/<run_id>/` |
|---|---|---|
| 1 | Domain | `domains/domain_clusters.json` |
| 2 | Clustering (uno por dominio) | `domains/<Dominio>.json`, `domains/all_domains.json` |
| 3 | Merging (solo si `len(dominios) != n`) | `domains/merged_domains.json` |
| 4 | Common Class | `common_result.json` |
| 5 | Review | **`result.json`** (la descomposición final) |

- `n` sale de la aplicación (3 o 5) y no se puede cambiar. `--number` y `--num` existen, pero el orquestador
  aborta si no coinciden con los de la aplicación.
- `--only-stage1` corre solo la Etapa 1 (prueba de humo, §7).
- La primera corrida real de cada aplicación guarda la huella del contexto en `logs/context_fingerprint/<app>.json`.
  Las corridas siguientes, incluidas las de la línea base, la comparan antes de empezar.
- **Un `run_id` nunca se sobrescribe.** Si una corrida falla, queda registrada en
  `output/<app>/<run_id>/logs/run_status.json` y se vuelve a intentar con un `run_id` nuevo (§10.4).
- En `logs/` de cada corrida quedan, por etapa: el prompt y el system prompt exactos, el flujo `stream-json`,
  las llamadas recibidas por el servidor MCP, la transcripción (solo en local, no se versiona) y una auditoría de aislamiento. A nivel de
  corrida quedan `run_manifest.json` (modelo, versión de Claude Code, fecha) y `run_status.json` (turnos,
  tokens, costo).

**Repetición aislada de la Etapa 4** (D41). Repite solo esa etapa con la entrada exacta de una corrida
anterior, para medir cuánto varía por el muestreo:

```powershell
python -X utf8 run_stage4.py --app jpetstore-6 --desde claude-run1 --run-id claude-run1-e4-r01
```

Antes de lanzar `claude`, verifica que el prompt sea idéntico byte a byte al de la corrida de origen. Tiene su
propia prueba sin cupo: `python -X utf8 scripts/test_stage4_offline.py`.

---

## 7. Fase 5: línea base zero-shot (§8)

Una sola llamada `claude -p` sin herramientas, que recibe el código, el esquema de base de datos y `n`. El
artefacto no publica ese prompt; la réplica lo reconstruye (D45).

```powershell
python -B -X utf8 run_baseline.py --app jpetstore-6 --run-id baseline-run1
```

- El `run_id` tiene que empezar por `baseline-`. La respuesta se limpia con la misma `clean_json_output` del
  original y no se corrige nada (D46).
- Requiere `logs/context_fingerprint/<app>.json`, es decir, que antes se haya hecho al menos una corrida real
  de MicroAgent con esa aplicación (§6).
- `--solo-prompt <carpeta>` arma el prompt sin llamar a `claude`. La carpeta tiene que estar fuera del proyecto
  (`Replica de Paper/`).
- Prueba sin cupo: `python -B -X utf8 scripts/test_baseline_offline.py`.

---

## 8. Fase 6: evaluación (§9)

Antes, devuelve las referencias a `evaluation/references/` si las apartaste. Si partes de cero, se preparan así
(copias byte a byte, D49):

| Origen | Destino |
|---|---|
| `../MicroAgent/decomposition/jpetstore.json` | `evaluation/references/jpetstore-6.json` |
| `../MicroAgent/decomposition/partsunlimited.json` | `evaluation/references/partsunlimited.json` |
| `../MicroAgent/metrics/test/common_dict.json` | `evaluation/common_dicts/jpetstore-6.json` |

`evaluation/common_dicts/partsunlimited.json` se genera con el primer comando (sin `--check`). Con `--check`
solo compara y no escribe nada.

```powershell
python -B -X utf8 evaluation/build_common_dict.py
```
```powershell
python -B -X utf8 evaluation/evaluate.py
```

- `evaluate.py` importa sin modificarlos `../MicroAgent/metrics/json_similarity.py` (WS y c2c) y
  `common_metrics.py` (P/R/F1 de clases comunes). La opción `-B` evita que se escriba `__pycache__` dentro de
  `MicroAgent/`.
- `build_common_dict.py` reconstruye el `common_dict` de PartsUnlimitedMRP (D50). Primero verifica que la misma
  regla reproduce el de JPetStore que publica el artefacto. Si no coincide, aborta sin escribir.

Salidas en `evaluation/`:

| Archivo | Contenido |
|---|---|
| `results.csv` | una fila por corrida, más media, desviación muestral, mediana, mínimo y máximo por (app, configuración) |
| `results_e4_repeticiones.csv` | las 5 repeticiones aisladas de la Etapa 4 |
| `sanity_check.json` | cada referencia evaluada contra sí misma (todo en 1,0) |
| `error_analysis.md` / `.json` | clases mal asignadas frente a la referencia, por corrida y servicio |
| `raw/` | salida completa de los scripts originales |

Correspondencia con el paper: WS = `metrics_m2.weighted_average`; c2c@X = `metrics_m2.above_X` (el script usa
`>` y el paper dice `≥`, D52); el F1 de clases comunes se reporta micro y macro (D53).

---

## 9. Corridas incluidas

| App | MicroAgent (tabla principal) | Línea base | Aparte |
|---|---|---|---|
| JPetStore | `claude-run4` … `claude-run13` | `baseline-run1` … `baseline-run3` | `claude-run1` … `run3` (2.1.327), `claude-run1-e4-r01` … `r05` (Etapa 4 aislada), `smoke-test` |
| PartsUnlimitedMRP | `claude-run4` … `claude-run6` | `baseline-run1` … `baseline-run3` | `claude-run1` … `run3` (2.1.327) |

La especificación pedía 3 corridas por configuración (§10). En MicroAgent con JPetStore se hicieron 10 porque la
Etapa 4 variaba mucho entre corridas (D58).

La tabla principal usa solo corridas con Claude Code 2.1.330. Las corridas de MicroAgent hechas antes con 2.1.327 se
repitieron con 2.1.330 usando `run_id` nuevos (D60). Las originales se conservan y `evaluate.py` las evalúa como
la configuración `microagent_cc2.1.327`. Si una corrida no tiene la versión que le corresponde según su
configuración, `evaluate.py` se detiene.

Versión de Claude Code de cada grupo, según los `run_manifest.json` (D48, D58, D60):

| Versión | Qué se corrió con ella |
|---|---|
| 2.1.325 | Fase 1 (resúmenes de PartsUnlimitedMRP) y pruebas de humo |
| 2.1.327 | `claude-run1` a `run3` de las dos apps y las 5 repeticiones de la Etapa 4 (todo fuera de la tabla principal) |
| 2.1.330 | JPetStore `claude-run4` a `run13`; PartsUnlimitedMRP `claude-run4` a `run6`; las 6 corridas de la línea base |

---

## 10. Comprobaciones rápidas (sin gastar cupo)

```powershell
python scripts/check_microagent_untouched.py
```
```powershell
python -X utf8 scripts/smoke_test_tools.py
```
```powershell
python -X utf8 scripts/check_prompts.py
```
```powershell
python -X utf8 scripts/test_pipeline_offline.py
```
```powershell
python -B -X utf8 scripts/test_baseline_offline.py
```
```powershell
python -X utf8 scripts/test_stage4_offline.py
```

- `check_microagent_untouched.py` puede dar `AVISO` en lugar de `OK`. Eso significa que el artefacto está
  intacto, pero hay archivos de más dentro de carpetas `target/` (hoy, 4 en `monolith/PassJava-.../target`; D14).
- `test_pipeline_offline.py` y `test_stage4_offline.py` **exigen apartar antes `evaluation/references/`** (§6),
  porque llaman al orquestador sin `--allow-references`.
- Las pruebas sin cupo reemplazan `claude` por `scripts/fake_claude.py` o `scripts/fake_claude_baseline.py`
  mediante la variable `MICROAGENT_CLAUDE_CMD`. Con el `claude` simulado, el `run_id` tiene que empezar por
  `_prueba-`.
- Dónde escriben: `test_baseline_offline.py` usa una carpeta temporal del sistema. `test_pipeline_offline.py` y
  `test_stage4_offline.py` escriben en `output/<app>/_prueba-*` y borran esas carpetas al terminar (`--keep` las
  conserva). `smoke_test_tools.py` regenera `output/jpetstore-6/smoke-test/` y la deja en su sitio.
