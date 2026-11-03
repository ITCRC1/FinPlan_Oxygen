# -*- coding: utf-8 -*-
"""«Channel Rooms Calculation», bajado como MODELO VIVO.

Owner, 2026-11-02: *«necesito que esta vista se pueda bajar tal cual como se ve
pero que esté formulado en forma automática todo… ADR, ocupación, total rooms,
fórmulas todo por mes y todo por full year. Que sólo se cambie ocupación y ADR
para llegar a un total»*.

## Qué cambia contra la descarga que había

La anterior bajaba **números**: noches e ingreso, ya calculados, sin fórmulas.
Servía para mirar, no para trabajar. En un archivo así, mover una noche no
mueve nada, y el que lo intenta tiene que rehacer la aritmética a mano —
exactamente lo que el archivo debería evitarle.

Acá se bajan **dos entradas por segmento y mes** —noches y tarifa promedio— y
**todo lo demás es fórmula**: ingreso, room nights, ADR, ocupación, RevPAR, y
la columna del año. Se cambia una noche de enero y el total del año se mueve
solo.

## Las tres reglas que el archivo tiene que respetar, porque el sistema las
## respeta

1. **Una noche de CORTESÍA ocupa la villa y no cobra.** Su ingreso es cero por
   fórmula, no por tener la tarifa en blanco: en blanco invita a escribir una,
   y entonces el archivo empezaría a cobrar lo que el sistema regala. Y sus
   noches quedan fuera del denominador del ADR, dentro del de la ocupación.

2. **El año se arma sumando las magnitudes y recalculando los promedios sobre
   esas sumas.** Un promedio de los doce ADR no es el ADR del año: con meses de
   volumen muy distinto sale corrido varios dólares. Por eso la columna «Total»
   de la tarifa promedio **divide**, no promedia.

3. **La ocupación sale de las noches, no al revés.** Abajo hay un bloque de
   OBJETIVO donde sí se teclea una ocupación y un ADR y se ve a qué ingreso
   llevarían — es para discutir el número, y está separado del modelo a
   propósito: si la ocupación fuera entrada, dos celdas dirían cuántas noches
   hay y nadie sabría cuál manda.
"""
from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

MESES_CORTOS = ("Ene", "Feb", "Mar", "Abr", "May", "Jun",
                "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")

ARIAL = "Arial"
AZUL = "1F3864"
AZUL_CLARO = "D9E1F2"
AMARILLO = "FFF2CC"
GRIS = "F2F2F2"
GRIS_FUERTE = "D9D9D9"

F_TIT = Font(name=ARIAL, size=14, bold=True, color="FFFFFF")
F_SUB = Font(name=ARIAL, size=9, italic=True, color="595959")
F_CAB = Font(name=ARIAL, size=9, bold=True, color="FFFFFF")
F_SEG = Font(name=ARIAL, size=10, bold=True, color=AZUL)
F_TXT = Font(name=ARIAL, size=10)
F_INP = Font(name=ARIAL, size=10, color="0000FF")   # azul = se teclea
F_TOT = Font(name=ARIAL, size=10, bold=True)
F_NOTA = Font(name=ARIAL, size=9, italic=True, color="7F7F7F")

M_USD = '$#,##0.00;($#,##0.00);-'
M_USD0 = '$#,##0;($#,##0);-'
M_NUM = '#,##0;(#,##0);-'
M_PCT = '0.0%;(0.0%);-'

_fino = Side(style="thin", color="BFBFBF")
BORDE = Border(left=_fino, right=_fino, top=_fino, bottom=_fino)
TAPA = Border(top=Side(style="medium", color="404040"))

#: A = etiqueta · B..M = los doce meses · N = el año.
COL_ETIQ = 1
COL_ENE = 2
COL_DIC = 13
COL_TOT = 14
LET = {m: get_column_letter(COL_ENE + m) for m in range(12)}
L_TOT = get_column_letter(COL_TOT)


