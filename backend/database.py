import csv
import hashlib
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

import json
from datetime import datetime, timedelta, timezone

from backend.catalogo import UNIDADES_LLEGADA, UNIDADES_PLANTA, leer_version, revisar_catalogo
from backend.claves import es_hash, hash_pin

ROOT_DIR = Path(__file__).resolve().parent.parent
INSUMOS_DIR = ROOT_DIR / "insumos"


def _resolve_db_path() -> Path:
    """Ubicación de la base SQLite.

    - Local (por defecto): cyrano.db en la raíz del proyecto (comportamiento de siempre).
    - Vercel u otro serverless de filesystem de solo lectura: se usa /tmp, ya que la
      carpeta del despliegue no permite escritura. Nota: en Vercel /tmp es efímero, así
      que la base NO persiste entre invocaciones (solo sirve para demo de la interfaz).
    - Override manual con la variable de entorno CYRANO_DB_PATH.
    """
    override = os.getenv("CYRANO_DB_PATH")
    if override:
        return Path(override)
    if os.getenv("VERCEL"):
        return Path("/tmp/cyrano.db")
    return ROOT_DIR / "cyrano.db"


DB_PATH = _resolve_db_path()


def get_connection() -> sqlite3.Connection:
    """Crea una conexion a la base SQLite local."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> dict[str, Any]:
    """Crea las tablas y carga los datos de los CSV. Devuelve el resultado de cargar el catálogo (P25)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            clave TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY,
            codigo_cyrano TEXT NOT NULL,
            nombre_producto TEXT NOT NULL,
            codigo_barra TEXT,
            proveedor TEXT NOT NULL,
            unidad_llega TEXT NOT NULL,
            cantidad_asociada REAL NOT NULL,
            unidad_planta TEXT NOT NULL,
            factor_conversion REAL NOT NULL,
            cantidad_por_caja REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ingresos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            nombre_producto TEXT NOT NULL,
            codigo_cyrano TEXT NOT NULL,
            cantidad_ingresada REAL NOT NULL,
            unidad_llega TEXT NOT NULL,
            cantidad_convertida REAL NOT NULL,
            unidad_planta TEXT NOT NULL,
            codigo_barra TEXT,
            lote TEXT NOT NULL DEFAULT '',
            fecha_caducidad TEXT NOT NULL DEFAULT '',
            estado_qc TEXT NOT NULL DEFAULT '',
            responsable_qc TEXT NOT NULL DEFAULT '',
            observaciones_qc TEXT NOT NULL DEFAULT '',
            empaque_ok INTEGER NOT NULL DEFAULT 0,
            sin_humedad INTEGER NOT NULL DEFAULT 0,
            temperatura_ok INTEGER NOT NULL DEFAULT 0,
            aspecto_olor_ok INTEGER NOT NULL DEFAULT 0,
            documentacion_proveedor_ok INTEGER NOT NULL DEFAULT 0,
            temperatura_recepcion REAL,
            created_at TEXT NOT NULL,
            session_id TEXT NOT NULL DEFAULT '',
            usuario_nombre TEXT,
            FOREIGN KEY (producto_id) REFERENCES productos(id)
        );

        -- P06: ingresos pendientes de confirmar, guardados en el servidor para que no se
        -- pierdan al recargar, tocar «atrás» o cerrar sesión. Van ligados al usuario.
        CREATE TABLE IF NOT EXISTS pendientes (
            id TEXT PRIMARY KEY,
            usuario_nombre TEXT NOT NULL,
            datos TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sesiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL UNIQUE,
            usuario_nombre TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )

    ensure_ingresos_session_column(cursor)
    ensure_ingresos_user_column(cursor)
    ensure_ingresos_lote_columns(cursor)
    ensure_ingresos_qc_columns(cursor)
    ensure_sesiones_table(cursor)
    ensure_recepciones(cursor)
    ensure_reglas_base(cursor)
    ensure_roles(cursor)
    ensure_anulacion_y_auditoria(cursor)
    ensure_cuarentena_y_rechazo(cursor)

    ensure_claves_seguras(cursor)
    sincronizar_usuarios(cursor)
    ensure_catalogo(cursor)
    resultado_catalogo = sincronizar_catalogo(cursor)
    if cursor.execute("SELECT COUNT(*) FROM proveedores").fetchone()[0] == 0:
        load_proveedores(cursor)

    conn.commit()
    conn.close()
    return resultado_catalogo


