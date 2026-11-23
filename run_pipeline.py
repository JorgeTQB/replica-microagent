"""Orquestador de la replica de MicroAgent con Claude Code (INSTRUCCIONES §7, Fase 4).

Reproduce la logica y el orden de `MicroAgent/microagent/src/microagent/main.py`. Cada agente es una
llamada independiente a `claude -p` con su system prompt, su lista de herramientas MCP y su limite de turnos:

    Etapa 1  Domain        -> domains/domain_clusters.json
    Etapa 2  Clustering    -> una llamada por dominio; domains/<Dominio>.json y domains/all_domains.json
    Etapa 3  Merging       -> solo si len(all_domain_results) != number; domains/merged_domains.json
    Etapa 4  Common Class  -> common_result.json (lo escribe la herramienta write_result_to_json)
    Etapa 5  Review        -> result.json (DESCOMPOSICION FINAL)

Uso:
    python -X utf8 run_pipeline.py --app jpetstore-6 --run-id claude-run1
    python -X utf8 run_pipeline.py --app jpetstore-6 --run-id prueba-humo-etapa1 --only-stage1   (prueba de humo, §7)

Los bloques marcados "main.py NNN-MMM" copian esas lineas del original; no se "mejoran" (principio rector,
§0). Lo que la replica anade alrededor (registro, auditoria y comprobaciones) no cambia lo que recibe el
modelo ni lo que se guarda en la carpeta de salida. Decisiones: DECISIONES.md, Fase 4.

Archivos por etapa en output/<app>/<run_id>/logs/ (<etapa> = 1_domain, 2_clustering_01, 3_merging, ...):
    <etapa>_prompt.txt, <etapa>_system_prompt.txt   bytes exactos entregados a `claude`
    <etapa>_mcp_config.json                          configuracion MCP generada (herramientas del agente)
    <etapa>_stream.jsonl                             flujo completo de `claude --output-format stream-json`
    <etapa>_claude.json                              evento final de `claude` (texto, turnos, duracion, tokens,
                                                     costo) + linea de comandos y entorno usados
    <etapa>_raw.txt, <etapa>_final_answer.txt        texto final completo y respuesta final extraida (D31)
    <etapa>_server.jsonl                             llamadas recibidas por el servidor MCP
    <etapa>_transcript.jsonl                         transcripcion de Claude Code (lo que se envio a la API)
    <etapa>_audit.json                               comprobaciones de aislamiento y de entrega de los prompts
    <etapa>_stderr.txt
y de la corrida: run_manifest.json, run_status.json, pipeline.log.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "prompts"))
sys.path.insert(0, os.path.join(BASE, "scripts"))
import build_prompts as bp  # noqa: E402
from claude_cli import EXTRA_ENV, MCP_ENV, MODEL, SANDBOX  # noqa: E402

MCP_SERVER_NAME = "microagent"
MCP_PREFIX = f"mcp__{MCP_SERVER_NAME}__"

# Herramientas y max_iter de cada agente: crew.py (lineas 71-157) e INSTRUCCIONES §5.3, en el mismo orden.
AGENT_TOOLS = {
    "domain": ["get_all_class_hierarchy", "get_database_summary", "get_all_class_summaries",
               "get_class_basic_info", "get_class_summary"],
    "clustering": ["get_all_class_hierarchy_complete", "get_database_summary", "codebase_semantic_search",
                   "get_related_class_list", "get_class_relation_and_code", "search_file"],
    "merging": ["get_all_class_hierarchy_complete", "get_database_summary", "get_class_relation_and_code",
                "search_file"],
    "common": ["get_all_class_hierarchy_complete", "get_database_summary", "rank_dependency_entropy",
               "assign_common_class_list", "get_more_potential_common_classes", "write_result_to_json",
               "get_class_relation_and_code", "search_file"],
    "review": ["get_all_class_hierarchy_complete", "get_database_summary", "get_class_relation_and_code",
               "search_file", "write_result_to_json", "get_related_class_list"],
}
MAX_TURNS = {"domain": 30, "clustering": 30, "merging": 30, "common": 45, "review": 45}

# Esfuerzo fijo (`output_config.effort` de la API). Sin esta opcion `claude` lo toma de la sesion que lo lanza
# (variable CLAUDE_EFFORT), y dejaria de ser el mismo en todas las corridas (§10.1). "high" es el valor por
# defecto de la API y el que llevaron las 54 llamadas de preparacion de contexto de la Fase 1 (D35).
EFFORT = "high"
# Variables CLAUDE*/ANTHROPIC* que SI se dejan pasar al proceso `claude` (el resto se quita, ver child_env).
ENV_KEEP = {"CLAUDE_CONFIG_DIR"}
# Variables que `claude` lee y que la sesion desde la que se lanza la corrida puede dejar en el entorno (la app
# de escritorio y Claude Code las exportan a sus procesos hijos; no todas empiezan por CLAUDE). Se quitan todas
# y despues se fijan las de la replica: el entorno de `claude` es el mismo se lance desde donde se lance (D35, D38).
ENV_DROP_PREFIXES = ("CLAUDE", "ANTHROPIC", "MCP_", "DISABLE_", "ENABLE_", "MAX_THINKING", "MAX_MCP", "OTEL_", "SENTRY")
ENV_DROP_NAMES = {"AI_AGENT", "API_TIMEOUT_MS", "API_FORCE_IDLE_TIMEOUT", "USE_LOCAL_OAUTH", "USE_STAGING_OAUTH",
                  "BAGGAGE", "MAX_STRUCTURED_OUTPUT_RETRIES", "SLASH_COMMAND_TOOL_CHAR_BUDGET",
                  "TASK_MAX_OUTPUT_LENGTH", "BASH_DEFAULT_TIMEOUT_MS", "BASH_MAX_TIMEOUT_MS", "BASH_MAX_OUTPUT_LENGTH"}
# Valores que fija el orquestador ademas de EXTRA_ENV y MCP_ENV (D38):
#   DISABLE_AUTOUPDATER             la version de Claude Code no cambia a mitad del experimento
#   API_TIMEOUT_MS                  el mismo valor con el que se hizo la prueba de humo
#   CLAUDE_CODE_DISABLE_CLAUDE_MDS  no se carga ningun CLAUDE.md (de _sandbox/ ni de carpetas superiores)
#   CLAUDE_CODE_DISABLE_AUTO_MEMORY no se carga ni se escribe memoria automatica
#   PYTHONDONTWRITEBYTECODE         el servidor MCP no deja __pycache__ en tools/
PIPELINE_ENV = {"DISABLE_AUTOUPDATER": "1", "API_TIMEOUT_MS": "900000", "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
                "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "PYTHONDONTWRITEBYTECODE": "1"}
# Lo unico que Claude Code 2.1.325 anade por su cuenta en `claude -p` (D4, D24, D35): un bloque de system antes
# del de la replica y cinco bloques <system-reminder> antes del mensaje de usuario, que se reconocen por como
# empiezan. Cualquier otra cosa (un CLAUDE.md, una memoria, un bloque nuevo) es contexto que no es de la replica
# y la llamada no vale (D38).
CLAUDE_CODE_SYSTEM_BLOCK = "You are a Claude agent, built on Anthropic's Claude Agent SDK."
CLAUDE_CODE_USER_BLOCKS = [
    ("entorno", "<system-reminder>\n# Environment\nYou have been invoked in the following environment: \n"),
    ("modelo", "<system-reminder>\nYou are powered by the model named "),
    ("tokens", "<system-reminder>\n<total_tokens>"),
    ("cuenta", "<system-reminder>\nAs you answer the user's questions, you can use the following context:\n# userEmail\n"),
    ("fecha", "<system-reminder>\nToday's date is "),
]

# Etiqueta de respuesta final de CrewAI (crewai/agents/constants.py, 1.8.1).
FINAL_ANSWER_ACTION = "Final Answer:"
# Texto con el que CrewAI 1.8.1 pide la respuesta final cuando un agente agota `max_iter`
# (crewai/translations/en.json, clave errors.force_final_answer; lo usa agent_utils.handle_max_iterations_exceeded).
# La replica lo envia igual cuando un agente agota --max-turns (decision de Jorge, D39).
FORCE_FINAL_ANSWER = ("Now it's time you MUST give your absolute best final answer. You'll ignore all previous "
                      "instructions, stop using any tools, and just return your absolute BEST Final answer.")
# Identificadores reservados: `smoke-test` es la particion artificial de la Fase 2 (D21).
RESERVED_RUN_IDS = {"smoke-test"}
TEST_RUN_PREFIX = "_prueba-"  # las corridas con el `claude` simulado solo pueden usar este prefijo


# --------------------------------------------------------------------------------------------------
# Copias literales del original
# --------------------------------------------------------------------------------------------------
def clean_json_output(output):
    # Copia literal de main.py 21-46.
    json_object_pattern = r"```(?:json)?\s*({[\s\S]*?})\s*```"
    json_array_pattern = r"```(?:json)?\s*(\[[\s\S]*?\])\s*```"

    match = re.search(json_object_pattern, output)
    if match:
        return match.group(1)

    match = re.search(json_array_pattern, output)
    if match:
        return match.group(1)

    try:
        start = output.find('{')
        end = output.rfind('}') + 1
        if start != -1 and end > start:
            return output[start:end]

        start = output.find('[')
        end = output.rfind(']') + 1
        if start != -1 and end > start:
            return output[start:end]
    except:
        pass

    return output


def extract_final_answer(text: str):
    """Respuesta final de un agente, como la obtiene CrewAI 1.8.1 (crewai/agents/parser.py::parse, rama
    `includes_answer`): lo que sigue a la ULTIMA aparicion de "Final Answer:", sin espacios en los extremos
    y sin una cerca ``` final desparejada. Es el `.raw` que main.py limpia con clean_json_output y el texto
    que se pasa como contexto a la tarea siguiente (D27, D31).

    Devuelve (respuesta, tenia_etiqueta). Si el texto no trae la etiqueta, CrewAI le reclamaria el formato al
    LLM; la replica no tiene equivalente y toma el texto completo recortado (decision de Jorge, D31)."""
    if FINAL_ANSWER_ACTION not in text:
        return text.strip(), False
    final_answer = text.split(FINAL_ANSWER_ACTION)[-1].strip()
    # Check whether the final answer ends with triple backticks.
    if final_answer.endswith("```"):
        # Count occurrences of triple backticks in the final answer.
        count = final_answer.count("```")
        # If count is odd then it's an unmatched trailing set; remove it.
        if count % 2 != 0:
            final_answer = final_answer[:-3].rstrip()
    return final_answer, True


