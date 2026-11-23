"""Comprueba que el artefacto original no fue modificado (regla de §2, lista de verificacion §13).

Referencia independiente: MicroAgent.zip (el artefacto tal como se descargo). Para cada archivo del zip se
compara su SHA-256 con el del mismo archivo en MicroAgent/. Ademas se listan los archivos que estan en la
carpeta y no en el zip (p. ej. carpetas target/ que genera el servidor de lenguaje Java de VS Code).

Resultado:
  OK     -> todos los archivos del artefacto estan presentes e identicos y no hay archivos adicionales.
  AVISO  -> el artefacto esta intacto, pero hay archivos adicionales solo dentro de carpetas target/.
  FALLA  -> falta o cambio algun archivo del artefacto, o hay archivos adicionales fuera de target/.
Uso: python scripts/check_microagent_untouched.py"""
import collections
import hashlib
import os
import sys
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BASE)  # carpeta "Replica de Paper"
FOLDER = os.path.join(ROOT, "MicroAgent")

z = zipfile.ZipFile(os.path.join(ROOT, "MicroAgent.zip"))
names = [n for n in z.namelist() if not n.endswith("/")]

missing, changed = [], []
for n in names:
    p = os.path.join(FOLDER, *n.split("/"))
    if not os.path.isfile(p):
        missing.append(n)
        continue
    with open(p, "rb") as fh:
        if hashlib.sha256(fh.read()).hexdigest() != hashlib.sha256(z.read(n)).hexdigest():
            changed.append(n)

on_disk = set()
for d, _, fs in os.walk(FOLDER):
    for fn in fs:
        on_disk.add(os.path.relpath(os.path.join(d, fn), FOLDER).replace(os.sep, "/"))
extra = sorted(on_disk - set(names))
extra_outside_target = [e for e in extra if "/target/" not in "/" + e]

print(f"archivos del artefacto (zip): {len(names)} | en la carpeta: {len(on_disk)}")
print(f"faltantes: {len(missing)} {missing[:10]}")
print(f"modificados: {len(changed)} {changed[:10]}")
print(f"adicionales (no estan en el zip): {len(extra)}")
for k, v in sorted(collections.Counter(e.split("/target/")[0] + "/target" for e in extra if e not in extra_outside_target).items()):
    print(f"   {v:5d}  {k}")
if extra_outside_target:
    print(f"   fuera de target/: {extra_outside_target[:20]}")

if missing or changed or extra_outside_target:
    print("RESULTADO: FALLA")
    sys.exit(1)
if extra:
    print("RESULTADO: AVISO (artefacto intacto; hay archivos adicionales solo en carpetas target/, ver DECISIONES.md D14)")
else:
    print("RESULTADO: OK (MicroAgent/ identico al zip)")
sys.exit(0)
