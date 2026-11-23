"""Linea base "LLM base" zero-shot (INSTRUCCIONES §8, Fase 5).

El paper (§4.1.2) le da al modelo el codigo original, los scripts de base de datos y el numero objetivo de
microservicios, en zero-shot. El artefacto NO publica ese prompt: aqui se reconstruye (DECISIONES.md, D45-D47).

Una corrida = UNA llamada `claude -p` sin herramientas, con el mismo modelo, esfuerzo, entorno limpio y opciones de
aislamiento que el orquestador (`run_pipeline.py`, D35, D38). El texto que devuelve el modelo se limpia con
`clean_json_output` (copia literal de main.py 21-46, la misma que se aplica a MicroAgent) y se guarda tal cual,
sin corregir clases que falten o sobren (D46).

Uso:
    python -B -X utf8 run_baseline.py --app jpetstore-6 --run-id baseline-run1
    python -B -X utf8 run_baseline.py --app partsunlimited --solo-prompt <carpeta>   (arma el prompt, no llama a claude)

Corrida simulada (sin cupo): MICROAGENT_CLAUDE_CMD='["python","-B","scripts/fake_claude_baseline.py"]' y un
run_id con el prefijo `_prueba-` (scripts/test_baseline_offline.py).

Archivos en output/<app>/<run_id>/:
    result.json                         descomposicion (lo que devolvio el modelo, limpiado con clean_json_output)
    logs/baseline_prompt.txt            bytes exactos enviados a `claude` por stdin
    logs/baseline_stream.jsonl          flujo completo de `claude --output-format stream-json`
    logs/baseline_claude.json           evento final de `claude` (modelo, tokens, costo) + linea de comandos y entorno
    logs/baseline_raw.txt               respuesta cruda del modelo
    logs/baseline_transcript.jsonl      transcripcion de Claude Code (lo que se envio a la API)
    logs/baseline_audit.json            comprobaciones de aislamiento y de entrega del prompt
    logs/baseline_stderr.txt
    logs/run_manifest.json, logs/run_status.json, logs/baseline.log
"""
from __future__ import annotations

import argparse
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
sys.path.insert(0, BASE)
import run_pipeline as rp  # noqa: E402  (mismas utilidades, entorno y auditoria que el orquestador)
from run_pipeline import (EFFORT, EXTRA_ENV, MCP_ENV, MODEL, PIPELINE_ENV,  # noqa: E402
                          SANDBOX, TEST_RUN_PREFIX, analyze_transcript, child_env, clean_json_output,
                          context_fingerprint, dump_result, find_transcript, kill_tree, now, sha256_bytes,
                          sha256_file, write_json, write_text)

ETAPA = "baseline"
# n de cada aplicacion (§4.2, §4.3) y esquema de BD crudo (D11: el mismo archivo del que salio el resumen de BD de
# PartsUnlimitedMRP; JPetStore: el DDL del clon, D45).
APPS = {
    "jpetstore-6": {"n": 3, "schema": "resources/jpetstore-6/src/main/resources/database/jpetstore-hsqldb-schema.sql"},
    "partsunlimited": {"n": 5, "schema": "resources/partsunlimited/src/Backend/OrderService/scripts/schema.psql"},
}
SYSTEM_PROMPT = ""   # sustituye el system prompt por defecto de Claude Code; solo queda su bloque fijo (D45)
MAX_TURNS = 1        # una sola peticion, sin herramientas
RUN_ID_PREFIX = "baseline-"
NUM = {3: "THREE", 5: "FIVE"}
# Huella del prompt por app: la escribe la primera corrida real y las siguientes la exigen (revision D47, hallazgo 6).
PROMPT_FINGERPRINT_DIR = os.path.join(BASE, "logs", "baseline_prompt_fingerprint")


# --------------------------------------------------------------------------------------------------
# Prompt reconstruido (D45). Zero-shot, en ingles. Cambiar una sola letra cambia la linea base: se registra.
# --------------------------------------------------------------------------------------------------
INTRO = ("Below is the source code of the classes of a monolithic Java application, together with its database "
         "schema. Your task is to decompose this application into exactly {n} microservices.\n")
TASK = ("## Task\n"
        "Decompose the application above into exactly {n} microservices. Assign classes to microservices by their "
        "fully qualified class names. A class that is shared by several microservices may appear in more than one "
        "microservice.\n\n"
        "Return ONLY a JSON object, with no other text, in the following format:\n"
        '{{"<ServiceName>": ["<fully.qualified.ClassName>", ...]}}\n')   # el formato literal de §8


