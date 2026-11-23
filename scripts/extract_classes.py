"""Extrae el objeto "classes" de la salida del analizador (java-class-analyzer.jar) y lo guarda
como class_info_dependency.json plano, que es el formato que publican los autores y que leen las herramientas.
Uso: python scripts/extract_classes.py <analyzer_raw_output.json> <class_info_dependency.json>"""
import json, sys
raw = json.load(open(sys.argv[1], encoding="utf-8"))
assert set(raw) == {"metadata", "classes"}, list(raw)
classes = raw["classes"]
assert raw["metadata"]["totalClasses"] == len(classes)
with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as f:
    json.dump(classes, f, indent=2, ensure_ascii=False)
print(f"{len(classes)} clases -> {sys.argv[2]} | metadata: {json.dumps(raw['metadata'])}")
