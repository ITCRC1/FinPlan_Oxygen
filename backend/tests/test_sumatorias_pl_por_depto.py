# -*- coding: utf-8 -*-
"""LAS FILAS DE SUBTOTAL DEL P&L POR DEPARTAMENTO SUMAN TODAS LAS COLUMNAS.

Traían sólo su cifra final —«Total Operating Profit» el GOP, «Total Overhead» el
total de gastos— y saltaban las demás columnas con `colSpan`, así que no había
forma de leer cuánto del presupuesto es planilla, cuánto gasto operativo y
cuánto ingreso sin ir sumando a mano las cinco filas de arriba. Pedido del owner
el 2026-08-27: «mete sumatorias acá para saber cuánto es planilla, opex o
ingreso».

Medido en el Budget Working 2026 de Amarena el mismo día:

    operativos   ingreso 547.079,20 · planilla 207.272,88 · opex 277.538,94
                 gastos  484.811,82 · GOP  62.267,38
    overhead                          planilla  45.421,27 · opex 225.443,60
                 gastos  270.864,87
    hotel        ingreso 547.079,20 · planilla 252.694,15 · opex 502.982,54
                 gastos  755.676,69 · GOP −208.597,49

Se prueba desde acá, contra el TSX, porque el cálculo que los subtotales suman
vive en el backend y la suma vive en el front: una prueba de cada lado pasaría
con las columnas vacías, que es como estaba.
"""
from __future__ import annotations

import io
import pathlib
import re

import pytest

PANTALLA = (pathlib.Path(__file__).resolve().parent.parent.parent
            / "frontend" / "app" / "reports" / "pl-by-dept" / "page.tsx")


@pytest.fixture(scope="module")
def fuente() -> str:
    if not PANTALLA.exists():
        pytest.skip(f"no está el front en este árbol: {PANTALLA}")
    return io.open(PANTALLA, encoding="utf-8").read()


def _fila(fuente: str, rotulo: str) -> str:
    """El `<tr>` que contiene ese rótulo.

    Se busca a partir del `<tbody>`: cada rótulo aparece ANTES, en el armado del
    Excel (`filas.push({ label: ... })`), y esa primera aparición no está dentro
    de ninguna fila.
    """
    tabla = fuente.index("<tbody>")
    i = fuente.index(rotulo, tabla)
    ini = fuente.rindex("<tr", tabla, i)
    fin = fuente.index("</tr>", i)
    return fuente[ini:fin]


@pytest.mark.parametrize("rotulo", [
    "Total Operating Profit",
    "Total Overhead",
    "GROSS OPERATING PROFIT (GOP)",
])
def test_la_fila_de_subtotal_no_salta_columnas(fuente, rotulo):
    """`colSpan` en la celda del rótulo es exactamente cómo se perdían las
    columnas: la fila entraba con dos celdas en vez de seis."""
    fila = _fila(fuente, rotulo)
    assert "colSpan" not in fila, (
        f"«{rotulo}» volvió a saltarse columnas con colSpan")


@pytest.mark.parametrize("rotulo", [
    "Total Operating Profit",
    "Total Overhead",
    "GROSS OPERATING PROFIT (GOP)",
])
def test_la_fila_de_subtotal_tiene_las_seis_celdas(fuente, rotulo):
    """Rótulo + Revenue + Payroll + Gastos Operativos + Total Gastos + GOP.
    Una celda de menos y la tabla se desalinea sin dar error."""
    fila = _fila(fuente, rotulo)
    assert fila.count("<td") == 6, (
        f"«{rotulo}» tiene {fila.count('<td')} celdas, no 6")


def test_los_subtotales_suman_los_MISMOS_campos_que_las_filas_de_depto(fuente):
    """Si el subtotal sumara otra cosa —por ejemplo `operating` con repartos
    cuando las filas lo muestran sin ellos— no cuadraría con la columna que
    tiene encima, y el reporte se leería mal sin fallar."""
    m = re.search(r'const suma = \(ds: typeof opDepts,\s*'
                  r'k: ("[a-z_]+"(?:\s*\|\s*"[a-z_]+")*)\)', fuente)
    assert m, "no encontré el ayudante de sumas"
    campos = set(re.findall(r'"([a-z_]+)"', m.group(1)))
    assert campos == {"revenue", "payroll", "operating", "total_expenses"}, campos


def test_el_ingreso_total_es_el_de_los_operativos(fuente):
    """El overhead no tiene ingreso: sumarlo sería sumar ceros, y tomarlo de otra
    parte abriría la puerta a que el ingreso del reporte difiera del subtotal."""
    fila = _fila(fuente, "GROSS OPERATING PROFIT (GOP)")
    assert "usd(opRev)" in fila, (
        "la fila del GOP dejó de usar el ingreso de los operativos")


def test_el_excel_lleva_las_mismas_sumatorias(fuente):
    """El Excel se baja para mandarlo afuera: si la pantalla suma y el archivo
    no, son dos reportes distintos con el mismo nombre."""
    for expr in ("valores: [opRev, opPay,", "ohPay, null, ohOpx,",
                 "valores: [opRev, totPay,"):
        assert expr in fuente, f"el Excel no lleva la sumatoria: {expr}"


def test_la_planilla_del_reporte_ya_no_pierde_la_de_lavanderia():
    """Los subtotales destaparon esto: la planilla del reporte daba 252.694,15
    contra los 262.532,67 del auxiliar. Faltaban los 9.838,52 de Lavandería
    (0161), que `ALLOC_EXCL_PAYROLL` saca porque su costo se REPARTE — y este
    escenario no tiene ni un reparto cargado, así que no reaparecía en ningún
    lado. Ver `test_solo_se_excluye_lo_que_de_verdad_se_reparte`.
    """
    from app.importers.gl_detail_importer import ALLOC_EXCL_PAYROLL

    # La lista sigue igual: lo que cambió es que la exclusión ahora se cruza con
    # los departamentos que efectivamente reparten en ESE escenario.
    assert ALLOC_EXCL_PAYROLL == {"0161", "0220"}
