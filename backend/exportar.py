"""P03 · Exportar a Excel las recepciones y sus productos por fecha.

Columnas alineadas con la línea base:
- Recepciones ↔ hoja de observación v2 (llegada, inicio de la descarga, fin) → KPI 1 y KPI 1b.
- Productos ↔ comparación libro–SAP del KPI 2 (fecha, proveedor, artículo, cantidad, unidad).
Los minutos se calculan con fórmulas de Excel para que se puedan revisar.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

AZUL = PatternFill("solid", fgColor="1F4FCF")
GRIS = PatternFill("solid", fgColor="EEF1F6")
BLANCO_NEGRITA = Font(bold=True, color="FFFFFF")
NEGRITA = Font(bold=True)


def _local(iso: str | None) -> datetime | None:
    """«2026-11-10T19:52:00-05:00» → datetime local sin zona (Excel no guarda zonas)."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso)).replace(tzinfo=None)
    except ValueError:
        return None


def _encabezado(ws: Any, columnas: list[tuple[str, int]]) -> None:
    for i, (titulo, ancho) in enumerate(columnas, start=1):
        celda = ws.cell(row=1, column=i, value=titulo)
        celda.fill = AZUL
        celda.font = BLANCO_NEGRITA
        celda.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = ancho
    ws.row_dimensions[1].height = 45
    ws.freeze_panes = "A2"


