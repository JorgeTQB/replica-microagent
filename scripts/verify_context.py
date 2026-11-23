"""Verificacion del contexto de una app (INSTRUCCIONES §4.2 paso 3 y §4.3 pasos 3 y 5).
Uso: python scripts/verify_context.py <app> [--reference <decomposition.json>]"""
import argparse, glob, json, os, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser()
ap.add_argument("app")
ap.add_argument("--reference")
a = ap.parse_args()

dep = json.load(open(os.path.join(BASE, "context", a.app, "class_info_dependency.json"), encoding="utf-8"))
summ = json.load(open(os.path.join(BASE, "context", a.app, "class_summaries.json"), encoding="utf-8"))
ok = True
kd, ks = set(dep), set(summ)
print(f"[{a.app}] clases en class_info_dependency.json: {len(kd)} | en class_summaries.json: {len(ks)}")
if kd != ks:
    ok = False
    print("  ERROR claves distintas. Solo en grafo:", sorted(kd - ks), "| solo en resumenes:", sorted(ks - kd))
else:
    print("  OK mismas claves en ambos JSON")
missing, badfmt, mismatch, empty = [], [], [], []
for k, v in summ.items():
    fp = v.get("file_path", "")
    if not fp.startswith(f"resources/{a.app}/") or "\\" in fp:
        badfmt.append((k, fp))
    if not os.path.isfile(os.path.join(BASE, fp)):
        missing.append((k, fp))
    elif not fp.endswith("/" + k.replace(".", "/") + ".java"):
        mismatch.append((k, fp))
    if not str(v.get("summary", "")).strip():
        empty.append(k)
for name, lst in (("file_path inexistente en el clon", missing), ("file_path con formato incorrecto", badfmt),
                  ("file_path que no corresponde al FQCN (clase secundaria del archivo?)", mismatch), ("summary vacio", empty)):
    print(f"  {'OK' if not lst else 'AVISO' if 'FQCN' in name else 'ERROR'} {name}: {len(lst)}", *[f"\n     {x}" for x in lst])
    if lst and "FQCN" not in name:
        ok = False
dbs = glob.glob(os.path.join(BASE, "database", a.app, "*-summary.json"))
print(f"  {'OK' if dbs else 'ERROR'} resumen de BD (*-summary.json): {[os.path.basename(d) for d in dbs]}")
ok = ok and bool(dbs)
for d in dbs:
    js = json.load(open(d, encoding="utf-8"))
    # Envoltura del artefacto: {"schema": {"schema_summary": {...}, "file_path": "..."}}
    ss = js.get("schema", js).get("schema_summary", {})
    if not ss.get("tables"):
        ok = False
    print(f"     {os.path.basename(d)}: tables={len(ss.get('tables', []))} relationships={len(ss.get('relationships', []))}")
if a.reference:
    ref = json.load(open(a.reference, encoding="utf-8"))
    parts = {c for k, v in ref.items() if k != "uncounted" for c in v}
    unc = set(ref.get("uncounted", []))
    print(f"  referencia: {len(parts)} clases distintas en particiones, {len(unc)} distintas en uncounted "
          f"(lista uncounted con {len(ref.get('uncounted', []))} elementos), union={len(parts | unc)}, interseccion={sorted(parts & unc)}")
    print(f"  universo - referencia: {sorted(kd - parts - unc)}")
    print(f"  referencia - universo: {sorted((parts | unc) - kd)}")
print("RESULTADO:", "OK" if ok else "FALLA")
sys.exit(0 if ok else 1)
