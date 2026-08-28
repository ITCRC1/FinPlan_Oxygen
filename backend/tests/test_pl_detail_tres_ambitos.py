# -*- coding: utf-8 -*-
"""
LOS TRES P&L DETAIL SON UNO SOLO, Y EL HOTEL ES EL CONSOLIDADO MENOS EL CLUB.

## Por qué existe (2026-08-27)

Owner, entregando `BUDGET 2026-AMA formato.xlsx`: *«lee bien estos formatos uno
a uno, creálos en Reporting … con la información de presupuesto Budget 2026»*.

Tres de las cuatro hojas pedidas son la misma cascada con un ámbito distinto. La
cuarta —`P&L Full Detail`— ya existía.

## La propiedad que esto vigila

    Consolidado - Club = Hotel

y **no es una sola resta: son tres**, que fue el primer bug de este archivo:

    TOTAL REVENUES              -  REV_CLUB
    Total Operating expenses    -  (OPEX_CLUB + COS_CLUB)
    de OPERATING PROFIT abajo   -  PROFIT_CLUB   (una sola vez)

Restar el resultado del Club —que es NEGATIVO— del ingreso lo hacía **subir**:
584,118 donde tenían que ser 397,039. Y el bloque de control seguía dando
diferencia 0, porque un total que se compara contra sus propias partes cuadra
aunque las partes estén mal. Lo delató cotejar contra el libro del owner.

## Y el otro que se escondió igual

En la hoja del Club, listar la planilla al lado del gasto operativo la contaba
DOS veces: `OPEX_CLUB` del motor ya la incluye —es el gasto del departamento,
no el gasto no-salarial—. Daba 279,184 de gasto donde el motor dice 187,079, y
también cerraba contra sí mismo. Por eso el control se computa contra la
UTILIDAD del motor y no contra la suma de las filas de arriba.
"""
import pathlib

import pytest

from app.api.pl_detail_api import (AMBITOS, CLUB, CONSOLIDADO, CLUB_FILAS,
                                   HOTEL_OVERHEAD, HOTEL_QUITA, _control,
                                   _plantilla_hotel, _que_resta_el_hotel, _serie)

RAIZ = pathlib.Path(__file__).resolve().parents[1]


def _codigos(plantilla):
    return {c for _t, _r, cods in plantilla for c in cods}


def _rotulos(plantilla, tipo=None):
    return [r for t, r, _c in plantilla if tipo is None or t == tipo]


# ── La cascada del owner, completa ───────────────────────────────────────────

@pytest.mark.parametrize("rotulo", [
    "TOTAL REVENUES", "Total Operationg expenses", "OPERATING PROFIT",
    "TOTAL OVERHEAD EXPENSES", "TOTAL GROSS OPERATING PROFIT",
    "TOTAL NON OP EXPENSES", "EBITDA BEFORE CAPITAL", "CAPITAL EXPENSE",
    "EBITDA AFTER CAPITAL", "EARNINGS BEFORE INCOME TAXES", "NET PROFIT",
])
def test_estan_todos_los_totales_del_libro(rotulo):
    assert rotulo in _rotulos(CONSOLIDADO)


def test_los_rotulos_conservan_las_erratas_del_owner():
    """«Total Operationg expenses» está mal escrito EN SU LIBRO.

    Corregirlo rompería el cotejo contra el archivo, que es para lo que sirve
    este reporte. La errata es parte del formato, no un descuido nuestro.
    """
    assert "Total Operationg expenses" in _rotulos(CONSOLIDADO)
    assert "Total Slary and Benefits" in _rotulos(CLUB_FILAS)
    assert "Miscellaneous  Revenue" in _rotulos(CONSOLIDADO)   # dos espacios


# ── Consolidado − Club = Hotel ───────────────────────────────────────────────

def test_el_hotel_saca_el_club_del_detalle():
    hotel = _plantilla_hotel(list(CONSOLIDADO))
    assert "Madresal Club" not in _rotulos(hotel, "det")
    assert "Madresal Club" in _rotulos(CONSOLIDADO, "det")


def test_el_hotel_abre_los_departamentos_de_servicio():
    hotel = _rotulos(_plantilla_hotel(list(CONSOLIDADO)), "det")
    for r in ("Claro Huerta", "Cafeteria", "Laundry"):
        assert r in hotel
    assert "Area Recreativa" not in hotel


def test_el_overhead_no_se_parte():
    """Administración, ventas y mantenimiento sirven al hotel y al Club.

    En el libro del owner el total de overhead es IDÉNTICO en las dos hojas; es
    lo que confirma que no se reparte.
    """
    hotel = _plantilla_hotel(list(CONSOLIDADO))
    def total(p):
        return [c for t, r, c in p if r == "TOTAL OVERHEAD EXPENSES"]
    assert total(hotel) == total(CONSOLIDADO) == [["TOTAL_OVERHEAD"]]
    assert _que_resta_el_hotel("TOTAL OVERHEAD EXPENSES", ["TOTAL_OVERHEAD"],
                               {}, [1.0] * 12) is None


# ── Las TRES restas, que no son una ──────────────────────────────────────────

@pytest.fixture
def libro():
    """Un mes con números distinguibles: si se resta el que no era, se nota."""
    return {
        "REV_CLUB": [100.0] * 12,
        "OPEX_CLUB": [70.0] * 12,
        "COS_CLUB": [5.0] * 12,
        "PROFIT_CLUB": [-40.0] * 12,     # NEGATIVO, como el real
    }


