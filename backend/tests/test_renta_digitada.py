# -*- coding: utf-8 -*-
"""EL IMPUESTO DE RENTA TAMBIEN SE PUEDE DIGITAR, Y LO DIGITADO MANDA.

Owner, 2026-08-27: «si, mejor que hay digitación».

**Por qué costó más que los otros tres.** Management Fee, Royalties y Capital
Reserve tienen UN cálculo detrás (% del ingreso), y con respetar lo digitado en
el motor alcanzaba. El impuesto tiene **dos**, en dos capas distintas:

  1. `pl_engine` — la tasa sobre el EBT, con el piso de cero aplicado al AÑO
     (`renta_por_mes`).
  2. `pl_api._apply_tax_correction` — la reparación de la COLUMNA ya sumada,
     que reescribe el impuesto en tres ramas: año en pérdida, ventana en
     pérdida, e |impuesto| < $1.

Respetar lo digitado sólo en el motor no alcanzaba: la reparación lo volvía a
pisar al armar el mes, el YTD o el Full Year. Por eso hay `_renta_digitada`, que
apaga la reparación por la misma puerta que ya usaba `lo_subido_manda`.

Un detalle que importa: el monto digitado se saca de la semilla **antes** del
pase 1. El impuesto va debajo del EBT y no puede participar de su cálculo — si
quedara en la semilla, la base del impuesto dependería de la fórmula del
reporte, y un cambio ahí la movería sin que se vea.
"""
from __future__ import annotations

from decimal import Decimal

from app.api.pl_api import _apply_tax_correction, _aggregate_selected
from app.engine.pl_engine import (ManualInputs, PLLineResult,
                                  calculate_budget_pl_from_mapping)

#: Las CALCULATED necesitan su `calculation_logic`: sin fórmula salen en cero y
#: las pruebas del EBT pasarían por comparar 0 contra 0. La cadena es la mínima
#: que hace falta para que el impuesto tenga una base real debajo.
LINEAS = [
    {"display_order": 1, "line_code": "REV_ROOMS", "line_name": "Rooms",
     "section": "REVENUES", "line_type": "MAPPED", "active": True},
    {"display_order": 30, "line_code": "TOTAL_REVENUES", "line_name": "Total",
     "section": "REVENUES", "line_type": "CALCULATED",
     "calculation_logic": "SUM(REV_*)", "active": True},
    {"display_order": 86, "line_code": "RENT", "line_name": "Rent",
     "section": "OWNER / NON-OP EXPENSES", "line_type": "MAPPED", "active": True},
    {"display_order": 129, "line_code": "EBT", "line_name": "EARNINGS BEFORE INCOME TAXES",
     "section": "TAX / NET PROFIT", "line_type": "CALCULATED",
     "calculation_logic": "TOTAL_REVENUES - RENT", "active": True},
    {"display_order": 131, "line_code": "INCOME_TAXES", "line_name": "INCOME TAXES (30%)",
     "section": "TAX / NET PROFIT", "line_type": "MAPPED", "active": True},
    {"display_order": 134, "line_code": "NET_PROFIT", "line_name": "NET PROFIT",
     "section": "TAX / NET PROFIT", "line_type": "CALCULATED",
     "calculation_logic": "EBT - INCOME_TAXES", "active": True},
]
INGRESO = {"rooms": Decimal("100000")}


def _linea(res, code: str) -> Decimal:
    for ln in res:
        if ln.line_code == code:
            return ln.amount_usd
    raise AssertionError(f"la línea {code} no salió en el resultado")


def _correr(manual=None, digitado=None, income_tax=None):
    return calculate_budget_pl_from_mapping(
        acct_rows=[], mappings=[], report_lines=LINEAS,
        revenue_by_line=INGRESO, manual=manual or ManualInputs(),
        extra_seeds=digitado or {}, income_tax=income_tax)


# ─── 1. El motor ──────────────────────────────────────────────────────────────
def test_el_impuesto_digitado_le_gana_a_la_tasa():
    res = _correr(ManualInputs(income_tax_rate=Decimal("0.30")),
                  {"INCOME_TAXES": Decimal("4321")})
    assert _linea(res, "INCOME_TAXES") == Decimal("4321")


def test_el_impuesto_digitado_le_gana_al_calculo_anual():
    """`income_tax` es el camino normal: el impuesto del mes ya resuelto con el
    año a la vista. Lo digitado también le gana a ese."""
    res = _correr(digitado={"INCOME_TAXES": Decimal("4321")},
                  income_tax=Decimal("9999"))
    assert _linea(res, "INCOME_TAXES") == Decimal("4321")


def test_sin_digitar_manda_el_calculo_anual():
    """La salida que le queda al usuario: borrar el monto devuelve el control."""
    res = _correr(income_tax=Decimal("9999"))
    assert _linea(res, "INCOME_TAXES") == Decimal("9999")


def test_un_impuesto_en_cero_no_apaga_el_calculo():
    """El auxiliar guarda una fila en cero por cada línea que se abre: abrir la
    línea no puede apagar el impuesto."""
    res = _correr(digitado={"INCOME_TAXES": Decimal("0")},
                  income_tax=Decimal("9999"))
    assert _linea(res, "INCOME_TAXES") == Decimal("9999")


