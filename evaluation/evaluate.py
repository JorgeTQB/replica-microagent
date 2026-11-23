"""Fase 6: evaluacion de las descomposiciones y de las 5 repeticiones de la Etapa 4 con los scripts originales
(INSTRUCCIONES §9; DECISIONES D49-D56, D58, D60). Tabla principal: 13 corridas de MicroAgent y 6 de la linea base,
todas con Claude Code 2.1.330; aparte, las 6 corridas de MicroAgent hechas con 2.1.327.

- Importa, sin modificarlos, MicroAgent/metrics/json_similarity.py (evaluate_similarity) y
  MicroAgent/metrics/common_metrics.py (calculate_metrics). No usa sus __main__ (tienen rutas fijas).
  json_similarity no imprime ni escribe; calculate_metrics imprime los FP/FN por stdout: se capturan y se guardan
  en evaluation/raw/. Ninguno de los dos escribe archivos al importarse o al llamarse.
- Correspondencia con el paper:
    WS      = f1.metrics_m2.weighted_average
    c2c@X   = f1.metrics_m2.above_X  (X = 0.5, 0.75, 0.9). El script usa ">" (el paper dice ">="); se reporta tal cual.
    F1 de clases comunes = calculate_metrics(...)["service_level"] (el paper dice "a nivel de servicio"); se
    reportan micro y macro porque el paper no aclara cual uso. El nivel por clase (utility_level) queda en raw/.
- Control de cordura: cada referencia evaluada contra si misma debe dar 1,0 en todo (se guarda en
  evaluation/sanity_check.json). Para calculate_metrics la referencia se pasa sin la clave "uncounted", porque
  esa clave no es un servicio (json_similarity la ignora; calculate_metrics la trataria como uno mas).
- Control contra los valores calculados a mano en D43, D44 y D48: si no coinciden, aborta sin escribir results.csv.

Salidas: evaluation/results.csv, evaluation/results_e4_repeticiones.csv, evaluation/sanity_check.json,
         evaluation/raw/<app>/<run_id>.json (+ _common_metrics_stdout.txt), evaluation/error_analysis.{json,md}.
Uso: python -B -X utf8 evaluation/evaluate.py
"""
import contextlib
import csv
import datetime
import io
import json
import math
import os
import statistics
import sys

sys.dont_write_bytecode = True  # no dejar __pycache__ en MicroAgent/metrics (ademas se corre con -B)

EVAL = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(EVAL)  # replica-claude-code
ROOT = os.path.dirname(BASE)
METRICS = os.path.join(ROOT, "MicroAgent", "metrics")
sys.path.insert(0, METRICS)
from json_similarity import evaluate_similarity  # noqa: E402  (original, sin modificar)
from common_metrics import calculate_metrics  # noqa: E402  (original, sin modificar)

sys.path.remove(METRICS)

APPS = ["jpetstore-6", "partsunlimited"]
# Corridas completas de MicroAgent por app (D58, D60). La configuracion principal "microagent" usa solo corridas con
# Claude Code 2.1.330, la misma version que la linea base: JPetStore claude-run4..13 (n = 10, ampliado por la
# variabilidad de la Etapa 4, D57) y PartsUnlimitedMRP claude-run4..6. Las corridas claude-run1..3 de cada app, hechas
# con 2.1.327, se conservan como grupo aparte ("microagent_cc2.1.327") y no entran en la tabla principal.
MICROAGENT_RUNS = {"jpetstore-6": range(4, 14), "partsunlimited": range(4, 7)}
CONFIGS = ["microagent", "baseline", "microagent_cc2.1.327"]
# Version de Claude Code que debe tener cada corrida de cada configuracion (run_manifest.json); si no, se aborta.
EXPECTED_CC_VERSION = {"microagent": "2.1.330", "baseline": "2.1.330", "microagent_cc2.1.327": "2.1.327"}


def runs_for(app):
    return {"microagent": [f"claude-run{i}" for i in MICROAGENT_RUNS[app]],
            "baseline": ["baseline-run1", "baseline-run2", "baseline-run3"],
            "microagent_cc2.1.327": ["claude-run1", "claude-run2", "claude-run3"]}


