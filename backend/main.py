import json
import secrets
from contextvars import ContextVar
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.claves import HASH_RELLENO, INTENTOS_MAXIMOS, MINUTOS_BLOQUEO, verificar_pin
from backend.database import get_connection, init_db
from backend.gs1 import gtins_equivalentes, leer_gs1
from backend.printer import build_label_zpl, printer_info, send_zpl
from backend.reglas import producto_existente, validar_calidad, validar_cantidad, validar_caducidad, validar_lote

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"

app = FastAPI(title="Cyrano Bodega", version="1.0.0")

# D17: horas con zona horaria explícita. Ecuador continental es UTC-5 todo el año
# (sin horario de verano); se usa un desfase fijo para no depender de tzdata en Vercel.
ZONA_EC = timezone(timedelta(hours=-5), "America/Guayaquil")


_CAMPOS = {
    "cantidad_ingresada": "la cantidad", "producto_id": "el producto", "lote": "el lote",
    "fecha_caducidad": "la fecha de caducidad", "estado_qc": "el estado de calidad",
    "temperatura_recepcion": "la temperatura de recepción", "recepcion_id": "la recepción",
}


@app.exception_handler(RequestValidationError)
async def _validacion_legible(_request: Any, exc: RequestValidationError) -> JSONResponse:
    """T04: «dos» en la cantidad daba un error técnico en inglés; ahora un texto claro."""
    errores = exc.errors()
    campo = next((str(p) for p in (errores[0].get("loc") or [])[::-1] if isinstance(p, str)), "") if errores else ""
    nombre = _CAMPOS.get(campo, campo or "un dato")
    return JSONResponse(status_code=422, content={"detail": f"Revisa {nombre}: el valor enviado no es válido"})


def ahora_ec() -> datetime:
    return datetime.now(ZONA_EC).replace(microsecond=0)


def ahora_iso() -> str:
    """Fecha y hora de Ecuador con zona, p. ej. 2026-11-10T20:15:00-05:00."""
    return ahora_ec().isoformat()


# ---------- P21 · Acceso: sesión obligatoria y roles ----------
# D20 / T17–T18: antes se podía borrar un ingreso o ver el resumen de administración
# sin haber entrado. Ahora toda ruta /api/ (salvo entrar y el estado del servidor) exige
# una sesión válida en la cabecera X-Session-Id; /api/admin/ exige rol de administrador.
# D16 / T13: el usuario de cada registro sale de esa sesión, nunca del formulario.
SESION_HORAS = 12
RUTAS_PUBLICAS = {"/api/login", "/api/health"}
_sesion_ctx: ContextVar[dict[str, Any] | None] = ContextVar("sesion", default=None)


