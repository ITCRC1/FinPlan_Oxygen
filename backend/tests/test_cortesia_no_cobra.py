# -*- coding: utf-8 -*-
"""Una noche de cortesía ocupa la villa y NO cobra.

## Lo que pasaba

`derivar_mes` le ponía tarifa a los ocho segmentos por igual. El CPL no tiene
comisión cargada —no la necesita, no se vende—, y un segmento sin comisión se
lee como **0 %**, o sea «vende a tarifa rack». Así que la cortesía entraba al
ingreso a precio publicado.

Medido el 2026-10-16 al cargar el tarifario de Oxygen 2027: **138 noches y
$79.355,25** que el P&L daba por cobrados. El ingreso del año saltaba de
$1.777.873,95 a $1.857.229,20.

## Por qué no se veía

Nada fallaba. La ocupación salía bien —las noches sí ocupan la villa—, el
total cuadraba consigo mismo, y los controles del libro daban cero. Lo único
raro era el ADR, y hacia arriba: esas noches suman al numerador del ADR y no
al denominador, porque `calcular_mes` sí las saca de ahí. Un ADR alto en un
presupuesto no se lee como error.

## La regla

`genera_ingreso` ya existía en el catálogo y lo respetaban `calcular_mes` y
`kpis_rack`. El que no lo miraba era el motor del tarifario — el único de los
tres que INVENTA el ingreso en vez de leerlo.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.engine.rack_tarifa import derivar_mes
from app.models.canal_rooms import SEGMENTOS_SEMILLA


class _Villa:
    def __init__(self, unidades, alta, verde):
        self.unidades = unidades
        self.rac_pico = Decimal("0")
        self.rac_alta = Decimal(str(alta))
        self.rac_verde = Decimal(str(verde))


class _Temp:
    def __init__(self, temporada, desde, hasta):
        self.temporada, self.desde, self.hasta = temporada, desde, hasta


#: El tarifario de Oxygen 2027, en chiquito: enero cae entero en ALTA.
VILLAS = [_Villa(13, 682.769230769230, 547.615384615384)]
TEMPS = [_Temp("ALTA", date(2027, 1, 1), date(2027, 4, 30)),
         _Temp("VERDE", date(2027, 5, 1), date(2027, 11, 30)),
         _Temp("ALTA", date(2027, 12, 1), date(2027, 12, 31))]
GENERA = {code: gen for code, _nombre, gen in SEGMENTOS_SEMILLA}


def _enero(genera):
    return derivar_mes(VILLAS, TEMPS,
                       {"AGENCIAS": (Decimal("0.23"), False)},
                       {"AGENCIAS": Decimal("100"), "CPL": Decimal("4")},
                       2027, 1, genera=genera)


def test_el_cpl_no_cobra():
    s = _enero(GENERA)["segmentos"]["CPL"]
    assert s["ingreso"] == Decimal("0")
    assert s["tarifa"] == Decimal("0")


def test_el_cpl_tampoco_suma_a_precio_rack():
    """El libro del hotel tampoco lo cuenta: su «Total Ingreso Rack» de 2027
    son $2.141.428,69, sin las 138 noches de cortesía."""
    assert _enero(GENERA)["segmentos"]["CPL"]["ingreso_rack"] == Decimal("0")


def test_el_que_si_vende_no_se_toca():
    s = _enero(GENERA)["segmentos"]["AGENCIAS"]
    assert s["ingreso"] > Decimal("0")
    assert s["tarifa"] > Decimal("0")


def test_sin_el_catalogo_todos_cobran():
    """El respaldo es «cobra», y tiene que serlo.

    ⚠️ Al revés —no cobra el que no aparece— un segmento nuevo entraría en
    cero y el ingreso bajaría sin que nada avise. Con este respaldo, el que
    falta entra cobrando: se nota.
    """
    assert _enero(None)["segmentos"]["CPL"]["ingreso"] > Decimal("0")


def test_la_semilla_declara_quien_cobra():
    """El CPL no es una excepción escrita en el motor: es una columna."""
    assert GENERA["CPL"] is False
    assert all(gen for code, _n, gen in SEGMENTOS_SEMILLA if code != "CPL")


@pytest.mark.parametrize("modulo,funcion", [
    ("app.api.rack_rooms_api", "_rederivar"),
    ("app.engine.recalculate", "aplicar_canales_rooms"),
])
def test_todo_el_que_deriva_pasa_el_catalogo(modulo, funcion):
    """La guarda: `derivar_mes` tiene que recibir `genera` en los dos caminos
    que escriben, no sólo en el que se arregló primero."""
    import importlib
    import inspect

    src = inspect.getsource(getattr(importlib.import_module(modulo), funcion))
    if "derivar_mes(" not in src:
        pytest.skip(f"{funcion} dejó de derivar")
    assert "genera=" in src, (
        f"{modulo}.{funcion} llama a derivar_mes sin el catálogo: la "
        f"cortesía vuelve a cobrarse a tarifa rack")
