"""Prueba de humo de las 14 herramientas del servidor MCP "microagent" con JPetStore (INSTRUCCIONES §5.2).

Lanza tools/mcp_server.py por stdio, igual que lo hara `claude -p`, y para cada herramienta:
  1. compara nombre, descripcion y argumentos publicados por MCP con los de la clase original;
  2. la invoca por MCP y compara la salida con la de llamar a `_run` directamente en este proceso;
  3. guarda la salida completa en logs/tool_smoke_test.txt.
Ademas prueba la fusion de write_result_to_json entre dos procesos del servidor.

La particion usada para las herramientas que leen output/<app>/<run_id>/domains/ es artificial (un dominio
por paquete Java); no es la descomposicion de referencia ni el resultado de ningun agente.

Uso: python -X utf8 scripts/smoke_test_tools.py
"""
import asyncio
import json
import os
import shutil
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP, RUN_ID = "jpetstore-6", "smoke-test"
RUN_DIR = os.path.join(BASE, "output", APP, RUN_ID)
RESULT_FILE = os.path.join(RUN_DIR, "smoke_result.json")
SANDBOX = os.path.join(BASE, "_sandbox")
OUT_TXT = os.path.join(BASE, "logs", "tool_smoke_test.txt")

if not sys.flags.utf8_mode:
    sys.exit("ejecutar con: python -X utf8 scripts/smoke_test_tools.py")

os.environ["APP_NAME"], os.environ["RUN_ID"] = APP, RUN_ID
sys.path.insert(0, os.path.join(BASE, "tools"))
import custom_tools as ct  # noqa: E402  (referencia: las clases originales, llamadas en este proceso)

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

EXPECTED = {
    "get_all_class_hierarchy": ct.GetAllClassHierarchy,
    "get_all_class_hierarchy_complete": ct.GetAllClassHierarchyComplete,
    "get_database_summary": ct.GetDatabaseSummary,
    "get_all_class_summaries": ct.GetAllClassSummaries,
    "get_class_summary": ct.GetClassSummary,
    "get_class_basic_info": ct.GetClassBasicInfo,
    "get_class_relation_and_code": ct.GetClassRelationAndCode,
    "search_file": ct.SearchFile,
    "codebase_semantic_search": ct.CodebaseSemanticSearch,
    "get_related_class_list": ct.GetRelatedClassList,
    "rank_dependency_entropy": ct.RankDependencyEntropyAndRatio,
    "get_more_potential_common_classes": ct.GetMorePotentialCommonClasses,
    "assign_common_class_list": ct.AssignCommonClassList,
    "write_result_to_json": ct.WriteResultToJson,
}

CART = "org.mybatis.jpetstore.domain.Cart"
CALLS = [
    ("get_all_class_hierarchy", {}),
    ("get_all_class_hierarchy_complete", {}),
    ("get_database_summary", {}),
    ("get_all_class_summaries", {}),
    ("get_class_summary", {"class_name": CART}),
    ("get_class_basic_info", {"class_name": CART}),
    ("get_class_relation_and_code", {"class_name": CART}),
    ("search_file", {"path": "resources/jpetstore-6/src/main/java/org/mybatis/jpetstore/domain/Cart.java",
                     "term": "addItem"}),
    ("codebase_semantic_search", {"query": "Manages the shopping cart and the items a customer wants to buy."}),
    ("get_related_class_list", {"class_names": [CART]}),
    ("rank_dependency_entropy", {}),
    ("get_more_potential_common_classes", {"common_classes": ["org.mybatis.jpetstore.domain.Item"]}),
    ("assign_common_class_list", {"common_class_domains": {
        "org.mybatis.jpetstore.domain.Item": {"domains": ["domain", "service"], "relationship_type": "incoming"}}}),
]


def prepare_run_dir():
    """Particion artificial por paquete para rank_dependency_entropy y codebase_semantic_search."""
    shutil.rmtree(RUN_DIR, ignore_errors=True)
    domains_dir = os.path.join(RUN_DIR, "domains")
    os.makedirs(domains_dir)
    graph = json.load(open(os.path.join(BASE, "context", APP, "class_info_dependency.json"), encoding="utf-8"))
    by_pkg = {}
    for fqcn in graph:
        pkg = fqcn.rsplit(".", 1)[0].split("org.mybatis.jpetstore.")[-1].split(".")[0]
        by_pkg.setdefault(pkg, []).append(fqcn)
    with open(os.path.join(domains_dir, "merged_domains.json"), "w", encoding="utf-8") as fh:
        json.dump({"Domain_Cluster": by_pkg}, fh, indent=2)
    with open(os.path.join(domains_dir, "domain_clusters.json"), "w", encoding="utf-8") as fh:
        json.dump({"business_domains": [{"name": k} for k in by_pkg]}, fh, indent=2)
    return by_pkg


SERVER_LOG = os.path.join(BASE, "logs", "tool_smoke_test_server.jsonl")


