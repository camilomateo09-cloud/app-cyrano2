"""P16 · Cuarentena y rechazo (prueba del plan: un rechazo queda registrado con su motivo)."""

import sqlite3
from datetime import date, timedelta
from io import BytesIO

import pytest
from openpyxl import load_workbook

from backend._cliente_pruebas import ClienteConSesion, entrar_json
from backend.database import get_connection, init_db
from backend.main import app

client = ClienteConSesion(app)
CAD = (date.today() + timedelta(days=90)).isoformat()


def setup_function() -> None:
    init_db()
    conn = get_connection()
    for tabla in ("ingresos", "recepciones", "pendientes", "sesiones", "auditoria"):
        conn.execute(f"DELETE FROM {tabla}")
    conn.commit()
    conn.close()


def recepcion(nombre: str = "Jose") -> tuple[str, int]:
    sid = client.post("/api/login", json=entrar_json(nombre)).json()["session_id"]
    rid = client.post("/api/recepciones", json={"session_id": sid, "proveedor": "VITA ALIMENTOS C.A", "documento_tipo": "factura", "documento_numero": f"QC-{nombre}"}).json()["id"]
    return sid, rid


def linea(sid, rid, estado, motivo=None, lote="L-QC", linea_id=None):
    return {"producto_id": 32, "cantidad_ingresada": 2, "lote": lote, "fecha_caducidad": CAD, "estado_qc": estado,
            "motivo_qc": motivo, "session_id": sid, "recepcion_id": rid, "linea_id": linea_id}


def fila(entry_id):
    conn = get_connection()
    try:
        return conn.execute("SELECT * FROM ingresos WHERE id = ?", (entry_id,)).fetchone()
    finally:
        conn.close()


def test_un_rechazo_queda_registrado_con_su_motivo():
    sid, rid = recepcion()
    r = client.post("/api/entries", json=linea(sid, rid, "rechazado", "Empaque dañado"))
    assert r.status_code == 200, r.text
    f = fila(r.json()["id"])
    assert f["estado_qc"] == "rechazado" and f["motivo_qc"] == "Empaque dañado" and f["estado_registro"] == "vigente"
    conn = get_connection()
    ev = conn.execute("SELECT detalle FROM auditoria WHERE accion = 'alta'").fetchone()
    conn.close()
    assert "Empaque dañado" in ev["detalle"]


def test_cuarentena_y_rechazo_exigen_motivo():
    sid, rid = recepcion()
    for estado in ("cuarentena", "rechazado"):
        r = client.post("/api/entries", json=linea(sid, rid, estado, "  "))
        assert r.status_code == 422 and "falta el motivo" in r.json()["detail"]
    assert client.post("/api/entries", json=linea(sid, rid, "aprobado")).status_code == 200


def test_la_base_tambien_exige_el_motivo():
    sid, rid = recepcion()
    conn = get_connection()
    try:
        with pytest.raises(sqlite3.IntegrityError, match="exige motivo"):
            conn.execute(
                "INSERT INTO ingresos (producto_id, nombre_producto, codigo_cyrano, cantidad_ingresada, unidad_llega, cantidad_convertida, "
                "unidad_planta, lote, fecha_caducidad, estado_qc, created_at, recepcion_id) "
                "VALUES (32, 'X', 'MT041', 1, 'caja', 1, 'l', 'L1', ?, 'rechazado', '2026-11-18T10:00:00-05:00', ?)", (CAD, rid))
    finally:
        conn.close()


def test_confirmar_una_lista_mezclada_guarda_todo():
    sid, rid = recepcion()
    r = client.post("/api/entries/bulk", json={"session_id": sid, "entries": [
        linea(sid, rid, "aprobado", lote="A1", linea_id="l1"),
        linea(sid, rid, "cuarentena", "Temperatura fuera de rango", lote="C1", linea_id="l2"),
        linea(sid, rid, "rechazado", "Humedad", lote="R1", linea_id="l3"),
    ]})
    assert r.status_code == 200, r.text
    conn = get_connection()
    estados = sorted(x[0] for x in conn.execute("SELECT estado_qc FROM ingresos").fetchall())
    conn.close()
    assert estados == ["aprobado", "cuarentena", "rechazado"]


