# -*- coding: utf-8 -*-
"""El cálculo de A&B: pax → comida → ingreso.

Tres cosas se cuidan acá, y las tres se pueden romper sin que nada reviente:

**La captura.** Multiplicar pax por las tres comidas da el techo, no el ingreso:
medido contra el mayor de Oxygen el 2026-10-03, 6.643 pax-noche × $126 daría
$837.018 contra $228.608 reales. Un error en este factor devuelve un número
cinco veces más grande con cara de estar bien calculado.

**El servicio.** Owner, 2026-10-07: *«el 10% no se considera un ingreso, es un
tip que se colecta para los empleados pagado por el cliente, es tipo impuesto»*.
La primera versión lo sumaba al Food. Si vuelve a sumar, el A&B del presupuesto
queda 10% inflado y cuadra consigo mismo.

**El descuento.** Sólo una parte de la comida del huésped viaja en paquete de
agencia, y el externo no lleva descuento nunca. Aplicarlo a todo, o a nada,
mueve el ingreso sin que nadie lo haya escrito.
"""
from decimal import Decimal as D

import pytest

from app.models.fb_plan import (
    FbPlanConfig, FbPlanMes, calcular_mes, COMIDAS, DEFAULT_SERVICIO)


def cfg(**kw):
    base = dict(precio_desayuno=D("21"), precio_almuerzo=D("42"), precio_cena=D("63"),
                captura_desayuno=D("1"), captura_almuerzo=D("1"), captura_cena=D("1"),
                servicio_pct=D("0"), pct_comisionable=D("0"), bev_pct_food=D("0"))
    base.update(kw)
    return FbPlanConfig(**base)


# ── Nace en cero ─────────────────────────────────────────────────────────────

def test_sin_configuracion_todo_en_cero():
    """Sin fila, el A&B es cero. Nada se inventa solo."""
    r = calcular_mes(None, None, 564)
    assert r["food"] == D("0")
    assert r["beverage"] == D("0")
    assert r["total"] == D("0")


def test_sin_configuracion_el_externo_tampoco_se_cobra_solo():
    """Hay ticket de externo pero no hay carta: no hay nada que facturar."""
    mes = FbPlanMes(pax_externos=50, ticket_externos=D("35"))
    r = calcular_mes(None, mes, 500)
    assert r["food"] == D("0")
    assert r["pax_externos"] == 50       # el dato se sigue viendo
    assert r["pax_total"] == D("550")


def test_pax_en_cero_no_genera_ingreso():
    r = calcular_mes(cfg(), None, 0)
    assert r["food_hospedados"] == D("0")
    assert r["food"] == D("0")


# ── La captura ───────────────────────────────────────────────────────────────

def test_captura_total_es_el_techo():
    """Captura 1 en las tres: el máximo teórico, 21+42+63 por pax."""
    r = calcular_mes(cfg(), None, 100)
    assert r["food_hospedados"] == D("12600")


def test_la_captura_reduce_cada_comida_por_separado():
    """El % va POR comida, no uno solo: el desayuno se consume casi siempre y
    la cena bastante menos. Un promedio aplana cuál de las tres mueve el
    ingreso."""
    r = calcular_mes(cfg(captura_almuerzo=D("0.15"), captura_cena=D("0.30")), None, 100)
    assert r["desayuno"] == D("2100")        # 100 × 21 × 1,00
    assert r["almuerzo"] == D("630.00")      # 100 × 42 × 0,15
    assert r["cena"] == D("1890.00")         # 100 × 63 × 0,30
    assert r["food_hospedados"] == D("4620.00")


def test_captura_en_cero_no_genera_ingreso():
    r = calcular_mes(cfg(captura_desayuno=D("0"), captura_almuerzo=D("0"),
                         captura_cena=D("0")), None, 1000)
    assert r["food_hospedados"] == D("0")


@pytest.mark.parametrize("comida", COMIDAS)
def test_cada_comida_aparece_abierta_en_el_resultado(comida):
    """El resultado se devuelve pieza por pieza: la pantalla, el Excel y esta
    prueba miran lo mismo y nadie reconstruye el desglose por su cuenta."""
    r = calcular_mes(cfg(), None, 10)
    assert comida in r
    assert r[comida] > 0


