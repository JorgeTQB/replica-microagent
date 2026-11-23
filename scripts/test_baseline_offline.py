"""Prueba de run_baseline.py SIN gastar cupo: `claude` simulado (fake_claude_baseline.py), run_id `_prueba-...`.

    python -B -X utf8 scripts/test_baseline_offline.py

Comprueba:
  - cada escenario (estado, motivo del fallo, observaciones, archivos, estadisticas y totales);
  - la auditoria de la transcripcion (system, reminders, prompt, effort, thinking, herramientas, peticiones), con
    una transcripcion sintetica en un CLAUDE_CONFIG_DIR temporal;
  - la linea de comandos, el cwd y el entorno que recibe `claude`, contra valores escritos a mano (D35, D38);
  - que el prompt es el registrado (sha256 fijo por app) y el que se guarda en baseline_prompt.txt;
  - que no se sobrescribe un run_id, que las corridas reales exigen el prefijo baseline- y el modelo unico, y que
    --solo-prompt no escribe dentro del proyecto.
Las corridas se escriben en una carpeta temporal (BASELINE_OUTPUT_ROOT), nunca en output/; al final se borra.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import run_baseline as rb  # noqa: E402

PY = [sys.executable, "-B", "-X", "utf8"]
FAKE = json.dumps(PY + [os.path.join(BASE, "scripts", "fake_claude_baseline.py")])
PREFIX = "_prueba-baseline-"
TMP = tempfile.mkdtemp(prefix="baseline_offline_")
OUT = os.path.join(TMP, "output")
CONFIG = os.path.join(TMP, "claude_config")
RECORD = os.path.join(TMP, "fake_record.json")

# Prompt registrado en DECISIONES.md D45 (si cambia una letra del prompt o del contexto, esta prueba falla).
EXPECTED_PROMPT_SHA = {
    "jpetstore-6": "4aa7c961a464e9e406167b15b0d1b82d66c5f9da2e19b9539d771fe5eca79312",
    "partsunlimited": "31230f37abefba161a9119c8f611901224a68ef1569c0f1448e5e1195352f1ab",
}
# Lo que debe recibir `claude` (escrito a mano, no copiado del codigo: D35, D38).
EXPECTED_ARGV = ["-p", "--model", "claude-sonnet-4-6", "--effort", "high", "--system-prompt", "", "--tools", "",
                 "--strict-mcp-config", "--disable-slash-commands", "--setting-sources", "", "--max-turns", "1",
                 "--output-format", "stream-json", "--verbose"]
EXPECTED_ENV = {"DISABLE_AUTOUPDATER": "1", "API_TIMEOUT_MS": "900000", "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
                "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "PYTHONDONTWRITEBYTECODE": "1", "MAX_THINKING_TOKENS": "0",
                "MCP_TIMEOUT": "300000", "MCP_TOOL_TIMEOUT": "600000", "CLAUDE_CONFIG_DIR": CONFIG}
# Variables heredadas que NO deben llegar a `claude` (se ponen a proposito en el entorno de la prueba).
CANARIES = {"CLAUDE_EFFORT": "low", "CLAUDE_CODE_ENTRYPOINT": "x", "ANTHROPIC_MODEL": "otro", "MCP_FOO": "1",
            "DISABLE_MICROCOMPACT": "1", "MAX_THINKING_TOKENS": "9999"}

# modo -> (estado esperado, motivo del fallo esperado o None, observaciones que deben aparecer)
CASES = {
    "ok": ("completa", None, []),
    "fenced": ("completa", None, ["json_entre_cercas_de_codigo"]),
    "text_around": ("completa", None, ["texto_alrededor_del_json"]),
    "missing": ("completa", None, ["clases_sin_asignar", "clases_fuera_del_universo"]),
    "wrong_n": ("completa", None, ["particiones_distintas_de_n"]),
    "duplicate_keys": ("completa", None, ["servicios_con_nombre_repetido", "clases_sin_asignar"]),
    "no_transcript": ("completa", None, ["transcripcion_no_encontrada"]),
    "invalid": ("fallida", "json_invalido", []),
    # JSON cortado: clean_json_output (literal de main.py) puede rescatar un arreglo interno -> forma_invalida
    "max_tokens": ("fallida", ("json_invalido", "forma_invalida"), ["stop_reason"]),
    "list": ("fallida", "forma_invalida", []),
    "nonlist": ("fallida", "forma_invalida", []),
    "api_error": ("fallida", "error_api_429", []),
    "no_result": ("fallida", "sin_resultado_de_claude", []),
    "exit_nonzero": ("fallida", "error_de_claude", []),
    "timeout": ("fallida", "tiempo_agotado", []),
    "tools_init": ("fallida", "herramientas_o_mcp_en_init", []),
    "mcp_init": ("fallida", "herramientas_o_mcp_en_init", []),
    "thinking": ("fallida", "auditoria", []),
    "tool": ("fallida", "auditoria", []),
    "wrong_model": ("fallida", "auditoria", []),
    "sys_extra": ("fallida", "auditoria", []),
    "effort_medium": ("fallida", "auditoria", []),
    "thinking_param": ("fallida", "auditoria", []),
    "extra_reminder": ("fallida", "auditoria", []),
    "prompt_trimmed": ("fallida", "auditoria", []),
    "two_requests": ("fallida", "auditoria", []),
    "tools_in_request": ("fallida", "auditoria", []),
}


def run(app, run_id, mode="ok", fake=True, extra=()):
    env = dict(os.environ, FAKE_BASELINE_MODE=mode, FAKE_BASELINE_RECORD=RECORD, CLAUDE_CONFIG_DIR=CONFIG, **CANARIES)
    for k in ("MICROAGENT_CLAUDE_CMD", "BASELINE_OUTPUT_ROOT"):
        env.pop(k, None)
    if fake:
        env["MICROAGENT_CLAUDE_CMD"] = FAKE
        env["BASELINE_OUTPUT_ROOT"] = OUT
    else:
        env["CLAUDE_CONFIG_DIR"] = os.environ.get("CLAUDE_CONFIG_DIR", "")  # sin tocar la del usuario
        if not env["CLAUDE_CONFIG_DIR"]:
            env.pop("CLAUDE_CONFIG_DIR")
    args = ["--app", app] + (["--run-id", run_id] if run_id else []) + list(extra)
    return subprocess.run(PY + [os.path.join(BASE, "run_baseline.py")] + args,
                          capture_output=True, text=True, encoding="utf-8", env=env, cwd=BASE)


def check_record(errors, app):
    rec = json.load(open(RECORD, encoding="utf-8"))
    problems = []
    if rec["argv"] != EXPECTED_ARGV:
        problems.append(f"argv {rec['argv']}")
    if os.path.normcase(os.path.realpath(rec["cwd"])) != os.path.normcase(os.path.realpath(rb.SANDBOX)):
        problems.append(f"cwd {rec['cwd']}")
    if rec["fijas"] != EXPECTED_ENV:
        problems.append(f"entorno {rec['fijas']}")
    leaked = [k for k in CANARIES if k in rec["nombres"] and k not in EXPECTED_ENV]
    if leaked:
        problems.append(f"variables heredadas que llegaron a claude: {leaked}")
    print(f"{'OK ' if not problems else 'ERR'} {app:15} linea de comandos, cwd y entorno de claude")
    if problems:
        errors.append((app, "configuracion", problems))


def main():
    errors = []
    output_before = sorted(glob.glob(os.path.join(BASE, "output", "*", "*")))
    fp_before = sorted(glob.glob(os.path.join(rb.PROMPT_FINGERPRINT_DIR, "*")))
    try:
        for app in rb.APPS:
            prompt, universe, _ = rb.build_prompt(app)
            sha = rb.sha256_bytes(prompt.encode("utf-8"))
            ok = sha == EXPECTED_PROMPT_SHA[app]
            print(f"{'OK ' if ok else 'ERR'} {app:15} sha256 del prompt {sha[:16]}... ({len(prompt)} caracteres)")
            if not ok:
                errors.append((app, "sha256 del prompt", sha))
            for mode, (estado, motivo, obs) in CASES.items():
                rid = f"{PREFIX}{mode}"
                t0 = time.time()
                proc = run(app, rid, mode, extra=["--timeout", "5"] if mode == "timeout" else [])
                took = time.time() - t0
                rd = os.path.join(OUT, app, rid)
                st = json.load(open(os.path.join(rd, "logs", "run_status.json"), encoding="utf-8"))
                tipos = [o["tipo"] for o in st["observaciones"]]
                got = (st["estado"], (st["fallo"] or {}).get("motivo"))
                notes = []
                if got[0] != estado or got[1] not in (motivo if isinstance(motivo, tuple) else (motivo,)):
                    notes.append(f"estado/motivo {got}")
                if not all(t in tipos for t in obs):
                    notes.append(f"faltan observaciones {set(obs) - set(tipos)}")
                if (proc.returncode == 0) != (estado == "completa"):
                    notes.append(f"exit {proc.returncode}")
                logs = os.path.join(rd, "logs")
                for f in ("baseline_prompt.txt", "baseline_raw.txt", "baseline_claude.json", "baseline_stream.jsonl",
                          "baseline_audit.json", "run_manifest.json"):
                    if not os.path.exists(os.path.join(logs, f)):
                        notes.append(f"falta {f}")
                if open(os.path.join(logs, "baseline_prompt.txt"), "rb").read() != prompt.encode("utf-8"):
                    notes.append("baseline_prompt.txt distinto del prompt")
                if os.path.exists(os.path.join(rd, "result.json")) != (estado == "completa"):
                    notes.append("result.json presente/ausente al reves")
                if mode in ("timeout", "tools_init", "mcp_init") and took > 25:
                    notes.append(f"no corto a tiempo ({took:.0f} s)")
                if mode == "max_tokens" and st["etapas"][0].get("stop_reason") != "max_tokens":
                    notes.append("stop_reason no registrado")
                if mode == "ok":
                    check_record(errors, app)
                    res, tot = st["resultado"], st["totales"]
                    if not (res["clases_sin_asignar"] == [] and res["particiones"] == rb.APPS[app]["n"]
                            and res["clases_del_universo"] == len(universe) and len(res["clases_en_varios_servicios"]) == 1):
                        notes.append(f"estadisticas {res}")
                    if not (tot["costo_usd"] == 0.01 and tot["peticiones_api"] == 1 and tot["turnos"] == 1
                            and tot["tokens"]["cache_creation_input_tokens"] == 2000 and tot["llamadas"] == 1):
                        notes.append(f"totales {tot}")
                    audit = json.load(open(os.path.join(logs, "baseline_audit.json"), encoding="utf-8"))
                    if not (audit["entrega"].get("legible") and audit["entrega"]["usuario_entregado_identico"]):
                        notes.append("la transcripcion sintetica no se audito")
                    for k in ("app", "run_id", "modelo", "number", "num", "simulado", "solo_etapa1", "estado", "inicio",
                              "fin", "fallo", "fusion", "etapas", "observaciones", "totales", "resultado"):
                        if k not in st:
                            notes.append(f"run_status sin la clave {k}")
                if mode == "missing":
                    res = st["resultado"]
                    if not (len(res["clases_sin_asignar"]) == 3 and res["clases_fuera_del_universo"] == ["com.example.Invented"]
                            and res["clases_distintas_asignadas"] == len(universe) - 3 + 1):
                        notes.append(f"estadisticas {res}")
                if mode == "duplicate_keys":
                    data = json.load(open(os.path.join(rd, "result.json"), encoding="utf-8"))
                    if data != {"A": ["x.W"], "B": ["x.Z"]}:
                        notes.append(f"result.json {data}")
                print(f"{'OK ' if not notes else 'ERR'} {app:15} {mode:16} -> {got} obs={tipos}")
                if notes:
                    errors.append((app, mode, notes, proc.stdout[-400:], proc.stderr[-400:]))
            # no sobrescribir
            proc = run(app, f"{PREFIX}ok")
            ok = proc.returncode != 0 and "nunca se sobrescribe" in (proc.stderr + proc.stdout)
            print(f"{'OK ' if ok else 'ERR'} {app:15} no sobrescribe un run_id existente")
            if not ok:
                errors.append((app, "sobrescritura", proc.stderr[-300:]))
            # Rechazos que deben cortar ANTES de lanzar cualquier proceso (con fake=False no hay claude simulado,
            # pero check() sale antes de llamar a nada).
            for rid, fake, extra, needle in (
                    (f"{PREFIX}x", False, [], "obligatorio y exclusivo"),
                    ("baseline-run1", True, [], "obligatorio y exclusivo"),
                    ("claude-run9", False, [], "debe llamarse baseline-"),
                    ("baseline-run9", False, ["--model", "claude-opus-4-1"], "un solo modelo")):
                proc = run(app, rid, fake=fake, extra=extra)
                ok = proc.returncode != 0 and needle in (proc.stderr + proc.stdout)
                ok = ok and not os.path.exists(os.path.join(OUT, app, rid))
                ok = ok and not os.path.exists(os.path.join(BASE, "output", app, rid))
                print(f"{'OK ' if ok else 'ERR'} {app:15} rechaza {rid!r} {extra} (simulado={fake})")
                if not ok:
                    errors.append((app, rid, proc.stderr[-300:]))
            # --solo-prompt: fuera del proyecto si; dentro (p. ej. context/<app>/) no
            proc = run(app, None, fake=False, extra=["--solo-prompt", os.path.join(TMP, "solo")])
            ok = proc.returncode == 0 and json.loads(proc.stdout)["sha256"] == sha
            inside = os.path.join(BASE, "context", app)
            before = sorted(os.listdir(inside))
            proc2 = run(app, None, fake=False, extra=["--solo-prompt", inside])
            ok = ok and proc2.returncode != 0 and sorted(os.listdir(inside)) == before
            print(f"{'OK ' if ok else 'ERR'} {app:15} --solo-prompt solo escribe fuera del proyecto")
            if not ok:
                errors.append((app, "--solo-prompt", proc.stderr[-300:], proc2.stderr[-300:]))
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
        if glob.glob(os.path.join(BASE, "output", "*", PREFIX + "*")):
            errors.append(("quedaron carpetas de prueba en output/", None))
        if sorted(glob.glob(os.path.join(BASE, "output", "*", "*"))) != output_before:
            errors.append(("la prueba cambio las carpetas de output/", None))
        else:
            print("OK  output/ no cambio (mismas carpetas antes y despues)")
        if sorted(glob.glob(os.path.join(rb.PROMPT_FINGERPRINT_DIR, "*"))) != fp_before:
            errors.append(("una corrida simulada escribio la huella del prompt", None))
    print("\nRESULTADO:", "OK" if not errors else f"{len(errors)} ERRORES")
    for e in errors:
        print(" ", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