def ensure_ingresos_session_column(cursor: sqlite3.Cursor) -> None:
    """Asegura que la tabla ingresos tenga los campos necesarios para sesiones y trazabilidad."""
    columns = [row[1] for row in cursor.execute("PRAGMA table_info(ingresos)").fetchall()]
    if "session_id" not in columns:
        cursor.execute("ALTER TABLE ingresos ADD COLUMN session_id TEXT NOT NULL DEFAULT ''")
    if "usuario_nombre" not in columns:
        cursor.execute("ALTER TABLE ingresos ADD COLUMN usuario_nombre TEXT NOT NULL DEFAULT ''")


def ensure_ingresos_user_column(cursor: sqlite3.Cursor) -> None:
    """Asegura que la tabla ingresos tenga el campo usuario_nombre para trazabilidad."""
    columns = [row[1] for row in cursor.execute("PRAGMA table_info(ingresos)").fetchall()]
    if "usuario_nombre" not in columns:
        cursor.execute("ALTER TABLE ingresos ADD COLUMN usuario_nombre TEXT")


def ensure_ingresos_lote_columns(cursor: sqlite3.Cursor) -> None:
    """Asegura que ingresos tenga lote y fecha_caducidad (clave del FIFO en despacho)."""
    columns = [row[1] for row in cursor.execute("PRAGMA table_info(ingresos)").fetchall()]
    if "lote" not in columns:
        cursor.execute("ALTER TABLE ingresos ADD COLUMN lote TEXT NOT NULL DEFAULT ''")
    if "fecha_caducidad" not in columns:
        cursor.execute("ALTER TABLE ingresos ADD COLUMN fecha_caducidad TEXT NOT NULL DEFAULT ''")


def ensure_ingresos_qc_columns(cursor: sqlite3.Cursor) -> None:
    """Asegura las columnas de Control de Calidad (QC) en ingresos, ligadas al lote.

    QC genérico para todos los productos. En el futuro, para QC por producto se podría
    agregar una tabla `qc_plantillas(articulo_id, checks_json, ...)` y resolver la
    plantilla por ArticuloID (producto_id) al recibir; estas columnas seguirían
    guardando el resultado del control de cada lote.
    """
    columns = [row[1] for row in cursor.execute("PRAGMA table_info(ingresos)").fetchall()]
    definiciones = {
        "estado_qc": "TEXT NOT NULL DEFAULT ''",
        "responsable_qc": "TEXT NOT NULL DEFAULT ''",
        "observaciones_qc": "TEXT NOT NULL DEFAULT ''",
        "empaque_ok": "INTEGER NOT NULL DEFAULT 0",
        "sin_humedad": "INTEGER NOT NULL DEFAULT 0",
        "temperatura_ok": "INTEGER NOT NULL DEFAULT 0",
        "aspecto_olor_ok": "INTEGER NOT NULL DEFAULT 0",
        "documentacion_proveedor_ok": "INTEGER NOT NULL DEFAULT 0",
        "temperatura_recepcion": "REAL",
    }
    for nombre, definicion in definiciones.items():
        if nombre not in columns:
            cursor.execute(f"ALTER TABLE ingresos ADD COLUMN {nombre} {definicion}")


