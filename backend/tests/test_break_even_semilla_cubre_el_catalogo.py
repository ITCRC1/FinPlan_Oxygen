# -*- coding: utf-8 -*-
"""LA SEMILLA DEL BREAK-EVEN CUBRE EL CATÁLOGO DE CUENTAS DE ESTA PROPIEDAD.

## Qué caza, y por qué importa

El motor (`app/engine/break_even.py` §2.6) resuelve cada monto del P&L en tres
pasos, y el tercero es: *sin regla → el monto se cuenta **100% FIJO** y se
registra en «Por defecto: 100% fijo»*. O sea que una cuenta sin clasificar **no
rompe nada**: entra al cálculo, suma al costo fijo y sube el punto de equilibrio
sin que ninguna pantalla diga «falta un dato». El error se ve como un número.

Es el mismo agujero por el que Oxygen arrancó con **cero filas** de
clasificación: el tab no fallaba, mostraba 100% de margen de contribución.

Así que la única forma de que se note es medirlo acá: **toda cuenta de gasto del
catálogo de la propiedad tiene que tener regla, o estar declarada abajo con su
motivo.** Si mañana alguien agrega una cuenta a `orden_plantilla.json` y se
olvida de clasificarla, esta prueba se pone roja con el código, el nombre y el
departamento — que es exactamente lo que el cálculo no dice.

## Por qué el catálogo es `orden_plantilla.json`

Es la lista de cuentas por departamento que la propiedad usa en el Detalle, y la
misma que alimenta el upload. Las cuentas de INGRESO quedan fuera a propósito:
el break-even clasifica COSTO (spec §2.2), el ingreso entra completo al margen.

## Idempotente por propiedad

Lee la carpeta de ESTA instalación (`app.seed_break_even.leer`, que resuelve por
`HOTEL_ID`). Una propiedad todavía sin semilla se saltea en vez de fallar — es
un estado legítimo del clon, y lo denuncia el Chequeo, no esta prueba.
"""
import json
import pathlib

import pytest

from app.hotel_actual import HOTEL_ID
from app.seed_break_even import leer

CATALOGO = (pathlib.Path(__file__).resolve().parents[1]
            / "app" / "seed_data" / "orden_plantilla.json")

#: Cuentas de gasto del catálogo que a propósito NO llevan regla, con el motivo.
#: **Vacío hoy**: las 663 cuentas de gasto de Oxygen tienen clasificación.
#:
#: Va acá y no en un comentario para que agregar una excepción sea un cambio
#: visible en el diff: dejar una cuenta sin clasificar es una decisión contable,
#: no un olvido, y tiene que costar una línea escrita.
SIN_REGLA_A_PROPOSITO: dict[tuple[str, str], str] = {}

#: Las clases de `orden_plantilla.json` que son GASTO. `Revenue` no entra: el
#: break-even clasifica costo.
CLASES_DE_GASTO = {"Payroll", "Cost", "Opex", "BelowGOP"}


def _cuentas_de_gasto() -> list[dict]:
    orden = json.loads(CATALOGO.read_text(encoding="utf-8"))["orden"]
    return [x for x in orden if x["clase"] in CLASES_DE_GASTO]


@pytest.fixture(scope="module")
def semilla():
    deptos, clases = leer()
    if not deptos and not clases:
        pytest.skip(f"la propiedad {HOTEL_ID} no trae semilla de break-even")
    return deptos, clases


def test_toda_cuenta_de_gasto_tiene_regla(semilla):
    """Ninguna cuenta del catálogo cae en «Por defecto: 100% fijo» por descuido."""
    _deptos, clases = semilla
    con_regla = {(c["dept_code"], c["account"]) for c in clases
                 if c["map_source"] == "GL"}

    faltan = [x for x in _cuentas_de_gasto()
              if (x["dept_code"], x["cuenta"]) not in con_regla
              and (x["dept_code"], x["cuenta"]) not in SIN_REGLA_A_PROPOSITO]

    assert not faltan, (
        "estas cuentas de gasto del catálogo no tienen regla de clasificación y "
        "el motor las va a contar como 100% FIJO sin avisar. Clasificalas en "
        f"app/seed_data/{HOTEL_ID}/break_even/be_classification_seed.csv, o "
        "declaralas en SIN_REGLA_A_PROPOSITO con su motivo:\n"
        + "\n".join(f"  {x['dept_code']} {x['cuenta']} ({x['clase']})"
                    for x in faltan))


def test_no_hay_reglas_para_cuentas_que_no_existen(semilla):
    """Al revés: una regla sin cuenta es una cuenta borrada o mal tecleada.

    No cambia ningún total —el motor la reporta como `regla_huerfana`— pero
    ensucia la pantalla de configuración con filas que nunca van a recibir un
    monto, y esconde las que sí importan.
    """
    _deptos, clases = semilla
    catalogo = {(x["dept_code"], x["cuenta"]) for x in _cuentas_de_gasto()}
    sobran = [(c["dept_code"], c["account"]) for c in clases
              if c["map_source"] == "GL"
              and (c["dept_code"], c["account"]) not in catalogo]
    assert not sobran, (
        "estas reglas apuntan a cuentas que el catálogo de la propiedad no "
        f"tiene: {sobran}")


def test_todo_departamento_del_catalogo_esta_en_la_semilla(semilla):
    """Un `dept_code` sin departamento pierde el corte por departamento.

    `_be_base` arma `dept_slug` desde `be_department.dept_codes`. Un código que
    no esté en ninguno entra al TOTAL con el slug vacío y desaparece del tab
    «Por Departamento»: las dos pantallas dejan de sumar lo mismo y la que
    miente es la que se usa para decidir.
    """
    deptos, _clases = semilla
    conocidos = {c.strip() for d in deptos
                 for c in (d["dept_codes"] or "").split(",") if c.strip()}
    faltan = sorted({x["dept_code"] for x in _cuentas_de_gasto()} - conocidos)
    assert not faltan, (
        "estos códigos de departamento del catálogo no están en ningún "
        f"`dept_codes` de be_departments_seed.csv: {faltan}")


def test_el_porcentaje_concuerda_con_la_clase(semilla):
    """`pct_variable` es lo único que se calcula; `original_class` es su origen.

    La carga inicial del spec §1 es literal: `Variable → 1.00`,
    `Fixed Cost → 0.00`. Si los dos campos se contradicen, el que manda es el
    porcentaje —el que la clase dice es el que el usuario cree estar viendo.
    """
    _deptos, clases = semilla
    malas = [(c["dept_code"], c["account"], c["original_class"], c["pct_variable"])
             for c in clases
             if c["pct_variable"] != ("1.0" if c["original_class"] == "Variable"
                                     else "0.0")]
    assert not malas, f"clase y porcentaje se contradicen: {malas}"


def test_solo_el_impuesto_de_renta_queda_fuera_del_equilibrio(semilla):
    """`excluded_from_be` es el impuesto y nada más (spec §2.5).

    Es función del resultado, no un costo fijo. Cualquier otra fila marcada
    saldría del costo fijo y **bajaría** el punto de equilibrio, o sea que el
    error se vería como una buena noticia.
    """
    _deptos, clases = semilla
    excluidas = {c["pl_line"] for c in clases
                 if str(c["excluded_from_be"]).strip().lower() in ("true", "1")}
    assert excluidas <= {"INCOME_TAXES"}, (
        f"hay filas excluidas del equilibrio que no son el impuesto: {excluidas}")