def read_source(rel: str) -> str:
    """Contenido del archivo sin recortar ni quitar licencias (D45). Se lee en modo texto, como hacen las
    herramientas del original: los CRLF del disco llegan al prompt como LF."""
    with open(os.path.join(BASE, rel), encoding="utf-8") as f:
        return f.read()


def fence(content: str) -> str:
    return content if content.endswith("\n") else content + "\n"


def build_prompt(app: str) -> tuple[str, list[str], dict]:
    """Devuelve (prompt, universo de clases en orden, archivos usados con su sha256)."""
    cfg = APPS[app]
    with open(os.path.join(BASE, "context", app, "class_summaries.json"), encoding="utf-8") as f:
        summaries = json.load(f)  # el orden de las claves es el del contexto que ve MicroAgent (D45, punto 1)
    schema_rel = cfg["schema"]
    parts = [INTRO.format(n=cfg["n"]),
             "## Database schema\n",
             f"File: {schema_rel}\n```sql\n{fence(read_source(schema_rel))}```\n",
             f"## Source code\nThe application consists of the following {len(summaries)} classes.\n"]
    # sha256 de los bytes en disco (CRLF) y del texto que entra al prompt (LF)
    used = {schema_rel: {"disco": sha256_file(os.path.join(BASE, schema_rel)),
                         "texto": sha256_bytes(read_source(schema_rel).encode("utf-8"))}}
    for fqcn, info in summaries.items():
        rel = info["file_path"].replace("\\", "/")  # formato del artefacto: resources/<app>/... (D45, punto 2)
        text = read_source(rel)
        parts.append(f"### {fqcn}\nFile: {rel}\n```java\n{fence(text)}```\n")
        used[rel] = {"disco": sha256_file(os.path.join(BASE, rel)), "texto": sha256_bytes(text.encode("utf-8"))}
    parts.append(TASK.format(n=cfg["n"]))
    return "\n".join(parts), list(summaries), used


# --------------------------------------------------------------------------------------------------
# Validacion de la respuesta (D46): solo se exige que sea un objeto JSON {str: [str, ...]}; nada se corrige.
# --------------------------------------------------------------------------------------------------
def parse_response(raw: str):
    """Devuelve (objeto, texto_limpio, problema, servicios_con_nombre_repetido). problema = None si es un objeto
    {str: [str]}. Como en main.py, `json.loads` se queda con la ULTIMA aparicion de una clave repetida; eso no se
    corrige, pero se informa con las listas que se perdieron (revision D47, hallazgo 1)."""
    cleaned = clean_json_output(raw)
    pairs = []

    def keep_pairs(items):
        pairs.append(items)
        return dict(items)
    try:
        obj = json.loads(cleaned, object_pairs_hook=keep_pairs)  # mismo resultado que json.loads
    except json.JSONDecodeError as e:
        return None, cleaned, f"json_invalido: {e}", {}
    duplicated = {}
    if isinstance(obj, dict) and pairs:
        top = pairs[-1]  # el objeto exterior es el ultimo en cerrarse
        names = [k for k, _ in top]
        duplicated = {k: [v for kk, v in top if kk == k] for k in names if names.count(k) > 1}
    if not isinstance(obj, dict):
        return obj, cleaned, f"forma_invalida: el JSON es {type(obj).__name__}, no un objeto", {}
    bad = [k for k, v in obj.items() if not isinstance(v, list) or not all(isinstance(c, str) for c in v)]
    if bad:
        return obj, cleaned, f"forma_invalida: servicios cuyo valor no es una lista de textos: {bad}", duplicated
    return obj, cleaned, None, duplicated


def result_stats(result: dict, universe: list, n: int) -> dict:
    """Lo mismo que `_result_stats` del orquestador, mas lo que interesa en la linea base (D46): clases omitidas
    (para separarlas de las mal asignadas en el reporte), desconocidas, repetidas y numero de servicios."""
    assigned, repeated, count = set(), {}, {}
    for service, classes in result.items():
        dup = sorted({c for c in classes if classes.count(c) > 1})
        if dup:
            repeated[service] = dup
        for c in set(classes):
            count[c] = count.get(c, 0) + 1
        assigned.update(classes)
    uni = set(universe)
    # Las 4 primeras claves de clases son las de `_result_stats` del orquestador, con la misma definicion.
    return {"archivo": None, "particiones": len(result), "particiones_pedidas": n,
            "particiones_igual_a_n": len(result) == n,
            "clases_por_particion": {k: len(v) for k, v in result.items()},
            "clases_distintas_asignadas": len(assigned), "clases_del_universo": len(uni),
            "clases_sin_asignar": sorted(uni - assigned),
            "clases_fuera_del_universo": sorted(assigned - uni),
            "clases_del_universo_asignadas": len(assigned & uni),
            "clases_en_varios_servicios": {c: k for c, k in sorted(count.items()) if k > 1},
            "repetidas_dentro_de_un_servicio": repeated,
            # json_similarity.py ignora la clave "uncounted" del objetivo: si el modelo la usara, se nota aqui.
            "servicio_llamado_uncounted": "uncounted" in result}


