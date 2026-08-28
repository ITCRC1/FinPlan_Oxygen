# -*- coding: utf-8 -*-
"""EL COSTO DE VENTAS TIENE QUE LEER EL MISMO INGRESO QUE EL P&L.

**El agujero, medido en el Budget 2026 de Amarena (2026-08-27).** `costs_api`
tenía su propia copia del cargador de ingresos, y esa copia armaba el resultado
**siempre** desde los drivers —tarifas × ocupación × paquetes × `RevenueOther`—
sin mirar `scenario.revenue_source`. En un escenario en modo `checkbook` eso
devuelve un ingreso que no existe:

  · El Spa tenía **US$11.448** de ingreso y su costo al 75 % daba **0,00**.
  · Los Tours, **US$10.800** al 80 %, también **0,00**.
  · La fila REFERENCIA de la pantalla mostraba **US$524.831** —Rooms más Club,
    que sí viven en `RevenueOther`— o sea el ingreso de otro cálculo. El owner
    lo leyó como «me está poniendo el ingreso total del hotel».

Nada fallaba y nada avisaba: el costo de ventas simplemente no existía, y el
margen bruto salía 0 %.

La regla que fija esta prueba: **una sola forma de cargar el ingreso**. Dos
copias del mismo cálculo envejecen por separado, y la que quedó atrás fue la que
no aprendió a leer el checkbook.
"""
from __future__ import annotations

import inspect
from decimal import Decimal

from app.engine.cost_calculator import _get_revenue_line, calculate_cost_amount
from app.engine.revenue_calculator import RevenueResult
from app.models.cost_entry import CostEntry


def _costo(ref: str, pct: str) -> CostEntry:
    return CostEntry(id="x", scenario_id="esc", hotel_id="AMA", dept_code="0140",
                     account_code="5300", account_name="SPA COST",
                     calc_mode="DRIVER", driver_type="REVENUE_LINE",
                     driver_pct_or_rate=Decimal(pct), revenue_line_ref=ref)


def test_el_costo_del_spa_sale_del_ingreso_del_spa():
    """El caso exacto de Amarena: 75 % sobre los US$2.544 del Spa de diciembre."""
    rev = RevenueResult(month=12, year=2026)
    rev.rooms = Decimal("119040")     # el ingreso del hotel NO es la base
    rev.spa = Decimal("2544")
    monto = calculate_cost_amount(_costo("SPA", "0.75"), 12, rev)
    assert monto == Decimal("1908.00")


def test_cada_referencia_toma_SU_linea_y_no_otra():
    """Cambiar «Ref Ingreso» tiene que cambiar la base. Si todas devolvieran lo
    mismo, el selector sería decorativo — que es como se veía en pantalla."""
    rev = RevenueResult(month=12, year=2026)
    rev.rooms = Decimal("119040")
    rev.spa = Decimal("2544")
    rev.activities = Decimal("2400")
    assert _get_revenue_line(rev, "SPA") == Decimal("2544")
    assert _get_revenue_line(rev, "ACTIVITIES") == Decimal("2400")
    assert _get_revenue_line(rev, "ROOMS") == Decimal("119040")


def test_el_cargador_de_costos_respeta_el_modo_del_escenario():
    """Que no vuelva a existir una segunda vía que ignore el checkbook.

    Se mira el código porque el fallo es de RUTEO: la fórmula del costo estaba
    bien, lo que estaba mal era de dónde salía el ingreso que recibía.
    """
    from app.api.costs_api import _load_revenue_results

    fuente = inspect.getsource(_load_revenue_results)
    assert "load_revenue_results" in fuente, (
        "el costo de ventas volvió a tener su propio cargador de ingresos")
    assert "calculate_annual_revenue" not in fuente, (
        "volvió a calcular el ingreso por drivers sin mirar revenue_source")


def test_el_cargador_compartido_si_mira_el_modo():
    """La contraparte: el cargador al que se delega tiene que seguir ramificando
    por `revenue_source`. Si perdiera esa rama, delegar no arreglaría nada."""
    from app.engine.recalculate import load_revenue_results

    fuente = inspect.getsource(load_revenue_results)
    assert "revenue_source" in fuente
    assert "checkbook" in fuente


def test_una_referencia_desconocida_da_cero_y_no_el_total():
    """Sin referencia elegida el costo es cero, no «todo el ingreso». Caer al
    total convertiría un campo vacío en un costo enorme."""
    rev = RevenueResult(month=6, year=2026)
    rev.rooms = Decimal("27000")
    rev.spa = Decimal("1272")
    assert _get_revenue_line(rev, "") == Decimal("0")
    assert _get_revenue_line(rev, "NO_EXISTE") == Decimal("0")