def ensure_sesiones_table(cursor: sqlite3.Cursor) -> None:
    """Asegura que exista la tabla de sesiones para asociar cada sesión con un usuario."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sesiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL UNIQUE,
            usuario_nombre TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )


def ensure_recepciones(cursor: sqlite3.Cursor) -> None:
    """P02: la recepción (entrega de un proveedor) es la unidad de trabajo.

    Guarda proveedor, documento (factura o guía) y las horas de llegada, inicio de
    descarga y fin, con zona horaria explícita (-05:00). Cada ingreso cuelga de una
    recepción (ingresos.recepcion_id). Base para los KPI 1, 1b y 2 del piloto.
    """
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            compras INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS recepciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proveedor TEXT NOT NULL,
            documento_tipo TEXT NOT NULL CHECK (documento_tipo IN ('factura', 'guia')),
            documento_numero TEXT NOT NULL,
            hora_llegada TEXT NOT NULL,
            hora_inicio_descarga TEXT,
            inicio_automatico INTEGER NOT NULL DEFAULT 0,
            hora_fin TEXT,
            estado TEXT NOT NULL DEFAULT 'abierta' CHECK (estado IN ('abierta', 'cerrada', 'anulada')),
            usuario_nombre TEXT NOT NULL,
            session_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE (proveedor, documento_tipo, documento_numero)
        );
        """
    )
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(ingresos)").fetchall()}
    if "recepcion_id" not in columns:
        cursor.execute("ALTER TABLE ingresos ADD COLUMN recepcion_id INTEGER REFERENCES recepciones(id)")


