"""P22 · Anular en vez de borrar y auditoría (prueba T23 y más)."""

import csv
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

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


def preparar() -> tuple[str, int, int]:
    sid = client.post("/api/login", json=entrar_json("Jose")).json()["session_id"]
    rid = client.post("/api/recepciones", json={"session_id": sid, "proveedor": "VITA ALIMENTOS C.A", "documento_tipo": "factura", "documento_numero": "AU-1"}).json()["id"]
    entry = client.post("/api/entries", json={
        "producto_id": 32, "cantidad_ingresada": 2, "lote": "L-AUD", "fecha_caducidad": (date.today() + timedelta(days=90)).isoformat(),
        "estado_qc": "aprobado", "session_id": sid, "recepcion_id": rid,
    })
    assert entry.status_code == 200, entry.text
    return sid, rid, entry.json()["id"]


def test_t23_anular_deja_el_registro_con_motivo_usuario_y_hora():
    sid, rid, entry_id = preparar()
    r = client.post(f"/api/entries/{entry_id}/anular", json={"motivo": "Se contó mal: eran 3 cajas", "session_id": sid})
    assert r.status_code == 200
    conn = get_connection()
    row = conn.execute("SELECT estado_registro, anulado_motivo, anulado_por, anulado_at FROM ingresos WHERE id = ?", (entry_id,)).fetchone()
    conn.close()
    assert row["estado_registro"] == "anulado"
    assert row["anulado_motivo"] == "Se contó mal: eran 3 cajas"
    assert row["anulado_por"] == "Jose"
    assert row["anulado_at"].endswith("-05:00")
    # la recepción ya no lo cuenta como confirmado
    assert client.get("/api/recepciones/abierta", params={"session_id": sid}).json()["ingresos_confirmados"] == 0


def test_no_se_borra_y_no_se_anula_dos_veces_ni_sin_motivo():
    sid, _, entry_id = preparar()
    assert client.delete(f"/api/entries/{entry_id}", params={"session_id": sid}).status_code == 405
    assert client.post(f"/api/entries/{entry_id}/anular", json={"motivo": "  ", "session_id": sid}).status_code == 422
    assert client.post(f"/api/entries/{entry_id}/anular", json={"motivo": "Duplicado", "session_id": sid}).status_code == 200
    assert client.post(f"/api/entries/{entry_id}/anular", json={"motivo": "Duplicado", "session_id": sid}).status_code == 409


def test_auditoria_registra_y_no_se_modifica():
    sid, rid, entry_id = preparar()
    client.post(f"/api/recepciones/{rid}/inicio", json={"session_id": sid})
    client.post(f"/api/entries/{entry_id}/anular", json={"motivo": "Duplicado", "session_id": sid})
    camilo = client.post("/api/login", json=entrar_json("Camilo")).json()["session_id"]
    eventos = client.get("/api/admin/auditoria", params={"session_id": camilo}).json()
    acciones = [(e["entidad"], e["accion"], e["usuario"]) for e in eventos]
    assert ("recepcion", "apertura", "Jose") in acciones
    assert ("ingreso", "alta", "Jose") in acciones
    assert ("ingreso", "anulacion", "Jose") in acciones
    assert next(e for e in eventos if e["accion"] == "anulacion")["detalle"]["motivo"] == "Duplicado"
    assert client.get("/api/admin/auditoria", params={"session_id": sid}).status_code == 403  # operador no
    conn = get_connection()
    with pytest.raises(Exception, match="no se puede modificar"):
        conn.execute("UPDATE auditoria SET usuario = 'otro'")
    with pytest.raises(Exception, match="no vuelve a vigente"):
        conn.execute("UPDATE ingresos SET estado_registro = 'vigente' WHERE id = ?", (entry_id,))
    conn.close()


def test_excel_marca_el_anulado_y_no_lo_cuenta():
    sid, _, entry_id = preparar()
    client.post(f"/api/entries/{entry_id}/anular", json={"motivo": "Duplicado", "session_id": sid})
    hoy = client.get("/api/recepciones/abierta", params={"session_id": sid}).json()["hora_llegada"][:10]
    wb = load_workbook(BytesIO(client.get("/api/export", params={"session_id": sid, "desde": hoy, "hasta": hoy}).content))
    fila = next(wb["Productos"].iter_rows(min_row=2, values_only=True))
    assert fila[18:20] == ("anulado", "Duplicado")
    assert next(wb["Recepciones"].iter_rows(min_row=2, values_only=True))[6] == 0
