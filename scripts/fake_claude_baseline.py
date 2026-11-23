"""Sustituto de `claude -p` para probar run_baseline.py SIN gastar cupo (lo usa test_baseline_offline.py).

Acepta la linea de comandos de run_baseline.py, lee el prompt por stdin y emite un flujo `stream-json` con la forma
del de Claude Code 2.1.325 (init / assistant / result). No llama a ningun modelo: arma una particion con las clases
que aparecen en el prompt (encabezados `### <FQCN>`), repartidas en n servicios.

Ademas (revision D47, hallazgos 3 y 4):
  - escribe una transcripcion sintetica en $CLAUDE_CONFIG_DIR/projects/fake/<session_id>.jsonl con la forma de las
    de Claude Code (api-request-shape / api-request-blob / api-request), para que run_baseline.py la audite;
    sus 5 <system-reminder> imitan los de la Fase 1 con datos ficticios (sin correo real);
  - guarda en $FAKE_BASELINE_RECORD su argv, su cwd y el entorno que recibio (solo las variables que fija la
    replica y los nombres de las demas), para que la prueba los compare con valores escritos a mano.

FAKE_BASELINE_MODE (por defecto "ok"):
  respuesta: ok, fenced, text_around, invalid, list, nonlist, missing, wrong_n, duplicate_keys, max_tokens
  claude:    api_error, no_result, exit_nonzero, timeout, thinking, tool, tools_init, mcp_init, wrong_model
  entrega (transcripcion): sys_extra, effort_medium, thinking_param, extra_reminder, prompt_trimmed,
             two_requests, tools_in_request, no_transcript
"""
import json
import os
import re
import sys
import time
import uuid

SDK_BLOCK = "You are a Claude agent, built on Anthropic's Claude Agent SDK."
REMINDERS = [
    "<system-reminder>\n# Environment\nYou have been invoked in the following environment: \n - Primary working "
    "directory: (simulado)\n</system-reminder>",
    "<system-reminder>\nYou are powered by the model named Sonnet 4.6. The exact model ID is claude-sonnet-4-6.\n"
    "</system-reminder>",
    "<system-reminder>\n<total_tokens>15000000 tokens left</total_tokens>\n</system-reminder>",
    "<system-reminder>\nAs you answer the user's questions, you can use the following context:\n# userEmail\n"
    "The user's email address is usuario@ejemplo.invalid.\n</system-reminder>",
    "<system-reminder>\nToday's date is 2026-11-21.\n</system-reminder>",
]
FIXED_ENV = ("DISABLE_AUTOUPDATER", "API_TIMEOUT_MS", "CLAUDE_CODE_DISABLE_CLAUDE_MDS", "CLAUDE_CODE_DISABLE_AUTO_MEMORY",
             "PYTHONDONTWRITEBYTECODE", "MAX_THINKING_TOKENS", "MCP_TIMEOUT", "MCP_TOOL_TIMEOUT", "CLAUDE_CONFIG_DIR")


