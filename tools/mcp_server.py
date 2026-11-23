"""Servidor MCP "microagent" (FastMCP, transporte stdio) - INSTRUCCIONES §5.2.

Expone 14 herramientas de custom_tools.py con el mismo `name`, la misma `description` y los mismos argumentos
(nombre, tipo y descripcion, tomados de `args_schema`) que su clase original. Cada herramienta devuelve la
cadena que produce el metodo `_run` original, sin modificar.

Variables de entorno:
    APP_NAME     nombre de la aplicacion (p. ej. jpetstore-6)            -> APP_CONFIG["app_name"]
    RUN_ID       identificador de la corrida (p. ej. claude-run1)        -> APP_CONFIG["model_name"]
    RESULT_FILE  ruta absoluta del archivo donde write_result_to_json guarda los resultados. Obligatoria si
                 el proceso publica write_result_to_json: sin ella la herramienta responderia "Successfully
                 saved" sin guardar nada (en el original main.py vuelca despues lo acumulado en memoria; aqui
                 el proceso termina y se perderia).
    MICROAGENT_TOOLS  (opcional) nombres de las herramientas a publicar, separados por comas; sin ella, las 14
    MICROAGENT_LOG    (opcional) ruta absoluta de un archivo JSONL donde el servidor anota cada llamada
                 (herramienta, argumentos, longitud de la respuesta, segundos) y sus avisos. Claude Code no
                 guarda el stderr del servidor; este archivo es la evidencia del lado del servidor.

Lanzamiento: python -X utf8 tools/mcp_server.py
    El modo UTF-8 es obligatorio: algunos `_run` abren archivos sin indicar codificacion, y en Windows la
    codificacion por defecto no es UTF-8 (en Linux o macOS, donde corre el original, si lo es).
"""
import contextlib
import inspect
import json
import os
import shutil
import sys
import time
from typing import Annotated

if not sys.flags.utf8_mode:
    sys.exit("mcp_server.py debe ejecutarse en modo UTF-8: python -X utf8 tools/mcp_server.py")
# stdout es el canal del protocolo MCP (stdio). Los `print` de custom_tools.py se desvian a stderr.
sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
with contextlib.redirect_stdout(sys.stderr):
    import custom_tools as ct  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402
from pydantic import Field  # noqa: E402

# Las 14 herramientas de la tabla de §5.2, en ese orden.
TOOL_CLASSES = [
    ct.GetAllClassHierarchy,
    ct.GetAllClassHierarchyComplete,
    ct.GetDatabaseSummary,
    ct.GetAllClassSummaries,
    ct.GetClassSummary,
    ct.GetClassBasicInfo,
    ct.GetClassRelationAndCode,
    ct.SearchFile,
    ct.CodebaseSemanticSearch,
    ct.GetRelatedClassList,
    ct.RankDependencyEntropyAndRatio,
    ct.GetMorePotentialCommonClasses,
    ct.AssignCommonClassList,
    ct.WriteResultToJson,
]

RESULT_FILE = os.environ.get("RESULT_FILE") or None
LOG_FILE = os.environ.get("MICROAGENT_LOG") or None

mcp = FastMCP("microagent", log_level="WARNING")


