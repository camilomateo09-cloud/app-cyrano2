"""P25 · Calidad y actualización del catálogo.

Antes de aplicar un catálogo nuevo se revisa entero:
- ERRORES (bloquean la recarga; se queda el catálogo anterior y se avisa por qué):
  id repetido o no numérico, sin código o sin nombre, unidad fuera de la lista,
  factor ≤ 0, cantidad por unidad que no es entero ≥ 1.
- AVISOS (el producto se carga, pero el administrador lo ve para corregirlo con Cyrano):
  dígito verificador GS1 inválido, código de barras usado por productos distintos,
  mismo código con nombres distintos.
Los nombres se limpian (espacios dobles o al borde) al cargar.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from backend.gs1 import leer_gs1

UNIDADES_LLEGADA = ("unidad", "paquete", "caja", "rollo", "saco", "caneca", "barril", "bulto", "lamina", "balde", "cubeta", "gaveta")
UNIDADES_PLANTA = ("unid", "kg", "l", "paquete", "rollo", "caja")
LARGOS_GTIN = (8, 12, 13, 14)


def digito_gs1(cuerpo: str) -> int:
    """Dígito verificador GS1 (módulo 10, pesos 3 y 1 desde la derecha)."""
    suma = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(cuerpo)))
    return (10 - suma % 10) % 10


def gtin_del_codigo(codigo: str) -> str | None:
    """GTIN que trae un código: el código mismo si es GTIN-8/12/13/14, o el de un GS1-128."""
    codigo = (codigo or "").strip()
    if re.fullmatch(r"\d+", codigo) and len(codigo) in LARGOS_GTIN:
        return codigo
    gs1 = leer_gs1(codigo) if len(codigo) > 16 else None
    return gs1["gtin"] if gs1 else None


def digito_valido(codigo: str) -> bool | None:
    """True/False si el código trae un GTIN; None si no es un código GS1 (p. ej. interno)."""
    gtin = gtin_del_codigo(codigo)
    if not gtin:
        return None
    return digito_gs1(gtin[:-1]) == int(gtin[-1])


def limpiar_nombre(nombre: str) -> str:
    return " ".join((nombre or "").split())


def _numero(valor: Any) -> float | None:
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None


def revisar_catalogo(filas: list[dict[str, str]]) -> dict[str, Any]:
    """Revisa las filas de productos.csv. Devuelve errores, avisos y las filas limpias."""
    errores: list[str] = []
    filas_con_error: set[int] = set()
    ids: set[int] = set()
    limpias: list[dict[str, str]] = []
    for n, fila in enumerate(filas, start=2):  # fila 1 = encabezado
        donde = f"fila {n}"
        try:
            pid = int(fila.get("id", ""))
        except ValueError:
            errores.append(f"{donde}: el id «{fila.get('id', '')}» no es un número")
            filas_con_error.add(n)
            continue
        if pid in ids:
            errores.append(f"{donde}: el id {pid} está repetido")
            filas_con_error.add(n)
        ids.add(pid)
        codigo, nombre = (fila.get("codigo_cyrano") or "").strip(), limpiar_nombre(fila.get("nombre_producto", ""))
        donde = f"fila {n} ({codigo or 'sin código'})"
        if not codigo:
            errores.append(f"{donde}: falta el código")
        if not nombre:
            errores.append(f"{donde}: falta el nombre")
        llegada, planta = (fila.get("unidad_llega") or "").strip().lower(), (fila.get("unidad_planta") or "").strip().lower()
        planta = {"unidad": "unid"}.get(planta, planta)
        errores_antes = len(errores)
        if llegada not in UNIDADES_LLEGADA:
            errores.append(f"{donde}: la unidad que llega «{llegada}» no está en la lista")
        if planta not in UNIDADES_PLANTA:
            errores.append(f"{donde}: la unidad de planta «{planta}» no está en la lista")
        factor = _numero(fila.get("factor_conversion"))
        if factor is None or factor <= 0:
            errores.append(f"{donde}: el factor de conversión debe ser mayor que 0")
        cantidad = _numero(fila.get("cantidad_por_caja"))
        if cantidad is None or cantidad < 1 or not float(cantidad).is_integer():
            errores.append(f"{donde}: la cantidad por unidad debe ser un entero de 1 o más")
        if len(errores) > errores_antes:
            filas_con_error.add(n)
        limpias.append({**fila, "nombre_producto": nombre, "codigo_barra": (fila.get("codigo_barra") or "").strip(),
                        "unidad_llega": llegada, "unidad_planta": planta, "_fila": n})

    # Avisos
    digito_malo = []
    por_barra: dict[str, set[tuple[str, str]]] = defaultdict(set)
    por_codigo: dict[str, set[str]] = defaultdict(set)
    nombres_limpiados = 0
    for fila in limpias:
        original = filas[fila["_fila"] - 2]
        barra = fila["codigo_barra"]
        if barra:
            if digito_valido(barra) is False:
                gtin = gtin_del_codigo(barra)
                digito_malo.append({"codigo": fila["codigo_cyrano"], "nombre": fila["nombre_producto"], "codigo_barra": barra,
                                    "digito_esperado": digito_gs1(gtin[:-1])})
            por_barra[barra].add((fila["codigo_cyrano"], fila["nombre_producto"]))
        por_codigo[fila["codigo_cyrano"]].add(fila["nombre_producto"])
        if original.get("nombre_producto", "") != fila["nombre_producto"]:
            nombres_limpiados += 1
    barras_repetidas = [{"codigo_barra": b, "productos": sorted(f"{c} {n}" for c, n in v)}
                        for b, v in sorted(por_barra.items()) if len({c for c, _ in v}) > 1]
    codigos_dos_nombres = [{"codigo": c, "nombres": sorted(v)} for c, v in sorted(por_codigo.items()) if len(v) > 1]
    return {
        "errores": errores,
        "avisos": {
            "digito_invalido": digito_malo,
            "barras_repetidas": barras_repetidas,
            "codigos_con_dos_nombres": codigos_dos_nombres,
            "nombres_limpiados": nombres_limpiados,
        },
        "filas": limpias,
        "filas_validas": [f for f in limpias if f["_fila"] not in filas_con_error],
    }


def leer_version(csv_path: Path) -> dict[str, Any]:
    """Lee insumos/catalogo_version.json (número de versión, fuente y fecha del catálogo)."""
    path = csv_path.parent / "catalogo_version.json"
    if not path.exists():
        return {"version": "sin versión", "fuente": "", "fecha": ""}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"version": "versión ilegible", "fuente": "", "fecha": ""}
