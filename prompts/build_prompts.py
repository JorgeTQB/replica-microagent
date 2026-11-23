"""Prompts literales de MicroAgent para la replica con Claude Code (INSTRUCCIONES §6, Fase 3).

Arma, para cada etapa, el *system prompt* y el *user prompt* que el artefacto original entregaba al LLM:

    agents.yaml / tasks.yaml (originales, leidos de MicroAgent/, sin copiarlos ni editarlos)
    + texto dinamico de main.py
    + plantillas de CrewAI 1.8.1 (crewai/translations/en.json)

El *user prompt* es identico, caracter por caracter, al mensaje de usuario del original.
El *system prompt* es el del original SIN el bloque de herramientas y formato ReAct
("You ONLY have access to the following tools ... Thought/Action/Observation"), que §6 excluye porque
Claude recibe las herramientas por llamada nativa (MCP).

Ambas cosas se comprueban contra una captura real de CrewAI 1.8.1: `scripts/check_prompts.py`
(capturas en `logs/prompts_golden/`, generadas por `scripts/capture_crewai_prompts.py`).

Decisiones de Jorge del 2026-11-16 (DECISIONES.md D25 a D27), que corrigen tres puntos de §6 y §7:
  1. `{{` y `}}` NO se convierten a `{` y `}`: CrewAI 1.8.1 no los convierte y el LLM original los recibia
     dobles (ejemplo JSON de las tareas de Domain y Merging).
  2. El mensaje de usuario lleva la envoltura completa de CrewAI ("Current Task: ... Begin! ... Thought:").
  3. Los agentes Common Class y Review reciben como contexto la respuesta final del agente anterior
     ("This is the context you're working with:"), igual que en el original.

Uso desde el orquestador (Fase 4):
    import build_prompts as bp
    p = bp.domain_prompts(number="3", num="THREE")
    p.system, p.user            # -> --system-prompt y mensaje de usuario
    bp.save_prompt(logs_dir, "1_domain", p)
Vista previa de los prompts que no dependen de la corrida:
    python prompts/build_prompts.py --app jpetstore-6 --out logs/prompts_preview/jpetstore-6
"""
from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from textwrap import dedent

import yaml

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGINAL_CONFIG_DIR = os.path.join(os.path.dirname(BASE), "MicroAgent", "microagent", "src", "microagent", "config")

# n y su forma en letras por aplicacion (INSTRUCCIONES §4.2, §4.3 y §7).
APPS = {"jpetstore-6": ("3", "THREE"), "partsunlimited": ("5", "FIVE")}

# --------------------------------------------------------------------------------------------------
# Plantillas de CrewAI 1.8.1, copiadas literalmente de crewai/translations/en.json ("slices").
# --------------------------------------------------------------------------------------------------
# System prompt = role_playing + tools. De `tools` (lista de herramientas + formato ReAct) no se usa nada.
SLICE_ROLE_PLAYING = "You are {role}. {backstory}\nYour personal goal is: {goal}"
# Mensaje de usuario = slice `task`, con {input} = prompt de la tarea.
SLICE_TASK = ("\nCurrent Task: {input}\n\nBegin! This is VERY important to you, use the tools available and give "
              "your best Final Answer, your job depends on it!\n\nThought:")
# Task.prompt() = "\n".join([description, SLICE_EXPECTED_OUTPUT.format(expected_output=...)])
SLICE_EXPECTED_OUTPUT = ("\nThis is the expected criteria for your final answer: {expected_output}\n"
                         "you MUST return the actual complete content as the final answer, not a summary.")
# Si la tarea tiene contexto (salida de una tarea anterior): format_task_with_context().
SLICE_TASK_WITH_CONTEXT = "{task}\n\nThis is the context you're working with:\n{context}"

# Agente (clave de agents.yaml) de cada etapa, en el orden de main.py.
STAGE_AGENT = {
    "domain": "domain_agent",
    "clustering": "clustering_agent",
    "merging": "merging_agent",
    "common": "common_class_agent",
    "review": "review_agent",
}


class PromptInterpolationError(ValueError):
    """El original habria abortado aqui: CrewAI lanza ValueError si un texto de tarea contiene una
    variable `{nombre}` que no esta en `inputs` (p. ej. dentro de una descripcion escrita por el
    Domain Agent). La replica no lo oculta: el orquestador debe registrar la corrida como fallida."""


