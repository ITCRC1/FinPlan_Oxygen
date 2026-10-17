# -*- coding: utf-8 -*-
"""Un camino de LECTURA no deja filas sucias en la sesión.

## Lo que se midió

Auditoría del 2026-10-16, contando `session.dirty` después de cada lectura:

    _ver (pantalla Rack Rooms)         sucias=  0
    get_monthly_revenue (consolidado)  sucias= 96   ←
    load_revenue_results (motor)       sucias= 96   ←
    get_revenue_by_room_type           sucias=  0

`aplicar_canales_rooms` derivaba la tarifa y la escribía **sobre la fila de la
base** para después pasársela a `calcular_mes`. Eso corre dentro de
`load_revenue_results`, que es el camino de lectura de `get_monthly_revenue`
— la puerta que consume Hotel Consolidation.

## Por qué no se veía

Escribía exactamente los mismos valores que ya estaban guardados, así que
ningún número cambiaba. El riesgo es el otro: basta que la tarifa guardada y la
derivada difieran —un RAC editado, una comisión nueva, una copia de escenario—
para que **un GET escriba en la base**, sin que nadie lo haya pedido y sin que
quede rastro de quién.

La regla ahora es explícita: se calcula sobre copias, y sólo el recálculo pasa
`persistir=True`.
"""
import inspect

from app.engine import recalculate

FUENTE = inspect.getsource(recalculate.aplicar_canales_rooms)


def test_por_omision_no_persiste():
    """El default manda: quien quiera escribir tiene que pedirlo."""
    firma = inspect.signature(recalculate.aplicar_canales_rooms)
    assert firma.parameters["persistir"].default is False
    firma2 = inspect.signature(recalculate.load_revenue_results)
    assert firma2.parameters["persistir"].default is False


def test_sin_persistir_calcula_sobre_copias():
    assert "_FilaDerivada(f, s[\"tarifa\"], s[\"ingreso\"])" in FUENTE
    assert "if persistir:" in FUENTE


def test_la_copia_lleva_lo_que_calcular_mes_necesita():
    """Si le falta un atributo, `calcular_mes` revienta con AttributeError en
    producción y no en las pruebas."""
    campos = set(recalculate._FilaDerivada.__slots__)
    assert {"segmento_code", "month", "noches", "tarifa", "ingreso"} <= campos


def test_solo_el_recalculo_escribe():
    """Un `persistir=True` en cualquier otro lado vuelve a poner un GET que
    escribe."""
    fuente = inspect.getsource(recalculate)
    # Sólo el CÓDIGO: los comentarios lo nombran para explicar la regla, y
    # contarlos haría que documentarla mejor rompa la prueba.
    usos = [ln.strip() for ln in fuente.splitlines()
            if "persistir=True" in ln and not ln.strip().startswith("#")]
    assert len(usos) == 1, f"persistir=True aparece {len(usos)} veces: {usos}"
    recalc = inspect.getsource(recalculate.recalculate_scenario)
    assert "persistir=True" in recalc


def test_un_segmento_sin_derivado_no_se_pierde():
    """Una fila cuyo segmento no vino en el derivado tiene que seguir contando:
    descartarla bajaría las noches ocupadas sin avisar."""
    assert "if s is None:" in FUENTE
    assert "copias.append(f)" in FUENTE
