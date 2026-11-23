"""Genera database/<app>/<nombre>-summary.json con el "Database Summary Prompt" literal del artefacto
(MicroAgent/prompt/context_preparation_prompt.md) (INSTRUCCIONES §4.3 paso 4).

Uso: python scripts/gen_db_summary.py --app partsunlimited \
        --sql resources/partsunlimited/src/Backend/OrderService/scripts/schema.psql --out-name sql-summary.json

El archivo de salida imita la envoltura del sql-summary.json publicado para JPetStore:
    {"schema": {"schema_summary": {...}, "file_path": "<ruta del SQL>"}}
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from claude_cli import BASE, MODEL, call_claude, extract_fenced_prompt, parse_json_text  # noqa: E402

PROMPT_MD = os.path.join(BASE, "..", "MicroAgent", "prompt", "context_preparation_prompt.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True)
    ap.add_argument("--sql", required=True, help="ruta relativa a replica-claude-code/")
    ap.add_argument("--out-name", default="sql-summary.json")
    ap.add_argument("--model", default=MODEL)
    a = ap.parse_args()
    assert a.out_name.endswith("-summary.json"), "la herramienta get_database_summary busca *-summary.json"

    sql_rel = a.sql.replace("\\", "/")
    template = extract_fenced_prompt(PROMPT_MD, "Database Summary Prompt")
    assert template.count("{sql_content}") == 1
    sql = open(os.path.join(BASE, sql_rel), encoding="utf-8").read()  # estricta: sin reemplazos silenciosos
    # Este prompt no usa escapes {{ }}: solo se sustituye {sql_content}.
    prompt = template.replace("{sql_content}", sql)

    log_dir = os.path.join(BASE, "logs", f"{a.app}_context", "database")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "db_summary.prompt.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(prompt)
    data = call_claude(prompt, model=a.model)
    with open(os.path.join(log_dir, "db_summary.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if data.get("is_error") or data.get("subtype") != "success":
        sys.exit(f"llamada fallida: subtype={data.get('subtype')} result={str(data.get('result'))[:300]}")
    parsed = parse_json_text(data["result"])
    assert "schema_summary" in parsed and {"tables", "relationships"} <= set(parsed["schema_summary"]), list(parsed)

    out = os.path.join(BASE, "database", a.app, a.out_name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"schema": {"schema_summary": parsed["schema_summary"], "file_path": sql_rel}}, f, indent=2, ensure_ascii=False)
    ss = parsed["schema_summary"]
    print(f"{out}: tables={len(ss['tables'])} relationships={len(ss['relationships'])} "
          f"modelos={list(data.get('modelUsage', {}))} turnos={data.get('num_turns')}")
    extra = sorted(set(parsed) - {"schema_summary"})
    if extra:
        print("AVISO: claves adicionales en la respuesta, no guardadas:", extra)


if __name__ == "__main__":
    main()
