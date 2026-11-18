"""Servicio de impresión de etiquetas en la Zebra ZD230 usando ZPL sobre TCP.

La impresora Zebra escucha ZPL crudo en un socket TCP (puerto 9100 por defecto).
La IP y el puerto son CONFIGURABLES por variable de entorno, no van fijos en el código:

    ZEBRA_IP      -> IP de la impresora (ej. 192.168.1.50)
    ZEBRA_PORT    -> puerto TCP (por defecto 9100)
    ZEBRA_TIMEOUT -> timeout de conexión en segundos (por defecto 5)

Modo de prueba: el endpoint puede devolver el ZPL sin enviarlo, para pegarlo en un
visor como https://labelary.com/viewer.html y validar el diseño sin hardware.
"""

import os
import socket


def _config() -> tuple[str, int, float]:
    """Lee la configuración de la impresora en cada llamada (permite cambiarla sin reiniciar)."""
    ip = os.getenv("ZEBRA_IP", "192.168.1.100")
    port = int(os.getenv("ZEBRA_PORT", "9100"))
    timeout = float(os.getenv("ZEBRA_TIMEOUT", "5"))
    return ip, port, timeout


def printer_info() -> dict[str, object]:
    """Devuelve la configuración actual de la impresora (para mostrar en la UI)."""
    ip, port, timeout = _config()
    return {"ip": ip, "port": port, "timeout": timeout}


def _zpl_sanitize(texto: object) -> str:
    """Neutraliza los caracteres de control de ZPL (^ y ~) dentro del texto de la etiqueta."""
    if texto is None:
        return ""
    return str(texto).replace("^", " ").replace("~", " ").strip()


def build_label_zpl(
    codigo: str,
    nombre: str,
    lote: str,
    fecha_caducidad: str,
    cantidad: int = 1,
) -> str:
    """Genera el ZPL de una etiqueta: código de barras Code 128 + texto.

    Texto: código, nombre, lote y fecha de caducidad. `cantidad` controla cuántas
    copias imprime la Zebra (^PQ). Etiqueta pensada para ~4x2 pulgadas a 203 dpi.
    """
    codigo_txt = _zpl_sanitize(codigo)
    nombre_txt = _zpl_sanitize(nombre)
    lote_txt = _zpl_sanitize(lote)
    fecha_txt = _zpl_sanitize(fecha_caducidad)
    copias = max(1, int(cantidad or 1))

    # ^CI28 -> UTF-8 (acentos). ^BY define el módulo del código de barras.
    # ^BCN,100,Y,N,N -> Code 128, alto 100 pt, con línea de interpretación.
    return (
        "^XA\n"
        "^CI28\n"
        "^PW812\n"          # ancho de impresión (~4\" @203dpi)
        "^LL406\n"          # alto de etiqueta (~2\")
        f"^FO30,30^A0N,34,34^FDCodigo: {codigo_txt}^FS\n"
        f"^FO30,75^A0N,30,30^FD{nombre_txt}^FS\n"
        f"^FO30,120^A0N,28,28^FDLote: {lote_txt}^FS\n"
        f"^FO30,158^A0N,28,28^FDVence: {fecha_txt}^FS\n"
        "^FO30,200^BY3\n"
        f"^BCN,100,Y,N,N^FD{codigo_txt}^FS\n"
        f"^PQ{copias}\n"
        "^XZ\n"
    )


def send_zpl(zpl: str) -> dict[str, object]:
    """Envía el ZPL a la Zebra por socket TCP. Lanza OSError si no puede conectar."""
    ip, port, timeout = _config()
    with socket.create_connection((ip, port), timeout=timeout) as sock:
        sock.sendall(zpl.encode("utf-8"))
    return {"ip": ip, "port": port}