# --------------------------------------------------------------------------------------------------
class Baseline:
    def __init__(self, args):
        self.app, self.run_id, self.model = args.app, args.run_id, args.model
        self.n = APPS[self.app]["n"]
        self.timeout = args.timeout
        fake = os.environ.get("MICROAGENT_CLAUDE_CMD")
        self.simulated = bool(fake)
        # Las corridas simuladas pueden (y en test_baseline_offline.py deben) escribir fuera de output/.
        root = os.environ.get("BASELINE_OUTPUT_ROOT")
        if root and not self.simulated:
            sys.exit("BASELINE_OUTPUT_ROOT solo se admite en corridas simuladas")
        self.run_dir = os.path.join(root or os.path.join(BASE, "output"), self.app, self.run_id)
        self.logs_dir = os.path.join(self.run_dir, "logs")
        self.claude_cmd = json.loads(fake) if fake else [shutil.which("claude") or ""]
        self.claude_version = ""
        self.observations = []
        # Mismas claves que run_status.json del orquestador (+ "configuracion"); fusion no aplica a la linea base.
        self.status = {"app": self.app, "run_id": self.run_id, "configuracion": "baseline", "modelo": self.model,
                       "number": str(self.n), "num": NUM[self.n], "simulado": self.simulated, "solo_etapa1": False,
                       "estado": "en_curso", "inicio": now(), "fin": None, "fallo": None, "fusion": "no_aplica",
                       "etapas": [], "observaciones": self.observations, "totales": {}, "resultado": None}

    def path(self, suffix: str) -> str:
        return os.path.join(self.logs_dir, f"{ETAPA}_{suffix}")

    def log(self, msg: str = "") -> None:
        print(msg, flush=True)
        with open(os.path.join(self.logs_dir, "baseline.log"), "a", encoding="utf-8", newline="\n") as f:
            f.write(f"[{now()}] {msg}\n")

    def observe(self, tipo: str, detalle) -> None:
        self.observations.append({"etapa": ETAPA, "tipo": tipo, "detalle": detalle})
        self.log(f"  [OBSERVACION] {tipo}: {detalle}")

    def save_status(self) -> None:
        # Mismas claves que run_status.json del orquestador ("turnos" = num_turns de Claude Code, D44).
        totals = {"llamadas": len(self.status["etapas"]), "turnos": 0, "peticiones_api": 0, "duracion_ms": 0,
                  "duracion_api_ms": 0, "costo_usd": 0.0, "llamadas_a_herramientas": 0,
                  "tokens": {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
                             "cache_read_input_tokens": 0}}
        for s in self.status["etapas"]:
            for k in ("turnos", "peticiones_api", "duracion_ms", "duracion_api_ms", "llamadas_a_herramientas"):
                totals[k] += s.get(k) or 0
            totals["costo_usd"] += s.get("costo_usd") or 0.0
            for k in totals["tokens"]:
                totals["tokens"][k] += (s.get("tokens") or {}).get(k) or 0
        self.status["totales"] = totals
        write_json(os.path.join(self.logs_dir, "run_status.json"), self.status, indent=2, ensure_ascii=False)

    # ---------------------------------------------------------------- preparacion
    def check(self) -> None:
        """Comprobaciones previas: si alguna falla, se sale sin crear nada."""
        if not self.simulated and self.model != MODEL:
            sys.exit(f"--model {self.model!r}: la replica usa un solo modelo, {MODEL} (D3, §10.1)")
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", self.run_id):
            sys.exit(f"--run-id no valido: {self.run_id!r}")
        if self.simulated != self.run_id.startswith(TEST_RUN_PREFIX):
            sys.exit(f"el prefijo {TEST_RUN_PREFIX!r} es obligatorio y exclusivo de las corridas con `claude` "
                     f"simulado (MICROAGENT_CLAUDE_CMD)")
        if not self.simulated and not self.run_id.startswith(RUN_ID_PREFIX):
            sys.exit(f"una corrida real de la linea base debe llamarse {RUN_ID_PREFIX}...: {self.run_id!r}")
        if not self.claude_cmd[0]:
            sys.exit("no se encontro el ejecutable 'claude' en el PATH")
        if not sys.flags.utf8_mode:
            sys.exit("ejecutar en modo UTF-8: python -B -X utf8 run_baseline.py ...")
        if os.path.exists(self.run_dir):
            sys.exit(f"ya existe {self.run_dir}: una corrida nunca se sobrescribe; usa otro --run-id (§10.4)")
        os.makedirs(SANDBOX, exist_ok=True)
        if os.listdir(SANDBOX):
            sys.exit(f"_sandbox no esta vacio: {os.listdir(SANDBOX)}")

        # El contexto debe ser el mismo que el de las corridas de MicroAgent (D32): class_summaries.json fija el
        # universo y el orden de las clases, y los .java son el codigo que se envia.
        fingerprint = context_fingerprint(self.app)
        baseline_path = os.path.join(BASE, "logs", "context_fingerprint", f"{self.app}.json")
        if os.path.exists(baseline_path):
            with open(baseline_path, encoding="utf-8") as f:
                ref = json.load(f)
            if ref["digest"] != fingerprint["digest"]:
                changed = sorted(k for k in set(ref["files"]) | set(fingerprint["files"])
                                 if ref["files"].get(k) != fingerprint["files"].get(k))
                sys.exit(f"el contexto de {self.app} cambio respecto a {ref['run_id']} ({ref['fecha']}): {changed}")
            note = f"igual al de las corridas de MicroAgent (linea base {ref['run_id']}, {ref['fecha']})"
        elif self.simulated:
            note = "sin huella de referencia (corrida simulada)"
        else:
            sys.exit(f"no existe {baseline_path}: la linea base se corre con el contexto de MicroAgent (D32)")
        self.context_note, self.fingerprint = note, fingerprint

        # El prompt debe ser el mismo en las 3 corridas (incluye el esquema, que la huella D32 no cubre).
        self.prompt, self.universe, self.used = build_prompt(self.app)
        self.prompt_sha = sha256_bytes(self.prompt.encode("utf-8"))
        fp_path = os.path.join(PROMPT_FINGERPRINT_DIR, f"{self.app}.json")
        self.prompt_note = "primera corrida real: se guarda la huella del prompt"
        if os.path.exists(fp_path):
            with open(fp_path, encoding="utf-8") as f:
                ref = json.load(f)
            if ref["sha256"] != self.prompt_sha:
                sys.exit(f"el prompt de {self.app} cambio respecto a {ref['run_id']} ({ref['fecha']}): "
                         f"{ref['sha256'][:16]}... -> {self.prompt_sha[:16]}... Se aborta.")
            self.prompt_note = f"igual al de {ref['run_id']} ({ref['fecha']})"
        elif self.simulated:
            self.prompt_note = "sin huella del prompt (corrida simulada)"
        self.prompt_fp_path = fp_path

    def prepare(self) -> None:
        """Crea la carpeta de la corrida; desde aqui, todo fallo queda en run_status.json."""
        os.makedirs(self.logs_dir)
        self.save_status()
        if not self.simulated and not os.path.exists(self.prompt_fp_path):
            os.makedirs(PROMPT_FINGERPRINT_DIR, exist_ok=True)
            write_json(self.prompt_fp_path, {"run_id": self.run_id, "fecha": now(), "app": self.app,
                                             "sha256": self.prompt_sha, "caracteres": len(self.prompt)}, indent=1)
        note, fingerprint, used = self.context_note, self.fingerprint, self.used
        version = ""
        if not self.simulated:
            proc = subprocess.run([self.claude_cmd[0], "--version"], capture_output=True, timeout=120, env=child_env()[0])
            version = proc.stdout.decode("utf-8", errors="replace").strip()
            self.claude_version = version.split()[0] if version else ""
        env, removed = child_env()
        write_json(os.path.join(self.logs_dir, "run_manifest.json"), {
            "app": self.app, "run_id": self.run_id, "configuracion": "baseline", "number": str(self.n),
            "modelo_pedido": self.model, "simulado": self.simulated, "fecha": now(), "argv": sys.argv,
            "claude_code_version": version, "claude_cmd": self.claude_cmd, "python": sys.version,
            "plataforma": platform.platform(), "entorno_de_claude": {**PIPELINE_ENV, **EXTRA_ENV, **MCP_ENV},
            "esfuerzo": EFFORT, "system_prompt": SYSTEM_PROMPT, "max_turns": MAX_TURNS,
            "variables_quitadas_del_entorno": removed, "variables_que_recibe_claude": sorted(env),
            "prompt": {"caracteres": len(self.prompt), "bytes_utf8": len(self.prompt.encode("utf-8")),
                       "sha256": self.prompt_sha, "comparacion": self.prompt_note, "clases": len(self.universe),
                       "archivos_incluidos_sha256": used},
            "contexto": {"comparacion": note, **fingerprint},
            "archivos_sha256": {os.path.relpath(p, os.path.dirname(BASE)).replace("\\", "/"): sha256_file(p)
                                for p in (os.path.join(BASE, "run_baseline.py"), os.path.join(BASE, "run_pipeline.py"))},
        }, indent=1, ensure_ascii=False)
        self.save_status()
        self.log(f"Linea base {self.run_id} de {self.app} (n={self.n}, modelo={self.model}"
                 f"{', SIMULADA' if self.simulated else ''})")
        self.log(f"Prompt: {len(self.prompt)} caracteres, {len(self.universe)} clases. Contexto: {note}")

    # ---------------------------------------------------------------- la llamada
    def run(self) -> None:
        prompt_path = self.path("prompt.txt")
        with open(prompt_path, "wb") as f:  # bytes exactos que recibe `claude` por stdin
            f.write(self.prompt.encode("utf-8"))
        args = ["-p", "--model", self.model, "--effort", EFFORT, "--system-prompt", SYSTEM_PROMPT,
                "--tools", "", "--strict-mcp-config",              # sin herramientas integradas ni servidores MCP
                "--disable-slash-commands", "--setting-sources", "",
                "--max-turns", str(MAX_TURNS), "--output-format", "stream-json", "--verbose"]
        env, removed = child_env()
        if os.listdir(SANDBOX):
            raise rp.StageFailure(ETAPA, "sandbox_no_vacio", str(os.listdir(SANDBOX)))
        self.log(f"\n>>> {ETAPA}: una llamada sin herramientas (max-turns {MAX_TURNS})")
        started = time.time()
        events, timed_out, early_abort = [], False, None
        with open(prompt_path, "rb") as fin, open(self.path("stderr.txt"), "wb") as ferr, \
                open(self.path("stream.jsonl"), "wb") as fstream:
            proc = subprocess.Popen(self.claude_cmd + args, stdin=fin, stdout=subprocess.PIPE, stderr=ferr,
                                    cwd=SANDBOX, env=env)

            def on_timeout():
                nonlocal timed_out
                timed_out = True
                kill_tree(proc)

            timer = threading.Timer(self.timeout, on_timeout)
            timer.start()
            try:
                for line in proc.stdout:
                    fstream.write(line)
                    fstream.flush()
                    try:
                        ev = json.loads(line.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(ev, dict):
                        continue
                    events.append(ev)
                    if ev.get("type") == "system" and ev.get("subtype") == "init" and early_abort is None:
                        # Corte temprano, como _check_init del orquestador (D22): no pagar una llamada invalida.
                        bad = [f"{k}={ev.get(k)}" for k in ("tools", "mcp_servers") if ev.get(k)]
                        early_abort = bad or False
                        if bad:
                            kill_tree(proc)
                            break
                proc.wait()
            finally:
                timer.cancel()
                kill_tree(proc)
        elapsed = round(time.time() - started, 1)
        init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), None) or {}
        result_ev = next((e for e in reversed(events) if e.get("type") == "result"), None)
        raw = (result_ev or {}).get("result")
        raw = raw if isinstance(raw, str) else ""

        record = dict(result_ev or {})
        record.update({"_exit_code": proc.returncode, "_cmd": args, "_claude_cmd": self.claude_cmd,
                       "_env": {**PIPELINE_ENV, **EXTRA_ENV, **MCP_ENV}, "_env_quitado": removed,
                       "_env_nombres": sorted(env), "_cwd": SANDBOX, "_init": init, "_wall_seconds": elapsed})
        write_json(self.path("claude.json"), record, indent=1, ensure_ascii=False)
        write_text(self.path("raw.txt"), raw)

        audit = self.audit(events, init, result_ev)
        write_json(self.path("audit.json"), audit, indent=1, ensure_ascii=False)
        r = result_ev or {}
        entry = {"etapa": ETAPA, "agente": "LLM base (zero-shot)", "session_id": r.get("session_id") or init.get("session_id"),
                 "subtype": r.get("subtype"), "is_error": r.get("is_error"), "turnos": r.get("num_turns"),
                 "max_turns": MAX_TURNS, "peticiones_api": audit["peticiones_api"],
                 "duracion_ms": r.get("duration_ms"), "duracion_api_ms": r.get("duration_api_ms"),
                 "costo_usd": r.get("total_cost_usd"),
                 "tokens": {k: (r.get("usage") or {}).get(k) or 0 for k in
                            ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")},
                 "llamadas_a_herramientas": len(audit["llamadas_a_herramientas"]),
                 "herramientas_usadas": {}, "etiqueta_final_answer": None, "caracteres_respuesta": len(raw),
                 "limite_de_turnos": False, "stop_reason": audit["stop_reason"], "caracteres_prompt": len(self.prompt),
                 "problemas": audit["problemas"]}
        self.status["etapas"].append(entry)
        self.save_status()

        # --- validez de la llamada: si falla, la corrida es fallida (§10.4); no se corrige ni se reintenta aqui
        if timed_out:
            raise rp.StageFailure(ETAPA, "tiempo_agotado", f"mas de {self.timeout} s")
        if early_abort:
            raise rp.StageFailure(ETAPA, "herramientas_o_mcp_en_init", "; ".join(early_abort))
        if result_ev is None:
            tail = open(self.path("stderr.txt"), encoding="utf-8", errors="replace").read()[-800:]
            raise rp.StageFailure(ETAPA, "sin_resultado_de_claude", f"exit={proc.returncode}; stderr: {tail!r}")
        if r.get("subtype") != "success" or r.get("is_error") or proc.returncode != 0:
            motivo = str(r.get("subtype") or "error")
            if motivo == "success":  # p. ej. cupo agotado: subtype "success" con is_error y HTTP 429 (D10)
                motivo = f"error_api_{r.get('api_error_status')}" if r.get("api_error_status") else "error_de_claude"
            raise rp.StageFailure(ETAPA, motivo, f"is_error={r.get('is_error')}; exit={proc.returncode}; "
                                                 f"api_error_status={r.get('api_error_status')}; texto: {raw[:300]!r}")
        if audit["problemas"]:
            raise rp.StageFailure(ETAPA, "auditoria", "; ".join(audit["problemas"]))
        for tipo, detalle in audit["observaciones"]:
            self.observe(tipo, detalle)

        # --- respuesta -> result.json (D46)
        obj, cleaned, problem, duplicated = parse_response(raw)
        if audit["stop_reason"] not in (None, "end_turn"):
            self.observe("stop_reason", f"{audit['stop_reason']} (la respuesta pudo quedar cortada)")
        if duplicated:
            self.observe("servicios_con_nombre_repetido", {"nota": "json.loads se queda con la ultima aparicion, "
                                                                   "como en main.py; result.json no se corrige",
                                                           "listas": duplicated})
        if cleaned.strip() != raw.strip():
            fenced_only = raw.strip().startswith("```") and raw.strip().endswith("```")
            self.observe("json_entre_cercas_de_codigo" if fenced_only else "texto_alrededor_del_json", f"clean_json_output recorto {len(raw.strip()) - len(cleaned.strip())} "
                                                     f"caracteres de {len(raw.strip())}")
        if problem:
            raise rp.StageFailure(ETAPA, problem.split(":")[0], problem)
        result_path = os.path.join(self.run_dir, "result.json")
        dump_result(result_path, obj)
        stats = result_stats(obj, self.universe, self.n)
        stats["archivo"] = os.path.relpath(result_path, BASE).replace("\\", "/") if not self.simulated else result_path
        self.status["resultado"] = stats
        if not stats["particiones_igual_a_n"]:
            self.observe("particiones_distintas_de_n", f"{stats['particiones']} servicios; se pidieron {self.n}")
        if stats["clases_sin_asignar"]:
            self.observe("clases_sin_asignar", stats["clases_sin_asignar"])
        if stats["clases_fuera_del_universo"]:
            self.observe("clases_fuera_del_universo", stats["clases_fuera_del_universo"])
        if stats["repetidas_dentro_de_un_servicio"]:
            self.observe("repetidas_dentro_de_un_servicio", stats["repetidas_dentro_de_un_servicio"])
        if stats["servicio_llamado_uncounted"]:
            self.observe("servicio_llamado_uncounted", "json_similarity.py ignora esa clave del objetivo")
        self.log(f"<<< {ETAPA}: {elapsed} s, respuesta de {len(raw)} caracteres, {stats['particiones']} servicios, "
                 f"{stats['clases_distintas_asignadas']} de {stats['clases_del_universo']} clases asignadas")

    def audit(self, events, init, result_ev) -> dict:
        """Aislamiento y entrega del prompt, con los mismos criterios que el orquestador (D22, D35, D38).
        `problemas` invalida la llamada; `observaciones` se registra."""
        problems, notes, models, thinking, tools = [], [], set(), 0, []
        ids, stop_reason = set(), None
        for ev in events:
            msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
            if ev.get("type") == "assistant":
                ids.add(msg.get("id") or id(ev))
                if msg.get("model"):
                    models.add(msg["model"])
                stop_reason = msg.get("stop_reason") or stop_reason
            for b in msg.get("content") or []:
                if isinstance(b, dict) and b.get("type") in ("thinking", "redacted_thinking"):
                    thinking += 1
                elif isinstance(b, dict) and b.get("type") == "tool_use":
                    tools.append(b.get("name"))
        if init.get("tools"):
            problems.append(f"herramientas visibles en init: {init.get('tools')} (se esperaba ninguna)")
        if init.get("mcp_servers"):
            problems.append(f"servidores MCP cargados: {init.get('mcp_servers')} (se esperaba ninguno)")
        if tools:
            problems.append(f"el modelo pidio herramientas: {tools}")
        if thinking:
            problems.append(f"{thinking} bloques de razonamiento extendido (debe estar desactivado, D4)")
        if len(models) > 1 or (models and models != {self.model}):
            problems.append(f"modelo(s) que respondieron: {sorted(models)}; pedido: {self.model} (§10.1)")
        if len(ids) > MAX_TURNS:
            problems.append(f"{len(ids)} peticiones a la API (se esperaba {MAX_TURNS})")
        if init.get("slash_commands") or init.get("skills"):
            notes.append(("comandos_o_skills_cargados", {"slash_commands": init.get("slash_commands"),
                                                         "skills": init.get("skills")}))
        if self.claude_version and init.get("claude_code_version") and init["claude_code_version"] != self.claude_version:
            problems.append(f"version de Claude Code {init['claude_code_version']} distinta de la de --version "
                            f"({self.claude_version})")

        session_id = (result_ev or init or {}).get("session_id")
        transcript = find_transcript(session_id) if session_id else None
        delivery = {"transcripcion": None}
        if transcript:
            copy = self.path("transcript.jsonl")
            shutil.copyfile(transcript, copy)
            delivery = analyze_transcript(copy, SYSTEM_PROMPT, self.prompt)
            delivery["transcripcion"] = os.path.basename(copy)
            if delivery.get("legible"):
                # Con --system-prompt "" la API recibe SOLO el bloque fijo de Claude Code (comprobado con la
                # transcripcion del resumen de BD de la Fase 1); unexpected_context lo exige.
                if not delivery["usuario_entregado_identico"]:
                    problems.append("el prompt enviado a la API no es identico al de la linea base "
                                    f"(solo recortado: {delivery['usuario_solo_recortado']})")
                # contexto_anadido_inesperado = unexpected_context(system, bloques antepuestos, ""): exige
                # system == [CLAUDE_CODE_SYSTEM_BLOCK] y los 5 <system-reminder> de siempre, nada mas.
                problems.extend(delivery["contexto_anadido_inesperado"])
                if any(t for t in delivery["herramientas_por_forma_de_peticion"]):
                    problems.append(f"herramientas enviadas a la API: {delivery['herramientas_por_forma_de_peticion']}")
                for p in delivery["parametros_de_las_peticiones"]:
                    if (p.get("thinking") or {}).get("type") not in (None, "disabled"):
                        problems.append(f"peticion con razonamiento extendido: {p.get('thinking')}")
                    if (p.get("output_config") or {}).get("effort") != EFFORT or p.get("model") != self.model:
                        problems.append(f"peticion con otra configuracion: model={p.get('model')}, "
                                        f"output_config={p.get('output_config')}")
                if delivery["peticiones_api"] != MAX_TURNS:
                    problems.append(f"{delivery['peticiones_api']} peticiones en la transcripcion (se esperaba {MAX_TURNS})")
            else:
                notes.append(("transcripcion_ilegible", delivery["archivo"]))
        else:
            notes.append(("transcripcion_no_encontrada", f"session_id={session_id}"))
        # Sin transcripcion legible no hay prueba de lo que recibio la API (system, effort, prompt): en una
        # corrida real eso invalida la llamada (revision D47, hallazgo 2).
        if not self.simulated and not delivery.get("legible"):
            problems.append("no hay transcripcion legible de la sesion: no se puede comprobar lo enviado a la API")
        if os.listdir(SANDBOX):
            notes.append(("sandbox_con_archivos_tras_la_llamada", os.listdir(SANDBOX)))
        return {"etapa": ETAPA, "modelo_pedido": self.model, "modelos_que_respondieron": sorted(models),
                "herramientas_visibles_init": init.get("tools"), "servidores_mcp": init.get("mcp_servers"),
                "apiKeySource": init.get("apiKeySource"), "claude_code_version": init.get("claude_code_version"),
                "peticiones_api": len(ids), "llamadas_a_herramientas": tools, "bloques_thinking": thinking,
                "stop_reason": stop_reason,
                "entrega": delivery, "problemas": problems, "observaciones": notes}


def main() -> int:
    ap = argparse.ArgumentParser(description="Linea base LLM zero-shot (INSTRUCCIONES §8).")
    ap.add_argument("--app", required=True, choices=sorted(APPS))
    ap.add_argument("--run-id", help="identificador de la corrida, p. ej. baseline-run1")
    ap.add_argument("--model", default=MODEL, help=f"modelo unico de la replica (por defecto {MODEL}, D3)")
    ap.add_argument("--timeout", type=int, default=1800, help="segundos maximos de la llamada")
    ap.add_argument("--solo-prompt", metavar="CARPETA",
                    help="solo arma el prompt, lo guarda en CARPETA/baseline_prompt_<app>.txt y no llama a claude")
    args = ap.parse_args()

    if args.solo_prompt:
        prompt, universe, used = build_prompt(args.app)
        out = os.path.normcase(os.path.realpath(args.solo_prompt))
        project = os.path.normcase(os.path.realpath(os.path.dirname(BASE)))  # Replica de Paper/ (incluye MicroAgent/)
        if out == project or out.startswith(project + os.sep):
            sys.exit(f"--solo-prompt debe escribir fuera de {project} (p. ej. en una carpeta temporal)")
        os.makedirs(out, exist_ok=True)
        dest = os.path.join(out, f"baseline_prompt_{args.app}.txt")
        with open(dest, "wb") as f:
            f.write(prompt.encode("utf-8"))
        print(json.dumps({"app": args.app, "archivo": dest, "caracteres": len(prompt),
                          "bytes_utf8": len(prompt.encode("utf-8")), "clases": len(universe),
                          "archivos": len(used), "sha256": sha256_bytes(prompt.encode("utf-8"))}, indent=1))
        return 0
    if not args.run_id:
        ap.error("--run-id es obligatorio salvo con --solo-prompt")

    b = Baseline(args)
    b.check()      # sale sin crear nada si algo no cuadra
    failure = None
    try:
        b.prepare()
        b.run()
    except rp.StageFailure as e:
        failure = {"etapa": e.etapa, "motivo": e.motivo, "detalle": e.detalle}
    except Exception as e:
        failure = {"etapa": "run_baseline", "motivo": f"excepcion {type(e).__name__}", "detalle": traceback.format_exc()}
    except KeyboardInterrupt:
        failure = {"etapa": "run_baseline", "motivo": "interrumpida", "detalle": "corrida interrumpida a mano (Ctrl+C)"}
    if not os.path.isdir(b.logs_dir):  # fallo al crear la carpeta: no hay donde registrar
        print(f"no se pudo crear {b.logs_dir}: {failure}", file=sys.stderr)
        return 1
    b.status["estado"] = "fallida" if failure else "completa"
    b.status["fallo"] = failure
    b.status["fin"] = now()
    b.save_status()
    tot = b.status["totales"]
    b.log("\n--- Linea base completa ---" if not failure else
          "\n--- CORRIDA FALLIDA (registrar y reintentar con otro run_id, §10.4) ---")
    b.log(f"Estado: {b.status['estado']} | turnos: {tot['turnos']} | peticiones: {tot['peticiones_api']} | "
          f"duracion: {round((tot['duracion_ms'] or 0) / 1000)} s | costo nominal: USD {tot['costo_usd']:.4f} | "
          f"tokens: {tot['tokens']}")
    if failure:
        b.log(f"Fallo en {failure['etapa']}: {failure['motivo']}\n{failure['detalle']}")
    return 1 if failure else 0


if __name__ == "__main__":
    sys.exit(main())
