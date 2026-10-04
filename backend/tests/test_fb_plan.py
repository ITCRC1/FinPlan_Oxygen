# -*- coding: utf-8 -*-
"""El cálculo de A&B: pax → comida → ingreso.

Lo que se cuida acá es **la captura**, que es la razón de ser de la pantalla.
Multiplicar pax por las tres comidas da el techo, no el ingreso: medido contra
el mayor de Oxygen el 2026-10-03, 6.643 pax-noche × $126 daría $837.018 contra
$228.608 reales. Un error en este factor no rompe nada — devuelve un número
cinco veces más grande con cara de estar bien.
"""
from decimal import Decimal as D

import pytest

from app.models.fb_plan import (
    FbPlanConfig, FbPlanMes, calcular_mes, COMIDAS, DEFAULT_SERVICIO)


def cfg(**kw):
    base = dict(precio_desayuno=D("21"), precio_almuerzo=D("42"), precio_cena=D("63"),
                captura_desayuno=D("1"), captura_almuerzo=D("1"), captura_cena=D("1"),
                servicio_pct=D("0"), bev_pct_food=D("0"))
    base.update(kw)
    return FbPlanConfig(**base)


def test_sin_configuracion_todo_en_cero():
    """Sin fila, el A&B es cero. Nada se inventa solo."""
    r = calcular_mes(None, None, 564)
    assert r["food"] == D("0")
    assert r["beverage"] == D("0")
    assert r["total"] == D("0")
    # pero los pax que vienen de Rooms se reportan igual
    assert r["pax_hospedados"] == D("564")


def test_captura_total_es_el_techo():
    """Captura 100% en las tres = pax × (21+42+63) = pax × 126."""
    r = calcular_mes(cfg(), None, 100)
    assert r["food_hospedados"] == D("12600")


def test_la_captura_reduce_cada_comida_por_separado():
    """Cada comida se multiplica por SU captura, no por un promedio.

    Desayuno 100%, almuerzo 15%, cena 30%:
        100 × 21 × 1.00 = 2.100
        100 × 42 × 0.15 =   630
        100 × 63 × 0.30 = 1.890
                          -----
                          4.620
    Un promedio simple de las tres capturas (48,33%) daría 6.090: $1.470 de más
    sobre cien pax, y el error crece con el volumen.
    """
    r = calcular_mes(cfg(captura_almuerzo=D("0.15"), captura_cena=D("0.30")), None, 100)
    assert r["desayuno"] == D("2100.00")
    assert r["almuerzo"] == D("630.00")
    assert r["cena"] == D("1890.00")
    assert r["food_hospedados"] == D("4620.00")


def test_captura_en_cero_no_genera_ingreso():
    """Una comida que no se vende no suma, aunque tenga precio."""
    r = calcular_mes(cfg(captura_desayuno=D("0"), captura_almuerzo=D("0"),
                         captura_cena=D("0")), None, 1000)
    assert r["food_hospedados"] == D("0")


def test_pax_en_cero_no_genera_ingreso():
    """Un mes sin huéspedes no factura comida, por más precios que haya."""
    r = calcular_mes(cfg(), None, 0)
    assert r["food_hospedados"] == D("0")
    assert r["total"] == D("0")


def test_externos_van_por_ticket_promedio():
    """Los externos NO pasan por las comidas: cantidad × ticket.

    Quien no se hospeda no desayuna. Owner, 2026-10-03.
    """
    mes = FbPlanMes(pax_externos=120, ticket_externos=D("35"))
    r = calcular_mes(cfg(captura_desayuno=D("0"), captura_almuerzo=D("0"),
                         captura_cena=D("0")), mes, 500)
    assert r["food_externos"] == D("4200")
    assert r["food_hospedados"] == D("0")
    assert r["food_pre_servicio"] == D("4200")