@dataclass(frozen=True)
class Prompt:
    stage: str          # domain | clustering | merging | common | review
    agent: str          # clave de agents.yaml
    system: str         # system prompt (role_playing, sin el bloque de herramientas/ReAct)
    user: str           # mensaje de usuario exacto del original
    description: str    # descripcion de la tarea ya interpolada (parte de `user`)
    expected_output: str  # expected_output ya interpolado (parte de `user`)


# --------------------------------------------------------------------------------------------------
# Carga de los YAML originales (CrewAI: yaml.safe_load, UTF-8; crewai/project/crew_base.py::load_yaml)
# --------------------------------------------------------------------------------------------------
def load_yaml(name: str) -> dict:
    with open(os.path.join(ORIGINAL_CONFIG_DIR, name), encoding="utf-8") as f:
        return yaml.safe_load(f)


def agents_config() -> dict:
    return load_yaml("agents.yaml")


def tasks_config() -> dict:
    return load_yaml("tasks.yaml")


# --------------------------------------------------------------------------------------------------
# Interpolacion de variables: misma logica que crewai/utilities/string_utils.py::interpolate_only (1.8.1).
# Solo sustituye `{nombre}` con nombre de variable valido; NO toca `{{` ni `}}` ni el JSON.
# --------------------------------------------------------------------------------------------------
_VARIABLE_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_\-]*)}")


def interpolate_only(input_string: str | None, inputs: dict) -> str:
    if input_string is None or not input_string:
        return ""
    if "{" not in input_string and "}" not in input_string:
        return input_string
    if not inputs:
        raise ValueError("Inputs dictionary cannot be empty when interpolating variables")
    variables = _VARIABLE_PATTERN.findall(input_string)
    result = input_string
    missing_vars = [var for var in variables if var not in inputs]
    if missing_vars:
        raise KeyError(f"Template variable '{missing_vars[0]}' not found in inputs dictionary")
    for var in variables:
        if var in inputs:
            placeholder = "{" + var + "}"
            value = str(inputs[var])
            result = result.replace(placeholder, value)
    return result


def _interpolate(text: str, inputs: dict, what: str) -> str:
    try:
        return interpolate_only(text, inputs)
    except KeyError as e:
        raise PromptInterpolationError(
            f"Missing required template variable '{e.args[0]}' in {what} "
            f"(el original habria fallado igual en Crew.kickoff)") from e


def _inputs(number, num) -> dict:
    """`inputs` de main.py: {'number': '3', 'num': 'THREE'} (cadenas)."""
    return {"number": str(number), "num": str(num)}


# --------------------------------------------------------------------------------------------------
# Ensamblado (CrewAI 1.8.1)
# --------------------------------------------------------------------------------------------------
def system_prompt(agent: str, number, num) -> str:
    """`You are {role}. {backstory}\\nYour personal goal is: {goal}` con role/goal/backstory interpolados
    (Agent.interpolate_inputs) y sustituidos en el mismo orden que Prompts._build_prompt."""
    cfg = agents_config()[agent]
    inputs = _inputs(number, num)
    role = _interpolate(cfg["role"], inputs, f"{agent}.role")
    goal = _interpolate(cfg["goal"], inputs, f"{agent}.goal")
    backstory = _interpolate(cfg["backstory"], inputs, f"{agent}.backstory")
    return SLICE_ROLE_PLAYING.replace("{goal}", goal).replace("{role}", role).replace("{backstory}", backstory)


def task_prompt(description: str, expected_output: str, context: str | None = None) -> str:
    """Task.prompt() + format_task_with_context(). `description` y `expected_output` ya interpolados."""
    prompt = "\n".join([description, SLICE_EXPECTED_OUTPUT.format(expected_output=expected_output)])
    if context:
        prompt = SLICE_TASK_WITH_CONTEXT.format(task=prompt, context=context)
    return prompt


def user_message(prompt: str) -> str:
    """CrewAgentExecutor._format_prompt sobre el slice `task`: `{input}` -> prompt de la tarea.
    El original sustituye despues `{tool_names}` y `{tools}` por el texto de herramientas de ReAct; si
    aparecieran (solo podrian venir del contexto), la replica no puede reproducirlo y lo avisa."""
    message = SLICE_TASK.replace("{input}", prompt)
    for token in ("{tool_names}", "{tools}"):
        if token in message:
            raise PromptInterpolationError(
                f"el prompt contiene {token}: el original lo reemplazaria por el texto de herramientas de "
                f"ReAct, que la replica no usa")
    return message


