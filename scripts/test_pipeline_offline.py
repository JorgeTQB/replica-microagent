"""Prueba de run_pipeline.py SIN gastar cupo (Fase 4).

Ejecuta el orquestador con `scripts/fake_claude.py` en lugar de `claude` y comprueba:

  A. Fidelidad a main.py. Para cada captura de logs/prompts_golden/ (el main.py ORIGINAL ejecutado con
     CrewAI 1.8.1 real y un LLM simulado, Fase 3), el orquestador recibe las mismas respuestas guionizadas y
     debe producir: las mismas etapas en el mismo orden, el mismo mensaje de usuario en cada una (byte a
     byte) y los mismos archivos de salida con el mismo contenido que dejo el original.
  B. Ramas que las capturas no cubren: dominios omitidos (desajuste de main.py, D31), dominios vacios, JSON
     invalido, respaldos de las etapas 4 y 5, respuesta sin "Final Answer:".
  C. Validez de cada llamada (D22): servidor MCP sin conectar, herramientas de mas, limite de turnos, error
     de la API, razonamiento extendido, otro modelo, herramienta fuera de lista, sin resultado.
  D. Cadena completa con el servidor MCP real (write_result_to_json, RESULT_FILE, auditoria de rutas).
  E. Piezas sueltas: copia literal de clean_json_output, regla de "Final Answer:", nombres de archivo,
     clasificacion de rutas, lectura de una transcripcion real, protecciones del orquestador.

Tras la revision de la fase (D38) compara ademas lo que el proceso `claude` simulado recibe de verdad
(argumentos y entorno) con el crew.py original y con valores escritos a mano en este archivo.

Uso: python -X utf8 scripts/test_pipeline_offline.py [--keep] [--skip-real-mcp] [--solo-capturas TEXTO]
Salida: logs/pipeline_offline_test.txt y codigo de salida 0 si todo coincide.
Las corridas de prueba usan identificadores `_prueba-...` en output/<app>/ y se borran al terminar.
"""
import argparse
import ast
import contextlib
import copy
import glob
import inspect
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import run_pipeline as rp  # noqa: E402

