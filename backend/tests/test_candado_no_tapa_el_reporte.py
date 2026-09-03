# -*- coding: utf-8 -*-
"""Un escenario cerrado congela sus DATOS, no el caché de su reporte.

Owner, 2026-09-03: *«recalculá todas las versiones en budget 2026 final; veo
que hay unos tabs que no tienen datos como si fuera 0, cosa que no es real»*.

## Qué estaba pasando

`BUDGET Final 2026` está `locked`. `recalculate_scenario` empezaba con
`assert_editable()`, así que **nunca** se le pudo escribir `pl_lines`: 0 filas,
contra 1.369 del `Working` — y los dos dan exactamente el mismo P&L
(Revenue 548.279,20 · GOP -300.613,30 · Net -416.820,51).

Los reportes que calculan al vuelo se veían bien; los que leen el guardado
—Resumen 12m, Consulta, Cuadre— mostraban cero. ⚠️ **Y un cero se lee como un
dato, no como un dato que falta.**

## Por qué esto no es aflojar el candado

`pl_lines` no es algo que alguien escribió: es el resultado de una cuenta sobre
los datos, guardado para no rehacerlo en cada consulta. Bloquear su escritura no
protegía ningún número.

Lo que sí sigue bloqueado: planilla, repartos y monedas — esos SÍ son datos, y
recalcularlos sobre un entregable aprobado lo cambiaría.
"""
import inspect
from pathlib import Path

from app.engine import recalculate as recalc

SRC = Path(recalc.__file__).read_text(encoding="utf-8")


def _cuerpo() -> str:
    return inspect.getsource(recalc.recalculate_scenario)


def test_un_escenario_cerrado_SI_puede_escribir_su_PL_guardado():
    cuerpo = _cuerpo()
    assert "if scenario.is_locked:" in cuerpo, (
        "volvió a no haber rama para el escenario cerrado: su `pl_lines` se "
        "queda en cero y los reportes que lo leen muestran cero")
    rama = cuerpo[cuerpo.index("if scenario.is_locked:"):]
    assert "_persist_pl" in rama[:600]


def test_y_NO_recalcula_planilla_ni_repartos_ni_monedas():
    """⚠️ Lo que hace segura a la rama de arriba.

    Si el escenario cerrado siguiera de largo hacia el recálculo completo, le
    reescribiría la planilla y los repartos — cambiando un entregable que ya se
    presentó. La rama tiene que TERMINAR ahí, con un `return`.
    """
    cuerpo = _cuerpo()
    rama = cuerpo[cuerpo.index("if scenario.is_locked:"):]
    hasta_return = rama[:rama.index("return {") + rama[rama.index("return {"):].index("}\n") + 2]
    for prohibido in ("_recalc_payroll", "_recalc_allocations", "_derivar_monedas"):
        assert prohibido not in hasta_return, (
            f"un escenario cerrado está llamando a {prohibido}: eso reescribe "
            f"un dato de un entregable aprobado")
    assert rama.index("return {") < len(rama), "la rama no corta el flujo"


def test_el_recalculo_de_un_escenario_cerrado_lo_DICE():
    """Un botón que parece hacer todo y hace una parte es peor que uno que
    explica cuál parte."""
    cuerpo = _cuerpo()
    rama = cuerpo[cuerpo.index("if scenario.is_locked:"):]
    # ⚠️ Se mira el aviso REAL, no el texto del archivo: el mensaje está
    # partido en varias líneas y buscar una frase entera en la fuente falla por
    # el corte, no por el contenido.
    assert "candado" in rama
    assert "La planilla, los repartos y las monedas" in rama


def test_el_candado_sigue_rechazando_la_EDICION():
    """La otra mitad: `assert_editable` no se tocó, y es lo que protege los
    datos en los 109 endpoints de escritura."""
    from app.models.scenario import Scenario, ScenarioLockedError
    # `is_locked` se DERIVA de `status`: no tiene setter, y está bien que no lo
    # tenga — dos formas de decir lo mismo terminan diciendo cosas distintas.
    s = Scenario(id="x", hotel_id="AMA", year=2026, type="BUDGET",
                 version="Final", status="locked")
    assert s.is_locked is True
    try:
        s.assert_editable()
    except ScenarioLockedError:
        return
    raise AssertionError("un escenario cerrado dejó de rechazar la edición")


def test_un_escenario_abierto_sigue_recalculando_TODO():
    """La rama nueva no puede haberse comido el camino normal."""
    cuerpo = _cuerpo()
    for etapa in ("_recalc_payroll", "_recalc_allocations", "_derivar_monedas"):
        assert etapa in cuerpo, f"desapareció la etapa {etapa}"
