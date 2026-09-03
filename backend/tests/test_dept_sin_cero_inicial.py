# -*- coding: utf-8 -*-
"""El upload trae los departamentos sin el cero de adelante.

Owner, 2026-09-03: *«el upload tiene mismos departamentos sin 0»*.

## Por qué esto es lo más caro que puede entrar por el importador

`_CODIGO_AL_INICIO` acepta **tres o cuatro** dígitos, y tiene que aceptarlos: el
Club (260), el Área Recreativa (270) y Misceláneos (280) son de tres de verdad.
Así que un «110 · Habitaciones» pasa el filtro y se guardaba como `110`.

Y `110` no está en el catálogo:

    pl_engine.group_for_dept("0110") -> ROOMS
    pl_engine.group_for_dept("110")  -> OTHER_OVERHEAD

⚠️ **No revienta, no se descarta, no avisa.** El gasto de Habitaciones aparece
como Overhead y **el P&L cuadra igual** — la plata sigue estando, sólo que en la
línea de al lado. Un reporte así no se ve roto: se ve raro, y sólo si alguien
conoce el negocio.
"""
from app.engine import pl_engine
from app.importers.gl_detail_importer import (
    _POR_PALABRA, _tres_digitos_reales, dept_code_from_name)


def test_al_de_cuatro_digitos_se_le_devuelve_el_cero():
    casos = {
        "110 - Habitaciones": "0110",
        "120 · A&B": "0120",
        "150 Tours": "0150",
        "161 Lavanderia": "0161",
        "200 Mantenimiento": "0200",
        "230 TI": "0230",
    }
    for entrada, esperado in casos.items():
        assert dept_code_from_name(entrada) == esperado, entrada


def test_los_TRES_que_de_verdad_son_de_tres_no_se_tocan():
    """⚠️ Rellenarlos sería el mismo error al revés: `0260` no existe."""
    for entrada, esperado in {"260 · Club Madresal": "260",
                              "270 Area Recreativa": "270",
                              "280 Miscelaneos": "280"}.items():
        assert dept_code_from_name(entrada) == esperado, entrada


def test_el_cero_ya_puesto_no_se_duplica():
    for entrada in ("0110 · Habitaciones", "0165 · Gift Shop", "0250 Property"):
        d = dept_code_from_name(entrada)
        assert d and len(d) == 4 and d.startswith("0"), (entrada, d)


def test_TODO_lo_que_resuelve_el_importador_lo_conoce_el_motor():
    """La prueba que de verdad importa: que nada caiga en `OTHER_OVERHEAD` por
    accidente.

    Recorre las palabras clave del propio módulo y cada código en su forma de
    tres dígitos, y exige que el motor lo ubique donde corresponde.
    """
    malos = []
    for _kw, code in _POR_PALABRA:
        if not code.startswith("0"):
            continue
        sin_cero = code.lstrip("0")
        resuelto = dept_code_from_name(f"{sin_cero} algo")
        if resuelto != code:
            malos.append(f"«{sin_cero}» -> {resuelto!r}, se esperaba {code!r}")
        # Y que el motor lo ubique en el MISMO lugar en las dos formas. Es lo
        # que se rompía: `0110`→ROOMS y `110`→OTHER_OVERHEAD.
        #
        # ⚠️ No se exige que ninguno sea OTHER_OVERHEAD: Claro Huerta (0205) y
        # Property (0250) SON overhead, y decir lo contrario haría fallar la
        # prueba por una clasificación correcta.
        if pl_engine.group_for_dept(resuelto) != pl_engine.group_for_dept(code):
            malos.append(f"«{sin_cero}» cae en otro grupo que «{code}»")
    assert not malos, malos


def test_la_lista_de_TRES_digitos_no_se_escribe_a_mano():
    """Se deriva de la tabla del módulo y de la del motor.

    ⚠️ Hacen falta las DOS, y el 280 explica por qué. Misceláneos no está en
    `_DEPT_TO_GROUP` porque es un departamento de PURO INGRESO: sus diez reglas
    de mapeo son las diez `Revenue`, y esa tabla dice dónde cae el GASTO. Un
    departamento sin gasto no aparece ahí.

    Mirando sólo al motor se lo rellenaría a `0280` —que no existe— y su
    ingreso se perdería. Y la tabla de palabras sólo cubre lo que tiene palabra
    clave.
    """
    assert _tres_digitos_reales() == frozenset({"260", "270", "280"})
    # Y que salga de las dos tablas y no de literales en la función.
    from app.importers import gl_detail_importer as m
    constantes = str(m._tres_digitos_reales.__code__.co_consts)
    for escrito_a_mano in ("260", "270", "280"):
        assert escrito_a_mano not in constantes, (
            f"«{escrito_a_mano}» quedó escrito a mano en `_tres_digitos_reales` "
            f"en vez de derivarse; el día que se agregue un departamento de "
            f"tres dígitos, nadie va a acordarse de venir acá")


def test_el_defecto_ORIGINAL_no_puede_volver():
    """Si alguien devuelve `m.group(1)` sin normalizar, esto lo agarra."""
    assert pl_engine.group_for_dept("110") == "OTHER_OVERHEAD", (
        "cambió el motor: revisá si esta prueba sigue midiendo lo que cree")
    assert dept_code_from_name("110 Habitaciones") == "0110", (
        "el importador volvió a guardar el código sin el cero; el gasto de "
        "Habitaciones va a aparecer como Overhead y el P&L va a cuadrar igual")