# Filas de resumen por grupo (la mediana, el minimo y el maximo se agregaron en D58).
SUMMARY_STATS = [("media", statistics.mean), ("desv_est_muestral", statistics.stdev), ("mediana", statistics.median),
                 ("minimo", min), ("maximo", max)]
E4_RUNS = [f"claude-run1-e4-r0{i}" for i in range(1, 6)]  # repeticiones aisladas de la Etapa 4 (D41, D43)
THRESHOLDS = [("c2c50", "above_0.5"), ("c2c75", "above_0.75"), ("c2c90", "above_0.9")]

# Valores calculados a mano en DECISIONES (porcentajes redondeados a 2 decimales en D44/D48 y a 1 en D43).
EXPECTED = {
    ("jpetstore-6", "claude-run1"): {"ws": 92.7}, ("jpetstore-6", "claude-run2"): {"ws": 72.6},
    ("jpetstore-6", "claude-run3"): {"ws": 74.4},
    ("partsunlimited", "claude-run1"): {"ws": 100.00, "c2c50": 100, "c2c75": 100, "c2c90": 100},
    ("partsunlimited", "claude-run2"): {"ws": 97.40, "c2c50": 100, "c2c75": 100, "c2c90": 100},
    ("partsunlimited", "claude-run3"): {"ws": 100.00, "c2c50": 100, "c2c75": 100, "c2c90": 100},
    ("jpetstore-6", "baseline-run1"): {"ws": 84.20, "c2c50": 100, "c2c75": 100, "c2c90": 33.3},
    ("jpetstore-6", "baseline-run2"): {"ws": 84.20, "c2c50": 100, "c2c75": 100, "c2c90": 33.3},
    ("jpetstore-6", "baseline-run3"): {"ws": 84.20, "c2c50": 100, "c2c75": 100, "c2c90": 33.3},
    ("partsunlimited", "baseline-run1"): {"ws": 67.15, "c2c50": 80, "c2c75": 40, "c2c90": 0},
    ("partsunlimited", "baseline-run2"): {"ws": 66.44, "c2c50": 100, "c2c75": 40, "c2c90": 0},
    ("partsunlimited", "baseline-run3"): {"ws": 66.13, "c2c50": 80, "c2c75": 40, "c2c90": 0},
    ("jpetstore-6", "claude-run1-e4-r01"): {"ws": 92.7}, ("jpetstore-6", "claude-run1-e4-r02"): {"ws": 76.4},
    ("jpetstore-6", "claude-run1-e4-r03"): {"ws": 86.3}, ("jpetstore-6", "claude-run1-e4-r04"): {"ws": 86.3},
    ("jpetstore-6", "claude-run1-e4-r05"): {"ws": 92.7},
}

COLUMNS = [
    "app", "configuracion", "run_id", "fila",
    "ws", "c2c50", "c2c75", "c2c90",
    "common_p_micro", "common_r_micro", "common_f1_micro",
    "common_p_macro", "common_r_macro", "common_f1_macro",
    "particiones", "clases_asignadas", "clases_sin_asignar", "clases_fuera_del_universo",
    "llamadas_claude", "turnos_num_turns", "llamadas_a_herramientas", "peticiones_api",
    "duracion_llamadas_s", "duracion_api_s", "duracion_reloj_s",
    "tokens_input", "tokens_output", "tokens_cache_creation", "tokens_cache_read", "tokens_total",
    "costo_nominal_usd", "modelo", "claude_code_version", "archivo_evaluado",
]
NUMERIC = COLUMNS[4:31]


def rel(path):
    return os.path.relpath(path, BASE).replace(os.sep, "/")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def jsonable(obj):
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [jsonable(v) for v in obj]
    return obj


def common(common_dict, services):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = calculate_metrics(common_dict, services)
    return res, buf.getvalue()


def ref_paths(app):
    return os.path.join(EVAL, "references", f"{app}.json"), os.path.join(EVAL, "common_dicts", f"{app}.json")


