# -*- coding: utf-8 -*-
"""El default de esta instalación tiene que ser ESTA instalación.

`app/hotel_actual.py` ya explica el modo de falla, y este repositorio lo tenía
puesto: se clonó de Amarena y los defaults quedaron en `AMA` / «Amarena Canvas
Beach Hotel». En producción no mordía porque Railway pasa `HOTEL_ID=OXI` por
entorno — o sea que lo único que separaba a Oxygen de nacer con el nombre, el
id y los datos del hotel de al lado era una variable de entorno.

Es exactamente lo que el módulo advierte que pasó una vez con Corcovado: «una
variable que no llegó a Railway hacía nacer el hotel llamándose Corcovado, sin
dar error y sin que nadie se enterara hasta ver dato ajeno».
"""
import os

MIO = {"OXI", "Oxygen", "Oxygen Jungle Villas"}
AJENOS = {"CWL", "AMA", "AMR", "COR", "OJO",
          "Corcovado", "Amarena", "Amarena Canvas Beach Hotel"}


def _defaults():
    """Los valores SIN entorno: es lo que se quiere blindar."""
    for v in ("HOTEL_ID", "HOTEL_NAME", "HOTEL_SHORT_NAME"):
        os.environ.pop(v, None)
    import importlib

    from app import hotel_actual
    importlib.reload(hotel_actual)
    return (hotel_actual.HOTEL_ID, hotel_actual.HOTEL_NAME,
            hotel_actual.HOTEL_SHORT)


def test_el_default_no_es_el_hotel_de_al_lado():
    for v in _defaults():
        assert v not in AJENOS, (
            "el default es de otra propiedad: sin la variable de entorno esta "
            "instalación nace con el nombre y el id ajenos, sin dar error")


def test_el_default_es_esta_propiedad():
    ident, nombre, corto = _defaults()
    assert ident in MIO and nombre in MIO and corto in MIO
