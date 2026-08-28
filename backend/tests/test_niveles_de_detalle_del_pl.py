# -*- coding: utf-8 -*-
"""
LOS TRES NIVELES DEL P&L SE ALCANZAN ENTRE SÍ, Y EL SALTO LLEVA EL ESCENARIO.

## Por qué existe (2026-08-27)

Owner: *«quiero ese reporte con varios niveles de detalle con solo un click:
1-Resumido · 2-P&L a nivel Departamental · 3-Detallado, máximo detalle»*.

Los tres reportes ya existían. Lo que faltaba era poder pasar de uno a otro sin
salir al menú **y sin volver a elegir el escenario** — que es donde se pierde la
comparación: el de al lado abre en otro escenario, los números no son los
mismos, y no hay nada que avise.

## Lo que cuida

* **Los tres destinos existen** como pantallas. Un `href` a una ruta que no está
  no da error de compilación: da un 404 al hacer clic.
* **El control está en las tres**, no sólo en la de donde salió el pedido. Si
  estuviera en una sola, sería un viaje de ida.
* **El salto lleva `esc`** — el escenario. Sin eso el reporte de al lado abre en
  el que tenga recordado y muestra **otro presupuesto real, bien sumado**. Es el
  mismo modo de falla que documenta `lib/contexto.ts` para `IrA`.
* **En la pantalla de DOS selectores se lleva el de la columna 2**, que es la
  que el `?esc=` de la dirección maneja en esa pantalla. Llevar la otra haría
  que ir y volver cambiara la columna que se estaba mirando.
"""
import pathlib
import re

import pytest

FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend"
CONTROL = FRONT / "components" / "NivelDeDetalle.tsx"

#: (ruta del componente de pantalla, ruta del `href` que le toca)
NIVELES = [
    ("app/pl/simplified/page.tsx",          "/pl/simplified"),
    ("app/reports/pl-by-dept/page.tsx",     "/reports/pl-by-dept"),
    ("app/reports/pl-full-detail/page.tsx", "/reports/pl-full-detail"),
]


def _texto(rel: str) -> str:
    return (FRONT / rel).read_text(encoding="utf-8")


def test_el_control_existe():
    assert CONTROL.exists(), "falta components/NivelDeDetalle.tsx"


def test_son_tres_niveles_en_orden():
    s = CONTROL.read_text(encoding="utf-8")
    ns = [int(n) for n in re.findall(r"\{\s*n:\s*(\d)", s)]
    assert ns == [1, 2, 3], f"los niveles no están 1-2-3: {ns}"


@pytest.mark.parametrize("rel,href", NIVELES)
def test_cada_destino_es_una_pantalla_que_existe(rel, href):
    assert (FRONT / rel).exists(), f"{href} no tiene pantalla"
    assert href in CONTROL.read_text(encoding="utf-8"), \
        f"{href} no está entre los destinos del control"


@pytest.mark.parametrize("rel,_href", NIVELES)
def test_el_control_esta_en_las_tres_pantallas(rel, _href):
    s = _texto(rel)
    assert "NivelDeDetalle" in s, (
        f"{rel} no muestra el control: desde ahí el salto sería de ida nomás")
    assert "@/components/NivelDeDetalle" in s, f"{rel} no lo importa"


@pytest.mark.parametrize("rel,_href", NIVELES)
def test_el_salto_lleva_el_escenario(rel, _href):
    """Sin `esc`, el reporte de al lado abre en OTRO presupuesto sin avisar."""
    s = _texto(rel)
    m = re.search(r"<NivelDeDetalle([^/]*)/>", s)
    assert m, f"{rel}: no se pudo leer el uso del control"
    assert "esc=" in m.group(1), f"{rel}: el salto no lleva el escenario"


def test_el_control_pasa_esc_por_la_url():
    s = CONTROL.read_text(encoding="utf-8")
    assert "conContexto" in s, "el href no se arma con el contexto compartido"
    assert '"esc"' in s, "el contexto que viaja no incluye el escenario"


def test_la_pantalla_de_dos_columnas_lleva_la_segunda():
    """En `pl/simplified` el `?esc=` maneja la columna 2 (`desdeUrl` está ahí).

    Llevar `col1Id` compilaría igual y haría que ir y volver cambiara la columna
    que se estaba mirando — sin error y sin aviso.
    """
    s = _texto("app/pl/simplified/page.tsx")
    m = re.search(r"<NivelDeDetalle([^/]*)/>", s)
    assert m and "col2Id" in m.group(1), (
        "debe llevar col2Id: es la columna que el ?esc= de la dirección maneja "
        "en esta pantalla")
    # Y que eso siga siendo cierto: si alguien mueve el `desdeUrl` a la col 1,
    # esta prueba tiene que hacerlo notar.
    assert re.search(r'useEscenarioDe\("pl/simplified:budget".*true\)', s), \
        "el `desdeUrl` ya no está en la columna 2 — revisar qué escenario viaja"


def test_el_nivel_actual_no_es_un_link():
    """Un link a la pantalla en la que ya estás recarga y pierde lo desplegado."""
    s = CONTROL.read_text(encoding="utf-8")
    assert "activo ?" in s and 'aria-current="page"' in s
