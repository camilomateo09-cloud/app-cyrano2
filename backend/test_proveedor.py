"""P10 · Proveedor por artículo (desde MovCompras). Prueba del plan: ningún artículo usado en
el piloto queda «Sin asignar» (se revisa con la lista del piloto cuando se defina)."""

import csv
import re
from pathlib import Path

from backend._cliente_pruebas import ClienteConSesion, entrar_json
from backend.database import get_connection, init_db
from backend.main import app

client = ClienteConSesion(app)
INSUMOS = Path(__file__).resolve().parent.parent / "insumos"


def setup_function() -> None:
    init_db()
    conn = get_connection()
    for tabla in ("ingresos", "recepciones", "pendientes", "sesiones", "auditoria"):
        conn.execute(f"DELETE FROM {tabla}")
    conn.commit()
    conn.close()


def con_recepcion(proveedor: str, numero: str = "PV-1") -> str:
    sid = client.post("/api/login", json=entrar_json("Jose")).json()["session_id"]
    r = client.post("/api/recepciones", json={"session_id": sid, "proveedor": proveedor, "documento_tipo": "factura", "documento_numero": numero})
    assert r.status_code == 200, r.text
    return sid


def test_el_archivo_tiene_solo_nombres_sin_ruc_ni_cedula():
    texto = (INSUMOS / "producto_proveedor.csv").read_text(encoding="utf-8")
    assert texto.startswith("codigo,proveedor,entradas,ultima_entrada")
    assert not re.search(r"\b\d{10}(001)?\b|P\d{10,}", texto)


def test_el_catalogo_trae_el_proveedor_principal():
    filas = list(csv.DictReader((INSUMOS / "productos.csv").open(encoding="utf-8")))
    por_codigo = {f["codigo_cyrano"]: f["proveedor"] for f in filas}
    assert por_codigo["MT041"] == "LA FABRIL S.A."
    assert por_codigo["HUE001"] == "AVITO CIA LTDA"
    sin = {f["codigo_cyrano"] for f in filas if f["proveedor"] == "Sin asignar"}
    assert len(sin) < 0.2 * len(por_codigo)  # más del 80 % de los códigos tiene proveedor


def test_al_escanear_avisa_si_ese_proveedor_no_lo_trae():
    sid = con_recepcion("VITA ALIMENTOS C.A")
    r = client.get("/api/products/scan", params={"code": "17861048690796", "session_id": sid}).json()
    p = r["productos"][0]
    assert p["codigo_cyrano"] == "MT041" and p["del_proveedor"] is False and p["proveedores"] == ["LA FABRIL S.A."]
    assert r["proveedor_recepcion"] == "VITA ALIMENTOS C.A"


def test_al_escanear_reconoce_al_proveedor_que_si_lo_trae():
    sid = con_recepcion("LA FABRIL S.A.", "PV-2")
    p = client.get("/api/products/scan", params={"code": "17861048690796", "session_id": sid}).json()["productos"][0]
    assert p["del_proveedor"] is True


def test_sin_recepcion_o_sin_datos_no_opina():
    sid = client.post("/api/login", json=entrar_json("Jose")).json()["session_id"]
    p = client.get("/api/products/scan", params={"code": "17861048690796", "session_id": sid}).json()["productos"][0]
    assert p["del_proveedor"] is None and p["proveedores"] == ["LA FABRIL S.A."]


def test_al_buscar_por_nombre_salen_primero_los_del_proveedor():
    sid = con_recepcion("AVITO CIA LTDA", "PV-3")
    res = client.get("/api/search", params={"q": "huevo", "session_id": sid}).json()["resultados"]
    productos = [x for x in res if x["type"] == "producto"]
    assert productos[0]["codigo_cyrano"] == "HUE001" and productos[0]["del_proveedor"] is True
    assert all(not x.get("del_proveedor") for x in productos[1:] if x["codigo_cyrano"] != "HUE001")


def test_administracion_muestra_cuantos_codigos_tienen_proveedor():
    sid = client.post("/api/login", json=entrar_json("Camilo")).json()["session_id"]
    info = client.get("/api/admin/catalogo", params={"session_id": sid}).json()
    assert info["codigos_total"] == 1244 and 1000 < info["codigos_con_proveedor"] < 1244
