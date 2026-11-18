"""P09 · Lectura GS1-128: lote y caducidad desde el código, y búsqueda por GTIN (R3)."""

import csv
from pathlib import Path

import pytest

from backend._cliente_pruebas import ClienteConSesion
from backend.database import get_connection, init_db
from backend.gs1 import fecha_gs1, leer_gs1
from backend.main import ahora_iso, app

client = ClienteConSesion(app)
SESION = "sesion-gs1"


def setup_function() -> None:
    init_db()
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO sesiones (session_id, usuario_nombre, created_at) VALUES (?, 'Jose', ?)", (SESION, ahora_iso()))
    conn.commit()
    conn.close()


@pytest.mark.parametrize("codigo, gtin, lote, caducidad, fuente", [
    ("0117861001234890172604161052010682NA", "17861001234890", "52010682NA", "2026-04-16", "17"),       # (01)(17)(10)
    ("010800564851402710441761066N15270624", "08005648514027", "441761066N", "2027-06-24", "15"),       # lote sin separador + (15)
    ("010350061117130610L030924", "03500611171306", "L030924", None, None),                            # solo lote
    ("011786212212036917000000109679", "17862122120369", "9679", None, None),                          # (17)000000 = sin fecha
    ("(01)17861071700035(17)261127(10)L11EZX24", "17861071700035", "L11EZX24", "2026-11-27", "17"),    # escrito a mano
    ("01178610717000351726112710L11\x1d21SERIE9", "17861071700035", "L11", "2026-11-27", "17"),        # con separador GS
    ("]C1011786107170003517261100101", "17861071700035", "1", "2026-11-30", "17"),                     # prefijo y día 00
])
def test_leer_gs1(codigo, gtin, lote, caducidad, fuente):
    r = leer_gs1(codigo)
    assert (r["gtin"], r["lote"], r["caducidad"], r["caducidad_fuente"]) == (gtin, lote, caducidad, fuente)


def test_codigos_comunes_no_son_gs1():
    assert leer_gs1("7861010907351") is None
    assert leer_gs1("200030384") is None
    assert fecha_gs1("261340") is None  # mes 13


def test_la_misma_caja_con_otro_lote_se_encuentra_r3():
    # En el catálogo está «01178610717000351726112710L11EZX24» (azúcar morena, saco).
    otro_lote = "01178610717000351727031510NUEVO99"
    r = client.get("/api/products/scan", params={"code": otro_lote, "session_id": SESION}).json()
    assert [p["codigo_cyrano"] for p in r["productos"]] == ["529"]  # una sola presentación (sin duplicar)
    assert r["gs1"] == {"gtin": "17861071700035", "lote": "NUEVO99", "caducidad": "2027-03-15", "caducidad_fuente": "17"}


def test_tres_etiquetas_del_catalogo_con_lote_y_caducidad():
    filas = [r for r in csv.DictReader((Path(__file__).resolve().parent.parent / "insumos" / "productos.csv").open(encoding="utf-8"))]
    largas = [f for f in filas if (g := leer_gs1(f["codigo_barra"])) and g["lote"] and g["caducidad"]][:3]
    assert len(largas) == 3
    for fila in largas:
        r = client.get("/api/products/scan", params={"code": fila["codigo_barra"], "session_id": SESION}).json()
        assert fila["id"] in [str(p["id"]) for p in r["productos"]]
        assert r["gs1"]["lote"] and r["gs1"]["caducidad"]


def test_gtin13_del_catalogo_se_encuentra_desde_gtin14():
    # Vaso degustación: en el catálogo 7861010907351 (GTIN-13); en la caja (01)07861010907351.
    r = client.get("/api/products/scan", params={"code": "010786101090735110LOTEX", "session_id": SESION}).json()
    assert [p["codigo_cyrano"] for p in r["productos"]] == ["856"]
    assert r["gs1"]["lote"] == "LOTEX"


def test_codigo_comun_y_desconocido():
    r = client.get("/api/products/scan", params={"code": "7861010907351", "session_id": SESION}).json()
    assert r["gs1"] is None and r["productos"][0]["codigo_cyrano"] == "856"
    assert client.get("/api/products/scan", params={"code": "999", "session_id": SESION}).json()["productos"] == []
