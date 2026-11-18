"""P23 · Catálogo: código SAP, unidades en lista cerrada y sin productos de ejemplo."""

import csv
import sqlite3
from pathlib import Path

import pytest

from backend.database import PRODUCTOS_EJEMPLO, UNIDADES_LLEGADA, UNIDADES_PLANTA, get_connection, init_db

CSV = Path(__file__).resolve().parent.parent / "insumos" / "productos.csv"


def setup_function() -> None:
    init_db()


def test_sin_productos_de_ejemplo_y_con_codigo_sap():
    conn = get_connection()
    try:
        marcas = ", ".join("?" for _ in PRODUCTOS_EJEMPLO)
        assert conn.execute(f"SELECT COUNT(*) FROM productos WHERE codigo_cyrano IN ({marcas})", PRODUCTOS_EJEMPLO).fetchone()[0] == 0
        total = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
        con_sap = conn.execute("SELECT COUNT(*) FROM productos WHERE codigo_sap IS NOT NULL").fetchone()[0]
        assert total == 669
        assert con_sap / total > 0.95
        assert conn.execute("SELECT codigo_sap FROM productos WHERE id = 32").fetchone()[0] == "MT041"  # aceite desmoldante
    finally:
        conn.close()


def test_unidades_en_lista_cerrada_y_regla_de_conversion():
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    assert {r["unidad_llega"] for r in rows} <= set(UNIDADES_LLEGADA)
    assert {r["unidad_planta"] for r in rows} <= set(UNIDADES_PLANTA)
    assert all(float(r["factor_conversion"]) > 0 for r in rows)
    assert all(float(r["cantidad_por_caja"]) >= 1 and float(r["cantidad_por_caja"]).is_integer() for r in rows)


@pytest.mark.parametrize("campo, valor, texto", [
    ("unidad_llega", "litros", "unidad de llegada"),
    ("unidad_planta", "unidad", "unidad de planta"),
    ("factor_conversion", 0, "factor"),
    ("cantidad_por_caja", 2.5, "unidades por empaque"),
])
def test_la_base_rechaza_productos_fuera_de_regla(campo, valor, texto):
    conn = get_connection()
    try:
        with pytest.raises(sqlite3.DatabaseError, match=texto):
            conn.execute(f"UPDATE productos SET {campo} = ? WHERE id = 1", (valor,))
    finally:
        conn.rollback()
        conn.close()
