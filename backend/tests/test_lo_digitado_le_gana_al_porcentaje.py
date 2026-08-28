# -*- coding: utf-8 -*-
"""EL MONTO DIGITADO LE GANA AL PORCENTAJE.

**El agujero.** Management Fee, Royalties y Capital Reserve tienen dos caminos:
un % sobre el ingreso total (tab Management Fees) y un monto a mano (auxiliar
Below-GOP). Cuando había % cargado, la fórmula **pisaba** el monto digitado:

    if _d(_pct) > ZERO:
        seeds[_lc] = total_rev * _d(_pct)     # ← se lleva lo que había

Y no se notaba, porque las dos cifras caen en la misma línea del P&L: no hay
error, no hay aviso, y el total del below-GOP cuadra con la fórmula. El
`setdefault` de la rama contraria ya protegía el caso sin porcentaje —esa mitad
estaba arreglada desde antes—, así que el hueco quedaba justo donde el owner
carga las dos cosas.

Owner, 2026-08-27: «quiero que abras la opción manual para todos. y que no se
sobreescriba al menos que yo venga y lo quite».

La salida para volver al porcentaje es borrar el monto del auxiliar. Es lo que
dice la pantalla y es lo que prueba `test_sin_monto_digitado_manda_el_porcentaje`.
"""
from __future__ import annotations

from decimal import Decimal

from app.engine.pl_engine import ManualInputs, calculate_budget_pl_from_mapping

LINEAS = [
    {"line_code": "REV_ROOMS", "line_type": "MAPPED", "section": "REVENUES",
     "display_order": 1, "line_name": "Rooms"},
    {"line_code": "MGMT_FEE_3", "line_type": "MAPPED", "section": "OWNER / NON-OP EXPENSES",
     "display_order": 87, "line_name": "MANAGEMENT FEES (3%)"},
    {"line_code": "MGMT_FEE_5_ROYALTIES", "line_type": "MAPPED",
     "section": "OWNER / NON-OP EXPENSES", "display_order": 88,
     "line_name": "MANAGEMENT FEES (5%) Royalties"},
    {"line_code": "CAPITAL_RESERVE", "line_type": "MAPPED", "section": "CAPITAL",
     "display_order": 109, "line_name": "CAPITAL RESERVE"},
]
#: `revenue_by_line` va por el nombre de la línea de `RevenueResult`, no por
#: el `line_code` del reporte: lo traduce `REVENUE_LINE_TO_REPORT_LINE`. Con la
#: clave equivocada el ingreso se descarta en silencio y `total_rev` queda en 0,
#: así que el % daría 0 y la prueba pasaría por el motivo equivocado.
INGRESO = {"rooms": Decimal("100000")}


def _linea(res, code: str) -> Decimal:
    """Como `get_line`, pero grita si la línea no está: un 0 por ausencia se
    confunde con un 0 calculado, y las dos mitades de esta prueba comparan
    contra 0."""
    for ln in res:
        if ln.line_code == code:
            return ln.amount_usd
    raise AssertionError(f"la línea {code} no salió en el resultado")


def _correr(manual: ManualInputs, digitado: dict | None = None):
    return calculate_budget_pl_from_mapping(
        acct_rows=[], mappings=[], report_lines=LINEAS,
        revenue_by_line=INGRESO, manual=manual, extra_seeds=digitado or {},
        income_tax=Decimal("0"))


def test_el_monto_digitado_sobrevive_al_porcentaje():
    """El caso exacto: 3% sobre 100.000 daría 3.000, y hay 7.500 digitados."""
    res = _correr(ManualInputs(mgmt_fee_pct_3=Decimal("0.03")),
                  {"MGMT_FEE_3": Decimal("7500")})
    assert _linea(res, "MGMT_FEE_3") == Decimal("7500")


def test_sin_monto_digitado_manda_el_porcentaje():
    """La contraparte, y la salida que le queda al usuario: borrar el monto del
    auxiliar devuelve el control al %."""
    res = _correr(ManualInputs(mgmt_fee_pct_3=Decimal("0.03")))
    assert _linea(res, "MGMT_FEE_3") == Decimal("3000")


def test_un_monto_en_cero_no_bloquea_el_porcentaje():
    """Cero no es «digitado»: la línea vacía del auxiliar no puede apagar el %,
    porque el auxiliar guarda una fila en cero por cada línea que se abre."""
    res = _correr(ManualInputs(mgmt_fee_pct_3=Decimal("0.03")),
                  {"MGMT_FEE_3": Decimal("0")})
    assert _linea(res, "MGMT_FEE_3") == Decimal("3000")


