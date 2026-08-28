# -*- coding: utf-8 -*-
"""EL BELOW-GOP SE ABRE POR CUENTA **Y POR DEPARTAMENTO**.

**Por qué.** La línea «Non Allocated Expenses» del P&L suma las cuentas 8xxx sin
mirar el departamento, y eso es correcto: el below-GOP no se asigna, va por
debajo del GOP departamental. Pero el drill-down existe justamente para poder
abrir esa línea, y agregaba también por cuenta sola — así que el Owners Fees del
Club Madresal y el de la propiedad caían juntos en un renglón y no había forma
de separarlos.

Caso real (Amarena, 2026-08-27): el Club trae **8005 Owners Fees US$18.915** y
**8015 Property Insurance US$1.670** en su propio checkbook. El owner pidió que
queden en el Club, que no se mezclen con Property Expenses y que **viajen con el
P&L por departamento**. Con el desglose por departamento alcanza: no hizo falta
marcar los nombres.

Segundo arreglo, del mismo tamaño: el rótulo salía de una tabla fija de nombres
que **ignoraba el `account_name` de la fila**, así que cualquier marca que se le
pusiera a una cuenta no llegaba a la pantalla.
"""
from __future__ import annotations

import asyncio
import inspect
from decimal import Decimal

from app.models.belowgop_account_entry import BelowGopAccountEntry


class _FakeResult:
    def __init__(self, filas): self._filas = filas
    def scalars(self): return self
    def all(self): return self._filas


class _FakeSession:
    """Devuelve las filas Below-GOP en la primera consulta y nada después.

    El respaldo por `ActualEntry`/`NonOpEntry` solo corre si la primera no trajo
    nada, así que con esto alcanza para probar la rama que importa.
    """
    def __init__(self, filas): self._filas = filas; self._n = 0
    async def execute(self, *a, **kw):
        self._n += 1
        return _FakeResult(self._filas if self._n == 1 else [])


class _Esc:
    id = "esc"


def _fila(cuenta, depto, nombre, dic):
    e = BelowGopAccountEntry(id=f"{cuenta}-{depto}", scenario_id="esc", hotel_id="AMA",
                             dept_code=depto, account_code=cuenta, account_name=nombre)
    for m in ("jan", "feb", "mar", "apr", "may", "jun",
              "jul", "aug", "sep", "oct", "nov", "dec"):
        setattr(e, m, Decimal(str(dic.get(m, 0))))
    return e


def _correr(filas, mes=12):
    from app.api.pl_api import _nonalloc_desde_cuentas
    partes, _src, _link = asyncio.run(
        _nonalloc_desde_cuentas(_FakeSession(filas), _Esc(), mes))
    return partes


def test_dos_departamentos_con_la_misma_cuenta_no_se_pisan():
    """El caso que motivó todo: Owners Fees del Club y de la propiedad."""
    partes = _correr([
        _fila("8005", "260", "Owners Fees — CM", {"dec": 2985}),
        _fila("8005", "0250", "Owners Fees", {"dec": 4000}),
    ])
    montos = sorted(p["amount"] for p in partes)
    assert montos == [2985.0, 4000.0], f"se fusionaron: {partes}"
    assert len(partes) == 2


def test_el_rotulo_usa_el_nombre_de_la_fila_y_no_la_tabla_fija():
    """Si una cuenta trae nombre propio, ese es el que se muestra. La tabla fija
    de nombres es el respaldo, no la autoridad."""
    partes = _correr([
        _fila("8005", "260", "Owners Fees — CM", {"dec": 2985}),
        _fila("8005", "0250", "Owners Fees", {"dec": 4000}),
    ])
    etiquetas = " | ".join(p["label"] for p in partes)
    assert "CM" in etiquetas, f"el rótulo perdió la marca del Club: {etiquetas}"


def test_con_un_solo_departamento_no_se_ensucia_el_rotulo():
    """El código del depto sólo aparece cuando hace falta distinguir. Con uno
    solo sería ruido en cada renglón."""
    partes = _correr([_fila("8015", "260", "Property Insurance — CM", {"dec": 239})])
    assert len(partes) == 1
    assert " · 260" not in partes[0]["label"], partes[0]["label"]
    assert "Property Insurance — CM" in partes[0]["label"]


def test_el_total_de_la_linea_no_cambia():
    """Abrir el desglose no puede mover la línea del P&L: sigue siendo la suma."""
    filas = [
        _fila("8005", "260", "Owners Fees — CM", {"dec": 2985}),
        _fila("8005", "0250", "Owners Fees", {"dec": 4000}),
        _fila("8015", "260", "Property Insurance — CM", {"dec": 239}),
    ]
    assert round(sum(p["amount"] for p in _correr(filas)), 2) == 7224.00


def test_una_cuenta_que_no_es_non_alloc_no_entra():
    """8030 (capital/depreciación) no es Non Allocated: va más abajo."""
    assert _correr([_fila("8030", "260", "Depreciación", {"dec": 999})]) == []


def test_el_pl_por_departamento_lleva_el_below_gop():
    """El P&L Full Detail recorre el GL agrupando por `dept_code`, así que estas
    cuentas viajan con el departamento. Es lo que pidió el owner; se fija acá
    para que nadie saque la tabla de ese recorrido."""
    from app.api import pl_full_detail_api

    fuente = inspect.getsource(pl_full_detail_api)
    assert "BelowGopAccountEntry" in fuente
    assert "cd(e.dept_code or \"\")" in fuente, (
        "el P&L por departamento dejó de agrupar el GL por departamento")
