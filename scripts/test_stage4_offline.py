"""Prueba de run_stage4.py SIN gastar cupo (D41). No llama a ningun modelo.

  A. Reconstruccion de la entrada: para cada corrida completa real indicada (--origenes), el prompt de la
     Etapa 4 que arma run_stage4.py es identico byte a byte al que recibio esa corrida.
  B. Repeticion simulada (scripts/fake_claude.py en lugar de `claude`, servidor MCP REAL en la Etapa 4) con la
     entrada de claude-run1 y con las mismas escrituras de write_result_to_json que hizo su agente:
     prompt y system identicos, domains/ identico, misma linea de comandos y entorno de `claude`, y el mismo
     common_result.json que la corrida de origen.
  C. Herramientas: las llamadas deterministas que hizo el agente de la Etapa 4 de claude-run1 se repiten con la
     carpeta de la repeticion y devuelven exactamente el texto registrado en la transcripcion de origen.
  D. Protecciones: origen inexistente, origen con el prompt alterado, origen que ya es una repeticion,
     run_id ya usado. En ninguno se crea la carpeta nueva ni se lanza `claude`.
  E. Nada se toca: las corridas de origen y los archivos del orquestador quedan con los mismos SHA-256.

Uso: python -X utf8 scripts/test_stage4_offline.py [--origenes claude-run1,claude-run2,claude-run3] [--keep]
Salida: logs/stage4_offline_test.txt. Las carpetas de prueba usan el prefijo `_prueba-` y se borran al final.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import run_pipeline as rp  # noqa: E402
import run_stage4 as s4  # noqa: E402

APP = "jpetstore-6"
OUT = os.path.join(BASE, "logs", "stage4_offline_test.txt")
FAKE = [sys.executable, "-X", "utf8", os.path.join(BASE, "scripts", "fake_claude.py")]
lines, problems = [], []


def log(msg=""):
    lines.append(msg)
    print(msg, flush=True)


def check(ok, label, detail=""):
    if not ok:
        problems.append(label)
    log(f"  [{'OK' if ok else 'FALLA'}] {label}" + (f" -- {detail}" if detail and not ok else ""))
    return ok


def run_dir(run_id):
    return os.path.join(BASE, "output", APP, run_id)


def clean(run_id):
    assert run_id.startswith(rp.TEST_RUN_PREFIX)
    shutil.rmtree(run_dir(run_id), ignore_errors=True)


def tree_hashes(root):
    out = {}
    for dirpath, _, files in os.walk(root):
        for fn in files:
            p = os.path.join(dirpath, fn)
            out[os.path.relpath(p, root).replace("\\", "/")] = rp.sha256_file(p)
    return out


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def run_stage4(desde, run_id, scenario=None, fake=True):
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ)
        env.pop("MICROAGENT_CLAUDE_CMD", None)
        if fake:
            sc_path = os.path.join(tmp, "scenario.json")
            with open(sc_path, "w", encoding="utf-8") as f:
                json.dump(scenario or {}, f)
            env["MICROAGENT_CLAUDE_CMD"] = json.dumps(FAKE)
            env["FAKE_CLAUDE_SCENARIO"] = sc_path
            env["FAKE_CLAUDE_REAL_MCP"] = "common"
        proc = subprocess.run([sys.executable, "-X", "utf8", os.path.join(BASE, "run_stage4.py"), "--app", APP,
                               "--desde", desde, "--run-id", run_id], env=env, capture_output=True, timeout=900)
    return proc.returncode, proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")


def recorded_calls(source):
    """(herramienta, argumentos, texto devuelto) de cada llamada de la Etapa 4, leidos de la transcripcion.
    La transcripcion de Claude Code guarda cada resultado dos veces; la segunda copia lleva al final el bloque
    <system-reminder> de tokens restantes que Claude Code anade (D35). Se toma la primera: es la respuesta
    tal cual de la herramienta."""
    uses, out, done = {}, [], set()
    for line in open(os.path.join(run_dir(source), "logs", "4_common_transcript.jsonl"), encoding="utf-8"):
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        content = (ev.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if b.get("type") == "tool_use" and b["id"] not in done:
                uses[b["id"]] = (b["name"].split("__")[-1], b.get("input") or {})
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in uses:
                done.add(b["tool_use_id"])
                text = b.get("content")
                if isinstance(text, list):
                    text = "".join(x.get("text", "") for x in text if isinstance(x, dict))
                name, args = uses.pop(b["tool_use_id"])
                out.append((name, args, text))
    return out


REPLAY = r"""
import contextlib, io, json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "tools"))
with contextlib.redirect_stdout(io.StringIO()):
    import custom_tools as ct
    import mcp_server as ms