# --------------------------------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------------------------------
class StageFailure(Exception):
    """Una llamada a un agente no es valida (error de `claude`, limite de turnos, servidor MCP sin conectar,
    herramientas distintas de las del agente...). La corrida se registra como fallida (§10.4)."""

    def __init__(self, etapa: str, motivo: str, detalle: str = ""):
        super().__init__(f"{etapa}: {motivo}" + (f" -- {detalle}" if detalle else ""))
        self.etapa, self.motivo, self.detalle = etapa, motivo, detalle


class PipelineStop(Exception):
    """Puntos en los que main.py hace `return` y deja el flujo sin terminar (lineas 105, 110, 116 y 179)."""

    def __init__(self, etapa: str, motivo: str):
        super().__init__(f"{etapa}: {motivo}")
        self.etapa, self.motivo = etapa, motivo


def now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_text(path: str, text: str) -> None:
    """UTF-8 y saltos de linea LF, como escribiria el original en Linux o macOS (alli `open(path, 'w')`)."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def write_json(path: str, obj, **kwargs) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, **kwargs)


def dump_result(path: str, obj) -> None:
    """`json.dump(obj, f, indent=2)`, que es como main.py escribe todos sus JSON de salida."""
    write_json(path, obj, indent=2)


_WINDOWS_FORBIDDEN = re.compile(r'[<>:"\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def domain_file_name(domain_name: str):
    """Nombre de `domains/<Dominio>.json`. Devuelve (nombre_del_original, nombre_usado).
    El original solo reemplaza `/` por `-` (main.py 238, 315 y 326). En Windows, ademas, hay caracteres que un
    nombre de archivo no admite: se sustituyen por `_` SOLO en la ruta, nunca en los prompts ni en los JSON (D29)."""
    original = domain_name.replace("/", "-")
    used = _WINDOWS_FORBIDDEN.sub("_", original).rstrip(" .") or "_"
    if used.split(".")[0].upper() in _WINDOWS_RESERVED:
        used = "_" + used
    return original, used


def context_fingerprint(app: str) -> dict:
    """SHA-256 de todo lo que las herramientas leen como contexto de la aplicacion: `context/<app>/`,
    `database/<app>/` y los archivos fuente que cita `class_summaries.json` (D32: el contexto debe ser el
    mismo en todas las corridas)."""
    files = {}
    for folder in ("context", "database"):
        root = os.path.join(BASE, folder, app)
        for dirpath, _, names in os.walk(root):
            for name in names:
                path = os.path.join(dirpath, name)
                files[os.path.relpath(path, BASE).replace("\\", "/")] = sha256_file(path)
    with open(os.path.join(BASE, "context", app, "class_summaries.json"), encoding="utf-8") as f:
        summaries = json.load(f)
    for info in summaries.values():
        rel = info["file_path"].replace("\\", "/")
        files[rel] = sha256_file(os.path.join(BASE, rel))
    digest = sha256_bytes(json.dumps(files, sort_keys=True).encode("utf-8"))
    return {"app": app, "digest": digest, "n_files": len(files), "files": dict(sorted(files.items()))}


def pipeline_files_fingerprint() -> dict:
    """Informativo: version de los archivos que definen lo que recibe el modelo."""
    paths = [
        os.path.join(BASE, "run_pipeline.py"),
        os.path.join(BASE, "prompts", "build_prompts.py"),
        os.path.join(BASE, "scripts", "claude_cli.py"),
        os.path.join(BASE, "tools", "custom_tools.py"),
        os.path.join(BASE, "tools", "mcp_server.py"),
        os.path.join(BASE, "tools", "microagent_shim.py"),
        os.path.join(bp.ORIGINAL_CONFIG_DIR, "agents.yaml"),
        os.path.join(bp.ORIGINAL_CONFIG_DIR, "tasks.yaml"),
    ]
    return {os.path.relpath(p, os.path.dirname(BASE)).replace("\\", "/"): sha256_file(p) for p in paths}


def clean_path(path_str):
    """Copia de `clean_path` de custom_tools.py (lineas 48-60). Solo se usa para AUDITAR las rutas que pidio
    el agente; las herramientas usan la suya."""
    if isinstance(path_str, str):
        path_str = path_str.strip()
        if (path_str.startswith('"') and path_str.endswith('"')) or \
                (path_str.startswith("'") and path_str.endswith("'")):
            path_str = path_str[1:-1]
        elif path_str.endswith('"') or path_str.endswith("'"):
            path_str = path_str[:-1]
        elif path_str.startswith('"') or path_str.startswith("'"):
            path_str = path_str[1:]
        path_str = path_str.strip()
    return path_str


def classify_path(path, app: str, run_id: str) -> dict:
    """Resuelve una ruta como lo hace `search_file` (custom_tools.py 265-279) y dice donde cae (D23, D32)."""
    info = {"pedida": path}
    if not isinstance(path, str):
        info.update(resuelta=None, existe=False, zona="no_es_texto")
        return info
    file_path = clean_path(path)
    if not os.path.isabs(file_path):
        full_path = os.path.join(BASE, file_path)
        if not os.path.exists(full_path):
            resource_path = os.path.join(BASE, "resources", app, file_path)
            if os.path.exists(resource_path):
                full_path = resource_path
        file_path = full_path
    resolved = os.path.normcase(os.path.realpath(file_path))

    def inside(*parts):
        root = os.path.normcase(os.path.realpath(os.path.join(BASE, *parts)))
        return resolved == root or resolved.startswith(root + os.sep)

    if inside("resources", app):
        zona = "resources_app"
    elif inside("output", app, run_id):
        zona = "salida_de_esta_corrida"
    elif inside("output") or inside("logs") or inside("evaluation"):
        zona = "contaminante"  # salidas de otras corridas, registros o evaluacion
    elif os.path.normcase(os.path.realpath(os.path.join(os.path.dirname(BASE), "MicroAgent", "decomposition"))) in resolved:
        zona = "contaminante"  # descomposiciones de referencia del artefacto
    else:
        zona = "fuera_de_resources_app"
    info.update(resuelta=file_path, existe=os.path.isfile(file_path), zona=zona)
    return info


def find_transcript(session_id: str):
    """Transcripcion que Claude Code guarda de cada sesion: ~/.claude/projects/<carpeta>/<session_id>.jsonl."""
    home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    hits = glob.glob(os.path.join(home, "projects", "*", f"{session_id}.jsonl"))
    return hits[0] if hits else None


def analyze_transcript(path: str, system_prompt: str, user_prompt: str) -> dict:
    """Que se envio de verdad a la API en la primera peticion de la sesion (D4, D24, D29):
    system prompt, bloques del primer mensaje de usuario, herramientas y parametros de muestreo."""
    shapes, first_user, params = [], None, []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = ev.get("type")
            if kind == "api-request-shape":
                shapes.append(ev.get("shape") or {})
            elif kind == "api-request-blob" and first_user is None:
                msg = ev.get("message") or {}
                if msg.get("role") == "user":
                    first_user = msg
            elif kind == "api-request":
                params.append(ev.get("params") or {})
    out = {"archivo": os.path.basename(path), "peticiones_api": len(params), "formas_de_peticion": len(shapes)}
    if not shapes or first_user is None:
        out["legible"] = False
        return out
    out["legible"] = True

    def texts(content):
        if isinstance(content, str):
            return [content]
        return [b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text"]

    system_blocks = texts(shapes[0].get("system"))
    out["system_bloques"] = [{"caracteres": len(t), "sha256": sha256_bytes(t.encode("utf-8")),
                              "es_el_de_la_replica": t == system_prompt, "inicio": t[:80]} for t in system_blocks]
    out["system_entregado_identico"] = system_prompt in system_blocks
    out["system_contenido_en_lo_enviado"] = system_prompt in "".join(system_blocks)
    out["system_solo_recortado"] = (not out["system_contenido_en_lo_enviado"]
                                    and system_prompt.strip() in "".join(system_blocks))
    user_blocks = texts(first_user.get("content"))
    out["usuario_entregado_identico"] = bool(user_blocks) and user_blocks[-1] == user_prompt
    out["usuario_solo_recortado"] = (bool(user_blocks) and not out["usuario_entregado_identico"]
                                     and user_blocks[-1].strip() == user_prompt.strip())
    added = user_blocks[:-1] if user_blocks else []
    out["usuario_bloques_anadidos_por_claude_code"] = [{"caracteres": len(t), "inicio": t[:60]} for t in added]
    out["contexto_anadido_inesperado"] = unexpected_context(system_blocks, added, system_prompt)
    out["herramientas_en_la_peticion"] = sorted({t.get("name") for s in shapes for t in s.get("tools") or []
                                                 if isinstance(t, dict)})
    # Cada forma de peticion por separado: la union podria ocultar una peticion sin herramientas o con otras.
    out["herramientas_por_forma_de_peticion"] = [sorted(t.get("name") for t in s.get("tools") or [] if isinstance(t, dict))
                                                 for s in shapes]
    distinct = []
    for p in params:
        slim = {k: p.get(k) for k in ("model", "max_tokens", "thinking", "temperature", "output_config")}
        if slim not in distinct:
            distinct.append(slim)
    out["parametros_de_las_peticiones"] = distinct
    return out


def analyze_forced(path: str, force_text: str) -> dict:
    """Como llego a la API el mensaje que pide la respuesta final (D39): se busca, en la transcripcion de la
    sesion reanudada, el ultimo mensaje de usuario con texto y se compara su ultimo bloque con `force_text`."""
    user_texts, params = [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "api-request-blob":
                msg = ev.get("message") or {}
                content = msg.get("content")
                if msg.get("role") == "user":
                    texts = [content] if isinstance(content, str) else [
                        b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text"]
                    if texts:
                        user_texts.append(texts)
            elif ev.get("type") == "api-request":
                params.append(ev.get("params") or {})
    out = {"archivo": os.path.basename(path), "peticiones_api_en_la_transcripcion": len(params),
           "mensajes_de_usuario_con_texto": len(user_texts)}
    last = user_texts[-1] if user_texts else []
    out["encontrado"] = len(user_texts) >= 2 and bool(last)  # el primero es el prompt del agente
    out["identico"] = out["encontrado"] and last[-1] == force_text
    out["bloques_antepuestos"] = [{"caracteres": len(t), "inicio": t[:60]} for t in last[:-1]] if out["encontrado"] else []
    out["bloques_antepuestos_inesperados"] = [
        t[:60] for t in (last[:-1] if out["encontrado"] else [])
        if not (t.startswith("<system-reminder>") and t.rstrip().endswith("</system-reminder>")
                and "\n# claudeMd" not in t and "\n# memory" not in t.lower())]
    distinct = []
    for prm in params:
        slim = {k: prm.get(k) for k in ("model", "max_tokens", "thinking", "temperature", "output_config")}
        if slim not in distinct:
            distinct.append(slim)
    out["parametros_de_las_peticiones"] = distinct
    return out


def unexpected_context(system_blocks: list, added_user_blocks: list, system_prompt: str) -> list:
    """Contexto que Claude Code envio y que no es ni de la replica ni lo que anade siempre (D38).
    Devuelve la lista de problemas (vacia si lo enviado es exactamente lo esperado)."""
    problems = []
    expected_system = [CLAUDE_CODE_SYSTEM_BLOCK] + ([system_prompt] if system_prompt else [])
    if system_blocks != expected_system:
        problems.append("bloques de system enviados: "
                        + str([(len(t), t[:50]) for t in system_blocks if t != system_prompt])
                        + " (se esperaba solo el de Claude Code y, despues, el de la replica)")
    if len(added_user_blocks) != len(CLAUDE_CODE_USER_BLOCKS):
        problems.append(f"{len(added_user_blocks)} bloques antepuestos al mensaje de usuario "
                        f"(se esperaban {len(CLAUDE_CODE_USER_BLOCKS)}): {[t[:50] for t in added_user_blocks]}")
    else:
        for (name, start), text in zip(CLAUDE_CODE_USER_BLOCKS, added_user_blocks):
            if not text.startswith(start) or not text.rstrip().endswith("</system-reminder>"):
                problems.append(f"el bloque '{name}' antepuesto al mensaje de usuario no es el esperado: {text[:60]!r}")
            elif text.count("\n# ") != (1 if name in ("entorno", "cuenta") else 0):
                # una seccion mas ("# claudeMd", "# memory"...) es contexto que no es de la replica
                problems.append(f"el bloque '{name}' trae secciones que no son las de siempre: "
                                f"{[line for line in text.splitlines() if line.startswith('# ')]}")
    return problems


def child_env() -> tuple:
    """Entorno del proceso `claude`: el del sistema SIN las variables heredadas que `claude` lee
    (ENV_DROP_PREFIXES, ENV_DROP_NAMES), mas las que fija la replica (PIPELINE_ENV, MAX_THINKING_TOKENS,
    MCP_TIMEOUT, MCP_TOOL_TIMEOUT). Si el orquestador se lanza desde una sesion de Claude Code o desde la app de
    escritorio, esas variables (CLAUDE_EFFORT, CLAUDE_CODE_ENTRYPOINT, DISABLE_MICROCOMPACT...) pueden cambiar
    lo que `claude` envia al modelo; quitandolas, una corrida es igual se lance desde donde se lance (D35, D38).
    Devuelve (entorno, nombres quitados)."""
    removed = sorted(k for k in os.environ
                     if (k.upper().startswith(ENV_DROP_PREFIXES) or k.upper() in ENV_DROP_NAMES)
                     and k.upper() not in ENV_KEEP)
    env = {k: v for k, v in os.environ.items() if k not in removed}
    env.update(PIPELINE_ENV)
    env.update(EXTRA_ENV)
    env.update(MCP_ENV)
    return env, removed


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":  # `claude` lanza el servidor MCP como proceso hijo
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.kill()


# --------------------------------------------------------------------------------------------------
# Orquestador
# --------------------------------------------------------------------------------------------------
class Pipeline:
    def __init__(self, args):
        self.app, self.run_id, self.model = args.app, args.run_id, args.model
        self.number, self.num = str(args.number), str(args.num)
        self.only_stage1 = args.only_stage1
        self.stage_timeout = args.stage_timeout
        self.max_turns_override = args.max_turns_override
        self.run_dir = os.path.join(BASE, "output", self.app, self.run_id)
        self.domains_dir = os.path.join(self.run_dir, "domains")
        self.logs_dir = os.path.join(self.run_dir, "logs")
        fake = os.environ.get("MICROAGENT_CLAUDE_CMD")
        self.simulated = bool(fake)
        self.claude_cmd = json.loads(fake) if fake else [shutil.which("claude") or ""]
        self.claude_version = ""
        self.stages, self.observations = [], []
        self.status = {"app": self.app, "run_id": self.run_id, "modelo": self.model, "number": self.number,
                       "num": self.num, "simulado": self.simulated, "solo_etapa1": self.only_stage1,
                       "estado": "en_curso", "inicio": now(), "fin": None, "fallo": None, "fusion": "no_alcanzada",
                       "etapas": self.stages, "observaciones": self.observations, "totales": {}, "resultado": None}

    # ---------------------------------------------------------------- registro
    def log(self, msg: str = "") -> None:
        print(msg, flush=True)
        with open(os.path.join(self.logs_dir, "pipeline.log"), "a", encoding="utf-8", newline="\n") as f:
            f.write(f"[{now()}] {msg}\n")

    def observe(self, etapa: str, tipo: str, detalle) -> None:
        self.observations.append({"etapa": etapa, "tipo": tipo, "detalle": detalle})
        self.log(f"  [OBSERVACION] {etapa}: {tipo}: {detalle}")

    def save_status(self) -> None:
        # "turnos" es la suma de `num_turns` de Claude Code (no son peticiones; ver "peticiones_api", D33, D40).
        totals = {"llamadas": len(self.stages), "turnos": 0, "peticiones_api": 0, "duracion_ms": 0, "duracion_api_ms": 0,
                  "costo_usd": 0.0, "llamadas_a_herramientas": 0,
                  "tokens": {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
                             "cache_read_input_tokens": 0}}
        for s in self.stages:
            totals["turnos"] += s.get("turnos") or 0
            totals["peticiones_api"] += s.get("peticiones_api") or 0
            totals["duracion_ms"] += s.get("duracion_ms") or 0
            totals["duracion_api_ms"] += s.get("duracion_api_ms") or 0
            totals["costo_usd"] += s.get("costo_usd") or 0.0
            totals["llamadas_a_herramientas"] += s.get("llamadas_a_herramientas") or 0
            for k in totals["tokens"]:
                totals["tokens"][k] += (s.get("tokens") or {}).get(k) or 0
        self.status["totales"] = totals
        write_json(os.path.join(self.logs_dir, "run_status.json"), self.status, indent=2, ensure_ascii=False)

    # ---------------------------------------------------------------- preparacion
    def prepare(self, allow_references: bool) -> None:
        expected = bp.APPS[self.app]
        if (self.number, self.num) != expected:
            sys.exit(f"--number/--num no corresponden a {self.app}: se esperaba {expected} (§4.2, §4.3)")
        if self.run_id in RESERVED_RUN_IDS or not re.fullmatch(r"[A-Za-z0-9_.\-]+", self.run_id):
            sys.exit(f"--run-id no valido o reservado: {self.run_id!r}")
        if self.simulated != self.run_id.startswith(TEST_RUN_PREFIX):
            sys.exit(f"el prefijo {TEST_RUN_PREFIX!r} es obligatorio y exclusivo de las corridas con `claude` "
                     f"simulado (MICROAGENT_CLAUDE_CMD)")
        if self.max_turns_override is not None and not self.only_stage1:
            sys.exit("--max-turns-override solo se admite con --only-stage1 (comprobacion de D2, no es una corrida)")
        if not self.claude_cmd[0]:
            sys.exit("no se encontro el ejecutable 'claude' en el PATH")
        if not sys.flags.utf8_mode:
            sys.exit("ejecutar en modo UTF-8: python -X utf8 run_pipeline.py ...")
        if os.path.isdir(self.run_dir) and os.listdir(self.run_dir):
            sys.exit(f"ya existe {self.run_dir}: una corrida nunca se sobrescribe; usa otro --run-id (§10.4)")
        os.makedirs(SANDBOX, exist_ok=True)
        if os.listdir(SANDBOX):
            sys.exit(f"_sandbox no esta vacio: {os.listdir(SANDBOX)}")
        references = os.path.join(BASE, "evaluation", "references")
        refs_present = sorted(os.listdir(references)) if os.path.isdir(references) else []
        if refs_present and not allow_references:
            sys.exit(f"evaluation/references/ contiene {refs_present}: las descomposiciones de referencia no deben "
                     f"estar al alcance de las herramientas durante las corridas (D23, D32). Apartalas o usa "
                     f"--allow-references (queda registrado).")

        fingerprint = context_fingerprint(self.app)
        baseline_path = os.path.join(BASE, "logs", "context_fingerprint", f"{self.app}.json")
        baseline_note = "sin linea base (corrida simulada)"
        if os.path.exists(baseline_path):
            with open(baseline_path, encoding="utf-8") as f:
                baseline = json.load(f)
            if baseline["digest"] != fingerprint["digest"]:
                changed = sorted(k for k in set(baseline["files"]) | set(fingerprint["files"])
                                 if baseline["files"].get(k) != fingerprint["files"].get(k))
                sys.exit(f"el contexto de {self.app} cambio respecto a la primera corrida ({baseline['run_id']}, "
                         f"{baseline['fecha']}). Archivos distintos: {changed}. Se aborta (D32).")
            baseline_note = f"igual al de la primera corrida ({baseline['run_id']}, {baseline['fecha']})"
        elif not self.simulated:
            os.makedirs(os.path.dirname(baseline_path), exist_ok=True)
            write_json(baseline_path, {"run_id": self.run_id, "fecha": now(), **fingerprint}, indent=1)
            baseline_note = "primera corrida de la aplicacion: se guarda como linea base"

        os.makedirs(self.domains_dir, exist_ok=True)  # main.py 59-61
        os.makedirs(self.logs_dir, exist_ok=True)
        version = ""
        if not self.simulated:
            proc = subprocess.run([self.claude_cmd[0], "--version"], capture_output=True, timeout=120, env=child_env()[0])
            version = proc.stdout.decode("utf-8", errors="replace").strip()
            self.claude_version = version.split()[0] if version else ""
        manifest = {
            "app": self.app, "run_id": self.run_id, "number": self.number, "num": self.num,
            "modelo_pedido": self.model, "simulado": self.simulated, "solo_etapa1": self.only_stage1,
            "max_turns_override": self.max_turns_override, "fecha": now(), "argv": sys.argv,
            "claude_code_version": version, "claude_cmd": self.claude_cmd,
            "python": sys.version, "plataforma": platform.platform(),
            "entorno_de_claude": {**PIPELINE_ENV, **EXTRA_ENV, **MCP_ENV},
            "esfuerzo": EFFORT,
            # Solo los NOMBRES (algunas pueden contener credenciales): las quitadas no llegan al proceso `claude`.
            "variables_quitadas_del_entorno": child_env()[1],
            "variables_que_recibe_claude": sorted(child_env()[0]),
            "herramientas_por_agente": AGENT_TOOLS, "max_turns": MAX_TURNS,
            "referencias_presentes": refs_present,
            "contexto": {"comparacion": baseline_note, **fingerprint},
            "archivos_del_pipeline_sha256": pipeline_files_fingerprint(),
        }
        write_json(os.path.join(self.logs_dir, "run_manifest.json"), manifest, indent=1, ensure_ascii=False)
        self.save_status()
        self.log(f"Corrida {self.run_id} de {self.app} (number={self.number}, num={self.num}, modelo={self.model}"
                 f"{', SIMULADA' if self.simulated else ''})")
        self.log(f"Contexto: {fingerprint['n_files']} archivos, sha256 {fingerprint['digest'][:16]}... ({baseline_note})")

    # ---------------------------------------------------------------- una llamada a un agente
    def call_agent(self, etapa: str, prompt: bp.Prompt, result_file: str | None = None, extra: dict | None = None) -> dict:
        """Una ejecucion de agente = un proceso `claude -p` nuevo, con su propio servidor MCP.
        Devuelve {"raw": texto final completo, "final_answer": respuesta final (D31), ...}."""
        stage = prompt.stage
        tools = AGENT_TOOLS[stage]
        allowed = [MCP_PREFIX + t for t in tools]
        max_turns = self.max_turns_override or MAX_TURNS[stage]
        path = lambda suffix: os.path.join(self.logs_dir, f"{etapa}_{suffix}")  # noqa: E731

        user_path, _ = bp.save_prompt(self.logs_dir, etapa, prompt)  # bytes exactos (§6)
        env_server = {"APP_NAME": self.app, "RUN_ID": self.run_id, "MICROAGENT_TOOLS": ",".join(tools),
                      "MICROAGENT_LOG": path("server.jsonl")}
        if result_file:
            env_server["RESULT_FILE"] = os.path.abspath(result_file)
        mcp_config = {"mcpServers": {MCP_SERVER_NAME: {
            "command": sys.executable,
            "args": ["-X", "utf8", os.path.join(BASE, "tools", "mcp_server.py")],
            "env": env_server,
        }}}
        write_json(path("mcp_config.json"), mcp_config, indent=2)

        common = ["--model", self.model,
                  "--effort", EFFORT,
                  "--system-prompt", prompt.system,
                  "--tools", "",                                # sin herramientas integradas (§5.3)
                  "--mcp-config", path("mcp_config.json"), "--strict-mcp-config"]
        tail = ["--disable-slash-commands", "--setting-sources", ""]
        output = ["--output-format", "stream-json", "--verbose"]
        args = ["-p"] + common + ["--allowedTools", ",".join(allowed)] + tail + ["--max-turns", str(max_turns)] + output
        env, env_removed = child_env()

        if os.listdir(SANDBOX):
            raise StageFailure(etapa, "sandbox_no_vacio", str(os.listdir(SANDBOX)))
        self.log(f"\n>>> {etapa} ({prompt.agent}; {len(tools)} herramientas; max-turns {max_turns}; "
                 f"prompt {len(prompt.user)} caracteres)")
        first = self._run_claude(args, user_path, path("stream.jsonl"), path("stderr.txt"), allowed, env)

        # Limite de turnos (D39, decision de Jorge): como CrewAI al agotar max_iter, no se falla; se hace UNA
        # peticion mas en la misma sesion pidiendo la respuesta final con el texto de CrewAI. Las herramientas
        # siguen declaradas (como en el original, donde siguen descritas en el system prompt), pero sin
        # --allowedTools: si el modelo pidiera alguna, Claude Code la deniega y no se ejecuta (en el original
        # tampoco se ejecuta nada en esa llamada).
        forced, forced_args = None, None
        first_result = first["result"] or {}
        if (not first["timed_out"] and not first["early_abort"] and first_result.get("subtype") == "error_max_turns"
                and first_result.get("session_id")):
            forced_args = (["-p", "--resume", first_result["session_id"]] + common + tail + ["--max-turns", "1"] + output)
            write_text(path("forzada_prompt.txt"), FORCE_FINAL_ANSWER)
            if os.listdir(SANDBOX):
                raise StageFailure(etapa, "sandbox_no_vacio", str(os.listdir(SANDBOX)))
            self.log(f"    {etapa}: el agente agoto sus {max_turns} peticiones; se pide la respuesta final como hace "
                     f"CrewAI (una peticion mas en la sesion {first_result['session_id']})")
            forced = self._run_claude(forced_args, path("forzada_prompt.txt"), path("forzada_stream.jsonl"),
                                      path("forzada_stderr.txt"), allowed, env)
        runs = [first] + ([forced] if forced else [])
        last = runs[-1]
        result_ev = last["result"]
        events = [e for r in runs for e in r["events"]]
        init = first["init"]
        elapsed = round(sum(r["elapsed"] for r in runs), 1)

        raw = (result_ev or {}).get("result")
        raw = raw if isinstance(raw, str) else ""
        asked_tools = False
        if forced and (result_ev or {}).get("subtype") == "error_max_turns":
            # El modelo pidio herramientas en la respuesta forzada. CrewAI toma el texto de esa respuesta tal cual
            # (handle_max_iterations_exceeded convierte un AgentAction en AgentFinish con su texto).
            asked_tools = True
            raw = "".join(b.get("text", "") for e in forced["events"] if e.get("type") == "assistant"
                          for b in ((e.get("message") or {}).get("content") or [])
                          if isinstance(b, dict) and b.get("type") == "text")

        record = dict(result_ev or {})
        record.update({"_exit_code": last["returncode"], "_cmd": args, "_claude_cmd": self.claude_cmd,
                       "_env": {**PIPELINE_ENV, **EXTRA_ENV, **MCP_ENV}, "_env_quitado": env_removed,
                       "_env_nombres": sorted(env), "_cwd": SANDBOX, "_init": init, "_mcp_config": mcp_config,
                       "_wall_seconds": elapsed})
        if forced:
            record.update({"_primera_llamada": first["result"], "_primera_llamada_exit_code": first["returncode"],
                           "_forzada": {"cmd": forced_args, "init": forced["init"], "exit_code": forced["returncode"],
                                        "wall_seconds": forced["elapsed"], "pidio_herramientas": asked_tools}})
        write_json(path("claude.json"), record, indent=1, ensure_ascii=False)

        final_answer, has_label = extract_final_answer(raw)
        write_text(path("raw.txt"), raw)
        write_text(path("final_answer.txt"), final_answer)

        # La auditoria principal usa la sesion de la primera llamada (alli esta el prompt del agente).
        audit = self._audit(etapa, prompt, allowed, events, init, first["result"], has_label)
        if forced:
            audit["respuesta_forzada"] = self._audit_forced(etapa, forced, first_result.get("session_id"), asked_tools)
            audit["problemas"].extend(audit["respuesta_forzada"]["problemas"])
            audit["observaciones"].extend(audit["respuesta_forzada"]["observaciones"])
        write_json(path("audit.json"), audit, indent=1, ensure_ascii=False)

        results = [r["result"] or {} for r in runs]
        total = lambda key: sum(r.get(key) or 0 for r in results)  # noqa: E731
        # En una sesion reanudada (Claude Code 2.1.325, comprobado en D39) `total_cost_usd`, `duration_api_ms` y
        # `modelUsage` son ACUMULADOS de la sesion; `usage`, `num_turns` y `duration_ms` son solo de esa llamada.
        # Si la llamada forzada no devuelve resultado, vale el acumulado de la primera (no se pierde lo gastado).
        cumulative = lambda key: (max([r[key] for r in results if r.get(key) is not None], default=None)  # noqa: E731
                                  if forced else total(key))
        # Peticiones a la API (lo que limita --max-turns, D33): mensajes de asistente distintos del flujo.
        # `num_turns` no sirve: con error_max_turns vale peticiones + 1, y con success, llamadas a herramientas + 1.
        requests = len({(e.get("message") or {}).get("id") or id(e) for e in events if e.get("type") == "assistant"})
        if forced and forced["result"]:
            session_usage = (forced["result"].get("modelUsage") or {}).get(self.model) or {}
            output_sum = sum((r.get("usage") or {}).get("output_tokens") or 0 for r in results)
            if session_usage and session_usage.get("outputTokens") != output_sum:
                audit["observaciones"].append(("contabilidad_de_la_sesion_reanudada_no_cuadra",
                                               f"modelUsage.outputTokens={session_usage.get('outputTokens')}, suma de "
                                               f"las dos llamadas={output_sum}: revisar costo y tokens de esta etapa"))
                write_json(path("audit.json"), audit, indent=1, ensure_ascii=False)
        entry = {"etapa": etapa, "agente": prompt.agent, "session_id": (first["result"] or init or {}).get("session_id"),
                 "subtype": (result_ev or {}).get("subtype"), "is_error": (result_ev or {}).get("is_error"),
                 "turnos": total("num_turns") if any(r.get("num_turns") is not None for r in results) else None,
                 "max_turns": max_turns, "peticiones_api": requests,
                 "duracion_ms": total("duration_ms"), "duracion_api_ms": cumulative("duration_api_ms"),
                 "costo_usd": cumulative("total_cost_usd"),
                 "tokens": {k: sum((r.get("usage") or {}).get(k) or 0 for r in results)
                            for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                      "cache_read_input_tokens")},
                 "llamadas_a_herramientas": len(audit["llamadas"]), "herramientas_usadas": audit["llamadas_por_herramienta"],
                 "etiqueta_final_answer": has_label, "caracteres_respuesta": len(final_answer),
                 "limite_de_turnos": bool(forced),
                 "problemas": audit["problemas"]}
        if forced:
            entry["respuesta_forzada"] = {
                "session_id": (forced["result"] or forced["init"] or {}).get("session_id"),
                "subtype": (forced["result"] or {}).get("subtype"), "pidio_herramientas": asked_tools,
                "peticiones_primera_llamada": len({(e.get("message") or {}).get("id") or id(e)
                                                   for e in first["events"] if e.get("type") == "assistant"}),
                "costo_usd_primera_llamada": first_result.get("total_cost_usd")}
        entry.update(extra or {})
        self.stages.append(entry)
        self.save_status()

        # --- validez de la llamada (D22): si falla, la corrida es fallida (§10.4), no se corrige ni se reintenta
        for r in runs:
            if r["timed_out"]:
                raise StageFailure(etapa, "tiempo_agotado", f"mas de {self.stage_timeout} s")
            if r["early_abort"]:
                raise StageFailure(etapa, "servidor_mcp_o_herramientas", "; ".join(r["early_abort"]))
            if r["result"] is None:
                raise StageFailure(etapa, "sin_resultado_de_claude",
                                   f"exit={r['returncode']}; stderr: {r['stderr_tail']!r}")
        if not asked_tools and (result_ev.get("subtype") != "success" or result_ev.get("is_error") or last["returncode"] != 0):
            motivo = str(result_ev.get("subtype") or "error")
            if motivo == "success":  # p. ej. cupo agotado: subtype "success" con is_error y HTTP 429 (D10)
                motivo = f"error_api_{result_ev.get('api_error_status')}" if result_ev.get("api_error_status") else "error_de_claude"
            raise StageFailure(etapa, motivo,
                               f"is_error={result_ev.get('is_error')}; exit={last['returncode']}; "
                               f"api_error_status={result_ev.get('api_error_status')}; texto: {raw[:300]!r}")
        if forced and not raw:
            raise StageFailure(etapa, "respuesta_forzada_vacia",
                               "la respuesta forzada no trae texto; el original aborta en este punto con "
                               "ValueError('Invalid response from LLM call - None or empty.')")
        if audit["problemas"]:
            raise StageFailure(etapa, "auditoria", "; ".join(audit["problemas"]))

        if forced:
            self.observe(etapa, "limite_de_turnos_respuesta_forzada",
                         f"el agente agoto sus {max_turns} peticiones a la API; se pidio la respuesta final con el "
                         f"texto de CrewAI en una peticion mas (D39)")
        if asked_tools:
            self.observe(etapa, "respuesta_forzada_pidio_herramientas",
                         "en la respuesta forzada el modelo pidio herramientas (denegadas, no se ejecutaron); se toma "
                         "el texto de esa respuesta, como hace CrewAI (D39)")
        for tipo, detalle in audit["observaciones"]:
            self.observe(etapa, tipo, detalle)
        self.log(f"<<< {etapa}: {entry['turnos']} turnos, {len(audit['llamadas'])} llamadas a herramientas, "
                 f"{elapsed} s, respuesta de {len(final_answer)} caracteres"
                 f"{'' if has_label else ' (sin etiqueta Final Answer:)'}"
                 f"{' (respuesta final forzada tras agotar el limite)' if forced else ''}")
        return {"raw": raw, "final_answer": final_answer, "has_label": has_label, "audit": audit}

    def _run_claude(self, args: list, stdin_path: str, stream_path: str, stderr_path: str, allowed: list, env: dict) -> dict:
        """Lanza un proceso `claude`, le pasa el mensaje por stdin y lee su flujo stream-json linea a linea."""
        started = time.time()
        events, init, early_abort, timed_out = [], None, None, False
        with open(stdin_path, "rb") as fin, open(stderr_path, "wb") as ferr, open(stream_path, "wb") as fstream:
            proc = subprocess.Popen(self.claude_cmd + args, stdin=fin, stdout=subprocess.PIPE, stderr=ferr,
                                    cwd=SANDBOX, env=env)

            def on_timeout():
                nonlocal timed_out
                timed_out = True
                kill_tree(proc)

            timer = threading.Timer(self.stage_timeout, on_timeout)
            timer.start()
            try:
                for raw_line in proc.stdout:
                    fstream.write(raw_line)
                    fstream.flush()
                    try:
                        ev = json.loads(raw_line.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(ev, dict):
                        continue
                    events.append(ev)
                    if ev.get("type") == "system" and ev.get("subtype") == "init" and init is None:
                        init = ev
                        early_abort = self._check_init(init, allowed)
                        if early_abort:  # no gastar cupo en una llamada que ya no es valida (D22)
                            kill_tree(proc)
                            break
                proc.wait()
            finally:
                timer.cancel()
                kill_tree(proc)
        with open(stderr_path, encoding="utf-8", errors="replace") as f:
            stderr_tail = f.read()[-800:]
        return {"events": events, "init": init, "early_abort": early_abort, "timed_out": timed_out,
                "returncode": proc.returncode, "elapsed": round(time.time() - started, 1), "stderr_tail": stderr_tail,
                "result": next((e for e in reversed(events) if e.get("type") == "result"), None)}

    def _audit_forced(self, etapa: str, forced: dict, main_session_id, asked_tools: bool) -> dict:
        """Entrega de la peticion que pide la respuesta final (D39): el texto de CrewAI debe llegar identico,
        en la misma sesion, con el mismo modelo y sin razonamiento extendido."""
        problems, notes = [], []
        result = forced["result"] or {}
        session_id = (forced["result"] or forced["init"] or {}).get("session_id")
        out = {"session_id": session_id, "misma_sesion": session_id == main_session_id,
               "subtype": result.get("subtype"), "pidio_herramientas": asked_tools,
               "permission_denials": result.get("permission_denials") or []}
        # En el original, la llamada forzada no ejecuta ninguna herramienta. Aqui toda peticion de herramienta
        # debe constar como denegada (sin --allowedTools); si alguna no consta, pudo ejecutarse.
        requested = [b.get("name") for e in forced["events"] if e.get("type") == "assistant"
                     for b in ((e.get("message") or {}).get("content") or [])
                     if isinstance(b, dict) and b.get("type") == "tool_use"]
        out["herramientas_pedidas"] = requested
        if len(requested) > len(out["permission_denials"]):
            problems.append(f"en la respuesta forzada se pidieron {len(requested)} herramientas y solo "
                            f"{len(out['permission_denials'])} constan como denegadas: alguna pudo ejecutarse")
        if session_id != main_session_id:
            notes.append(("respuesta_forzada_en_otra_sesion", f"{session_id} (la del agente era {main_session_id})"))
        transcript = find_transcript(session_id) if session_id else None
        if transcript:
            copy = os.path.join(self.logs_dir, f"{etapa}_forzada_transcript.jsonl")
            shutil.copyfile(transcript, copy)
            delivery = analyze_forced(copy, FORCE_FINAL_ANSWER)
            out["entrega"] = delivery
            if not delivery["encontrado"]:
                problems.append("no se encontro en la transcripcion el mensaje que pide la respuesta final")
            elif not delivery["identico"]:
                problems.append("el mensaje que pide la respuesta final no llego identico al texto de CrewAI")
            if delivery["bloques_antepuestos_inesperados"]:
                problems.append("contexto inesperado antepuesto al mensaje que pide la respuesta final: "
                                f"{delivery['bloques_antepuestos_inesperados']}")
            for prm in delivery["parametros_de_las_peticiones"]:
                if ((prm.get("thinking") or {}).get("type") not in (None, "disabled")
                        or (prm.get("output_config") or {}).get("effort") != EFFORT or prm.get("model") != self.model):
                    problems.append(f"peticion de la respuesta forzada con otra configuracion: {prm}")
        else:
            notes.append(("transcripcion_de_la_respuesta_forzada_no_encontrada", f"session_id={session_id}"))
        out["problemas"], out["observaciones"] = problems, notes
        return out

    def _check_init(self, init: dict, allowed: list) -> list:
        """Comprobacion temprana sobre el mensaje `init` (D22): servidor conectado y herramientas visibles
        exactamente iguales a las del agente. Devuelve la lista de problemas (vacia si todo esta bien)."""
        servers = {s.get("name"): s.get("status") for s in init.get("mcp_servers") or [] if isinstance(s, dict)}
        problems = []
        if set(servers) != {MCP_SERVER_NAME}:
            problems.append(f"servidores MCP cargados: {servers} (se esperaba solo '{MCP_SERVER_NAME}')")
        status = servers.get(MCP_SERVER_NAME)
        if status == "pending":
            return problems  # aun conectando: se decide despues con la transcripcion
        if status != "connected":
            problems.append(f"servidor MCP '{MCP_SERVER_NAME}' en estado {status!r}")
        elif sorted(init.get("tools") or []) != sorted(allowed):
            problems.append(f"herramientas visibles {sorted(init.get('tools') or [])} != las del agente {sorted(allowed)}")
        return problems

    def _audit(self, etapa, prompt, allowed, events, init, result_ev, has_label) -> dict:
        """Aislamiento (§5.3) y entrega de los prompts (D29). `problemas` invalida la llamada;
        `observaciones` se registra y se informa, pero no la invalida."""
        problems, notes = [], []
        calls, results, thinking, models, seen = [], {}, 0, set(), set()
        for ev in events:
            msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
            if ev.get("type") == "assistant" and msg.get("model"):
                models.add(msg["model"])
            for block in msg.get("content") or []:
                if not isinstance(block, dict):
                    continue
                kind = block.get("type")
                if kind == "tool_use" and block.get("id") not in seen:
                    seen.add(block.get("id"))
                    calls.append({"id": block.get("id"), "herramienta": block.get("name"), "argumentos": block.get("input")})
                elif kind in ("thinking", "redacted_thinking"):
                    thinking += 1
                elif kind == "tool_result":
                    results[block.get("tool_use_id")] = bool(block.get("is_error"))
        by_tool = {}
        for c in calls:
            by_tool[c["herramienta"]] = by_tool.get(c["herramienta"], 0) + 1
            c["error"] = results.get(c["id"])

        init = init or {}
        servers = {s.get("name"): s.get("status") for s in init.get("mcp_servers") or [] if isinstance(s, dict)}
        outside = sorted({c["herramienta"] for c in calls if c["herramienta"] not in allowed})
        if outside:
            problems.append(f"llamadas a herramientas fuera de la lista del agente: {outside}")
        if thinking:
            problems.append(f"{thinking} bloques de razonamiento extendido (debe estar desactivado, D4)")
        if len(models) > 1 or (models and self.model.startswith("claude-") and models != {self.model}):
            problems.append(f"modelo(s) que respondieron: {sorted(models)}; pedido: {self.model} (§10.1)")
        denials = (result_ev or {}).get("permission_denials") or []
        if denials:
            notes.append(("llamadas_denegadas", [d.get("tool_name") for d in denials if isinstance(d, dict)]))
        if init.get("slash_commands") or init.get("skills"):
            notes.append(("comandos_o_skills_cargados", {"slash_commands": init.get("slash_commands"), "skills": init.get("skills")}))
        if not has_label and result_ev is not None:
            notes.append(("sin_etiqueta_final_answer", "el texto final no contiene 'Final Answer:'; se toma completo (D31)"))
        tool_errors = [c["herramienta"] for c in calls if c["error"]]
        if tool_errors:
            notes.append(("resultados_de_herramienta_con_error", tool_errors))

        # Registro del lado del servidor y rutas pedidas a search_file (D23, D32).
        server_calls, server_warnings, server_log = [], [], os.path.join(self.logs_dir, f"{etapa}_server.jsonl")
        if os.path.exists(server_log):
            with open(server_log, encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("event") == "call":
                        server_calls.append(rec)
                    elif rec.get("event") == "warning":
                        server_warnings.append(rec.get("message"))
        if server_warnings:
            notes.append(("avisos_del_servidor_mcp", server_warnings))
        if len(server_calls) != len(calls):
            notes.append(("llamadas_servidor_vs_flujo", f"servidor {len(server_calls)}, flujo de claude {len(calls)}"))
        paths = [classify_path((c.get("args") or {}).get("path"), self.app, self.run_id)
                 for c in server_calls if c.get("tool") == "search_file"]
        outside_paths = [p for p in paths if p["zona"] != "resources_app"]
        if outside_paths:
            notes.append(("rutas_fuera_de_resources_app", outside_paths))
        if any(p["zona"] == "contaminante" and p["existe"] for p in paths):
            notes.append(("CORRIDA_CONTAMINADA", "search_file leyo salidas de otra corrida, logs/ o evaluation/ (D23, D32)"))

        # Lo que se envio de verdad a la API (transcripcion de Claude Code).
        session_id = (result_ev or init).get("session_id")
        transcript = find_transcript(session_id) if session_id else None
        delivery = {"transcripcion": None}
        if transcript:
            copy = os.path.join(self.logs_dir, f"{etapa}_transcript.jsonl")
            shutil.copyfile(transcript, copy)
            delivery = analyze_transcript(copy, prompt.system, prompt.user)
            delivery["transcripcion"] = os.path.basename(copy)
            if delivery.get("legible"):
                # Un agente que no recibio exactamente los prompts del original no es una replica (§6, D29, D38).
                if not delivery["system_entregado_identico"]:
                    problems.append("el system prompt enviado a la API no es identico al de la replica "
                                    f"(contenido en lo enviado: {delivery['system_contenido_en_lo_enviado']}; "
                                    f"solo recortado: {delivery['system_solo_recortado']})")
                if not delivery["usuario_entregado_identico"]:
                    problems.append("el mensaje de usuario enviado a la API no es identico al de la replica "
                                    f"(solo recortado: {delivery['usuario_solo_recortado']})")
                problems.extend(delivery["contexto_anadido_inesperado"])
                if any(tools != sorted(allowed) for tools in delivery["herramientas_por_forma_de_peticion"]):
                    problems.append(f"herramientas enviadas a la API {delivery['herramientas_por_forma_de_peticion']} != "
                                    f"las del agente {sorted(allowed)}")
                for p in delivery["parametros_de_las_peticiones"]:
                    if (p.get("thinking") or {}).get("type") not in (None, "disabled"):
                        problems.append(f"peticion con razonamiento extendido: {p.get('thinking')}")
                    if (p.get("output_config") or {}).get("effort") != EFFORT or p.get("model") != self.model:
                        problems.append(f"peticion con otra configuracion: model={p.get('model')}, "
                                        f"output_config={p.get('output_config')} (se esperaba {self.model}, effort {EFFORT})")
            else:
                notes.append(("transcripcion_ilegible", delivery["archivo"]))
        else:
            notes.append(("transcripcion_no_encontrada", f"session_id={session_id}"))
            if servers.get(MCP_SERVER_NAME) != "connected" and result_ev is not None:
                problems.append("no se pudo confirmar que el servidor MCP estuviera conectado (init sin 'connected' "
                                "y sin transcripcion)")
        # Compactacion del historial por Claude Code: el agente habria seguido con un resumen de sus propios
        # mensajes (CrewAI tambien resume al exceder la ventana, pero aqui no deberia ocurrir): se informa.
        compactions = [e.get("subtype") for e in events if e.get("type") == "system" and "compact" in str(e.get("subtype"))]
        if compactions:
            notes.append(("historial_compactado_por_claude_code", compactions))
        if self.claude_version and init.get("claude_code_version") and init["claude_code_version"] != self.claude_version:
            problems.append(f"version de Claude Code {init['claude_code_version']} distinta de la del inicio de la "
                            f"corrida ({self.claude_version})")
        sandbox_after = os.listdir(SANDBOX)
        if sandbox_after:
            notes.append(("sandbox_con_archivos_tras_la_llamada", sandbox_after))
        return {
            "etapa": etapa, "agente": prompt.agent, "modelo_pedido": self.model, "modelos_que_respondieron": sorted(models),
            "servidores_mcp": servers, "herramientas_del_agente": sorted(allowed),
            "herramientas_visibles_init": sorted(init.get("tools") or []),
            "apiKeySource": init.get("apiKeySource"), "claude_code_version": init.get("claude_code_version"),
            "llamadas": calls, "llamadas_por_herramienta": by_tool, "llamadas_fuera_de_lista": outside,
            "llamadas_registradas_por_el_servidor": len(server_calls),
            "bloques_thinking": thinking, "permission_denials": denials,
            "etiqueta_final_answer": has_label, "rutas_search_file": paths, "entrega": delivery,
            "problemas": problems, "observaciones": notes,
        }

    # ---------------------------------------------------------------- flujo de main.py
    def run(self) -> None:
        number, num = self.number, self.num
        domains_dir = self.domains_dir

        # STAGE 1: Identify the business domains (main.py 63-116)
        self.log("--- Stage 1: Identifying Business Domains ---")
        r = self.call_agent("1_domain", bp.domain_prompts(number, num))
        identification_result = r["final_answer"]            # crew_output.raw
        identification_result = clean_json_output(identification_result)

        domain_clusters_path = os.path.join(domains_dir, "domain_clusters.json")
        write_text(domain_clusters_path, identification_result)
        self.log(f"Domain clusters saved to: {domain_clusters_path}")

        try:
            domains_data = json.loads(identification_result)
        except json.JSONDecodeError as e:
            raise PipelineStop("1_domain", f"Error parsing domain data string from Stage 1: {e}")
        business_domains = domains_data.get("business_domains", [])
        if not business_domains:
            raise PipelineStop("1_domain", "No business domains identified from Stage 1. Stopping workflow.")
        self.log(f"Etapa 1: {len(business_domains)} dominios: "
                 f"{[d.get('domain_name') if isinstance(d, dict) else d for d in business_domains]}")
        if self.only_stage1:
            self.status["estado"] = "parcial_etapa1"
            return

        # STAGE 2: one clustering call per domain (main.py 94-257)
        self.log("\n--- Stage 2: Clustering Classes for Each Domain ---")
        clustering_tasks = []
        for domain in business_domains:                      # main.py 134-175
            domain_name = domain.get("domain_name", "Unknown Domain")
            domain_description = domain.get("description", "No description provided")
            if domain_name == "Unknown Domain" or not domain_name:
                self.observe("2_clustering", "dominio_omitido", f"Skipping domain with missing name: {domain}")
                continue
            if domain_description == "No description provided":
                self.observe("2_clustering", "dominio_omitido", f"Skipping domain with missing description: {domain}")
                continue
            clustering_tasks.append(domain)
        if not clustering_tasks:
            raise PipelineStop("2_clustering", "No clustering tasks were created. Stopping workflow.")

        all_domain_results = {}
        for i, task_domain in enumerate(clustering_tasks):   # main.py 204-250
            # main.py 205 empareja la tarea i con business_domains[i], sin descontar los dominios omitidos.
            # Se reproduce tal cual (decision de Jorge, D31) y se deja constancia si hay desajuste.
            domain_name = business_domains[i].get("domain_name", "Unknown Domain")
            etapa = f"2_clustering_{i + 1:02d}"
            task_name = task_domain.get("domain_name", "Unknown Domain")
            if task_name != domain_name:
                self.observe(etapa, "desajuste_de_dominios_del_original",
                             f"la tarea analiza '{task_name}' pero main.py busca su resultado como '{domain_name}' (D31)")
            # CrewAI interpola al lanzar la tarea: si falla, las tareas anteriores ya se ejecutaron.
            prompt = bp.clustering_prompts(task_domain, business_domains, number, num)
            r = self.call_agent(etapa, prompt, extra={"dominio_de_la_tarea": task_name, "dominio_emparejado": domain_name})
            task_result = r["final_answer"]
            cleaned_result = clean_json_output(task_result)

            try:
                # Parse the JSON
                domain_data = json.loads(cleaned_result)

                # Extract class list ensuring consistent format
                class_list = []

                # Check if the domain data has the expected structure
                if domain_name in domain_data and isinstance(domain_data[domain_name], list):
                    class_list = domain_data[domain_name]
                else:
                    self.observe(etapa, "dominio_sin_lista_en_la_respuesta",
                                 f"la respuesta no trae una lista bajo la clave '{domain_name}': lista vacia (main.py 227-231)")

                # Store the flattened class list
                all_domain_results[domain_name] = class_list

                # Also save individual domain file with consistent format
                original_name, safe_domain_name = domain_file_name(domain_name)
                if safe_domain_name != original_name:
                    self.observe(etapa, "nombre_de_archivo_saneado", f"{original_name!r} -> {safe_domain_name!r} (D29)")
                domain_file = os.path.join(domains_dir, f"{safe_domain_name}.json")
                dump_result(domain_file, {domain_name: class_list})
                self.log(f"Domain '{domain_name}' data saved to {domain_file} ({len(class_list)} clases)")

            except json.JSONDecodeError as e:
                self.observe(etapa, "json_invalido_en_clustering",
                             f"Error parsing domain data for '{domain_name}': {e}. Lista vacia, como el original (main.py 244-250)")
                all_domain_results[domain_name] = []

        # Save all domain results to a single file
        all_domains_file = os.path.join(domains_dir, "all_domains.json")
        dump_result(all_domains_file, all_domain_results)
        self.log(f"All domain results saved to {all_domains_file}")

        # STAGE 3: merging, only if the number of domains differs (main.py 259-338)
        skip_merging = len(all_domain_results) == int(number)
        merged_domains_file = os.path.join(domains_dir, "merged_domains.json")
        merging_context = None  # respuesta final del Merging Agent: contexto de la Etapa 4 solo si hubo fusion (D27)

        if skip_merging:
            self.status["fusion"] = "saltada"
            self.log(f"\nSkipping merging task as the number of domains ({len(all_domain_results)}) matches the desired number ({number})")
            # Copy all_domains.json to merged_domains.json
            dump_result(merged_domains_file, all_domain_results)

            # Use all_domain_results as the domain clusters
            domain_clusters = all_domain_results
        else:
            self.status["fusion"] = "ejecutada"
            self.log(f"\n--- Stage 3: Merging {len(all_domain_results)} domains into {number} ---")
            r = self.call_agent("3_merging", bp.merging_prompts(business_domains, all_domain_results, number, num))
            merging_result = r["final_answer"]
            merging_context = r["final_answer"]

            if merging_result:
                merging_result = clean_json_output(merging_result)

                try:
                    merged_domains = json.loads(merging_result)

                    # Save the merged domains to a file
                    dump_result(merged_domains_file, merged_domains)
                    self.log(f"Merged domains saved to {merged_domains_file}")

                    # Extract the domain clusters
                    domain_clusters = {}
                    if "Domain_Cluster" in merged_domains:
                        domain_clusters = merged_domains["Domain_Cluster"]
                    else:
                        domain_clusters = merged_domains

                    # Save individual domain files
                    for domain_name, class_list in domain_clusters.items():
                        if isinstance(class_list, list):
                            _, safe_domain_name = domain_file_name(domain_name)
                            domain_file = os.path.join(domains_dir, f"{safe_domain_name}.json")
                            dump_result(domain_file, {domain_name: class_list})
                        elif isinstance(class_list, dict):
                            all_classes = []
                            for layer, classes in class_list.items():
                                if isinstance(classes, list):
                                    all_classes.extend(classes)

                            _, safe_domain_name = domain_file_name(domain_name)
                            domain_file = os.path.join(domains_dir, f"{safe_domain_name}.json")
                            dump_result(domain_file, {domain_name: all_classes})

                except json.JSONDecodeError as e:
                    # Igual que el original: se vuelve a all_domain_results y NO se escribe merged_domains.json.
                    self.observe("3_merging", "json_invalido_en_fusion",
                                 f"Error parsing merging task result: {e}. Se usa all_domain_results (main.py 332-335); "
                                 f"merged_domains.json no existe")
                    domain_clusters = all_domain_results
            else:
                self.observe("3_merging", "fusion_sin_respuesta", "Error: Could not find merging task result (main.py 336-338)")
                domain_clusters = all_domain_results

        # STAGE 4: common classes (main.py 340-395)
        self.log("\n--- Running Common Task ---")
        common_result_file = os.path.join(self.run_dir, "common_result.json")
        # main.py 345-347: WriteResultToJson.reset() + set_output_file(). En la replica el servidor MCP de esta
        # llamada arranca vacio y fusiona con lo que haya en RESULT_FILE: el archivo no debe existir (D23).
        if os.path.exists(common_result_file):
            os.remove(common_result_file)
        r = self.call_agent("4_common", bp.common_class_prompts(domain_clusters, number, num, context=merging_context),
                            result_file=common_result_file)
        common_final_answer = r["final_answer"]
        common_result_json = self._accumulated_results(common_result_file)   # WriteResultToJson.get_accumulated_results()

        if common_result_json:
            self.log(f"Common task completed. Got results for {len(common_result_json)} domains from tool calls.")
            dump_result(common_result_file, common_result_json)
        else:
            self.observe("4_common", "sin_resultados_de_write_result_to_json",
                         "Warning: No results from WriteResultToJson tool. Trying to parse from raw output... (main.py 384-395)")
            cleaned_common_result = clean_json_output(common_final_answer)
            try:
                common_result_json = json.loads(cleaned_common_result)
                dump_result(common_result_file, common_result_json)
                self.log(f"Common task result saved to {common_result_file}")
            except json.JSONDecodeError as e:
                self.observe("4_common", "json_invalido_en_clases_comunes", f"Error parsing common result: {e}; common_result_json = {{}}")
                common_result_json = {}

        # STAGE 5: review (main.py 397-488)
        self.log("\n--- Running Review Task ---")
        context_dir = os.path.join(BASE, "context", self.app)
        class_info_file = os.path.join(context_dir, "class_summaries.json")
        all_classes = []

        try:
            if not os.path.exists(class_info_file):
                self.observe("5_review", "sin_class_summaries", f"Warning: Class summaries file not found at {class_info_file}")
            else:
                with open(class_info_file, 'r', encoding='utf-8', errors='replace') as f:
                    class_info = json.load(f)
                    # All keys in the class_summaries.json are class names
                    all_classes = list(class_info.keys())
                self.log(f"Found {len(all_classes)} total classes in the application")
        except Exception as e:
            self.observe("5_review", "error_leyendo_class_summaries", f"Error reading class_summaries.json: {e}")
            all_classes = []

        # Identify classes that have been assigned to domains
        assigned_classes = set()
        for domain, classes in common_result_json.items():
            if isinstance(classes, list):
                assigned_classes.update(classes)
            elif isinstance(classes, dict):
                for layer, layer_classes in classes.items():
                    if isinstance(layer_classes, list):
                        assigned_classes.update(layer_classes)

        # Find remaining unassigned classes
        remaining_classes = [cls for cls in all_classes if cls not in assigned_classes]
        self.log(f"Found {len(remaining_classes)} unassigned classes")

        result_file = os.path.join(self.run_dir, "result.json")
        if os.path.exists(result_file):                       # main.py 435-437, como en la Etapa 4
            os.remove(result_file)
        # El contexto es la respuesta final del Common Class Agent, siempre (crew.py 200; D27).
        r = self.call_agent("5_review", bp.review_prompts(common_result_json, remaining_classes, domain_clusters,
                                                          number, num, context=common_final_answer),
                            result_file=result_file)
        final_result_raw = r["final_answer"]
        final_result_json = self._accumulated_results(result_file)

        if final_result_json:
            self.log(f"Review task completed. Got results for {len(final_result_json)} domains from tool calls.")
            dump_result(result_file, final_result_json)
            self.log(f"Final result saved to {result_file}")
        else:
            self.observe("5_review", "sin_resultados_de_write_result_to_json",
                         "Warning: No results from WriteResultToJson tool. Trying to parse from raw output... (main.py 473-488)")
            cleaned_final_result = clean_json_output(final_result_raw)
            try:
                final_result_json = json.loads(cleaned_final_result)
                dump_result(result_file, final_result_json)
                self.log(f"Final result saved to {result_file}")
            except json.JSONDecodeError as e:
                result_file_txt = os.path.join(self.run_dir, "result.txt")
                write_text(result_file_txt, final_result_raw)
                raise PipelineStop("5_review", f"Error parsing final result: {e}. Raw final result saved to {result_file_txt}; "
                                               f"no hay result.json")

        self.status["estado"] = "completa"
        self.status["resultado"] = self._result_stats(result_file, final_result_json, all_classes)

    def _accumulated_results(self, result_file: str) -> dict:
        """Equivalente a `WriteResultToJson.get_accumulated_results()`: lo que la herramienta fue guardando.
        En el original vive en memoria; aqui, en el RESULT_FILE que escribe el servidor MCP en cada llamada."""
        if not os.path.exists(result_file):
            return {}
        try:
            with open(result_file, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            self.observe(os.path.basename(result_file), "archivo_de_resultados_ilegible", str(e))
            return {}
        return data if isinstance(data, dict) else {}

    def _result_stats(self, result_file, result, all_classes) -> dict:
        stats = {"archivo": os.path.relpath(result_file, BASE).replace("\\", "/")}
        if not isinstance(result, dict):
            stats["nota"] = f"result.json no es un objeto ({type(result).__name__})"
            return stats
        assigned = set()
        for classes in result.values():
            if isinstance(classes, list):
                assigned.update(c for c in classes if isinstance(c, str))
        universe = set(all_classes)
        stats.update({"particiones": len(result),
                      "clases_por_particion": {k: len(v) if isinstance(v, list) else None for k, v in result.items()},
                      "clases_distintas_asignadas": len(assigned), "clases_del_universo": len(universe),
                      "clases_sin_asignar": sorted(universe - assigned),
                      "clases_fuera_del_universo": sorted(assigned - universe)})
        return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Replica de MicroAgent con Claude Code: orquestador (INSTRUCCIONES §7).")
    ap.add_argument("--app", required=True, choices=sorted(bp.APPS))
    ap.add_argument("--number", help="numero de microservicios; por defecto, el de la aplicacion (3 o 5)")
    ap.add_argument("--num", help="el mismo numero en letras; por defecto, el de la aplicacion (THREE o FIVE)")
    ap.add_argument("--run-id", required=True, help="identificador de la corrida, p. ej. claude-run1")
    ap.add_argument("--model", default=MODEL, help=f"modelo unico de la replica (por defecto {MODEL}, D3)")
    ap.add_argument("--only-stage1", action="store_true", help="ejecuta solo la Etapa 1 (prueba de humo de §7)")
    ap.add_argument("--stage-timeout", type=int, default=3600, help="segundos maximos por llamada a un agente")
    ap.add_argument("--allow-references", action="store_true",
                    help="permite correr con evaluation/references/ no vacia (queda registrado)")
    ap.add_argument("--max-turns-override", type=int, help=argparse.SUPPRESS)  # solo para comprobar --max-turns (D2)
    args = ap.parse_args()
    args.number = args.number or bp.APPS[args.app][0]
    args.num = args.num or bp.APPS[args.app][1]

    pipeline = Pipeline(args)
    pipeline.prepare(args.allow_references)
    failure = None
    try:
        pipeline.run()
    except StageFailure as e:
        failure = {"etapa": e.etapa, "motivo": e.motivo, "detalle": e.detalle}
    except PipelineStop as e:
        failure = {"etapa": e.etapa, "motivo": "el_flujo_se_detiene_como_en_main_py", "detalle": e.motivo}
    except bp.PromptInterpolationError as e:
        failure = {"etapa": "armado_del_prompt", "motivo": "el_original_habria_abortado_al_interpolar", "detalle": str(e)}
    except Exception as e:  # el original habria terminado con una excepcion en el mismo punto
        failure = {"etapa": "orquestador", "motivo": f"excepcion {type(e).__name__}", "detalle": traceback.format_exc()}
    except KeyboardInterrupt:  # Ctrl+C: la corrida no queda "en_curso" (call_agent ya mato a `claude`)
        failure = {"etapa": "orquestador", "motivo": "interrumpida", "detalle": "corrida interrumpida a mano (Ctrl+C)"}
    if failure:
        pipeline.status["estado"] = "fallida"
        pipeline.status["fallo"] = failure
        # write_result_to_json escribe result.json dominio a dominio durante la Etapa 5. Si la corrida falla
        # despues de alguna escritura, ese archivo es parcial: se aparta para que nadie lo evalue (D39).
        partial = os.path.join(pipeline.run_dir, "result.json")
        if os.path.exists(partial):
            os.replace(partial, os.path.join(pipeline.run_dir, "result_parcial_de_corrida_fallida.json"))
            pipeline.status["resultado"] = None
            pipeline.observe("orquestador", "result_json_parcial_apartado",
                             "result.json quedo a medias y se renombro a result_parcial_de_corrida_fallida.json")
    pipeline.status["fin"] = now()
    pipeline.save_status()

    st, tot = pipeline.status, pipeline.status["totales"]
    pipeline.log("\n--- Workflow Complete ---" if not failure else "\n--- CORRIDA FALLIDA (registrar y reintentar con otro run_id, §10.4) ---")
    pipeline.log(f"Estado: {st['estado']} | fusion: {st['fusion']} | llamadas a agentes: {tot['llamadas']} | "
                 f"turnos: {tot['turnos']} | duracion: {round(tot['duracion_ms'] / 1000)} s | "
                 f"costo nominal: USD {tot['costo_usd']:.4f} | observaciones: {len(st['observaciones'])}")
    if failure:
        pipeline.log(f"Fallo en {failure['etapa']}: {failure['motivo']}\n{failure['detalle']}")
    if st["resultado"]:
        res = st["resultado"]
        pipeline.log(f"Final Result: {res['archivo']} | {res.get('particiones')} particiones | "
                     f"{res.get('clases_distintas_asignadas')} de {res.get('clases_del_universo')} clases asignadas | "
                     f"sin asignar: {len(res.get('clases_sin_asignar') or [])}")
    pipeline.log(f"Registro: {os.path.relpath(pipeline.logs_dir, BASE)}")
    return 1 if failure else 0


if __name__ == "__main__":
    sys.exit(main())
