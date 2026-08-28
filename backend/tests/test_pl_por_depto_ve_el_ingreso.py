# -*- coding: utf-8 -*-
"""EL P&L POR DEPARTAMENTO TIENE QUE VER EL INGRESO.

**El agujero, medido en Amarena el 2026-08-27.** El reporte tomaba el ingreso
sólo de `RevenueAccountEntry` —el ingreso abierto por cuenta 4xxx— y los **diez**
escenarios de la propiedad tienen cero filas ahí: los de checkbook presupuestan
el ingreso a nivel de LÍNEA (rate cards, capture rate del Spa, cuota del Club) y
los de drivers lo calculan. Resultado: la columna REVENUE salía toda en «—» y
cada departamento operativo mostraba su gasto como pérdida. Rooms aparecía con
−251.543,77 mientras el hotel tenía 547.079,20 de ingreso.

Y no se quedaba en la columna: `total_non_op` se deriva como
`total_gop − ebitda_before`, y el EBITDA sí sale del P&L oficial, que sí ve el
ingreso. Con el GOP sin ingresos, todo el bloque below-GOP del reporte salía
corrido — y sin dar error, porque la resta siempre da algo.

Es el mismo patrón que el costo de ventas: un segundo camino al ingreso que no
mira `revenue_source`. Por eso el arreglo delega en `load_revenue_results`, el
cargador compartido, en vez de calcular otra vez.
"""
from __future__ import annotations

import inspect

from app.engine import pl_engine
from app.engine.recalculate import revenue_line_dict
from app.engine.revenue_calculator import RevenueResult


def _fuente() -> str:
    from app.api.scenarios_api import pl_by_dept

    return inspect.getsource(pl_by_dept)


def test_el_reporte_usa_el_cargador_compartido():
    fuente = _fuente()
    assert "load_revenue_results" in fuente, (
        "el reporte volvió a leer el ingreso por su cuenta")
    assert "calculate_annual_revenue" not in fuente, (
        "volvió a calcular el ingreso por drivers sin mirar revenue_source")


def test_la_compuerta_es_la_TABLA_y_no_el_modo_del_escenario():
    """Hay DOS campos que dicen de dónde sale el ingreso —`source_mode` y
    `revenue_source`— y no siempre coinciden: los Working 2027-2035 de Amarena
    están en `imported`/`drivers` y tampoco tienen ingreso por cuenta. Preguntar
    por la tabla cubre los dos casos y no puede equivocarse.
    """
    fuente = _fuente()
    assert "if not rev_rows:" in fuente, (
        "la compuerta del respaldo dejó de ser «no hay filas por cuenta»")
    cuerpo = fuente[fuente.index("if not rev_rows:"):]
    for campo in ("source_mode", "revenue_source"):
        assert campo not in cuerpo, (
            f"el respaldo se colgó de `{campo}`: un escenario con los dos campos "
            f"en desacuerdo vuelve a quedarse sin ingreso")


def test_el_respaldo_no_puede_duplicar():
    """Corre SÓLO cuando no hay ingreso por cuenta, así que las dos fuentes
    nunca se suman. Si alguien saca esa guarda, un escenario con las dos cosas
    mostraría el ingreso dos veces — y el GOP saldría inflado sin avisar."""
    fuente = _fuente()
    i_suma = fuente.index('acc(group_for_dept(e.dept_code))["revenue"]')
    i_guarda = fuente.index("if not rev_rows:")
    assert i_suma < i_guarda, "el respaldo quedó antes de la suma por cuenta"


def test_toda_linea_de_ingreso_cae_en_un_grupo_con_nombre():
    """**La prueba que de verdad cuida el arreglo.** El respaldo asigna con
    `REVENUE_LINE_TO_GROUP.get(linea)` y descarta lo que no encuentra: una línea
    sin grupo desaparecería del reporte en silencio, que es justo el modo de
    falla que se está arreglando. Y sin nombre de grupo la fila saldría rotulada
    con el código crudo.
    """
    lineas = set(revenue_line_dict(RevenueResult(month=1, year=2026)))
    assert lineas, "revenue_line_dict dejó de devolver líneas"

    sin_grupo = sorted(l for l in lineas if l not in pl_engine.REVENUE_LINE_TO_GROUP)
    assert not sin_grupo, (
        f"estas líneas de ingreso no tienen grupo y se caerían del reporte: {sin_grupo}")

    sin_nombre = sorted({pl_engine.REVENUE_LINE_TO_GROUP[l] for l in lineas}
                        - set(pl_engine.GROUP_NAMES))
    assert not sin_nombre, (
        f"estos grupos saldrían rotulados con el código crudo: {sin_nombre}")


def test_el_ingreso_por_grupo_suma_lo_mismo_que_el_total():
    """Repartir por grupo no puede perder ni inventar plata: la suma de los
    grupos es el ingreso del período. Es el cuadre que el reporte necesita para
    que el GOP por depto sume el GOP total."""
    r = RevenueResult(month=6, year=2026)
    r.rooms = __import__("decimal").Decimal("374791.20")
    r.spa = __import__("decimal").Decimal("11448")
    r.activities = __import__("decimal").Decimal("10800")

    por_linea = revenue_line_dict(r)
    total = sum(float(v or 0) for v in por_linea.values())

    por_grupo: dict[str, float] = {}
    for linea, monto in por_linea.items():
        g = pl_engine.REVENUE_LINE_TO_GROUP.get(linea)
        assert g is not None, f"la línea {linea} se caería del reporte"
        por_grupo[g] = por_grupo.get(g, 0.0) + float(monto or 0)

    assert round(sum(por_grupo.values()), 2) == round(total, 2)
    assert round(total, 2) == 397039.20
