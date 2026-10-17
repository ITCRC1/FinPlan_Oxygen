# -*- coding: utf-8 -*-
"""La plantilla de Rooms por segmento: baja, se llena en Excel, sube.

Owner, 2026-10-16: *«por qué no creás un download file para actualizar los
datos vía upload: se baja el archivo, se actualizan los datos y se vuelve a
subir y se despliegan los datos»*.

Es el mismo trato que la plantilla del punto de equilibrio
(`break_even_xlsx`), y por la misma razón: hay trabajo que se hace mejor en
Excel —ordenar, arrastrar una celda, comparar meses de corrido, revisarlo con
alguien antes de subirlo— que celda por celda en una pantalla.

## Qué se edita y qué no

Se editan **dos cosas**, las mismas dos que se digitan en el libro del owner:

    Noches            por segmento y mes (filas 8, 14, 20… del libro)
    % Comisión        por segmento Y MES — en el libro es una sola columna
                      (`B67:B73`), acá son doce. Owner, 2026-10-16: *«pone el
                      primer mes y se replica a los 12 meses y manual se cambia
                      el mes que probablemente cambie»*.

y, sólo para los segmentos sin tarifario, la **tarifa propia** mes a mes.

Todo lo demás —ingreso, tarifa promedio, ocupación, ADR, RevPAR— **no viene en
la plantilla para llenar**: se deriva al subir. Ponerlo editable sería invitar a
cambiarlo, y entonces el ingreso dejaría de salir del RAC sin que nada avise.
Va abajo, en un bloque de sólo lectura, para que se vea con qué números se está
trabajando.

## Las reglas del archivo

**La hoja va protegida** con todo bloqueado menos lo editable. No es
desconfianza: el archivo vuelve y se aparea por la columna `clave`. Una columna
corrida a mano rompe el apareo y el que sube no se entera.

⚠️ **Una celda vacía NO es un cero.** Vacío significa «no toqué esta celda» y la
deja como está. Tratarla como cero convertiría un descuido —borrar una celda,
filtrar y no darse cuenta— en poner un mes en cero, y el total seguiría
cuadrando consigo mismo. Para poner cero hay que escribir `0`.

⚠️ **El encabezado se busca por CONTENIDO, no por número de fila.** El día que
la leyenda crezca una línea, el archivo que alguien tenía a medio llenar tiene
que seguir subiendo.
"""
from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Protection

from app.export.excel_base import (align, fill, font, protect_sheet,
                                   set_col_widths, unlock, workbook_to_bytes)

_BLOQUEADA = Protection(locked=True)

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
         "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

#: Columnas fijas antes de los doce meses.
COL_CLAVE, COL_SEGMENTO, COL_QUE, COL_COMISION = 1, 2, 3, 4
COL_ENE = 5
COL_TOTAL = COL_ENE + 12

FILA_ENCABEZADO = 8

#: Lo que dice la columna «Qué». Es texto para el humano; el apareo va por
#: `clave`, que trae el tipo adentro.
ETIQUETA = {"NOCHES": "Noches", "COMISION": "% Comisión",
            "TARIFA": "Tarifa propia $"}


def clave_de(code: str, tipo: str) -> str:
    """`AGENCIAS` para las noches, `LONG_TERM|TARIFA` para la tarifa propia.

    El tipo va DENTRO de la clave y no en una columna aparte porque la columna
    se puede ordenar sola y dejar la fila apareada contra otra cosa.
    """
    return code if tipo == "NOCHES" else f"{code}|{tipo}"


def partir_clave(clave: str) -> tuple[str, str]:
    code, _, tipo = str(clave or "").strip().partition("|")
    return code.strip(), (tipo.strip().upper() or "NOCHES")


