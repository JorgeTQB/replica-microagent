"""Audita las llamadas `claude -p` de preparacion de contexto de una app (DECISIONES.md D3, D4, D16).

Para cada JSON de logs/<app>_context/summaries/ y logs/<app>_context/database/ comprueba: modelo pedido y
modelo usado, 1 turno, sin error, variable MAX_THINKING_TOKENS=0 registrada. Ademas busca la transcripcion de
Claude Code de esa sesion (carpeta ~/.claude/projects/*sandbox*) y cuenta los bloques `thinking` y los modelos
que respondio la API. No imprime el contenido de las transcripciones.

Uso: python scripts/check_context_calls.py <app> [--model claude-sonnet-4-6]
"""
import argparse
import collections
import glob
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_transcripts():
    root = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    out = {}
    for d in glob.glob(os.path.join(root, "*sandbox*")):
        for p in glob.glob(os.path.join(d, "*.jsonl")):
            out[os.path.splitext(os.path.basename(p))[0]] = p
    return out


def scan_transcript(path):
    thinking, models = 0, collections.Counter()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = ev.get("message") if isinstance(ev, dict) else None
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            if msg.get("model"):
                models[msg["model"]] += 1
            content = msg.get("content")
            if isinstance(content, list):
                thinking += sum(1 for b in content if isinstance(b, dict) and b.get("type") in ("thinking", "redacted_thinking"))
    return thinking, models


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("app")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(BASE, "logs", f"{a.app}_context", "summaries", "*.json")))
    files += sorted(glob.glob(os.path.join(BASE, "logs", f"{a.app}_context", "database", "*.json")))
    transcripts = find_transcripts()
    problems, cost, api_models = [], 0.0, collections.Counter()
    with_transcript = thinking_total = 0
    for p in files:
        name = os.path.basename(p)
        d = json.load(open(p, encoding="utf-8"))
        cmd = d.get("_cmd", [])
        asked = cmd[cmd.index("--model") + 1] if "--model" in cmd else None
        used = list(d.get("modelUsage", {}))
        if asked != a.model:
            problems.append(f"{name}: modelo pedido {asked}")
        if used != [a.model]:
            problems.append(f"{name}: modelUsage {used}")
        if d.get("num_turns") != 1:
            problems.append(f"{name}: turnos {d.get('num_turns')}")
        if d.get("is_error") or d.get("subtype") != "success":
            problems.append(f"{name}: is_error={d.get('is_error')} subtype={d.get('subtype')}")
        if d.get("_env") != {"MAX_THINKING_TOKENS": "0"}:
            problems.append(f"{name}: _env {d.get('_env')}")
        tt = (d.get("usage", {}).get("output_tokens_details") or {}).get("thinking_tokens")
        if tt != 0:
            problems.append(f"{name}: usage.output_tokens_details.thinking_tokens = {tt!r}")
        if "--tools" not in cmd or cmd[cmd.index("--tools") + 1] != "":
            problems.append(f"{name}: la llamada no lleva --tools \"\"")
        cost += d.get("total_cost_usd") or 0
        t = transcripts.get(d.get("session_id"))
        if not t:
            problems.append(f"{name}: sin transcripcion para la sesion {d.get('session_id')}")
            continue
        with_transcript += 1
        n, models = scan_transcript(t)
        thinking_total += n
        api_models.update(models)
        if n:
            problems.append(f"{name}: {n} bloques thinking en la transcripcion")
        if set(models) != {a.model}:
            problems.append(f"{name}: modelos en la transcripcion {dict(models)}")

    print(f"llamadas auditadas: {len(files)} | con transcripcion: {with_transcript}")
    print(f"bloques thinking en transcripciones: {thinking_total}")
    print(f"modelos que respondio la API (mensajes): {dict(api_models)}")
    print(f"costo nominal total (total_cost_usd): {cost:.4f}")
    failed = glob.glob(os.path.join(BASE, "logs", f"{a.app}_context", "summaries", "*.failed"))
    print(f"registros .failed conservados: {len(failed)}")
    for pr in problems:
        print("  PROBLEMA:", pr)
    print("RESULTADO:", "OK" if not problems else "FALLA")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
