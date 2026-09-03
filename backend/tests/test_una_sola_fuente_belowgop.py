# -*- coding: utf-8 -*-
"""El gasto de propiedad se lee de UNA sola tabla.

Owner, 2026-09-03, cotejando su Excel contra la app: el gasto de propiedad daba
**$116.207,21 en el P&L y $20.585,21 en «Property x Cuenta»**. Mismo concepto,
mismo mes, dos números — y nada avisaba.

## Por qué pasaba

El below-GOP vive en DOS tablas y cada pantalla leía una:

    nonop_entries              8005 Owners Fees  →  68.337,08   (el P&L)
    belowgop_account_entries   8005 Owners Fees  →  18.915,01   (el cuadro)

Cuál número veías dependía de por qué pantalla entraras. El owner llegó a tener
**tres cifras** para la misma cuenta —52.000 en su Excel, y esas dos—, y tardó
en verlo porque cada pantalla sumaba consigo misma.

## La regla

`recalculate.nonop_line_seeds_for_month` siembra las líneas del P&L desde `NonOpEntry`.
**Esa es la fuente.** Cualquier cuadro que muestre gasto de propiedad de un
presupuesto tiene que leer la misma, o vuelve a haber dos verdades.
"""
import inspect

from app.api import gasto_por_clase_api
from app.engine import recalculate


def test_el_MOTOR_siembra_el_below_gop_desde_NonOpEntry():
    """La fuente de verdad, fijada. Si el motor cambiara de tabla, el cuadro
    tendría que cambiar con él — y esta prueba avisa."""
    fuente = inspect.getsource(recalculate.nonop_line_seeds_for_month)
    assert "select(NonOpEntry)" in fuente


def test_el_cuadro_de_propiedad_lee_la_MISMA_tabla_que_el_PL():
    """⚠️ Es la corrección: antes leía `BelowGopAccountEntry` y por eso mostraba
    $20.585,21 donde el P&L decía $116.207,21."""
    fuente = inspect.getsource(gasto_por_clase_api)
    assert "below = (await session.execute(select(NonOpEntry)" in fuente, (
        "el cuadro de propiedad volvió a leer la tabla vieja: mostraría un "
        "gasto distinto del que muestra el P&L")


def test_la_tabla_vieja_solo_se_usa_para_los_NOMBRES():
    """`NonOpEntry` trae el nombre de cuenta casi siempre vacío, y una lista de
    8005, 8015, 8020 no le dice nada a nadie. Se busca en la otra tabla, pero
    **sólo el rótulo** — ningún monto sale de ahí."""
    fuente = inspect.getsource(gasto_por_clase_api)
    assert "nombres_bg" in fuente
    # El único uso de la tabla vieja es armar ese diccionario de nombres.
    usos = [ln.strip() for ln in fuente.splitlines()
            if "BelowGopAccountEntry" in ln
            and "import" not in ln
            and not ln.strip().startswith("#")]
    assert len(usos) == 2, (
        f"la tabla vieja se usa en más lugares de los esperados: {usos}")
    assert any("select(BelowGopAccountEntry)" in u for u in usos), (
        "el único uso que queda tiene que ser la consulta de NOMBRES")


def test_las_DOS_tablas_tienen_proposito_distinto_y_eso_esta_bien():
    """⚠️ No son un duplicado: son dos cosas distintas, y confundirlas fue el bug.

    | tabla | qué es | ¿va al P&L? |
    |---|---|---|
    | `NonOpEntry` | el checkbook del propietario | **sí** |
    | `BelowGopAccountEntry` | ajustes de reconciliación sobre el GL | **no, a propósito** |

    Su único escritor es `POST /scenarios/{id}/belowgop-adjustment/`, que sirve
    para «parkear diferencias de reconciliación sin re-importar» y dice en su
    propio docstring que NO toca el P&L.

    Por eso `consulta_api` y `revenue_api` la leen sin traducir —muestran los
    ajustes, que es su trabajo— y `pl_full_detail` la lista y la revierte con
    renglones negativos. Todo eso es correcto y **no hay que unificarlo**.

    Lo que estaba mal era un solo cuadro: `/gasto-por-clase/` mezclaba las dos.
    """
    import inspect

    from app.api import scenarios_api

    fuente = inspect.getsource(scenarios_api.belowgop_adjustment)
    # El docstring parte la frase en dos lineas; se busca lo que no se corta.
    assert "snapshot del P&L" in fuente and "NO toca" in fuente, (
        "si el ajuste empieza a tocar el P&L, hay que revisar TODO esto: la "
        "separación entre las dos tablas dejaría de ser cierta")