def test_el_administrador_libera_o_rechaza_la_cuarentena_con_motivo():
    sid, rid = recepcion()
    c1 = client.post("/api/entries", json=linea(sid, rid, "cuarentena", "Temperatura fuera de rango", lote="C1")).json()["id"]
    c2 = client.post("/api/entries", json=linea(sid, rid, "cuarentena", "Olor o aspecto raro", lote="C2")).json()["id"]
    admin = client.post("/api/login", json=entrar_json("Camilo")).json()["session_id"]
    lista = client.get("/api/admin/cuarentena", params={"session_id": admin}).json()
    assert {x["id"] for x in lista} == {c1, c2}
    assert client.post(f"/api/admin/ingresos/{c1}/calidad", json={"session_id": admin, "estado": "aprobado", "motivo": ""}).status_code == 422
    r = client.post(f"/api/admin/ingresos/{c1}/calidad", json={"session_id": admin, "estado": "aprobado", "motivo": "Temperatura verificada: 4 °C"})
    assert r.status_code == 200 and "pasa a inventario" in r.json()["message"]
    r = client.post(f"/api/admin/ingresos/{c2}/calidad", json={"session_id": admin, "estado": "rechazado", "motivo": "Olor confirmado"})
    assert r.status_code == 200
    f1, f2 = fila(c1), fila(c2)
    assert f1["estado_qc"] == "aprobado" and f1["qc_resuelto_por"] == "Camilo" and f1["qc_resolucion"] == "Temperatura verificada: 4 °C"
    assert f1["motivo_qc"] == "Temperatura fuera de rango"  # el motivo original se conserva
    assert f2["estado_qc"] == "rechazado" and f2["qc_resuelto_at"].endswith("-05:00")
    assert client.get("/api/admin/cuarentena", params={"session_id": admin}).json() == []
    # Aprobado y rechazado son finales.
    assert client.post(f"/api/admin/ingresos/{c1}/calidad", json={"session_id": admin, "estado": "rechazado", "motivo": "cambio"}).status_code == 409
    conn = get_connection()
    acciones = sorted(x[0] for x in conn.execute("SELECT accion FROM auditoria WHERE accion IN ('liberacion','rechazo_cuarentena')").fetchall())
    conn.close()
    assert acciones == ["liberacion", "rechazo_cuarentena"]


def test_el_operador_no_resuelve_la_cuarentena():
    sid, rid = recepcion()
    c = client.post("/api/entries", json=linea(sid, rid, "cuarentena", "Humedad")).json()["id"]
    r = client.post(f"/api/admin/ingresos/{c}/calidad", json={"session_id": sid, "estado": "aprobado", "motivo": "ok ok"})
    assert r.status_code == 403


def test_la_base_no_deja_cambiar_un_estado_final():
    sid, rid = recepcion()
    a = client.post("/api/entries", json=linea(sid, rid, "aprobado")).json()["id"]
    conn = get_connection()
    try:
        with pytest.raises(sqlite3.IntegrityError, match="solo un lote en cuarentena"):
            conn.execute("UPDATE ingresos SET estado_qc = 'rechazado', qc_resuelto_por = 'x', qc_resolucion = 'xyz' WHERE id = ?", (a,))
    finally:
        conn.close()


def test_etiquetas_rechazado_no_y_cuarentena_con_aviso():
    sid, rid = recepcion()
    rech = client.post("/api/entries", json=linea(sid, rid, "rechazado", "Humedad", lote="R1")).json()["id"]
    cuar = client.post("/api/entries", json=linea(sid, rid, "cuarentena", "Humedad", lote="C1")).json()["id"]
    admin = client.post("/api/login", json=entrar_json("Camilo")).json()["session_id"]
    r = client.post("/api/print/label", json={"session_id": admin, "entry_id": rech, "cantidad": 1, "test_mode": True})
    assert r.status_code == 422 and "rechazado" in r.json()["detail"]
    r = client.post("/api/print/label", json={"session_id": admin, "entry_id": cuar, "cantidad": 1, "test_mode": True})
    assert r.status_code == 200 and "EN CUARENTENA - NO USAR" in r.json()["zpl"]


def test_el_excel_muestra_el_destino_y_cuenta_por_calidad():
    sid, rid = recepcion()
    client.post("/api/entries/bulk", json={"session_id": sid, "entries": [
        linea(sid, rid, "aprobado", lote="A1", linea_id="e1"),
        linea(sid, rid, "cuarentena", "Humedad", lote="C1", linea_id="e2"),
        linea(sid, rid, "rechazado", "Empaque dañado", lote="R1", linea_id="e3"),
    ]})
    hoy = date.today().isoformat()
    r = client.get("/api/export", params={"session_id": sid, "desde": hoy, "hasta": hoy})
    assert r.status_code == 200
    wb = load_workbook(BytesIO(r.content))
    ws = wb["Productos"]
    encabezado = [c.value for c in ws[1]]
    col = {n: i for i, n in enumerate(encabezado)}
    filas = {row[col["Lote"]]: row for row in ws.iter_rows(min_row=2, values_only=True)}
    assert filas["A1"][col["Destino"]] == "Inventario"
    assert filas["C1"][col["Destino"]] == "Retenido (cuarentena)" and filas["C1"][col["Motivo de calidad"]] == "Humedad"
    assert filas["R1"][col["Destino"]] == "No ingresa (rechazado)"
    resumen = [row for row in wb["Resumen"].iter_rows(values_only=True) if row[0]]
    nombres = [row[0] for row in resumen]
    assert "Pasan a inventario (aprobados)" in nombres and "Rechazados (no ingresan)" in nombres
    # La fórmula usa la columna de calidad (P) y la del registro (S)
    formula = next(row[1] for row in resumen if row[0] == "Pasan a inventario (aprobados)")
    assert "Productos!P2" in formula and "Productos!S2" in formula and encabezado[15] == "Calidad" and encabezado[18] == "Estado del registro"