def server_env():
    env = dict(os.environ)
    for var in ("RESULT_FILE", "MICROAGENT_TOOLS", "MICROAGENT_LOG"):
        env.pop(var, None)
    env.update({"APP_NAME": APP, "RUN_ID": RUN_ID, "RESULT_FILE": RESULT_FILE, "MICROAGENT_LOG": SERVER_LOG})
    return env


def server_params():
    return StdioServerParameters(command=sys.executable,
                                 args=["-X", "utf8", os.path.join(BASE, "tools", "mcp_server.py")],
                                 env=server_env(), cwd=SANDBOX)


def startup_must_fail(overrides, removed=()):
    """Lanza el servidor con una configuracion invalida y devuelve (codigo de salida, ultima linea de stderr)."""
    import subprocess
    env = server_env()
    for var in removed:
        env.pop(var, None)
    env.update(overrides)
    try:
        proc = subprocess.run([sys.executable, "-X", "utf8", os.path.join(BASE, "tools", "mcp_server.py")],
                              env=env, cwd=SANDBOX, input=b"", capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        return None, "el servidor no termino (se esperaba que abortara al arrancar)"
    err = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()
    return proc.returncode, (err[-1] if err else "")


def text_of(result):
    return "".join(c.text for c in result.content if getattr(c, "type", None) == "text")


def canonical(text):
    """Forma canonica de una salida JSON: listas ordenadas. Sirve para comparar salidas de herramientas que
    construyen listas a partir de conjuntos (`set`) de Python: su orden cambia de un proceso a otro por la
    aleatorizacion del hash de cadenas, tambien en el original."""
    def norm(x):
        if isinstance(x, dict):
            return {k: norm(v) for k, v in sorted(x.items())}
        if isinstance(x, list):
            return sorted((norm(v) for v in x), key=lambda v: json.dumps(v, sort_keys=True))
        return x
    try:
        return json.dumps(norm(json.loads(text)), sort_keys=True)
    except json.JSONDecodeError:
        return None


async def main():
    problems, lines = [], []
    by_pkg = prepare_run_dir()
    os.makedirs(SANDBOX, exist_ok=True)
    if os.path.exists(SERVER_LOG):
        os.remove(SERVER_LOG)
    lines.append(f"Prueba de humo del servidor MCP 'microagent' | app={APP} run_id={RUN_ID}")
    lines.append(f"Particion artificial por paquete: { {k: len(v) for k, v in by_pkg.items()} }\n")

    async with stdio_client(server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = {t.name: t for t in (await session.list_tools()).tools}

            # 1. Nombre, descripcion y argumentos frente a las clases originales.
            lines.append("=== HERRAMIENTAS PUBLICADAS ===")
            if set(listed) != set(EXPECTED):
                problems.append(f"conjunto de herramientas distinto: {sorted(set(listed) ^ set(EXPECTED))}")
            for name, cls in EXPECTED.items():
                tool = cls()
                pub = listed.get(name)
                if pub is None:
                    continue
                if pub.description != tool.description:
                    problems.append(f"{name}: la descripcion publicada difiere de la original")
                orig = tool.args_schema.model_json_schema()
                op, pp = orig.get("properties", {}), pub.inputSchema.get("properties", {})
                if set(op) != set(pp):
                    problems.append(f"{name}: argumentos {sorted(pp)} != originales {sorted(op)}")
                for arg in op:
                    for key in ("type", "description", "items", "default"):
                        if op[arg].get(key) != pp.get(arg, {}).get(key):
                            problems.append(f"{name}.{arg}: '{key}' publicado {pp.get(arg, {}).get(key)!r} != "
                                            f"original {op[arg].get(key)!r}")
                if sorted(orig.get("required", [])) != sorted(pub.inputSchema.get("required", [])):
                    problems.append(f"{name}: 'required' {pub.inputSchema.get('required')} != {orig.get('required')}")
                lines.append(f"- {name} | args={list(pp)} | outputSchema={pub.outputSchema}")
                lines.append(f"  inputSchema={json.dumps(pub.inputSchema, ensure_ascii=False)}")

            # 2. Llamadas por MCP frente a _run directo.
            for name, args in CALLS:
                res = await session.call_tool(name, args)
                out = text_of(res)
                direct = EXPECTED[name]()._run(**args)
                if out == direct:
                    same = "si"
                elif canonical(out) is not None and canonical(out) == canonical(direct):
                    same = "si, salvo el orden de las listas (conjuntos de Python)"
                else:
                    same = "NO"
                    problems.append(f"{name}: la salida MCP difiere de _run directo")
                if res.isError:
                    problems.append(f"{name}: la llamada MCP devolvio isError")
                if out.startswith("Error") or not out.strip():
                    problems.append(f"{name}: salida vacia o de error: {out[:120]!r}")
                lines.append(f"\n=== {name}({json.dumps(args, ensure_ascii=False)}) ===")
                lines.append(f"[isError={res.isError} | igual a _run directo={same} | {len(out)} caracteres | "
                             f"structuredContent={'si' if res.structuredContent else 'no'}]")
                lines.append(out)

            # 3. write_result_to_json: archivo previo + dos llamadas en este proceso.
            with open(RESULT_FILE, "w", encoding="utf-8") as fh:
                json.dump({"Previo": ["a.B"]}, fh)
            r1 = text_of(await session.call_tool("write_result_to_json",
                                                 {"domain_name": "Uno", "class_list": [CART]}))
            r2 = text_of(await session.call_tool("write_result_to_json",
                                                 {"domain_name": "Dos", "class_list": [CART, "x.Y"]}))
            lines.append("\n=== write_result_to_json (proceso 1; el archivo ya tenia el dominio 'Previo') ===")
            lines += [r1, r2]

    # 4. Segundo proceso del servidor: debe fusionar con lo ya escrito y permitir sobrescribir un dominio.
    async with stdio_client(server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            r3 = text_of(await session.call_tool("write_result_to_json",
                                                 {"domain_name": "Tres", "class_list": ["z.W"]}))
            r4 = text_of(await session.call_tool("write_result_to_json",
                                                 {"domain_name": "Uno", "class_list": ["nuevo.Valor"]}))
            lines.append("\n=== write_result_to_json (proceso 2: fusion con el archivo existente) ===")
            lines += [r3, r4]

    final = json.load(open(RESULT_FILE, encoding="utf-8"))
    expected_final = {"Previo": ["a.B"], "Uno": ["nuevo.Valor"], "Dos": [CART, "x.Y"], "Tres": ["z.W"]}
    lines.append(f"Contenido final de RESULT_FILE: {json.dumps(final, ensure_ascii=False)}")
    if final != expected_final:
        problems.append(f"fusion de write_result_to_json incorrecta: {final}")

    # 5. RESULT_FILE inutilizable: el servidor guarda una copia antes de que _run lo sobrescriba.
    with open(RESULT_FILE, "w", encoding="utf-8") as fh:
        fh.write('{"Previo": ["a.B"], "Cortado": [')
    async with stdio_client(server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            r5 = text_of(await session.call_tool("write_result_to_json",
                                                 {"domain_name": "Cinco", "class_list": ["q.R"]}))
    after = json.load(open(RESULT_FILE, encoding="utf-8"))
    backups = [f for f in os.listdir(RUN_DIR) if f.startswith("smoke_result.json.descartado-")]
    lines.append("\n=== write_result_to_json (proceso 3: RESULT_FILE con JSON cortado) ===")
    lines += [r5, f"Contenido de RESULT_FILE: {json.dumps(after, ensure_ascii=False)}", f"Copias guardadas: {backups}"]
    if after != {"Cinco": ["q.R"]} or len(backups) != 1:
        problems.append(f"RESULT_FILE inutilizable mal tratado: {after} | copias {backups}")

    # 6. Configuraciones invalidas: el servidor debe abortar al arrancar (y no publicar nada).
    lines.append("\n=== arranques que deben abortar ===")
    for label, overrides, removed in [
        ("write_result_to_json publicada sin RESULT_FILE", {"MICROAGENT_TOOLS": "write_result_to_json"}, ("RESULT_FILE",)),
        ("RESULT_FILE relativa", {"RESULT_FILE": "rel.json"}, ()),
        ("MICROAGENT_TOOLS con un nombre desconocido", {"MICROAGENT_TOOLS": "get_class_summary,foo"}, ()),
    ]:
        code, last = startup_must_fail(overrides, removed)
        lines.append(f"{label}: exit={code} | {last}")
        if code in (0, None):
            problems.append(f"el servidor no aborto con: {label}")

    # 7. Registro del servidor (MICROAGENT_LOG): una linea por llamada recibida.
    events = [json.loads(l) for l in open(SERVER_LOG, encoding="utf-8") if l.strip()]
    n_calls = sum(1 for e in events if e.get("event") == "call")
    n_warn = sum(1 for e in events if e.get("event") == "warning")
    lines.append(f"\n=== MICROAGENT_LOG ===\nllamadas anotadas: {n_calls} | avisos: {n_warn} | "
                 f"arranques: {sum(1 for e in events if e.get('event') == 'start')}")
    if n_calls != len(CALLS) + 5 or n_warn != 1:
        problems.append(f"MICROAGENT_LOG: {n_calls} llamadas (esperadas {len(CALLS) + 5}), {n_warn} avisos (esperado 1)")

    lines.append("\n=== RESULTADO ===")
    lines += [f"PROBLEMA: {p}" for p in problems]
    lines.append("OK" if not problems else "FALLA")
    with open(OUT_TXT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"{OUT_TXT}: {len(CALLS) + 5} llamadas | problemas: {len(problems)}")
    for p in problems:
        print("  PROBLEMA:", p)
    left = os.listdir(SANDBOX)
    if left:
        print("  AVISO: _sandbox no quedo vacio:", left)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    asyncio.run(main())