def construir_excel(recepciones: list[dict[str, Any]], ingresos: list[dict[str, Any]], desde: str, hasta: str) -> bytes:
    wb = Workbook()

    # ---------- Resumen (primera hoja; se llena al final con fórmulas) ----------
    resumen = wb.active
    resumen.title = "Resumen"

    # ---------- Recepciones ----------
    ws = wb.create_sheet("Recepciones")
    _encabezado(ws, [
        ("ID recepción", 11), ("Fecha", 11), ("Operador", 12), ("Proveedor", 34),
        ("Documento", 11), ("N.° documento", 18), ("N.° de productos confirmados", 13),
        ("Llegada a la planta", 11), ("Inicio de la descarga", 11), ("¿Inicio marcado con el 1.er producto?", 14),
        ("Fin de la recepción", 11), ("Espera (min) = inicio − llegada · KPI 1b", 15),
        ("Atención (min) = fin − inicio", 14), ("Tiempo en planta según la app (min) = fin − llegada · KPI 1", 17),
        ("Estado", 10),
    ])
    for r, rec in enumerate(recepciones, start=2):
        llegada, inicio, fin = _local(rec["hora_llegada"]), _local(rec["hora_inicio_descarga"]), _local(rec["hora_fin"])
        valores = [
            rec["id"], llegada.date() if llegada else None, rec["usuario_nombre"], rec["proveedor"],
            "Guía" if rec["documento_tipo"] == "guia" else "Factura", rec["documento_numero"],
            rec["productos"], llegada, inicio, "Sí" if rec["inicio_automatico"] else "No", fin,
            f'=IF(AND(H{r}<>"",I{r}<>""),ROUND((I{r}-H{r})*1440,1),"")',
            f'=IF(AND(I{r}<>"",K{r}<>""),ROUND((K{r}-I{r})*1440,1),"")',
            f'=IF(AND(H{r}<>"",K{r}<>""),ROUND((K{r}-H{r})*1440,1),"")',
            rec["estado"],
        ]
        for c, v in enumerate(valores, start=1):
            ws.cell(row=r, column=c, value=v)
        ws.cell(row=r, column=2).number_format = "yyyy-mm-dd"
        for c in (8, 9, 11):
            ws.cell(row=r, column=c).number_format = "hh:mm"
        for c in (12, 13, 14):
            ws.cell(row=r, column=c).fill = GRIS
    n_rec = len(recepciones) + 1  # última fila con datos

    # ---------- Productos ----------
    wp = wb.create_sheet("Productos")
    _encabezado(wp, [
        ("ID ingreso", 10), ("ID recepción", 11), ("Fecha", 11), ("Proveedor", 32), ("Documento", 20),
        ("Código Cyrano", 12), ("Código SAP", 13), ("Producto", 36), ("Código de barras", 16),
        ("Cantidad que llega", 11), ("Unidad de llegada", 11),
        ("Cantidad en unidad de planta", 12), ("Unidad de planta", 10),
        ("Lote", 14), ("Caducidad", 11), ("Calidad", 11), ("Hora de registro", 11), ("Operador", 12),
        ("Estado del registro", 11), ("Motivo de anulación", 30), ("Anulado por", 12), ("Anulado (hora)", 16),
    ])
    for r, ing in enumerate(ingresos, start=2):
        registro = _local(ing["created_at"])
        doc = ""
        if ing.get("documento_numero"):
            doc = f'{"Guía" if ing["documento_tipo"] == "guia" else "Factura"} {ing["documento_numero"]}'
        valores = [
            ing["id"], ing.get("recepcion_id"), registro.date() if registro else None, ing.get("proveedor") or "",
            doc, ing["codigo_cyrano"], ing.get("codigo_sap") or "", ing["nombre_producto"], ing["codigo_barra"] or "",
            ing["cantidad_ingresada"], ing["unidad_llega"], ing["cantidad_convertida"], ing["unidad_planta"],
            ing["lote"], ing["fecha_caducidad"], ing["estado_qc"], registro, ing.get("usuario_nombre") or "",
            ing.get("estado_registro") or "vigente", ing.get("anulado_motivo") or "", ing.get("anulado_por") or "",
            _local(ing.get("anulado_at")),
        ]
        for c, v in enumerate(valores, start=1):
            wp.cell(row=r, column=c, value=v)
        wp.cell(row=r, column=3).number_format = "yyyy-mm-dd"
        wp.cell(row=r, column=17).number_format = "hh:mm"
        wp.cell(row=r, column=22).number_format = "yyyy-mm-dd hh:mm"
        if (ing.get("estado_registro") or "vigente") == "anulado":
            for c in range(1, 23):
                wp.cell(row=r, column=c).font = Font(color="8A8A8A", strike=True)
    n_ing = len(ingresos) + 1

    # ---------- Resumen con fórmulas ----------
    resumen.column_dimensions["A"].width = 52
    resumen.column_dimensions["B"].width = 16
    resumen.column_dimensions["C"].width = 60
    resumen["A1"] = "Recepción de materia prima · datos de la app (piloto)"
    resumen["A1"].font = Font(bold=True, size=14)
    resumen["A2"] = f"Periodo exportado: {desde} a {hasta}"
    generado = datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M")
    resumen["A3"] = f"Generado: {generado} (hora de Ecuador)"
    filas = [
        ("Recepciones", f"=COUNT(Recepciones!A2:A{max(n_rec, 2)})", "Todas las del periodo."),
        ("Recepciones cerradas (con hora de fin)", f'=COUNTIF(Recepciones!O2:O{max(n_rec, 2)},"cerrada")', "Solo estas tienen tiempo en planta."),
        ("Tiempo en planta según la app · promedio (min)", f'=IFERROR(AVERAGE(Recepciones!N2:N{max(n_rec, 2)}),"")', "KPI 1. Línea base (bitácora, abr–ago 2026): 14,48 min; semana en planta: 17,7 min."),
        ("Tiempo en planta según la app · mediana (min)", f'=IFERROR(MEDIAN(Recepciones!N2:N{max(n_rec, 2)}),"")', "Línea base: mediana 11 min (bitácora)."),
        ("Espera del proveedor · promedio (min)", f'=IFERROR(AVERAGE(Recepciones!L2:L{max(n_rec, 2)}),"")', "KPI 1b = inicio de la descarga − llegada."),
        ("Espera del proveedor · mediana (min)", f'=IFERROR(MEDIAN(Recepciones!L2:L{max(n_rec, 2)}),"")', ""),
        ("Atención · promedio (min)", f'=IFERROR(AVERAGE(Recepciones!M2:M{max(n_rec, 2)}),"")', "Fin − inicio de la descarga."),
        ("Recepciones con inicio marcado por el 1.er producto", f'=COUNTIF(Recepciones!J2:J{max(n_rec, 2)},"Sí")', "En estas la espera es aproximada: nadie tocó «Empezar descarga»."),
        ("Productos confirmados (vigentes)", f'=COUNTIF(Productos!S2:S{max(n_ing, 2)},"vigente")', "Líneas para comparar con SAP en el KPI 2. Los anulados no cuentan."),
        ("Productos anulados", f'=COUNTIF(Productos!S2:S{max(n_ing, 2)},"anulado")', "Siguen en la hoja Productos (tachados) con su motivo."),
    ]
    resumen["A5"], resumen["B5"], resumen["C5"] = "Indicador", "Valor", "Nota"
    for c in "ABC":
        resumen[f"{c}5"].fill = AZUL
        resumen[f"{c}5"].font = BLANCO_NEGRITA
    for i, (nombre, formula, nota) in enumerate(filas, start=6):
        resumen.cell(row=i, column=1, value=nombre)
        resumen.cell(row=i, column=2, value=formula).number_format = "0.0"
        resumen.cell(row=i, column=3, value=nota).alignment = Alignment(wrap_text=True)
    resumen.cell(row=6, column=2).number_format = "0"
    resumen.cell(row=7, column=2).number_format = "0"
    resumen.cell(row=13, column=2).number_format = "0"
    resumen.cell(row=14, column=2).number_format = "0"
    resumen.cell(row=15, column=2).number_format = "0"

    # ---------- Leyenda ----------
    wl = wb.create_sheet("Leyenda")
    wl.column_dimensions["A"].width = 30
    wl.column_dimensions["B"].width = 100
    leyenda = [
        ("Hoja / columna", "Qué significa"),
        ("Recepciones", "Una fila por entrega de un proveedor, abierta en la app. Las horas son de Ecuador (UTC−5); en la base quedan con la zona escrita."),
        ("Llegada a la planta", "La pone el operador al abrir la recepción (propone la hora actual). Equivale a «Llegada a la planta» de la hoja de observación v2."),
        ("Inicio de la descarga", "Cuando se toca «Empezar descarga». Si no se toca, la marca el primer producto agregado (columna ¿Inicio marcado con el 1.er producto? = Sí)."),
        ("Fin de la recepción", "Cuando se toca «Cerrar recepción». No es la salida del proveedor de la bitácora: por eso el tiempo de la app se compara con la bitácora del mismo día."),
        ("KPI 1", "Tiempo del proveedor en planta. La línea base sale de la bitácora de seguridad (entrada − salida)."),
        ("KPI 1b", "Espera del proveedor = inicio de la descarga − llegada."),
        ("Productos", "Una fila por producto confirmado, ligado a su recepción. Sirve para comparar con las entradas de SAP (KPI 2) por fecha, proveedor y artículo."),
        ("Cantidad en unidad de planta", "Cantidad que llega × unidades por empaque × factor (regla del catálogo)."),
        ("Estado del registro", "vigente o anulado. Un ingreso confirmado no se borra: se anula con motivo, usuario y hora, y queda en la hoja tachado."),
        ("Código SAP", "Código del artículo en SAP (MovCompras), de la tabla de equivalencias código Cyrano – código SAP (P23). Vacío = equivalencia por confirmar con Cyrano."),
    ]
    for i, (a, b) in enumerate(leyenda, start=1):
        wl.cell(row=i, column=1, value=a).font = NEGRITA if i > 1 else BLANCO_NEGRITA
        wl.cell(row=i, column=2, value=b).alignment = Alignment(wrap_text=True)
        if i == 1:
            wl.cell(row=i, column=1).fill = AZUL
            wl.cell(row=i, column=2).fill = AZUL
            wl.cell(row=i, column=2).font = BLANCO_NEGRITA

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