def test_al_ingreso_se_le_resta_el_ingreso_del_club(libro):
    r = _que_resta_el_hotel("TOTAL REVENUES", ["TOTAL_REVENUES"], libro, libro["PROFIT_CLUB"])
    assert r == [100.0] * 12, (
        "se está restando otra cosa: con el resultado (negativo) el ingreso del "
        "Hotel SUBIRÍA por encima del consolidado")


def test_al_gasto_se_le_resta_el_gasto_del_club(libro):
    r = _que_resta_el_hotel("Total Operationg expenses", ["TOTAL_OPERATING_EXPENSES"],
                            libro, libro["PROFIT_CLUB"])
    assert r == [75.0] * 12, "el gasto del Club es su opex MÁS su costo de ventas"


@pytest.mark.parametrize("rotulo", [
    "OPERATING PROFIT", "TOTAL GROSS OPERATING PROFIT", "EBITDA BEFORE CAPITAL",
    "EBITDA AFTER CAPITAL", "EARNINGS BEFORE INCOME TAXES", "NET PROFIT",
])
def test_de_operating_profit_para_abajo_se_corre_por_el_resultado(rotulo, libro):
    r = _que_resta_el_hotel(rotulo, ["LO_QUE_SEA"], libro, libro["PROFIT_CLUB"])
    assert r == [-40.0] * 12, (
        f"{rotulo} no se corre por el resultado del Club: ahí ingreso y gasto "
        "ya vienen netos y restar cualquier otra cosa los cuenta dos veces")


def test_una_linea_de_detalle_no_se_toca(libro):
    """Al Club se lo saca quitando su FILA, no restándole algo a las demás."""
    assert _que_resta_el_hotel("Administrations", ["OH_ADMIN"], libro,
                               libro["PROFIT_CLUB"]) is None


# ── La hoja del Club no cuenta la planilla dos veces ─────────────────────────

def test_el_gasto_del_club_no_suma_la_planilla_aparte():
    """`OPEX_CLUB` YA contiene la planilla del departamento."""
    total = [c for t, r, c in CLUB_FILAS if r == "Total Gastos"]
    assert total == [["OPEX_CLUB", "COS_CLUB"]], (
        "el total del Club está sumando la planilla por separado: OPEX_CLUB ya "
        "la trae, y el reporte cerraría igual contra sí mismo")
    # Y la fila de opex que se muestra al lado de la planilla tiene que ser la
    # que YA le restó la planilla.
    opex = [c for t, r, c in CLUB_FILAS if r == "Operating Expenses" and t == "det"]
    assert opex == [["@CLUB_OPEX_SIN_PLANILLA"]]


def test_el_seguro_del_club_es_memo_y_no_entra_al_total():
    """En el motor el seguro va bajo el GOP: meterlo en el total del
    departamento haría que la utilidad no sea la del motor."""
    memo = [r for t, r, c in CLUB_FILAS if "@CLUB_SEGURO" in c]
    assert memo and "memo" in memo[0].lower()
    assert "@CLUB_SEGURO" not in {c for t, r, cods in CLUB_FILAS
                                  if r in ("Total Gastos", "Total Operating Expenses")
                                  for c in cods}


# ── El control se calcula, no se escribe ─────────────────────────────────────

def _fila(rotulo, valor):
    return {"tipo": "tot", "rotulo": rotulo, "meses": [0.0] * 12,
            "ytd": valor, "full": valor}


def test_el_control_calcula_la_diferencia():
    filas = [_fila("TOTAL REVENUES", 100.0),
             _fila("Total Operationg expenses", 60.0),
             _fila("TOTAL OVERHEAD EXPENSES", 30.0),
             _fila("NET PROFIT", 10.0)]
    assert _control(filas)["diferencia"] == 0.0
    filas[-1] = _fila("NET PROFIT", 7.0)
    assert _control(filas)["diferencia"] == 3.0, (
        "un descuadre tiene que SALIR: el Excel del owner trae «Variance 0» "
        "escrito a mano, y eso no controla nada")


def test_el_club_usa_su_propia_cascada_en_el_control():
    """Con los rótulos del consolidado daba gasto 0 y se acusaba de un
    descuadre de 187,079 que era del control, no del dato."""
    filas = [_fila("TOTAL REVENUES", 150.0), _fila("Total Gastos", 187.0),
             _fila("NET PROFIT", -37.0)]
    assert _control(filas, "club")["gastos"] == 187.0
    assert _control(filas, "club")["diferencia"] == 0.0


# ── Higiene ──────────────────────────────────────────────────────────────────

def test_los_tres_ambitos_y_nada_mas():
    assert AMBITOS == ("consolidado", "hotel", "club")


def test_un_codigo_que_no_existe_suma_cero():
    """Una propiedad sin Private Bar tiene que ver el renglón en cero, no un 500."""
    assert _serie({}, ["NO_EXISTE"]) == [0.0] * 12


def test_la_pantalla_llega_por_las_tres_entradas_del_menu():
    nav = (RAIZ.parent / "frontend" / "components" / "TopNav.tsx").read_text(
        encoding="utf-8")
    for a in AMBITOS:
        assert f"/reports/pl-detail?ambito={a}" in nav, f"falta la entrada de {a}"
