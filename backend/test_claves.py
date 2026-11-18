"""P24 · Claves y datos personales (prueba T20: se bloquea tras varios intentos; no hay
claves en texto plano)."""

import csv
from datetime import timedelta
from pathlib import Path

from backend._cliente_pruebas import PINES_PRUEBA, ClienteConSesion, entrar_json
from backend.claves import INTENTOS_MAXIMOS, es_hash, hash_pin, problema_pin, verificar_pin
from backend.database import ensure_claves_seguras, get_connection, init_db
from backend.main import ahora_ec, app

client = ClienteConSesion(app)
CSV_REAL = Path(__file__).resolve().parent.parent / "insumos" / "usuarios.csv"


def setup_function() -> None:
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM sesiones")
    conn.execute("DELETE FROM auditoria")
    conn.execute("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL")
    conn.commit()
    conn.close()


def fallar(nombre: str = "Jose"):
    return client.post("/api/login", json={"usuario": nombre, "clave": "000001"})


def test_t20_el_csv_del_repositorio_no_tiene_claves_en_texto():
    filas = list(csv.DictReader(CSV_REAL.open(encoding="utf-8")))
    assert filas, "el CSV de usuarios no puede estar vacío"
    assert "clave" not in filas[0], "la columna con la clave en texto debe haber desaparecido"
    for fila in filas:
        assert es_hash(fila["clave_hash"]), fila["nombre"]
    texto = CSV_REAL.read_text(encoding="utf-8")
    for vieja in ("janet123", "jose123", "camilo123", "david123"):
        assert vieja not in texto


def test_t20_la_base_guarda_hash_y_no_el_pin():
    conn = get_connection()
    filas = conn.execute("SELECT nombre, clave FROM usuarios").fetchall()
    conn.close()
    for fila in filas:
        assert es_hash(fila["clave"])
        assert PINES_PRUEBA.get(fila["nombre"]) not in fila["clave"]


def test_entra_con_usuario_y_pin_sin_importar_mayusculas_ni_espacios():
    r = client.post("/api/login", json={"usuario": "  jose ", "clave": PINES_PRUEBA["Jose"]})
    assert r.status_code == 200
    assert r.json()["nombre"] == "Jose"
    assert client.post("/api/login", json=entrar_json("Camilo")).json()["rol"] == "administrador"


def test_el_pin_de_otro_usuario_no_sirve():
    r = client.post("/api/login", json={"usuario": "Jose", "clave": PINES_PRUEBA["Janet"]})
    assert r.status_code == 401


def test_mensaje_igual_si_falla_el_usuario_o_el_pin():
    no_existe = client.post("/api/login", json={"usuario": "Nadie", "clave": "592046"})
    pin_malo = fallar()
    assert no_existe.status_code == pin_malo.status_code == 401
    assert no_existe.json()["detail"] == pin_malo.json()["detail"] == "Usuario o PIN incorrecto."


def test_t20_se_bloquea_tras_5_intentos_y_avisa_antes():
    respuestas = [fallar() for _ in range(INTENTOS_MAXIMOS)]
    assert [r.status_code for r in respuestas] == [401] * (INTENTOS_MAXIMOS - 1) + [429]
    assert "Te quedan 3 intentos" in respuestas[1].json()["detail"]
    assert "Te queda 1 intento" in respuestas[3].json()["detail"]
    assert "bloqueado" in respuestas[-1].json()["detail"]
    # Bloqueado: ni siquiera el PIN correcto entra.
    r = client.post("/api/login", json=entrar_json("Jose"))
    assert r.status_code == 429 and "Espera" in r.json()["detail"]
    # Los demás usuarios no quedan bloqueados.
    assert client.post("/api/login", json=entrar_json("Janet")).status_code == 200


def test_t20_el_bloqueo_vence_y_se_reinicia_el_contador():
    for _ in range(INTENTOS_MAXIMOS):
        fallar()
    conn = get_connection()
    conn.execute(
        "UPDATE usuarios SET bloqueado_hasta = ? WHERE nombre = 'Jose'",
        ((ahora_ec() - timedelta(seconds=1)).isoformat(timespec="seconds"),),
    )
    conn.commit()
    conn.close()
    assert client.post("/api/login", json=entrar_json("Jose")).status_code == 200
    conn = get_connection()
    fila = conn.execute("SELECT intentos_fallidos, bloqueado_hasta FROM usuarios WHERE nombre = 'Jose'").fetchone()
    conn.close()
    assert fila["intentos_fallidos"] == 0 and fila["bloqueado_hasta"] is None


def test_entrar_bien_reinicia_los_intentos():
    fallar(); fallar(); fallar()
    assert client.post("/api/login", json=entrar_json("Jose")).status_code == 200
    respuestas = [fallar() for _ in range(INTENTOS_MAXIMOS - 1)]
    assert all(r.status_code == 401 for r in respuestas)  # vuelve a tener 5 intentos


def test_el_bloqueo_queda_en_la_auditoria():
    for _ in range(INTENTOS_MAXIMOS):
        fallar()
    conn = get_connection()
    fila = conn.execute("SELECT usuario, entidad, accion FROM auditoria WHERE accion = 'bloqueo_por_intentos'").fetchone()
    conn.close()
    assert fila is not None and fila["usuario"] == "Jose" and fila["entidad"] == "usuario"


def test_un_pin_enorme_se_rechaza_sin_calcular_el_hash():
    r = client.post("/api/login", json={"usuario": "Jose", "clave": "9" * 10_000})
    assert r.status_code == 422


def test_una_base_vieja_con_claves_en_texto_se_convierte_a_hash():
    conn = get_connection()
    conn.execute("INSERT INTO usuarios (id, nombre, clave, rol) VALUES (99, 'Viejo', 'viejo123', 'operador')")
    ensure_claves_seguras(conn.cursor())
    guardado = conn.execute("SELECT clave FROM usuarios WHERE id = 99").fetchone()[0]
    conn.execute("DELETE FROM usuarios WHERE id = 99")
    conn.commit()
    conn.close()
    assert es_hash(guardado) and verificar_pin("viejo123", guardado)


def test_hash_con_sal_distinta_y_reglas_del_pin_nuevo():
    a, b = hash_pin("592046", iteraciones=1_000), hash_pin("592046", iteraciones=1_000)
    assert a != b and verificar_pin("592046", a) and verificar_pin("592046", b)
    assert not verificar_pin("592047", a)
    assert problema_pin("12345") and problema_pin("12a456")          # no son 6 números
    assert problema_pin("123456") and problema_pin("777777")         # fáciles de adivinar
    assert problema_pin("345678") and problema_pin("987654")         # escaleras
    assert problema_pin("592046") is None