def sanity_check():
    out, ok = {}, True
    for app in APPS:
        ref_path, cd_path = ref_paths(app)
        sim = evaluate_similarity(ref_path, ref_path)
        ref = load(ref_path)
        services = {k: v for k, v in ref.items() if k != "uncounted"}
        cm, stdout = common(load(cd_path), services)
        vals = {f"f1.metrics_m2.{k}": v for k, v in sim["f1"]["metrics_m2"].items()}
        vals.update({f"f1.metrics_m1.{k}": v for k, v in sim["f1"]["metrics_m1"].items()})
        for lvl in ("service_level", "utility_level"):
            for kind in ("micro", "macro"):
                for m, v in cm[lvl][kind].items():
                    vals[f"common.{lvl}.{kind}.{m}"] = v
        bad = {k: v for k, v in vals.items() if not math.isclose(v, 1.0)}
        ok &= not bad
        out[app] = {"referencia": rel(ref_path), "common_dict": rel(cd_path), "valores": vals,
                    "distintos_de_1": bad, "fp_fn_impresos": [l for l in stdout.splitlines() if l.startswith("False")]}
    return ok, out


def stats_of(services, universe):
    assigned = {c for k, v in services.items() if k != "uncounted" for c in v}
    return {"particiones": len([k for k in services if k != "uncounted"]),
            "clases_asignadas": len(assigned & universe),
            "clases_sin_asignar": len(universe - assigned),
            "clases_fuera_del_universo": len(assigned - universe)}


def run_costs(run_dir, notes):
    st = load(os.path.join(run_dir, "logs", "run_status.json"))
    man = load(os.path.join(run_dir, "logs", "run_manifest.json"))
    tot, etapas = st["totales"], st["etapas"]
    # Comprobaciones de coherencia: los totales son la suma de las llamadas, y num_turns = herramientas + 1 por llamada.
    for key in ("turnos", "peticiones_api", "llamadas_a_herramientas", "duracion_ms", "duracion_api_ms"):
        s = sum(e[key] for e in etapas)
        if s != tot[key]:
            notes.append(f"{rel(run_dir)}: totales.{key}={tot[key]} != suma de etapas={s}")
    if not math.isclose(sum(e["costo_usd"] for e in etapas), tot["costo_usd"], rel_tol=1e-9):
        notes.append(f"{rel(run_dir)}: totales.costo_usd distinto de la suma de etapas")
    for e in etapas:
        if e["turnos"] != e["llamadas_a_herramientas"] + 1:
            notes.append(f"{rel(run_dir)} {e['etapa']}: num_turns={e['turnos']} != herramientas+1="
                         f"{e['llamadas_a_herramientas'] + 1} (subtype={e.get('subtype')})")
    if len(etapas) != tot["llamadas"]:
        notes.append(f"{rel(run_dir)}: totales.llamadas={tot['llamadas']} != {len(etapas)} etapas")
    t0 = datetime.datetime.fromisoformat(st["inicio"])
    t1 = datetime.datetime.fromisoformat(st["fin"])
    tk = tot["tokens"]
    return st, {
        "llamadas_claude": tot["llamadas"], "turnos_num_turns": tot["turnos"],
        "llamadas_a_herramientas": tot["llamadas_a_herramientas"], "peticiones_api": tot["peticiones_api"],
        "duracion_llamadas_s": tot["duracion_ms"] / 1000, "duracion_api_s": tot["duracion_api_ms"] / 1000,
        "duracion_reloj_s": (t1 - t0).total_seconds(),
        "tokens_input": tk["input_tokens"], "tokens_output": tk["output_tokens"],
        "tokens_cache_creation": tk["cache_creation_input_tokens"], "tokens_cache_read": tk["cache_read_input_tokens"],
        "tokens_total": sum(tk[k] for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                            "cache_read_input_tokens")),
        "costo_nominal_usd": tot["costo_usd"], "modelo": st["modelo"],
        "claude_code_version": man["claude_code_version"].replace(" (Claude Code)", ""),
    }