# ── El servicio: se cobra, no es ingreso ─────────────────────────────────────

def test_el_servicio_no_suma_al_ingreso():
    """Owner, 2026-10-07: «no es un ingreso, es un tip… es tipo impuesto».

    Se calcula —hay que saber cuánto se recauda para el personal— pero el Food
    es el mismo con servicio o sin él.
    """
    con = calcular_mes(cfg(servicio_pct=D("0.10")), None, 100)
    sin = calcular_mes(cfg(servicio_pct=D("0")), None, 100)
    assert con["food"] == sin["food"] == D("12600")
    assert con["servicio"] == D("1260.00")
    assert sin["servicio"] == D("0")


def test_el_servicio_se_cobra_sobre_el_precio_de_carta():
    """El cliente ve la carta en la cuenta: el 10% va sobre el bruto, no sobre
    lo que queda después de la comisión de la agencia."""
    r = calcular_mes(cfg(servicio_pct=D("0.10"), pct_comisionable=D("1")),
                     None, 100, net_factor=D("0.80"))
    assert r["food_bruto"] == D("12600")
    assert r["servicio"] == D("1260.00")     # 10% del bruto, no del neto
    assert r["food"] == D("10080.00")        # el ingreso sí está neteado


def test_el_servicio_tambien_se_cobra_al_externo():
    mes = FbPlanMes(pax_externos=10, ticket_externos=D("100"))
    r = calcular_mes(cfg(captura_desayuno=D("0"), captura_almuerzo=D("0"),
                         captura_cena=D("0"), servicio_pct=D("0.10")), mes, 0)
    assert r["food"] == D("1000")
    assert r["servicio"] == D("100.0")


def test_el_default_del_servicio_es_diez_por_ciento():
    """Costa Rica. Es un default de la fila, no una constante del motor."""
    assert DEFAULT_SERVICIO == D("0.10")


# ── El descuento de canal ────────────────────────────────────────────────────

def test_sin_factor_no_hay_descuento():
    """`net_factor` ausente significa «nadie cobra comisión», no «cero ingreso».

    Un escenario sin canales cargados no puede dejar el Food en cero: eso sería
    un factor inventado moviendo plata sin que nadie lo escriba.
    """
    r = calcular_mes(cfg(pct_comisionable=D("1")), None, 100)
    assert r["descuento"] == D("0")
    assert r["food"] == D("12600")


def test_comisionable_en_cero_ignora_el_factor():
    """Nada se vende con agencia: el factor existe y no toca el ingreso."""
    r = calcular_mes(cfg(pct_comisionable=D("0")), None, 100, net_factor=D("0.80"))
    assert r["descuento"] == D("0")
    assert r["food"] == D("12600")


def test_el_descuento_cae_solo_sobre_la_parte_comisionable():
    """Owner, 2026-10-07: «es como un factor, decir de todas las ventas 50%
    lleva comisión y el otro no».

    Bruto 12.600, mitad con agencia, comisión 20% → se descuenta el 20% de la
    mitad: 1.260, no 2.520.
    """
    r = calcular_mes(cfg(pct_comisionable=D("0.50")), None, 100, net_factor=D("0.80"))
    assert r["food_bruto"] == D("12600")
    assert r["descuento"] == D("1260.000")
    assert r["food_hospedados"] == D("11340.000")


def test_el_externo_nunca_lleva_descuento():
    """Owner, 2026-10-07: «los externos no llevan descuento». Paga en la puerta."""
    mes = FbPlanMes(pax_externos=50, ticket_externos=D("35"))
    r = calcular_mes(cfg(captura_desayuno=D("0"), captura_almuerzo=D("0"),
                         captura_cena=D("0"), pct_comisionable=D("1")),
                     mes, 500, net_factor=D("0.50"))
    assert r["descuento"] == D("0")          # no hay comida de huésped que netear
    assert r["food"] == D("1750")            # el externo entra entero


def test_el_descuento_no_toca_al_externo_cuando_hay_de_los_dos():
    mes = FbPlanMes(pax_externos=10, ticket_externos=D("100"))
    r = calcular_mes(cfg(pct_comisionable=D("1")), mes, 100, net_factor=D("0.80"))
    assert r["food_hospedados"] == D("10080.00")   # 12.600 × 0,80
    assert r["food_externos"] == D("1000")         # intacto
    assert r["food"] == D("11080.00")


