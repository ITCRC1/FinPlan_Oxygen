# -*- coding: utf-8 -*-
"""`rooms_source` manda, esté el escenario en `checkbook` o en `drivers`.

## El defecto que esto persigue

`load_revenue_results` tiene dos ramas según `revenue_source`. La de `checkbook`
hacía `return` directo y **se saltaba `aplicar_canales_rooms`**.

Eso no daba error. Daba un **interruptor muerto**: el usuario conectaba el
modelo por canal desde la pantalla, la pantalla decía «conectado», y el P&L
seguía mostrando la línea ROOMS del checkbook. El total cuadraba consigo mismo,
así que podía quedarse así indefinidamente — y lo que viaja a Hotel
Consolidation es justo ese total.

Se descubrió el 2026-10-16 al ir a conectar `BUDGET Working 2027`: estaba en
modo `checkbook`, con el tarifario RAC cargado y verificado contra el libro, y
conectar no habría movido un centavo.

## Por qué la prueba es estructural

Lo que hay que blindar no es «este escenario da tal número» sino **«las dos
ramas pasan por la misma puerta»**. Una prueba de integración sobre una rama
pasa igual el día que alguien agregue una tercera.
"""
import inspect
import re

from app.engine import recalculate


FUENTE = inspect.getsource(recalculate.load_revenue_results)


def test_las_dos_ramas_aplican_el_modelo_por_canal():
    """Ni `checkbook` ni `drivers` pueden devolver sin pasar por el modelo."""
    retornos = [ln.strip() for ln in FUENTE.splitlines()
                if ln.strip().startswith("return ")]
    assert retornos, "no se encontró ningún return: ¿cambió la forma de la función?"
    # Todo `return` tiene que venir después de una llamada al modelo. Se mide
    # por posición en el texto: un `return` antes de la primera llamada es
    # exactamente el agujero que esto vigila.
    for m in re.finditer(r"^\s*return\s", FUENTE, re.M):
        antes = FUENTE[:m.start()]
        assert "aplicar_canales_rooms(" in antes, (
            "hay un `return` en load_revenue_results que no pasó por "
            "`aplicar_canales_rooms`: ese camino deja el interruptor "
            "`rooms_source` muerto — la pantalla dice «conectado» y el P&L "
            "muestra el modelo viejo, sin error y con el total cuadrando solo")


def test_la_rama_de_checkbook_lo_llama_explicitamente():
    """Que esté la llamada, no sólo el nombre en un comentario."""
    # Se corta en el `return` REAL y no en la palabra: el comentario de la
    # rama cuenta la historia y la nombra, que es justo lo que no alcanza.
    rama = FUENTE[FUENTE.index('== "checkbook"'):]
    fin = next(i for i, ln in enumerate(rama.splitlines())
               if ln.strip().startswith("return "))
    rama = chr(10).join(rama.splitlines()[:fin])
    assert "await aplicar_canales_rooms(" in rama


def test_la_condicion_del_modelo_sigue_siendo_solo_rooms_source():
    """El modelo NO puede condicionarse a la propiedad, al año ni al modo.

    Si alguien agrega `and revenue_source == ...`, vuelve el interruptor muerto
    por la puerta de al lado.
    """
    fuente = inspect.getsource(recalculate.aplicar_canales_rooms)
    guarda = fuente[fuente.index('rooms_source'):fuente.index("return False") + 12]
    assert '!= "canales"' in guarda
    for prohibido in ("hotel_id", "scenario.year", "revenue_source"):
        assert prohibido not in guarda, (
            f"la guarda del modelo por canal mira `{prohibido}`: la condición "
            f"tiene que ser `rooms_source` y nada más")


def test_sin_tarifario_no_escribe_nada():
    """Un escenario conectado pero sin villas/temporadas no se pone en cero.

    El RAC daría cero y el ingreso con él — y el total seguiría cuadrando.
    """
    fuente = inspect.getsource(recalculate.aplicar_canales_rooms)
    assert "hay_tarifario = bool(villas and temps)" in fuente
    assert "if not filas:" in fuente and "return False" in fuente
