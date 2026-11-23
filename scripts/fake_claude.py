"""Sustituto de `claude -p` para probar run_pipeline.py SIN gastar cupo (lo usa test_pipeline_offline.py).

Acepta la misma linea de comandos que arma el orquestador, lee el prompt por stdin y emite por stdout un
flujo `stream-json` con la misma forma que el de Claude Code 2.1.325 (eventos init / assistant / user /
result; ver logs/cli_checks/check5_mcp_filtered_stream.jsonl). No llama a ningun modelo: responde con un
guion, que tiene las mismas claves que el del LLM simulado de capture_crewai_prompts.py, de modo que el
orquestador recorre el mismo camino que recorrio el main.py original en las capturas de logs/prompts_golden/.

Variables de entorno:
    FAKE_CLAUDE_SCENARIO   ruta del JSON con el guion (obligatoria)
    FAKE_CLAUDE_REAL_MCP   etapas (domain,clustering,merging,common,review separadas por comas, o "all") en
                           las que se lanza el servidor MCP REAL de la configuracion recibida y las llamadas
                           a herramientas pasan por el. En las demas, write_result_to_json se imita escribiendo
                           RESULT_FILE y MICROAGENT_LOG directamente.
Claves opcionales del guion:
    final_label (bool)     si es false, el texto final no lleva "Final Answer:"
    faults {etapa: fallo}  mcp_failed | extra_tool_visible | max_turns | api_error | thinking | tool_outside |
                           wrong_model | no_result   (etapa = domain, clustering, merging, common o review)
                           forced_tool | forced_tool_text | forced_api_error: el agente agota el limite de turnos
                           y, en la llamada que pide la respuesta final (`--resume`, D39), pide una herramienta
                           sin texto / con texto / devuelve un error de la API; forced_tool_undenied: pide
                           una herramienta con texto y NO consta como denegada (debe invalidar la llamada).
Contabilidad (como Claude Code 2.1.325, D39): cada peticion cuesta USD 0.01, 10 tokens de entrada y 100 de
salida. `usage`, `num_turns` y `duration_ms` son de esta llamada; `total_cost_usd`, `duration_api_ms` y
`modelUsage` son acumulados de la sesion (al reanudar se suman a los de la llamada anterior).
Limite de turnos: si el guion necesita tantas peticiones con herramientas como `--max-turns` antes de la respuesta
final, termina con `error_max_turns` (como el real) y guarda la respuesta pendiente; al reanudar la sesion con
`--resume <id>` la devuelve.
    search_file_paths {etapa: [rutas]}  llamadas a search_file antes de la respuesta final
"""
import argparse
import asyncio
import json
import os
import re
import sys
import time
import uuid

ROLES = {
    "Expert Software Architect - domain agent": "domain",
    "Expert Software Architect - clustering agent": "clustering",
    "Expert Software Architect - merging agent": "merging",
    "Expert Software Architect - common class agent": "common",
    "Expert Software Architect - review agent": "review",
}
PREFIX = "mcp__microagent__"


