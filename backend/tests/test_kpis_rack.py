# -*- coding: utf-8 -*-
"""Los KPIs a precio RACK, contra las celdas del libro del owner.

Fuente: `Presupuesto_Ojochal_2027_Modelo 1_3 bismark.xlsx`, pestaña `KPIs Rack`,
escenario «Proyección 2027». Cada aserción nombra la celda.

Owner, 2026-10-16: *«no veo en el app el cálculo de rooms revenue a tarifa rack,
sólo veo net»*. El neto es lo que entra al P&L; el rack es **contra lo que se
mide el descuento**. Sin el rack, «vendimos a $177,68» no se compara con nada y
la comisión se queda sin denominador.
"""
from decimal import Decimal

import pytest

from app.engine.rack_tarifa import kpis_rack

CENT = Decimal("0.01")

#: Los siete segmentos que facturan, más el de cortesía.
GENERA = {"AGENCIAS": True, "DIRECT_WEB": True, "CRC_DIRECT": True,
          "DIRECT_PHONE": True, "DIRECT_GROUPS": True, "LONG_TERM": True,
          "OTA": True, "CPL": False}
PROPIAS = {"LONG_TERM"}

#: Año completo. Rack de `KPIs Rack` filas 18-24, neto de la fila 33 repartido
#: igual que el rack (sólo se usan los totales, que son los que se comparan).
AÑO_RACK = {
    "AGENCIAS":      Decimal("92106.0704"),
    "DIRECT_WEB":    Decimal("260566.7155"),
    "CRC_DIRECT":    Decimal("22351.1437"),
    "DIRECT_PHONE":  Decimal("7309.0909"),
    "DIRECT_GROUPS": Decimal("0"),
    "LONG_TERM":     Decimal("24000"),
    "OTA":           Decimal("68214.0176"),
}
AÑO_NETO = {
    "AGENCIAS":      Decimal("69079.5528"),
    "DIRECT_WEB":    Decimal("234510.044"),
    "CRC_DIRECT":    Decimal("16763.3578"),
    "DIRECT_PHONE":  Decimal("6578.1818"),
    "DIRECT_GROUPS": Decimal("0"),
    "LONG_TERM":     Decimal("24000"),
    "OTA":           Decimal("51160.5132"),
}
AÑO_NOCHES = {
    "AGENCIAS": 400, "DIRECT_WEB": 1125, "CRC_DIRECT": 98,
    "DIRECT_PHONE": 30, "DIRECT_GROUPS": 0, "LONG_TERM": 315, "OTA": 295,
    "CPL": 0,
}
DISPONIBLES = 4015


@pytest.fixture
def año():
    segmentos = {c: {"tarifa": Decimal("0"), "ingreso": AÑO_NETO[c],
                     "ingreso_rack": AÑO_RACK[c]} for c in AÑO_RACK}
    segmentos["CPL"] = {"tarifa": Decimal("0"), "ingreso": Decimal("0"),
                        "ingreso_rack": Decimal("0")}
    return kpis_rack(segmentos, AÑO_NOCHES, GENERA, PROPIAS, DISPONIBLES)


def _cerca(a, b, tol="0.01"):
    assert abs(Decimal(str(a)) - Decimal(str(b))) <= Decimal(tol), f"{a} != {b}"


# ── El bloque que faltaba en la pantalla ────────────────────────────────────
def test_ingreso_rack_del_anio(año):
    """`KPIs Rack` N25 = 474.547,0381."""
    _cerca(año["ingreso_rack"], "474547.0381")


def test_adr_rack(año):
    """N28 = 209,6982. Es el rack sobre TODAS las noches que facturan."""
    _cerca(año["adr_rack"], "209.6982", "0.001")


def test_adr_rack_sin_tarifa_propia(año):
    """N29 = 231,287.

    Saca Long term, que no tiene RAC. Es el número que se compara contra el
    tarifario del año: mezclarlo con la tarifa propia hace parecer que el
    tarifario bajó cuando sólo se vendieron más noches largas.
    """
    _cerca(año["adr_rack_sin_propias"], "231.287", "0.001")