def ensure_reglas_base(cursor: sqlite3.Cursor) -> None:
    """P20: reglas básicas también en la base (D14), para que no entre un registro malo
    aunque llegue por otro camino que no sea la API.

    SQLite no deja agregar CHECK a una tabla que ya existe, así que se usan disparadores
    (BEFORE INSERT/UPDATE) y un índice único para la línea (D11).
    """
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(ingresos)").fetchall()}
    if "linea_id" not in columns:
        cursor.execute("ALTER TABLE ingresos ADD COLUMN linea_id TEXT")
    cursor.executescript(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_ingresos_linea_id ON ingresos(linea_id) WHERE linea_id IS NOT NULL;

        DROP TRIGGER IF EXISTS tr_ingresos_reglas_insert;
        CREATE TRIGGER tr_ingresos_reglas_insert BEFORE INSERT ON ingresos
        BEGIN
            SELECT RAISE(ABORT, 'cantidad debe ser mayor que 0') WHERE NEW.cantidad_ingresada <= 0;
            SELECT RAISE(ABORT, 'cantidad convertida negativa') WHERE NEW.cantidad_convertida < 0;
            SELECT RAISE(ABORT, 'lote vacío o de más de 30 caracteres') WHERE length(trim(NEW.lote)) NOT BETWEEN 1 AND 30;
            SELECT RAISE(ABORT, 'caducidad no es una fecha AAAA-MM-DD') WHERE date(NEW.fecha_caducidad) IS NULL OR date(NEW.fecha_caducidad) <> NEW.fecha_caducidad;
            SELECT RAISE(ABORT, 'estado de calidad no válido') WHERE NEW.estado_qc NOT IN ('aprobado', 'cuarentena', 'rechazado');
            SELECT RAISE(ABORT, 'temperatura fuera de rango') WHERE NEW.temperatura_recepcion IS NOT NULL AND NEW.temperatura_recepcion NOT BETWEEN -30 AND 60;
            SELECT RAISE(ABORT, 'el producto no existe') WHERE NOT EXISTS (SELECT 1 FROM productos WHERE id = NEW.producto_id);
        END;

        DROP TRIGGER IF EXISTS tr_ingresos_reglas_update;
        CREATE TRIGGER tr_ingresos_reglas_update BEFORE UPDATE OF cantidad_ingresada, lote, fecha_caducidad, estado_qc ON ingresos
        BEGIN
            SELECT RAISE(ABORT, 'cantidad debe ser mayor que 0') WHERE NEW.cantidad_ingresada <= 0;
            SELECT RAISE(ABORT, 'lote vacío o de más de 30 caracteres') WHERE length(trim(NEW.lote)) NOT BETWEEN 1 AND 30;
            SELECT RAISE(ABORT, 'caducidad no es una fecha AAAA-MM-DD') WHERE date(NEW.fecha_caducidad) IS NULL OR date(NEW.fecha_caducidad) <> NEW.fecha_caducidad;
            SELECT RAISE(ABORT, 'estado de calidad no válido') WHERE NEW.estado_qc NOT IN ('aprobado', 'cuarentena', 'rechazado');
        END;
        """
    )


def ensure_roles(cursor: sqlite3.Cursor) -> None:
    """P21 / D20: rol de cada usuario en la base (antes se decidía por el nombre «Camilo»)."""
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(usuarios)").fetchall()}
    if "rol" not in columns:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT NOT NULL DEFAULT 'operador'")
        cursor.execute("UPDATE usuarios SET rol = 'administrador' WHERE lower(trim(nombre)) = 'camilo'")


def ensure_cuarentena_y_rechazo(cursor: sqlite3.Cursor) -> None:
    """P16: los lotes en cuarentena o rechazados se registran (con su motivo) sin pasar a
    inventario. La cuarentena se resuelve después: se libera (pasa a aprobado) o se rechaza,
    con quién, cuándo y por qué. Aprobado y rechazado son finales.
    """
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(ingresos)").fetchall()}
    for nombre, definicion in {
        "motivo_qc": "TEXT",          # por qué quedó en cuarentena o se rechazó
        "qc_resuelto_por": "TEXT",    # quién liberó o rechazó la cuarentena
        "qc_resuelto_at": "TEXT",
        "qc_resolucion": "TEXT",      # motivo de la liberación o del rechazo posterior
    }.items():
        if nombre not in columns:
            cursor.execute(f"ALTER TABLE ingresos ADD COLUMN {nombre} {definicion}")
    cursor.executescript(
        """
        DROP TRIGGER IF EXISTS tr_ingresos_motivo_qc;
        CREATE TRIGGER tr_ingresos_motivo_qc BEFORE INSERT ON ingresos
        BEGIN
            SELECT RAISE(ABORT, 'cuarentena o rechazo exige motivo')
            WHERE NEW.estado_qc IN ('cuarentena', 'rechazado') AND length(trim(coalesce(NEW.motivo_qc, ''))) < 3;
        END;
        DROP TRIGGER IF EXISTS tr_ingresos_qc_transicion;
        CREATE TRIGGER tr_ingresos_qc_transicion BEFORE UPDATE OF estado_qc ON ingresos
        WHEN OLD.estado_qc <> NEW.estado_qc
        BEGIN
            SELECT RAISE(ABORT, 'solo un lote en cuarentena cambia de estado (a aprobado o rechazado)')
            WHERE NOT (OLD.estado_qc = 'cuarentena' AND NEW.estado_qc IN ('aprobado', 'rechazado'));
            SELECT RAISE(ABORT, 'resolver la cuarentena exige quién y motivo')
            WHERE length(trim(coalesce(NEW.qc_resuelto_por, ''))) = 0 OR length(trim(coalesce(NEW.qc_resolucion, ''))) < 3;
        END;
        """
    )


def ensure_anulacion_y_auditoria(cursor: sqlite3.Cursor) -> None:
    """P22 / D18 (ALCOA «original»): un ingreso confirmado no se borra, se anula con
    motivo, usuario y hora; y cada alta, anulación y evento de la recepción queda en
    una tabla de auditoría que no se puede modificar.
    """
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(ingresos)").fetchall()}
    for nombre, definicion in {
        "estado_registro": "TEXT NOT NULL DEFAULT 'vigente'",
        "anulado_motivo": "TEXT",
        "anulado_por": "TEXT",
        "anulado_at": "TEXT",
    }.items():
        if nombre not in columns:
            cursor.execute(f"ALTER TABLE ingresos ADD COLUMN {nombre} {definicion}")
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            usuario TEXT NOT NULL,
            entidad TEXT NOT NULL,
            entidad_id INTEGER,
            accion TEXT NOT NULL,
            detalle TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS ix_auditoria_entidad ON auditoria(entidad, entidad_id);

        -- La auditoría no se edita.
        DROP TRIGGER IF EXISTS tr_auditoria_no_editar;
        CREATE TRIGGER tr_auditoria_no_editar BEFORE UPDATE ON auditoria
        BEGIN
            SELECT RAISE(ABORT, 'la auditoría no se puede modificar');
        END;

        -- Estado del registro válido; un anulado no vuelve a vigente; anular exige motivo.
        DROP TRIGGER IF EXISTS tr_ingresos_estado_registro;
        CREATE TRIGGER tr_ingresos_estado_registro BEFORE UPDATE OF estado_registro ON ingresos
        BEGIN
            SELECT RAISE(ABORT, 'estado de registro no válido') WHERE NEW.estado_registro NOT IN ('vigente', 'anulado');
            SELECT RAISE(ABORT, 'un ingreso anulado no vuelve a vigente') WHERE OLD.estado_registro = 'anulado';
            SELECT RAISE(ABORT, 'anular exige motivo') WHERE NEW.estado_registro = 'anulado' AND length(trim(coalesce(NEW.anulado_motivo, ''))) < 5;
        END;
        """
    )


