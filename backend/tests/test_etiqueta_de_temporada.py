# -*- coding: utf-8 -*-
"""Cada propiedad llama a sus temporadas como las llama.

El tarifario RAC se portó desde Ojochal, que vende con TRES niveles de tarifa
y los llama Pico, Alta y Verde. Oxygen vende con **dos** —`Origen Tarifa Rack`
del libro 2027 dice «RAC Alta» y «RAC Baja»— sobre tres rangos de fecha:
Alta (ene–abr), Baja (may–nov), Alta (dic).

## Lo que NO se hizo

Renombrar `rac_verde` a `rac_baja`. Arreglaría Oxygen y rompería Ojochal, que
tiene las tres y las llama por su nombre. Lo que cambia entre propiedades no
es cuántos niveles existen en la base: es **cómo se llaman** y **cuántos se
usan**.

Así que la casilla siguió siendo la llave técnica —`rac_villa_mes` mapea
`PICO`/`ALTA`/`VERDE` a su tarifa, y eso no se toca— y el nombre que ve el
usuario pasó a ser un dato del escenario.

## Lo que vigila esta prueba

Que la etiqueta sea **decorado**: si alguna vez decide una tarifa, dos
escenarios con etiquetas distintas sobre la misma casilla darían números
distintos con el mismo tarifario, y el total cuadraría consigo mismo.
"""
import inspect
import re
from datetime import date
from decimal import Decimal

import pytest

from app.engine import rack_tarifa
from app.models.rack_rooms import TEMPORADAS


class _Villa:
    def __init__(self, unidades, pico, alta, verde):
        self.unidades = unidades
        self.rac_pico, self.rac_alta, self.rac_verde = (
            Decimal(str(pico)), Decimal(str(alta)), Decimal(str(verde)))


class _Temp:
    def __init__(self, temporada, desde, hasta, etiqueta=None):
        self.temporada = temporada
        self.desde, self.hasta = desde, hasta
        self.etiqueta = etiqueta


#: El tarifario de Oxygen: dos niveles sobre tres rangos. La casilla PICO no
#: se usa, y por eso va en cero — no porque Oxygen «tenga dos temporadas»
#: escrito en algún lado.
OXYGEN = [
    _Temp("ALTA", date(2027, 1, 1), date(2027, 4, 30), "Alta"),
    _Temp("VERDE", date(2027, 5, 1), date(2027, 11, 30), "Baja"),
    _Temp("ALTA", date(2027, 12, 1), date(2027, 12, 31), "Alta"),
]


def test_la_etiqueta_no_cambia_ni_un_centavo():
    """Es lo único que hay que saber de la etiqueta: no decide nada."""
    villa = _Villa(7, 0, 698, 554)
    con = rack_tarifa.rac_villa_mes(villa, 2027, 6, OXYGEN)
    sin = rack_tarifa.rac_villa_mes(villa, 2027, 6, [
        _Temp(t.temporada, t.desde, t.hasta) for t in OXYGEN])
    assert con == sin == Decimal("554")


def test_la_casilla_sigue_decidiendo_la_tarifa():
    """Junio cae en VERDE: paga la tarifa baja aunque la etiqueta diga «Baja»."""
    assert rack_tarifa.rac_villa_mes(
        _Villa(7, 999, 698, 554), 2027, 6, OXYGEN) == Decimal("554")
    assert rack_tarifa.rac_villa_mes(
        _Villa(7, 999, 698, 554), 2027, 2, OXYGEN) == Decimal("698")


def test_diciembre_vuelve_a_la_casilla_alta():
    """Son DOS rangos sobre la misma casilla, y el de diciembre existe.

    Si se perdiera, diciembre quedaría sin temporada: el RAC del mes saldría
    diluido y el total del año seguiría cuadrando consigo mismo.
    """
    assert rack_tarifa.dias_sin_temporada(2027, 12, OXYGEN) == 0
    assert rack_tarifa.rac_villa_mes(
        _Villa(7, 0, 698, 554), 2027, 12, OXYGEN) == Decimal("698")


@pytest.mark.parametrize("mes", range(1, 13))
def test_ningun_mes_queda_sin_temporada(mes):
    assert rack_tarifa.dias_sin_temporada(2027, mes, OXYGEN) == 0


def test_una_casilla_sin_rango_no_rompe_nada():
    """PICO no tiene rango en Oxygen. Eso no es un hueco: es una casilla que
    esta propiedad no usa, y la pantalla la esconde."""
    assert "PICO" not in {t.temporada for t in OXYGEN}
    assert set(t.temporada for t in OXYGEN) <= set(TEMPORADAS)


def test_el_motor_no_mira_la_etiqueta():
    """La guarda de código: `rack_tarifa` no puede nombrar `etiqueta`.

    ⚠️ Se mira la fuente SIN prosa: este módulo explica la etiqueta y la
    nombra para contarlo. Hacer fallar la guarda por su propia explicación
    invita al arreglo que no hay que hacer — borrar la explicación.
    """
    src = inspect.getsource(rack_tarifa)
    for comilla in ('"""', "'''"):
        src = re.sub(comilla + r"[\s\S]*?" + comilla, "", src)
    src = re.sub(r"#[^\n]*", "", src)
    assert "etiqueta" not in src, (
        "el motor del tarifario empezó a mirar la etiqueta: dos escenarios "
        "con nombres distintos sobre la misma casilla darían números "
        "distintos con el mismo tarifario")


def test_la_etiqueta_viaja_al_consolidado():
    """La puerta del consolidado re-arma el cuadro llave por llave.

    Esa lista es a mano **a propósito**: `entradas` no sale de ahí, y el
    comentario de la ruta lo dice — «solo totales por mes y segmento; sin
    reservas ni huéspedes». O sea que no se puede derivar de `_ver`.

    El precio de esa decisión es que una llave nueva no viaja sola. Owner,
    2026-10-15: *«me preocupa que siempre haya datos que no viajen… o viajen
    mal»*. Con el rótulo de la temporada el número viaja bien y el nombre no,
    que es la peor de las dos: Hotel Consolidation diría «Verde» donde Oxygen
    vende «Baja», y nada fallaría.
    """
    src = inspect.getsource(
        __import__("app.api.consolidado_rooms_api", fromlist=["x"]).rooms_rack_rooms)
    for clave in ("temporada_etiquetas", "temporadas_usadas"):
        assert f'"{clave}"' in src, (
            f"«{clave}» dejó de viajar al consolidado: el tarifario llega con "
            f"los nombres de otra propiedad")
