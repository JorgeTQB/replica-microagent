"""Repeticion aislada de la Etapa 4 (Common Class Agent) a partir de una corrida completa (D41).

Para que sirve: medir cuanto varia la Etapa 4 cuando recibe EXACTAMENTE la misma entrada. Claude Code envia
`temperature: 1` y no permite cambiarla (D4, D35); el original usa 0. Repetir solo esta etapa aisla esa
variabilidad de la de las etapas 1 a 3.

Que hace, sin cambiar nada de lo que recibe el modelo:
  1. Lee de la corrida de origen (`--desde`) lo que el orquestador tenia al empezar la Etapa 4: la carpeta
     `domains/`, `domain_clusters` (merged_domains.json o, si no existe, all_domains.json, como main.py) y la
     respuesta final del Merging Agent como contexto si hubo fusion (D27).
  2. Arma el prompt con `build_prompts.common_class_prompts`, la misma funcion que usa run_pipeline.py, y
     exige que el mensaje de usuario y el system prompt sean IDENTICOS, byte a byte, a los que recibio la
     Etapa 4 de la corrida de origen. Si no lo son, se aborta antes de llamar a `claude`.
  3. Copia `domains/` del origen a la nueva corrida (las herramientas leen esa carpeta) y comprueba sus SHA-256.
  4. Ejecuta la Etapa 4 con `Pipeline.call_agent`, que es la misma llamada `claude -p` (modelo, esfuerzo,
     entorno limpio, herramientas MCP, limite de turnos y auditoria) que en una corrida completa, y el mismo
     bloque de main.py 340-395 que run_pipeline.py.

La corrida de origen solo se lee; nunca se modifica. Lo unico que no se puede igualar es la fecha que Claude
Code antepone al mensaje (D35): si la repeticion es otro dia, cambia esa linea.

Uso:
    python -X utf8 run_stage4.py --app jpetstore-6 --desde claude-run1 --run-id claude-run1-e4-r01

Salida en output/<app>/<run_id>/: domains/ (copia), common_result.json y logs/ (los mismos archivos de la
Etapa 4 que una corrida completa, mas origen_etapa4.json). run_status.json lleva estado "parcial_etapa4".
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import traceback

import run_pipeline as rp
from run_pipeline import bp

ESTADO_OK = "parcial_etapa4"


def sha256_dir(path: str) -> dict:
    return {name: rp.sha256_file(os.path.join(path, name))
            for name in sorted(os.listdir(path)) if os.path.isfile(os.path.join(path, name))}


def read_exact(path: str) -> str:
    """Lee sin traducir saltos de linea (los prompts se guardan con newline="", bp.save_prompt)."""
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


class Stage4Repeat(rp.Pipeline):
    def __init__(self, args):
        args.only_stage1, args.max_turns_override = False, None
        super().__init__(args)
        self.source_id = args.desde
        self.source_dir = os.path.join(rp.BASE, "output", self.app, self.source_id)
        self.status["solo_etapa4_desde"] = self.source_id
        self.prompt = None
        self.origin = {}

    # ---------------------------------------------------------------- entrada de la corrida de origen
    def load_source(self) -> None:
        """Valida la corrida de origen y reconstruye la entrada de su Etapa 4. Sale sin crear nada si algo falla."""
        src, logs = self.source_dir, os.path.join(self.source_dir, "logs")
        if self.source_id == self.run_id:
            sys.exit("--desde y --run-id no pueden ser la misma corrida")
        if not os.path.isdir(src):
            sys.exit(f"no existe la corrida de origen {src}")
        try:
            with open(os.path.join(logs, "run_status.json"), encoding="utf-8") as f:
                status = json.load(f)
            with open(os.path.join(logs, "run_manifest.json"), encoding="utf-8") as f:
                manifest = json.load(f)
        except (OSError, ValueError) as e:
            sys.exit(f"la corrida de origen no tiene run_status.json/run_manifest.json legibles: {e}")
        if status.get("solo_etapa4_desde"):
            sys.exit("la corrida de origen ya es una repeticion de la Etapa 4: usa la corrida completa original")
        if status.get("app") != self.app or status.get("modelo") != self.model:
            sys.exit(f"la corrida de origen es de {status.get('app')} / {status.get('modelo')}, no de {self.app} / {self.model}")
        if (status.get("number"), status.get("num")) != (self.number, self.num):
            sys.exit(f"la corrida de origen uso number/num {status.get('number')}/{status.get('num')}")
        if bool(status.get("simulado")) and not self.simulated:
            sys.exit("la corrida de origen es simulada: no sirve de entrada para una repeticion real")
        if not any(e.get("etapa") == "4_common" for e in status.get("etapas") or []):
            sys.exit("la corrida de origen no llego a ejecutar la Etapa 4")
        digest = rp.context_fingerprint(self.app)["digest"]
        if (manifest.get("contexto") or {}).get("digest") != digest:
            sys.exit("el contexto de la aplicacion cambio desde la corrida de origen (D32): la entrada no seria la misma")
        # Mismo orquestador, prompts, herramientas, YAML del original y configuracion de `claude` que el origen.
        same = {
            "archivos_del_pipeline_sha256": manifest.get("archivos_del_pipeline_sha256") == rp.pipeline_files_fingerprint(),
            "esfuerzo": manifest.get("esfuerzo") == rp.EFFORT,
            "max_turns": manifest.get("max_turns") == rp.MAX_TURNS,
            "herramientas_por_agente": manifest.get("herramientas_por_agente") == rp.AGENT_TOOLS,
            "entorno_de_claude": manifest.get("entorno_de_claude") == {**rp.PIPELINE_ENV, **rp.EXTRA_ENV, **rp.MCP_ENV},
        }
        if not all(same.values()):
            sys.exit(f"la repeticion no usaria la misma configuracion que la corrida de origen: "
                     f"{[k for k, v in same.items() if not v]}")
        if not self.simulated:   # `claude --version` no llama al modelo
            proc = subprocess.run([self.claude_cmd[0], "--version"], capture_output=True, timeout=120, env=rp.child_env()[0])
            version = proc.stdout.decode("utf-8", errors="replace").strip()
            if version != (manifest.get("claude_code_version") or ""):
                sys.exit(f"version de Claude Code distinta de la de la corrida de origen: {version!r} frente a "
                         f"{manifest.get('claude_code_version')!r}")
            same["claude_code_version"] = True

        domains = os.path.join(src, "domains")
        merged_path, all_path = os.path.join(domains, "merged_domains.json"), os.path.join(domains, "all_domains.json")
        # Mismo domain_clusters que tenia run_pipeline.py al llegar a la Etapa 4 (main.py 259-338): el
        # merged_domains.json que escribio (con la clave Domain_Cluster desenvuelta) o, si la fusion dio un JSON
        # invalido y no lo escribio, all_domain_results.
        if os.path.exists(merged_path):
            with open(merged_path, encoding="utf-8") as f:
                merged = json.load(f)
            domain_clusters = merged["Domain_Cluster"] if "Domain_Cluster" in merged else merged
            clusters_from = "domains/merged_domains.json"
        else:
            with open(all_path, encoding="utf-8") as f:
                domain_clusters = json.load(f)
            clusters_from = "domains/all_domains.json"
        merging_context = None
        if status.get("fusion") == "ejecutada":   # D27: contexto de la Etapa 4 solo si hubo fusion
            merging_context = read_exact(os.path.join(logs, "3_merging_final_answer.txt"))

        prompt = bp.common_class_prompts(domain_clusters, self.number, self.num, context=merging_context)
        user_src = read_exact(os.path.join(logs, "4_common_prompt.txt"))
        system_src = read_exact(os.path.join(logs, "4_common_system_prompt.txt"))
        if prompt.user != user_src or prompt.system != system_src:
            sys.exit("el prompt reconstruido NO es identico al que recibio la Etapa 4 de la corrida de origen "
                     f"(usuario identico: {prompt.user == user_src}; system identico: {prompt.system == system_src}). "
                     "Se aborta sin llamar a `claude`.")
        self.prompt = prompt
        self.origin = {
            "corrida_de_origen": self.source_id,
            "estado_de_origen": status.get("estado"), "fusion_de_origen": status.get("fusion"),
            "domain_clusters_desde": clusters_from,
            "contexto_de_fusion": "3_merging_final_answer.txt" if merging_context is not None else None,
            "prompt_usuario_sha256": hashlib.sha256(user_src.encode("utf-8")).hexdigest(),
            "system_prompt_sha256": hashlib.sha256(system_src.encode("utf-8")).hexdigest(),
            "prompt_identico_al_origen": True,
            "domains_de_origen_sha256": sha256_dir(domains),
            "contexto_sha256": digest,
            "configuracion_igual_al_origen": same,
            # El orden de algunas respuestas de herramientas depende de la semilla de hash de Python (D41); como en
            # el original, no se fija. Se registra si la sesion que lanza la repeticion la tiene definida.
            "PYTHONHASHSEED_en_el_entorno": os.environ.get("PYTHONHASHSEED"),
        }

    def prepare(self, allow_references: bool) -> None:
        self.load_source()                 # antes de crear nada: si el origen no sirve, no queda carpeta
        super().prepare(allow_references)  # mismas protecciones que una corrida completa
        self.common_complete = False

    # ---------------------------------------------------------------- Etapa 4 (main.py 340-395)
    def run(self) -> None:
        # Copia de domains/ (las herramientas leen output/<app>/<run_id>/domains). Dentro de run(): si falla, la
        # repeticion queda registrada como fallida y no "en_curso".
        src_domains = os.path.join(self.source_dir, "domains")
        for name in sorted(os.listdir(src_domains)):
            if os.path.isfile(os.path.join(src_domains, name)):
                shutil.copyfile(os.path.join(src_domains, name), os.path.join(self.domains_dir, name))
        copied = sha256_dir(self.domains_dir)
        if copied != self.origin["domains_de_origen_sha256"]:
            raise rp.StageFailure("preparacion", "copia_de_domains_distinta", "la copia de domains/ no coincide con el origen")
        self.origin["domains_copiados_identicos"] = True
        rp.write_json(os.path.join(self.logs_dir, "origen_etapa4.json"), self.origin, indent=1, ensure_ascii=False)
        self.log(f"Repeticion aislada de la Etapa 4 con la entrada de {self.source_id} (fusion: "
                 f"{self.origin['fusion_de_origen']}; prompt identico al de origen; domains/ copiado: "
                 f"{len(copied)} archivos)")
        self.status["fusion"] = f"de_la_corrida_de_origen: {self.origin['fusion_de_origen']}"
        with open(os.path.join(self.domains_dir, os.path.basename(self.origin["domain_clusters_desde"])),
                  encoding="utf-8") as f:
            loaded = json.load(f)
        domain_clusters = loaded["Domain_Cluster"] if "Domain_Cluster" in loaded else loaded

        # Mismo bloque que run_pipeline.py (Pipeline.run, STAGE 4).
        self.log("\n--- Running Common Task ---")
        common_result_file = os.path.join(self.run_dir, "common_result.json")
        if os.path.exists(common_result_file):
            os.remove(common_result_file)
        r = self.call_agent("4_common", self.prompt, result_file=common_result_file)
        common_final_answer = r["final_answer"]
        common_result_json = self._accumulated_results(common_result_file)

        if common_result_json:
            self.log(f"Common task completed. Got results for {len(common_result_json)} domains from tool calls.")
            rp.dump_result(common_result_file, common_result_json)
        else:
            self.observe("4_common", "sin_resultados_de_write_result_to_json",
                         "Warning: No results from WriteResultToJson tool. Trying to parse from raw output... (main.py 384-395)")
            cleaned_common_result = rp.clean_json_output(common_final_answer)
            try:
                common_result_json = json.loads(cleaned_common_result)
                rp.dump_result(common_result_file, common_result_json)
                self.log(f"Common task result saved to {common_result_file}")
            except json.JSONDecodeError as e:
                self.observe("4_common", "json_invalido_en_clases_comunes", f"Error parsing common result: {e}; common_result_json = {{}}")
                common_result_json = {}
        self.common_complete = True   # lo que sigue es informativo: un fallo ahi no convierte el resultado en parcial

        # Solo informativo (no llega al modelo): que anadio la Etapa 4 a cada dominio respecto de su entrada.
        added = {}
        if isinstance(common_result_json, dict):
            for name, classes in common_result_json.items():
                before = set(domain_clusters.get(name) or []) if isinstance(domain_clusters.get(name), list) else set()
                if isinstance(classes, list):
                    added[name] = sorted(c for c in set(classes) - before if isinstance(c, str))
        with open(os.path.join(rp.BASE, "context", self.app, "class_summaries.json"), encoding="utf-8", errors="replace") as f:
            all_classes = list(json.load(f).keys())
        self.status["estado"] = ESTADO_OK
        self.status["resultado"] = {**self._result_stats(common_result_file, common_result_json, all_classes),
                                    "clases_anadidas_por_la_etapa4": added}


def main() -> int:
    ap = argparse.ArgumentParser(description="Repeticion aislada de la Etapa 4 con la entrada de una corrida completa (D41).")
    ap.add_argument("--app", required=True, choices=sorted(bp.APPS))
    ap.add_argument("--desde", required=True, help="corrida completa de origen, p. ej. claude-run1 (solo se lee)")
    ap.add_argument("--run-id", required=True, help="identificador nuevo, p. ej. claude-run1-e4-r01")
    ap.add_argument("--model", default=rp.MODEL, help=f"debe ser el de la corrida de origen (por defecto {rp.MODEL})")
    ap.add_argument("--stage-timeout", type=int, default=3600, help="segundos maximos para la llamada al agente")
    ap.add_argument("--allow-references", action="store_true",
                    help="permite correr con evaluation/references/ no vacia (queda registrado)")
    args = ap.parse_args()
    args.number, args.num = bp.APPS[args.app]

    pipeline = Stage4Repeat(args)
    pipeline.prepare(args.allow_references)
    failure = None
    try:
        pipeline.run()
    except rp.StageFailure as e:
        failure = {"etapa": e.etapa, "motivo": e.motivo, "detalle": e.detalle}
    except bp.PromptInterpolationError as e:
        failure = {"etapa": "armado_del_prompt", "motivo": "el_original_habria_abortado_al_interpolar", "detalle": str(e)}
    except Exception as e:
        failure = {"etapa": "orquestador", "motivo": f"excepcion {type(e).__name__}", "detalle": traceback.format_exc()}
    except KeyboardInterrupt:
        failure = {"etapa": "orquestador", "motivo": "interrumpida", "detalle": "repeticion interrumpida a mano (Ctrl+C)"}
    if failure:
        pipeline.status["estado"] = "fallida"
        pipeline.status["fallo"] = failure
        # write_result_to_json escribe common_result.json dominio a dominio: si la llamada falla, queda parcial.
        partial = os.path.join(pipeline.run_dir, "common_result.json")
        if os.path.exists(partial) and not getattr(pipeline, "common_complete", False):
            os.replace(partial, os.path.join(pipeline.run_dir, "common_result_parcial_de_corrida_fallida.json"))
            pipeline.status["resultado"] = None
            pipeline.observe("orquestador", "common_result_parcial_apartado",
                             "common_result.json quedo a medias y se renombro a common_result_parcial_de_corrida_fallida.json")
    pipeline.status["fin"] = rp.now()
    pipeline.save_status()

    st, tot = pipeline.status, pipeline.status["totales"]
    pipeline.log("\n--- Etapa 4 completa ---" if not failure else "\n--- REPETICION FALLIDA (registrar; no se repite con el mismo run_id) ---")
    pipeline.log(f"Estado: {st['estado']} | llamadas a agentes: {tot['llamadas']} | peticiones: {tot['peticiones_api']} | "
                 f"duracion: {round(tot['duracion_ms'] / 1000)} s | costo nominal: USD {tot['costo_usd']:.4f} | "
                 f"observaciones: {len(st['observaciones'])}")
    if failure:
        pipeline.log(f"Fallo en {failure['etapa']}: {failure['motivo']}\n{failure['detalle']}")
        return 1
    added = (st.get("resultado") or {}).get("clases_anadidas_por_la_etapa4") or {}
    pipeline.log("Clases anadidas por la Etapa 4: " + "; ".join(
        f"{k}: {[c.split('.')[-1] for c in v]}" for k, v in added.items()))
    pipeline.log(f"Registro: {os.path.relpath(pipeline.logs_dir, rp.BASE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