def construir_plantilla(
    segmentos: list[dict], hotel: str, escenario: str, anio: int,
    resumen: list[dict] | None = None,
) -> bytes:
    """`segmentos` trae, por segmento: code, nombre, comision, propia, noches,
    tarifas. `resumen` son las filas de sólo lectura del pie.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Noches por segmento"

    # ── La leyenda ───────────────────────────────────────────────────────────
    #
    # Va ARRIBA y no en otra hoja: una instrucción en otra pestaña es una
    # instrucción que no se lee.
    ws["A1"] = f"Rooms por segmento — {hotel} · {escenario} {anio}"
    ws["A1"].font = font(bold=True, size=13)
    ws["A2"] = ("Escribí las NOCHES y el % DE COMISIÓN de cada segmento, mes "
                "por mes. Son las únicas celdas editables.")
    ws["A3"] = ("Una celda VACÍA deja el valor como está. Para poner cero, "
                "escribí 0.")
    ws["A4"] = ("El ingreso, la tarifa promedio y la ocupación NO se escriben: "
                "salen del tarifario RAC al subir el archivo.")
    ws["A5"] = ("El resto de la hoja está bloqueado a propósito: el archivo se "
                "sube de vuelta y se aparea por la columna «clave».")
    ws["A6"] = ("Guardá en .xlsx y subilo desde la misma pantalla de donde lo "
                "bajaste. Primero te muestra qué cambiaría.")
    for r in (2, 3, 4, 5, 6):
        ws.cell(r, 1).font = font(size=10, color="4A5568")

    # ── Encabezado ───────────────────────────────────────────────────────────
    cabeceras = [(COL_CLAVE, "clave"), (COL_SEGMENTO, "Segmento"),
                 (COL_QUE, "Qué"), (COL_COMISION, "% Comisión")]
    for col, titulo in cabeceras:
        c = ws.cell(FILA_ENCABEZADO, col, titulo)
        c.font = font(bold=True, color="FFFFFF")
        c.fill = fill("2B6CB0" if col == COL_COMISION else "2D3748")
        c.alignment = align(h="center", wrap=True)
    for i, m in enumerate(MESES):
        c = ws.cell(FILA_ENCABEZADO, COL_ENE + i, m)
        c.font = font(bold=True, color="FFFFFF")
        c.fill = fill("2B6CB0")
        c.alignment = align(h="center")
    c = ws.cell(FILA_ENCABEZADO, COL_TOTAL, "Total")
    c.font = font(bold=True, color="FFFFFF")
    c.fill = fill("2D3748")
    c.alignment = align(h="center")

    ws.freeze_panes = ws.cell(FILA_ENCABEZADO + 1, COL_ENE)

    # ── Las filas ────────────────────────────────────────────────────────────
    r = FILA_ENCABEZADO
    for s in segmentos:
        for tipo in ("NOCHES", "COMISION", "TARIFA"):
            if tipo == "TARIFA" and not s.get("propia"):
                continue
            # Un segmento de tarifa propia no tiene comisión sobre el rack:
            # su tarifa YA es la neta. Traer la fila invitaría a llenarla.
            if tipo == "COMISION" and s.get("propia"):
                continue
            r += 1
            ws.cell(r, COL_CLAVE, clave_de(s["code"], tipo)).font = font(
                size=9, color="A0AEC0")
            ws.cell(r, COL_SEGMENTO, s["nombre"]).font = font(
                bold=(tipo == "NOCHES"))
            ws.cell(r, COL_QUE, ETIQUETA[tipo]).font = font(size=9,
                                                            color="4A5568")
            if tipo == "TARIFA":
                ws.cell(r, COL_COMISION, "tarifa propia").font = font(
                    size=9, italic=True, color="718096")
            valores = {"NOCHES": s["noches"], "COMISION": s["comisiones"],
                       "TARIFA": s["tarifas"]}[tipo]
            formato = {"NOCHES": "#,##0", "COMISION": "0.00%",
                       "TARIFA": "#,##0.00"}[tipo]
            for i in range(12):
                cel = ws.cell(r, COL_ENE + i, valores[i])
                cel.number_format = formato
                cel.fill = fill("EBF8FF")
                unlock(cel)
            tot = ws.cell(r, COL_TOTAL)
            if tipo == "NOCHES":
                # Fórmula y no número: si alguien cambia un mes en Excel, el
                # total se mueve con él. Un total congelado contradiría la fila
                # de al lado y no se sabría cuál mirar.
                col_ini = ws.cell(r, COL_ENE).column_letter
                col_fin = ws.cell(r, COL_ENE + 11).column_letter
                tot.value = f"=SUM({col_ini}{r}:{col_fin}{r})"
                tot.number_format = "#,##0"
            tot.protection = _BLOQUEADA

    # ── El pie de sólo lectura ───────────────────────────────────────────────
    #
    # Para ver con qué números se está trabajando. NO se lee de vuelta: lo que
    # manda es lo que se derive de las noches y la comisión.
    if resumen:
        r += 2
        c = ws.cell(r, COL_SEGMENTO, "ASÍ ESTÁ HOY (no se edita, no se lee)")
        c.font = font(bold=True, color="4A5568")
        for fila in resumen:
            r += 1
            ws.cell(r, COL_SEGMENTO, fila["label"]).font = font(
                size=9, color="4A5568")
            for i, v in enumerate(fila["valores"]):
                cel = ws.cell(r, COL_ENE + i, v)
                cel.number_format = fila.get("formato", "#,##0.00")
                cel.font = font(size=9, color="718096")
            cel = ws.cell(r, COL_TOTAL, fila.get("total"))
            cel.number_format = fila.get("formato", "#,##0.00")
            cel.font = font(size=9, color="718096")

    set_col_widths(ws, {COL_CLAVE: 20, COL_SEGMENTO: 32, COL_QUE: 15,
                        COL_COMISION: 12, COL_TOTAL: 13,
                        **{COL_ENE + i: 10 for i in range(12)}})
    protect_sheet(ws)
    return workbook_to_bytes(wb)


def leer_plantilla(crudo: bytes) -> list[tuple[str, object, list]]:
    """Devuelve `[(clave, comisión cruda, [doce valores crudos])]`.

    **Función PURA y sin criterio de negocio**: no convierte, no valida, no
    decide qué es un cero. Sólo encuentra el encabezado y saca las celdas.
    Quién puede cambiar qué lo decide el endpoint, que es el que ve la base.
    """
    import io

    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(crudo), data_only=True, read_only=True)
    ws = wb[wb.sheetnames[0]]
    filas = list(ws.iter_rows(values_only=True))

    cab = idx = None
    for i, fila in enumerate(filas):
        vals = [str(v).strip().lower() if v is not None else "" for v in fila]
        if "clave" in vals and "segmento" in vals:
            cab, idx = vals, i
            break
    if cab is None:
        raise ValueError("el archivo no tiene el encabezado de la plantilla")

    c_clave = cab.index("clave")
    # La comisión dejó de ser una columna: es una FILA por segmento, igual que
    # las noches. Se devuelve `None` para no romper a quien ya desempaqueta
    # tres valores.
    c_com = None
    # Los meses se ubican por su rótulo: si alguien mete una columna en el
    # medio, el archivo sigue subiendo igual.
    c_meses = []
    for m in MESES:
        try:
            c_meses.append(cab.index(m.lower()))
        except ValueError:
            raise ValueError(f"falta la columna del mes «{m}»")

    fuera: list[tuple[str, object, list]] = []
    for fila in filas[idx + 1:]:
        if c_clave >= len(fila):
            continue
        clave = str(fila[c_clave] or "").strip()
        if not clave:
            continue
        com = None
        meses = [fila[c] if c < len(fila) else None for c in c_meses]
        fuera.append((clave, com, meses))
    return fuera
