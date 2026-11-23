"""Comprobacion de la Fase 3: `prompts/build_prompts.py` frente a los prompts reales del original.

Compara, caracter por caracter, lo que arma la replica con lo que CrewAI 1.8.1 entrego al LLM al ejecutar
el main.py original (capturas de `logs/prompts_golden/`, generadas por `scripts/capture_crewai_prompts.py`).

  - Mensaje de usuario: debe ser IDENTICO al del original.
  - System prompt: el del original debe ser el de la replica + el bloque de herramientas/ReAct de CrewAI
    (lo unico que §6 excluye), y nada mas.

Uso:  python -X utf8 scripts/check_prompts.py      (no llama a ningun LLM; no necesita CrewAI)
Salida: logs/prompts_check.txt y codigo de salida 0 si todo coincide.
"""
import glob
import hashlib
import json
import os
import re
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "prompts"))
import build_prompts as bp  # noqa: E402

GOLDEN_DIR = os.path.join(BASE, "logs", "prompts_golden")
OUT = os.path.join(BASE, "logs", "prompts_check.txt")

# Inicio y fin del slice `tools` de CrewAI 1.8.1 (bloque que la replica NO envia).
TOOLS_PREFIX = "\nYou ONLY have access to the following tools, and should NEVER make up tools that are not listed here:\n\n"
TOOLS_SUFFIX = ("\n```\n\nOnce all necessary information is gathered, return the following format:\n\n```\n"
                "Thought: I now know the final answer\nFinal Answer: the final answer to the original input question\n```")
# Herramientas por agente segun INSTRUCCIONES §5.3 (control cruzado con lo que CrewAI anuncio al LLM).
TOOLS_5_3 = {
    "domain": ["get_all_class_hierarchy", "get_database_summary", "get_all_class_summaries",
               "get_class_basic_info", "get_class_summary"],
    "clustering": ["get_all_class_hierarchy_complete", "get_database_summary", "codebase_semantic_search",
                   "get_related_class_list", "get_class_relation_and_code", "search_file"],
    "merging": ["get_all_class_hierarchy_complete", "get_database_summary", "get_class_relation_and_code",
                "search_file"],
    "common": ["get_all_class_hierarchy_complete", "get_database_summary", "rank_dependency_entropy",
               "assign_common_class_list", "get_more_potential_common_classes", "write_result_to_json",
               "get_class_relation_and_code", "search_file"],
    "review": ["get_all_class_hierarchy_complete", "get_database_summary", "get_class_relation_and_code",
               "search_file", "write_result_to_json", "get_related_class_list"],
}

lines, problems = [], []


def log(msg=""):
    lines.append(msg)
    print(msg)


def first_diff(a: str, b: str) -> str:
    n = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return f"primera diferencia en el caracter {n}: replica={a[max(0, n - 40):n + 40]!r} | original={b[max(0, n - 40):n + 40]!r}"


def check(ok: bool, label: str, detail: str = ""):
    if not ok:
        problems.append(label)
    log(f"  [{'OK' if ok else 'FALLA'}] {label}" + (f" -- {detail}" if detail and not ok else ""))


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_golden(path: str):
    with open(path, encoding="utf-8") as f:
        g = json.load(f)
    sc, outputs, executions = g["scenario"], g["outputs"], g["executions"]
    check(g["crewai_version"] == "1.8.1", f"{os.path.basename(path)} capturada con CrewAI 1.8.1 (la version del artefacto)",
          g["crewai_version"])
    number, num, app = sc["number"], sc["num"], sc["app"]
    log(f"\n== {os.path.basename(path)}  (app={app}, number={number}, num={num}, CrewAI {g['crewai_version']}, "
        f"{len(executions)} ejecuciones de agente)")

    # Datos intermedios tal como los dejo el main.py original en su carpeta de salida.
    business_domains = json.loads(outputs["domains/domain_clusters.json"])["business_domains"]

    if g.get("error"):
        # El original aborto al interpolar una descripcion con una variable desconocida: la replica debe
        # negarse igual, en la misma etapa.
        check([e["stage"] for e in executions] == ["domain"], "el original solo llego a ejecutar la Etapa 1")
        try:
            bp.clustering_prompts(business_domains[0], business_domains, number, num)
            check(False, "la replica lanza PromptInterpolationError donde el original aborta")
        except bp.PromptInterpolationError as e:
            check("boundaries" in str(e), "la replica lanza PromptInterpolationError donde el original aborta")
            log(f"       original: {g['error']}")
            log(f"       replica : {e}")
        expected = [bp.domain_prompts(number, num)]
    else:
        all_domain_results = json.loads(outputs["domains/all_domains.json"])
        merged = len(all_domain_results) != int(number)
        # merged_domains.json es la salida de la fusion tal cual; main.py 306-310 la desenvuelve.
        # Si la fusion no devolvio JSON, main.py 332-335 no escribe el archivo y sigue con los dominios sin fusionar.
        if "domains/merged_domains.json" in outputs:
            merged_domains = json.loads(outputs["domains/merged_domains.json"])
            domain_clusters = merged_domains["Domain_Cluster"] if "Domain_Cluster" in merged_domains else merged_domains
        else:
            domain_clusters = all_domain_results
        common_result = json.loads(outputs["common_result.json"])
        with open(os.path.join(BASE, "context", app, "class_summaries.json"), encoding="utf-8") as f:
            all_classes = list(json.load(f).keys())
        assigned = set()  # main.py 421-428
        for classes in common_result.values():
            if isinstance(classes, list):
                assigned.update(classes)
            elif isinstance(classes, dict):
                for layer_classes in classes.values():
                    if isinstance(layer_classes, list):
                        assigned.update(layer_classes)
        remaining = [c for c in all_classes if c not in assigned]

        expected = [bp.domain_prompts(number, num)]
        # main.py 134-142: no crea tarea para un dominio sin nombre o sin descripcion.
        with_task = [d for d in business_domains
                     if d.get("domain_name", "Unknown Domain") not in ("Unknown Domain", "", None)
                     and d.get("description", "No description provided") != "No description provided"]
        expected += [bp.clustering_prompts(d, business_domains, number, num) for d in with_task]
        if merged:
            expected.append(bp.merging_prompts(business_domains, all_domain_results, number, num))
        expected.append(bp.common_class_prompts(domain_clusters, number, num,
                                                context=sc["merging_raw"] if merged else None))
        expected.append(bp.review_prompts(common_result, remaining, domain_clusters, number, num,
                                          context=sc["common_final"]))
        check(merged == (sc["merging_raw"] is not None), f"fusion {'ejecutada' if merged else 'saltada'} segun len == number")

    check([p.stage for p in expected] == [e["stage"] for e in executions],
          "mismas etapas y en el mismo orden", f"{[p.stage for p in expected]} vs {[e['stage'] for e in executions]}")
    for i, (p, e) in enumerate(zip(expected, executions)):
        tag = f"{i}:{p.stage}"
        check(e["roles"] == ["system", "user"], f"{tag} el original envia [system, user]")
        check(p.user == e["user"], f"{tag} mensaje de usuario identico ({len(p.user)} caracteres)",
              first_diff(p.user, e["user"]))
        rest = e["system"][len(p.system):]
        check(e["system"].startswith(p.system) and rest.startswith(TOOLS_PREFIX) and rest.endswith(TOOLS_SUFFIX),
              f"{tag} system del original = system de la replica ({len(p.system)} car.) + bloque herramientas/ReAct "
              f"({len(rest)} car.)", first_diff(p.system, e["system"]))
        announced = re.findall(r"^Tool Name: (\S+)$", rest, re.M)
        check(announced == TOOLS_5_3[p.stage], f"{tag} herramientas anunciadas por CrewAI = tabla de §5.3",
              f"{announced}")
        check(("This is the context you're working with:" in e["user"]) ==
              (p.stage == "review" or (p.stage == "common" and sc["merging_raw"] is not None)),
              f"{tag} bloque de contexto presente solo donde corresponde")