GOLDEN_DIR = os.path.join(BASE, "logs", "prompts_golden")
OUT = os.path.join(BASE, "logs", "pipeline_offline_test.txt")
ORIGINAL_MAIN = os.path.join(os.path.dirname(BASE), "MicroAgent", "microagent", "src", "microagent", "main.py")
ORIGINAL_DIR = os.path.dirname(ORIGINAL_MAIN)
STAGE_OF = {"1": "domain", "2": "clustering", "3": "merging", "4": "common", "5": "review"}
# Valores escritos a mano (NO se leen de run_pipeline.py): lo que debe recibir el proceso `claude` (D35, D38).
EXPECTED_ENV = {"MAX_THINKING_TOKENS": "0", "MCP_TIMEOUT": "300000", "MCP_TOOL_TIMEOUT": "600000",
                "DISABLE_AUTOUPDATER": "1", "API_TIMEOUT_MS": "900000", "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
                "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "PYTHONDONTWRITEBYTECODE": "1"}
EXPECTED_MODEL, EXPECTED_EFFORT = "claude-sonnet-4-6", "high"
# Texto de CrewAI 1.8.1 (translations/en.json, errors.force_final_answer), escrito a mano; ademas se compara con
# el mensaje que el original envio de verdad en la captura jpetstore_limite_de_iteraciones.
FORCE_TEXT = ("Now it's time you MUST give your absolute best final answer. You'll ignore all previous instructions, "
              "stop using any tools, and just return your absolute BEST Final answer.")
# Variables que la prueba pone en el entorno del orquestador imitando a la sesion que lo lanza: ninguna debe
# llegar al proceso `claude` (y MAX_THINKING_TOKENS debe llegar con el valor de la replica, no con este).
INHERITED_ENV = {"CLAUDE_HEREDADA_DE_PRUEBA": "x", "ANTHROPIC_HEREDADA_DE_PRUEBA": "x", "CLAUDE_EFFORT": "low",
                 "DISABLE_MICROCOMPACT": "1", "MCP_CONNECTION_NONBLOCKING": "true", "AI_AGENT": "prueba",
                 "MAX_THINKING_TOKENS": "31999", "API_TIMEOUT_MS": "1", "USE_STAGING_OAUTH": "1"}
ALLOWED_CLAUDE_VARS = {"CLAUDE_CODE_DISABLE_CLAUDE_MDS", "CLAUDE_CODE_DISABLE_AUTO_MEMORY", "CLAUDE_CONFIG_DIR"}


def original_agent_config() -> dict:
    """Herramientas (por su nombre, en orden) y max_iter de cada agente, leidos del crew.py y del
    custom_tools.py ORIGINALES con `ast` (sin importarlos)."""
    with open(os.path.join(ORIGINAL_DIR, "tools", "custom_tools.py"), encoding="utf-8") as f:
        tools_tree = ast.parse(f.read())
    tool_name = {}
    for node in ast.walk(tools_tree):
        if isinstance(node, ast.ClassDef):
            for st in node.body:
                if (isinstance(st, ast.AnnAssign) and getattr(st.target, "id", None) == "name"
                        and isinstance(st.value, ast.Constant)):
                    tool_name[node.name] = st.value.value
    with open(os.path.join(ORIGINAL_DIR, "crew.py"), encoding="utf-8") as f:
        crew_tree = ast.parse(f.read())
    config = {}
    methods = {"domain_agent": "domain", "clustering_agent": "clustering", "merging_agent": "merging",
               "common_class_agent": "common", "review_agent": "review"}
    for node in ast.walk(crew_tree):
        if isinstance(node, ast.FunctionDef) and node.name in methods:
            call = next(n for n in ast.walk(node) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "Agent")
            kw = {k.arg: k.value for k in call.keywords}
            config[methods[node.name]] = {"tools": [tool_name[e.func.id] for e in kw["tools"].elts],
                                          "max_iter": kw["max_iter"].value}
    return config


CREW = original_agent_config()

lines, problems = [], []
ARGS = None


def log(msg=""):
    lines.append(msg)
    print(msg, flush=True)


def check(ok, label, detail=""):
    if not ok:
        problems.append(label)
    log(f"  [{'OK' if ok else 'FALLA'}] {label}" + (f" -- {detail}" if detail and not ok else ""))
    return ok


def norm(text: str) -> str:
    return text.replace("\r\n", "\n")


def run_dir(app, run_id):
    return os.path.join(BASE, "output", app, run_id)


def clean(app, run_id):
    assert run_id.startswith(rp.TEST_RUN_PREFIX)
    shutil.rmtree(run_dir(app, run_id), ignore_errors=True)


def run(scenario: dict, run_id: str, extra=(), real_mcp: str = "", fake: bool = True):
    """Ejecuta run_pipeline.py. Devuelve (codigo de salida, salida, status o None)."""
    app = scenario["app"]
    with tempfile.TemporaryDirectory() as tmp:
        sc_path = os.path.join(tmp, "scenario.json")
        with open(sc_path, "w", encoding="utf-8") as f:
            json.dump(scenario, f)
        env = dict(os.environ)
        env.update(INHERITED_ENV)
        env.pop("MICROAGENT_CLAUDE_CMD", None)
        if fake:
            env["MICROAGENT_CLAUDE_CMD"] = json.dumps([sys.executable, "-X", "utf8", os.path.join(BASE, "scripts", "fake_claude.py")])
        env["FAKE_CLAUDE_SCENARIO"] = sc_path
        env["FAKE_CLAUDE_REAL_MCP"] = real_mcp
        proc = subprocess.run([sys.executable, "-X", "utf8", os.path.join(BASE, "run_pipeline.py"), "--app", app,
                               "--run-id", run_id, *extra], env=env, capture_output=True, timeout=1800)
    out = proc.stdout.decode("utf-8", errors="replace") + proc.stderr.decode("utf-8", errors="replace")
    status_path = os.path.join(run_dir(app, run_id), "logs", "run_status.json")
    status = None
    if os.path.exists(status_path):
        with open(status_path, encoding="utf-8") as f:
            status = json.load(f)
    return proc.returncode, out, status


def output_files(app, run_id) -> dict:
    root, found = run_dir(app, run_id), {}
    for dirpath, dirs, files in os.walk(root):
        if os.path.abspath(dirpath) == os.path.abspath(root):
            dirs[:] = [d for d in dirs if d != "logs"]
        for fn in files:
            p = os.path.join(dirpath, fn)
            with open(p, encoding="utf-8", newline="") as f:
                found[os.path.relpath(p, root).replace("\\", "/")] = f.read()
    return found


def stage_names(status) -> list:
    return [STAGE_OF[e["etapa"][0]] for e in status["etapas"]]


def obs_types(status) -> list:
    return [o["tipo"] for o in status["observaciones"]]


def finish(app, run_id):
    if not ARGS.keep:
        clean(app, run_id)


# --------------------------------------------------------------------------------------------------
# A. Capturas del original
# --------------------------------------------------------------------------------------------------
def test_golden(path, real_mcp="", suffix="", scenario_patch=None, expect_same_outputs=True):
    with open(path, encoding="utf-8") as f:
        g = json.load(f)
    sc = copy.deepcopy(g["scenario"])
    sc.update(scenario_patch or {})
    app, run_id = sc["app"], f"{rp.TEST_RUN_PREFIX}{sc['name']}{suffix}"
    log(f"\n== {os.path.basename(path)}{suffix}  (app={app}, {len(g['executions'])} ejecuciones de agente en el original"
        f"{', servidor MCP real en: ' + real_mcp if real_mcp else ''})")
    clean(app, run_id)
    code, out, status = run(sc, run_id, real_mcp=real_mcp)
    if not check(status is not None, "el orquestador deja run_status.json", out[-1500:]):
        return None
    original_aborted = bool(g.get("error"))
    check((code != 0) == original_aborted and status["estado"] == ("fallida" if original_aborted else "completa"),
          f"estado {status['estado']!r} y codigo de salida {code} (el original {'aborto' if original_aborted else 'termino'})",
          json.dumps(status.get("fallo"), ensure_ascii=False))
    if original_aborted:
        check(status["fallo"]["motivo"] == "el_original_habria_abortado_al_interpolar",
              "la corrida falla donde el original aborta (variable desconocida al interpolar)", str(status["fallo"]))
        log(f"       original: {g['error']}")
        log(f"       replica : {status['fallo']['detalle']}")
    expected_stages = [e["stage"] for e in g["executions"]]
    check(stage_names(status) == expected_stages, "mismas ejecuciones de agente y en el mismo orden que el original",
          f"{stage_names(status)} vs {expected_stages}")
    logs = os.path.join(run_dir(app, run_id), "logs")
    same_user = same_system = received_ok = 0
    for entry, e in zip(status["etapas"], g["executions"]):
        with open(os.path.join(logs, f"{entry['etapa']}_prompt.txt"), encoding="utf-8", newline="") as f:
            user = f.read()
        with open(os.path.join(logs, f"{entry['etapa']}_system_prompt.txt"), encoding="utf-8", newline="") as f:
            system = f.read()
        same_user += user == e["user"]
        same_system += e["system"].startswith(system) and len(system) > 100
        with open(os.path.join(logs, f"{entry['etapa']}_claude.json"), encoding="utf-8") as f:
            rec = json.load(f)
        cmd = rec["_cmd"]
        sent_system = cmd[cmd.index("--system-prompt") + 1]
        allowed = cmd[cmd.index("--allowedTools") + 1].split(",")
        stage = STAGE_OF[entry["etapa"][0]]
        if not (sent_system == system and cmd[cmd.index("--tools") + 1] == ""
                and allowed == [rp.MCP_PREFIX + t for t in rp.AGENT_TOOLS[stage]]
                and cmd[cmd.index("--max-turns") + 1] == str(rp.MAX_TURNS[stage])
                and "--strict-mcp-config" in cmd
                and rec["_mcp_config"]["mcpServers"]["microagent"]["env"]["MICROAGENT_TOOLS"] == ",".join(rp.AGENT_TOOLS[stage])
                and ("RESULT_FILE" in rec["_mcp_config"]["mcpServers"]["microagent"]["env"]) == (stage in ("common", "review"))):
            check(False, f"{entry['etapa']}: linea de comandos y configuracion MCP del agente", str(cmd)[:400])
        # Lo que el proceso `claude` (simulado) recibio de verdad, contra crew.py y valores escritos a mano.
        init = rec.get("_init") or {}
        argv, names = init.get("_fake_argv") or [], init.get("_fake_env_names") or []
        opt = lambda o: argv[argv.index(o) + 1] if o in argv else None  # noqa: E731
        leaked = sorted(k for k in names if (k in INHERITED_ENV and k not in EXPECTED_ENV)
                        or (k.upper().startswith(("CLAUDE", "ANTHROPIC")) and k.upper() not in ALLOWED_CLAUDE_VARS))
        received_ok += (opt("--model") == EXPECTED_MODEL and opt("--effort") == EXPECTED_EFFORT
                        and opt("--max-turns") == str(CREW[stage]["max_iter"])
                        and (opt("--allowedTools") or "").split(",") == ["mcp__microagent__" + t for t in CREW[stage]["tools"]]
                        and rec["_mcp_config"]["mcpServers"]["microagent"]["env"]["MICROAGENT_TOOLS"] == ",".join(CREW[stage]["tools"])
                        and opt("--tools") == "" and opt("--setting-sources") == "" and opt("--output-format") == "stream-json"
                        and "--strict-mcp-config" in argv and "--disable-slash-commands" in argv
                        and init.get("_fake_env") == EXPECTED_ENV and not leaked)
        if leaked:
            log(f"       variables heredadas que llegaron a `claude` en {entry['etapa']}: {leaked}")
    check(received_ok == len(status["etapas"]),
          "cada `claude` recibe modelo, esfuerzo, max-turns y herramientas de crew.py, el entorno fijado y ninguna variable heredada",
          f"{received_ok} de {len(status['etapas'])}")
    # Limite de turnos (D39): la respuesta final forzada ocurre donde ocurre en el original y con su texto.
    forced_expected = [i for i, e in enumerate(g["executions"]) if e.get("forced_final_answer")]
    forced_got = [i for i, e in enumerate(status["etapas"]) if e.get("limite_de_turnos")]
    check(forced_got == forced_expected,
          f"respuesta final forzada en las mismas ejecuciones que el original ({len(forced_expected)})",
          f"replica {forced_got} vs original {forced_expected}")
    for i in forced_expected:
        if i >= len(status["etapas"]) or not status["etapas"][i].get("limite_de_turnos"):
            continue
        entry, e = status["etapas"][i], g["executions"][i]
        stage = STAGE_OF[entry["etapa"][0]]
        with open(os.path.join(logs, f"{entry['etapa']}_claude.json"), encoding="utf-8") as f:
            rec = json.load(f)
        finit = (rec.get("_forzada") or {}).get("init") or {}
        fargv, sent = finit.get("_fake_argv") or [], finit.get("_fake_stdin")
        fopt = lambda o: fargv[fargv.index(o) + 1] if o in fargv else None  # noqa: E731
        check(sent == FORCE_TEXT == rp.FORCE_FINAL_ANSWER and e["forced_final_answer"]["last_message"].endswith("\n" + sent)
              and e["forced_final_answer"]["roles_tail"][-1] == "assistant",
              f"{entry['etapa']}: el mensaje que pide la respuesta final es el texto que CrewAI anadio en el original",
              repr(sent)[:200])
        with open(os.path.join(logs, f"{entry['etapa']}_system_prompt.txt"), encoding="utf-8", newline="") as f:
            system = f.read()
        check(fopt("--resume") == entry["session_id"] and "--allowedTools" not in fargv and "--allowed-tools" not in fargv
              and fopt("--max-turns") == "1" and fopt("--model") == EXPECTED_MODEL and fopt("--effort") == EXPECTED_EFFORT
              and fopt("--system-prompt") == system and fopt("--tools") == "" and "--strict-mcp-config" in fargv
              and fopt("--mcp-config") == rec["_cmd"][rec["_cmd"].index("--mcp-config") + 1]
              and finit.get("_fake_env") == EXPECTED_ENV,
              f"{entry['etapa']}: la peticion forzada reanuda la misma sesion, con una sola peticion, las herramientas "
              f"declaradas pero ninguna permitida, y la misma configuracion", str(fargv)[:300])
        check(e["n_llm_calls"] == CREW[stage]["max_iter"] + 1 and entry["max_turns"] == CREW[stage]["max_iter"],
              f"{entry['etapa']}: max_iter + 1 llamadas al modelo en el original = max-turns peticiones + 1 forzada",
              f"original {e['n_llm_calls']}, max_turns {entry['max_turns']}")
    n = len(g["executions"])
    check(same_user == n == len(status["etapas"]), f"mensaje de usuario identico al del original en las {n} ejecuciones",
          f"{same_user} de {n}")
    check(same_system == n, f"system prompt = inicio del system del original en las {n} ejecuciones", f"{same_system} de {n}")
    if expect_same_outputs:
        mine, theirs = output_files(app, run_id), g["outputs"]
        check(sorted(mine) == sorted(theirs), "mismos archivos de salida que el original",
              f"replica {sorted(mine)} vs original {sorted(theirs)}")
        different = [k for k in theirs if k in mine and norm(mine[k]) != norm(theirs[k])]
        check(not different, f"contenido identico al del original en los {len(theirs)} archivos de salida", str(different))
        check(not any("\r" in v for v in mine.values()), "los archivos de salida usan saltos de linea LF")
    return status


# --------------------------------------------------------------------------------------------------
# B y C. Ramas y fallos que las capturas no cubren
# --------------------------------------------------------------------------------------------------
def base_scenario(name="jpetstore_con_fusion"):
    with open(os.path.join(GOLDEN_DIR, name + ".json"), encoding="utf-8") as f:
        return copy.deepcopy(json.load(f)["scenario"])


def test_branches():
    log("\n== Ramas que las capturas no cubren")
    app = "jpetstore-6"

    # Desajuste de dominios omitidos de main.py (D31): [A, B sin descripcion, C, D] -> {A: [...], B: [], C: []}
    sc = base_scenario()
    domains = json.loads(rp.clean_json_output(sc["domain_raw"]))["business_domains"]
    names = [d["domain_name"] for d in domains]
    del domains[1]["description"]
    sc["domain_raw"] = json.dumps({"business_domains": domains})
    run_id = rp.TEST_RUN_PREFIX + "desajuste"
    clean(app, run_id)
    code, out, st = run(sc, run_id)
    files = output_files(app, run_id)
    all_domains = json.loads(files.get("domains/all_domains.json", "null"))
    first = json.loads(rp.clean_json_output(sc["clustering_raw"][names[0]]))[names[0]]
    check(all_domains == {names[0]: first, names[1]: [], names[2]: []},
          "dominio sin descripcion: se reproduce el desajuste de main.py ({A: [...], B: [], C: []})", str(all_domains))
    check(st["fusion"] == "saltada" and stage_names(st) == ["domain", "clustering", "clustering", "clustering", "common", "review"],
          "la fusion se salta porque len == number, como en el original", f"{st['fusion']} {stage_names(st)}")
    check([e.get("dominio_de_la_tarea") for e in st["etapas"][1:4]] == [names[0], names[2], names[3]]
          and [e.get("dominio_emparejado") for e in st["etapas"][1:4]] == names[:3],
          "queda registrado que tarea se emparejo con que dominio")
    check("dominio_omitido" in obs_types(st) and obs_types(st).count("desajuste_de_dominios_del_original") == 2,
          "el desajuste queda documentado en las observaciones de la corrida", str(obs_types(st)))
    finish(app, run_id)

    for label, raw, expected in [
        ("Etapa 1 sin dominios", '{"business_domains": []}', "No business domains identified"),
        ("Etapa 1 con JSON invalido", "I could not identify any domain.", "Error parsing domain data string from Stage 1"),
    ]:
        sc = base_scenario()
        sc["domain_raw"] = raw
        run_id = rp.TEST_RUN_PREFIX + "etapa1-mala"
        clean(app, run_id)
        code, out, st = run(sc, run_id)
        check(code == 1 and st["estado"] == "fallida" and expected in st["fallo"]["detalle"] and stage_names(st) == ["domain"],
              f"{label}: el flujo se detiene como en main.py y la corrida queda fallida", str(st["fallo"]))
        finish(app, run_id)

    # Respaldos de las etapas 4 y 5 (main.py 384-395 y 473-488)
    sc = base_scenario("jpetstore_sin_fusion")
    common = {k: v for k, v in sc["common_writes"]}
    sc["common_writes"], sc["common_final"] = [], "```json\n" + json.dumps(common) + "\n```"
    final = {k: v for k, v in sc["review_writes"]}
    sc["review_writes"], sc["review_final"] = [], json.dumps(final)
    run_id = rp.TEST_RUN_PREFIX + "respaldos"
    clean(app, run_id)
    code, out, st = run(sc, run_id)
    files = output_files(app, run_id)
    check(code == 0 and json.loads(files.get("common_result.json", "null")) == common
          and json.loads(files.get("result.json", "null")) == final,
          "sin llamadas a write_result_to_json: common_result.json y result.json salen del texto de la respuesta")
    check(obs_types(st).count("sin_resultados_de_write_result_to_json") == 2, "el uso del respaldo queda registrado")
    check(st["resultado"]["particiones"] == len(final), "resumen final correcto (no el error de `final_result_raw` de main.py)")
    finish(app, run_id)

    sc["review_final"] = "All domains were saved."
    clean(app, run_id)
    code, out, st = run(sc, run_id)
    files = output_files(app, run_id)
    check(code == 1 and "result.json" not in files and files.get("result.txt") == "All domains were saved.",
          "Etapa 5 sin resultados ni JSON: se guarda result.txt, no hay result.json y la corrida queda fallida", str(sorted(files)))
    finish(app, run_id)

    # Respuesta sin la etiqueta "Final Answer:" (D31): se toma el texto completo y se anota
    g_path = os.path.join(GOLDEN_DIR, "jpetstore_con_fusion.json")
    st = test_golden(g_path, suffix="-sin-etiqueta", scenario_patch={"final_label": False})
    if st:
        check(obs_types(st).count("sin_etiqueta_final_answer") == len(st["etapas"])
              and not any(e["etiqueta_final_answer"] for e in st["etapas"]),
              "sin 'Final Answer:': mismas salidas y contexto, y queda anotado en cada etapa")
        finish("jpetstore-6", rp.TEST_RUN_PREFIX + "jpetstore_con_fusion-sin-etiqueta")


def test_faults():
    log("\n== Validez de cada llamada (una llamada invalida deja la corrida como fallida)")
    app = "jpetstore-6"
    cases = [
        ("mcp_failed", "domain", "servidor_mcp_o_herramientas", ["domain"]),
        ("extra_tool_visible", "domain", "servidor_mcp_o_herramientas", ["domain"]),
        ("no_result", "domain", "sin_resultado_de_claude", ["domain"]),
        ("thinking", "domain", "auditoria", ["domain"]),
        ("wrong_model", "domain", "auditoria", ["domain"]),
        ("tool_outside", "domain", "auditoria", ["domain"]),
        ("api_error", "clustering", "error_api_429", ["domain", "clustering"]),
        # Limite de turnos (D39): la respuesta forzada tambien puede fallar.
        ("forced_tool", "merging", "respuesta_forzada_vacia", ["domain"] + ["clustering"] * 4 + ["merging"]),
        ("forced_tool_undenied", "merging", "auditoria", ["domain"] + ["clustering"] * 4 + ["merging"]),
        ("forced_api_error", "review", "error_api_429", ["domain"] + ["clustering"] * 4 + ["merging", "common", "review"]),
    ]
    for fault, stage, motivo, stages in cases:
        sc = base_scenario()
        sc["faults"] = {stage: fault}
        run_id = rp.TEST_RUN_PREFIX + "fallo-" + fault.replace("_", "-")
        clean(app, run_id)
        code, out, st = run(sc, run_id)
        ok = (code == 1 and st and st["estado"] == "fallida" and st["fallo"]["motivo"] == motivo
              and stage_names(st) == stages and "result.json" not in output_files(app, run_id))
        check(ok, f"{fault} en {stage}: corrida fallida ({motivo}), sin etapas posteriores ni result.json",
              (json.dumps(st.get("fallo"), ensure_ascii=False) if st else out[-800:]))
        if fault == "forced_api_error" and st:
            check("result_parcial_de_corrida_fallida.json" in output_files(app, run_id)
                  and "result_json_parcial_apartado" in obs_types(st) and st["resultado"] is None,
                  "una corrida que falla con result.json a medias lo aparta con otro nombre")
        if fault in ("mcp_failed", "extra_tool_visible") and st:
            wall = json.load(open(os.path.join(run_dir(app, run_id), "logs", "1_domain_claude.json"), encoding="utf-8"))["_wall_seconds"]
            check(wall < 15, f"{fault}: el proceso se corta al ver el `init` invalido, sin esperar la respuesta", f"{wall} s")
        finish(app, run_id)

    # Limite de turnos (D39): la corrida NO falla; se pide la respuesta final como hace CrewAI.
    with open(os.path.join(GOLDEN_DIR, "jpetstore_con_fusion.json"), encoding="utf-8") as f:
        golden = json.load(f)
    full = [e["stage"] for e in golden["executions"]]
    sc = base_scenario()
    sc["faults"] = {"merging": "max_turns"}
    run_id = rp.TEST_RUN_PREFIX + "limite-de-turnos"
    clean(app, run_id)
    code, out, st = run(sc, run_id)
    mine = output_files(app, run_id)
    # Contabilidad (D39, D40): el sustituto cobra USD 0.01 y 100 tokens de salida por peticion; la merging hace 1
    # peticion + 1 forzada. El costo de la sesion reanudada es ACUMULADO (0.02, no 0.01 + 0.02).
    merging = next((e for e in (st or {}).get("etapas", []) if e["etapa"] == "3_merging"), {})
    check(merging.get("costo_usd") == 0.02 and (merging.get("tokens") or {}).get("output_tokens") == 200
          and merging.get("peticiones_api") == 2 and (merging.get("respuesta_forzada") or {}).get("peticiones_primera_llamada") == 1
          and merging.get("duracion_api_ms") == 14
          and "contabilidad_de_la_sesion_reanudada_no_cuadra" not in obs_types(st or {"observaciones": []}),
          "limite de turnos: costo y tiempo de API acumulados de la sesion, tokens sumados y peticiones contadas",
          json.dumps({k: merging.get(k) for k in ("costo_usd", "tokens", "peticiones_api", "duracion_api_ms", "respuesta_forzada")}))
    if st:
        check(st["totales"]["peticiones_api"] == sum(e.get("peticiones_api") or 0 for e in st["etapas"])
              and round(st["totales"]["costo_usd"], 6) == round(sum(e["costo_usd"] for e in st["etapas"]), 6),
              "totales de la corrida: peticiones y costo sumados por etapa")
    check(code == 0 and st and st["estado"] == "completa" and stage_names(st) == full
          and "limite_de_turnos_respuesta_forzada" in obs_types(st)
          and [e["etapa"] for e in st["etapas"] if e.get("limite_de_turnos")] == ["3_merging"]
          and sorted(mine) == sorted(golden["outputs"]) and all(norm(mine[k]) == norm(v) for k, v in golden["outputs"].items()),
          "limite de turnos en merging: se pide la respuesta final, la corrida termina y deja las salidas del original",
          (json.dumps(st.get("fallo"), ensure_ascii=False) if st else out[-800:]))
    finish(app, run_id)

    sc = base_scenario()
    sc["faults"] = {"common": "forced_tool_text"}
    clean(app, run_id)
    code, out, st = run(sc, run_id)
    mine = output_files(app, run_id)
    review_prompt = ""
    if st and len(st["etapas"]) == len(full):
        with open(os.path.join(run_dir(app, run_id), "logs", "5_review_prompt.txt"), encoding="utf-8", newline="") as f:
            review_prompt = f.read()
    check(code == 0 and st and st["estado"] == "completa" and "respuesta_forzada_pidio_herramientas" in obs_types(st)
          and norm(mine.get("common_result.json", "")) == norm(golden["outputs"]["common_result.json"])
          and "No Debe Escribirse" not in "".join(mine.values())
          and "This is the context you're working with:\nLet me save one more domain before answering.\n" in review_prompt,
          "respuesta forzada que pide una herramienta: no se ejecuta, se toma su texto (como CrewAI) y pasa de contexto a la Etapa 5",
          (json.dumps(st.get("fallo"), ensure_ascii=False) if st else out[-800:]))
    finish(app, run_id)


# --------------------------------------------------------------------------------------------------
# D. Cadena completa con el servidor MCP real
# --------------------------------------------------------------------------------------------------
def test_real_mcp():
    g_path = os.path.join(GOLDEN_DIR, "jpetstore_con_fusion.json")
    app, run_id = "jpetstore-6", rp.TEST_RUN_PREFIX + "jpetstore_con_fusion-mcp-real"
    paths = ["resources/jpetstore-6/src/main/java/org/mybatis/jpetstore/domain/Cart.java",
             "src/main/java/org/mybatis/jpetstore/domain/Item.java",       # relativa a resources/<app>/
             "DECISIONES.md",                                              # fuera de resources/<app>/
             "output/jpetstore-6/smoke-test/domains/merged_domains.json",  # salida de otra "corrida"
             "no/existe.java"]
    keep, ARGS.keep = ARGS.keep, True
    st = test_golden(g_path, real_mcp="merging,common,review", suffix="-mcp-real",
                     scenario_patch={"search_file_paths": {"merging": paths}})
    ARGS.keep = keep
    if not st:
        return
    logs = os.path.join(run_dir(app, run_id), "logs")
    audits = {e["etapa"]: json.load(open(os.path.join(logs, e["etapa"] + "_audit.json"), encoding="utf-8")) for e in st["etapas"]}
    for etapa in ("3_merging", "4_common", "5_review"):
        a = audits[etapa]
        stage = STAGE_OF[etapa[0]]
        check(a["herramientas_visibles_init"] == sorted(rp.MCP_PREFIX + t for t in rp.AGENT_TOOLS[stage])
              and a["servidores_mcp"] == {"microagent": "connected"},
              f"{etapa}: el servidor MCP real publica exactamente las herramientas del agente ({len(rp.AGENT_TOOLS[stage])})",
              str(a["herramientas_visibles_init"]))
        check(a["llamadas_registradas_por_el_servidor"] == len(a["llamadas"]) > 0,
              f"{etapa}: el registro del servidor coincide con el flujo ({len(a['llamadas'])} llamadas)")
    zones = [p["zona"] for p in audits["3_merging"]["rutas_search_file"]]
    check(zones == ["resources_app", "resources_app", "fuera_de_resources_app", "contaminante", "fuera_de_resources_app"],
          "auditoria de rutas de search_file: dentro de resources/<app>, fuera y contaminante", str(zones))
    types = obs_types(st)
    check("rutas_fuera_de_resources_app" in types and "CORRIDA_CONTAMINADA" in types,
          "una lectura de salidas de otra corrida marca la corrida como contaminada (no la descarta)", str(types))
    finish(app, run_id)


# --------------------------------------------------------------------------------------------------
# E. Piezas sueltas
# --------------------------------------------------------------------------------------------------
def test_units():
    log("\n== Piezas sueltas")
    with open(ORIGINAL_MAIN, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    original = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "clean_json_output")
    mine = ast.parse(textwrap.dedent(inspect.getsource(rp.clean_json_output))).body[0]
    check(ast.dump(original) == ast.dump(mine), "clean_json_output es copia literal de main.py (mismo arbol sintactico)")

    fa = rp.extract_final_answer
    cases = [
        ("Thought: x\nFinal Answer: {\"a\": 1}", ('{"a": 1}', True)),
        ("Final Answer: uno\nThought: y\nFinal Answer:  dos  ", ("dos", True)),                 # la ULTIMA aparicion
        ("Final Answer: ```json\n{}\n```", ("```json\n{}\n```", True)),                          # cercas pareadas: se dejan
        ("```\nThought: x\nFinal Answer: {\"a\": 1}\n```", ('{"a": 1}', True)),                  # cerca final desparejada
        ("  {\"a\": 1}\n", ('{"a": 1}', False)),                                                 # sin etiqueta (D31)
        ("", ("", False)),
    ]
    check(all(fa(t) == exp for t, exp in cases), "extract_final_answer sigue la regla de crewai/agents/parser.py (1.8.1)",
          str([(t, fa(t)) for t, exp in cases if fa(t) != exp]))

    names = [("Order/Payment", "Order-Payment", "Order-Payment"), ('Cart: "items"', 'Cart: "items"', "Cart_ _items_"),
             ("Catalog.", "Catalog.", "Catalog"), ("CON", "CON", "_CON"), ("Customer's Account", "Customer's Account", "Customer's Account")]
    check(all(rp.domain_file_name(n) == (o, u) for n, o, u in names), "domain_file_name: `/`->`-` como el original; el resto solo se sanea en la ruta",
          str([rp.domain_file_name(n) for n, _, _ in names]))

    cp = lambda p: rp.classify_path(p, "jpetstore-6", "claude-run1")["zona"]  # noqa: E731
    zone_cases = [("resources/jpetstore-6/pom.xml", "resources_app"), ("'resources/jpetstore-6/pom.xml'", "resources_app"),
                  ("pom.xml", "resources_app"), ("resources/partsunlimited/README.md", "fuera_de_resources_app"),
                  ("output/jpetstore-6/claude-run1/domains/all_domains.json", "salida_de_esta_corrida"),
                  ("output/jpetstore-6/claude-run2/result.json", "contaminante"), ("logs/prompts_check.txt", "contaminante"),
                  ("evaluation/references/jpetstore.json", "contaminante"),
                  (os.path.join(os.path.dirname(BASE), "MicroAgent", "decomposition", "jpetstore.json"), "contaminante"),
                  ("resources/jpetstore-6/../../DECISIONES.md", "fuera_de_resources_app"), (None, "no_es_texto")]
    check(all(cp(p) == z for p, z in zone_cases), "classify_path resuelve las rutas como search_file y las clasifica",
          str([(p, cp(p)) for p, z in zone_cases if cp(p) != z]))

    fp1, fp2 = rp.context_fingerprint("jpetstore-6"), rp.context_fingerprint("jpetstore-6")
    check(fp1["digest"] == fp2["digest"] and fp1["n_files"] == 3 + 24, "huella del contexto de JPetStore: estable, 3 + 24 archivos",
          str(fp1["n_files"]))
    check(rp.context_fingerprint("partsunlimited")["n_files"] == 3 + 53, "huella del contexto de PartsUnlimitedMRP: 3 + 53 archivos")

    # Configuracion de los agentes contra el crew.py ORIGINAL (no contra las constantes de run_pipeline.py).
    check(sorted(CREW) == sorted(rp.AGENT_TOOLS) and all(rp.AGENT_TOOLS[s] == CREW[s]["tools"] for s in CREW),
          "herramientas de cada agente = las de crew.py original, en el mismo orden",
          str({s: (rp.AGENT_TOOLS.get(s), CREW[s]["tools"]) for s in CREW if rp.AGENT_TOOLS.get(s) != CREW[s]["tools"]}))
    check({s: CREW[s]["max_iter"] for s in CREW} == rp.MAX_TURNS == {"domain": 30, "clustering": 30, "merging": 30, "common": 45, "review": 45},
          "limite de turnos de cada agente = max_iter de crew.py original (30/30/30/45/45)", str(rp.MAX_TURNS))
    check(rp.MODEL == EXPECTED_MODEL and rp.EFFORT == EXPECTED_EFFORT, "modelo y esfuerzo por defecto: claude-sonnet-4-6, high")

    # Contexto que Claude Code anade por su cuenta (D38): el de la prueba de humo real es el esperado, y
    # cualquier bloque o seccion de mas (un CLAUDE.md, una memoria) invalida la llamada.
    smoke = os.path.join(BASE, "logs", "fase4_prueba_humo", "prueba-humo-etapa1-b", "logs")
    if os.path.exists(os.path.join(smoke, "1_domain_transcript.jsonl")):
        read = lambda n: open(os.path.join(smoke, n), encoding="utf-8", newline="").read()  # noqa: E731
        system, user = read("1_domain_system_prompt.txt"), read("1_domain_prompt.txt")
        d = rp.analyze_transcript(os.path.join(smoke, "1_domain_transcript.jsonl"), system, user)
        check(d["legible"] and d["system_entregado_identico"] and d["usuario_entregado_identico"]
              and d["contexto_anadido_inesperado"] == []
              and d["herramientas_por_forma_de_peticion"] == [sorted("mcp__microagent__" + t for t in CREW["domain"]["tools"])],
              "prueba de humo real: prompts identicos, solo el contexto habitual de Claude Code y las 5 herramientas del Domain Agent",
              json.dumps(d, ensure_ascii=False)[:600])
    else:
        system = "You are Expert Software Architect - domain agent. ..."
        log("  [--] no esta la transcripcion de la prueba de humo; unexpected_context solo se prueba con bloques sinteticos")
    blocks = [start + "...\n</system-reminder>\n" for _, start in rp.CLAUDE_CODE_USER_BLOCKS]
    sysb = [rp.CLAUDE_CODE_SYSTEM_BLOCK, system]
    with_claude_md = blocks[:3] + [blocks[3].replace("</system-reminder>", "# claudeMd\nContents of CLAUDE.md\n</system-reminder>")] + blocks[4:]
    context_cases = [
        ("lo habitual", sysb, blocks, False),
        ("un bloque de mas", sysb, blocks + ["<system-reminder>\nextra\n</system-reminder>"], True),
        ("un CLAUDE.md en el bloque de la cuenta", sysb, with_claude_md, True),
        ("un bloque de system de mas", sysb + ["otro bloque"], blocks, True),
        ("falta el bloque de system de Claude Code", [system], blocks, True),
        ("un bloque distinto del esperado", sysb, blocks[:4] + ["<system-reminder>\nOtra cosa\n</system-reminder>"], True),
        ("un bloque menos", sysb, blocks[:4], True),
    ]
    wrong = [name for name, sb, ub, bad in context_cases if bool(rp.unexpected_context(sb, ub, system)) != bad]
    check(not wrong, f"unexpected_context: acepta lo habitual y rechaza {len(context_cases) - 1} variantes con contexto ajeno", str(wrong))

    # Entrega de la peticion forzada (D39, D40), sobre la transcripcion REAL archivada de la comprobacion.
    forced_tr = os.path.join(BASE, "logs", "fase4_prueba_humo", "comprobacion-respuesta-forzada", "logs",
                             "1_domain_forzada_transcript.jsonl")
    if os.path.exists(forced_tr):
        ok_case = rp.analyze_forced(forced_tr, FORCE_TEXT)
        bad_case = rp.analyze_forced(forced_tr, FORCE_TEXT + " ")
        check(ok_case["encontrado"] and ok_case["identico"] and ok_case["bloques_antepuestos_inesperados"] == []
              and ok_case["parametros_de_las_peticiones"] == [{"model": EXPECTED_MODEL, "max_tokens": 32000,
                                                               "thinking": {"type": "disabled"}, "temperature": 1,
                                                               "output_config": {"effort": EXPECTED_EFFORT}}]
              and bad_case["encontrado"] and not bad_case["identico"],
              "analyze_forced (transcripcion real): reconoce el texto de CrewAI identico y detecta uno distinto",
              json.dumps(ok_case, ensure_ascii=False)[:400])
        # La contabilidad real de esa llamada: el resultado de la sesion reanudada trae el costo ACUMULADO.
        rec = json.load(open(os.path.join(os.path.dirname(forced_tr), "1_domain_claude.json"), encoding="utf-8"))
        first, last = rec["_primera_llamada"], rec
        check(last["total_cost_usd"] > first["total_cost_usd"]
              and (last["modelUsage"][EXPECTED_MODEL]["outputTokens"]
                   == first["usage"]["output_tokens"] + last["usage"]["output_tokens"]),
              "en la llamada real reanudada, costo y modelUsage son acumulados y usage es de esa llamada")
    else:
        log("  [--] no esta la transcripcion real de la respuesta forzada; analyze_forced no se prueba con datos reales")

    # Transcripcion real de la Fase 2 (check5): system prompt vacio y prompt conocido.
    sys.path.insert(0, os.path.join(BASE, "scripts"))
    import check_mcp_with_claude as c5
    session = None
    stream = os.path.join(BASE, "logs", "cli_checks", "check5_mcp_filtered_stream.jsonl")
    if os.path.exists(stream):
        for line in open(stream, encoding="utf-8"):
            ev = json.loads(line)
            if ev.get("type") == "result":
                session = ev.get("session_id")
    transcript = rp.find_transcript(session) if session else None
    if transcript:
        d = rp.analyze_transcript(transcript, "", c5.PROMPT)
        check(d["legible"] and d["usuario_entregado_identico"] and d["herramientas_en_la_peticion"] == ["mcp__microagent__get_class_summary"]
              and all((p["thinking"] or {}).get("type") == "disabled" for p in d["parametros_de_las_peticiones"]),
              "analyze_transcript lee una transcripcion real (check5): prompt identico, 1 herramienta, thinking desactivado",
              json.dumps(d, ensure_ascii=False)[:600])
        d2 = rp.analyze_transcript(transcript, "otro system", c5.PROMPT + " ")
        check(not d2["system_entregado_identico"] and not d2["usuario_entregado_identico"] and d2["usuario_solo_recortado"],
              "analyze_transcript detecta un system prompt distinto y un mensaje recortado")
        log(f"       parametros de la API registrados en esa transcripcion: {d['parametros_de_las_peticiones']}")
        log(f"       bloques de system que envio Claude Code: {[b['inicio'] for b in d['system_bloques']]}")
    else:
        log("  [--] no se encontro la transcripcion de check5; no se prueba analyze_transcript con datos reales")


def test_guards():
    log("\n== Protecciones del orquestador")
    sc = base_scenario("jpetstore_sin_fusion")
    app = "jpetstore-6"
    run_id = rp.TEST_RUN_PREFIX + "protecciones"
    clean(app, run_id)
    code, out, st = run(sc, run_id, extra=["--only-stage1"])
    check(code == 0 and st["estado"] == "parcial_etapa1" and stage_names(st) == ["domain"]
          and sorted(output_files(app, run_id)) == ["domains/domain_clusters.json"],
          "--only-stage1: solo la Etapa 1, estado parcial_etapa1", str(st and st["estado"]))
    code, out, _ = run(sc, run_id)
    check(code != 0 and "nunca se sobrescribe" in out, "una corrida existente no se sobrescribe")
    finish(app, run_id)
    code, out, _ = run(sc, "claude-prueba-prefijo")
    check(code != 0 and "prefijo" in out and not os.path.exists(run_dir(app, "claude-prueba-prefijo")),
          "una corrida simulada no puede usar un identificador de corrida real")
    code, out, _ = run(sc, run_id, fake=False)
    check(code != 0 and "prefijo" in out and not os.path.exists(run_dir(app, run_id)),
          "una corrida real no puede usar el prefijo de las simuladas (y no se llama a `claude`)")
    code, out, _ = run(sc, run_id, extra=["--number", "5", "--num", "FIVE"])
    check(code != 0 and "no corresponden" in out, "--number/--num distintos de los de la aplicacion: se rechaza")
    code, out, _ = run(sc, "smoke-test")
    check(code != 0, "el identificador reservado `smoke-test` se rechaza")

    # Ctrl+C a mitad de corrida (D38): no debe quedar "en_curso". Se prueba en este mismo proceso.
    run_id_int = rp.TEST_RUN_PREFIX + "interrumpida"
    clean(app, run_id_int)
    saved = (sys.argv, rp.Pipeline.run, os.environ.get("MICROAGENT_CLAUDE_CMD"))

    def interrupted(self):
        raise KeyboardInterrupt

    try:
        os.environ["MICROAGENT_CLAUDE_CMD"] = json.dumps([sys.executable])
        sys.argv = ["run_pipeline.py", "--app", app, "--run-id", run_id_int]
        rp.Pipeline.run = interrupted
        with contextlib.redirect_stdout(io.StringIO()):
            code = rp.main()
    finally:
        sys.argv, rp.Pipeline.run = saved[0], saved[1]
        if saved[2] is None:
            os.environ.pop("MICROAGENT_CLAUDE_CMD", None)
        else:
            os.environ["MICROAGENT_CLAUDE_CMD"] = saved[2]
    with open(os.path.join(run_dir(app, run_id_int), "logs", "run_status.json"), encoding="utf-8") as f:
        st = json.load(f)
    check(code == 1 and st["estado"] == "fallida" and st["fallo"]["motivo"] == "interrumpida" and st["fin"],
          "una corrida interrumpida con Ctrl+C queda registrada como fallida (no 'en_curso')", str(st.get("fallo")))
    finish(app, run_id_int)

    # Linea base del contexto (D32). Si ya hay una real, se aparta mientras dura la prueba y se restaura intacta.
    baseline = os.path.join(BASE, "logs", "context_fingerprint", f"{app}.json")
    aside = baseline + ".apartada-por-la-prueba"
    real_exists = os.path.exists(baseline)
    real_hash = rp.sha256_file(baseline) if real_exists else None
    if real_exists:
        code, out, st = run(sc, run_id, extra=["--only-stage1"])
        check(code == 0 and rp.sha256_file(baseline) == real_hash,
              "con el contexto igual al de la linea base real, la corrida arranca y la linea base no se toca", out[-300:])
        finish(app, run_id)
        os.replace(baseline, aside)
    try:
        os.makedirs(os.path.dirname(baseline), exist_ok=True)
        fp = rp.context_fingerprint(app)
        fp["files"]["context/jpetstore-6/class_summaries.json"] = "0" * 64
        with open(baseline, "w", encoding="utf-8") as f:
            json.dump({"run_id": "linea-base-de-prueba", "fecha": "prueba", **fp, "digest": "0" * 64}, f)
        code, out, _ = run(sc, run_id)
        check(code != 0 and "el contexto de jpetstore-6 cambio" in out and "class_summaries.json" in out
              and not os.path.exists(run_dir(app, run_id)),
              "si el contexto no coincide con el de la primera corrida, se aborta antes de llamar a nadie (D32)", out[-400:])
    finally:
        os.remove(baseline)
        if real_exists:
            os.replace(aside, baseline)
        elif not os.listdir(os.path.dirname(baseline)):
            os.rmdir(os.path.dirname(baseline))
    check(os.path.exists(baseline) == real_exists and (not real_exists or rp.sha256_file(baseline) == real_hash),
          "la linea base del contexto queda como estaba antes de la prueba")


def main():
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="no borrar las corridas de prueba")
    ap.add_argument("--skip-real-mcp", action="store_true", help="omitir la prueba con el servidor MCP real (lenta)")
    ap.add_argument("--solo-capturas", metavar="TEXTO",
                    help="prueba parcial y rapida (para mutaciones): solo las piezas sueltas y las capturas cuyo "
                         "nombre contiene TEXTO (varios separados por comas); no reescribe el informe")
    ARGS = ap.parse_args()
    baseline_before = sorted(glob.glob(os.path.join(BASE, "logs", "context_fingerprint", "*.json")))
    files = sorted(glob.glob(os.path.join(GOLDEN_DIR, "*.json")))
    log(f"Prueba sin cupo de run_pipeline.py (Fase 4). Capturas del original: {len(files)}")
    partial = [t for t in (ARGS.solo_capturas or "").split(",") if t]
    if partial:
        files = [f for f in files if any(t in os.path.basename(f) for t in partial)]
        log(f"PRUEBA PARCIAL (--solo-capturas): {[os.path.basename(f) for f in files]}")
    test_units()
    if not partial:
        test_guards()
    for path in files:
        st = test_golden(path)
        if st:
            finish(st["app"], st["run_id"])
    if not partial:
        test_branches()
        test_faults()
        if not ARGS.skip_real_mcp:
            test_real_mcp()
    log("\n== Limpieza")
    check(sorted(glob.glob(os.path.join(BASE, "logs", "context_fingerprint", "*.json"))) == baseline_before,
          "las corridas simuladas no crearon ni cambiaron la linea base del contexto")
    check(not os.listdir(os.path.join(BASE, "_sandbox")), "_sandbox vacio al terminar")
    leftovers = [p for p in glob.glob(os.path.join(BASE, "output", "*", rp.TEST_RUN_PREFIX + "*"))]
    check(ARGS.keep or not leftovers, "no quedan corridas de prueba en output/", str(leftovers))
    log(f"\nRESULTADO: {'OK' if not problems else 'FALLA'} ({len(problems)} problemas)")
    for p in problems:
        log(f"  - {p}")
    if not partial:
        with open(OUT, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