def test_sin_porcentaje_ni_monto_la_linea_es_cero():
    res = _correr(ManualInputs())
    assert _linea(res, "MGMT_FEE_3") == Decimal("0")


def test_sin_porcentaje_el_monto_digitado_llega_igual():
    """Esta mitad ya estaba bien (el `setdefault`); se fija para que no se
    rompa al cambiar la otra."""
    res = _correr(ManualInputs(), {"MGMT_FEE_3": Decimal("7500")})
    assert _linea(res, "MGMT_FEE_3") == Decimal("7500")


def test_las_royalties_siguen_la_misma_regla():
    res = _correr(ManualInputs(mgmt_fee_pct_5=Decimal("0.05")),
                  {"MGMT_FEE_5_ROYALTIES": Decimal("1234.56")})
    assert _linea(res, "MGMT_FEE_5_ROYALTIES") == Decimal("1234.56")


def test_el_capital_reserve_sigue_la_misma_regla():
    """Antes tenía su propio `if` aparte, sin `setdefault` y sin mirar lo
    digitado. Ahora entra al mismo bucle que los honorarios."""
    res = _correr(ManualInputs(capital_reserve_pct=Decimal("0.03")),
                  {"CAPITAL_RESERVE": Decimal("9000")})
    assert _linea(res, "CAPITAL_RESERVE") == Decimal("9000")


def test_el_capital_reserve_por_porcentaje_sigue_funcionando():
    res = _correr(ManualInputs(capital_reserve_pct=Decimal("0.03")))
    assert _linea(res, "CAPITAL_RESERVE") == Decimal("3000")


def test_las_tres_lineas_se_pueden_digitar_a_la_vez():
    """Con los tres % cargados, los tres montos a mano tienen que sobrevivir:
    el bucle no puede arreglar una línea y pisar las otras dos."""
    res = _correr(
        ManualInputs(mgmt_fee_pct_3=Decimal("0.03"), mgmt_fee_pct_5=Decimal("0.05"),
                     capital_reserve_pct=Decimal("0.03")),
        {"MGMT_FEE_3": Decimal("1000"), "MGMT_FEE_5_ROYALTIES": Decimal("2000"),
         "CAPITAL_RESERVE": Decimal("3000")})
    assert _linea(res, "MGMT_FEE_3") == Decimal("1000")
    assert _linea(res, "MGMT_FEE_5_ROYALTIES") == Decimal("2000")
    assert _linea(res, "CAPITAL_RESERVE") == Decimal("3000")


def test_las_tres_lineas_tienen_renglon_en_el_auxiliar():
    """Sin renglón, «lo digitado gana» no sirve de nada: no hay dónde digitar."""
    import io
    import pathlib
    import re

    import pytest

    tsx = (pathlib.Path(__file__).resolve().parent.parent.parent
           / "frontend" / "app" / "nonop" / "checkbook" / "page.tsx")
    if not tsx.exists():
        pytest.skip("no está el front en este árbol")
    fuente = io.open(tsx, encoding="utf-8").read()
    bloque = fuente[fuente.index("const SECTIONS"):fuente.index("type Row =")]
    codigos = re.findall(r'(?<!account_)code:\s*"([A-Z0-9_]+)"', bloque)
    for code in ("MGMT_FEE_3", "MGMT_FEE_5_ROYALTIES", "CAPITAL_RESERVE"):
        assert code in codigos, f"{code} no tiene renglón en el auxiliar"


def test_los_renglones_dicen_manual():
    """El owner pidió el rótulo para distinguirlos de los que salen por %:
    «mete la línea y que diga manual para diferenciar»."""
    import io
    import pathlib
    import re

    import pytest

    tsx = (pathlib.Path(__file__).resolve().parent.parent.parent
           / "frontend" / "app" / "nonop" / "checkbook" / "page.tsx")
    if not tsx.exists():
        pytest.skip("no está el front en este árbol")
    fuente = io.open(tsx, encoding="utf-8").read()
    bloque = fuente[fuente.index("const SECTIONS"):fuente.index("type Row =")]
    for code in ("MGMT_FEE_3", "MGMT_FEE_5_ROYALTIES", "CAPITAL_RESERVE"):
        m = re.search(r'code:\s*"%s",\s*name:\s*"([^"]+)"' % code, bloque)
        assert m, f"no encontré el renglón de {code}"
        assert "manual" in m.group(1).lower(), (
            f"el rótulo de {code} no dice manual: {m.group(1)!r}")
