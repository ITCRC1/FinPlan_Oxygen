# -*- coding: utf-8 -*-
"""La auditoría responde al ámbito de arriba: mes, YTD o año completo.

Owner, 2026-09-08: *«todo debe moverse con la parte de arriba… y toda auditoría
debe responder a si es mes, YTD o full year; no debe haber variable de decisión
intermedia»*.

## Qué se rompía

El endpoint sólo sabía de un mes. La pantalla llegó a pasarle el ámbito, pero
lo usaba nada más para escribir un rótulo: el texto decía «acumulado» y los
números seguían siendo los del mes. Obedecer a medias es peor que no obedecer,
porque se ve igual de bien.

## La invariante que se vigila acá

**Las dos mitades del cuadre se acumulan sobre LOS MISMOS MESES.** El detalle
sumando sus columnas del GL, el motor agregando sus resultados. Si una sumara
1..7 y la otra sólo julio, la columna «Dif.» mostraría una diferencia que no es
un error contable sino de aritmética — y sería indistinguible de un descuadre
real, que es justo lo que este reporte existe para encontrar.
"""
import asyncio
import inspect

import pytest

from app.api import auditoria_api as api
from app.errores import ErrorApi


# ── Los tres ámbitos ─────────────────────────────────────────────────────────

def test_mes_es_solo_ese_mes():
    assert api._meses_del_horizonte(7, "month") == [7]


def test_ytd_es_de_enero_al_mes():
    assert api._meses_del_horizonte(7, "ytd") == [1, 2, 3, 4, 5, 6, 7]
    assert api._meses_del_horizonte(1, "ytd") == [1]
    assert api._meses_del_horizonte(12, "ytd") == list(range(1, 13))


def test_full_year_son_los_doce_sin_importar_el_mes():
    """⚠️ El año completo NO depende del mes elegido. Si dependiera, «full
    year» en marzo mostraría un trimestre y se leería como el año."""
    assert api._meses_del_horizonte(3, "full") == list(range(1, 13))
    assert api._meses_del_horizonte(12, "full") == list(range(1, 13))


def test_los_tres_ambitos_son_los_MISMOS_que_los_del_pl():
    """`month` · `ytd` · `full`, con esos nombres. El ámbito viaja desde la
    pantalla hasta el backend sin traducirse: en las traducciones es donde se
    pierde."""
    assert api.HORIZONTES == ("month", "ytd", "full")


# ── Lo que el endpoint rechaza ───────────────────────────────────────────────

def test_un_horizonte_inventado_se_rechaza_antes_de_tocar_la_base():
    """No hay default silencioso: un ámbito que no existe es un error, no un
    mes suelto disfrazado."""
    with pytest.raises(ErrorApi) as e:
        asyncio.run(api.auditoria_del_mes("cualquiera", 7, "trimestre"))
    assert e.value.status_code == 422


def test_el_mes_sigue_validandose():
    with pytest.raises(ErrorApi) as e:
        asyncio.run(api.auditoria_del_mes("cualquiera", 13, "month"))
    assert e.value.status_code == 422


# ── La invariante: las dos mitades suman los mismos meses ────────────────────

def _fuente():
    return inspect.getsource(api.auditoria_del_mes)


def test_las_dos_mitades_salen_de_la_MISMA_lista_de_meses():
    f = _fuente()
    assert "meses = _meses_del_horizonte(mes, horizonte)" in f
    # El detalle suma las columnas de esos meses…
    assert "cols = [MESES[m - 1] for m in meses]" in f
    assert "for c in cols" in f
    # …y el motor agrega los resultados de esos mismos meses.
    assert 'm["month"] in set(meses)' in f


def test_el_detalle_ya_no_lee_una_sola_columna():
    """⚠️ `getattr(e, col)` era la forma vieja: una columna, un mes. Si vuelve,
    el YTD mostraría el detalle de un mes contra el motor de siete."""
    f = _fuente()
    assert "col = MESES[mes - 1]" not in f
    assert "getattr(e, col," not in f


def test_el_motor_se_agrega_con_el_agregador_de_la_pantalla():
    """⚠️ Y NO sumando `amount_usd` mes a mes.

    La diferencia está en el impuesto de renta: `_apply_tax_correction` mira el
    EBT del AÑO para decidir si una ventana paga —un ejercicio que cierra en
    pérdida no paga renta en ningún YTD suyo, por más que ese YTD dé positivo—.
    Una suma cruda mostraría un impuesto que el P&L de arriba no muestra, y la
    auditoría acusaría de descuadre justo a la línea que está bien.
    """
    f = _fuente()
    assert "_aggregate_selected(" in f
    assert "lo_subido_manda=await _lo_subido_manda(session, escenario)" in f
    assert "ebt_anual=_ebt_anual(mensual)" in f
    assert "renta_digitada=await _renta_digitada(session, escenario)" in f


def test_las_lineas_del_agregador_se_leen_como_diccionario():
    """`_aggregate_selected` devuelve dicts, no `PLLineResult`. Leerlas con
    punto reventaría en tiempo de ejecución, y ningún test de fuente lo vería:
    por eso se comprueba la forma, no el texto."""
    from app.api.pl_api import _aggregate_selected
    vacio = _aggregate_selected([])
    assert isinstance(vacio["lines"], list)
    assert '["amount_usd"]' in _fuente()


# ── El rótulo ────────────────────────────────────────────────────────────────

def test_el_rotulo_dice_que_periodo_es():
    assert api._rotulo_periodo(7, "month") == "Julio"
    assert api._rotulo_periodo(7, "ytd") == "Acumulado a Julio"
    assert api._rotulo_periodo(7, "full") == "Año completo"


def test_la_respuesta_devuelve_el_ambito_y_los_meses():
    """El reporte tiene que poder decir qué período es cuando se abra en Excel
    dentro de un mes, sin la pantalla al lado."""
    f = _fuente()
    for clave in ('"horizonte": horizonte', '"meses": meses',
                  '"periodo": _rotulo_periodo(mes, horizonte)'):
        assert clave in f, clave