def load_proveedores(cursor: sqlite3.Cursor) -> None:
    """Carga la lista de proveedores (insumos/proveedores.csv, sacada de MovCompras)."""
    path = INSUMOS_DIR / "proveedores.csv"
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            cursor.execute(
                "INSERT OR IGNORE INTO proveedores (nombre, compras) VALUES (?, ?)",
                (row["proveedor"].strip(), int(row["compras"] or 0)),
            )


# ---------- P23 · Catálogo: código SAP, unidades en lista cerrada, sin productos de ejemplo ----------
# Regla de conversión (D9): cantidad en unidad de planta = cantidad que llega × cantidad_por_caja × factor_conversion.
# Listas cerradas de unidades: viven en backend/catalogo.py (P25) y se importan arriba.
PRODUCTOS_EJEMPLO = ("HAR035", "HAR036", "M22", "MAN012", "CHO040", "HUE001")  # no son de Cyrano


def ensure_catalogo(cursor: sqlite3.Cursor) -> None:
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(productos)").fetchall()}
    if "codigo_sap" not in columns:
        cursor.execute("ALTER TABLE productos ADD COLUMN codigo_sap TEXT")
    if "equivalencia_sap" not in columns:
        cursor.execute("ALTER TABLE productos ADD COLUMN equivalencia_sap TEXT NOT NULL DEFAULT 'sin pareja'")
    llegada = ", ".join(f"'{u}'" for u in UNIDADES_LLEGADA)
    planta = ", ".join(f"'{u}'" for u in UNIDADES_PLANTA)
    reglas = f"""
            SELECT RAISE(ABORT, 'unidad de llegada fuera de la lista') WHERE NEW.unidad_llega NOT IN ({llegada});
            SELECT RAISE(ABORT, 'unidad de planta fuera de la lista') WHERE NEW.unidad_planta NOT IN ({planta});
            SELECT RAISE(ABORT, 'factor de conversión debe ser mayor que 0') WHERE NEW.factor_conversion <= 0;
            SELECT RAISE(ABORT, 'unidades por empaque debe ser un entero mayor o igual a 1')
                WHERE NEW.cantidad_por_caja < 1 OR NEW.cantidad_por_caja <> CAST(NEW.cantidad_por_caja AS INTEGER);
    """
    cursor.executescript(f"""
        DROP TRIGGER IF EXISTS tr_productos_reglas_insert;
        CREATE TRIGGER tr_productos_reglas_insert BEFORE INSERT ON productos BEGIN {reglas} END;
        DROP TRIGGER IF EXISTS tr_productos_reglas_update;
        CREATE TRIGGER tr_productos_reglas_update BEFORE UPDATE ON productos BEGIN {reglas} END;
    """)


