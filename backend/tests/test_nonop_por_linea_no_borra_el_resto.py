# -*- coding: utf-8 -*-
"""UN GUARDADO PARCIAL NO PUEDE BORRAR LO QUE NO ESTA MIRANDO.

`bulk_replace_nonop` borra TODO el below-GOP del escenario antes de insertar. Eso
está bien para la pantalla del auxiliar, que manda siempre el set completo, y es
una bomba para cualquier pantalla parcial: la de Management Fees toca tres
líneas —honorarios, royalties y capital reserve— y con el bulk se habría llevado
la renta (US$11.200) y el seguro (US$1.670,13) del owner sin decir nada.

Por eso existe `replace_nonop_lines`: reemplaza SÓLO los `report_line_code` que
vienen en el cuerpo. Lo que fija esta prueba es justo eso, porque es un fallo que
no da error — la pantalla diría «guardado» y la plata ya no estaría.

Cuerpo vacío = no hacer nada. «Borrar todo lo que vino» cuando no vino nada
sería el mismo bug por la puerta de atrás.
"""
from __future__ import annotations

import inspect

import pytest

from app.api.nonop_api import replace_nonop_lines


def _fuente() -> str:
    return inspect.getsource(replace_nonop_lines)


def test_el_delete_esta_filtrado_por_linea():
    """La guarda entera es ese `in_(lineas)`. Sin él, es el bulk."""
    fuente = _fuente()
    assert "NonOpEntry.report_line_code.in_(lineas)" in fuente, (
        "el borrado dejó de estar filtrado por línea: se lleva todo el below-GOP")


def test_el_delete_tambien_esta_acotado_al_escenario():
    """Un `delete` por línea sin `scenario_id` cruzaría escenarios: guardar en el
    Working 2026 borraría la misma línea del 2027."""
    fuente = _fuente()
    i = fuente.index("delete(NonOpEntry)")
    trozo = fuente[i:i + 400]
    assert "NonOpEntry.scenario_id == scenario_id" in trozo


def test_un_cuerpo_vacio_no_borra_nada():
    fuente = _fuente()
    assert "if not lineas:" in fuente, (
        "sin líneas en el cuerpo tiene que salir sin tocar la base")
    i_guarda = fuente.index("if not lineas:")
    i_delete = fuente.index("delete(NonOpEntry)")
    assert i_guarda < i_delete, "la salida temprana quedó después del borrado"


def test_valida_las_lineas_contra_el_reporte():
    """Estas filas siembran la línea del P&L directamente, sin pasar por el
    mapeo de cuentas: un código inexistente se guardaría y su monto no llegaría
    a ningún reporte."""
    fuente = _fuente()
    assert "nonop.lineas_inexistentes" in fuente
    assert "load_report_line_config" in fuente


def test_mira_el_candado_del_escenario():
    fuente = _fuente()
    assert "assert_editable" in fuente, (
        "escribiría sobre un escenario enllavado")


def test_esta_registrado_en_la_api():
    from app.main import app

    rutas = app.openapi()["paths"]
    assert "/api/nonop/{scenario_id}/lines/" in rutas
    assert "put" in rutas["/api/nonop/{scenario_id}/lines/"]


def test_el_bulk_sigue_borrando_todo():
    """La contraparte. El bulk NO se cambió: la pantalla del auxiliar depende de
    que borre todo, porque así es como se elimina un renglón de detalle."""
    from app.api.nonop_api import bulk_replace_nonop

    fuente = inspect.getsource(bulk_replace_nonop)
    assert "delete(NonOpEntry)" in fuente
    assert "report_line_code.in_(" not in fuente


def test_la_pantalla_de_fees_no_usa_el_bulk():
    """El motivo de todo: si esa pantalla vuelve al bulk, borra la renta y el
    seguro en el primer Guardar."""
    import io
    import pathlib

    tsx = (pathlib.Path(__file__).resolve().parent.parent.parent
           / "frontend" / "app" / "nonop" / "management-fees" / "page.tsx")
    if not tsx.exists():
        pytest.skip("no está el front en este árbol")
    fuente = io.open(tsx, encoding="utf-8").read()
    assert "replaceNonOpLines" in fuente
    assert "bulkReplaceNonOp" not in fuente, (
        "la pantalla de Management Fees volvió al bulk: borra el resto del "
        "below-GOP en cada guardado")


def test_la_pantalla_de_fees_manda_las_tres_lineas_aunque_esten_en_cero():
    """Escribir ceros es cómo se BORRA un monto manual y se le devuelve el
    control al %. Si la pantalla filtrara los ceros, un monto ya guardado no se
    podría quitar nunca desde ahí."""
    import io
    import pathlib

    tsx = (pathlib.Path(__file__).resolve().parent.parent.parent
           / "frontend" / "app" / "nonop" / "management-fees" / "page.tsx")
    if not tsx.exists():
        pytest.skip("no está el front en este árbol")
    fuente = io.open(tsx, encoding="utf-8").read()
    for code in ("MGMT_FEE_3", "MGMT_FEE_5_ROYALTIES", "CAPITAL_RESERVE"):
        assert code in fuente, f"la pantalla dejó de mandar {code}"
    assert "if (variosDetalles[code]) continue;" in fuente, (
        "se perdió la guarda de los varios detalles: guardar desde acá "
        "colapsaría los renglones del auxiliar en uno")