def _c(ws, fila, col, valor, fuente=F_TXT, fmt=None, fill=None, ali="right",
       borde=True):
    x = ws.cell(row=fila, column=col, value=valor)
    x.font = fuente
    if fmt:
        x.number_format = fmt
    if fill:
        x.fill = PatternFill("solid", fgColor=fill)
    x.alignment = Alignment(horizontal=ali, vertical="center")
    if borde:
        x.border = BORDE
    return x


def _suma_de(filas: list[int], col: str) -> str:
    """`=B8+B12+B16…` — las filas de un bloque NO son contiguas.

    Un `SUM` de rango agarraría también las filas de tarifa y de etiqueta que
    hay en el medio. Sumarlas daría un total más alto sin que nada avise.
    """
    return "=" + "+".join(f"{col}{f}" for f in filas) if filas else "=0"


def construir_modelo(*, hotel: str, escenario: str, anio: int,
                     segmentos: list[dict], entradas: dict,
                     disponibles: dict[int, Decimal],
                     ingreso_sistema: Decimal | None = None) -> bytes:
    """El libro.

    `segmentos` — `[{code, nombre, genera_ingreso}]`, en el orden de la pantalla.
    `entradas`  — `{(code, mes 1-12): {"noches", "tarifa"}}`.
    `disponibles` — `{mes 1-12: noches disponibles}`.
    `ingreso_sistema` — el ingreso que el sistema tenía al bajar el archivo.
        Va al CONTROL del pie. Sin él, el control no se dibuja.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Channel Rooms"
    ws.sheet_view.showGridLines = False

    ws.column_dimensions["A"].width = 34
    for m in range(12):
        ws.column_dimensions[LET[m]].width = 12
    ws.column_dimensions[L_TOT].width = 14

    _c(ws, 1, COL_ETIQ, "CHANNEL ROOMS CALCULATION", F_TIT, fill=AZUL,
       ali="left", borde=False)
    ws.row_dimensions[1].height = 24
    _c(ws, 2, COL_ETIQ, f"{hotel} · {escenario} · bajado el "
                        f"{date.today().strftime('%d/%m/%Y')}",
       F_SUB, ali="left", borde=False)
    _c(ws, 3, COL_ETIQ,
       "Azul = se teclea (noches y tarifa promedio). Negro = fórmula. "
       "El ingreso, el ADR, la ocupación y el RevPAR salen solos.",
       F_NOTA, ali="left", borde=False)

    CAB = 5
    _c(ws, CAB, COL_ETIQ, "Segmento", F_CAB, fill="404040", ali="left")
    for m in range(12):
        _c(ws, CAB, COL_ENE + m, MESES_CORTOS[m], F_CAB, fill="404040",
           ali="center")
    _c(ws, CAB, COL_TOT, "Total año", F_CAB, fill="404040", ali="center")

    # ── un bloque de tres filas por segmento ────────────────────────────────
    fila = CAB + 1
    filas_noches: list[int] = []        # TODOS los segmentos
    filas_noches_cobran: list[int] = []  # sólo los que generan ingreso
    filas_ingreso: list[int] = []
    for s in segmentos:
        cobra = bool(s["genera_ingreso"])
        _c(ws, fila, COL_ETIQ, s["nombre"], F_SEG, ali="left", fill=GRIS)
        for m in range(12):
            _c(ws, fila, COL_ENE + m, None, F_TXT, fill=GRIS)
        _c(ws, fila, COL_TOT, None, F_TXT, fill=GRIS)
        if not cobra:
            ws.cell(row=fila, column=COL_ETIQ).comment = Comment(
                "Cortesía: ocupa la villa y NO cobra.\n"
                "Su ingreso es cero por fórmula y sus noches quedan fuera\n"
                "del denominador del ADR, pero dentro del de la ocupación.",
                "FinPlan")
        f_n, f_t, f_i = fila + 1, fila + 2, fila + 3

        _c(ws, f_n, COL_ETIQ, "    Noches", F_TXT, ali="left")
        _c(ws, f_t, COL_ETIQ, "    Tarifa promedio", F_TXT, ali="left")
        _c(ws, f_i, COL_ETIQ, "    Ingreso", F_TXT, ali="left")

        for m in range(12):
            col = COL_ENE + m
            L = LET[m]
            e = entradas.get((s["code"], m + 1), {})
            _c(ws, f_n, col, float(e.get("noches") or 0), F_INP, M_NUM,
               AMARILLO)
            if cobra:
                _c(ws, f_t, col, float(e.get("tarifa") or 0), F_INP, M_USD,
                   AMARILLO)
                _c(ws, f_i, col, f"={L}{f_n}*{L}{f_t}", F_TXT, M_USD,
                   AZUL_CLARO)
            else:
                # ⚠️ Cero por FÓRMULA, no por celda vacía. Vacía invita a
                # escribir una tarifa, y el archivo empezaría a cobrar lo que
                # el sistema regala — sin error y con el total cuadrando solo.
                _c(ws, f_t, col, "—", F_NOTA, None, GRIS, ali="center")
                _c(ws, f_i, col, "=0", F_TXT, M_USD, GRIS)

        _c(ws, f_n, COL_TOT, f"=SUM({LET[0]}{f_n}:{LET[11]}{f_n})", F_TOT,
           M_NUM, GRIS_FUERTE)
        # ⚠️ La tarifa del año DIVIDE: el promedio de los doce no es el del año.
        _c(ws, f_t, COL_TOT,
           f"=IFERROR({L_TOT}{f_i}/{L_TOT}{f_n},\"\")" if cobra else "—",
           F_TOT, M_USD if cobra else None, GRIS_FUERTE,
           ali="right" if cobra else "center")
        _c(ws, f_i, COL_TOT, f"=SUM({LET[0]}{f_i}:{LET[11]}{f_i})", F_TOT,
           M_USD, GRIS_FUERTE)

        filas_noches.append(f_n)
        if cobra:
            filas_noches_cobran.append(f_n)
        filas_ingreso.append(f_i)
        fila = f_i + 1

    ws.cell(row=CAB + 3, column=COL_TOT).comment = Comment(
        "La tarifa del año se obtiene dividiendo el ingreso del año entre las\n"
        "noches del año. Promediar las doce tarifas da otro número: con meses\n"
        "de volumen distinto, sale corrido varios dólares.", "FinPlan")

    # ── el cuadro de totales ────────────────────────────────────────────────
    fila += 1
    _c(ws, fila, COL_ETIQ, "TOTALES", F_CAB, fill=AZUL, ali="left")
    for m in range(12):
        _c(ws, fila, COL_ENE + m, None, F_CAB, fill=AZUL)
    _c(ws, fila, COL_TOT, None, F_CAB, fill=AZUL)

    f_disp = fila + 1
    f_cobran = fila + 2
    f_todas = fila + 3
    f_ing = fila + 4
    f_adr = fila + 5
    f_ocu = fila + 6
    f_ocu_t = fila + 7
    f_rev = fila + 8

    _c(ws, f_disp, COL_ETIQ, "Habitaciones disponibles", F_TXT, ali="left")
    _c(ws, f_cobran, COL_ETIQ, "Room nights (generan ingreso)", F_TXT, ali="left")
    _c(ws, f_todas, COL_ETIQ, "Room nights totales (incl. cortesía)", F_TXT,
       ali="left")
    _c(ws, f_ing, COL_ETIQ, "TOTAL INGRESOS", F_TOT, ali="left")
    _c(ws, f_adr, COL_ETIQ, "ADR", F_TOT, ali="left")
    _c(ws, f_ocu, COL_ETIQ, "% Ocupación", F_TOT, ali="left")
    _c(ws, f_ocu_t, COL_ETIQ, "% Ocupación (incl. cortesía)", F_TXT, ali="left")
    _c(ws, f_rev, COL_ETIQ, "RevPAR", F_TOT, ali="left")

    for m in range(12):
        col, L = COL_ENE + m, LET[m]
        _c(ws, f_disp, col, float(disponibles.get(m + 1) or 0), F_INP, M_NUM,
           AMARILLO)
        _c(ws, f_cobran, col, _suma_de(filas_noches_cobran, L), F_TXT, M_NUM,
           AZUL_CLARO)
        _c(ws, f_todas, col, _suma_de(filas_noches, L), F_TXT, M_NUM, AZUL_CLARO)
        _c(ws, f_ing, col, _suma_de(filas_ingreso, L), F_TOT, M_USD0, AZUL_CLARO)
        _c(ws, f_adr, col, f"=IFERROR({L}{f_ing}/{L}{f_cobran},\"\")", F_TOT,
           M_USD, AZUL_CLARO)
        _c(ws, f_ocu, col, f"=IFERROR({L}{f_cobran}/{L}{f_disp},\"\")", F_TOT,
           M_PCT, AZUL_CLARO)
        _c(ws, f_ocu_t, col, f"=IFERROR({L}{f_todas}/{L}{f_disp},\"\")", F_TXT,
           M_PCT, AZUL_CLARO)
        _c(ws, f_rev, col, f"=IFERROR({L}{f_ing}/{L}{f_disp},\"\")", F_TOT,
           M_USD, AZUL_CLARO)

    for f, fmt in ((f_disp, M_NUM), (f_cobran, M_NUM), (f_todas, M_NUM),
                   (f_ing, M_USD0)):
        _c(ws, f, COL_TOT, f"=SUM({LET[0]}{f}:{LET[11]}{f})", F_TOT, fmt,
           GRIS_FUERTE).border = TAPA
    # ⚠️ Los promedios del año salen de las SUMAS, no de promediar los meses.
    _c(ws, f_adr, COL_TOT, f"=IFERROR({L_TOT}{f_ing}/{L_TOT}{f_cobran},\"\")",
       F_TOT, M_USD, GRIS_FUERTE)
    _c(ws, f_ocu, COL_TOT, f"=IFERROR({L_TOT}{f_cobran}/{L_TOT}{f_disp},\"\")",
       F_TOT, M_PCT, GRIS_FUERTE)
    _c(ws, f_ocu_t, COL_TOT, f"=IFERROR({L_TOT}{f_todas}/{L_TOT}{f_disp},\"\")",
       F_TXT, M_PCT, GRIS_FUERTE)
    _c(ws, f_rev, COL_TOT, f"=IFERROR({L_TOT}{f_ing}/{L_TOT}{f_disp},\"\")",
       F_TOT, M_USD, GRIS_FUERTE)

    ws.cell(row=f_adr, column=COL_ETIQ).comment = Comment(
        "ADR = ingreso / room nights que GENERAN ingreso.\n"
        "Las noches de cortesía no entran acá —no cobran— pero sí entran en\n"
        "la ocupación, porque la villa está ocupada igual.", "FinPlan")

    # ── el bloque de objetivo ───────────────────────────────────────────────
    f = f_rev + 2
    _c(ws, f, COL_ETIQ, "OBJETIVO · a qué ingreso llevan una ocupación y un ADR",
       F_CAB, fill="BF8F00", ali="left")
    for m in range(12):
        _c(ws, f, COL_ENE + m, None, F_CAB, fill="BF8F00")
    _c(ws, f, COL_TOT, None, F_CAB, fill="BF8F00")
    _c(ws, f + 1, COL_ETIQ,
       "Se teclean los dos de abajo y el archivo dice cuántas noches y cuánto "
       "ingreso harían falta. No toca el modelo de arriba.", F_NOTA, ali="left",
       borde=False)

    o_ocu, o_adr, o_noc, o_ing, o_dif = f + 2, f + 3, f + 4, f + 5, f + 6
    _c(ws, o_ocu, COL_ETIQ, "% Ocupación objetivo", F_TXT, ali="left")
    _c(ws, o_adr, COL_ETIQ, "ADR objetivo", F_TXT, ali="left")
    _c(ws, o_noc, COL_ETIQ, "    Noches que implica", F_TXT, ali="left")
    _c(ws, o_ing, COL_ETIQ, "    Ingreso que implica", F_TOT, ali="left")
    _c(ws, o_dif, COL_ETIQ, "    Diferencia contra el modelo", F_TOT, ali="left")

    for m in range(12):
        col, L = COL_ENE + m, LET[m]
        _c(ws, o_ocu, col, f"={L}{f_ocu}", F_INP, M_PCT, AMARILLO)
        _c(ws, o_adr, col, f"={L}{f_adr}", F_INP, M_USD, AMARILLO)
        _c(ws, o_noc, col, f"={L}{o_ocu}*{L}{f_disp}", F_TXT, M_NUM, GRIS)
        _c(ws, o_ing, col, f"={L}{o_noc}*{L}{o_adr}", F_TOT, M_USD0, GRIS)
        _c(ws, o_dif, col, f"={L}{o_ing}-{L}{f_ing}", F_TOT, M_USD0, GRIS)

    _c(ws, o_ocu, COL_TOT, f"=IFERROR({L_TOT}{o_noc}/{L_TOT}{f_disp},\"\")",
       F_TOT, M_PCT, GRIS_FUERTE)
    _c(ws, o_adr, COL_TOT, f"=IFERROR({L_TOT}{o_ing}/{L_TOT}{o_noc},\"\")",
       F_TOT, M_USD, GRIS_FUERTE)
    for ff, fmt in ((o_noc, M_NUM), (o_ing, M_USD0), (o_dif, M_USD0)):
        _c(ws, ff, COL_TOT, f"=SUM({LET[0]}{ff}:{LET[11]}{ff})", F_TOT, fmt,
           GRIS_FUERTE)

    ws.cell(row=o_ocu, column=COL_ETIQ).comment = Comment(
        "Arrancan igual al modelo, así que la diferencia es cero hasta que se\n"
        "cambie algo. Es a propósito: un bloque que arranca en blanco obliga a\n"
        "retranscribir doce meses antes de poder comparar nada.", "FinPlan")

    # ── el control ──────────────────────────────────────────────────────────
    if ingreso_sistema is not None:
        fc = o_dif + 2
        _c(ws, fc, COL_ETIQ, "CONTROL · modelo contra el sistema", F_CAB,
           fill="404040", ali="left")
        _c(ws, fc, COL_TOT, None, F_CAB, fill="404040")
        _c(ws, fc + 1, COL_ETIQ, "Ingreso del sistema al bajar el archivo",
           F_TXT, ali="left")
        _c(ws, fc + 1, COL_TOT, float(ingreso_sistema), F_TXT, M_USD,
           AZUL_CLARO)
        _c(ws, fc + 2, COL_ETIQ, "Diferencia", F_TOT, ali="left")
        _c(ws, fc + 2, COL_TOT, f"={L_TOT}{f_ing}-{L_TOT}{fc + 1}", F_TOT,
           M_USD, AZUL_CLARO)
        _c(ws, fc + 3, COL_ETIQ,
           "Al bajar no da exactamente cero, y es correcto: el archivo "
           "REHACE el ingreso como noches × tarifa, y la tarifa está "
           "redondeada al centavo — el sistema la deriva sin redondear. Son "
           "centavos por noche. Si la diferencia se vuelve grande, es porque "
           "cambiaste algo arriba, que es justamente para lo que sirve.",
           F_NOTA, ali="left", borde=False)
        ws.cell(row=fc + 2, column=COL_ETIQ).comment = Comment(
            "Esta celda es el termometro del archivo: dice cuanto se "
            "aparta del presupuesto que tiene el sistema." + "\n" +
            "Arranca en unos centavos por el redondeo de la tarifa.",
            "FinPlan")

    ws.freeze_panes = f"{get_column_letter(COL_ENE)}{CAB + 1}"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
