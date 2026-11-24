"""Checkbook OPEX en vivo (port de CWL, owner 2026-11-23).

En Oxygen el endpoint NO usa el Excel de subida de OPEX (que en CWL sí cambió):
trae sus ayudantes propios. Estas pruebas fijan lo que el libro necesita de ellos.
"""
from app.api.consolidado_planilla_api import (
    DETALLES_HASTA_820, LUGARES, _hoja_de, _lugares_por_defecto, _seg3_de,
    _seg3_de_la_cuenta,
)


def test_seg3_de_traduce_los_codigos_de_oxygen():
    # Oxygen guarda «001»…«010»: el 801…810 de Integrity. Vacío o raro, el 800.
    assert _seg3_de("001") == "801"
    assert _seg3_de("010") == "810"
    assert _seg3_de("") == "800"
    assert _seg3_de(None) == "800"
    assert _seg3_de("abc") == "800"


def test_seg3_de_respeta_un_8xx():
    assert _seg3_de("800") == "800"
    assert _seg3_de("815") == "815"


def test_detalles_de_la_cuenta_800_810_o_820():
    assert _seg3_de_la_cuenta("7065") == [str(n) for n in range(800, 811)]
    for cta in DETALLES_HASTA_820:
        assert _seg3_de_la_cuenta(cta) == [str(n) for n in range(800, 821)]


def test_hoja_de_deja_al_depto_con_hoja_propia():
    assert _hoja_de("0190", {"0190", "0110"}) == "0190"


def test_los_seis_lugares_tienen_defecto():
    d = _lugares_por_defecto(2027, "Working", None)
    assert set(d) == set(LUGARES)
    assert d["MES"] == ("BUDGET", 2027, "Working", 12)