def _build(stage: str, raw_description: str, raw_expected_output: str, number, num,
           context: str | None = None) -> Prompt:
    """Lo que hace Crew.kickoff(inputs): interpola la descripcion y el expected_output COMPLETOS (incluido
    el texto dinamico de main.py) y arma los mensajes."""
    inputs = _inputs(number, num)
    agent = STAGE_AGENT[stage]
    description = _interpolate(raw_description, inputs, f"description ({stage})")
    expected_output = _interpolate(raw_expected_output, inputs, f"expected_output ({stage})")
    return Prompt(
        stage=stage,
        agent=agent,
        system=system_prompt(agent, number, num),
        user=user_message(task_prompt(description, expected_output, context)),
        description=description,
        expected_output=expected_output,
    )


# --------------------------------------------------------------------------------------------------
# Etapas (texto dinamico copiado de main.py; las lineas citadas son de ese archivo)
# --------------------------------------------------------------------------------------------------
def domain_prompts(number, num) -> Prompt:
    """Etapa 1 (main.py 66-75): identification_task tal cual."""
    task = tasks_config()["identification_task"]
    return _build("domain", task["description"], task["expected_output"], number, num)


def all_domains_summary(business_domains: list) -> str:
    """main.py 122-128."""
    summary = "Summary of all business domains:\n\n"
    for idx, domain in enumerate(business_domains, 1):
        domain_name = domain.get("domain_name", "Unknown Domain")
        domain_description = domain.get("description", "No description provided")
        summary += f"{idx}. {domain_name}: {domain_description}\n"
    summary += ("\nYou are responsible for analyzing ONLY your assigned domain, but understanding the boundaries "
                "between domains is important for proper classification.")
    return summary


def clustering_prompts(domain: dict, business_domains: list, number, num) -> Prompt:
    """Etapa 2 (main.py 131-175): una llamada por dominio. `domain` es un elemento de `business_domains`
    con nombre y descripcion (main.py 137-142 omite los que no los tienen; eso lo decide el orquestador)."""
    domain_name = domain.get("domain_name", "Unknown Domain")
    domain_description = domain.get("description", "No description provided")
    original_clustering_description = tasks_config()["clustering_task"]["description"]
    task_description = (
        f"You are analyzing the '{domain_name}' domain. The description of this domain is: {domain_description}\n\n"
        f"{all_domains_summary(business_domains)}\n\n"
        f"{original_clustering_description}"
    )
    expected_output = dedent(f"""
                A JSON object containing the clustering class list for the '{domain_name}' domain.
                The JSON MUST follow this EXACT structure with proper commas between elements:
                {{
                  "{domain_name}": [
                    "org.example.Class1",
                    "org.example.Class2",
                    "org.example.Class3"
                  ]
                }}

                DO NOT nest the classes under categories like "Domain Objects", "Presentation Layer", etc.
                Just provide a flat array of class names under the domain name key.

                Ensure all JSON elements have proper commas between them.
                Your final answer MUST be ONLY the JSON object, with no other text, commentary, or explanation.
            """)
    return _build("clustering", task_description, expected_output, number, num)


def domain_list_str(business_domains: list) -> str:
    """main.py 183-184 (incluye TODOS los dominios de la Etapa 1, tambien los omitidos en la Etapa 2)."""
    all_domain_names_descriptions = [
        f"'{domain.get('domain_name', 'Unknown Domain')}' -- description: '{domain.get('description', 'No description provided')}'"
        for domain in business_domains
    ]
    return ", ".join(all_domain_names_descriptions)


def merging_prompts(business_domains: list, all_domain_results: dict, number, num) -> Prompt:
    """Etapa 3 (main.py 186-289). Solo se usa si len(all_domain_results) != number.
    `{all_domain_results}` es el repr de Python del dict, como en el original."""
    task = tasks_config()["merging_task"]
    original_description = task["description"]
    description = (
        f"You need to merge the business domains into {_inputs(number, num)['number']} clusters. You have been provided with the class structures for the following business domains: {domain_list_str(business_domains)}. "
        f"The details of each domain data is as follows: {all_domain_results}. "
        f"{original_description}"
    )
    return _build("merging", description, task["expected_output"], number, num)


