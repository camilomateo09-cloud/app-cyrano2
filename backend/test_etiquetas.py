"""P13 · Etiquetas aparte: el operador no ve datos técnicos (IP, puerto, ZPL)."""

import re
from datetime import date, timedelta

from backend._cliente_pruebas import ClienteConSesion, entrar_json
from backend.database import get_connection, init_db
from backend.main import app

client = ClienteConSesion(app)


def setup_function() -> None:
    init_db()
    conn = get_connection()
    for tabla in ("ingresos", "recepciones", "pendientes", "sesiones", "auditoria"):
        conn.execute(f"DELETE FROM {tabla}")
    conn.commit()
    conn.close()


def ingreso(nombre: str = "Jose") -> tuple[str, int]:
    sid = client.post("/api/login", json=entrar_json(nombre)).json()["session_id"]
    rid = client.post("/api/recepciones", json={"session_id": sid, "proveedor": "VITA ALIMENTOS C.A", "documento_tipo": "factura", "documento_numero": f"ET-{nombre}"}).json()["id"]
    r = client.post("/api/entries", json={
        "producto_id": 32, "cantidad_ingresada": 3, "lote": "L-ET", "fecha_caducidad": (date.today() + timedelta(days=90)).isoformat(),
        "estado_qc": "aprobado", "session_id": sid, "recepcion_id": rid,
    })
    assert r.status_code == 200, r.text
    return sid, r.json()["id"]


def sin_datos_tecnicos(texto: str) -> bool:
    return not re.search(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|9100|\^XA", texto)


def test_el_operador_no_ve_la_configuracion_de_la_impresora():
    sid, _ = ingreso("Jose")
    r = client.get("/api/print/config", params={"session_id": sid})
    assert r.status_code == 403 and sin_datos_tecnicos(r.text)


def test_el_administrador_si_ve_la_configuracion():
    sid = client.post("/api/login", json=entrar_json("Camilo")).json()["session_id"]
    r = client.get("/api/print/config", params={"session_id": sid})
    assert r.status_code == 200 and {"ip", "port"} <= set(r.json())


def test_el_operador_no_puede_usar_el_modo_prueba_ni_ver_el_zpl():
    sid, entry_id = ingreso("Jose")
    r = client.post("/api/print/label", json={"session_id": sid, "entry_id": entry_id, "cantidad": 2, "test_mode": True})
    assert r.status_code == 403 and sin_datos_tecnicos(r.text)


def test_el_administrador_ve_el_zpl_en_modo_prueba():
    _, entry_id = ingreso("Jose")
    sid = client.post("/api/login", json=entrar_json("Camilo")).json()["session_id"]
    r = client.post("/api/print/label", json={"session_id": sid, "entry_id": entry_id, "cantidad": 2, "test_mode": True})
    assert r.status_code == 200
    assert r.json()["zpl"].startswith("^XA") and "^PQ2" in r.json()["zpl"]


def test_si_falla_la_impresora_el_operador_ve_que_hacer_sin_ip(monkeypatch):
    monkeypatch.setenv("ZEBRA_IP", "127.0.0.1")
    monkeypatch.setenv("ZEBRA_PORT", "9")  # puerto cerrado: falla al instante
    monkeypatch.setenv("ZEBRA_TIMEOUT", "1")
    sid, entry_id = ingreso("Jose")
    r = client.post("/api/print/label", json={"session_id": sid, "entry_id": entry_id, "cantidad": 1})
    assert r.status_code == 502
    detalle = r.json()["detail"]
    assert "avisa al supervisor" in detalle and "127.0.0.1" not in detalle and ":9" not in detalle


def test_cantidad_de_etiquetas_entre_1_y_50():
    sid, entry_id = ingreso("Jose")
    for mala in (0, 51, -3):
        r = client.post("/api/print/label", json={"session_id": sid, "entry_id": entry_id, "cantidad": mala})
        assert r.status_code == 422, mala


def test_un_ingreso_anulado_no_se_imprime():
    sid, entry_id = ingreso("Jose")
    assert client.post(f"/api/entries/{entry_id}/anular", json={"motivo": "Duplicado", "session_id": sid}).status_code == 200
    sid_admin = client.post("/api/login", json=entrar_json("Camilo")).json()["session_id"]
    r = client.post("/api/print/label", json={"session_id": sid_admin, "entry_id": entry_id, "cantidad": 1, "test_mode": True})
    assert r.status_code == 422
