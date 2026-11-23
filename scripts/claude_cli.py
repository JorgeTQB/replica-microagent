"""Envoltorio minimo de `claude -p` para la preparacion de contexto (Fase 1).

Cada llamada:
  - se ejecuta desde un directorio vacio (_sandbox/), sin CLAUDE.md;
  - no tiene herramientas (--tools "") ni servidores MCP (--strict-mcp-config sin --mcp-config);
  - no carga skills/comandos (--disable-slash-commands) ni settings de usuario/proyecto (--setting-sources "");
  - usa --system-prompt "" (el prompt original de preparacion de contexto es solo un mensaje de usuario);
  - recibe el prompt por stdin (evita el limite de longitud de la linea de comandos en Windows).
Opciones verificadas con `claude --help` y con logs/cli_checks/ (Claude Code 2.1.325).
"""
import json
import os
import shutil
import subprocess

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SANDBOX = os.path.join(BASE, "_sandbox")
# Unico modelo de la replica (DECISIONES.md D3 y D16). Claude Sonnet 4.6 no tiene ID con fecha: el ID completo
# es este mismo. La primera generacion del contexto (Sonnet 4.5, archivada en logs/_archivo_sonnet45_thinking/)
# quedo descartada porque ese modelo se retira el 2026-11-30.
MODEL = "claude-sonnet-4-6"
# Razonamiento extendido desactivado (DECISIONES.md D4 y D16): el original llama al LLM sin `thinking`.
# Claude Code lo activa por defecto; MAX_THINKING_TOKENS=0 lo apaga (comprobado en logs/cli_checks/check3_*).
EXTRA_ENV = {"MAX_THINKING_TOKENS": "0"}
# Solo para las llamadas que usan el servidor MCP (fases 2, 4): tiempos de espera de Claude Code, en ms.
# El servidor tarda hasta ~60 s en arrancar en frio porque custom_tools.py importa sentence_transformers al
# cargarse; con el valor por defecto de Claude Code el servidor queda como "failed" (DECISIONES.md, Fase 2).
MCP_ENV = {"MCP_TIMEOUT": "300000", "MCP_TOOL_TIMEOUT": "600000"}


def call_claude(prompt: str, model: str = MODEL, system_prompt: str = "", max_turns: int = 1, timeout: int = 900) -> dict:
    """Devuelve el JSON completo de `claude -p --output-format json` (dict). Lanza RuntimeError si falla."""
    os.makedirs(SANDBOX, exist_ok=True)
    if os.listdir(SANDBOX):
        raise RuntimeError(f"_sandbox no esta vacio: {os.listdir(SANDBOX)}")
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("no se encontro el ejecutable 'claude' en el PATH")
    cmd = [
        exe, "-p",
        "--model", model,
        "--system-prompt", system_prompt,
        "--tools", "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--setting-sources", "",
        "--max-turns", str(max_turns),
        "--output-format", "json",
    ]
    env = dict(os.environ)
    env.update(EXTRA_ENV)
    proc = subprocess.run(cmd, input=prompt.encode("utf-8"), capture_output=True, cwd=SANDBOX, timeout=timeout, env=env)
    out = proc.stdout.decode("utf-8", errors="replace")
    err = proc.stderr.decode("utf-8", errors="replace")
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude devolvio salida no JSON (exit={proc.returncode}): {out[:500]!r} | stderr: {err[:500]!r}")
    data["_exit_code"] = proc.returncode
    data["_stderr"] = err
    data["_cmd"] = cmd[1:]
    data["_env"] = dict(EXTRA_ENV)
    return data


def extract_fenced_prompt(md_path: str, heading: str) -> str:
    """Devuelve literalmente el contenido del bloque ``` que sigue al encabezado `## <heading>` en un .md.
    El cierre es la ultima linea ``` antes del siguiente encabezado `## ` (el Database Summary Prompt
    contiene un bloque ```sql anidado, por eso no se usa el primer ``` de cierre)."""
    lines = open(md_path, encoding="utf-8").read().split("\n")
    start = next(i for i, l in enumerate(lines) if l.strip() == f"## {heading}")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    section = lines[start + 1:end]
    opens = [i for i, l in enumerate(section) if l.strip().startswith("```")]
    first, last = opens[0], opens[-1]
    assert section[first].strip() == "```" and section[last].strip() == "```" and first < last, (heading, opens)
    return "\n".join(section[first + 1:last])


def parse_json_text(text: str):
    """Parsea el JSON de la respuesta; tolera cercas ```json ... ``` alrededor."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        i, j = t.find("{"), t.rfind("}")
        if i == -1 or j == -1:
            raise
        return json.loads(t[i:j + 1])
