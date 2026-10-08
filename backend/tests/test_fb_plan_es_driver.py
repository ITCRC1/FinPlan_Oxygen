# -*- coding: utf-8 -*-
"""El A&B del plan tiene que sobrevivir al recálculo.

## Lo que pasó el 2026-10-08

Se cargó el A&B de Oxygen en Planning, se apretó «pasar al checkbook» —que
escribió $246.516,56 de Food y $143.842,41 de Beverage— y al recalcular **las
dos líneas quedaron en cero**.

No falló nada. En modo `drivers` el recálculo baja el ingreso derivado al
sub-mayor (`sincronizar_ingreso_derivado`), y el derivado de A&B salía de
`package_configs`: el Full Board de Corcovado, que Oxygen no vende y tiene
vacío. Escribió los ceros del modelo encima de lo cargado, en silencio, y el
P&L siguió cuadrando contra el número equivocado.

Por eso el plan de A&B pasó a ser **driver**. Estas pruebas cuidan las dos
mitades del arreglo:

1. `aplicar_plan_ab` llena FOOD y BEVERAGE en el camino de `drivers`, así que
   el recálculo ya no tiene ceros que bajar.
2. Donde no hay plan cargado, no toca nada: el Full Board sigue mandando.
"""
from decimal import Decimal as D

import pytest

from app.engine.recalculate import aplicar_plan_ab
from app.engine.revenue_calculator import RevenueResult
from app.models.fb_plan import FbPlanConfig, FbPlanMes
from app.models.sales_channel_config import SalesChannelConfig


class _Esc:
    def __init__(self, sid="S1"):
        self.id = sid
        self.hotel_id = "OXI"


class _Sesion:
    """Devuelve las filas que le pongan, sin tocar base.

    `aplicar_plan_ab` hace dos consultas y en este orden: la config y los meses.
    """
    def __init__(self, cfg, meses):
        self._tandas = [[cfg] if cfg is not None else [], list(meses)]

    async def execute(self, _q):
        datos = self._tandas.pop(0)
        return _Res(datos)


class _Res:
    def __init__(self, datos):
        self._d = datos

    def scalars(self):
        return self

    def all(self):
        return self._d

    def scalar_one_or_none(self):
        return self._d[0] if self._d else None


def _cfg():
    return FbPlanConfig(
        precio_desayuno=D("20"), precio_almuerzo=D("45"), precio_cena=D("60"),
        captura_desayuno=D("1"), captura_almuerzo=D("0.16"), captura_cena=D("0.16"),
        servicio_pct=D("0.10"), pct_comisionable=D("0.50"), bev_pct_food=D("0.5835"))


def _canales(mes):
    return [
        SalesChannelConfig(channel="TA", mix_pct=D("0.55"),
                           commission_pct=D("0.20"), month=mes),
        SalesChannelConfig(channel="DIRECT", mix_pct=D("0.45"),
                           commission_pct=D("0.10"), month=mes),
    ]


def _res(mes, guests):
    r = RevenueResult(month=mes, year=2027)
    r.guests = D(str(guests))
    return r


@pytest.mark.asyncio
async def test_el_plan_llena_food_y_beverage_en_el_camino_de_drivers():
    """Lo que no pasaba: con `package_configs` vacío el driver daba cero."""
    res = {1: _res(1, 564)}
    assert res[1].food == D("0")          # así llegaba antes del arreglo
    aplico = await aplicar_plan_ab(
        _Sesion(_cfg(), [FbPlanMes(month=1, pax_externos=50,
                                   ticket_externos=D("35"))]),
        _Esc(), res, _canales(1))
    assert aplico is True
    # 564 x 36,80 = 20.755,20 bruto - 7,75% + 1.750 de externos
    assert res[1].food == D("20896.67")
    assert res[1].beverage == D("12193.21")


@pytest.mark.asyncio
async def test_sin_plan_no_toca_nada():
    """La propiedad que vende paquete no cambia: la condición es que exista el
    plan, no el año ni el hotel."""
    res = {1: _res(1, 564)}
    res[1].food = D("99999")              # lo que puso el Full Board
    aplico = await aplicar_plan_ab(_Sesion(None, []), _Esc(), res, _canales(1))
    assert aplico is False
    assert res[1].food == D("99999")      # intacto


@pytest.mark.asyncio
async def test_sin_canales_no_descuenta():
    """Un escenario sin mezcla cargada no puede dejar el A&B en cero: sin canal
    no hay comisión, no hay factor cero."""
    res = {1: _res(1, 564)}
    await aplicar_plan_ab(
        _Sesion(_cfg(), []), _Esc(), res, [])
    # 564 x 36,80 bruto, sin descuento y sin externos
    assert res[1].food == D("20755.20")


@pytest.mark.asyncio
async def test_el_descuento_usa_el_factor_del_mes():
    """La mezcla se guarda por mes: dos meses con comisión distinta tienen que
    dar Food distinto sobre los mismos pax."""
    res = {1: _res(1, 564), 2: _res(2, 564)}
    canales = _canales(1) + [
        SalesChannelConfig(channel="TA", mix_pct=D("1"),
                           commission_pct=D("0.40"), month=2)]
    await aplicar_plan_ab(_Sesion(_cfg(), []), _Esc(), res, canales)
    assert res[2].food < res[1].food


@pytest.mark.asyncio
async def test_sin_pax_no_hay_comida_pero_el_externo_entra():
    """Un mes cerrado no vende comida de huésped. El externo, si se presupuestó,
    sí: entra por la puerta aunque el hotel no tenga a nadie durmiendo."""
    res = {1: _res(1, 0)}
    await aplicar_plan_ab(
        _Sesion(_cfg(), [FbPlanMes(month=1, pax_externos=50,
                                   ticket_externos=D("35"))]),
        _Esc(), res, _canales(1))
    assert res[1].food == D("1750.00")
