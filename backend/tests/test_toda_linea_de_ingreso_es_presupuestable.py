# -*- coding: utf-8 -*-
"""Toda línea de ingreso del P&L tiene que poder presupuestarse.

Owner, 2026-10-08: *«todas las líneas de ingreso deben estar acá; si meto otras
que no están deben aparecer acá»*.

## Lo que había

Siete líneas del reporte no tenían forma de llenarse desde ningún presupuesto:

* `REV_MISC_OTHER` — **$47.876 reales** en doce meses. El Actual la mostraba con
  plata y el Budget no podía ponerle un número.
* `REV_PRIVATE_BAR`, `REV_TIENDA`, `REV_AREC` — el mapa
  `REVENUE_LINE_TO_REPORT_LINE` las nombraba apuntando a atributos que **no
  existían** en `RevenueResult`, así que `revenue_seed_from_lines` las saltaba.
* `REV_CROWTHER_LAB`, `REV_ROOMS_OTHER`, `REV_CLARO_HUERTA` — estaban en
  `report_line_config` y en ningún mapa.

Y dos más que existían pero sólo salían del paquete, `REV_TOURS` y
`REV_TRANSPORTATION`: $209.002 reales en Oxygen, que no vende paquete, contra
cero presupuestable.

Nada de eso fallaba. El P&L cuadraba, el checkbook cuadraba, y la línea
simplemente nunca llegaba — que es el modo de falla caro de este sistema.

## La cadena que estas pruebas recorren

    REVENUE_LINES  →  RevenueResult.<campo>  →  REVENUE_LINE_TO_REPORT_LINE
                   →  línea REV_* de report_line_config

Si alguien agrega una línea al reporte y no la engancha, acá se entera. Si
alguien agrega un campo al mapa y se equivoca en el nombre, también.
"""
import json
from pathlib import Path

import pytest

from app.engine.pl_engine import REVENUE_LINE_TO_REPORT_LINE
from app.engine.recalculate import revenue_line_dict
from app.engine.revenue_calculator import RevenueResult
from app.models.revenue_entry import REVENUE_LINES, REVENUE_LINE_LABELS
from app.models.revenue_other import OTHER_REVENUE_LINES, DERIVED_REVENUE_LINES

SEMILLA = Path(__file__).resolve().parents[1] / "app" / "seed_data" / "mapping_pl.json"


def _lineas_del_reporte() -> set[str]:
    datos = json.loads(SEMILLA.read_text(encoding="utf-8"))
    return {
        r["line_code"] for r in datos["report_line_config"]
        if r.get("active") and str(r.get("line_code", "")).startswith("REV_")
    }


def _resultado() -> RevenueResult:
    return RevenueResult(month=1, year=2027)


def test_toda_linea_rev_del_reporte_tiene_de_donde_salir():
    """La que falló: siete líneas dibujadas y ninguna fuente."""
    huerfanas = sorted(_lineas_del_reporte() - set(REVENUE_LINE_TO_REPORT_LINE.values()))
    assert not huerfanas, (
        "líneas del P&L que ningún presupuesto puede llenar: " + ", ".join(huerfanas))


def test_el_mapa_no_nombra_atributos_que_no_existen():
    """`REV_MISC_OTHER` apuntaba a `misc_other`, que no estaba en el dataclass.

    `revenue_seed_from_lines` no revienta con eso: lo salta. Por eso hace falta
    mirarlo desde afuera.
    """
    r = _resultado()
    fantasmas = sorted(k for k in REVENUE_LINE_TO_REPORT_LINE if not hasattr(r, k))
    assert not fantasmas, "el mapa nombra atributos inexistentes: " + ", ".join(fantasmas)


def test_toda_linea_del_checkbook_tiene_su_campo():
    """`_REVENUE_LINE_TO_FIELD` se deriva bajando a minúsculas: si el campo no
    existe con ese nombre, el modo `checkbook` pierde la línea."""
    r = _resultado()
    sin_campo = sorted(ln for ln in REVENUE_LINES if not hasattr(r, ln.lower()))
    assert not sin_campo, "líneas sin campo en RevenueResult: " + ", ".join(sin_campo)


def test_toda_linea_del_checkbook_llega_al_pl():
    """Del checkbook al reporte, sin saltos: la línea tiene campo, el campo está
    en `revenue_line_dict`, y el dict tiene destino en el mapa."""
    emitidos = set(revenue_line_dict(_resultado()))
    perdidas = sorted(
        ln for ln in REVENUE_LINES
        if ln.lower() not in emitidos or ln.lower() not in REVENUE_LINE_TO_REPORT_LINE)
    assert not perdidas, "líneas que no llegan al P&L: " + ", ".join(perdidas)


def test_toda_linea_del_checkbook_tiene_nombre():
    """Sin etiqueta la pantalla muestra el código en crudo."""
    sin_nombre = sorted(set(REVENUE_LINES) - set(REVENUE_LINE_LABELS))
    assert not sin_nombre, "líneas sin etiqueta: " + ", ".join(sin_nombre)


def test_toda_linea_se_puede_presupuestar_en_drivers():
    """En modo `drivers` una línea o la deriva el motor o se digita como monto
    mensual. Si no es ninguna de las dos, no hay forma de presupuestarla."""
    sueltas = sorted(
        ln for ln in REVENUE_LINES
        if ln not in OTHER_REVENUE_LINES and ln not in DERIVED_REVENUE_LINES)
    assert not sueltas, "líneas sin forma de presupuestarse: " + ", ".join(sueltas)


def test_tours_y_transporte_se_pueden_digitar():
    """Lo que le faltaba a Oxygen: $209.002 reales y cero presupuestable, porque
    las dos salían SÓLO del paquete y esta propiedad no vende paquete."""
    assert "ACTIVITIES" in OTHER_REVENUE_LINES
    assert "TRANSPORT" in OTHER_REVENUE_LINES


def test_el_total_suma_todas_las_lineas():
    """`total_revenue` tiene que incluir cada línea: si una queda afuera, el
    total y el P&L se contradicen y nada lo señala."""
    r = _resultado()
    for ln in REVENUE_LINES:
        setattr(r, ln.lower(), __import__("decimal").Decimal("0"))
    for ln in REVENUE_LINES:
        campo = ln.lower()
        antes = r.total_revenue
        setattr(r, campo, __import__("decimal").Decimal("100"))
        assert r.total_revenue == antes + 100, f"{ln} no suma al total"
        setattr(r, campo, __import__("decimal").Decimal("0"))


@pytest.mark.parametrize("linea,destino", [
    ("MISC_OTHER", "REV_MISC_OTHER"),
    ("TIENDA", "REV_TIENDA"),
    ("PRIVATE_BAR", "REV_PRIVATE_BAR"),
    ("AREC", "REV_AREC"),
    ("CROWTHER", "REV_CROWTHER_LAB"),
    ("ROOMS_OTHER", "REV_ROOMS_OTHER"),
    ("CLARO_HUERTA", "REV_CLARO_HUERTA"),
])
def test_las_siete_que_faltaban(linea, destino):
    """Una por una, con nombre y apellido, para que el día que alguien borre
    una el mensaje diga cuál."""
    assert linea in REVENUE_LINES
    assert REVENUE_LINE_TO_REPORT_LINE[linea.lower()] == destino
