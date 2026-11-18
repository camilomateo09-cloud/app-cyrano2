from backend._cliente_pruebas import ClienteConSesion

from backend.database import get_connection, init_db
from backend.main import ahora_iso, app

client = ClienteConSesion(app)


RECEPCIONES: dict[str, int] = {}
# Puntos del checklist marcados (son opcionales; solo el estado es obligatorio).
CHECKS = {"empaque_ok": True, "sin_humedad": True, "temperatura_ok": True, "aspecto_olor_ok": True, "documentacion_proveedor_ok": True}


def _sesion_con_recepcion(session_id: str, usuario: str) -> int:
    """P02: cada ingreso cuelga de una recepción abierta del usuario de la sesión."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO sesiones (session_id, usuario_nombre, created_at) VALUES (?, ?, ?)",
        (session_id, usuario, ahora_iso()),
    )
    conn.commit()
    conn.close()
    response = client.post(
        "/api/recepciones",
        json={"session_id": session_id, "proveedor": "PROVEEDOR PRUEBA", "documento_tipo": "factura", "documento_numero": f"F-{session_id}"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def setup_function() -> None:
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM ingresos")
    conn.execute("DELETE FROM recepciones")
    conn.execute("DELETE FROM pendientes")
    conn.commit()
    conn.close()
    RECEPCIONES.clear()
    for session_id, usuario in [("session-a", "Janet"), ("session-b", "Jose"), ("camilo-session", "Camilo")]:
        RECEPCIONES[session_id] = _sesion_con_recepcion(session_id, usuario)


def test_entries_are_scoped_by_session_id() -> None:
    first = client.post(
        "/api/entries",
        json={"producto_id": 1, "cantidad_ingresada": 2, "lote": "L-A1", "fecha_caducidad": "2026-12-31", "estado_qc": "aprobado", **CHECKS, "responsable_qc": "QC", "session_id": "session-a", "usuario_nombre": "Janet", "recepcion_id": RECEPCIONES["session-a"]},
    )
    second = client.post(
        "/api/entries",
        json={"producto_id": 1, "cantidad_ingresada": 3, "lote": "L-B1", "fecha_caducidad": "2026-12-31", "estado_qc": "aprobado", **CHECKS, "responsable_qc": "QC", "session_id": "session-b", "usuario_nombre": "Jose", "recepcion_id": RECEPCIONES["session-b"]},
    )

    assert first.status_code == 200
    assert second.status_code == 200

    response = client.get("/api/entries", params={"session_id": "session-a"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["cantidad_ingresada"] == 2


def test_admin_summary_uses_session_user_name() -> None:
    created = client.post(
        "/api/entries",
        json={"producto_id": 462, "cantidad_ingresada": 2, "lote": "L-C1", "fecha_caducidad": "2026-12-31", "estado_qc": "aprobado", **CHECKS, "responsable_qc": "QC", "session_id": "camilo-session", "usuario_nombre": "Camilo", "recepcion_id": RECEPCIONES["camilo-session"]},
    )
    assert created.status_code == 200

    summary = client.get("/api/admin/summary", params={"usuario": "Camilo", "session_id": "camilo-session"})
    assert summary.status_code == 200
    data = summary.json()
    assert data["filtro_actual"] == "Camilo"
    assert any(item["usuario_nombre"] == "Camilo" for item in data["ingresos_filtrados"])


def test_delete_entry_and_admin_filter_by_user() -> None:
    created = client.post(
        "/api/entries",
        json={"producto_id": 462, "cantidad_ingresada": 2, "lote": "L-A2", "fecha_caducidad": "2026-12-31", "estado_qc": "aprobado", **CHECKS, "responsable_qc": "QC", "session_id": "session-a", "usuario_nombre": "Janet", "recepcion_id": RECEPCIONES["session-a"]},
    )
    assert created.status_code == 200
    entry_id = created.json()["id"]

    # P22: ya no se borra; se anula con motivo y sigue en la lista marcado como anulado.
    anulado = client.post(f"/api/entries/{entry_id}/anular", json={"motivo": "Cantidad mal escrita", "session_id": "session-a"})
    assert anulado.status_code == 200

    remaining = client.get("/api/entries", params={"session_id": "session-a"})
    assert remaining.status_code == 200
    assert [e["estado_registro"] for e in remaining.json()] == ["anulado"]

    created_second = client.post(
        "/api/entries",
        json={"producto_id": 462, "cantidad_ingresada": 3, "lote": "L-B2", "fecha_caducidad": "2026-12-31", "estado_qc": "aprobado", **CHECKS, "responsable_qc": "QC", "session_id": "session-b", "usuario_nombre": "Jose", "recepcion_id": RECEPCIONES["session-b"]},
    )
    assert created_second.status_code == 200

    summary = client.get("/api/admin/summary", params={"usuario": "Jose", "session_id": "camilo-session"})
    assert summary.status_code == 200
    data = summary.json()
    assert data["filtro_actual"] == "Jose"
    assert len(data["ingresos_filtrados"]) == 1
    assert data["ingresos_filtrados"][0]["usuario_nombre"] == "Jose"


def test_entry_without_reception_is_rejected() -> None:
    response = client.post(
        "/api/entries",
        json={"producto_id": 1, "cantidad_ingresada": 2, "lote": "L-X", "fecha_caducidad": "2026-12-31", "estado_qc": "aprobado", **CHECKS, "session_id": "session-a"},
    )
    assert response.status_code == 422
    assert "recepción" in response.json()["detail"]


def test_reception_times_and_close() -> None:
    rid = RECEPCIONES["session-a"]
    # no se puede abrir otra mientras haya una abierta, ni repetir documento del mismo proveedor
    again = client.post("/api/recepciones", json={"session_id": "session-a", "proveedor": "OTRO", "documento_tipo": "guia", "documento_numero": "G-1"})
    assert again.status_code == 409
    dup = client.post("/api/recepciones", json={"session_id": "session-b", "proveedor": "PROVEEDOR PRUEBA", "documento_tipo": "factura", "documento_numero": "F-session-a"})
    assert dup.status_code == 409

    started = client.post(f"/api/recepciones/{rid}/inicio", json={"session_id": "session-a"}).json()
    assert started["hora_inicio_descarga"].endswith("-05:00")
    assert started["inicio_automatico"] == 0

    saved = client.post(
        "/api/entries",
        json={"producto_id": 1, "cantidad_ingresada": 1, "lote": "L-R1", "fecha_caducidad": "2026-12-31", "estado_qc": "aprobado", **CHECKS, "session_id": "session-a", "recepcion_id": rid},
    )
    assert saved.status_code == 200

    closed = client.post(f"/api/recepciones/{rid}/cerrar", json={"session_id": "session-a"}).json()
    assert closed["estado"] == "cerrada"
    assert closed["hora_llegada"] <= closed["hora_inicio_descarga"] <= closed["hora_fin"]
    assert closed["ingresos_confirmados"] == 1

    after = client.post(
        "/api/entries",
        json={"producto_id": 1, "cantidad_ingresada": 1, "lote": "L-R2", "fecha_caducidad": "2026-12-31", "estado_qc": "aprobado", **CHECKS, "session_id": "session-a", "recepcion_id": rid},
    )
    assert after.status_code == 422


def test_pending_blocks_close_and_marks_start() -> None:
    rid = RECEPCIONES["session-b"]
    put = client.put(
        "/api/pending/1731300000000",
        json={"session_id": "session-b", "datos": {"id": 1731300000000, "producto_id": 1, "recepcion_id": rid}},
    )
    assert put.status_code == 200
    rec = client.get("/api/recepciones/abierta", params={"session_id": "session-b"}).json()
    assert rec["hora_inicio_descarga"] is not None and rec["inicio_automatico"] == 1
    blocked = client.post(f"/api/recepciones/{rid}/cerrar", json={"session_id": "session-b"})
    assert blocked.status_code == 422


def test_export_excel_has_receptions_and_products() -> None:
    from io import BytesIO

    from openpyxl import load_workbook

    rid = RECEPCIONES["session-a"]
    client.post(
        "/api/entries",
        json={"producto_id": 32, "cantidad_ingresada": 1, "lote": "L-EX", "fecha_caducidad": "2026-12-31", "estado_qc": "aprobado", **CHECKS, "session_id": "session-a", "recepcion_id": rid},
    )
    client.post(f"/api/recepciones/{rid}/cerrar", json={"session_id": "session-a"})
    hoy = client.get("/api/recepciones/abierta", params={"session_id": "session-b"}).json()["hora_llegada"][:10]

    response = client.get("/api/export", params={"session_id": "session-a", "desde": hoy, "hasta": hoy})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
    wb = load_workbook(BytesIO(response.content))
    assert wb.sheetnames == ["Resumen", "Recepciones", "Productos", "Leyenda"]
    recepciones = list(wb["Recepciones"].iter_rows(min_row=2, values_only=True))
    assert len(recepciones) == 3  # las 3 recepciones de prueba
    productos = list(wb["Productos"].iter_rows(min_row=2, values_only=True))
    assert any(row[13] == "L-EX" and row[11] == 22.71 and row[6] == "MT041" for row in productos)

    sin_sesion = client.get("/api/export", params={"session_id": "no-existe", "desde": hoy, "hasta": hoy})
    assert sin_sesion.status_code == 401