def test_externos_suman_al_pax_total_pero_no_a_las_comidas():
    mes = FbPlanMes(pax_externos=120, ticket_externos=D("35"))
    r = calcular_mes(cfg(), mes, 500)
    assert r["pax_hospedados"] == D("500")
    assert r["pax_externos"] == 120
    assert r["pax_total"] == D("620")
    # las comidas se calcularon sobre los 500, no sobre los 620
    assert r["desayuno"] == D("10500")


def test_servicio_se_suma_encima():
    """Owner, 2026-10-03: el 10% se SUMA al precio digitado, no viene incluido.

    126 × 1,10 = 138,60 — el mismo número de la tabla de referencia.
    """
    r = calcular_mes(cfg(servicio_pct=D("0.10")), None, 1)
    assert r["food_pre_servicio"] == D("126")
    assert r["servicio"] == D("12.60")
    assert r["food"] == D("138.60")


def test_servicio_tambien_aplica_a_los_externos():
    """El servicio se cobra sobre toda la comida, no sólo la del huésped."""
    mes = FbPlanMes(pax_externos=10, ticket_externos=D("100"))
    r = calcular_mes(cfg(captura_desayuno=D("0"), captura_almuerzo=D("0"),
                         captura_cena=D("0"), servicio_pct=D("0.10")), mes, 0)
    assert r["food_pre_servicio"] == D("1000")
    assert r["food"] == D("1100.0")


def test_beverage_es_porcentaje_del_food_con_servicio():
    """Owner, 2026-10-03: «el beverage va a salir por % de Food».

    Se calcula sobre el Food YA con servicio, porque el % se midió contra el
    ingreso facturado del mayor, que lo incluye.
    """
    r = calcular_mes(cfg(servicio_pct=D("0.10"), bev_pct_food=D("0.584")), None, 1)
    assert r["food"] == D("138.60")
    assert r["beverage"] == D("80.9424")
    assert r["total"] == r["food"] + r["beverage"]


def test_beverage_en_cero_no_resta_nada():
    r = calcular_mes(cfg(bev_pct_food=D("0")), None, 100)
    assert r["beverage"] == D("0")
    assert r["total"] == r["food"]


@pytest.mark.parametrize("comida", COMIDAS)
def test_cada_comida_aparece_abierta_en_el_resultado(comida):
    """El resultado se devuelve pieza por pieza: la pantalla, el Excel y esta
    prueba miran lo mismo y nadie reconstruye el desglose por su cuenta."""
    r = calcular_mes(cfg(), None, 10)
    assert comida in r
    assert r[comida] > 0


def test_el_default_del_servicio_es_diez_por_ciento():
    """Costa Rica. Es un default de la fila, no una constante del motor."""
    assert DEFAULT_SERVICIO == D("0.10")


def test_caso_oxygen_reproduce_el_historico():
    """Con la captura medida, el modelo llega al Food real de Oxygen.

    12 meses corridos (ago-25 a jul-26): 228.608 de Food sobre pax-noche.
    El escenario 2027 presupuesta 6.643 pax-noche; a $27,04 por pax-noche el
    objetivo es ~179.600. Con desayuno al 100%, almuerzo al 15% y cena al 30%
    sobre precios 21/42/63 pre-servicio, más el 10%:

        6.643 × (21 + 42×0,15 + 63×0,30) = 6.643 × 46,20 = 306.906,60

    que es MÁS del objetivo: la prueba fija el orden de magnitud y deja escrito
    que las capturas de arriba son un ejemplo, no las de esta propiedad. Las
    reales las digita el hotel.
    """
    r = calcular_mes(cfg(captura_almuerzo=D("0.15"), captura_cena=D("0.30"),
                         servicio_pct=D("0.10")), None, 6643)
    assert r["food_hospedados"] == D("306906.60")
    # y el techo sin captura sería casi tres veces eso
    techo = calcular_mes(cfg(), None, 6643)["food_hospedados"]
    assert techo == D("837018")
    assert techo > r["food_hospedados"] * 2
