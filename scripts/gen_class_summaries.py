"""Genera context/<app>/class_summaries.json con el "Class Summary Prompt" literal del artefacto
(MicroAgent/prompt/context_preparation_prompt.md), un archivo .java por llamada (INSTRUCCIONES §4.3 paso 3).

Uso: python scripts/gen_class_summaries.py --app partsunlimited \
        --java-root resources/partsunlimited/src/Backend/OrderService/src/main/java [--workers 3] [--only FQCN ...]

Es reanudable: si logs/<app>_context/summaries/<FQCN>.json ya existe y es valido, no se vuelve a llamar.
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from claude_cli import BASE, MODEL, call_claude, extract_fenced_prompt, parse_json_text  # noqa: E402

PROMPT_MD = os.path.join(BASE, "..", "MicroAgent", "prompt", "context_preparation_prompt.md")


def build_prompt(template: str, java_code: str) -> str:
    # Escapes de formato ({{ }} -> { }) ANTES de insertar el codigo, para no alterar llaves del Java.
    t = template.replace("{{", "{").replace("}}", "}")
    assert t.count("{java_class_content}") == 1
    return t.replace("{java_class_content}", java_code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True)
    ap.add_argument("--java-root", required=True, help="ruta relativa a replica-claude-code/")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()

    java_root = a.java_root.replace("\\", "/").rstrip("/")
    assert java_root.startswith(f"resources/{a.app}/"), java_root
    graph = json.load(open(os.path.join(BASE, "context", a.app, "class_info_dependency.json"), encoding="utf-8"))
    template = extract_fenced_prompt(PROMPT_MD, "Class Summary Prompt")
    log_dir = os.path.join(BASE, "logs", f"{a.app}_context", "summaries")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "_prompt_template_literal.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(template)

    # Un archivo .java por llamada. FQCN esperado = ruta relativa a la raiz Java.
    files = []
    for d, _, fs in os.walk(os.path.join(BASE, java_root)):
        for fn in sorted(fs):
            if fn.endswith(".java"):
                rel = os.path.relpath(os.path.join(d, fn), os.path.join(BASE, java_root)).replace(os.sep, "/")
                files.append((rel[:-5].replace("/", "."), f"{java_root}/{rel}"))
    files.sort()
    if a.only:
        files = [x for x in files if x[0] in a.only]

    lock = threading.Lock()
    notes = []

    def work(item):
        fqcn, rel_path = item
        raw_path = os.path.join(log_dir, f"{fqcn}.json")
        if os.path.exists(raw_path):
            data = json.load(open(raw_path, encoding="utf-8"))
            cached = True
        else:
            # Lectura UTF-8 estricta: un byte invalido debe fallar, no reemplazarse en silencio.
            code = open(os.path.join(BASE, rel_path), encoding="utf-8").read()
            prompt = build_prompt(template, code)
            with open(os.path.join(log_dir, f"{fqcn}.prompt.txt"), "w", encoding="utf-8", newline="\n") as f:
                f.write(prompt)
            data = call_claude(prompt, model=a.model)
            cached = False
        if data.get("is_error") or data.get("subtype") != "success":
            if not cached:
                with open(raw_path + ".failed", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            raise RuntimeError(f"{fqcn}: llamada fallida subtype={data.get('subtype')} result={str(data.get('result'))[:300]}")
        parsed = parse_json_text(data["result"])  # si falla, no se guarda el log como valido
        if not cached:
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        with lock:
            print(f"  {'(cache) ' if cached else ''}{fqcn}: claves={list(parsed)} turnos={data.get('num_turns')} "
                  f"modelos={list(data.get('modelUsage', {}))}", flush=True)
        return fqcn, rel_path, parsed

    results, failures = {}, []
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(work, it): it for it in files}
        for fut in cf.as_completed(futs):
            try:
                fqcn, rel_path, parsed = fut.result()
                results[fqcn] = (rel_path, parsed)
            except Exception as e:  # no se descarta en silencio
                failures.append((futs[fut][0], str(e)))
                print(f"  FALLO {futs[fut][0]}: {e}", flush=True)

    # Union y conciliacion de claves con el grafo.
    summaries = {}
    for fqcn in sorted(results):
        rel_path, parsed = results[fqcn]
        for key, val in parsed.items():
            summary = val.get("summary") if isinstance(val, dict) else val
            model_path = val.get("file_path") if isinstance(val, dict) else None
            if key in graph:
                final_key = key
            elif len(parsed) == 1:
                final_key = fqcn
                notes.append(f"clave renombrada: el modelo devolvio '{key}' para {rel_path}; se usa '{fqcn}'")
            else:
                notes.append(f"entrada descartada (no es clase de nivel superior del grafo): '{key}' en {rel_path}")
                continue
            if final_key != fqcn:
                notes.append(f"clave '{final_key}' devuelta al resumir {rel_path} (FQCN esperado {fqcn})")
            if final_key in summaries:
                notes.append(f"clave duplicada '{final_key}' (tambien en {rel_path}); se conserva la primera")
                continue
            # file_path: el modelo no conoce la ruta (el prompt solo recibe el codigo); se fija la ruta real.
            summaries[final_key] = {"summary": summary, "file_path": rel_path}
            if model_path != rel_path:
                notes.append(f"file_path del modelo para {final_key}: {model_path!r} -> reemplazado por {rel_path!r}")

    if not a.only:
        ordered = {k: summaries[k] for k in graph if k in summaries}
        out = os.path.join(BASE, "context", a.app, "class_summaries.json")
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(ordered, f, indent=4, ensure_ascii=False)
        print(f"\n{len(ordered)} resumenes -> {out}")
        print("en grafo y sin resumen:", sorted(set(graph) - set(ordered)))
        print("con resumen y fuera del grafo:", sorted(set(summaries) - set(graph)))
    # Con --only (pruebas parciales) no se sobrescribe el registro de la corrida completa.
    conc_name = "_conciliacion_parcial.txt" if a.only else "_conciliacion.txt"
    with open(os.path.join(log_dir, conc_name), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(notes) + "\n")
        f.write("\nFALLOS:\n" + "\n".join(f"{k}: {e}" for k, e in failures) + "\n")
    print(f"notas de conciliacion: {len(notes)} (logs/{a.app}_context/summaries/{conc_name}) | fallos: {len(failures)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