def check_static():
    log("\n== Comprobaciones sin captura")
    agents, tasks = bp.agents_config(), bp.tasks_config()
    for app, (number, num) in bp.APPS.items():
        for stage, agent in bp.STAGE_AGENT.items():
            s = bp.system_prompt(agent, number, num)
            cfg = agents[agent]
            ok = (s.startswith(f"You are {cfg['role']}. ") and "{number}" not in s and "{num}" not in s
                  and "Thought:" not in s and "Action:" not in s and "You ONLY have access" not in s
                  and s.endswith("\nYour personal goal is: " + cfg["goal"]))
            check(ok, f"{app} system {agent}: role/backstory/goal del YAML, sin variables ni ReAct")
        s = bp.system_prompt("merging_agent", number, num)
        check(f"form EXACTLY {number} clusters" in s, f"{app} backstory del Merging Agent con {{number}} -> {number}")
        d = bp.domain_prompts(number, num)
        check(d.user.startswith("\nCurrent Task: You are tasked with identifying core business domains")
              and d.user.endswith("your job depends on it!\n\nThought:"), f"{app} envoltura completa de CrewAI en la Etapa 1")
        check(f"more than OR equal to {num}." in d.user, f"{app} {{num}} -> {num} en la Etapa 1")
        raw = tasks["identification_task"]["expected_output"]
        check(d.user.count("{{") == raw.count("{{") == 2 and d.user.count("}}") == raw.count("}}") == 2,
              f"{app} llaves dobles del YAML intactas en la Etapa 1")
    # Texto de los YAML presente sin tocar (salvo {num}/{number}).
    for name, t in tasks.items():
        if name in ("identification_task", "merging_task", "review_task"):
            continue
        check("{" not in t["description"], f"{name}.description no tiene variables")
    # save_prompt: bytes exactos.
    with tempfile.TemporaryDirectory() as tmp:
        p = bp.domain_prompts("3", "THREE")
        user_path, system_path = bp.save_prompt(tmp, "1_domain", p)
        with open(user_path, "rb") as f:
            ub = f.read()
        with open(system_path, "rb") as f:
            sb = f.read()
        check(ub == p.user.encode("utf-8") and sb == p.system.encode("utf-8") and b"\r" not in ub + sb,
              "save_prompt escribe los bytes exactos (UTF-8, sin CRLF)")
    for name in ("agents.yaml", "tasks.yaml"):
        log(f"  sha256 {name}: {sha(os.path.join(bp.ORIGINAL_CONFIG_DIR, name))}")


def main():
    files = sorted(glob.glob(os.path.join(GOLDEN_DIR, "*.json")))
    log(f"Comprobacion de prompts (Fase 3). Capturas: {len(files)} en {os.path.relpath(GOLDEN_DIR, BASE)}")
    check(len(files) >= 7, "hay capturas del original (ejecuta scripts/capture_crewai_prompts.py si faltan)")
    for path in files:
        check_golden(path)
    check_static()
    log(f"\nRESULTADO: {'OK' if not problems else 'FALLA'} ({len(problems)} problemas)")
    for p in problems:
        log(f"  - {p}")
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