def common_class_prompts(domain_clusters: dict, number, num, context: str | None = None) -> Prompt:
    """Etapa 4 (main.py 342-376).
    `context`: respuesta final (texto) del Merging Agent si la Etapa 3 se ejecuto; None si se salto.
    En el original llega por `context=[self.merging_task()]` de crew.py (la tarea esta memoizada)."""
    original_common_description = tasks_config()["common_class_task"]["description"]
    domain_names = list(domain_clusters.keys())
    description = (
        f"You have been provided with the merged domain clusters: {domain_clusters}. "
        f"This file contains the domains for classes after the merging phase. "
        f"{original_common_description}\n\n"
        f"IMPORTANT: To avoid output token limit issues, you MUST use the 'write_result_to_json' tool to save results. "
        f"Call the tool ONCE for EACH domain ({len(domain_names)} domains total: {domain_names}). "
        f"After calling the tool for all domains, simply confirm that all domains have been saved."
    )
    expected_output = (
        f"Use the 'write_result_to_json' tool to save the class list for each of the {len(domain_names)} domains. "
        f"After saving all domains, confirm completion with a brief summary of how many domains and classes were saved."
    )
    return _build("common", description, expected_output, number, num, context)


def review_prompts(common_result_json: dict, remaining_classes: list, domain_clusters: dict, number, num,
                   context: str | None = None) -> Prompt:
    """Etapa 5 (main.py 399-465).
    `context`: respuesta final (texto) del Common Class Agent. En el original llega siempre, por
    `context=[self.common_class_task()]` de crew.py."""
    original_microservice_description = tasks_config()["review_task"]["description"]
    review_domain_names = list(common_result_json.keys()) if common_result_json else list(domain_clusters.keys())
    description = (
        f"You have been provided with the domain clusters with assigned common classes: {common_result_json}. "
        f"This contains the domain assignments for classes after identifying common classes.\n\n"
        f"Additionally, there are {len(remaining_classes)} classes that haven't been assigned to any domain yet: {remaining_classes}.\n\n"
        f"{original_microservice_description}\n\n"
        f"IMPORTANT: To avoid output token limit issues, you MUST use the 'write_result_to_json' tool to save results. "
        f"Call the tool ONCE for EACH domain ({len(review_domain_names)} domains total: {review_domain_names}). "
        f"After calling the tool for all domains, simply confirm that all domains have been saved."
    )
    expected_output = (
        f"Use the 'write_result_to_json' tool to save the final class list for each of the {len(review_domain_names)} domains. "
        f"After saving all domains, confirm completion with a brief summary of how many domains and classes were saved."
    )
    return _build("review", description, expected_output, number, num, context)


# --------------------------------------------------------------------------------------------------
# Registro del prompt exacto (INSTRUCCIONES §6: output/<app>/<run_id>/logs/<etapa>_prompt.txt)
# --------------------------------------------------------------------------------------------------
def save_prompt(logs_dir: str, etapa: str, prompt: Prompt) -> tuple:
    """Guarda sin alterar ni un caracter (UTF-8, sin traduccion de saltos de linea):
       <etapa>_prompt.txt         mensaje de usuario
       <etapa>_system_prompt.txt  system prompt"""
    os.makedirs(logs_dir, exist_ok=True)
    paths = (os.path.join(logs_dir, f"{etapa}_prompt.txt"), os.path.join(logs_dir, f"{etapa}_system_prompt.txt"))
    for path, text in zip(paths, (prompt.user, prompt.system)):
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    return paths


def main() -> None:
    ap = argparse.ArgumentParser(description="Vista previa de los prompts que no dependen de la corrida.")
    ap.add_argument("--app", choices=sorted(APPS), required=True)
    ap.add_argument("--number", help="por defecto, el de la aplicacion")
    ap.add_argument("--num", help="por defecto, el de la aplicacion")
    ap.add_argument("--out", required=True, help="carpeta de salida")
    args = ap.parse_args()
    number, num = args.number or APPS[args.app][0], args.num or APPS[args.app][1]
    domain = domain_prompts(number, num)
    save_prompt(args.out, "1_domain", domain)
    for stage, agent in STAGE_AGENT.items():
        path = os.path.join(args.out, f"system_{agent}.txt")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(system_prompt(agent, number, num))
    print(f"{args.app} (number={number}, num={num}): 5 system prompts y el prompt de la Etapa 1 en {args.out}")
    print("Los prompts de las etapas 2 a 5 dependen de las salidas de la corrida (los arma el orquestador).")


if __name__ == "__main__":
    main()
