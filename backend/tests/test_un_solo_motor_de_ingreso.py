# -*- coding: utf-8 -*-
"""Un solo motor de ingreso. El que abra un segundo, falla acá.

Owner, 2026-10-15, mirando Hotel Consolidation: *«me preocupa que siempre haya
datos que no viajen… o viajen mal»*. Tenía razón, y esta era la puerta.

## Lo que pasaba

`get_monthly_revenue` calculaba el ingreso con `calculate_annual_revenue`, que
repite `calculate_revenue` mes a mes y **no aplica ninguno de los drivers** que
viven en `load_revenue_results`: el modelo de Rooms por canal, el plan de A&B y
el capture del Spa.

Medido ese día en el Budget 2027 de Oxygen, API contra motor del P&L:

    rooms       1.074.207,63  vs  1.731.330,55
    food                0,00  vs    254.019,07
    beverage            0,00  vs    148.220,13
    misc_other          0,00  vs     47.875,98
    ────────────────────────────────────────────
                                  +1.107.238,10  de ingreso que no viajaba

Esa función alimenta las pantallas de Revenue **y** la puerta de solo lectura
que consume Hotel Consolidation. La app de los dueños mostraba el Budget 2027
de Oxygen en $1,07M cuando eran $1,73M — y el botón «Actualizar desde FinPlan»
volvía a traer el número viejo. Nada fallaba: el total cuadraba consigo mismo.

## La regla

El repo ya la tenía escrita para el P&L por departamento y para el costo de
ventas (*«volvió a calcular el ingreso por drivers sin mirar revenue_source»*).
Acá se extiende a las dos puertas que faltaban, que resultaron ser las que más
lejos mandan el dato.
"""
import inspect

import pytest

#: Las funciones que devuelven ingreso y tienen que usar el cargador compartido.
#: El nombre del modulo y de la funcion, para que el mensaje diga cual se rompio.
PUERTAS = [
    ("app.api.revenue_api", "get_monthly_revenue"),
    ("app.api.scenarios_api", "pl_by_dept"),
]


def _fuente(modulo: str, funcion: str) -> str:
    import importlib
    return inspect.getsource(getattr(importlib.import_module(modulo), funcion))


def _codigo(modulo: str, funcion: str) -> str:
    """La fuente SIN la prosa.

    ⚠️ La docstring de `get_monthly_revenue` explica el defecto y nombra
    `calculate_annual_revenue` para contarlo. Mirar la fuente cruda haría fallar
    la guarda por culpa de su propia explicación — y el arreglo obvio, borrar la
    explicación, es justo lo que no hay que hacer.
    """
    import re

    src = _fuente(modulo, funcion)
    for comilla in ('"""', "'''"):
        src = re.sub(comilla + r"[\s\S]*?" + comilla, "", src)
    return re.sub(r"#[^\n]*", "", src)


@pytest.mark.parametrize("modulo,funcion", PUERTAS)
def test_la_puerta_usa_el_cargador_compartido(modulo, funcion):
    assert "load_revenue_results" in _fuente(modulo, funcion), (
        f"{modulo}.{funcion} dejó de usar el cargador compartido")


@pytest.mark.parametrize("modulo,funcion", PUERTAS)
def test_la_puerta_no_abre_su_propio_motor(modulo, funcion):
    """⚠️ `calculate_annual_revenue` NO aplica los drivers. Usarlo devuelve el
    ingreso de las tarifas aunque el escenario esté en otro modelo."""
    assert "calculate_annual_revenue" not in _codigo(modulo, funcion), (
        f"{modulo}.{funcion} volvió a calcular el ingreso por su cuenta: "
        f"no va a ver rooms_source, ni el plan de A&B, ni el capture del Spa")


def test_el_serializador_deriva_las_lineas_y_no_las_escribe():
    """Tenía once líneas escritas a mano y el sistema ya tenía veintiuna.

    Faltaban el Club con sus tres fuentes y las siete que entraron el
    2026-10-08. Y no se notaba: `total_revenue` se calcula aparte y SÍ las
    sumaba, así que el cuadro cerraba contra un total que no era la suma de sus
    filas.
    """
    fuente = _fuente("app.api.revenue_api", "_revenue_result_to_dict")
    assert "revenue_line_dict" in fuente, (
        "el serializador volvió a tener su lista de líneas escrita a mano")


def test_el_serializador_devuelve_TODAS_las_lineas():
    """La prueba que mira el resultado, no el código."""
    from app.api.revenue_api import _revenue_result_to_dict
    from app.engine.revenue_calculator import RevenueResult
    from app.models.revenue_entry import REVENUE_LINES

    d = _revenue_result_to_dict(RevenueResult(month=1, year=2027))
    faltan = sorted(ln.lower() for ln in REVENUE_LINES if ln.lower() not in d)
    assert not faltan, f"estas líneas no llegan a la respuesta: {', '.join(faltan)}"


def test_la_puerta_del_consolidado_no_calcula_por_su_cuenta():
    """Hotel Consolidation lee por acá. Si esta puerta abre su propio motor, el
    número viaja mal a la app de los dueños — y allá nadie puede notarlo,
    porque no tiene con qué compararlo."""
    import app.api.consolidado_rooms_api as c

    import re
    fuente = re.sub(r'"""[\s\S]*?"""', "", inspect.getsource(c))
    assert "calculate_annual_revenue" not in fuente, (
        "el consolidado calcula el ingreso por su cuenta")
    assert "get_monthly_revenue" in fuente, (
        "el consolidado dejó de leer por la puerta compartida")