def _cargar_sesion(session_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT s.session_id, s.usuario_nombre, s.created_at, COALESCE(u.rol, 'operador') AS rol
            FROM sesiones s LEFT JOIN usuarios u ON u.nombre = s.usuario_nombre
            WHERE s.session_id = ?
            """,
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        creada = datetime.fromisoformat(str(row["created_at"]))
    except ValueError:
        return None
    if creada.tzinfo is None:
        creada = creada.replace(tzinfo=ZONA_EC)
    if ahora_ec() - creada > timedelta(hours=SESION_HORAS):
        return None
    return {"session_id": row["session_id"], "usuario": row["usuario_nombre"], "rol": row["rol"]}


@app.middleware("http")
async def exigir_sesion(request: Request, call_next: Any) -> Any:
    path = request.url.path
    if path.startswith("/api/") and path not in RUTAS_PUBLICAS:
        session_id = request.headers.get("x-session-id", "").strip()
        sesion = _cargar_sesion(session_id) if session_id else None
        if sesion is None:
            return JSONResponse(status_code=401, content={"detail": "La sesión no es válida o venció. Vuelve a entrar con tu clave."})
        if path.startswith("/api/admin/") and sesion["rol"] != "administrador":
            return JSONResponse(status_code=403, content={"detail": "Solo un administrador puede ver esto."})
        token = _sesion_ctx.set(sesion)
        try:
            return await call_next(request)
        finally:
            _sesion_ctx.reset(token)
    return await call_next(request)


def sesion_actual() -> dict[str, Any]:
    sesion = _sesion_ctx.get()
    if sesion is None:
        raise HTTPException(status_code=401, detail="La sesión no es válida o venció. Vuelve a entrar con tu clave.")
    return sesion


# ---------- P22 · Auditoría ----------
def auditar(conn: Any, entidad: str, entidad_id: int | None, accion: str, detalle: dict[str, Any] | None = None) -> None:
    """Deja rastro de quién hizo qué y cuándo (D18). Se escribe en la misma transacción."""
    sesion = _sesion_ctx.get()
    conn.execute(
        "INSERT INTO auditoria (fecha, usuario, entidad, entidad_id, accion, detalle) VALUES (?, ?, ?, ?, ?, ?)",
        (ahora_iso(), sesion["usuario"] if sesion else "sistema", entidad, entidad_id, accion,
         json.dumps(detalle or {}, ensure_ascii=False)),
    )


class LoginPayload(BaseModel):
    # P24: usuario + PIN. Se limita el largo para no gastar tiempo de hash en textos enormes.
    usuario: str = Field(min_length=1, max_length=60)
    clave: str = Field(min_length=1, max_length=64)
    session_id: str | None = None


# Estados válidos del control de calidad y el único que permite confirmar el lote.
ESTADOS_QC = {"aprobado", "rechazado", "cuarentena"}
ESTADO_QC_CONFIRMABLE = "aprobado"


class EntryPayload(BaseModel):
    producto_id: int
    cantidad_ingresada: float
    lote: str
    fecha_caducidad: str
    # --- Control de calidad (QC), ligado al lote ---
    estado_qc: str
    responsable_qc: str | None = None
    observaciones_qc: str | None = None
    empaque_ok: bool = False
    sin_humedad: bool = False
    temperatura_ok: bool = False
    aspecto_olor_ok: bool = False
    documentacion_proveedor_ok: bool = False
    temperatura_recepcion: float | None = None
    session_id: str | None = None
    usuario_nombre: str | None = None
    recepcion_id: int | None = None  # P02: cada ingreso cuelga de una recepción abierta
    linea_id: str | None = None      # P20: id único de la línea creado en la tablet (evita duplicar reenvíos)


class BulkEntryPayload(BaseModel):
    entries: list[EntryPayload]
    # P06: ids de los pendientes que se confirman; se borran en la misma transacción.
    pending_ids: list[str] = []


class PendingPayload(BaseModel):
    session_id: str | None = None  # ya no se usa: la sesión viene en la cabecera
    datos: dict[str, Any]


class RecepcionPayload(BaseModel):
    session_id: str | None = None  # ya no se usa: la sesión viene en la cabecera
    proveedor: str
    documento_tipo: str
    documento_numero: str
    hora_llegada: str | None = None  # "HH:MM" de hoy; si no viene, la hora actual


class AnularPayload(BaseModel):
    motivo: str
    session_id: str | None = None


class SesionPayload(BaseModel):
    session_id: str | None = None  # ya no se usa: la sesión viene en la cabecera


class PrintLabelPayload(BaseModel):
    entry_id: int
    cantidad: int = 1
    test_mode: bool = False  # True: devuelve el ZPL sin enviarlo a la impresora


def validar_qc(payload: EntryPayload) -> str:
    """Valida el estado_qc y aplica la regla: solo se confirma un lote APROBADO.

    Devuelve el estado normalizado. Lanza 422 si el estado es inválido o si el lote
    no puede confirmarse por estar rechazado o en cuarentena (con el motivo).
    """
    estado = (payload.estado_qc or "").strip().lower()
    if estado not in ESTADOS_QC:
        raise HTTPException(status_code=422, detail="El estado de control de calidad es obligatorio")
    if estado != ESTADO_QC_CONFIRMABLE:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Lote {payload.lote or ''} bloqueado: el control de calidad está en "
                f"'{estado}'. Solo se puede confirmar un lote APROBADO."
            ),
        )
    return estado


def convertir_cantidad(cantidad: float, product: Any) -> float:
    """P05 / R1: cantidad en unidad de planta = cantidad × unidades por empaque × factor.

    Antes se multiplicaba solo cantidad × factor y se ignoraba la cantidad por caja o
    paquete: 1 caja de aceite desmoldante (6 × 3,785 L) quedaba en 3,785 L en vez de 22,71 L.
    """
    por_empaque = product["cantidad_por_caja"] or 1
    if por_empaque <= 0:
        por_empaque = 1
    return round(cantidad * por_empaque * product["factor_conversion"], 3)


# INSERT único de ingresos (incluye lote/caducidad y todo el bloque de QC),
# compartido por el alta individual y el ingreso masivo para evitar duplicar columnas.
_INSERT_INGRESO_SQL = """
    INSERT INTO ingresos (
        producto_id, nombre_producto, codigo_cyrano, cantidad_ingresada, unidad_llega,
        cantidad_convertida, unidad_planta, codigo_barra, lote, fecha_caducidad,
        estado_qc, responsable_qc, observaciones_qc, empaque_ok, sin_humedad,
        temperatura_ok, aspecto_olor_ok, documentacion_proveedor_ok, temperatura_recepcion,
        created_at, session_id, usuario_nombre, recepcion_id, linea_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _insert_ingreso_params(
    product: Any,
    payload: EntryPayload,
    cantidad_convertida: float,
    estado_qc: str,
    lote: str,
    fecha_caducidad: str,
    usuario_nombre: str,
) -> tuple[Any, ...]:
    return (
        product["id"],
        product["nombre_producto"],
        product["codigo_cyrano"],
        payload.cantidad_ingresada,
        product["unidad_llega"],
        cantidad_convertida,
        product["unidad_planta"],
        product["codigo_barra"],
        lote,
        fecha_caducidad,
        estado_qc,
        (payload.responsable_qc or "").strip(),
        (payload.observaciones_qc or "").strip(),
        int(payload.empaque_ok),
        int(payload.sin_humedad),
        int(payload.temperatura_ok),
        int(payload.aspecto_olor_ok),
        int(payload.documentacion_proveedor_ok),
        payload.temperatura_recepcion,
        ahora_iso(),
        payload.session_id or "",
        usuario_nombre,
        payload.recepcion_id,
    )


# ---------- P02 · Recepción como unidad ----------

def _recepcion_abierta(conn: Any, recepcion_id: int | None) -> Any:
    """El ingreso debe colgar de una recepción abierta (regla Ingreso.recepcion_id)."""
    if not recepcion_id:
        raise HTTPException(status_code=422, detail="Abre una recepción (proveedor y documento) antes de registrar productos")
    rec = conn.execute("SELECT * FROM recepciones WHERE id = ?", (recepcion_id,)).fetchone()
    if rec is None:
        raise HTTPException(status_code=422, detail="La recepción no existe")
    if rec["estado"] != "abierta":
        raise HTTPException(status_code=422, detail="La recepción ya está cerrada; abre una nueva")
    return rec


def _marcar_inicio_si_falta(conn: Any, recepcion_id: int | None) -> None:
    """Si no se tocó «Empezar descarga», el primer producto marca el inicio (queda como automático)."""
    if recepcion_id:
        conn.execute(
            "UPDATE recepciones SET hora_inicio_descarga = ?, inicio_automatico = 1 "
            "WHERE id = ? AND hora_inicio_descarga IS NULL AND estado = 'abierta'",
            (ahora_iso(), recepcion_id),
        )


def _recepcion_dict(conn: Any, rec: Any) -> dict[str, Any]:
    data = dict(rec)
    data["ingresos_confirmados"] = conn.execute(
        "SELECT COUNT(*) FROM ingresos WHERE recepcion_id = ? AND estado_registro = 'vigente'", (rec["id"],)
    ).fetchone()[0]
    return data


@app.on_event("startup")
def startup_event() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok"}  # P21: ya no se muestra la ruta de la base


MENSAJE_LOGIN_FALLIDO = "Usuario o PIN incorrecto."


def _registrar_evento_usuario(conn: Any, usuario: str, usuario_id: int | None, accion: str, detalle: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO auditoria (fecha, usuario, entidad, entidad_id, accion, detalle) VALUES (?, ?, 'usuario', ?, ?, ?)",
        (ahora_iso(), usuario, usuario_id, accion, json.dumps(detalle, ensure_ascii=False)),
    )


@app.post("/api/login")
def login(payload: LoginPayload) -> dict[str, Any]:
    """P24 / D21: usuario + PIN comparado contra su hash; bloqueo temporal tras
    INTENTOS_MAXIMOS fallos seguidos. El mensaje no dice si falló el usuario o el PIN.
    """
    conn = get_connection()
    try:
        user = conn.execute(
            "SELECT id, nombre, clave, rol, intentos_fallidos, bloqueado_hasta FROM usuarios "
            "WHERE lower(trim(nombre)) = lower(trim(?))",
            (payload.usuario,),
        ).fetchone()
        if not user:
            verificar_pin(payload.clave, HASH_RELLENO)  # misma demora que con un usuario real
            raise HTTPException(status_code=401, detail=MENSAJE_LOGIN_FALLIDO)

        ahora = ahora_ec()
        if user["bloqueado_hasta"]:
            hasta = datetime.fromisoformat(user["bloqueado_hasta"])
            if hasta > ahora:
                minutos = max(1, -(-int((hasta - ahora).total_seconds()) // 60))
                raise HTTPException(
                    status_code=429,
                    detail=f"Usuario bloqueado por varios intentos fallidos. Espera {minutos} min y vuelve a intentar.",
                )

        if not verificar_pin(payload.clave, user["clave"]):
            intentos = int(user["intentos_fallidos"] or 0) + 1
            if intentos >= INTENTOS_MAXIMOS:
                hasta = (ahora + timedelta(minutes=MINUTOS_BLOQUEO)).isoformat(timespec="seconds")
                conn.execute("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = ? WHERE id = ?", (hasta, user["id"]))
                _registrar_evento_usuario(conn, str(user["nombre"]), user["id"], "bloqueo_por_intentos",
                                          {"intentos": intentos, "bloqueado_hasta": hasta})
                conn.commit()
                raise HTTPException(
                    status_code=429,
                    detail=f"Usuario bloqueado por {INTENTOS_MAXIMOS} intentos fallidos. Espera {MINUTOS_BLOQUEO} min y vuelve a intentar.",
                )
            conn.execute("UPDATE usuarios SET intentos_fallidos = ? WHERE id = ?", (intentos, user["id"]))
            conn.commit()
            quedan = INTENTOS_MAXIMOS - intentos
            aviso = f" Te queda {quedan} intento antes del bloqueo." if quedan == 1 else (
                f" Te quedan {quedan} intentos antes del bloqueo." if quedan <= 3 else "")
            raise HTTPException(status_code=401, detail=MENSAJE_LOGIN_FALLIDO + aviso)

        conn.execute("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id = ?", (user["id"],))
        conn.commit()
    finally:
        conn.close()

    # P21: el identificador de sesión lo crea el servidor (aleatorio, no adivinable);
    # antes lo inventaba la tablet. El rol sale de la base, no del nombre.
    rol = user["rol"] if "rol" in user.keys() and user["rol"] else "operador"
    session_id = secrets.token_urlsafe(32)
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO sesiones (session_id, usuario_nombre, created_at) VALUES (?, ?, ?)",
            (session_id, str(user["nombre"]), ahora_iso()),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "id": user["id"],
        "nombre": user["nombre"],
        "fecha": ahora_ec().strftime("%d/%m/%Y"),
        "rol": rol,
        "is_admin": rol == "administrador",
        "session_id": session_id,
    }


@app.post("/api/logout")
def logout() -> dict[str, Any]:
    sesion = sesion_actual()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM sesiones WHERE session_id = ?", (sesion["session_id"],))
        conn.commit()
    finally:
        conn.close()
    return {"message": "Sesión cerrada"}


@app.get("/api/admin/summary")
def admin_summary(usuario: str | None = Query(default=None)) -> dict[str, Any]:
    conn = get_connection()
    try:
        users_count = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        products_count = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
        entries_count = conn.execute("SELECT COUNT(*) FROM ingresos").fetchone()[0]
        users_from_db = [row[0] for row in conn.execute("SELECT nombre FROM usuarios ORDER BY nombre").fetchall()]
        user_names_from_entries = [
            row[0]
            for row in conn.execute("SELECT DISTINCT usuario_nombre FROM ingresos WHERE usuario_nombre IS NOT NULL AND usuario_nombre != '' ORDER BY usuario_nombre").fetchall()
        ]
        user_names_from_sessions = [
            row[0]
            for row in conn.execute("SELECT DISTINCT usuario_nombre FROM sesiones ORDER BY usuario_nombre").fetchall()
        ]
        users = sorted(set(users_from_db + user_names_from_entries + user_names_from_sessions))

        base_query = """
            SELECT i.nombre_producto, i.codigo_cyrano, i.cantidad_ingresada, i.unidad_llega,
                   i.cantidad_convertida, i.unidad_planta, i.codigo_barra, i.created_at,
                   i.lote, i.fecha_caducidad, i.estado_qc, i.responsable_qc,
                   i.usuario_nombre, i.estado_registro, i.anulado_motivo,
                   COALESCE(NULLIF(i.usuario_nombre, ''), s.usuario_nombre, 'desconocido') AS usuario,
                   COALESCE(NULLIF(i.usuario_nombre, ''), s.usuario_nombre, '') AS usuario_resuelto
            FROM ingresos i
            LEFT JOIN sesiones s ON s.session_id = i.session_id
        """
        params: tuple[Any, ...] = ()
        if usuario:
            filter_clause = " WHERE COALESCE(NULLIF(i.usuario_nombre, ''), s.usuario_nombre, '') = ?"
            params = (usuario,)
        else:
            filter_clause = ""

        recent_entries = conn.execute(base_query + filter_clause + " ORDER BY i.id DESC LIMIT 10", params).fetchall()
        filtered_entries = conn.execute(base_query + filter_clause + " ORDER BY i.id DESC", params).fetchall()
    finally:
        conn.close()

    return {
        "totales": {
            "usuarios": users_count,
            "productos": products_count,
            "ingresos": entries_count,
        },
        "usuarios": users,
        "filtro_actual": usuario or "todos",
        "ultimos_ingresos": [dict(row) for row in recent_entries],
        "ingresos_filtrados": [dict(row) for row in filtered_entries],
    }


@app.post("/api/admin/reload")
def admin_reload() -> dict[str, Any]:
    init_db()
    return {"message": "Datos recargados correctamente"}


@app.get("/api/providers")
def get_providers() -> list[str]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT DISTINCT proveedor FROM productos ORDER BY proveedor").fetchall()
    finally:
        conn.close()
    return [row["proveedor"] for row in rows]


def _normalizar(texto: Any) -> str:
    """Minusculas y sin acentos, para comparar de forma insensible a mayusculas/acentos."""
    if texto is None:
        return ""
    base = unicodedata.normalize("NFKD", str(texto))
    sin_acentos = "".join(c for c in base if not unicodedata.combining(c))
    return sin_acentos.casefold().strip()


@app.get("/api/search")
def search_all(q: str = Query(default="")) -> dict[str, Any]:
    """Busqueda unificada para autocompletado: productos (por codigo o nombre) y proveedores.

    Coincidencia parcial e insensible a mayusculas/acentos. El dataset es pequeno,
    asi que filtramos en Python para poder normalizar acentos de forma confiable.
    """
    termino = _normalizar(q)
    conn = get_connection()
    try:
        productos = conn.execute("SELECT * FROM productos ORDER BY nombre_producto").fetchall()
        proveedores = [
            row[0]
            for row in conn.execute("SELECT DISTINCT proveedor FROM productos ORDER BY proveedor").fetchall()
        ]
    finally:
        conn.close()

    resultados: list[dict[str, Any]] = []
    if not termino:
        return {"resultados": resultados}

    # Productos: coincidencia por codigo_cyrano o por nombre.
    for producto in productos:
        if termino in _normalizar(producto["codigo_cyrano"]) or termino in _normalizar(producto["nombre_producto"]):
            item = dict(producto)
            item["type"] = "producto"
            resultados.append(item)

    # Proveedores: coincidencia por nombre.
    for proveedor in proveedores:
        if termino in _normalizar(proveedor):
            resultados.append({"type": "proveedor", "proveedor": proveedor})

    return {"resultados": resultados[:25]}


@app.get("/api/products/search")
def search_products(
    barcode: str | None = Query(default=None),
    code: str | None = Query(default=None),
    provider: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if barcode:
            rows = conn.execute(
                "SELECT * FROM productos WHERE codigo_barra = ?",
                (barcode,),
            ).fetchall()
        elif code:
            rows = conn.execute(
                "SELECT * FROM productos WHERE codigo_cyrano = ?",
                (code,),
            ).fetchall()
        elif provider:
            rows = conn.execute(
                "SELECT * FROM productos WHERE proveedor = ? ORDER BY nombre_producto",
                (provider,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM productos ORDER BY nombre_producto").fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


@app.get("/api/products/scan")
def scan_product(code: str = Query(..., min_length=1, max_length=120)) -> dict[str, Any]:
    """P09: busca el producto de un código escaneado y, si es GS1-128, devuelve lote y caducidad.

    Primero busca el código tal cual. Si no está y es GS1-128, busca por el GTIN de la caja
    (R3: antes la misma caja con otro lote salía «no encontrado»).
    """
    codigo = code.strip()
    gs1 = leer_gs1(codigo)
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM productos WHERE codigo_barra = ?", (codigo,)).fetchall()
        if not rows and gs1:
            opciones = gtins_equivalentes(gs1["gtin"])
            marcas = ", ".join("?" for _ in opciones)
            rows = conn.execute(
                f"SELECT * FROM productos WHERE codigo_barra IN ({marcas}) "
                "OR codigo_barra LIKE ? OR codigo_barra LIKE ? ORDER BY id",
                (*opciones, f"01{gs1['gtin']}%", f"02{gs1['gtin']}%"),
            ).fetchall()
    finally:
        conn.close()
    # La misma presentación puede estar dos veces (con el GTIN solo y con un código GS1 completo).
    vistos, productos = set(), []
    for row in rows:
        clave = (row["codigo_cyrano"], row["unidad_llega"], row["cantidad_por_caja"], row["factor_conversion"])
        if clave not in vistos:
            vistos.add(clave)
            productos.append(dict(row))
    datos = None
    if gs1 and (gs1["lote"] or gs1["caducidad"]):
        datos = {k: gs1[k] for k in ("gtin", "lote", "caducidad", "caducidad_fuente")}
    return {"productos": productos, "gs1": datos}


def _guardar_ingreso(conn: Any, item: EntryPayload) -> int | None:
    """P20: valida un ingreso con el diccionario de datos y lo guarda.

    Devuelve el id nuevo, o None si la misma línea (linea_id) ya estaba guardada:
    así un doble toque en «Confirmar» no duplica (T16), pero dos líneas iguales y
    legítimas con distinto linea_id sí se guardan las dos (T15, D11).
    """
    product = producto_existente(conn, item.producto_id)                      # D5, T12
    cantidad = validar_cantidad(item.cantidad_ingresada, product["unidad_llega"])  # D1, T01–T03
    lote = validar_lote(item.lote)                                             # D3, T08–T09
    fecha_caducidad = validar_caducidad(item.fecha_caducidad, ahora_ec().date())  # D2, T05–T07
    estado_qc = validar_qc(item)                                               # estado obligatorio; solo aprobado (P16)
    calidad = validar_calidad(item)                                            # D4, D7; T10–T11
    _recepcion_abierta(conn, item.recepcion_id)

    linea_id = (item.linea_id or "").strip() or None
    if linea_id and conn.execute("SELECT 1 FROM ingresos WHERE linea_id = ?", (linea_id,)).fetchone():
        return None

    # P21 / D16 / T13: el usuario y la sesión salen de la sesión, no del formulario.
    sesion = sesion_actual()
    usuario_nombre = sesion["usuario"]
    if not calidad["responsable_qc"]:
        calidad["responsable_qc"] = usuario_nombre  # FH 17: por defecto, quien registra

    limpio = item.model_copy(update={"cantidad_ingresada": cantidad, "session_id": sesion["session_id"], **calidad})
    cantidad_convertida = convertir_cantidad(cantidad, product)
    _marcar_inicio_si_falta(conn, item.recepcion_id)
    cur = conn.execute(
        _INSERT_INGRESO_SQL,
        _insert_ingreso_params(product, limpio, cantidad_convertida, estado_qc, lote, fecha_caducidad, usuario_nombre) + (linea_id,),
    )
    auditar(conn, "ingreso", cur.lastrowid, "alta", {
        "producto": product["codigo_cyrano"], "cantidad": cantidad, "unidad": product["unidad_llega"],
        "lote": lote, "caducidad": fecha_caducidad, "calidad": estado_qc, "recepcion_id": item.recepcion_id,
    })
    return cur.lastrowid


@app.post("/api/entries")
def create_entry(payload: EntryPayload) -> dict[str, Any]:
    conn = get_connection()
    try:
        entry_id = _guardar_ingreso(conn, payload)
        conn.commit()
    finally:
        conn.close()
    if entry_id is None:
        return {"id": None, "message": "Esta línea ya estaba guardada"}
    return {"id": entry_id, "message": "Ingreso guardado"}


@app.post("/api/entries/bulk")
def create_bulk_entries(payload: BulkEntryPayload) -> dict[str, Any]:
    if not payload.entries:
        raise HTTPException(status_code=422, detail="No hay ingresos para confirmar")
    conn = get_connection()
    guardados = repetidos = 0
    try:
        for n, item in enumerate(payload.entries, start=1):
            try:
                nuevo = _guardar_ingreso(conn, item)
            except HTTPException as error:
                # Se dice qué línea falló; no se guarda ninguna (la transacción no se confirma).
                producto = conn.execute("SELECT codigo_cyrano FROM productos WHERE id = ?", (item.producto_id,)).fetchone()
                codigo = producto["codigo_cyrano"] if producto else item.producto_id
                raise HTTPException(
                    status_code=error.status_code,
                    detail=f"Línea {n} ({codigo} · lote {(item.lote or '').strip() or 'sin lote'}): {error.detail}. No se guardó ninguna línea.",
                )
            if nuevo is None:
                repetidos += 1
            else:
                guardados += 1
        if payload.pending_ids:
            conn.executemany("DELETE FROM pendientes WHERE id = ?", [(pid,) for pid in payload.pending_ids])
        conn.commit()
    finally:
        conn.close()

    return {"message": "Ingresos masivos guardados", "guardados": guardados, "ya_guardados": repetidos}


@app.get("/api/proveedores")
def list_proveedores() -> list[str]:
    """Lista de proveedores para la recepción (de MovCompras, por número de compras)."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT nombre FROM proveedores ORDER BY compras DESC, nombre").fetchall()
    finally:
        conn.close()
    return [row["nombre"] for row in rows]


@app.get("/api/recepciones/abierta")
def recepcion_abierta(session_id: str | None = Query(default=None)) -> dict[str, Any] | None:
    """La recepción abierta del usuario de la sesión (para retomarla al entrar o recargar)."""
    conn = get_connection()
    try:
        usuario = _usuario_de_sesion(conn, session_id)
        rec = conn.execute(
            "SELECT * FROM recepciones WHERE usuario_nombre = ? AND estado = 'abierta' ORDER BY id DESC LIMIT 1",
            (usuario,),
        ).fetchone()
        return _recepcion_dict(conn, rec) if rec else None
    finally:
        conn.close()


@app.post("/api/recepciones")
def abrir_recepcion(payload: RecepcionPayload) -> dict[str, Any]:
    proveedor = " ".join((payload.proveedor or "").split())
    documento_tipo = (payload.documento_tipo or "").strip().lower()
    documento_numero = (payload.documento_numero or "").strip()
    if not proveedor:
        raise HTTPException(status_code=422, detail="Falta el proveedor")
    if documento_tipo not in {"factura", "guia"}:
        raise HTTPException(status_code=422, detail="El documento debe ser factura o guía")
    if not documento_numero:
        raise HTTPException(status_code=422, detail="Falta el número de la factura o guía")

    ahora = ahora_ec()
    llegada = ahora
    if payload.hora_llegada:
        try:
            hh, mm = (int(x) for x in payload.hora_llegada.split(":")[:2])
            llegada = ahora.replace(hour=hh, minute=mm, second=0)
        except ValueError:
            raise HTTPException(status_code=422, detail="Hora de llegada no válida")
        if llegada > ahora:
            raise HTTPException(status_code=422, detail="La hora de llegada no puede ser futura")

    conn = get_connection()
    try:
        usuario = _usuario_de_sesion(conn, payload.session_id)
        abierta = conn.execute(
            "SELECT id FROM recepciones WHERE usuario_nombre = ? AND estado = 'abierta'", (usuario,)
        ).fetchone()
        if abierta:
            raise HTTPException(status_code=409, detail="Ya tienes una recepción abierta; ciérrala antes de abrir otra")
        repetida = conn.execute(
            "SELECT id FROM recepciones WHERE proveedor = ? AND documento_tipo = ? AND documento_numero = ?",
            (proveedor, documento_tipo, documento_numero),
        ).fetchone()
        if repetida:
            nombre_doc = "factura" if documento_tipo == "factura" else "guía"
            raise HTTPException(status_code=409, detail=f"Ya existe una recepción con la {nombre_doc} {documento_numero} de este proveedor")
        cur = conn.execute(
            """
            INSERT INTO recepciones (proveedor, documento_tipo, documento_numero, hora_llegada,
                                     estado, usuario_nombre, session_id, created_at)
            VALUES (?, ?, ?, ?, 'abierta', ?, ?, ?)
            """,
            (proveedor, documento_tipo, documento_numero, llegada.isoformat(), usuario, sesion_actual()["session_id"], ahora.isoformat()),
        )
        auditar(conn, "recepcion", cur.lastrowid, "apertura", {
            "proveedor": proveedor, "documento": f"{documento_tipo} {documento_numero}", "hora_llegada": llegada.isoformat(),
        })
        conn.commit()
        rec = conn.execute("SELECT * FROM recepciones WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _recepcion_dict(conn, rec)
    finally:
        conn.close()


def _recepcion_del_usuario(conn: Any, recepcion_id: int, session_id: str) -> Any:
    usuario = _usuario_de_sesion(conn, session_id)
    rec = conn.execute("SELECT * FROM recepciones WHERE id = ? AND usuario_nombre = ?", (recepcion_id, usuario)).fetchone()
    if rec is None:
        raise HTTPException(status_code=404, detail="Recepción no encontrada")
    if rec["estado"] != "abierta":
        raise HTTPException(status_code=422, detail="La recepción ya está cerrada")
    return rec


@app.post("/api/recepciones/{recepcion_id}/inicio")
def iniciar_descarga(recepcion_id: int, payload: SesionPayload) -> dict[str, Any]:
    conn = get_connection()
    try:
        rec = _recepcion_del_usuario(conn, recepcion_id, payload.session_id)
        if rec["hora_inicio_descarga"] is None:
            conn.execute(
                "UPDATE recepciones SET hora_inicio_descarga = ?, inicio_automatico = 0 WHERE id = ?",
                (ahora_iso(), recepcion_id),
            )
            auditar(conn, "recepcion", recepcion_id, "inicio_descarga")
            conn.commit()
        rec = conn.execute("SELECT * FROM recepciones WHERE id = ?", (recepcion_id,)).fetchone()
        return _recepcion_dict(conn, rec)
    finally:
        conn.close()


@app.post("/api/recepciones/{recepcion_id}/cerrar")
def cerrar_recepcion(recepcion_id: int, payload: SesionPayload) -> dict[str, Any]:
    conn = get_connection()
    try:
        rec = _recepcion_del_usuario(conn, recepcion_id, payload.session_id)
        pendientes = conn.execute(
            "SELECT COUNT(*) FROM pendientes WHERE json_extract(datos, '$.recepcion_id') = ?",
            (recepcion_id,),
        ).fetchone()[0]
        if pendientes:
            raise HTTPException(status_code=422, detail=f"Hay {pendientes} producto(s) pendientes de confirmar en esta recepción")
        ahora = ahora_iso()
        conn.execute(
            "UPDATE recepciones SET hora_fin = ?, estado = 'cerrada', "
            "hora_inicio_descarga = COALESCE(hora_inicio_descarga, ?) WHERE id = ?",
            (ahora, rec["hora_llegada"], recepcion_id),
        )
        auditar(conn, "recepcion", recepcion_id, "cierre", {"hora_fin": ahora})
        conn.commit()
        rec = conn.execute("SELECT * FROM recepciones WHERE id = ?", (recepcion_id,)).fetchone()
        return _recepcion_dict(conn, rec)
    finally:
        conn.close()


# ---------- P03 · Exportar a Excel ----------

@app.get("/api/export")
def exportar_excel(
    session_id: str | None = Query(default=None),
    desde: str = Query(..., description="AAAA-MM-DD"),
    hasta: str = Query(..., description="AAAA-MM-DD"),
) -> Response:
    """Recepciones (por fecha de llegada) y sus productos, en un Excel para los KPI 1, 1b y 2."""
    from backend.exportar import construir_excel  # import diferido: openpyxl solo se carga al exportar

    try:
        d1 = datetime.strptime(desde, "%Y-%m-%d").date()
        d2 = datetime.strptime(hasta, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=422, detail="Fechas no válidas (AAAA-MM-DD)")
    if d2 < d1:
        raise HTTPException(status_code=422, detail="La fecha «hasta» es anterior a «desde»")

    conn = get_connection()
    try:
        _usuario_de_sesion(conn, session_id)
        recepciones = [dict(r) for r in conn.execute(
            """
            SELECT r.*, (SELECT COUNT(*) FROM ingresos i WHERE i.recepcion_id = r.id AND i.estado_registro = 'vigente') AS productos
            FROM recepciones r
            WHERE substr(r.hora_llegada, 1, 10) BETWEEN ? AND ?
            ORDER BY r.hora_llegada, r.id
            """,
            (desde, hasta),
        ).fetchall()]
        ingresos = [dict(r) for r in conn.execute(
            """
            SELECT i.*, r.proveedor, r.documento_tipo, r.documento_numero, p.codigo_sap
            FROM ingresos i LEFT JOIN recepciones r ON r.id = i.recepcion_id
            LEFT JOIN productos p ON p.id = i.producto_id
            WHERE (r.id IS NOT NULL AND substr(r.hora_llegada, 1, 10) BETWEEN ? AND ?)
               OR (r.id IS NULL AND substr(i.created_at, 1, 10) BETWEEN ? AND ?)
            ORDER BY i.recepcion_id, i.id
            """,
            (desde, hasta, desde, hasta),
        ).fetchall()]
    finally:
        conn.close()

    contenido = construir_excel(recepciones, ingresos, desde, hasta)
    nombre = f"cyrano_recepciones_{desde}_a_{hasta}.xlsx"
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


# ---------- P06 · Pendientes guardados en el servidor ----------

def _usuario_de_sesion(_conn: Any = None, _session_id: Any = None) -> str:
    """P21: el usuario es siempre el de la sesión validada (cabecera X-Session-Id);
    se ignora cualquier session_id que venga en el cuerpo o en la dirección."""
    return sesion_actual()["usuario"]


@app.get("/api/pending")
def list_pending(session_id: str | None = Query(default=None)) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        usuario = _usuario_de_sesion(conn, session_id)
        rows = conn.execute(
            "SELECT datos FROM pendientes WHERE usuario_nombre = ? ORDER BY created_at DESC, id DESC",
            (usuario,),
        ).fetchall()
    finally:
        conn.close()
    return [json.loads(row["datos"]) for row in rows]


@app.put("/api/pending/{pending_id}")
def save_pending(pending_id: str, payload: PendingPayload) -> dict[str, Any]:
    conn = get_connection()
    try:
        usuario = _usuario_de_sesion(conn, payload.session_id)
        datos = dict(payload.datos, id=payload.datos.get("id", pending_id))
        _marcar_inicio_si_falta(conn, datos.get("recepcion_id"))
        conn.execute(
            """
            INSERT INTO pendientes (id, usuario_nombre, datos, created_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET datos = excluded.datos
            """,
            (pending_id, usuario, json.dumps(datos, ensure_ascii=False), ahora_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": pending_id, "message": "Pendiente guardado"}


@app.delete("/api/pending/{pending_id}")
def delete_pending(pending_id: str, session_id: str | None = Query(default=None)) -> dict[str, Any]:
    conn = get_connection()
    try:
        usuario = _usuario_de_sesion(conn, session_id)
        conn.execute("DELETE FROM pendientes WHERE id = ? AND usuario_nombre = ?", (pending_id, usuario))
        conn.commit()
    finally:
        conn.close()
    return {"id": pending_id, "message": "Pendiente eliminado"}


@app.get("/api/entries")
def get_entries(
    filter_no_barcode: bool = False,
    session_id: str | None = None,
    lote: str | None = None,
    fecha_caducidad: str | None = None,
) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        base_query = """
            SELECT i.*, p.cantidad_por_caja,
                   COALESCE(NULLIF(i.usuario_nombre, ''), s.usuario_nombre, '') AS usuario_resuelto
            FROM ingresos i
            LEFT JOIN productos p ON p.id = i.producto_id
            LEFT JOIN sesiones s ON s.session_id = i.session_id
        """
        # Construimos las condiciones de forma acumulativa para poder combinar filtros.
        conditions: list[str] = []
        params: list[Any] = []
        # P21: siempre los de la sesión de la cabecera (no la que mande el cliente).
        conditions.append("i.session_id = ?")
        params.append(sesion_actual()["session_id"])
        if filter_no_barcode:
            conditions.append("(i.codigo_barra IS NULL OR i.codigo_barra = '')")
        if lote:
            conditions.append("i.lote LIKE ?")
            params.append(f"%{lote}%")
        if fecha_caducidad:
            conditions.append("i.fecha_caducidad = ?")
            params.append(fecha_caducidad)

        query = base_query
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY i.id DESC"
        rows = conn.execute(query, tuple(params)).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


@app.delete("/api/entries/{entry_id}")
def delete_entry(entry_id: int) -> dict[str, Any]:
    """P22: ya no se borra físicamente ningún ingreso confirmado."""
    raise HTTPException(status_code=405, detail="Los ingresos confirmados no se borran: usa «Anular» con un motivo")


@app.post("/api/entries/{entry_id}/anular")
def anular_ingreso(entry_id: int, payload: AnularPayload) -> dict[str, Any]:
    """P22 / D18 / T23: el ingreso queda en la base marcado como anulado, con motivo, usuario y hora."""
    sesion = sesion_actual()
    motivo = " ".join((payload.motivo or "").split())
    if len(motivo) < 5:
        raise HTTPException(status_code=422, detail="Escribe el motivo de la anulación (al menos 5 caracteres)")
    if len(motivo) > 300:
        raise HTTPException(status_code=422, detail="El motivo pasa de 300 caracteres")
    conn = get_connection()
    try:
        row = conn.execute("SELECT usuario_nombre, estado_registro, codigo_cyrano, lote FROM ingresos WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Registro no encontrado")
        if sesion["rol"] != "administrador" and row["usuario_nombre"] != sesion["usuario"]:
            raise HTTPException(status_code=403, detail="Solo quien registró el ingreso o un administrador puede anularlo")
        if row["estado_registro"] == "anulado":
            raise HTTPException(status_code=409, detail="Este ingreso ya estaba anulado")
        ahora = ahora_iso()
        conn.execute(
            "UPDATE ingresos SET estado_registro = 'anulado', anulado_motivo = ?, anulado_por = ?, anulado_at = ? WHERE id = ?",
            (motivo, sesion["usuario"], ahora, entry_id),
        )
        auditar(conn, "ingreso", entry_id, "anulacion", {"motivo": motivo, "producto": row["codigo_cyrano"], "lote": row["lote"]})
        conn.commit()
    finally:
        conn.close()
    return {"id": entry_id, "estado_registro": "anulado", "anulado_por": sesion["usuario"], "anulado_at": ahora, "message": "Ingreso anulado"}


@app.get("/api/admin/auditoria")
def ver_auditoria(limite: int = Query(default=100, ge=1, le=1000)) -> list[dict[str, Any]]:
    """Últimos eventos de la auditoría (solo administrador)."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM auditoria ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
    finally:
        conn.close()
    return [{**dict(r), "detalle": json.loads(r["detalle"] or "{}")} for r in rows]


@app.get("/api/print/config")
def print_config() -> dict[str, Any]:
    """Configuración actual de la impresora Zebra (para mostrarla en la UI)."""
    return printer_info()


@app.post("/api/print/label")
def print_label(payload: PrintLabelPayload) -> dict[str, Any]:
    """Genera el ZPL de una entrada/lote y lo imprime en la Zebra (o lo devuelve en modo prueba)."""
    conn = get_connection()
    try:
        entry = conn.execute("SELECT * FROM ingresos WHERE id = ?", (payload.entry_id,)).fetchone()
    finally:
        conn.close()

    if not entry:
        raise HTTPException(status_code=404, detail="Ingreso no encontrado")
    if entry["estado_registro"] == "anulado":
        raise HTTPException(status_code=422, detail="El ingreso está anulado: no se imprime su etiqueta")

    cantidad = max(1, payload.cantidad)
    zpl = build_label_zpl(
        codigo=entry["codigo_cyrano"],
        nombre=entry["nombre_producto"],
        lote=entry["lote"],
        fecha_caducidad=entry["fecha_caducidad"],
        cantidad=cantidad,
    )

    info = printer_info()

    # Modo prueba: no toca la impresora, solo devuelve el ZPL para verlo/pegarlo en Labelary.
    if payload.test_mode:
        return {"test_mode": True, "cantidad": cantidad, "printer": info, "zpl": zpl}

    try:
        send_zpl(zpl)
    except OSError as error:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo conectar con la impresora Zebra en {info['ip']}:{info['port']} ({error})",
        )

    return {
        "test_mode": False,
        "cantidad": cantidad,
        "printer": info,
        "message": f"Etiqueta enviada ({cantidad}) a {info['ip']}:{info['port']}",
        "zpl": zpl,
    }


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
