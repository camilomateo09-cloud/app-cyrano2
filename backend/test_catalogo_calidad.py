"""P25 · Calidad y actualización del catálogo (prueba T22: la recarga aplica los cambios
o avisa por qué no)."""

import csv
import json
import shutil
from pathlib import Path

import pytest

from backend._cliente_pruebas import ClienteConSesion, entrar_json
from backend.catalogo import digito_gs1, digito_valido, revisar_catalogo
from backend.database import get_connection, init_db
from backend.main import app

client = ClienteConSesion(app)
INSUMOS = Path(__file__).resolve().parent.parent / "insumos"


@pytest.fixture(autouse=True)
def catalogo_real(monkeypatch):
    monkeypatch.delenv("CYRANO_PRODUCTOS_CSV", raising=False)
    init_db()
    yield
    monkeypatch.delenv("CYRANO_PRODUCTOS_CSV", raising=False)
    init_db()  # deja cargado el catálogo real para las demás pruebas


def copia_del_catalogo(tmp_path: Path, version: str, cambio) -> Path:
    filas = list(csv.DictReader((INSUMOS / "productos.csv").open(encoding="utf-8")))
    cambio(filas)
    destino = tmp_path / "productos.csv"
    with destino.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    (tmp_path / "catalogo_version.json").write_text(json.dumps({"version": version, "fuente": "prueba"}), encoding="utf-8")
    return destino


def nombre(pid: int) -> str:
    conn = get_connection()
    try:
        return conn.execute("SELECT nombre_producto FROM productos WHERE id = ?", (pid,)).fetchone()[0]
    finally:
        conn.close()


def admin() -> str:
    return client.post("/api/login", json=entrar_json("Camilo")).json()["session_id"]


def test_t22_una_recarga_valida_se_aplica_con_su_version(tmp_path, monkeypatch):
    def cambio(filas):
        filas[0]["nombre_producto"] = "VASO DEGUSTACION CAMBIADO"
    monkeypatch.setenv("CYRANO_PRODUCTOS_CSV", str(copia_del_catalogo(tmp_path, "prueba-2", cambio)))
    r = client.post("/api/admin/reload", json={"session_id": admin()})
    assert r.status_code == 200 and r.json()["resultado"] == "aplicado"
    assert "prueba-2" in r.json()["message"]
    assert nombre(1) == "VASO DEGUSTACION CAMBIADO"
    info = client.get("/api/admin/catalogo", params={"session_id": admin()}).json()
    assert info["version"] == "prueba-2" and info["estado"] == "aplicado" and info["ultimo_rechazo"] is None
    assert info["cargas"][0]["resultado"] == "aplicado"


def test_t22_una_recarga_con_errores_no_se_aplica_y_dice_por_que(tmp_path, monkeypatch):
    antes = nombre(1)
    def cambio(filas):
        filas[0]["nombre_producto"] = "NO DEBE APARECER"
        filas[5]["factor_conversion"] = "0"
        filas[7]["unidad_llega"] = "tonel"
    monkeypatch.setenv("CYRANO_PRODUCTOS_CSV", str(copia_del_catalogo(tmp_path, "prueba-mala", cambio)))
    r = client.post("/api/admin/reload", json={"session_id": admin()})
    assert r.status_code == 200 and r.json()["resultado"] == "rechazado"
    mensaje = r.json()["message"]
    assert "No se aplicó la versión prueba-mala" in mensaje and "2 error(es)" in mensaje
    assert "fila 7" in mensaje and "factor" in mensaje and "tonel" in mensaje
    assert nombre(1) == antes  # se sigue usando el catálogo anterior
    info = client.get("/api/admin/catalogo", params={"session_id": admin()}).json()
    assert info["ultimo_rechazo"] and info["version"] != "prueba-mala"
    assert info["cargas"][0]["resultado"] == "rechazado"
    # Repetir la recarga del mismo CSV malo no vuelve a registrar el intento.
    assert client.post("/api/admin/reload", json={"session_id": admin()}).json()["resultado"] == "sin cambios"


def test_sin_cambios_dice_la_version_en_uso():
    r = client.post("/api/admin/reload", json={"session_id": admin()})
    assert r.json()["resultado"] == "sin cambios" and "versión" in r.json()["message"]


def test_la_version_del_catalogo_real_y_sus_avisos():
    version = json.loads((INSUMOS / "catalogo_version.json").read_text(encoding="utf-8"))
    info = client.get("/api/admin/catalogo", params={"session_id": admin()}).json()
    assert info["version"] == version["version"] and info["filas"] == 1417
    assert len(info["avisos"]["digito_invalido"]) == 6
    assert len(info["avisos"]["barras_repetidas"]) == 5
    assert len(info["avisos"]["codigos_con_dos_nombres"]) == 3
    malo = {x["codigo"]: x for x in info["avisos"]["digito_invalido"]}["ADT126"]
    assert malo["codigo_barra"] == "7707297186790" and malo["digito_esperado"] == digito_gs1("770729718679")


def test_el_operador_no_ve_el_estado_del_catalogo():
    sid = client.post("/api/login", json=entrar_json("Jose")).json()["session_id"]
    assert client.get("/api/admin/catalogo", params={"session_id": sid}).status_code == 403
    assert client.post("/api/admin/reload", json={"session_id": sid}).status_code == 403


def test_digito_verificador_gs1():
    assert digito_valido("7861010907351") is True          # GTIN-13 real del catálogo
    assert digito_valido("7861010907352") is False         # último dígito cambiado
    assert digito_valido("17861048690796") is True         # GTIN-14
    assert digito_valido("011786100891211117280124102401") is True  # GS1-128 con GTIN
    assert digito_valido("GRANO0183") is None and digito_valido("200030384") is None  # códigos internos


def test_al_escanear_un_codigo_mal_leido_se_avisa():
    sid = client.post("/api/login", json=entrar_json("Jose")).json()["session_id"]
    r = client.get("/api/products/scan", params={"code": "7861010907352", "session_id": sid}).json()
    assert r["productos"] == [] and r["digito_valido"] is False
    r = client.get("/api/products/scan", params={"code": "7861010907351", "session_id": sid}).json()
    assert r["productos"] and r["digito_valido"] is True


def test_nombres_limpios_y_filas_con_error_fuera():
    filas = [
        {"id": "1", "codigo_cyrano": "A1", "nombre_producto": " CUCHARAS  LARGAS X ", "codigo_barra": "", "unidad_llega": "caja",
         "unidad_planta": "unid", "factor_conversion": "1", "cantidad_por_caja": "12"},
        {"id": "2", "codigo_cyrano": "A2", "nombre_producto": "MALO", "codigo_barra": "", "unidad_llega": "caja",
         "unidad_planta": "kg", "factor_conversion": "-1", "cantidad_por_caja": "1"},
        {"id": "2", "codigo_cyrano": "A3", "nombre_producto": "ID REPETIDO", "codigo_barra": "", "unidad_llega": "caja",
         "unidad_planta": "kg", "factor_conversion": "1", "cantidad_por_caja": "1.5"},
    ]
    r = revisar_catalogo(filas)
    assert [f["nombre_producto"] for f in r["filas_validas"]] == ["CUCHARAS LARGAS X"]
    assert any("id 2 está repetido" in e for e in r["errores"])
    assert any("entero" in e for e in r["errores"]) and any("mayor que 0" in e for e in r["errores"])
    assert r["avisos"]["nombres_limpiados"] == 1
