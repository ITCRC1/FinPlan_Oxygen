# -*- coding: utf-8 -*-
"""EL VERBO QUE MANDA EL FRONT TIENE QUE SER EL QUE ACEPTA LA RUTA.

**El agujero, encontrado en Amarena el 2026-08-27.** El owner apretó «Guardar
cambios» en el auxiliar Below-GOP —con la renta ya digitada, US$11.200— y le
salió `Error: API 405: {"detail":"Method Not Allowed"}`. La ruta existía, el
front la llamaba, los tipos compilaban y las 3.682 pruebas pasaban: el front
mandaba **PUT** a `/nonop/{id}/bulk/` y el backend la tenía declarada **POST**.
El propio docstring del archivo decía PUT.

No era el único. Tres más del mismo tipo, todas botones de guardar:

  · `/scenarios/{id}/master/`          — Master Data. El handler se llama
                                        `put_scenario_master` y estaba en POST.
  · `/estadisticas/catalogo/{code}/`   — editar el nombre de una cuenta.
  · `/pl/{id}/manual/{month}/`         — los inputs manuales del P&L, que es de
                                        donde sale el management fee.

Por qué no lo veía nada: una prueba de backend llama a la función de Python, no
a la ruta, así que el verbo le da igual; y `tsc` verifica los tipos del cuerpo,
no que el método exista al otro lado. La única señal era el 405 en pantalla,
cuando el usuario ya había digitado.

Se comparan sólo las llamadas cuya ruta SÍ existe en el backend. Una ruta que no
aparece es casi siempre un `${qs}` de query string que este normalizador toma
como segmento — ahí habría falsos positivos, y una prueba con falsos positivos
se termina apagando.
"""
from __future__ import annotations

import io
import pathlib
import re

import pytest

API_TS = (pathlib.Path(__file__).resolve().parent.parent.parent
          / "frontend" / "lib" / "api.ts")

#: `api.put<T>(`/ruta/${x}/`, ...)`. El genérico es opcional.
LLAMADA = re.compile(
    r"api\.(get|post|put|delete|patch)\s*(?:<[^>(]*>)?\s*\(\s*`([^`]+)`")


def _normalizar(ruta: str) -> str:
    """`/nonop/${id}/bulk/` → `/api/nonop/{p}/bulk/`, comparable con el openapi."""
    ruta = re.sub(r"\$\{[^}]*\}", "{p}", ruta).split("?")[0]
    return ruta if ruta.startswith("/api") else "/api" + ruta


@pytest.fixture(scope="module")
def llamadas_del_front() -> list[tuple[str, str, str]]:
    if not API_TS.exists():
        pytest.skip(f"no está el front en este árbol: {API_TS}")
    fuente = io.open(API_TS, encoding="utf-8").read()
    return [(v.upper(), cruda, _normalizar(cruda))
            for v, cruda in LLAMADA.findall(fuente)]


@pytest.fixture(scope="module")
def rutas_del_back() -> dict[str, set[str]]:
    from app.main import app

    out: dict[str, set[str]] = {}
    for ruta, ops in app.openapi()["paths"].items():
        out.setdefault(re.sub(r"\{[^}]*\}", "{p}", ruta), set()).update(
            m.upper() for m in ops)
    return out


def test_el_lector_encuentra_las_llamadas(llamadas_del_front):
    """Si el regex deja de casar, todo lo demás pasaría vacío y en silencio."""
    assert len(llamadas_del_front) > 200, (
        f"sólo {len(llamadas_del_front)} llamadas: el lector de api.ts se rompió")


def test_ninguna_llamada_del_front_da_405(llamadas_del_front, rutas_del_back):
    malas = []
    for verbo, cruda, ruta in llamadas_del_front:
        acepta = rutas_del_back.get(ruta)
        if acepta is not None and verbo not in acepta:
            malas.append(f"el front manda {verbo} a {cruda} "
                         f"y el backend acepta {sorted(acepta)}")
    assert not malas, (
        "estas llamadas devuelven 405 Method Not Allowed en producción:\n  "
        + "\n  ".join(malas))


def test_el_guardado_del_auxiliar_below_gop_acepta_put(rutas_del_back):
    """El caso que lo destapó, por nombre: sin esto no se puede guardar la renta."""
    assert "PUT" in rutas_del_back["/api/nonop/{p}/bulk/"]


@pytest.mark.parametrize("ruta", [
    "/api/scenarios/{p}/master/",
    "/api/estadisticas/catalogo/{p}/",
    "/api/pl/{p}/manual/{p}/",
    "/api/opex/{p}/bulk/",
    "/api/payroll/{p}/bulk/",
    "/api/capital/{p}/bulk/",
])
def test_los_guardados_de_reemplazo_van_por_put(ruta, rutas_del_back):
    """La convención de la casa: una carga que REEMPLAZA lo que había es PUT.
    Estaba respetada en opex, payroll y capital, y rota en las otras tres."""
    assert "PUT" in rutas_del_back[ruta], (
        f"{ruta} acepta {sorted(rutas_del_back[ruta])}")
