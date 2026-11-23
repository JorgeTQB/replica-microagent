"""Conciliacion del universo de clases de PartsUnlimitedMRP (INSTRUCCIONES §4.3 paso 5).
Compara: claves del grafo, archivos .java de la raiz analizada y la referencia de los autores.
Uso: python scripts/reconcile_partsunlimited.py"""
import collections
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = "resources/partsunlimited/src/Backend/OrderService/src/main/java"

dep = json.load(open(os.path.join(BASE, "context/partsunlimited/class_info_dependency.json"), encoding="utf-8"))
ref = json.load(open(os.path.join(BASE, "..", "MicroAgent", "decomposition", "partsunlimited.json"), encoding="utf-8"))

parts = {c for k, v in ref.items() if k != "uncounted" for c in v}
unc = set(ref["uncounted"])
print(f"universo (grafo): {len(dep)} | particiones: {len(parts)} | uncounted distintas: {len(unc)} "
      f"(lista de {len(ref['uncounted'])}) | union referencia: {len(parts | unc)}")
print("universo - referencia:", sorted(set(dep) - parts - unc))
print("referencia - universo:", sorted((parts | unc) - set(dep)))
print("particiones ∩ uncounted:", sorted(parts & unc))

cnt = collections.Counter(c for k, v in ref.items() if k != "uncounted" for c in v)
common = sorted(c for c, n in cnt.items() if n > 1)
print(f"clases en >1 particion (comunes): {len(common)}")
for c in common:
    print(f"   {c}  (en {cnt[c]} particiones)")

files = []
for d, _, fs in os.walk(os.path.join(BASE, ROOT)):
    for f in fs:
        if f.endswith(".java"):
            rel = os.path.relpath(os.path.join(d, f), os.path.join(BASE, ROOT)).replace(os.sep, "/")
            files.append(rel)
fq = {f[:-5].replace("/", ".") for f in files}
print(f"archivos .java en la raiz: {len(files)} | FQCN por ruta == claves del grafo: {fq == set(dep)}")
print("solo por ruta:", sorted(fq - set(dep)), "| solo en grafo:", sorted(set(dep) - fq))

iso = sorted(k for k, v in dep.items() if not v.get("relationships"))
print(f"clases sin relaciones ({len(iso)}):", iso)
print("tipos de relacion presentes:", sorted({t for v in dep.values() for t in v.get("relationships", {})}))
targets = {t for v in dep.values() for rel in v.get("relationships", {}).values() for t in rel}
print("destinos de relaciones fuera del universo:", sorted(targets - set(dep)))