def error_analysis(sim, ref, target):
    """Clases mal asignadas frente a la referencia.

    Cada servicio producido se asocia a su particion de referencia mas parecida (p2r, metodo 2: el best_match que
    usa el WS). Para cada clase contada (no 'uncounted'), se compara el conjunto de particiones de referencia que la
    contienen con el de particiones asociadas a los servicios que la contienen:
      de_mas  = esta en un servicio cuya particion asociada no la contiene en la referencia;
      falta   = la referencia la pone en una particion y ningun servicio asociado a ella la contiene.
    """
    uncounted = set(ref.get("uncounted", []))
    mapping = {s: r["best_match"] for s, r in sim["p2r"]["results_m2"].items()}
    r2p = {r: v["best_match"] for r, v in sim["r2p"]["results_m2"].items()}
    ref_parts = {k: set(v) for k, v in ref.items() if k != "uncounted"}
    tgt = {k: set(v) for k, v in target.items() if k != "uncounted"}
    classes = sorted({c for v in ref_parts.values() for c in v} | {c for v in tgt.values() for c in v})
    errors = []
    for c in classes:
        if c in uncounted:
            continue
        in_ref = {r for r, v in ref_parts.items() if c in v}
        in_tgt = {s for s, v in tgt.items() if c in v}
        mapped = {mapping[s] for s in in_tgt if mapping.get(s)}
        extra = sorted(s for s in in_tgt if mapping.get(s) not in in_ref)
        missing = sorted(in_ref - mapped)
        if extra or missing or (not in_ref):
            errors.append({
                "clase": c,
                "referencia": sorted(in_ref) if in_ref else "no esta en la referencia",
                "servicios_producidos": [f"{s} (~{mapping.get(s)})" for s in sorted(in_tgt)],
                "de_mas_en": [f"{s} (~{mapping.get(s)})" for s in extra],
                "falta_en_particion_de_referencia": missing,
            })
    collisions = {}
    for s, r in mapping.items():
        collisions.setdefault(r, []).append(s)
    uncounted_where = {c: sorted(s for s, v in tgt.items() if c in v) for c in sorted(uncounted)}
    return {
        "asociacion_servicio_a_referencia_p2r": {s: {"particion": r, "similitud":
                                                     round(sim["p2r"]["results_m2"][s]["similarity"], 4)}
                                                for s, r in mapping.items()},
        "asociacion_referencia_a_servicio_r2p": {r: {"servicio": s, "similitud":
                                                     round(sim["r2p"]["results_m2"][r]["similarity"], 4)}
                                                for r, s in r2p.items()},
        "particiones_de_referencia_con_varios_servicios": {r: ss for r, ss in collisions.items() if len(ss) > 1},
        "particiones_de_referencia_sin_servicio_asociado": sorted(set(ref_parts) - set(mapping.values())),
        "clases_mal_asignadas": errors,
        "clases_uncounted_donde_quedaron": uncounted_where,
    }


