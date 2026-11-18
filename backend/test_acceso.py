"""P21 · Acceso, usuario de la sesión y texto seguro (pruebas T13, T17, T18 y más)."""

import csv
from datetime import date, timedelta
from pathlib import Path

from backend._cliente_pruebas import ClienteConSesion, entrar_json
from backend.database import get_connection, init_db

from backend.main import app

client = ClienteConSesion(app)
CHECKS = {"empaque_ok": True, "sin_humedad": True, "temperatura_ok": True, "aspecto_olor_ok": True, "documentacion_proveedor_ok": True}


def setup_function() -> None:
    init_db()
    conn = get_connection()
    for tabla in ("ingresos", "recepciones", "pendientes", "sesiones"):
        conn.execute(f"DELETE FROM {tabla}")
    conn.commit()
    conn.close()


def entrar(nombre: str) -> str:
    response = client.post("/api/login", json=entrar_json(nombre))
    assert response.status_code == 200
    data = response.json()
    assert len(data["session_id"]) >= 32  # creado por el servidor, aleatorio
    return data["session_id"]


def recepcion(sid: str, doc: str) -> int:
    r = client.post("/api/recepciones", json={"session_id": sid, "proveedor": "VITA ALIMENTOS C.A", "documento_tipo": "factura", "documento_numero": doc})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def guardar(sid: str, rid: int, **extra) -> int:
    body = {"producto_id": 32, "cantidad_ingresada": 1, "lote": "L-ACC", "fecha_caducidad": (date.today() + timedelta(days=90)).isoformat(),
            "estado_qc": "aprobado", **CHECKS, "session_id": sid, "recepcion_id": rid, **extra}
    r = client.post("/api/entries", json=body)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_login_da_rol_desde_la_base():
    assert client.post("/api/login", json=entrar_json("Camilo")).json()["rol"] == "administrador"
    assert client.post("/api/login", json=entrar_json("Jose")).json()["rol"] == "operador"


def test_rutas_sin_sesion_o_con_sesion_inventada_se_rechazan():
    for metodo, ruta in [("get", "/api/providers"), ("get", "/api/entries"), ("get", "/api/proveedores"), ("post", "/api/entries/bulk")]:
        assert getattr(client, metodo)(ruta).status_code == 401, ruta
    assert client.get("/api/entries", headers={"X-Session-Id": "inventada"}).status_code == 401
    assert client.get("/api/health").status_code == 200
    assert "db" not in client.get("/api/health").json()


def test_t13_usuario_sale_de_la_sesion_no_del_formulario():
    sid = entrar("Jose")
    entry_id = guardar(sid, recepcion(sid, "A-1"), usuario_nombre="Otro")
    conn = get_connection()
    row = conn.execute("SELECT usuario_nombre, responsable_qc, session_id FROM ingresos WHERE id = ?", (entry_id,)).fetchone()
    conn.close()
    assert row["usuario_nombre"] == "Jose"
    assert row["responsable_qc"] == "Jose"  # por defecto, quien registra
    assert row["session_id"] == sid


def test_no_se_puede_usar_la_sesion_de_otro_en_el_cuerpo():
    jose = entrar("Jose")
    janet = entrar("Janet")
    # Janet manda en el cuerpo el session_id de Jose, pero su cabecera es la suya
    r = client.post("/api/recepciones", headers={"X-Session-Id": janet},
                    json={"session_id": jose, "proveedor": "VITA ALIMENTOS C.A", "documento_tipo": "guia", "documento_numero": "G-9"})
    assert r.json()["usuario_nombre"] == "Janet"


def test_t17_anular_sin_sesion_se_rechaza_y_operador_no_anula_lo_de_otro():
    jose = entrar("Jose")
    entry_id = guardar(jose, recepcion(jose, "B-1"))
    motivo = {"motivo": "Registro duplicado"}
    assert client.post(f"/api/entries/{entry_id}/anular", json=motivo).status_code == 401
    janet = entrar("Janet")
    assert client.post(f"/api/entries/{entry_id}/anular", json={**motivo, "session_id": janet}).status_code == 403
    camilo = entrar("Camilo")
    assert client.post(f"/api/entries/{entry_id}/anular", json={**motivo, "session_id": camilo}).status_code == 200


def test_t18_resumen_de_administracion_solo_para_administrador():
    assert client.get("/api/admin/summary").status_code == 401
    assert client.get("/api/admin/summary", params={"session_id": entrar("Jose")}).status_code == 403
    r = client.get("/api/admin/summary", params={"session_id": entrar("Camilo")})
    assert r.status_code == 200
    assert "db_file" not in r.json()


def test_sesion_vencida_y_cerrar_sesion():
    sid = entrar("Jose")
    conn = get_connection()
    conn.execute("UPDATE sesiones SET created_at = '2026-01-01T08:00:00-05:00' WHERE session_id = ?", (sid,))
    conn.commit()
    conn.close()
    assert client.get("/api/entries", params={"session_id": sid}).status_code == 401
    otra = entrar("Jose")
    assert client.post("/api/logout", json={"session_id": otra}).status_code == 200
    assert client.get("/api/entries", params={"session_id": otra}).status_code == 401