def test_un_credito_negativo_digitado_si_cuenta():
    """Un mes en pérdida devenga crédito: el negativo es dato, no vacío."""
    res = _correr(digitado={"INCOME_TAXES": Decimal("-2500")},
                  income_tax=Decimal("9999"))
    assert _linea(res, "INCOME_TAXES") == Decimal("-2500")


def test_el_impuesto_digitado_no_entra_en_el_EBT():
    """Se saca de la semilla antes del pase 1. Si contaminara el EBT, el
    impuesto se estaría descontando dos veces: una en su línea y otra dentro de
    la base."""
    sin = _correr(income_tax=Decimal("0"))
    con = _correr(digitado={"INCOME_TAXES": Decimal("50000")},
                  income_tax=Decimal("0"))
    assert _linea(sin, "EBT") == _linea(con, "EBT")


def test_el_net_profit_resta_el_impuesto_digitado():
    res = _correr(digitado={"INCOME_TAXES": Decimal("4321")}, income_tax=Decimal("0"))
    assert _linea(res, "NET_PROFIT") == _linea(res, "EBT") - Decimal("4321")


# ─── 2. La reparación de la columna ───────────────────────────────────────────
def _columna(ebt: float, tax: float) -> list[dict]:
    return [{"month": 1,
             "kpis": {"rooms_available": 30, "rooms_occupied": 10, "guests": 20,
                      "adr": 0.0},
             "lines": [
                 PLLineResult(line_code="EBT", line_name="EBT",
                              section="TAX / NET PROFIT", amount_usd=Decimal(str(ebt))),
                 PLLineResult(line_code="INCOME_TAXES", line_name="Income Taxes",
                              section="TAX / NET PROFIT", amount_usd=Decimal(str(tax))),
                 PLLineResult(line_code="NET_PROFIT", line_name="Net Profit",
                              section="TAX / NET PROFIT",
                              amount_usd=Decimal(str(ebt - tax))),
             ]}]


def _monto(col: dict, code: str) -> float:
    for ln in col["lines"]:
        if ln["line_code"] == code:
            return ln["amount_usd"]
    raise AssertionError(f"la línea {code} no salió en la columna")


def test_la_reparacion_pisaba_el_impuesto_de_una_ventana_en_perdida():
    """La rama del problema, sin la bandera: EBT negativo con impuesto positivo
    se manda a cero. Un impuesto digitado se perdía acá."""
    amounts = {"EBT": -5000.0, "INCOME_TAXES": 3000.0, "NET_PROFIT": -8000.0}
    _apply_tax_correction(amounts)
    assert amounts["INCOME_TAXES"] == 0.0


def test_con_renta_digitada_la_columna_no_se_corrige():
    """Mismo caso, ahora por la vía real: la columna respeta lo digitado."""
    col = _aggregate_selected(_columna(ebt=-5000.0, tax=3000.0),
                              renta_digitada=True)
    assert _monto(col, "INCOME_TAXES") == 3000.0


def test_sin_renta_digitada_la_columna_si_se_corrige():
    """La contraparte: sin monto a mano la reparación sigue haciendo su trabajo.
    Si esta prueba se cae, la bandera apagó la corrección para todos."""
    col = _aggregate_selected(_columna(ebt=-5000.0, tax=3000.0))
    assert _monto(col, "INCOME_TAXES") == 0.0


def test_la_renta_digitada_no_apaga_la_correccion_de_otro_escenario():
    """La bandera es por escenario y por columna, no global."""
    con = _aggregate_selected(_columna(ebt=-5000.0, tax=3000.0), renta_digitada=True)
    sin = _aggregate_selected(_columna(ebt=-5000.0, tax=3000.0), renta_digitada=False)
    assert _monto(con, "INCOME_TAXES") == 3000.0
    assert _monto(sin, "INCOME_TAXES") == 0.0


def test_lo_subido_sigue_mandando_por_su_cuenta():
    """La puerta vieja no se tocó: un histórico sigue saliendo tal cual."""
    col = _aggregate_selected(_columna(ebt=-5000.0, tax=3000.0),
                              lo_subido_manda=True)
    assert _monto(col, "INCOME_TAXES") == 3000.0


# ─── 3. El renglón ────────────────────────────────────────────────────────────
def test_el_impuesto_tiene_renglon_rotulado_manual():
    import io
    import pathlib
    import re

    import pytest

    tsx = (pathlib.Path(__file__).resolve().parent.parent.parent
           / "frontend" / "app" / "nonop" / "checkbook" / "page.tsx")
    if not tsx.exists():
        pytest.skip("no está el front en este árbol")
    bloque = io.open(tsx, encoding="utf-8").read()
    bloque = bloque[bloque.index("const SECTIONS"):bloque.index("type Row =")]
    m = re.search(r'code:\s*"INCOME_TAXES",\s*name:\s*"([^"]+)"', bloque)
    assert m, "el impuesto no tiene renglón en el auxiliar"
    assert "manual" in m.group(1).lower(), m.group(1)


def test_el_auxiliar_acepta_la_linea_del_impuesto():
    """`bulk_replace_nonop` valida el `report_line_code` contra el reporte: si
    INCOME_TAXES no fuera una línea válida, el guardado daría 422."""
    import io
    import json
    import pathlib

    semilla = (pathlib.Path(__file__).resolve().parent.parent
               / "app" / "seed_data" / "mapping_pl.json")
    d = json.loads(io.open(semilla, encoding="utf-8").read())
    codigos = {r["line_code"] for r in d["report_line_config"]}
    assert "INCOME_TAXES" in codigos
