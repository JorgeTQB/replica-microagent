"""Comprueba con UNA llamada real a `claude -p` que Claude Code usa el servidor MCP "microagent" y que el
aislamiento de herramientas de §5.3 funciona (sin herramientas integradas, solo las MCP permitidas).

Guarda el flujo completo en logs/cli_checks/<nombre>_stream.jsonl e imprime un resumen: herramientas que ve
el modelo, estado del servidor MCP, herramientas llamadas, denegaciones y bloques thinking.

Uso: python -X utf8 scripts/check_mcp_with_claude.py --name check4_mcp [--expose-all]
  --expose-all  no pasa MICROAGENT_TOOLS al servidor (publica las 14) para ver que ve el modelo en ese caso.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from claude_cli import BASE, EXTRA_ENV, MCP_ENV, MODEL, SANDBOX  # noqa: E402

APP, RUN_ID = "jpetstore-6", "smoke-test"
ALLOWED = ["get_class_summary"]
PROMPT = ("Call the get_class_summary tool for the class org.mybatis.jpetstore.domain.Cart. Then call the "
          "get_database_summary tool. Finally reply with one line listing which of the two calls succeeded.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--expose-all", action="store_true")
    a = ap.parse_args()

    run_dir = os.path.join(BASE, "output", APP, RUN_ID)
    os.makedirs(run_dir, exist_ok=True)
    log_dir = os.path.join(BASE, "logs", "cli_checks")
    env_server = {"APP_NAME": APP, "RUN_ID": RUN_ID,
                  "MICROAGENT_LOG": os.path.join(log_dir, f"{a.name}_server.jsonl")}
    if a.expose_all:
        # Con las 14 publicadas, write_result_to_json exige RESULT_FILE (mcp_server.py).
        env_server["RESULT_FILE"] = os.path.join(run_dir, f"{a.name}_result.json")
    else:
        env_server["MICROAGENT_TOOLS"] = ",".join(ALLOWED)
    cfg = {"mcpServers": {"microagent": {
        "command": sys.executable,
        "args": ["-X", "utf8", os.path.join(BASE, "tools", "mcp_server.py")],
        "env": env_server,
    }}}
    # En logs/cli_checks/ y no en output/.../smoke-test/, que smoke_test_tools.py borra al ejecutarse.
    cfg_path = os.path.join(log_dir, f"{a.name}_mcp_config.json")
    with open(cfg_path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)

    os.makedirs(SANDBOX, exist_ok=True)
    assert not os.listdir(SANDBOX), "_sandbox no esta vacio"
    cmd = [shutil.which("claude"), "-p", "--model", MODEL, "--system-prompt", "", "--tools", "",
           "--mcp-config", cfg_path, "--strict-mcp-config",
           "--allowedTools", ",".join(f"mcp__microagent__{t}" for t in ALLOWED),
           "--disable-slash-commands", "--setting-sources", "", "--max-turns", "6",
           "--output-format", "stream-json", "--verbose"]
    env = dict(os.environ)
    env.update(EXTRA_ENV)
    env.update(MCP_ENV)
    proc = subprocess.run(cmd, input=PROMPT.encode("utf-8"), capture_output=True, cwd=SANDBOX, env=env, timeout=600)
    out = proc.stdout.decode("utf-8", errors="replace")
    with open(os.path.join(log_dir, f"{a.name}_stream.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(out)
    with open(os.path.join(log_dir, f"{a.name}_stderr.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(proc.stderr.decode("utf-8", errors="replace"))

    tool_uses, thinking, denials, results = [], 0, [], []
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            print("modelo:", ev.get("model"), "| herramientas visibles:", ev.get("tools"))
            print("servidores MCP:", ev.get("mcp_servers"))
        msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
        for block in msg.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                tool_uses.append(block.get("name"))
            elif block.get("type") in ("thinking", "redacted_thinking"):
                thinking += 1
            elif block.get("type") == "tool_result":
                content = block.get("content")
                text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                results.append((bool(block.get("is_error")), text[:160]))
        if ev.get("type") == "result":
            denials = ev.get("permission_denials") or []
            print("resultado:", ev.get("subtype"), "| turnos:", ev.get("num_turns"), "| is_error:", ev.get("is_error"))
            print("texto final:", str(ev.get("result"))[:300])
    print("exit code:", proc.returncode)
    print("tool_use:", tool_uses)
    print("tool_result (is_error, inicio):", results)
    print("permission_denials:", [d.get("tool_name") for d in denials])
    print("bloques thinking:", thinking)
    print("_sandbox tras la llamada:", os.listdir(SANDBOX))


if __name__ == "__main__":
    main()