def emit(ev: dict) -> None:
    sys.stdout.write(json.dumps(ev, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--print", action="store_true")
    ap.add_argument("--resume")
    ap.add_argument("--model")
    ap.add_argument("--effort")
    ap.add_argument("--system-prompt", default="")
    ap.add_argument("--tools")
    ap.add_argument("--mcp-config")
    ap.add_argument("--strict-mcp-config", action="store_true")
    ap.add_argument("--allowedTools")
    ap.add_argument("--disable-slash-commands", action="store_true")
    ap.add_argument("--setting-sources")
    ap.add_argument("--max-turns", type=int)
    ap.add_argument("--output-format")
    ap.add_argument("--verbose", action="store_true")
    return ap.parse_args()


class Server:
    """Llamadas a herramientas: por el servidor MCP real, o imitando lo minimo que el orquestador observa."""

    def __init__(self, cfg: dict, real: bool):
        self.cfg = cfg["mcpServers"]["microagent"]
        self.env = self.cfg["env"]
        self.real = real
        self.session = None
        self._stack = None

    async def __aenter__(self):
        if self.real:
            from contextlib import AsyncExitStack
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            env = dict(os.environ)
            env.update(self.env)
            params = StdioServerParameters(command=self.cfg["command"], args=self.cfg["args"], env=env, cwd=os.getcwd())
            self._stack = AsyncExitStack()
            read, write = await self._stack.enter_async_context(stdio_client(params))
            self.session = await self._stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
        return self

    async def __aexit__(self, *exc):
        if self._stack:
            await self._stack.aclose()

    async def tool_names(self) -> list:
        if self.real:
            return [t.name for t in (await self.session.list_tools()).tools]
        return [n for n in self.env.get("MICROAGENT_TOOLS", "").split(",") if n]

    async def call(self, name: str, args: dict) -> str:
        if self.real:
            res = await self.session.call_tool(name, args)
            return "".join(getattr(c, "text", "") for c in res.content)
        text = f"(simulado) {name}"
        if name == "write_result_to_json":  # lo que hace el servidor: fusionar con RESULT_FILE y reescribirlo
            path = self.env["RESULT_FILE"]
            data = {}
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            data[args["domain_name"]] = args["class_list"]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            text = (f"Successfully saved {len(args['class_list'])} classes for domain '{args['domain_name']}'. "
                    f"Total domains saved so far: {len(data)}")
        with open(self.env["MICROAGENT_LOG"], "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"event": "call", "tool": name, "args": args, "result_chars": len(text)}) + "\n")
        return text


async def run() -> int:
    a = parse_args()
    prompt = sys.stdin.buffer.read().decode("utf-8")
    with open(os.environ["FAKE_CLAUDE_SCENARIO"], encoding="utf-8") as f:
        sc = json.load(f)
    with open(a.mcp_config, encoding="utf-8") as f:
        cfg = json.load(f)
    role = re.match(r"You are (.*?)\. ", a.system_prompt)
    stage = ROLES[role.group(1)]
    fault = (sc.get("faults") or {}).get(stage)
    real_stages = [s for s in os.environ.get("FAKE_CLAUDE_REAL_MCP", "").split(",") if s]
    real = "all" in real_stages or stage in real_stages
    sid = a.resume or str(uuid.uuid4())
    state_path = os.path.join(os.path.dirname(os.environ["FAKE_CLAUDE_SCENARIO"]), f"fake_session_{sid}.json")
    model = "claude-other-model" if fault == "wrong_model" else a.model
    hits_limit = fault in ("max_turns", "forced_tool", "forced_tool_text", "forced_api_error", "forced_tool_undenied")
    started = time.time()
    turns = 0
    prior = {"requests": 0}
    if a.resume and os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as f:
            prior = json.load(f)

    def assistant(blocks, msg_id=None):
        # Cada llamada sin msg_id es una peticion nueva a la API (en el flujo real, un `message.id` distinto).
        nonlocal turns
        turns += 1
        emit({"type": "assistant", "session_id": sid,
              "message": {"id": msg_id or f"msg_{sid[:8]}_{prior['requests'] + turns}", "model": model,
                          "role": "assistant", "type": "message", "content": blocks}})

    def acct(requests):
        total = prior["requests"] + requests
        return {"duration_ms": 1, "duration_api_ms": 7 * total, "total_cost_usd": round(0.01 * total, 6),
                "usage": {"input_tokens": 10 * requests, "output_tokens": 100 * requests,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
                "modelUsage": {model: {"inputTokens": 10 * total, "outputTokens": 100 * total}}}

    async with Server(cfg, real) as server:
        names = await server.tool_names()
        visible = [PREFIX + n for n in names]
        status = "connected"
        if fault == "mcp_failed":
            visible, status = [], "failed"
        elif fault == "extra_tool_visible":
            visible = visible + ["Read"]
        emit({"type": "system", "subtype": "init", "cwd": os.getcwd(), "session_id": sid, "tools": visible,
              "mcp_servers": [{"name": "microagent", "status": status}], "model": a.model,
              "slash_commands": [], "skills": [], "apiKeySource": "none", "claude_code_version": "simulado",
              # Lo que este proceso recibio DE VERDAD (no lo que el orquestador dice haber enviado): la prueba
              # lo compara con valores escritos a mano y con crew.py. Solo nombres de variables, sin valores,
              # salvo las que fija la replica.
              "_fake_argv": sys.argv[1:], "_fake_env_names": sorted(os.environ),
              "_fake_env": {k: os.environ.get(k) for k in (
                  "MAX_THINKING_TOKENS", "MCP_TIMEOUT", "MCP_TOOL_TIMEOUT", "DISABLE_AUTOUPDATER", "API_TIMEOUT_MS",
                  "CLAUDE_CODE_DISABLE_CLAUDE_MDS", "CLAUDE_CODE_DISABLE_AUTO_MEMORY", "PYTHONDONTWRITEBYTECODE")},
              **({"_fake_stdin": prompt} if a.resume else {})})
        if fault in ("mcp_failed", "extra_tool_visible"):
            # Un `claude` real seguiria adelante y hasta devolveria "success" (D22): el orquestador debe cortar antes.
            time.sleep(20)
            emit({"type": "result", "subtype": "success", "is_error": False, "num_turns": 1, "session_id": sid,
                  "result": "Final Answer: {\"business_domains\": [{\"domain_name\": \"Inventado\", \"description\": \"x\"}]}"})
            return 0
        if fault == "no_result":
            sys.stderr.write("fake_claude: fallo simulado sin evento result\n")
            return 2

        async def tool(name, args):
            tid = "toolu_" + uuid.uuid4().hex[:20]
            assistant([{"type": "tool_use", "id": tid, "name": PREFIX + name if name in names else name, "input": args}])
            text = await server.call(name, args) if name in names else "denied"
            emit({"type": "user", "session_id": sid, "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tid, "content": [{"type": "text", "text": text}]}]}})

        def max_turns_result(denials=()):
            emit({"type": "result", "subtype": "error_max_turns", "is_error": True, "num_turns": turns + 1,
                  "session_id": sid, **acct(turns), "permission_denials": list(denials)})

        if a.resume:  # la llamada que pide la respuesta final tras agotar el limite (D39)
            pending = prior["final"]
            if fault == "forced_api_error":
                emit({"type": "result", "subtype": "success", "is_error": True, "num_turns": 1, "session_id": sid,
                      "api_error_status": 429, "result": "API Error: 429 You've hit your 5-hour limit",
                      "duration_ms": 1, "duration_api_ms": 1, "total_cost_usd": 0.0, "usage": {}})
                return 1
            if fault in ("forced_tool", "forced_tool_text", "forced_tool_undenied"):
                # El modelo pide una herramienta pese a la instruccion: sin --allowedTools, Claude Code la
                # deniega y NO se ejecuta (aqui no se llama al servidor).
                tid = "toolu_" + uuid.uuid4().hex[:20]
                call = {"type": "tool_use", "id": tid, "name": PREFIX + names[-1],  # una herramienta del propio agente
                        "input": {"domain_name": "No Debe Escribirse", "class_list": ["x.Y"]}}
                one = f"msg_{sid[:8]}_forzada"
                if fault in ("forced_tool_text", "forced_tool_undenied"):
                    assistant([{"type": "text", "text": "Let me save one more domain before answering."}], one)
                assistant([call], one)
                turns = 1
                emit({"type": "user", "session_id": sid, "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": tid, "is_error": True,
                     "content": "Claude requested permissions to use this tool, but you haven't granted it yet."}]}})
                max_turns_result([] if fault == "forced_tool_undenied" else
                                 [{"tool_name": call["name"], "tool_use_id": tid, "tool_input": call["input"]}])
                return 1
            assistant([{"type": "text", "text": pending}])
            emit({"type": "result", "subtype": "success", "is_error": False, "num_turns": 1, "session_id": sid,
                  "result": pending, **acct(1), "permission_denials": []})
            return 0

        if fault == "thinking":
            assistant([{"type": "thinking", "thinking": "..."}])
        if fault == "tool_outside":
            await tool("Read", {"file_path": "x"})
        for path in (sc.get("search_file_paths") or {}).get(stage, []):
            await tool("search_file", {"path": path, "term": "class"})
        if fault == "api_error":
            emit({"type": "result", "subtype": "success", "is_error": True, "num_turns": 1, "session_id": sid,
                  "api_error_status": 429, "result": "API Error: 429 You've hit your 5-hour limit",
                  "duration_ms": 1, "duration_api_ms": 1, "total_cost_usd": 0.0, "usage": {}})
            return 1

        # Guion: mismas respuestas que el LLM simulado de capture_crewai_prompts.py.
        if stage == "domain":
            text = sc["domain_raw"]
        elif stage == "clustering":
            name = re.search(r"You are analyzing the '(.*?)' domain\. The description", prompt, re.S).group(1)
            by_sent_name = {k.replace("{num}", sc["num"]).replace("{number}", sc["number"]): v
                            for k, v in sc["clustering_raw"].items()}
            text = by_sent_name[name]
        elif stage == "merging":
            text = sc["merging_raw"]
        else:
            writes, text = (sc["common_writes"], sc["common_final"]) if stage == "common" else \
                           (sc["review_writes"], sc["review_final"])
            for domain_name, class_list in writes:
                await tool("write_result_to_json", {"domain_name": domain_name, "class_list": class_list})
        if sc.get("final_label", True):
            text = "Thought: I now know the final answer\nFinal Answer: " + text
        if hits_limit and turns == 0:
            await tool(names[0], {})
        if hits_limit or (a.max_turns is not None and turns >= a.max_turns):
            # Como el real: tras N peticiones que piden herramientas ya no hay otra para la respuesta final.
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump({"final": text, "requests": turns}, f)
            max_turns_result()
            return 1
        assistant([{"type": "text", "text": text}])
        ms = int((time.time() - started) * 1000)
        emit({"type": "result", "subtype": "success", "is_error": False, "num_turns": turns, "session_id": sid,
              "result": text, **dict(acct(turns), duration_ms=ms), "permission_denials": []})
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