def ruta_productos() -> Path:
    # Las pruebas pueden usar otro CSV (variable CYRANO_PRODUCTOS_CSV).
    return Path(os.getenv("CYRANO_PRODUCTOS_CSV") or INSUMOS_DIR / "productos.csv")


def _ahora_ec() -> str:
    return datetime.now(timezone(timedelta(hours=-5))).isoformat(timespec="seconds")


def _tablas_catalogo(cursor: sqlite3.Cursor) -> None:
    cursor.execute("CREATE TABLE IF NOT EXISTS catalogo_version (id INTEGER PRIMARY KEY CHECK (id = 1), huella TEXT NOT NULL, cargado_at TEXT NOT NULL)")
    columnas = {row[1] for row in cursor.execute("PRAGMA table_info(catalogo_version)").fetchall()}
    for columna in ("version TEXT", "fuente TEXT", "filas INTEGER", "estado TEXT", "mensaje TEXT", "avisos TEXT", "huella_rechazada TEXT"):
        if columna.split()[0] not in columnas:
            cursor.execute(f"ALTER TABLE catalogo_version ADD COLUMN {columna}")
    # Historial de cada intento de carga (aplicado, parcial o rechazado).
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogo_cargas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            version TEXT,
            huella TEXT NOT NULL,
            resultado TEXT NOT NULL CHECK (resultado IN ('aplicado', 'parcial', 'rechazado')),
            filas INTEGER,
            mensaje TEXT
        )
        """
    )


def sincronizar_catalogo(cursor: sqlite3.Cursor) -> dict[str, Any]:
    """P25 / T22: carga el catálogo de productos.csv cuando cambia, o avisa por qué no.

    - Se guarda una huella del CSV; si no cambió, no se hace nada.
    - Antes de aplicar, se revisa entero (backend/catalogo.py). Si tiene ERRORES y ya hay un
      catálogo cargado, NO se aplica: se queda el anterior y se guarda el motivo. Si la base
      está vacía (p. ej. arranque en Vercel), se cargan las filas sin error y queda «parcial».
    - Los AVISOS (dígito GS1, barras repetidas, código con dos nombres) se guardan para el
      administrador; esos productos sí se cargan.
    - Se quitan los productos que ya no están, salvo los que tienen ingresos (trazabilidad).
    """
    _tablas_catalogo(cursor)
    path = ruta_productos()
    # P10: la huella incluye también la relación producto–proveedor (si cambia, se recarga).
    archivo_pp = path.parent / "producto_proveedor.csv"
    huella = hashlib.sha256(path.read_bytes() + (archivo_pp.read_bytes() if archivo_pp.exists() else b"")).hexdigest()
    actual = cursor.execute("SELECT huella, huella_rechazada FROM catalogo_version WHERE id = 1").fetchone()
    hay_productos = cursor.execute("SELECT COUNT(*) FROM productos").fetchone()[0] > 0
    if hay_productos and actual and huella in (actual[0], actual[1]):
        return {"resultado": "sin cambios"}

    with path.open("r", encoding="utf-8", newline="") as handle:
        filas = list(csv.DictReader(handle))
    revision = revisar_catalogo(filas)
    version = leer_version(path)
    numero = str(version.get("version", "sin versión"))
    avisos = revision["avisos"]
    errores = revision["errores"]
    ahora = _ahora_ec()

    if errores and hay_productos:
        mensaje = (f"No se aplicó la versión {numero} del catálogo: tiene {len(errores)} error(es). Se sigue usando la anterior. "
                   + " · ".join(errores[:5]) + (" · …" if len(errores) > 5 else ""))
        cursor.execute("UPDATE catalogo_version SET huella_rechazada = ?, mensaje = ? WHERE id = 1", (huella, mensaje))
        cursor.execute("INSERT INTO catalogo_cargas (fecha, version, huella, resultado, filas, mensaje) VALUES (?, ?, ?, 'rechazado', ?, ?)",
                       (ahora, numero, huella, len(filas), mensaje))
        return {"resultado": "rechazado", "mensaje": mensaje, "errores": errores}

    validas = revision["filas_validas"]
    ids = load_productos(cursor, validas)
    cargar_producto_proveedor(cursor, archivo_pp)
    marcas = ", ".join("?" for _ in ids) or "NULL"
    cursor.execute(
        f"DELETE FROM productos WHERE id NOT IN ({marcas}) AND id NOT IN (SELECT producto_id FROM ingresos WHERE producto_id IS NOT NULL)",
        tuple(ids),
    )
    resultado = "parcial" if errores else "aplicado"
    mensaje = (f"Versión {numero} cargada: {len(validas)} productos."
               + (f" {len(errores)} fila(s) con error no se cargaron: " + " · ".join(errores[:5]) if errores else ""))
    cursor.execute(
        """
        INSERT INTO catalogo_version (id, huella, cargado_at, version, fuente, filas, estado, mensaje, avisos, huella_rechazada)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(id) DO UPDATE SET huella = excluded.huella, cargado_at = excluded.cargado_at, version = excluded.version,
            fuente = excluded.fuente, filas = excluded.filas, estado = excluded.estado, mensaje = excluded.mensaje,
            avisos = excluded.avisos, huella_rechazada = NULL
        """,
        (huella, ahora, numero, str(version.get("fuente", "")), len(validas), resultado, mensaje, json.dumps(avisos, ensure_ascii=False)),
    )
    cursor.execute("INSERT INTO catalogo_cargas (fecha, version, huella, resultado, filas, mensaje) VALUES (?, ?, ?, ?, ?, ?)",
                   (ahora, numero, huella, resultado, len(validas), mensaje))
    return {"resultado": resultado, "mensaje": mensaje, "errores": errores}


def cargar_producto_proveedor(cursor: sqlite3.Cursor, archivo: Path) -> int:
    """P10: qué proveedores han traído cada artículo (de MovCompras; solo nombres)."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS producto_proveedor (
            codigo TEXT NOT NULL,
            proveedor TEXT NOT NULL,
            entradas INTEGER NOT NULL DEFAULT 0,
            ultima_entrada TEXT,
            PRIMARY KEY (codigo, proveedor)
        )
        """
    )
    cursor.execute("DELETE FROM producto_proveedor")
    if not archivo.exists():
        return 0
    with archivo.open("r", encoding="utf-8", newline="") as handle:
        filas = [(f["codigo"].strip(), " ".join(f["proveedor"].split()), int(f["entradas"] or 0), f["ultima_entrada"] or None)
                 for f in csv.DictReader(handle) if f.get("codigo") and f.get("proveedor")]
    cursor.executemany("INSERT OR REPLACE INTO producto_proveedor VALUES (?, ?, ?, ?)", filas)
    return len(filas)


def ensure_claves_seguras(cursor: sqlite3.Cursor) -> None:
    """P24 / D21: contador de intentos fallidos y bloqueo temporal por usuario; y si una
    base vieja todavía tiene claves en texto, se convierten a hash en el sitio.
    """
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(usuarios)").fetchall()}
    if "intentos_fallidos" not in columns:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN intentos_fallidos INTEGER NOT NULL DEFAULT 0")
    if "bloqueado_hasta" not in columns:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueado_hasta TEXT")
    for row in cursor.execute("SELECT id, clave FROM usuarios").fetchall():
        if not es_hash(row[1]):
            cursor.execute("UPDATE usuarios SET clave = ? WHERE id = ?", (hash_pin(str(row[1])), row[0]))


def sincronizar_usuarios(cursor: sqlite3.Cursor) -> None:
    """Carga o actualiza los usuarios desde insumos/usuarios.csv.

    P24: el CSV ya no trae la clave, sino su hash (columna «clave_hash»). Se sincroniza
    en cada arranque, así que cambiar un PIN con el script de cambios-interfaz/scripts_p24
    se aplica también a una base que ya existía.
    """
    # Las pruebas automáticas usan su propio CSV con PIN de prueba (variable CYRANO_USUARIOS_CSV).
    path = Path(os.getenv("CYRANO_USUARIOS_CSV") or INSUMOS_DIR / "usuarios.csv")
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            # P21: el rol viene en la columna «rol» del CSV (operador / administrador).
            rol = (row.get("rol") or "").strip().lower() or "operador"
            guardado = (row.get("clave_hash") or "").strip()
            if not es_hash(guardado):
                # CSV antiguo con la clave en texto: se guarda solo su hash.
                guardado = hash_pin((row.get("clave") or "").strip() or secrets.token_hex(16))
            actual = cursor.execute("SELECT clave FROM usuarios WHERE id = ?", (int(row["id"]),)).fetchone()
            if actual is None:
                cursor.execute(
                    "INSERT INTO usuarios (id, nombre, clave, rol) VALUES (?, ?, ?, ?)",
                    (int(row["id"]), row["nombre"].strip(), guardado, rol),
                )
            elif actual[0] != guardado:
                # PIN nuevo: se reemplaza y se limpia cualquier bloqueo.
                cursor.execute(
                    "UPDATE usuarios SET nombre = ?, clave = ?, rol = ?, intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id = ?",
                    (row["nombre"].strip(), guardado, rol, int(row["id"])),
                )
            else:
                cursor.execute("UPDATE usuarios SET nombre = ?, rol = ? WHERE id = ?", (row["nombre"].strip(), rol, int(row["id"])))


def load_productos(cursor: sqlite3.Cursor, filas: list[dict[str, Any]] | None = None) -> list[int]:
    """Carga (o actualiza por id) productos; devuelve los ids. Sin filas, lee el CSV tal cual."""
    if filas is None:
        with ruta_productos().open("r", encoding="utf-8", newline="") as handle:
            filas = list(csv.DictReader(handle))
    ids: list[int] = []
    for row in filas:
        ids.append(int(row["id"]))
        cursor.execute(
            """
            INSERT INTO productos (
                id,
                codigo_cyrano,
                nombre_producto,
                codigo_barra,
                proveedor,
                unidad_llega,
                cantidad_asociada,
                unidad_planta,
                factor_conversion,
                cantidad_por_caja,
                codigo_sap,
                equivalencia_sap
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                codigo_cyrano = excluded.codigo_cyrano, nombre_producto = excluded.nombre_producto,
                codigo_barra = excluded.codigo_barra, proveedor = excluded.proveedor,
                unidad_llega = excluded.unidad_llega, cantidad_asociada = excluded.cantidad_asociada,
                unidad_planta = excluded.unidad_planta, factor_conversion = excluded.factor_conversion,
                cantidad_por_caja = excluded.cantidad_por_caja, codigo_sap = excluded.codigo_sap,
                equivalencia_sap = excluded.equivalencia_sap
            """,
            (
                int(row["id"]),
                row["codigo_cyrano"],
                row["nombre_producto"],
                row["codigo_barra"] or None,
                row["proveedor"],
                row["unidad_llega"].strip().lower(),
                float(row["cantidad_asociada"]),
                {"unidad": "unid"}.get(row["unidad_planta"].strip().lower(), row["unidad_planta"].strip().lower()),
                float(row["factor_conversion"]),
                float(row["cantidad_por_caja"]),
                (row.get("codigo_sap") or "").strip() or None,
                (row.get("equivalencia_sap") or "sin pareja").strip(),
            ),
        )
    return ids


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    return rows
