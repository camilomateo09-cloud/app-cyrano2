"""P09 · Lectura de códigos GS1-128 (etiquetas logísticas de las cajas).

Un código GS1-128 junta varios datos, cada uno con su identificador (IA) de 2 a 4 dígitos:
(01) GTIN de la caja, (02) GTIN del contenido, (10) lote, (17) caducidad, (15) consumir
preferentemente antes de, (11) fecha de producción, (21) serie, (37) cantidad, (91) dato interno…

El escáner del EDA52 lo manda de corrido; entre campos de largo variable puede venir el
separador FNC1 (carácter GS, \\x1d) o nada. Si no viene separador y el lote termina en algo
como «17AAMMDD» o «15AAMMDD», se separa (es lo que se ve en el catálogo: …10441761066N15270624).
"""

from __future__ import annotations

import calendar
import re
from typing import Any

GS = "\x1d"
FIJOS = {"00": 18, "01": 14, "02": 14, "11": 6, "12": 6, "13": 6, "15": 6, "16": 6, "17": 6, "20": 2}
VARIABLES = {"10": 20, "21": 20, "22": 20, "30": 8, "37": 8, "90": 30, "91": 90, "92": 90, "93": 90,
             "94": 90, "95": 90, "96": 90, "97": 90, "98": 90, "99": 90}
VARIABLES_3 = {"240": 30, "241": 30, "250": 30, "251": 30, "400": 30, "401": 30, "410": 13, "420": 20}
FECHAS = ("11", "12", "13", "15", "16", "17")


def fecha_gs1(aammdd: str) -> str | None:
    """AAMMDD → AAAA-MM-DD. DD = 00 es el último día del mes; 000000 = sin fecha."""
    if not re.fullmatch(r"\d{6}", aammdd or "") or aammdd == "000000":
        return None
    anio, mes, dia = 2000 + int(aammdd[:2]), int(aammdd[2:4]), int(aammdd[4:6])
    if not 1 <= mes <= 12:
        return None
    ultimo = calendar.monthrange(anio, mes)[1]
    if dia == 0:
        dia = ultimo
    if not 1 <= dia <= ultimo:
        return None
    return f"{anio:04d}-{mes:02d}-{dia:02d}"


def _leer_campos(texto: str) -> dict[str, str]:
    if "(" in texto:  # escrito a mano: (01)…(17)…(10)…
        return {ia: valor.strip() for ia, valor in re.findall(r"\((\d{2,4})\)([^()]*)", texto)}
    campos: dict[str, str] = {}
    pos = 0
    while pos < len(texto):
        if texto[pos] == GS:
            pos += 1
            continue
        dos, tres = texto[pos:pos + 2], texto[pos:pos + 3]
        if re.fullmatch(r"3[1-6]\d\d", texto[pos:pos + 4] or ""):  # pesos y medidas: 4 dígitos + 6
            ia, largo, fijo = texto[pos:pos + 4], 6, True
        elif dos in FIJOS:
            ia, largo, fijo = dos, FIJOS[dos], True
        elif tres in VARIABLES_3:
            ia, largo, fijo = tres, VARIABLES_3[tres], False
        elif dos in VARIABLES:
            ia, largo, fijo = dos, VARIABLES[dos], False
        else:
            break  # IA desconocido: se deja de leer
        pos += len(ia)
        if fijo:
            campos[ia] = texto[pos:pos + largo]
            pos += largo
        else:
            fin = texto.find(GS, pos)
            fin = len(texto) if fin == -1 else fin
            campos[ia] = texto[pos:fin][:largo]
            pos = fin
    return campos


def leer_gs1(codigo: str) -> dict[str, Any] | None:
    """Devuelve gtin, lote y caducidad si el código es GS1-128 con (01) o (02); si no, None."""
    texto = (codigo or "").strip()
    for prefijo in ("]C1", "]d2", "]Q3"):
        if texto.startswith(prefijo):
            texto = texto[len(prefijo):]
    if len(texto) <= 14 or not (texto.startswith(("01", "02", "(01)", "(02)"))):
        return None
    campos = _leer_campos(texto)
    gtin = campos.get("01") or campos.get("02")
    if not gtin or not re.fullmatch(r"\d{14}", gtin):
        return None
    # Sin separador, el lote puede «tragarse» una fecha al final: …10LOTE17AAMMDD
    if GS not in texto and "(" not in texto:
        for ia_var in ("10", "21"):
            valor = campos.get(ia_var, "")
            m = re.fullmatch(r"(.+?)(1[1-7])(\d{6})", valor)
            if m and m.group(2) in FECHAS and m.group(2) not in campos and fecha_gs1(m.group(3)):
                campos[ia_var] = m.group(1)
                campos[m.group(2)] = m.group(3)
    caducidad, fuente = None, None
    for ia in ("17", "15"):
        if fecha_gs1(campos.get(ia, "")):
            caducidad, fuente = fecha_gs1(campos[ia]), ia
            break
    return {
        "gtin": gtin,
        "lote": (campos.get("10") or "").strip() or None,
        "caducidad": caducidad,
        "caducidad_fuente": fuente,  # "17" caducidad · "15" consumir preferentemente antes de
        "campos": campos,
    }


def gtins_equivalentes(gtin: str) -> list[str]:
    """El mismo artículo puede estar en el catálogo como GTIN-14, GTIN-13 (sin el 0 inicial) o GTIN-12."""
    opciones = [gtin]
    recortado = gtin
    while recortado.startswith("0") and len(recortado) > 12:
        recortado = recortado[1:]
        opciones.append(recortado)
    return opciones
