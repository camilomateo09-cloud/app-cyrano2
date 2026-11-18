"""P20 · Reglas de validación del ingreso (diccionario de datos, hoja Reglas_validacion).

Se aplican en el servidor (la tablet ayuda, pero no basta) y las más básicas también en
la base, con disparadores (ver database.ensure_reglas_base). Cada regla dice qué criterio
de la evaluación de datos cubre (D1–D14) y qué prueba la comprueba (T01–T16).

Supuestos editables (marcados SUPUESTO): no hay todavía un tope por artículo ni un tipo
de bodega en el catálogo; se usan valores generales hasta que Cyrano los defina.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException

TOPE_CANTIDAD = 10_000            # SUPUESTO: tope general en la unidad de llegada (D1, T03)
LOTE_MAX = 30                     # D3, T08
LOTE_PATRON = re.compile(r"^[A-Z0-9][A-Z0-9\-/.]*$")  # letras, números, guion, barra, punto (D3, T09)
TEMP_MIN, TEMP_MAX = -30.0, 60.0  # rango físico de la lectura (D4, T10)
TEMP_OK_MIN, TEMP_OK_MAX = -25.0, 25.0  # SUPUESTO: «Temperatura OK» solo en este rango hasta tener tipo de bodega (D7, T11)
CADUCIDAD_MAX_ANIOS = 15          # una caducidad más lejana casi siempre es un error de digitación
OBSERVACIONES_MAX = 500
RESPONSABLE_MAX = 80
# Decisión de Mateo (10-nov): los 5 puntos del checklist NO son obligatorios, porque no
# aplican a todos los productos; se marcan los que correspondan. Solo el estado es obligatorio.


def _error(texto: str) -> HTTPException:
    return HTTPException(status_code=422, detail=texto)


def validar_cantidad(cantidad: float, unidad: str) -> float:
    if cantidad is None or cantidad <= 0:
        raise _error("La cantidad debe ser mayor que 0")
    if cantidad > TOPE_CANTIDAD:
        raise _error(f"La cantidad ({cantidad:g} {unidad}) pasa el tope de {TOPE_CANTIDAD:,} {unidad}: revisa si está bien escrita".replace(",", " "))
    return round(float(cantidad), 3)


def validar_lote(lote: str | None) -> str:
    valor = (lote or "").strip().upper()
    if not valor:
        raise _error("El lote es obligatorio")
    if len(valor) > LOTE_MAX:
        raise _error(f"El lote tiene {len(valor)} caracteres; el máximo es {LOTE_MAX}")
    if not LOTE_PATRON.match(valor):
        raise _error("El lote solo puede tener letras, números, guion (-), barra (/) y punto (.), sin espacios")
    return valor


def validar_caducidad(texto: str | None, hoy: date) -> str:
    valor = (texto or "").strip()
    if not valor:
        raise _error("La fecha de caducidad es obligatoria")
    try:
        fecha = datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        raise _error(f"La fecha de caducidad «{valor[:20]}» no es válida (formato AAAA-MM-DD)")
    if fecha <= hoy:
        raise _error(f"La fecha de caducidad ({fecha.isoformat()}) ya pasó o es hoy: el producto está vencido")
    if fecha.year > hoy.year + CADUCIDAD_MAX_ANIOS:
        raise _error(f"La fecha de caducidad ({fecha.isoformat()}) está demasiado lejos: revisa el año")
    return fecha.isoformat()


def validar_calidad(item: Any) -> dict[str, Any]:
    """Temperatura y coherencia del control de calidad (D4, D7 en parte; T10, T11).

    Los puntos del checklist son opcionales (decisión de Mateo, 10-nov).
    """
    temp = item.temperatura_recepcion
    if temp is not None and not (TEMP_MIN <= temp <= TEMP_MAX):
        raise _error(f"La temperatura de recepción ({temp:g} °C) está fuera del rango posible ({TEMP_MIN:g} a {TEMP_MAX:g} °C)")
    if item.temperatura_ok and temp is not None and not (TEMP_OK_MIN <= temp <= TEMP_OK_MAX):
        raise _error(f"«Temperatura OK» está marcada pero la lectura es {temp:g} °C (rango aceptado {TEMP_OK_MIN:g} a {TEMP_OK_MAX:g} °C)")

    observaciones = (item.observaciones_qc or "").strip()
    responsable = (item.responsable_qc or "").strip()
    if len(observaciones) > OBSERVACIONES_MAX:
        raise _error(f"Las observaciones pasan de {OBSERVACIONES_MAX} caracteres")
    if len(responsable) > RESPONSABLE_MAX:
        raise _error(f"El responsable pasa de {RESPONSABLE_MAX} caracteres")

    return {"observaciones_qc": observaciones, "responsable_qc": responsable}


def producto_existente(conn: Any, producto_id: int) -> Any:
    """D5 / R2 / T12: antes, un producto inexistente se guardaba como el primero del catálogo."""
    product = conn.execute("SELECT * FROM productos WHERE id = ?", (producto_id,)).fetchone()
    if product is None:
        raise _error(f"El producto {producto_id} no existe en el catálogo")
    return product
