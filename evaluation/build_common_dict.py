"""Reconstruye el common_dict de PartsUnlimitedMRP (INSTRUCCIONES §9.2; DECISIONES D50).

El artefacto solo publica el common_dict de JPetStore (MicroAgent/metrics/test/common_dict.json). Regla:
  - clases comunes = clases que aparecen en mas de una particion de la referencia (sin la clave "uncounted");
  - valores = clases con una relacion DIRECTA hacia la clase comun en context/<app>/class_info_dependency.json
    (los tipos de VALID_RELATIONSHIP_TYPES de custom_tools.py del original);
  - se excluyen las clases comunes sin ningun dependiente (decision de Jorge, opcion A de D50): con una lista
    vacia, la asignacion ideal no tendria ningun servicio y la referencia evaluada contra si misma no daria 1,0.

Antes de escribir, comprueba que la misma regla reproduce el common_dict publicado de JPetStore (como conjuntos)
y que salen las 8 clases que lista §9.2. Si algo no coincide, aborta sin escribir.

Uso: python -B -X utf8 evaluation/build_common_dict.py [--check]   (--check no escribe; solo compara)
"""
import collections
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # replica-claude-code
ROOT = os.path.dirname(BASE)

# Copia literal de VALID_RELATIONSHIP_TYPES (custom_tools.py del original, lineas 20-32).
DIRECT = ["EXTENDS", "IMPLEMENTS", "CALLS", "USES", "REFERENCES", "INJECTS", "ASSOCIATES",
          "ANNOTATED_WITH", "CREATES", "PERSISTS", "DEPENDS_ON"]

EXPECTED_PU_COMMON = {
    "smpl.ordering.repositories.RepositoryFactory", "smpl.ordering.SimpleCORSFilter", "smpl.ordering.TestPath",
    "smpl.ordering.Utility", "smpl.ordering.OrderingConfiguration", "smpl.ordering.OrderingInitializer",
    "smpl.ordering.BadRequestException", "smpl.ordering.ConflictingRequestException",
}


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def build(app):
    ref = load(os.path.join(BASE, "evaluation", "references", f"{app}.json"))
    dep = load(os.path.join(BASE, "context", app, "class_info_dependency.json"))
    count = collections.Counter(c for k, v in ref.items() if k != "uncounted" for c in set(v))
    common = sorted(c for c, n in count.items() if n > 1)
    full = {}
    for c in common:
        full[c] = sorted({src for src, data in dep.items() if src != c
                          for rel, targets in data.get("relationships", {}).items()
                          if rel in DIRECT and c in targets})
    return full


def main():
    check_only = "--check" in sys.argv[1:]
    # 1. Control con JPetStore.
    jp = build("jpetstore-6")
    published = load(os.path.join(ROOT, "MicroAgent", "metrics", "test", "common_dict.json"))
    same = (set(jp) == set(published)
            and all(set(jp[k]) == set(published[k]) and len(published[k]) == len(set(published[k])) for k in jp))
    print("JPetStore: la regla reproduce el common_dict publicado:", "SI" if same else "NO")
    if not same:
        print("  regla:", json.dumps(jp, indent=2))
        print("  publicado:", json.dumps(published, indent=2))
        sys.exit(1)
    # 2. PartsUnlimitedMRP.
    pu = build("partsunlimited")
    if set(pu) != EXPECTED_PU_COMMON:
        print("PartsUnlimitedMRP: las clases comunes no son las 8 de §9.2:", sorted(pu))
        sys.exit(1)
    empty = sorted(c for c, v in pu.items() if not v)
    print("PartsUnlimitedMRP: 8 clases comunes; sin dependientes (se excluyen):", empty)
    final = {c: v for c, v in pu.items() if v}
    out = os.path.join(BASE, "evaluation", "common_dicts", "partsunlimited.json")
    text = json.dumps(final, indent=2) + "\n"
    if check_only:
        with open(out, encoding="utf-8") as fh:
            ok = fh.read() == text
        print("common_dicts/partsunlimited.json coincide con la regla:", "SI" if ok else "NO")
        sys.exit(0 if ok else 1)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"Escrito {os.path.relpath(out, BASE)} con {len(final)} clases comunes.")


if __name__ == "__main__":
    main()
