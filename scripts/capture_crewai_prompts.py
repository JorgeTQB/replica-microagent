"""Captura de los prompts EXACTOS que arma el artefacto original (control de la Fase 3).

Ejecuta una COPIA temporal de `MicroAgent/microagent/src/microagent` (main.py, crew.py, YAML y
custom_tools.py originales, sin cambios de logica) con **CrewAI 1.8.1 real** y un **LLM simulado**
que no llama a ningun servicio: solo registra los mensajes (system, user) que CrewAI le entrega y
devuelve respuestas guionizadas. No gasta cupo ni usa la red.

Sirve para comprobar, caracter por caracter, que `prompts/build_prompts.py` reproduce lo que enviaba
el original (INSTRUCCIONES §6 y lista de verificacion §13).

Requisitos (NO son los de la replica: CrewAI 1.8.1 exige Python < 3.14):
    uv venv --python 3.12 <venv>
    uv pip install --python <venv>/Scripts/python.exe crewai==1.8.1 pyyaml
Uso:
    <venv>/Scripts/python.exe scripts/capture_crewai_prompts.py --workdir <carpeta temporal vacia>
Salida: logs/prompts_golden/<escenario>.json

Lo unico que se toca de la copia (nunca de `MicroAgent/`) son los tres valores que el propio original
manda editar a mano para cambiar de aplicacion: `'number'`, `'num'` (main.py, "Should be modified based
on desired output") y `"app_name"` (config.py). Cada sustitucion queda registrada en el JSON.
`sentence_transformers` y `sklearn` se sustituyen por modulos vacios: el LLM simulado solo llama a
`write_result_to_json`, que no los usa.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGINAL_SRC = os.path.join(os.path.dirname(BASE), "MicroAgent", "microagent", "src", "microagent")
OUT_DIR = os.path.join(BASE, "logs", "prompts_golden")

ROLES = {
    "Expert Software Architect - domain agent": "domain",
    "Expert Software Architect - clustering agent": "clustering",
    "Expert Software Architect - merging agent": "merging",
    "Expert Software Architect - common class agent": "common",
    "Expert Software Architect - review agent": "review",
}


# --------------------------------------------------------------------------------------------------
# Escenarios (guion del LLM simulado). Los textos son artificiales: solo importa que ejerciten las
# ramas de main.py (con y sin fusion) y caracteres delicados (comillas, apostrofos, llaves, saltos).
# --------------------------------------------------------------------------------------------------
def build_scenario(name: str) -> dict:
    app, number, num, n_domains = {
        "jpetstore_sin_fusion": ("jpetstore-6", "3", "THREE", 3),
        "jpetstore_con_fusion": ("jpetstore-6", "3", "THREE", 4),
        "partsunlimited_con_fusion": ("partsunlimited", "5", "FIVE", 6),
        "partsunlimited_sin_fusion": ("partsunlimited", "5", "FIVE", 5),
        # Una descripcion de dominio con una variable `{boundaries}` valida para CrewAI y ausente de `inputs`:
        # el original debe abortar al interpolar la primera tarea de clustering.
        "jpetstore_variable_en_descripcion": ("jpetstore-6", "3", "THREE", 3),
        # Un nombre de dominio con `{num}`: CrewAI lo interpola en la descripcion Y en el expected_output.
        "jpetstore_num_en_nombre": ("jpetstore-6", "3", "THREE", 3),
        # Salida de la fusion envuelta en "Domain_Cluster" y con un dominio agrupado por capas (main.py 306-330).
        "jpetstore_fusion_domain_cluster": ("jpetstore-6", "3", "THREE", 4),
        # Dominios que main.py omite (uno sin descripcion, otro sin nombre): el resumen y la lista de dominios
        # los siguen citando, la segunda tarea se empareja con el dominio equivocado (main.py 205) y quedan
        # MENOS resultados que `number`, asi que la fusion se ejecuta. La fusion devuelve un dominio por capas
        # y el Common Class Agent no usa la herramienta: su respuesta (con capas) se lee del texto (main.py 384-395)
        # y las capas cuentan al calcular las clases sin asignar (main.py 421-428). Anadido tras la revision de
        # la Fase 4 (D38).
        "jpetstore_dominios_omitidos": ("jpetstore-6", "3", "THREE", 4),
        # La fusion devuelve un texto que no es JSON (main.py 332-335): no se escribe merged_domains.json y las
        # etapas 4 y 5 siguen con los dominios sin fusionar. Anadido tras la revision de la Fase 4 (D38).
        "jpetstore_fusion_json_invalido": ("jpetstore-6", "3", "THREE", 4),
        # El Common Class Agent agota sus 45 iteraciones (max_iter) llamando a la herramienta: CrewAI no falla,
        # hace una llamada mas pidiendo la respuesta final (agent_utils.handle_max_iterations_exceeded). La
        # captura guarda los mensajes de esa llamada forzada. Anadido para D39.
        "jpetstore_limite_de_iteraciones": ("jpetstore-6", "3", "THREE", 3),
    }[name]
    with open(os.path.join(BASE, "context", app, "class_summaries.json"), encoding="utf-8") as f:
        classes = list(json.load(f).keys())

    descriptions = [
        "Manages the product catalog: categories, products and items. It doesn't cover orders.",
        'Handles the customer\'s "account" lifecycle (sign-on, profile).\nSecond line of the description.',
        "Order placement & fulfilment; line items, totals and sequence numbers {see boundaries}.",
        "Shopping cart: add/remove items, quantities, subtotal.",
        "Shipment tracking and delivery events for dealers.",
        "Quotes requested by dealers before an order exists.",
    ]
    names = ["Product Catalog", "Customer's Account", "Order Management", "Shopping Cart",
             "Shipment Tracking", "Dealer Quotes"]
    # Nota: la descripcion 2 lleva "{see boundaries}" (llaves que NO son una variable valida de CrewAI,
    # por el espacio) para comprobar que la interpolacion las deja intactas.
    if name == "jpetstore_variable_en_descripcion":
        descriptions[2] = descriptions[2].replace("{see boundaries}", "{boundaries}")
    if name == "jpetstore_num_en_nombre":
        names[1] = "Account {num} Services"
    domains = [{"domain_name": names[i], "description": descriptions[i]} for i in range(n_domains)]

    domain_json = json.dumps({"business_domains": domains}, indent=2)
    domain_raw = "```json\n" + domain_json + "\n```"  # con cerca, para ejercitar clean_json_output

    clustering_raw, expected_all = {}, {}
    for i, d in enumerate(domains):
        cls = classes[i::n_domains][:4]
        if i == 0:
            raw = "```json\n" + json.dumps({d["domain_name"]: cls}, indent=2) + "\n```"
        elif i == 2:
            raw = "Here is the result (not valid JSON on purpose): {" + ", ".join(cls)  # -> lista vacia
            cls = []
        else:
            raw = json.dumps({d["domain_name"]: cls})
        clustering_raw[d["domain_name"]] = raw
        expected_all[d["domain_name"]] = cls

    merged, merging_raw = None, None
    if n_domains != int(number):
        merged = dict(list(expected_all.items())[: int(number) - 1])
        rest = list(expected_all.items())[int(number) - 1:]
        merged["Merged " + " and ".join(k for k, _ in rest)] = [c for _, v in rest for c in v]
        merging_raw = json.dumps(merged, indent=2)
        if name == "jpetstore_fusion_domain_cluster":
            first = next(iter(merged))
            layered = dict(merged)
            layered[first] = {"Presentation": merged[first][:1], "Data": merged[first][1:]}
            merging_raw = "```json\n" + json.dumps({"Domain_Cluster": layered}, indent=2) + "\n```"
    clusters = merged if merged is not None else expected_all

    common_cls = classes[-1]
    if name == "jpetstore_fusion_json_invalido":
        merging_raw = "I merged the domains as requested. The result is: {" + ", ".join(expected_all)
        clusters = expected_all  # main.py 335: sigue con los dominios sin fusionar
    if name == "jpetstore_dominios_omitidos":
        del domains[1]["description"]  # main.py 140-142: sin tarea
        del domains[2]["domain_name"]  # main.py 137-139: sin tarea; "Unknown Domain" en el resumen
        domain_raw = "```json\n" + json.dumps({"business_domains": domains}, indent=2) + "\n```"
        first = expected_all[names[0]]
        merged = {names[0]: {"Presentation": first[:1], "Data": first[1:]},
                  "Customer & Cart": classes[1::n_domains][:3], "Everything Else": classes[2::n_domains][:2]}
        merging_raw = json.dumps(merged, indent=2)
        layered = {k: (dict(v, Data=v["Data"] + [common_cls]) if isinstance(v, dict) else v + [common_cls])
                   for k, v in merged.items()}
        flat = {k: ([c for layer in v.values() for c in layer] if isinstance(v, dict) else v) for k, v in layered.items()}
        return {
            "name": name, "app": app, "number": number, "num": num,
            "domain_raw": domain_raw, "clustering_raw": clustering_raw, "merging_raw": merging_raw,
            "common_writes": [], "common_final": "```json\n" + json.dumps(layered, indent=2) + "\n```",
            "review_writes": [[k, v + [classes[-2]]] for k, v in flat.items()],
            "review_final": f"Final microservices saved: {len(flat)} domains.",
        }
    common_writes = [[k, list(v) + [common_cls]] for k, v in clusters.items()]
    common_final = (f"All {len(clusters)} domains have been saved.\n"
                    f"Summary: {len(clusters)} domains, {sum(len(v) for _, v in common_writes)} classes.")
    review_writes = [[k, list(v) + [classes[-2]]] for k, v in common_writes]
    review_final = f"Final microservices saved: {len(clusters)} domains."
    if name == "jpetstore_limite_de_iteraciones":
        common_writes = common_writes * 15  # 45 llamadas a la herramienta = max_iter del Common Class Agent
    return {
        "name": name, "app": app, "number": number, "num": num,
        "domain_raw": domain_raw, "clustering_raw": clustering_raw, "merging_raw": merging_raw,
        "common_writes": common_writes, "common_final": common_final,
        "review_writes": review_writes, "review_final": review_final,
    }


# --------------------------------------------------------------------------------------------------
# Proceso padre: prepara la copia, lanza un hijo por escenario y guarda el JSON.
# --------------------------------------------------------------------------------------------------
def patch_copy(root: str, sc: dict) -> list:
    patches = []

    def sub(rel, old, new):
        path = os.path.join(root, rel)
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        if text.count(old) != 1:
            raise SystemExit(f"se esperaba 1 aparicion de {old!r} en {rel}, hay {text.count(old)}")
        if old != new:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text.replace(old, new))
        patches.append({"file": rel, "old": old, "new": new})

    sub("src/microagent/main.py", "'number': '3'", f"'number': '{sc['number']}'")
    sub("src/microagent/main.py", "'num': 'THREE'", f"'num': '{sc['num']}'")
    sub("src/microagent/config/config.py", '"app_name": "jpetstore-6"', f'"app_name": "{sc["app"]}"')
    return patches


def run_parent(workdir: str, names: list) -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    failures = 0
    for name in names:
        sc = build_scenario(name)
        root = os.path.join(workdir, name)
        if os.path.exists(root):
            shutil.rmtree(root)
        shutil.copytree(ORIGINAL_SRC, os.path.join(root, "src", "microagent"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        for folder in ("context", "database"):
            shutil.copytree(os.path.join(BASE, folder, sc["app"]), os.path.join(root, folder, sc["app"]))
        patches = patch_copy(root, sc)
        script_path = os.path.join(root, "_scenario.json")
        capture_path = os.path.join(root, "_capture.json")
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(sc, f)
        env = dict(os.environ)
        env.update({
            "MODEL": "fake-model", "OPENAPI_API_KEY": "none", "OPENAPI_API_BASE": "http://localhost:9",
            "CREWAI_DISABLE_TELEMETRY": "true", "CREWAI_DISABLE_TRACKING": "true", "OTEL_SDK_DISABLED": "true",
            "CREWAI_TRACING_ENABLED": "false", "CREWAI_STORAGE_DIR": "microagent-prompt-capture",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
        })
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", script_path, capture_path],
                              cwd=root, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=900)
        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        if proc.returncode != 0 or not os.path.exists(capture_path):
            failures += 1
            print(f"[{name}] FALLO (exit={proc.returncode})\n{stdout[-3000:]}\n{stderr[-3000:]}")
            continue
        with open(capture_path, encoding="utf-8") as f:
            capture = json.load(f)
        outputs = {}
        out_root = os.path.join(root, "output", sc["app"], "fake-model")
        for dirpath, _, files in os.walk(out_root):
            for fn in files:
                p = os.path.join(dirpath, fn)
                with open(p, encoding="utf-8", newline="") as f:
                    outputs[os.path.relpath(p, out_root).replace("\\", "/")] = f.read()
        golden = {
            "descripcion": "Mensajes que CrewAI entrega al LLM al ejecutar el main.py original con un LLM simulado.",
            "crewai_version": capture["crewai_version"], "python": capture["python"],
            "scenario": sc, "patches_en_la_copia": patches,
            "executions": capture["executions"], "error": capture.get("error"), "outputs": outputs,
            "stdout_tail": stdout[-1500:],
        }
        with open(os.path.join(OUT_DIR, name + ".json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(golden, f, indent=1, ensure_ascii=False)
        stages = [e["stage"] for e in capture["executions"]]
        print(f"[{name}] OK: {len(stages)} ejecuciones de agente: {stages}"
              + (f" | el original aborto con: {capture['error']}" if capture.get("error") else ""))
    return failures


# --------------------------------------------------------------------------------------------------
# Proceso hijo: importa el original con CrewAI real y un LLM simulado.
# --------------------------------------------------------------------------------------------------
def run_child(script_path: str, capture_path: str) -> None:
    import re
    import types

    with open(script_path, encoding="utf-8") as f:
        sc = json.load(f)

    def stub(modname, **attrs):
        mod = types.ModuleType(modname)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[modname] = mod
        return mod

    def _unavailable(*a, **k):
        raise RuntimeError("modulo sustituido en la captura de prompts; no debe usarse")

    stub("sentence_transformers", SentenceTransformer=_unavailable)
    stub("sklearn")
    stub("sklearn.metrics")
    stub("sklearn.metrics.pairwise", cosine_similarity=_unavailable)
    stub("sklearn.feature_extraction")
    stub("sklearn.feature_extraction.text", TfidfVectorizer=_unavailable)

    import crewai
    from crewai.llms.base_llm import BaseLLM

    executions = []

    class FakeLLM(BaseLLM):
        def call(self, messages, tools=None, callbacks=None, available_functions=None,
                 from_task=None, from_agent=None, response_model=None, **kwargs):
            if isinstance(messages, str):
                messages = [{"role": "user", "content": messages}]
            system = next((m["content"] for m in messages if m["role"] == "system"), "")
            users = [m["content"] for m in messages if m["role"] == "user"]
            n_assistant = sum(1 for m in messages if m["role"] == "assistant")
            role = re.match(r"You are (.*?)\. ", system)
            stage = ROLES.get(role.group(1) if role else "", "desconocido")
            if n_assistant == 0:
                executions.append({"stage": stage, "roles": [m["role"] for m in messages],
                                   "system": system, "user": users[0] if users else "", "n_llm_calls": 0})
            executions[-1]["n_llm_calls"] += 1
            # Llamada forzada al agotar max_iter: CrewAI anade un mensaje que termina con este texto.
            if messages[-1]["role"] != "user" and str(messages[-1]["content"]).endswith("just return your absolute BEST Final answer."):
                executions[-1]["forced_final_answer"] = {
                    "llm_call_number": executions[-1]["n_llm_calls"], "n_messages": len(messages),
                    "roles_tail": [m["role"] for m in messages[-3:]],
                    "previous_message": messages[-2]["content"], "last_message": messages[-1]["content"]}

            def final(text):
                return "Thought: I now know the final answer\nFinal Answer: " + text

            def write(pair):
                return ("Thought: I need to save this domain.\nAction: write_result_to_json\nAction Input: "
                        + json.dumps({"domain_name": pair[0], "class_list": pair[1]}))

            if stage == "domain":
                return final(sc["domain_raw"])
            if stage == "clustering":
                name = re.search(r"You are analyzing the '(.*?)' domain\. The description", users[0], re.S).group(1)
                # El nombre llega ya interpolado por CrewAI ({num}/{number}); el guion usa el nombre original.
                by_sent_name = {k.replace("{num}", sc["num"]).replace("{number}", sc["number"]): v
                                for k, v in sc["clustering_raw"].items()}
                return final(by_sent_name[name])
            if stage == "merging":
                return final(sc["merging_raw"])
            writes, last = (sc["common_writes"], sc["common_final"]) if stage == "common" else \
                           (sc["review_writes"], sc["review_final"])
            return write(writes[n_assistant]) if n_assistant < len(writes) else final(last)

        def supports_function_calling(self) -> bool:
            return False

        def supports_stop_words(self) -> bool:
            return True

        def get_context_window_size(self) -> int:
            return 200000

    crewai.LLM = lambda **kw: FakeLLM(model=kw.get("model") or "fake-model")

    sys.path.insert(0, os.path.join(os.getcwd(), "src"))
    import microagent.main as original_main  # la copia del main.py original

    error = None
    try:
        original_main.run()
    except NameError as e:  # error conocido del final de main.py (`final_result_raw` sin definir, §7)
        print(f"NameError esperado al final de main.py: {e}")
    except Exception as e:  # el original aborta: se registra tal cual (no es un fallo de la captura)
        error = f"{type(e).__name__}: {e}"
        print(f"El original aborto: {error}")

    with open(capture_path, "w", encoding="utf-8") as f:
        json.dump({"crewai_version": crewai.__version__, "python": sys.version, "executions": executions,
                   "error": error}, f)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        run_child(sys.argv[2], sys.argv[3])
        sys.exit(0)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workdir", required=True, help="carpeta temporal (fuera de MicroAgent/) para las copias")
    ap.add_argument("--scenario", nargs="*", default=["jpetstore_sin_fusion", "jpetstore_con_fusion",
                                                      "partsunlimited_con_fusion", "partsunlimited_sin_fusion",
                                                      "jpetstore_variable_en_descripcion",
                                                      "jpetstore_num_en_nombre", "jpetstore_fusion_domain_cluster",
                                                      "jpetstore_dominios_omitidos", "jpetstore_fusion_json_invalido",
                                                      "jpetstore_limite_de_iteraciones"])
    args = ap.parse_args()
    sys.exit(1 if run_parent(os.path.abspath(args.workdir), args.scenario) else 0)