def evaluate_run(app, run_id, file_name, configuracion, fila, universe, notes, raw_dir):
    ref_path, cd_path = ref_paths(app)
    run_dir = os.path.join(BASE, "output", app, run_id)
    target_path = os.path.join(run_dir, file_name)
    sim = evaluate_similarity(ref_path, target_path)
    target = load(target_path)
    # Igual que json_similarity, la clave "uncounted" no es un servicio (hallazgo 1 del revisor, D55). Ninguna de las
    # 24 descomposiciones (19 corridas y 5 repeticiones de la Etapa 4) la trae; si apareciera, queda anotado.
    if "uncounted" in target:
        notes.append(f"{app}/{run_id}: el objetivo trae una clave 'uncounted'; no se cuenta como servicio")
    cm, stdout = common(load(cd_path), {k: v for k, v in target.items() if k != "uncounted"})
    f1 = sim["f1"]["metrics_m2"]
    row = {"app": app, "configuracion": configuracion, "run_id": run_id, "fila": fila,
           "ws": f1["weighted_average"] * 100,
           **{col: float(f1[key]) * 100 for col, key in THRESHOLDS}}  # calculate_f1 devuelve int 0 si ambos son 0
    for kind in ("micro", "macro"):
        for m, short in (("precision", "p"), ("recall", "r"), ("f1", "f1")):
            row[f"common_{short}_{kind}"] = cm["service_level"][kind][m] * 100
    row.update(stats_of(target, universe))
    st, costs = run_costs(run_dir, notes)
    row.update(costs)
    row["archivo_evaluado"] = rel(target_path)
    # Coherencia con run_status.json.resultado
    res = st.get("resultado") or {}
    if res and file_name == "result.json":
        if res.get("particiones") != row["particiones"] or len(res.get("clases_sin_asignar", [])) != row["clases_sin_asignar"]:
            notes.append(f"{app}/{run_id}: estadisticas distintas de run_status.json.resultado")
    # Control contra D43/D44/D48
    for key, val in EXPECTED.get((app, run_id), {}).items():
        digits = 1 if (app == "jpetstore-6" and run_id.startswith("claude-run")) or key.startswith("c2c") else 2
        if round(row[key], digits) != round(val, digits):
            raise SystemExit(f"DISCREPANCIA con DECISIONES: {app}/{run_id} {key} = {row[key]:.4f}, se esperaba {val}")
    os.makedirs(raw_dir, exist_ok=True)
    with open(os.path.join(raw_dir, f"{run_id}.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(jsonable({"referencia": rel(ref_path), "common_dict": rel(cd_path), "objetivo": rel(target_path),
                            "evaluate_similarity": sim, "calculate_metrics": cm}), fh, indent=2)
    with open(os.path.join(raw_dir, f"{run_id}_common_metrics_stdout.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(stdout)
    return row, error_analysis(sim, load(ref_path), target)


def summary_rows(rows):
    out = []
    for app in APPS:
        for conf in CONFIGS:
            grp = [r for r in rows if r["app"] == app and r["configuracion"] == conf]
            for fila, fn in SUMMARY_STATS:
                r = {"app": app, "configuracion": conf, "run_id": f"n={len(grp)}", "fila": fila}
                for c in NUMERIC:
                    r[c] = fn([g[c] for g in grp])
                r["modelo"] = ";".join(sorted({g["modelo"] for g in grp}))
                r["claude_code_version"] = ";".join(sorted({g["claude_code_version"] for g in grp}))
                r["archivo_evaluado"] = ""
                out.append(r)
    return out


def fmt(v):
    if isinstance(v, float):
        return f"{v:.4f}"
    return v


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: fmt(r.get(k, "")) for k in COLUMNS})


def write_error_md(path, analysis):
    lines = ["# Analisis de errores por corrida (Fase 6)", "",
             "Generado por `evaluation/evaluate.py`. Cada servicio producido se asocia a la particion de la referencia",
             "con mayor similitud (direccion P→R, metodo 2, la misma que usa el WS). Una clase esta **de más** en un",
             "servicio si la particion asociada no la contiene en la referencia, y **falta** en una particion de",
             "referencia si ningun servicio asociado a ella la contiene. Las clases `uncounted` no cuentan como error",
             "(el WS las excluye); se indica donde quedaron.", ""]
    for key, a in analysis.items():
        app, run_id = key.split("/")
        lines += [f"## {app} / {run_id}", "", "| Servicio producido | ≈ Particion de referencia | Similitud |", "|---|---|---|"]
        for s, m in a["asociacion_servicio_a_referencia_p2r"].items():
            lines.append(f"| {s} | {m['particion']} | {m['similitud']:.3f} |")
        if a["particiones_de_referencia_con_varios_servicios"]:
            lines.append(f"\nParticiones con varios servicios asociados: {a['particiones_de_referencia_con_varios_servicios']}")
        if a["particiones_de_referencia_sin_servicio_asociado"]:
            lines.append(f"\nParticiones de referencia sin servicio asociado: {a['particiones_de_referencia_sin_servicio_asociado']}")
        lines.append("")
        if not a["clases_mal_asignadas"]:
            lines += ["Sin clases mal asignadas.", ""]
        else:
            lines += ["| Clase | En la referencia | De más en | Falta en (referencia) |", "|---|---|---|---|"]
            for e in a["clases_mal_asignadas"]:
                refp = e["referencia"] if isinstance(e["referencia"], str) else ", ".join(e["referencia"])
                lines.append(f"| `{e['clase'].split('.')[-1]}` | {refp} | {', '.join(e['de_mas_en']) or '—'} | "
                             f"{', '.join(e['falta_en_particion_de_referencia']) or '—'} |")
            lines.append("")
        unc = {c.split(".")[-1]: len(v) for c, v in a["clases_uncounted_donde_quedaron"].items()}
        if unc:
            lines += [f"Clases `uncounted` (nº de servicios donde quedaron): {unc}", ""]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))


