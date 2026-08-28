# -*- coding: utf-8 -*-
"""TODA LINEA OBLIGATORIA DE BELOW-GOP TIENE QUE TENER DONDE DIGITARSE.

**El agujero, medido en Amarena el 2026-08-27.** La pantalla `/nonop` («Gastos
del Propietario — Below GOP») arma sus secciones con una lista **clavada en el
TSX**, y de esa lista se derivan tres cosas: qué renglones se pueden llenar, el
subtotal de cada sección y el TOTAL BELOW-GOP. Traía cinco cuentas —8025, 8030,
8035, 8045, 8040— y le faltaban dos que `lineas_obligatorias.json` manda a esa
misma pantalla: **RENT (8000)** y **PROPERTIES INSURANCE (8015)**.

Lo que hacía el hueco difícil de ver: el aviso de la pantalla decía «23 de 33
líneas obligatorias están en cero» y contaba esas dos, así que pedía cargar algo
que no se podía cargar en ningún lado. El owner lo encontró al revés, buscando
dónde meter la renta: «revisa si en algún lugar está la opción de Rent… hay unos
gastos que no están quedando acá y hay que abrirlos».

Se prueba desde acá, contra el TSX, porque el dato que gobierna vive en el
backend (`lineas_obligatorias.json` y el `display_order` del mapeo) y la lista
que lo consume vive en el front. Una prueba de cada lado habría pasado las dos.
"""
from __future__ import annotations

import io
import json
import pathlib
import re

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PANTALLA = RAIZ.parent / "frontend" / "app" / "nonop" / "checkbook" / "page.tsx"
SEMILLA = RAIZ / "app" / "seed_data"

#: Van por fórmula (% del revenue / % del EBT), no a mano. El propio TSX lo dice
#: en su comentario: Owners Fee y Capital Reserve son el tab Management Fees, e
#: Income Tax lo calcula el P&L. No son huecos.
POR_FORMULA = {"MGMT_FEE_3", "MGMT_FEE_5_ROYALTIES", "CAPITAL_RESERVE", "INCOME_TAXES"}


@pytest.fixture(scope="module")
def fuente() -> str:
    if not PANTALLA.exists():
        pytest.skip(f"no está el front en este árbol: {PANTALLA}")
    return io.open(PANTALLA, encoding="utf-8").read()


@pytest.fixture(scope="module")
def lineas_de_la_pantalla(fuente: str) -> list[str]:
    """Los `code:` del bloque SECTIONS, en el orden en que se pintan.

    El lookbehind deja fuera `account_code:`, que también termina en «code:».
    """
    ini = fuente.index("const SECTIONS")
    fin = fuente.index("type Row =", ini)
    return re.findall(r'(?<!account_)code:\s*"([A-Z0-9_]+)"', fuente[ini:fin])


@pytest.fixture(scope="module")
def obligatorias_del_nonop() -> list[dict]:
    d = json.loads(io.open(SEMILLA / "lineas_obligatorias.json", encoding="utf-8").read())
    return [x for x in d["lineas"] if "Below GOP" in (x.get("donde_se_carga") or "")]


@pytest.fixture(scope="module")
def orden_del_pl() -> dict[str, int]:
    d = json.loads(io.open(SEMILLA / "mapping_pl.json", encoding="utf-8").read())
    return {r["line_code"]: r["display_order"] for r in d["report_line_config"]}


def test_ninguna_obligatoria_del_nonop_se_queda_sin_renglon(
        obligatorias_del_nonop, lineas_de_la_pantalla):
    faltan = sorted(x["line_code"] for x in obligatorias_del_nonop
                    if x["line_code"] not in lineas_de_la_pantalla
                    and x["line_code"] not in POR_FORMULA)
    assert not faltan, (
        "estas líneas obligatorias se cargan en /nonop y la pantalla no las "
        f"ofrece, así que no hay dónde digitarlas: {faltan}")


def test_la_renta_y_el_seguro_estan(lineas_de_la_pantalla):
    """Las dos que faltaban, por nombre. Si alguien saca una, esto lo dice."""
    assert "RENT" in lineas_de_la_pantalla
    assert "PROPERTY_INSURANCE" in lineas_de_la_pantalla


def test_la_renta_va_primero(lineas_de_la_pantalla, orden_del_pl):
    """«Deben ir de primero» (owner) — y es el orden del P&L, no una preferencia:
    RENT es la 86, la más baja del below-GOP."""
    assert lineas_de_la_pantalla[0] == "RENT", (
        f"el primer renglón es {lineas_de_la_pantalla[0]}")
    assert orden_del_pl["RENT"] == min(
        orden_del_pl[c] for c in lineas_de_la_pantalla if c in orden_del_pl)


def test_la_pantalla_respeta_el_orden_del_pl(lineas_de_la_pantalla, orden_del_pl):
    """Un auxiliar que ordena distinto al reporte se lee mal: el que cuadra a
    mano va renglón por renglón contra el P&L."""
    ordenes = [orden_del_pl[c] for c in lineas_de_la_pantalla if c in orden_del_pl]
    assert ordenes == sorted(ordenes), (
        "la pantalla pinta las líneas en otro orden que el P&L: "
        + ", ".join(f"{c}={orden_del_pl[c]}" for c in lineas_de_la_pantalla
                    if c in orden_del_pl))


def test_cada_renglon_de_la_pantalla_es_una_linea_del_pl(
        lineas_de_la_pantalla, orden_del_pl):
    """El auxiliar suma por `report_line_code` (ver `nonop_line_seeds_for_month`): un
    código que el P&L no conoce se digita, se guarda y **no aparece en ningún
    reporte**. No falla nada; la plata simplemente no llega."""
    huerfanos = sorted(c for c in lineas_de_la_pantalla if c not in orden_del_pl)
    assert not huerfanos, f"no son líneas del P&L: {huerfanos}"


def test_las_dos_cuentas_nuevas_existen_en_el_mapeo():
    """8000 y 8015 tienen que estar en `account_mapping`, si no el P&L por
    departamento y el drill-down del below-GOP no las reconocen."""
    d = json.loads(io.open(SEMILLA / "mapping_pl.json", encoding="utf-8").read())
    porcuenta = {m["account_code"]: m["report_line_code"] for m in d["account_mapping"]
                 if m["source_origin"] == "Below GOP"}
    assert porcuenta.get("8000") == "RENT"
    assert porcuenta.get("8015") == "PROPERTY_INSURANCE"


def test_el_rescate_del_cashflow_ya_contaba_estas_dos_lineas():
    """`_real_nonalloc_series` las tenía en `_NONALLOC_LINES` desde antes: el
    circuito siempre esperó que la renta y el seguro llegaran por el auxiliar.
    Lo único que faltaba era el renglón para escribirlas."""
    from app.api.pl_api import _NONALLOC_LINES

    assert "RENT" in _NONALLOC_LINES
    assert "PROPERTY_INSURANCE" in _NONALLOC_LINES