tools = {}  # una instancia por herramienta durante todo el proceso, como el servidor MCP
classes = {c.model_fields["name"].default: c for c in ms.TOOL_CLASSES}
calls = json.load(open(sys.argv[2], encoding="utf-8"))
res = []
for name, args in calls:
    tool = tools.setdefault(name, classes[name]())
    with contextlib.redirect_stdout(io.StringIO()):
        r = tool._run(**args)
    res.append(r if isinstance(r, str) else str(r))
json.dump(res, open(sys.argv[3], "w", encoding="utf-8"))
"""


# Herramientas del original cuya respuesta recorre un `set` de cadenas: el orden depende de la semilla de hash
# de cada proceso de Python (PYTHONHASHSEED), en el original igual que aqui (custom_tools.py es copia literal).
SET_ORDER_TOOLS = {"get_more_potential_common_classes", "assign_common_class_list"}


def canonical(text):
    """El mismo JSON con todas sus listas ordenadas (para comparar sin depender del orden)."""
    def norm(x):
        if isinstance(x, dict):
            return {k: norm(v) for k, v in x.items()}
        if isinstance(x, list):
            return sorted((norm(v) for v in x), key=lambda v: json.dumps(v, sort_keys=True))
        for prefix in ("depends on ", "is depended on by "):   # "depends on A, B, C" (assign_common_class_list)
            if isinstance(x, str) and x.startswith(prefix):
                return prefix + ", ".join(sorted(x[len(prefix):].split(", ")))
        return x
    try:
        return json.dumps(norm(json.loads(text)), sort_keys=True)
    except ValueError:
        return text


def replay(run_id, calls, seed=None):
    with tempfile.TemporaryDirectory() as tmp:
        cp, rp_path, script = (os.path.join(tmp, n) for n in ("calls.json", "res.json", "replay.py"))
        json.dump([[n, a] for n, a, _ in calls], open(cp, "w", encoding="utf-8"))
        open(script, "w", encoding="utf-8").write(REPLAY)
        env = dict(os.environ, APP_NAME=APP, RUN_ID=run_id)
        env.pop("PYTHONHASHSEED", None)
        if seed is not None:
            env["PYTHONHASHSEED"] = seed
        proc = subprocess.run([sys.executable, "-X", "utf8", script, BASE, cp, rp_path], env=env,
                              capture_output=True, timeout=300, cwd=os.path.join(BASE, "_sandbox"))
        if proc.returncode:
            return None, proc.stderr.decode("utf-8", "replace")[-600:]
        return json.load(open(rp_path, encoding="utf-8")), ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--origenes", default="claude-run1,claude-run2,claude-run3")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    sources = [s for s in args.origenes.split(",") if s]
    created = []
    try:
        return body(args, sources, created)
    finally:
        # Siempre, aunque la prueba aborte: la copia `_prueba-origen-alterado` lleva transcripciones con datos de
        # la cuenta y no debe quedar en output/.
        if not args.keep:
            for r in created + [rp.TEST_RUN_PREFIX + n for n in ("a", "d1", "d2", "d3")]:
                clean(r)


def body(args, sources, created):
    before = {s: tree_hashes(run_dir(s)) for s in sources}
    with open(os.path.join(run_dir(sources[-1]), "logs", "run_manifest.json"), encoding="utf-8") as f:
        pipeline_files = json.load(f)["archivos_del_pipeline_sha256"]

    log("A. Reconstruccion de la entrada de la Etapa 4 (sin crear carpetas ni llamar a `claude`)")
    for src in sources:
        ns = argparse.Namespace(app=APP, run_id=rp.TEST_RUN_PREFIX + "a", model=rp.MODEL, number="3", num="THREE",
                                stage_timeout=60, desde=src)
        p = s4.Stage4Repeat(ns)
        try:
            p.load_source()
            ok, detail = True, ""
        except SystemExit as e:
            ok, detail = False, str(e)
        check(ok and p.origin.get("prompt_identico_al_origen") is True,
              f"{src}: prompt y system prompt reconstruidos identicos al de su Etapa 4", detail)
        check(not os.path.exists(run_dir(ns.run_id)), f"{src}: load_source no crea la carpeta de la repeticion")

    log("\nB. Repeticion simulada con la entrada de claude-run1")
    src, rid = sources[0], rp.TEST_RUN_PREFIX + "e4-" + sources[0]
    clean(rid)
    created.append(rid)
    with open(os.path.join(run_dir(src), "logs", "4_common_server.jsonl"), encoding="utf-8") as f:
        writes = [[e["args"]["domain_name"], e["args"]["class_list"]] for e in map(json.loads, f)
                  if e.get("event") == "call" and e.get("tool") == "write_result_to_json"]
    scenario = {"name": "etapa4", "app": APP, "number": "3", "num": "THREE", "final_label": False,
                "common_writes": writes, "common_final": read(os.path.join(run_dir(src), "logs", "4_common_raw.txt"))}
    code, out = run_stage4(src, rid, scenario)
    check(code == 0, "run_stage4.py termina sin error", out[-800:])
    logs, slogs = os.path.join(run_dir(rid), "logs"), os.path.join(run_dir(src), "logs")
    status = json.load(open(os.path.join(logs, "run_status.json"), encoding="utf-8")) if code == 0 else {}
    check(status.get("estado") == s4.ESTADO_OK and [e["etapa"] for e in status.get("etapas", [])] == ["4_common"],
          "una sola llamada (4_common) y estado parcial_etapa4", str(status.get("estado")))
    check(status.get("simulado") is True and status.get("solo_etapa4_desde") == src, "registra simulado y origen")
    for fn in ("4_common_prompt.txt", "4_common_system_prompt.txt"):
        check(os.path.exists(os.path.join(logs, fn)) and read(os.path.join(logs, fn)) == read(os.path.join(slogs, fn)),
              f"{fn} identico byte a byte al de {src}")
    check(tree_hashes(os.path.join(run_dir(rid), "domains")) == tree_hashes(os.path.join(run_dir(src), "domains")),
          "domains/ identico al de origen")
    mine = json.load(open(os.path.join(logs, "4_common_claude.json"), encoding="utf-8")) if code == 0 else {}
    theirs = json.load(open(os.path.join(slogs, "4_common_claude.json"), encoding="utf-8"))
    norm_cmd = lambda c, r: [x.replace(r, "<RUN>") for x in (c or [])]  # noqa: E731
    check(norm_cmd(mine.get("_cmd"), rid) == norm_cmd(theirs.get("_cmd"), src),
          "misma linea de comandos de `claude` que la Etapa 4 de origen (salvo la ruta de la corrida)",
          f"{mine.get('_cmd')} vs {theirs.get('_cmd')}")
    check(mine.get("_env") == theirs.get("_env"), "mismas variables y valores que fija el orquestador para `claude`")
    # Los NOMBRES del resto del entorno dependen de la sesion que lanza el proceso (child_env, D35), no del script;
    # la prueba anade ademas FAKE_CLAUDE_* y MICROAGENT_CLAUDE_CMD. Se informa la diferencia.
    test_only = lambda n: n.startswith("FAKE_CLAUDE_") or n == "MICROAGENT_CLAUDE_CMD"  # noqa: E731
    diff = sorted(n for n in set(mine.get("_env_nombres") or []) ^ set(theirs.get("_env_nombres") or []) if not test_only(n))
    check(not [n for n in diff if n.startswith(("CLAUDE", "ANTHROPIC"))],
          "ninguna variable CLAUDE*/ANTHROPIC* distinta de la Etapa 4 de origen", str(diff))
    log(f"  [INFO] variables de la sesion que lanza el proceso distintas de las de {src}: {diff or 'ninguna'}")
    cfg_m, cfg_t = mine.get("_mcp_config") or {}, theirs.get("_mcp_config") or {}
    env_m = (cfg_m.get("mcpServers") or {}).get("microagent", {}).get("env", {})
    env_t = (cfg_t.get("mcpServers") or {}).get("microagent", {}).get("env", {})
    check({k: v.replace(rid, "<RUN>") for k, v in env_m.items()} == {k: v.replace(src, "<RUN>") for k, v in env_t.items()},
          "misma configuracion del servidor MCP (herramientas y variables), salvo la ruta de la corrida")
    cr = os.path.join(run_dir(rid), "common_result.json")
    check(os.path.exists(cr) and read(cr) == read(os.path.join(run_dir(src), "common_result.json")),
          "con las mismas escrituras del agente, common_result.json identico al de origen")
    check(os.path.exists(os.path.join(logs, "origen_etapa4.json")), "deja origen_etapa4.json")
    check(not os.listdir(rp.SANDBOX), "_sandbox vacio tras la repeticion")

    log("\nC. Herramientas de la Etapa 4: mismas respuestas que en la corrida de origen")
    calls = [c for c in recorded_calls(src) if c[0] != "write_result_to_json"]
    got, err = replay(rid, calls)
    check(got is not None and len(got) == len(calls), f"repeticion de las {len(calls)} llamadas registradas", err)
    for (name, a, expected), result in zip(calls, got or []):
        label = f"{name}({', '.join(f'{k}=...' for k in a)})"
        if name in SET_ORDER_TOOLS:
            check(canonical(result) == canonical(expected),
                  f"{label}: mismo contenido que en {src} (el orden de sus listas depende de PYTHONHASHSEED)")
        else:
            check(result == expected, f"{label} devuelve el mismo texto que en {src}",
                  f"{len(result)} vs {len(expected)} caracteres")
    # Variabilidad de las herramientas del original (D41): con la semilla fija la salida se repite exacta; con la
    # semilla aleatoria de cada proceso (lo normal, tambien en el original) puede cambiar de orden.
    seeded = [c for c in calls if c[0] in SET_ORDER_TOOLS]
    if seeded:
        a1, _ = replay(rid, seeded, seed="0")
        a2, _ = replay(rid, seeded, seed="0")
        check(a1 is not None and a1 == a2, "con PYTHONHASHSEED=0 fijo, esas herramientas devuelven siempre el mismo texto")
        variants = {tuple(replay(rid, seeded, seed=str(s))[0] or ()) for s in range(1, 6)}
        log(f"  [INFO] con 5 semillas distintas se obtienen {len(variants)} ordenes distintos de esas respuestas")
    with open(os.path.join(run_dir(sources[1] if len(sources) > 1 else src), "logs", "4_common_server.jsonl"),
              encoding="utf-8") as f:
        assign2 = [e["args"] for e in map(json.loads, f) if e.get("tool") == "assign_common_class_list"]
    if len(sources) > 1 and assign2:
        exp2 = [t for n, a, t in recorded_calls(sources[1]) if n == "assign_common_class_list"]
        rid2_calls = [("assign_common_class_list", assign2[0], exp2[0])]
        got2, err2 = replay(sources[1], rid2_calls)
        check(got2 is not None and canonical(got2[0]) == canonical(exp2[0]),
              f"control: assign_common_class_list de {sources[1]} se reproduce con su propia carpeta", err2)

    log("\nD. Protecciones (no se crea la carpeta ni se lanza `claude`)")
    for label, desde, new, msg in [
            ("origen inexistente", rp.TEST_RUN_PREFIX + "no-existe", rp.TEST_RUN_PREFIX + "d1", "no existe la corrida de origen"),
            ("origen que ya es una repeticion", rid, rp.TEST_RUN_PREFIX + "d2", "ya es una repeticion"),
            ("run_id ya usado", src, rid, "una corrida nunca se sobrescribe")]:
        snapshot = tree_hashes(run_dir(new)) if os.path.isdir(run_dir(new)) else None
        code, out = run_stage4(desde, new, scenario)
        after = tree_hashes(run_dir(new)) if os.path.isdir(run_dir(new)) else None
        check(code != 0 and msg in out and after == snapshot, f"{label}: se rechaza ({msg!r})", out[-300:])
    altered = rp.TEST_RUN_PREFIX + "origen-alterado"
    clean(altered)
    created.append(altered)
    shutil.copytree(run_dir(src), run_dir(altered))
    with open(os.path.join(run_dir(altered), "logs", "4_common_prompt.txt"), "a", encoding="utf-8", newline="") as f:
        f.write(" ")
    code, out = run_stage4(altered, rp.TEST_RUN_PREFIX + "d3", scenario)
    check(code != 0 and "NO es identico" in out and not os.path.exists(run_dir(rp.TEST_RUN_PREFIX + "d3")),
          "origen con el prompt alterado: se rechaza antes de llamar a `claude`", out[-300:])
    other = rp.TEST_RUN_PREFIX + "origen-otra-config"
    clean(other)
    created.append(other)
    shutil.copytree(run_dir(src), run_dir(other))
    mpath = os.path.join(run_dir(other), "logs", "run_manifest.json")
    manifest = json.load(open(mpath, encoding="utf-8"))
    manifest["archivos_del_pipeline_sha256"] = {k: "0" * 64 for k in manifest["archivos_del_pipeline_sha256"]}
    json.dump(manifest, open(mpath, "w", encoding="utf-8"))
    code, out = run_stage4(other, rp.TEST_RUN_PREFIX + "d3", scenario)
    check(code != 0 and "misma configuracion" in out and not os.path.exists(run_dir(rp.TEST_RUN_PREFIX + "d3")),
          "origen hecho con otro orquestador o herramientas: se rechaza antes de llamar a `claude`", out[-300:])

    log("\nE. Nada se toca")
    for s in sources:
        check(tree_hashes(run_dir(s)) == before[s], f"{s}: todos sus archivos con el mismo SHA-256")
    check(rp.pipeline_files_fingerprint() == pipeline_files,
          "run_pipeline.py, prompts, herramientas y YAML del original con el mismo SHA-256 que en la ultima corrida")

    if not args.keep:
        for r in created + [rp.TEST_RUN_PREFIX + n for n in ("a", "d1", "d2", "d3")]:
            clean(r)
        leftovers = [d for d in os.listdir(os.path.join(BASE, "output", APP)) if d.startswith(rp.TEST_RUN_PREFIX)]
        check(not leftovers, "no quedan carpetas de prueba en output/", str(leftovers))
    check(not os.listdir(rp.SANDBOX), "_sandbox vacio al terminar")

    log(f"\n{'TODO OK' if not problems else f'{len(problems)} FALLAS: ' + '; '.join(problems)}")
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    if not sys.flags.utf8_mode:
        sys.exit("ejecutar con: python -X utf8 scripts/test_stage4_offline.py")
    sys.exit(main())
