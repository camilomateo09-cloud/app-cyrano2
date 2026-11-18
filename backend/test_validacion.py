"""P20 · Pruebas T01–T16 del cuaderno de validación de datos (05_Validacion_datos).

Cada prueba repite el caso de la hoja Pruebas y comprueba el resultado esperado.
"""

from datetime import date, timedelta

import pytest
from backend._cliente_pruebas import ClienteConSesion

from backend.database import get_connection, init_db
from backend.main import ahora_iso, app

client = ClienteConSesion(app)
SESION = "sesion-validacion"
CHECKS = {"empaque_ok": True, "sin_humedad": True, "temperatura_ok": True, "aspecto_olor_ok": True, "documentacion_proveedor_ok": True}
MANANA = (date.today() + timedelta(days=200)).isoformat()
RID: dict[str, int] = {}


def setup_function() -> None:
    init_db()
    conn = get_connection()
    for tabla in ("ingresos", "recepciones", "pendientes"):
        conn.execute(f"DELETE FROM {tabla}")
    conn.execute(
        "INSERT OR REPLACE INTO sesiones (session_id, usuario_nombre, created_at) VALUES (?, 'Jose', ?)",
        (SESION, ahora_iso()),
    )
    conn.commit()
    conn.close()
    rec = client.post("/api/recepciones", json={"session_id": SESION, "proveedor": "VITA ALIMENTOS C.A", "documento_tipo": "factura", "documento_numero": "T-001"})
    RID["id"] = rec.json()["id"]


def ingreso(**cambios):
    base = {"producto_id": 32, "cantidad_ingresada": 2, "lote": "L-2611", "fecha_caducidad": MANANA,
            "estado_qc": "aprobado", **CHECKS, "session_id": SESION, "recepcion_id": RID["id"]}
    base.update(cambios)
    return base


def contar() -> int:
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM ingresos").fetchone()[0]
    finally:
        conn.close()


@pytest.mark.parametrize("prueba, cambios, texto", [
    ("T01 cantidad negativa", {"cantidad_ingresada": -5}, "mayor que 0"),
    ("T02 cantidad cero", {"cantidad_ingresada": 0}, "mayor que 0"),
    ("T03 cantidad enorme", {"cantidad_ingresada": 1_000_000}, "tope"),
    ("T04 cantidad con texto", {"cantidad_ingresada": "dos"}, "la cantidad"),
    ("T05 fecha inválida", {"fecha_caducidad": "31/02/2027"}, "no es válida"),
    ("T06 fecha con texto", {"fecha_caducidad": "mañana"}, "no es válida"),
    ("T07 fecha pasada", {"fecha_caducidad": "2020-01-01"}, "vencido"),
    ("T08 lote de 500 caracteres", {"lote": "A" * 500}, "máximo es 30"),
    ("T09 lote con HTML", {"lote": "<img src=x onerror=alert(1)>"}, "solo puede tener"),
    ("T10 temperatura -500", {"temperatura_recepcion": -500}, "fuera del rango posible"),
    ("T11 temperatura OK con 35 °C", {"temperatura_recepcion": 35}, "Temperatura OK"),
    ("T12 producto inexistente", {"producto_id": 99999}, "no existe"),
])
def test_rechaza_datos_invalidos(prueba, cambios, texto):
    response = client.post("/api/entries", json=ingreso(**cambios))
    assert response.status_code == 422, prueba
    assert texto in response.json()["detail"], (prueba, response.json())
    assert contar() == 0, prueba


def test_checklist_es_opcional_solo_el_estado_es_obligatorio():
    """Decisión de Mateo (10-nov): los puntos del checklist no aplican a todos los productos."""
    sin_checks = {k: False for k in CHECKS}
    assert client.post("/api/entries", json=ingreso(**sin_checks, linea_id="sin-checks")).status_code == 200
    sin_estado = client.post("/api/entries", json=ingreso(estado_qc="", linea_id="sin-estado"))
    assert sin_estado.status_code == 422
    assert contar() == 1


def test_t14_estado_en_mayusculas_y_lote_normalizado():
    response = client.post("/api/entries", json=ingreso(estado_qc="APROBADO", lote="  l-2611/a "))
    assert response.status_code == 200
    conn = get_connection()
    row = conn.execute("SELECT estado_qc, lote FROM ingresos").fetchone()
    conn.close()
    assert (row["estado_qc"], row["lote"]) == ("aprobado", "L-2611/A")


def test_t15_dos_lineas_iguales_legitimas_se_guardan_las_dos():
    lineas = [ingreso(linea_id="tablet-1"), ingreso(linea_id="tablet-2")]
    response = client.post("/api/entries/bulk", json={"entries": lineas})
    assert response.status_code == 200
    assert response.json()["guardados"] == 2
    assert contar() == 2


def test_t16_doble_toque_no_duplica():
    lineas = [ingreso(linea_id="tablet-9")]
    client.post("/api/entries/bulk", json={"entries": lineas})
    again = client.post("/api/entries/bulk", json={"entries": lineas})
    assert again.status_code == 200
    assert again.json() == {"message": "Ingresos masivos guardados", "guardados": 0, "ya_guardados": 1}
    assert contar() == 1


def test_lote_invalido_en_masivo_dice_la_linea_y_no_guarda_ninguna():
    lineas = [ingreso(linea_id="ok-1"), ingreso(linea_id="mal-2", lote="LOTE CON ESPACIO")]
    response = client.post("/api/entries/bulk", json={"entries": lineas})
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Línea 2 (1371 · lote LOTE CON ESPACIO)")
    assert contar() == 0


def test_la_base_rechaza_un_registro_malo_aunque_no_pase_por_la_api():
    conn = get_connection()
    with pytest.raises(Exception, match="mayor que 0"):
        conn.execute(
            "INSERT INTO ingresos (producto_id, nombre_producto, codigo_cyrano, cantidad_ingresada, unidad_llega, "
            "cantidad_convertida, unidad_planta, lote, fecha_caducidad, estado_qc, created_at) "
            "VALUES (32, 'X', '1371', -1, 'caja', 0, 'l', 'L1', '2027-01-01', 'aprobado', '2026-11-10T08:00:00-05:00')"
        )
    conn.close()