def _log(event: dict):
    """Anota un evento en MICROAGENT_LOG (si esta definida). Nunca interrumpe una llamada."""
    if not LOG_FILE:
        return
    try:
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "pid": os.getpid()}
        record.update(event)
        with open(LOG_FILE, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        print(f"[mcp_server] no se pudo escribir MICROAGENT_LOG ({exc})", file=sys.stderr)


def _warn(message: str):
    print(f"[mcp_server] {message}", file=sys.stderr)
    _log({"event": "warning", "message": message})


def _prepare_write_result():
    """Equivalente a lo que hace main.py antes de las tareas que usan write_result_to_json:
    WriteResultToJson.reset() y WriteResultToJson.set_output_file(<archivo>)."""
    ct.WriteResultToJson.reset()
    if RESULT_FILE:
        ct.WriteResultToJson.set_output_file(RESULT_FILE)


def _merge_existing_results():
    """Fusiona, dominio por dominio, lo ya guardado en RESULT_FILE con lo acumulado en memoria (§5.2).

    En el original los resultados se acumulan en una variable de clase durante toda la tarea. Aqui cada
    `claude -p` arranca su propio proceso del servidor, asi que antes de cada llamada se recarga el archivo.
    Lo acumulado en este proceso tiene prioridad sobre lo leido del archivo.

    Si el archivo existe pero no se puede usar (ilegible, JSON invalido o no es un objeto), `_run` lo va a
    sobrescribir: antes se guarda una copia `<RESULT_FILE>.descartado-<fecha>` y se anota el aviso."""
    if not RESULT_FILE or not os.path.exists(RESULT_FILE):
        return
    problem = None
    try:
        with open(RESULT_FILE, "r", encoding="utf-8") as fh:
            on_disk = json.load(fh)
        if not isinstance(on_disk, dict):
            problem = "no contiene un objeto JSON"
    except (OSError, ValueError) as exc:
        problem = f"no se pudo leer ({exc})"
    if problem:
        backup = None
        try:
            if os.path.getsize(RESULT_FILE) > 0:
                backup = f"{RESULT_FILE}.descartado-{time.strftime('%Y%m%d-%H%M%S')}"
                shutil.copyfile(RESULT_FILE, backup)
        except OSError as exc:
            backup = f"(copia fallida: {exc})"
        _warn(f"RESULT_FILE {problem}; se ignora su contenido. Copia: {backup}")
        return
    merged = dict(on_disk)
    merged.update(ct.WriteResultToJson._accumulated_results)
    ct.WriteResultToJson._accumulated_results = merged


def _make_handler(tool):
    """Crea la funcion que FastMCP registra: mismos argumentos que `args_schema` y llamada directa a `_run`."""
    is_write_result = isinstance(tool, ct.WriteResultToJson)

    def handler(**kwargs):
        start = time.time()
        with contextlib.redirect_stdout(sys.stderr):
            if is_write_result:
                _merge_existing_results()
            result = tool._run(**kwargs)
        result = result if isinstance(result, str) else str(result)
        _log({"event": "call", "tool": tool.name, "args": kwargs, "result_chars": len(result),
              "seconds": round(time.time() - start, 3)})
        return result

    params = []
    for field_name, field in tool.args_schema.model_fields.items():
        default = inspect.Parameter.empty if field.is_required() else field.default
        annotation = Annotated[field.annotation, Field(description=field.description)]
        params.append(inspect.Parameter(field_name, inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                        default=default, annotation=annotation))
    handler.__signature__ = inspect.Signature(params, return_annotation=str)
    handler.__name__ = tool.name
    return handler


def _selected_names():
    """Herramientas que publica este proceso. Sin MICROAGENT_TOOLS se publican las 14. Con MICROAGENT_TOOLS
    (nombres separados por comas) solo esas: asi el modelo ve unicamente las herramientas de su agente (§5.3),
    igual que en crew.py, donde cada agente recibe solo su lista. `--allowedTools` por si solo no basta: las
    herramientas no permitidas siguen apareciendo en el contexto del modelo (logs/cli_checks/check4_mcp_all_*)."""
    raw = os.environ.get("MICROAGENT_TOOLS", "").strip()
    if not raw:
        return None
    names = [n.strip() for n in raw.split(",") if n.strip()]
    known = {cls.model_fields["name"].default for cls in TOOL_CLASSES}
    unknown = [n for n in names if n not in known]
    if unknown:
        sys.exit(f"MICROAGENT_TOOLS contiene herramientas desconocidas: {unknown}")
    return set(names)


def build_server():
    selected = _selected_names()
    write_name = ct.WriteResultToJson.model_fields["name"].default
    if selected is None or write_name in selected:
        if not RESULT_FILE:
            sys.exit(f"RESULT_FILE es obligatoria cuando se publica {write_name}")
        if not os.path.isabs(RESULT_FILE):
            sys.exit(f"RESULT_FILE debe ser una ruta absoluta: {RESULT_FILE!r}")
    _prepare_write_result()
    _log({"event": "start", "app": ct.APP_CONFIG["app_name"], "run_id": ct.APP_CONFIG["model_name"],
          "tools": sorted(selected) if selected is not None else "todas", "result_file": RESULT_FILE})
    for cls in TOOL_CLASSES:
        if selected is not None and cls.model_fields["name"].default not in selected:
            continue
        with contextlib.redirect_stdout(sys.stderr):
            tool = cls()
        mcp.add_tool(_make_handler(tool), name=tool.name, description=tool.description, structured_output=False)
    return mcp


if __name__ == "__main__":
    build_server().run(transport="stdio")
