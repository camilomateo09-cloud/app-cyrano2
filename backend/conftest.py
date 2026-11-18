"""Prepara las pruebas: base SQLite temporal y usuarios con PIN de prueba (P24).

Así las pruebas no tocan la base local de trabajo ni necesitan los PIN reales.
"""

import csv
import os
import tempfile
from pathlib import Path

from backend._cliente_pruebas import PINES_PRUEBA, ROLES_PRUEBA
from backend.claves import hash_pin

_carpeta = Path(tempfile.mkdtemp(prefix="cyrano-pruebas-"))
_csv = _carpeta / "usuarios.csv"
with _csv.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle)
    writer.writerow(["id", "nombre", "clave_hash", "rol"])
    for numero, (nombre, pin) in enumerate(PINES_PRUEBA.items(), start=1):
        writer.writerow([numero, nombre, hash_pin(pin, iteraciones=1_000), ROLES_PRUEBA[nombre]])

os.environ.setdefault("CYRANO_DB_PATH", str(_carpeta / "pruebas.db"))
os.environ["CYRANO_USUARIOS_CSV"] = str(_csv)