# ── El beverage ──────────────────────────────────────────────────────────────

def test_beverage_es_porcentaje_del_food_ya_neto():
    """El % se midió contra el ingreso facturado del mayor, que ya viene neto de
    comisión y sin servicio. Calcularlo sobre el bruto lo inflaría."""
    r = calcular_mes(cfg(servicio_pct=D("0.10"), pct_comisionable=D("1"),
                         bev_pct_food=D("0.5835")), None, 100, net_factor=D("0.80"))
    assert r["food"] == D("10080.00")
    assert r["beverage"] == D("5881.680000")
    assert r["total"] == r["food"] + r["beverage"]


def test_beverage_en_cero_no_resta_nada():
    r = calcular_mes(cfg(bev_pct_food=D("0")), None, 100)
    assert r["beverage"] == D("0")
    assert r["total"] == r["food"]


# ── Los externos ─────────────────────────────────────────────────────────────

def test_externos_van_por_ticket_promedio():
    """Quien no se hospeda no desayuna: entra a comer una vez. Por eso son dos
    campos —cuántos y cuánto gastan— y no tres capturas más."""
    mes = FbPlanMes(pax_externos=120, ticket_externos=D("35"))
    r = calcular_mes(cfg(captura_desayuno=D("0"), captura_almuerzo=D("0"),
                         captura_cena=D("0")), mes, 0)
    assert r["food_externos"] == D("4200")
    assert r["food"] == D("4200")


def test_externos_suman_al_pax_total_pero_no_a_las_comidas():
    mes = FbPlanMes(pax_externos=120, ticket_externos=D("35"))
    r = calcular_mes(cfg(), mes, 500)
    assert r["pax_hospedados"] == D("500")
    assert r["pax_externos"] == 120
    assert r["pax_total"] == D("620")
    assert r["desayuno"] == D("10500")       # 500 × 21, el externo no desayuna


# ── El cuadre contra el histórico ────────────────────────────────────────────

def test_caso_oxygen_cuadra_contra_el_historico():
    """El modelo completo, contra los doce meses reales de Oxygen.

    Período ago-25 a jul-26 (el del criterio contable vigente): **6.122
    pax-noche** y **$228.607,90** de Food facturado — que ya viene neto de
    comisión, porque la cuenta 7080 tiene $2.537 en todo 2026 y la comisión se
    netea del ingreso, no se gasta.

    Con la carta de Oxygen (20/45/60), desayuno al 100%, almuerzo y cena al 16%,
    la mitad comisionable y el factor de canal real de la propiedad (TA 55% al
    20% + Directo 45% al 10% → 0,845), más 50 externos al mes a $35:

        6.122 × $36,80 bruto = 225.289,60
        − 7,75% sobre la mitad comisionable = −17.459,94
        + externos 21.000,00
        = 228.829,66  contra  228.607,90 real  →  0,1% de diferencia
    """
    carta = cfg(precio_desayuno=D("20"), precio_almuerzo=D("45"), precio_cena=D("60"),
                captura_desayuno=D("1"), captura_almuerzo=D("0.16"),
                captura_cena=D("0.16"), pct_comisionable=D("0.50"),
                servicio_pct=D("0.10"))
    mes = FbPlanMes(pax_externos=50, ticket_externos=D("35"))
    r = calcular_mes(carta, mes, 6122, net_factor=D("0.845"))

    assert r["food_bruto"] == D("225289.60")
    assert r["descuento"].quantize(D("0.01")) == D("17459.94")
    assert r["food_externos"] == D("1750")
    # El año: once meses más de externos sobre el mismo cálculo de huésped.
    anual = r["food"] + D("1750") * 11
    assert abs(anual - D("228607.90")) < D("250")


def test_el_techo_sin_captura_es_cinco_veces_el_real():
    """La prueba que explica por qué existe la captura: sin ella el presupuesto
    de A&B de Oxygen sería $837.018 contra $228.608 de realidad."""
    techo = calcular_mes(
        cfg(precio_desayuno=D("21"), precio_almuerzo=D("42"), precio_cena=D("63")),
        None, 6643)["food_hospedados"]
    assert techo == D("837018")
    assert techo > D("228607.90") * 3