def test_los_dos_ADR_rack_NO_son_el_mismo_numero(año):
    """Si alguien los unifica «porque se parecen», se pierde la comparación
    contra el tarifario. En 2027 son $209,70 contra $231,29."""
    assert año["adr_rack"] != año["adr_rack_sin_propias"]
    assert año["adr_rack_sin_propias"] > año["adr_rack"]


def test_revpar_rack(año):
    """N30 = 118,1935."""
    _cerca(año["revpar_rack"], "118.1935", "0.001")


# ── Rack contra neto ────────────────────────────────────────────────────────
def test_ingreso_neto_del_anio(año):
    """N33 = 402.091,6496 — el que entra al P&L."""
    _cerca(año["ingreso_neto"], "402091.6496")


def test_adr_y_revpar_netos(año):
    """N34 = 177,6808 · N35 = 100,1474."""
    _cerca(año["adr_neto"], "177.6808", "0.001")
    _cerca(año["revpar_neto"], "100.1474", "0.001")


def test_comision_contra_rack(año):
    """N36 = 72.455,3886 · N37 = 15,27 %."""
    _cerca(año["comision_usd"], "72455.3886")
    _cerca(año["comision_pct"], "0.1527", "0.0001")


def test_porcentaje_del_rack_retenido(año):
    """N38 = 84,73 %. Es `1 − comisión`, y va aparte porque es el número que se
    mira para negociar con un canal."""
    _cerca(año["pct_rack_retenido"], "0.8473", "0.0001")
    _cerca(año["pct_rack_retenido"] + año["comision_pct"], "1", "0.0001")


# ── El mix ──────────────────────────────────────────────────────────────────
def test_mix_de_ingreso_rack(año):
    """N41-N47. Direct web es el 54,91 % del rack del año."""
    _cerca(año["mix_rack"]["DIRECT_WEB"], "0.5491", "0.0001")
    _cerca(año["mix_rack"]["AGENCIAS"], "0.1941", "0.0001")
    _cerca(año["mix_rack"]["OTA"], "0.1437", "0.0001")
    _cerca(año["mix_rack"]["LONG_TERM"], "0.0506", "0.0001")


def test_el_mix_suma_uno(año):
    _cerca(sum(año["mix_rack"].values()), "1", "0.0001")


def test_el_mix_no_incluye_a_los_que_no_facturan(año):
    """CPL no tiene ingreso rack: meterlo en el mix lo pondría en 0 % y daría a
    entender que se midió, cuando lo que pasa es que no aplica."""
    assert "CPL" not in año["mix_rack"]


# ── Las noches ──────────────────────────────────────────────────────────────
def test_noches_facturadas_y_de_tarifa_propia(año):
    """N8 = 2.263 · N9 = 315 (de las cuales, Long term)."""
    _cerca(año["noches_facturadas"], "2263")
    _cerca(año["noches_tarifa_propia"], "315")


def test_las_cortesias_van_aparte(año):
    """N10 = 0 en la Proyección 2027, pero la fila existe: si un mes trae
    cortesías tienen que verse, no desaparecer dentro de las facturadas."""
    assert "noches_cortesia" in año
    _cerca(año["noches_cortesia"], "0")


def test_una_cortesia_no_entra_en_el_ADR():
    """El detalle que hace que el cuadro cierre o no.

    Seis noches de uso casa ocupan villa pero no facturan. Si entraran en el
    denominador, el ADR bajaría sin que nadie hubiera cambiado una tarifa.
    """
    segs = {"OTA": {"tarifa": Decimal("100"), "ingreso": Decimal("1000"),
                    "ingreso_rack": Decimal("1000")},
            "CPL": {"tarifa": Decimal("0"), "ingreso": Decimal("0"),
                    "ingreso_rack": Decimal("0")}}
    k = kpis_rack(segs, {"OTA": 10, "CPL": 6}, GENERA, PROPIAS, 341)
    assert k["noches_facturadas"] == Decimal("10")
    assert k["noches_cortesia"] == Decimal("6")
    _cerca(k["adr_rack"], "100")      # 1000 / 10, NO 1000 / 16


def test_sin_noches_no_divide_por_cero():
    k = kpis_rack({}, {}, GENERA, PROPIAS, 341)
    assert k["adr_rack"] == Decimal("0")
    assert k["comision_pct"] == Decimal("0")
    assert k["pct_rack_retenido"] == Decimal("0")
