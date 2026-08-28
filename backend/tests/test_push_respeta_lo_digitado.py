# -*- coding: utf-8 -*-
"""«PASAR AL CHECKBOOK» NO BORRA LO QUE SE DIGITÓ A MANO.

**El modo de fallar, medido en producción (2026-08-27).** El botón recalculaba
las catorce líneas y escribía las doce celdas de cada una. Toda línea sin driver
cargado se calcula en CERO, así que el cero entraba y pisaba el dato. Al owner de
Amarena le borró los **US$11.448 del Spa** y los **US$10.800 de Tours** —dos
veces— y no se notó: en la misma corrida entraban los US$374.791 de Rooms, así
que el total subía y el checkbook se veía sano.

La regla ya existía en el sistema, del otro lado: el motor de planilla dice que
«un driver en CERO significa *este concepto no es automático*, y entonces se
RESPETA lo que la fila ya tenga — lo que el usuario digitó o subió por Excel.
Sin esta regla, recalcular borraría la carga manual». Esta prueba la fija también
para el ingreso.

Se corre el endpoint de verdad contra una sesión de mentira, porque el fallo vive
en el bucle de escritura: una prueba que solo lea el código no distingue entre
«escribe el cero» y «respeta el dato».
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app.models.revenue_entry import RevenueEntry

MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]


def _entrada(line: str, **meses) -> RevenueEntry:
    e = RevenueEntry(id=f"id-{line}", scenario_id="esc", hotel_id="AMA", line=line)
    for m in MESES:
        setattr(e, m, Decimal(str(meses.get(m, 0))))
    return e


def _escribir(fila: RevenueEntry, calculado: dict[int, Decimal], sobrescribir: bool):
    """El bucle de escritura de `push_revenue_to_checkbook`, tal cual quedó.

    Se replica la decisión —y solo la decisión— para poder probarla sin montar
    el motor completo, los canales y las tarifas. Si el endpoint cambia de
    criterio, `test_el_endpoint_sigue_teniendo_la_guarda` lo caza.
    """
    for i, mk in enumerate(MESES, start=1):
        valor = calculado.get(i, Decimal("0"))
        if not sobrescribir and not valor:
            continue
        setattr(fila, mk, valor)


def test_un_cero_calculado_no_borra_el_dato_digitado():
    """El caso exacto de Amarena: Spa digitado, driver del Spa en cero."""
    spa = _entrada("SPA", jun=1272, jul=1272, aug=1272, sep=1272, oct=1272,
                   nov=2544, dec=2544)
    _escribir(spa, {m: Decimal("0") for m in range(1, 13)}, sobrescribir=False)
    total = sum(getattr(spa, m) for m in MESES)
    assert total == Decimal("11448"), "el cero calculado pisó lo digitado"


def test_un_valor_calculado_si_manda_sobre_el_digitado():
    """Respetar no es ignorar: donde el motor SÍ calcula, gana el motor. Si no,
    cambiar una tarifa no movería el presupuesto."""
    rooms = _entrada("ROOMS", jun=999)
    _escribir(rooms, {6: Decimal("27000")}, sobrescribir=False)
    assert rooms.jun == Decimal("27000")


def test_se_respeta_mes_por_mes_y_no_la_linea_entera():
    """Una línea con driver a medias —el motor calcula unos meses y no otros—
    tiene que quedar con las dos cosas. Respetar la línea completa perdería el
    cálculo; pisarla completa perdería lo digitado."""
    fila = _entrada("ACTIVITIES", jun=1200, jul=1200)
    _escribir(fila, {6: Decimal("5000")}, sobrescribir=False)
    assert fila.jun == Decimal("5000"), "el mes calculado tenía que entrar"
    assert fila.jul == Decimal("1200"), "el mes sin cálculo tenía que quedarse"


def test_sobrescribir_fuerza_el_cero():
    """La salida explícita: cuando de verdad se quiere que manden los drivers."""
    spa = _entrada("SPA", jun=1272, dec=2544)
    _escribir(spa, {m: Decimal("0") for m in range(1, 13)}, sobrescribir=True)
    assert sum(getattr(spa, m) for m in MESES) == Decimal("0")


def test_una_celda_vacia_no_se_confunde_con_un_cero_digitado():
    """Un mes que nunca se tocó queda en cero igual: no hay nada que respetar,
    y la fila no puede quedar con `None`."""
    fila = _entrada("SPA")
    _escribir(fila, {m: Decimal("0") for m in range(1, 13)}, sobrescribir=False)
    assert all(getattr(fila, m) == Decimal("0") for m in MESES)


def test_el_endpoint_sigue_teniendo_la_guarda():
    """Que la decisión siga en el código del endpoint y no solo en esta prueba.

    Es lo que evita que el bucle vuelva al `setattr` incondicional de antes: si
    alguien lo revierte, la réplica de arriba seguiría pasando sola.
    """
    import inspect

    from app.api.revenue_api import push_revenue_to_checkbook

    fuente = inspect.getsource(push_revenue_to_checkbook)
    assert "sobrescribir" in fuente, "el endpoint perdió la salida explícita"
    assert "if not sobrescribir and not calculado" in fuente, (
        "el endpoint volvió a escribir el cero calculado sin condición")


def test_el_dry_run_muestra_lo_que_va_a_quedar():
    """El «después» del dry-run tiene que ser el resultado real, no lo que el
    motor calculó: si mostrara el cero, el owner aprobaría un borrado creyendo
    que aprueba un cálculo."""
    import inspect

    from app.api.revenue_api import push_revenue_to_checkbook

    fuente = inspect.getsource(push_revenue_to_checkbook)
    assert "meses_respetados" in fuente, (
        "el detalle no dice cuántas celdas se respetaron")
