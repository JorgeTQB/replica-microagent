"""Compara dos class_info_dependency.json (control de §4.2 paso 4). Uso: compare_graph.py <autores.json> <regenerado.json>"""
import json, sys

def norm(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False)

a = json.load(open(sys.argv[1], encoding="utf-8"))
b = json.load(open(sys.argv[2], encoding="utf-8"))
# El analizador exporta {"metadata":..., "classes":{...}}; el contexto publicado es el objeto "classes" plano.
if set(a) == {"metadata", "classes"}: a = a["classes"]
if set(b) == {"metadata", "classes"}: b = b["classes"]
ka, kb = set(a), set(b)
print(f"clases A={len(ka)} B={len(kb)} | solo en A: {sorted(ka - kb)} | solo en B: {sorted(kb - ka)}")
ident, diff = [], []
for k in sorted(ka & kb):
    (ident if norm(a[k]) == norm(b[k]) else diff).append(k)
print(f"entradas identicas: {len(ident)} / {len(ka & kb)}")
for k in diff:
    fields = sorted(set(a[k]) | set(b[k]))
    bad = [f for f in fields if norm(a[k].get(f)) != norm(b[k].get(f))]
    print(f"  DIFIERE {k}: campos {bad}")
    for f in bad:
        va, vb = a[k].get(f), b[k].get(f)
        if isinstance(va, list) and isinstance(vb, list):
            sa, sb = {norm(x) for x in va}, {norm(x) for x in vb}
            for x in sorted(sa - sb): print(f"      - solo A [{f}]: {x[:220]}")
            for x in sorted(sb - sa): print(f"      + solo B [{f}]: {x[:220]}")
            if sa == sb: print(f"      (mismo conjunto, distinto orden) [{f}]")
        else:
            print(f"      A[{f}]={norm(va)[:220]}\n      B[{f}]={norm(vb)[:220]}")
