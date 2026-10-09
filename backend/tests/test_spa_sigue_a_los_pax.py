# -*- coding: utf-8 -*-
"""El Spa tiene que seguir a los pax, no a la última vez que alguien guardó.

## Lo que se encontró el 2026-10-08

El Budget 2027 de Oxygen tenía el Spa en **$30.141**. Su propia configuración
—capture 10% × $150 sobre 6.643 pax— da **$99.645**. La línea no coincidía con
el driver que supuestamente la calcula: era una copia de cuando los pax eran
otros (la instalación se clonó de Amarena, con ~2.009 pax) y se quedó ahí, con
una estacionalidad que no era la del escenario.

Dos recálculos seguidos no la movieron ni un centavo, porque el driver sólo
escribía al apretar guardar en su pantalla. El P&L cuadraba contra el número
viejo y nada lo señalaba — el mismo modo de falla del A&B.

Lo real, para dimensionar: $120.787 en doce meses contra $30.141 presupuestado.
"""
from decimal import Decimal as D

import pytest

from app.engine.recalculate import aplicar_spa
from app.engine.revenue_calculator import RevenueResult
from app.models.spa_budget import SpaBudget


class _Esc:
    id = "S1"
    hotel_id = "OXI"


class _Sesion:
    """Una sola consulta: las filas de `spa_budgets`."""
    def __init__(self, filas):
        self._filas = list(filas)

    async def execute(self, _q):
        return _Res(self._filas)


class _Res:
    def __init__(self, d):
        self._d = d

    def scalars(self):
        return self

    def all(self):
        return self._d


def _mes(m, cap="0.10", precio="150"):
    return SpaBudget(month=m, capture_pct=D(cap), avg_price=D(precio))


def _res(mes, guests):
    r = RevenueResult(month=mes, year=2027)
    r.guests = D(str(guests))
    return r


@pytest.mark.asyncio
async def test_el_spa_sale_de_los_pax_del_mes():
    """564 pax × 10% × $150 = $8.460. Lo que su config siempre dijo."""
    res = {1: _res(1, 564)}
    assert await aplicar_spa(_Sesion([_mes(1)]), _Esc(), res) is True
    assert res[1].spa == D("8460.00")


@pytest.mark.asyncio
async def test_si_cambian_los_pax_cambia_el_spa():
    """El defecto en una frase: antes no pasaba."""
    a, b = {1: _res(1, 564)}, {1: _res(1, 1128)}
    ses = lambda: _Sesion([_mes(1)])  # noqa: E731
    await aplicar_spa(ses(), _Esc(), a)
    await aplicar_spa(ses(), _Esc(), b)
    assert b[1].spa == a[1].spa * 2


@pytest.mark.asyncio
async def test_el_capture_puede_variar_por_mes():
    """La tabla guarda capture y precio POR MES: la temporada alta puede tener
    un capture distinto y el cálculo tiene que respetarlo."""
    res = {1: _res(1, 500), 2: _res(2, 500)}
    ses = _Sesion([_mes(1, "0.10"), _mes(2, "0.20")])
    await aplicar_spa(ses, _Esc(), res)
    assert res[2].spa == res[1].spa * 2


@pytest.mark.asyncio
async def test_sin_driver_configurado_no_toca_nada():
    """Una propiedad que digita el Spa a mano no cambia de comportamiento: sin
    filas, el monto plano que haya en `RevenueOther` sigue mandando."""
    res = {1: _res(1, 564)}
    res[1].spa = D("4321")
    assert await aplicar_spa(_Sesion([]), _Esc(), res) is False
    assert res[1].spa == D("4321")


@pytest.mark.asyncio
async def test_con_el_driver_en_cero_tampoco_toca_nada():
    """Filas con capture o precio en cero no son un driver configurado: son una
    tabla vacía. Tratarlas como driver pondría el Spa en cero sin que nadie lo
    haya pedido."""
    res = {1: _res(1, 564)}
    res[1].spa = D("4321")
    assert await aplicar_spa(
        _Sesion([_mes(1, "0", "0"), _mes(2, "0.10", "0")]), _Esc(), res) is False
    assert res[1].spa == D("4321")


@pytest.mark.asyncio
async def test_un_mes_sin_fila_se_queda_como_estaba():
    """La tabla puede estar a medio llenar mientras se construye el
    presupuesto: el mes sin configurar no se pisa con un cero."""
    res = {1: _res(1, 564), 2: _res(2, 510)}
    res[2].spa = D("999")
    await aplicar_spa(_Sesion([_mes(1)]), _Esc(), res)
    assert res[1].spa == D("8460.00")
    assert res[2].spa == D("999")


@pytest.mark.asyncio
async def test_sin_pax_no_hay_spa():
    """Un mes cerrado no vende tratamientos."""
    res = {1: _res(1, 0)}
    await aplicar_spa(_Sesion([_mes(1)]), _Esc(), res)
    assert res[1].spa == D("0.00")


@pytest.mark.asyncio
async def test_el_caso_de_oxygen():
    """El año completo del Budget 2027, con la config que ya tenía cargada."""
    pax = [564, 510, 564, 546, 564, 546, 564, 564, 546, 564, 546, 564]
    res = {m: _res(m, pax[m - 1]) for m in range(1, 13)}
    await aplicar_spa(_Sesion([_mes(m) for m in range(1, 13)]), _Esc(), res)
    # Los pax reales traen decimales (564,21…) y en produccion dan 99.645; aca
    # van redondeados, que es lo que hace comparable el numero a mano.
    total = sum(r.spa for r in res.values())
    assert total == D("99630.00")        # y NO los 30.141 que estaban guardados
    assert total > D("30141") * 3