def emit(ev):
    sys.stdout.write(json.dumps(ev, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def opt(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def write_transcript(sid, prompt, model, mode):
    home = os.environ.get("CLAUDE_CONFIG_DIR")
    if not home or mode == "no_transcript":
        return
    folder = os.path.join(home, "projects", "fake")
    os.makedirs(folder, exist_ok=True)
    system = [{"type": "text", "text": SDK_BLOCK}]
    if mode == "sys_extra":
        system.append({"type": "text", "text": "# claudeMd\nalgo que no es de la replica"})
    reminders = REMINDERS + (["<system-reminder>\n# memory\nrecuerdo\n</system-reminder>"] if mode == "extra_reminder" else [])
    user_text = prompt.strip() if mode == "prompt_trimmed" else prompt
    params = {"model": model, "max_tokens": 32000, "thinking": {"type": "enabled" if mode == "thinking_param" else "disabled"},
              "temperature": 1, "output_config": {"effort": "medium" if mode == "effort_medium" else "high"}}
    tools = [{"name": "Read"}] if mode == "tools_in_request" else []
    lines = [{"type": "api-request-shape", "shape": {"system": system, "tools": tools}},
             {"type": "api-request-blob", "message": {"role": "user", "content":
                 [{"type": "text", "text": t} for t in reminders] + [{"type": "text", "text": user_text}]}},
             {"type": "api-request", "params": params}]
    if mode == "two_requests":
        lines.append({"type": "api-request", "params": params})
    with open(os.path.join(folder, f"{sid}.jsonl"), "w", encoding="utf-8") as f:
        for ev in lines:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def main():
    argv = sys.argv[1:]
    prompt = sys.stdin.buffer.read().decode("utf-8")
    mode = os.environ.get("FAKE_BASELINE_MODE", "ok")
    record = os.environ.get("FAKE_BASELINE_RECORD")
    if record:
        with open(record, "w", encoding="utf-8") as f:
            json.dump({"argv": argv, "cwd": os.getcwd(), "fijas": {k: os.environ.get(k) for k in FIXED_ENV},
                       "nombres": sorted(os.environ)}, f, indent=1)
    model = opt(argv, "--model")
    sid = str(uuid.uuid4())
    n = int(re.search(r"into exactly (\d+) microservices", prompt).group(1))
    classes = re.findall(r"^### (\S+)$", prompt, flags=re.M)

    emit({"type": "system", "subtype": "init", "cwd": os.getcwd(), "session_id": sid,
          "tools": ["Bash"] if mode == "tools_init" else [],
          "mcp_servers": [{"name": "x", "status": "connected"}] if mode == "mcp_init" else [], "model": model,
          "permissionMode": "default", "slash_commands": [], "apiKeySource": "none",
          "claude_code_version": "2.1.325", "output_style": "default", "skills": []})
    if mode in ("tools_init", "mcp_init"):
        time.sleep(30)  # run_baseline.py debe cortar aqui (corte temprano); si no, la prueba lo nota por el tiempo
    if mode == "timeout":
        time.sleep(60)
    write_transcript(sid, prompt, model, mode)
    if mode == "api_error":
        emit({"type": "result", "subtype": "success", "is_error": True, "num_turns": 1, "session_id": sid,
              "api_error_status": 429, "result": "API Error: 429 You've hit your 5-hour limit",
              "total_cost_usd": 0, "usage": {}})
        return 0
    if mode == "missing":
        classes = classes[3:] + ["com.example.Invented"]
    k = n - 1 if mode == "wrong_n" else n
    services = {f"Service{i + 1}": classes[i::k] for i in range(k)}
    if len(classes) > 1:
        services["Service2"].append(classes[0])  # una clase compartida (classes[0] esta en Service1)
    body = json.dumps(services, indent=2)
    text = {"ok": body, "fenced": f"```json\n{body}\n```", "text_around": f"Here is the decomposition:\n\n{body}\n\nDone.",
            "invalid": "I cannot do that.", "list": json.dumps(list(services)),
            "nonlist": json.dumps({"Service1": "all"}),
            "duplicate_keys": '{"A": ["x.Y"], "B": ["x.Z"], "A": ["x.W"]}',
            "max_tokens": body[: len(body) // 2]}.get(mode, body)
    content = []
    if mode == "thinking":
        content.append({"type": "thinking", "thinking": "..."})
    if mode == "tool":
        content.append({"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}})
    content.append({"type": "text", "text": text})
    emit({"type": "assistant", "session_id": sid, "message": {
        "id": "msg_" + sid[:8], "role": "assistant", "content": content,
        "stop_reason": "max_tokens" if mode == "max_tokens" else "end_turn",
        "model": "claude-opus-4-1" if mode == "wrong_model" else model}})
    if mode == "no_result":
        sys.stderr.write("fake_claude_baseline: fallo simulado sin evento result\n")
        return 1
    emit({"type": "result", "subtype": "success", "is_error": False, "num_turns": 1, "session_id": sid,
          "result": text, "duration_ms": 1000, "duration_api_ms": 900, "total_cost_usd": 0.01,
          "usage": {"input_tokens": 10, "output_tokens": 100, "cache_creation_input_tokens": 2000,
                    "cache_read_input_tokens": 0}, "permission_denials": []})
    return 3 if mode == "exit_nonzero" else 0


if __name__ == "__main__":
    sys.exit(main())
