# -*- coding: utf-8 -*-
"""LA COMISIÓN DE TARJETA VA DENTRO DE A&G, NO EN SU PROPIA LÍNEA.

**De dónde salió la línea que el owner no pidió.** El P&L le mostraba, en
OVERHEAD EXPENSES, un renglón «Credit Card Commissions» de US$11.782,66 que él
nunca cargó por separado: es la cuenta **7120** del checkbook de Administración,
que el mapeo partía en dos reglas por vigencia —`OH_ADMIN` hasta jun-2026 y
`OH_CC_COMMISSIONS` desde jul-2026— porque SCP la exigía separada de A&G. El
efecto colateral era peor que la línea: Administrations salía en 73.323,68
cuando su OPEX más su planilla dan 85.106,34, y la diferencia no se veía en
ningún lado porque los dos renglones caen en el mismo subtotal.

Owner, 2026-08-27: «olvidemos la regla de Scp, quitemos eso. no puede ir
separado credit car comisions».

**Lo que NO se toca.** La fila 30 del Owners Q sigue donde está. `row_no` es la
llave con la que SCP consolida —lo dice el modelo— y el fixture
`fixture_SCPCWL_JUN2026.csv` se compara fila por fila contra el archivo real.
Queda sin fuente: sale en cero y su plata viaja en `UND_AG`.
"""
from __future__ import annotations

import io
import json
import pathlib

import pytest

BASE = pathlib.Path(__file__).resolve().parent.parent / "app" / "seed_data"


@pytest.fixture(scope="module")
def mapeo() -> dict:
    return json.loads(io.open(BASE / "mapping_pl.json", encoding="utf-8").read())


@pytest.fixture(scope="module")
def ownersq() -> dict:
    return json.loads(io.open(BASE / "owners_q.json", encoding="utf-8").read())


def test_la_7120_tiene_UNA_regla_y_apunta_a_administrations(mapeo):
    reglas = [m for m in mapeo["account_mapping"] if m["account_code"] == "7120"]
    assert len(reglas) == 1, (
        f"volvió a haber más de una regla para la 7120: "
        f"{[(r['report_line_code'], r.get('vigente_desde'), r.get('vigente_hasta')) for r in reglas]}")
    assert reglas[0]["report_line_code"] == "OH_ADMIN"
    assert reglas[0]["dept_code"] == "0180"


def test_la_regla_de_la_7120_no_tiene_vigencia(mapeo):
    """Con tope de vigencia, los meses de fuera del rango se caen del P&L.

    Es la parte silenciosa: no da error, la línea simplemente no recibe esos
    meses. Junio (US$991,78) era exactamente ese caso al revés.
    """
    regla = next(m for m in mapeo["account_mapping"] if m["account_code"] == "7120")
    assert not regla.get("vigente_desde")
    assert not regla.get("vigente_hasta")


def test_no_quedo_ninguna_linea_de_comision_de_tarjeta(mapeo):
    codigos = {r["line_code"] for r in mapeo["report_line_config"]}
    assert "OH_CC_COMMISSIONS" not in codigos
    assert not [m for m in mapeo["account_mapping"]
                if m["report_line_code"] == "OH_CC_COMMISSIONS"]


def test_administrations_sigue_siendo_una_sola_linea_del_overhead(mapeo):
    """La 7120 tiene que caer en la MISMA línea que el resto de Administración.

    Si cayera en otra —aunque fuese del mismo subtotal— volvería a estar
    separada, que es justo lo que se quitó.
    """
    admin = [m for m in mapeo["account_mapping"]
             if m.get("dept_code") == "0180" and m["source_origin"] == "Opex"]
    lineas = {m["report_line_code"] for m in admin}
    assert lineas == {"OH_ADMIN"}, f"el OPEX de Administración se abre en {sorted(lineas)}"


def test_la_fila_de_scp_conserva_su_posicion_pero_no_su_fuente(ownersq):
    fila = next(f for f in ownersq["report_lines"]
                if f["report_code"] == "UND_CC_COMMISSIONS")
    assert fila["row_no"] == 30, "mover la fila desalinea la consolidación de SCP"
    assert fila["lineas_pl"] == [], "volvió a tener fuente propia"
    assert not fila["operandos"]


def test_el_ruteo_del_owners_q_no_apunta_a_una_linea_que_no_existe(ownersq, mapeo):
    """Un `linea_pl` colgante no rompe nada: se pierde en silencio."""
    codigos_pl = {r["line_code"] for r in mapeo["report_line_config"]}
    colgantes = sorted({r["linea_pl"] for r in ownersq["report_line_mapping"]
                        if r["linea_pl"] not in codigos_pl})
    assert not colgantes, f"apuntan a líneas P&L inexistentes: {colgantes}"


def test_la_comision_viaja_en_ag(ownersq):
    """Si `UND_AG` no sumara `OH_ADMIN`, la 7120 se caería del reporte."""
    ag = next(f for f in ownersq["report_lines"] if f["report_code"] == "UND_AG")
    assert "OH_ADMIN" in ag["lineas_pl"]
