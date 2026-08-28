# -*- coding: utf-8 -*-
"""
LOS CÓDIGOS DE CATEGORÍA SON DEL GRUPO, Y UNA PROPIEDAD NUEVA NACE CON ELLOS.

## Por qué existe (2026-08-27)

El owner dejó un juego de códigos ESTÁNDAR para todas las propiedades —`BL01`,
`BI02`…— con la idea de que cada hotel sólo editara el NOMBRE. Al clonar para
Amarena eso no viajó, y no porque se perdiera: nunca estuvo hecho para viajar.

La migración `068_room_type_code.py` los asigna dentro de un
`if r.hotel_id == "CWL"`; cualquier otra propiedad cae en el `else` y recibe el
correlativo `SH01`, `SH02`… Y aunque el `if` no la excluyera, tampoco pasaría
nada: la migración renumera filas que ya existen, y una propiedad nueva no tiene
ninguna.

El resultado medido: si Amarena se provisionaba desde la app, las dos pantallas
que crean categorías (`revenue/inventory`, `revenue/master`) llaman a
`createRoomType` SIN código, así que nacían `SH01…SH0N`.

**Y eso no se arregla después.** El `PUT` devuelve 409
`tipo_habitacion.codigo_no_se_cambia` en cuanto hay un código puesto —sólo deja
rellenar uno VACÍO, y el autogenerado no lo está—, el `DELETE` oculta en vez de
borrar, y el correlativo cuenta también las ocultas. Un código mal puesto el
primer día queda mal para siempre, y el reporte de Junta cruza por código.

## Lo que cuida

* El estándar es UNO y del grupo: no vive bajo `seed_data/<HOTEL_ID>/`.
* Son los ocho códigos del owner, en su orden, sin repetidos.
* La semilla NO trae el nombre de ninguna categoría de Corcovado — el rótulo es
  de cada propiedad y sembrar el ajeno es exactamente cómo se guardan las
  noches de un hotel bajo la categoría de otro.
* `units` arranca en 0: un número plausible pero ajeno se arrastra a ocupación,
  RevPAR y P&L sin dar error. En 0 se nota que falta.
* Los enteros llegan como `int` y no como `Decimal` ni `str` — las columnas son
  `Integer`.
"""
import pathlib

import pytest

from app.seed_data import room_types_estandar

#: Los del owner, en orden (2026-08-27). Si esta lista cambia, que sea a mano y
#: leyendo la prueba: renumerar categorías es lo que la regla del 409 prohíbe.
ESTANDAR = ["BL01", "BI02", "PO03", "RO04", "BI05", "BL06", "SH07", "SH08"]

#: Nombres reales de las categorías de Corcovado. Ninguno puede aparecer en la
#: semilla del grupo. Salen de `CWL_ROOM_TYPES`, que sigue en el modelo.
NOMBRES_DE_CORCOVADO = [
    "corcovado", "carate", "agujas", "sirena", "treehouse", "5 elements",
    "deluxe king", "residencia",
]


def test_el_estandar_no_vive_por_hotel():
    """Un archivo por propiedad haría que dejara de ser un estándar."""
    raiz = pathlib.Path(__file__).resolve().parents[1] / "app" / "seed_data"
    assert (raiz / "room_types_estandar.json").exists()
    # Y que a nadie se le ocurra ponerle una copia a una propiedad.
    copias = list(raiz.glob("*/room_types_estandar.json"))
    assert copias == [], f"el estándar se bifurcó por hotel: {copias}"


def test_son_los_ocho_codigos_del_owner_en_orden():
    filas = room_types_estandar()
    assert [f["code"] for f in filas] == ESTANDAR
    assert [f["sort_order"] for f in filas] == list(range(1, len(ESTANDAR) + 1))


def test_ningun_codigo_repetido():
    codigos = [f["code"] for f in room_types_estandar()]
    assert len(codigos) == len(set(codigos))


@pytest.mark.parametrize("campo", ["name", "short_name"])
def test_el_nombre_no_es_el_de_corcovado(campo):
    for fila in room_types_estandar():
        texto = fila[campo].lower()
        for ajeno in NOMBRES_DE_CORCOVADO:
            assert ajeno not in texto, (
                f"la semilla del grupo trae «{fila[campo]}», que es de Corcovado: "
                "el código es del grupo, el nombre es de cada propiedad")


def test_arranca_sin_unidades():
    for fila in room_types_estandar():
        assert fila["units"] == 0, (
            f"{fila['code']} nace con {fila['units']} unidades: un número ajeno "
            "se arrastra a ocupación y RevPAR sin dar error")


def test_los_enteros_son_enteros():
    """Las columnas son `Integer`; un `Decimal` de `_a_decimal` no entra."""
    for fila in room_types_estandar():
        for campo in ("sort_order", "units", "pax_min", "pax_max"):
            assert type(fila[campo]) is int, f"{fila['code']}.{campo}"


def test_el_seed_siembra_solo_si_no_hay_nada():
    """La condición es «la tabla está vacía», no «el hotel es X».

    Un seed que reafirmara en cada arranque le pisaría al owner el nombre que
    acaba de cargar — que es el modo de falla documentado para `account_mapping`
    y `report_line_config` en `CLAUDE.md`.
    """
    fuente = (pathlib.Path(__file__).resolve().parents[1] / "app" / "seed.py"
              ).read_text(encoding="utf-8")
    bloque = fuente.split("existing_types = result.scalars().all()")[1]
    condicion, resto = bloque.split("else:", 1)
    assert "if existing_types:" in condicion
    # Sembrar va en la rama del `else` (tabla vacía), nunca en la otra.
    assert "room_types_estandar()" in resto
    assert "room_types_estandar()" not in condicion