def main():
    ok, sanity = sanity_check()
    with open(os.path.join(EVAL, "sanity_check.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"resultado": "OK" if ok else "FALLA", "apps": sanity}, fh, indent=2)
    print("Control de cordura (referencia contra si misma = 1,0):", "OK" if ok else "FALLA")
    if not ok:
        print(json.dumps({a: s["distintos_de_1"] for a, s in sanity.items()}, indent=2))
        sys.exit(1)

    notes, rows, rows_e4, analysis = [], [], [], {}
    for app in APPS:
        universe = set(load(os.path.join(BASE, "context", app, "class_summaries.json")))
        raw_dir = os.path.join(EVAL, "raw", app)
        for conf, runs in runs_for(app).items():
            for run_id in runs:
                row, err = evaluate_run(app, run_id, "result.json", conf, "corrida", universe, notes, raw_dir)
                if row["claude_code_version"] != EXPECTED_CC_VERSION[conf]:
                    raise SystemExit(f"{app}/{run_id}: Claude Code {row['claude_code_version']}, se esperaba "
                                     f"{EXPECTED_CC_VERSION[conf]} en la configuracion {conf} (D60)")
                rows.append(row)
                analysis[f"{app}/{run_id}"] = err
        if app == "jpetstore-6":
            for run_id in E4_RUNS:
                row, err = evaluate_run(app, run_id, "common_result.json", "microagent_solo_etapa4",
                                        "repeticion_etapa4", universe, notes, raw_dir)
                rows_e4.append(row)
                analysis[f"{app}/{run_id}"] = err
    print("Valores de D43, D44 y D48: coinciden.")

    write_csv(os.path.join(EVAL, "results.csv"), rows + summary_rows(rows))
    write_csv(os.path.join(EVAL, "results_e4_repeticiones.csv"), rows_e4)
    with open(os.path.join(EVAL, "error_analysis.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(analysis, fh, indent=2, ensure_ascii=False)
    write_error_md(os.path.join(EVAL, "error_analysis.md"), analysis)
    print("Notas de coherencia:", "ninguna" if not notes else "")
    for n in notes:
        print("  -", n)
    with open(os.path.join(EVAL, "raw", "notas_de_coherencia.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(notes) + ("\n" if notes else ""))
    print("\n{:<15} {:<11} {:>4} {:>14} {:>8} {:>15} {:>8} {:>8} {:>8} {:>9} {:>9}".format(
        "app", "config", "n", "WS", "mediana", "min-max", "c2c50", "c2c75", "c2c90", "F1 micro", "F1 macro"))
    s = summary_rows(rows)
    k = len(SUMMARY_STATS)
    for grp in (s[i:i + k] for i in range(0, len(s), k)):
        g = {r["fila"]: r for r in grp}
        m, d = g["media"], g["desv_est_muestral"]
        print("{:<15} {:<11} {:>4} {:>6.2f} ± {:<5.2f} {:>8.2f} {:>7.2f}-{:<7.2f} {:>8.1f} {:>8.1f} {:>8.1f} {:>9.1f} {:>9.1f}".format(
            m["app"], m["configuracion"], m["run_id"][2:], m["ws"], d["ws"], g["mediana"]["ws"], g["minimo"]["ws"],
            g["maximo"]["ws"], m["c2c50"], m["c2c75"], m["c2c90"], m["common_f1_micro"], m["common_f1_macro"]))


if __name__ == "__main__":
    main()
