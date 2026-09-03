# -*- coding: utf-8 -*-
"""El default de esta instalación tiene que ser ESTA instalación.

`app/hotel_actual.py` ya explica el modo de falla, y se materializó dos veces:

* **Corcovado**, contado en ese módulo: «una variable que no llegó a Railway
  hacía nacer el hotel llamándose Corcovado, sin dar error y sin que nadie se
  enterara hasta ver dato ajeno».
* **Oxygen**, el 2026-09-03: se clonó de Amarena y los defaults quedaron en
  `AMA`. En producción no mordía porque Railway pasa `HOTEL_ID`, o sea que lo
  único que separaba a Oxygen de nacer con el id del hotel de al lado era una
  variable de entorno.

⚠️ **La primera versión de esta prueba escribía el id esperado a mano.** Eso la
ataba a una propiedad: al clonar a Ojochal Gardens falló pidiendo `OXI`. Y era
peor que eso — **como sólo miraba el backend, no vio que el front de Oxygen
seguía en `AMA`** después de arreglar el backend.

Lo que se comprueba ahora no es *cuál* es el id, sino que **los dos lados digan
el mismo**. Eso vale en cualquier clon sin tocar la prueba, y agarra justo el
caso que se escapó: arreglar una mitad y olvidar la otra.
"""
import os
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[2] / "frontend"


def _del_backend():
    """Los valores SIN entorno: es lo que se quiere blindar."""
    for v in ("HOTEL_ID", "HOTEL_NAME", "HOTEL_SHORT_NAME"):
        os.environ.pop(v, None)
    import importlib

    from app import hotel_actual
    importlib.reload(hotel_actual)
    return hotel_actual.HOTEL_ID


def _del_front():
    texto = (FRONT / "lib" / "hotel.ts").read_text(encoding="utf-8")
    m = re.search(r'NEXT_PUBLIC_HOTEL_ID\s*\|\|\s*"([^"]+)"', texto)
    assert m, "cambió la forma del default en frontend/lib/hotel.ts"
    return m.group(1)


def test_el_backend_y_el_front_declaran_el_MISMO_hotel():
    atras, adelante = _del_backend(), _del_front()
    assert atras == adelante, (
        f"el backend nace como «{atras}» y el front como «{adelante}»: una "
        f"mitad quedó con la identidad de otra propiedad, y sólo la variable "
        f"de entorno lo tapa")


def test_el_default_existe_y_no_es_un_relleno():
    ident = _del_backend()
    assert ident and ident.strip(), (
        "sin default, esta instalación nace sin identidad si la variable de "
        "entorno no llega")
    assert ident.upper() == ident, (
        "el id del hotel es un código en mayúsculas; el reporte de Junta cruza "
        "por ese código y no por el nombre")
