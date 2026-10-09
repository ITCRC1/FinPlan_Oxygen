# -*- coding: utf-8 -*-
"""«Miscellaneous Revenue» no puede esconder un departamento con nombre propio.

Owner, 2026-10-09, señalando la línea en el Budget Package: *«puedes darle
visibilidad a lo que haya en esta línea… debe ser separado»*.

## Lo que escondía

El renglón sumaba CUATRO departamentos —misceláneos, sustainability, transporte
e Innoceana— bajo un solo rótulo. En Oxygen daba **$148.357**, de los cuales
**$100.481 eran Transporte**: la cuarta línea de ingreso de la propiedad,
invisible dentro de un renglón que dice «misceláneos».

Y no fallaba nada. El total cuadraba, el reporte cerraba, y el departamento
simplemente no aparecía en ningún lado del P&L — que es la forma cara de estar
mal en este sistema.

## Lo que se cuida

Que un renglón rotulado «misceláneos» lleve **un solo** código de ingreso. El
día que alguien vuelva a meterle un departamento adentro para «simplificar el
cuadro», esto falla y dice cuál.
"""
import pytest

from app.api.pl_detail_api import CONSOLIDADO

#: Lo que NO puede vivir dentro de un renglón de misceláneos: cada uno es un
#: departamento con su propia operación, su propio costo y su propia utilidad.
CON_NOMBRE_PROPIO = {
    "REV_TRANSPORTATION", "REV_INNOCEANA", "REV_SUSTAINABILITY",
    "OPEX_TRANSPORTATION", "COS_TRANSPORTATION",
    "OPEX_INNOCEANA", "COS_INNOCEANA",
    "PROFIT_TRANSPORTATION", "PROFIT_INNOCEANA", "PROFIT_SUSTAINABILITY",
}


def _renglones_de_miscelaneos():
    return [(rot, cods) for tipo, rot, cods in CONSOLIDADO
            if tipo == "det" and "iscell" in rot]


def test_hay_renglones_de_miscelaneos():
    """Si el rótulo cambió, esta prueba deja de mirar nada y hay que ajustarla."""
    assert _renglones_de_miscelaneos(), "ya no hay renglón de «Miscellaneous»"


def test_miscelaneos_no_lleva_departamentos_adentro():
    """La que falló: $100.481 de Transporte escondidos en «misceláneos»."""
    escondidos = []
    for rot, cods in _renglones_de_miscelaneos():
        escondidos += [c for c in (cods or []) if c in CON_NOMBRE_PROPIO]
    assert not escondidos, (
        "estos departamentos quedaron escondidos dentro de «Miscellaneous»: "
        + ", ".join(sorted(set(escondidos))))


@pytest.mark.parametrize("codigo,rotulo", [
    ("REV_TRANSPORTATION", "Transportation"),
    ("REV_INNOCEANA", "Innoceana"),
    ("REV_SUSTAINABILITY", "Sustainability Fee"),
])
def test_cada_uno_tiene_su_propio_renglon(codigo, rotulo):
    """Y con su nombre, no con el del vecino."""
    filas = [rot for tipo, rot, cods in CONSOLIDADO
             if tipo == "det" and codigo in (cods or [])]
    assert filas == [rotulo], f"{codigo} aparece en {filas}, se esperaba [{rotulo!r}]"


def test_ningun_codigo_se_perdio_ni_se_duplico():
    """⚠️ Separar no puede tirar un código ni contarlo dos veces: lo primero
    deja plata fuera del reporte y lo segundo la cuenta doble, y el total sigue
    cuadrando contra sí mismo en los dos casos."""
    for bloque in ("REVENUES", "Operating Expenses", "Operating Profit"):
        dentro, vistos = False, []
        for tipo, rot, cods in CONSOLIDADO:
            if tipo == "sec":
                dentro = rot == bloque
                continue
            if dentro and tipo == "det":
                vistos += list(cods or [])
            elif dentro and tipo == "tot":
                break
        assert len(vistos) == len(set(vistos)), (
            f"{bloque}: códigos repetidos → {sorted(c for c in vistos if vistos.count(c) > 1)}")


def test_el_orden_es_el_del_pl_declarado():
    """El orden sale del CLAUDE.md §17.3: Transporte va después de Retail, no al
    fondo con lo que no tiene nombre."""
    orden = [rot for tipo, rot, _ in CONSOLIDADO if tipo == "det"]
    i_retail = orden.index("Retail-Gift Shop")
    i_transp = orden.index("Transportation")
    i_misc = next(i for i, r in enumerate(orden) if "iscell" in r)
    assert i_retail < i_transp < i_misc
