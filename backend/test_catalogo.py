"""P23 · Catálogo (desde nov-2026 sale del Libro11 de Cyrano): código, unidades en lista cerrada,
regla de conversión y recarga cuando cambia el CSV."""

import csv
import sqlite3
from pathlib import Path

import pytest

from backend.database import UNIDADES_LLEGADA, UNIDADES_PLANTA, get_connection, init_db

CSV = Path(__file__).resolve().parent.parent / "insumos" / "productos.csv"


def setup_function() -> None:
    init_db()


def test_el_catalogo_es_el_libro11_completo():
    filas = list(csv.DictReader(CSV.open(encoding="utf-8")))
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
        assert total == len(filas) == 1417
        assert conn.execute("SELECT COUNT(*) FROM productos WHERE codigo_sap IS NULL OR codigo_sap = ''").fetchone()[0] == 0
        assert conn.execute("SELECT codigo_cyrano FROM productos WHERE id = 32").fetchone()[0] == "MT041"  # aceite desmoldante (mismo id)
        # Unidades nuevas del Libro11: lámina, cubeta…
        assert conn.execute("SELECT COUNT(*) FROM productos WHERE unidad_llega = 'lamina'").fetchone()[0] > 0
        huevo = conn.execute("SELECT unidad_llega, cantidad_por_caja, factor_conversion, unidad_planta FROM productos WHERE codigo_cyrano = 'HUE001'").fetchone()
        assert tuple(huevo) == ("cubeta", 30, 0.0567, "kg")  # 1 cubeta = 30 × 0,0567 kg
    finally:
        conn.close()


def test_si_cambia_el_csv_el_catalogo_se_vuelve_a_cargar():
    conn = get_connection()
    try:
        conn.execute("UPDATE productos SET nombre_producto = 'NOMBRE VIEJO' WHERE id = 32")
        conn.execute("INSERT INTO productos (id, codigo_cyrano, nombre_producto, proveedor, unidad_llega, cantidad_asociada, unidad_planta, factor_conversion, cantidad_por_caja) "
                     "VALUES (99999, 'VIEJO1', 'PRODUCTO QUE YA NO ESTA', 'x', 'unidad', 1, 'unid', 1, 1)")
        conn.execute("UPDATE catalogo_version SET huella = 'otra'")
        conn.commit()
    finally:
        conn.close()
    init_db()
    conn = get_connection()
    try:
        assert conn.execute("SELECT nombre_producto FROM productos WHERE id = 32").fetchone()[0] == "ACEITE DESMOLDANTE FABRIL"
        assert conn.execute("SELECT COUNT(*) FROM productos WHERE id = 99999").fetchone()[0] == 0
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
