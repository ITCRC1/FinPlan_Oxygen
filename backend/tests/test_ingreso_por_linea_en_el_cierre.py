# -*- coding: utf-8 -*-
"""
EL TAB DE INGRESO DEL CIERRE MUESTRA ALGO, Y MUESTRA LO MISMO QUE EL P&L.

## Por qué existe (2026-08-27)

Owner, mirando «Revenue x Depto» vacío y el P&L al lado con las cifras: *«¿y por
qué acá sí sale?»*.

Los dos cuadros salían de fuentes distintas. El P&L lee `pl_lines` —donde el
ingreso está abierto por LÍNEA: Rooms $374,791.20, Club Madresal $150,040, SPA
$11,448, Tours $10,800—. El tab de apertura lee `/gasto-por-clase/?detalle=true`,
que tiene **dos caminos**: cuando hay detalle del mayor abre las cinco clases,
y cuando no lo hay —un presupuesto armado con checkbooks— abría planilla, costo
y opex… y **nunca tocaba el ingreso**. No existe un `revenue_by_dept` al lado de
`payroll_by_dept`, `cos_by_dept` y `opex_by_dept`.

Resultado: el tab salía vacío con el aviso «los presupuestos armados solo con
drivers no tienen detalle por departamento», que era **falso** — Amarena tiene
checkbook de ingresos cargado.

## Por qué por LÍNEA y no por departamento

El ingreso del presupuesto no se carga por departamento: se carga por línea. Y
una línea como `ROOMS` abarca cinco departamentos (`0110`, `0111`, `0112`,
`0113`, `0114` en `OPERATING_DEPT_GROUPS`). Repartirla entre ellos sería inventar
una atribución que nadie cargó — en un libro que va a los dueños.

## Lo que cuida

* **La rama de checkbook abre el ingreso.** Es lo que estaba faltando.
* **Sale de `pl_lines`**, la misma fila que lee el tab de P&L. Los dos cuadros
  coinciden porque leen lo mismo, no porque dos cálculos den igual.
* **Los agregados quedan afuera.** `TOTAL_REVENUES` y `SEC_REVENUES` son el total
  y el encabezado de la sección: incluirlos duplicaría el ingreso, y el error se
  vería como «el doble» — de los que pasan desapercibidos porque todo sigue
  sumando consigo mismo.
* **Los rótulos viajan**, o la fila diría `REV_ROOMS` a secas.
"""
import pathlib
import re

FUENTE = (pathlib.Path(__file__).resolve().parents[1] /
          "app" / "api" / "gasto_por_clase_api.py").read_text(encoding="utf-8")

#: Los dos agregados de la sección REVENUES que NO son una línea de ingreso.
AGREGADOS = ["TOTAL_REVENUES", "SEC_REVENUES"]


def _rama_checkbook() -> str:
    """El bloque `else:` de `_por_mes` — el camino sin detalle del mayor."""
    cuerpo = FUENTE.split("filas_gl = await recalc.actual_rows_for_month")[1]
    return cuerpo.split("filas.append(")[0].split("else:", 1)[1]


def test_la_rama_de_checkbook_abre_el_ingreso():
    """Era exactamente lo que faltaba: las otras tres clases sí se abrían."""
    rama = _rama_checkbook()
    for clase in ("payroll", "cost", "opex", "property"):
        assert clase in rama, f"la rama dejó de abrir {clase}"
    assert '"revenue"' in rama, (
        "la rama de checkbook no abre el ingreso: el tab «Revenue x Depto» "
        "vuelve a salir vacío en todo presupuesto armado con checkbooks")


def test_el_ingreso_sale_de_las_lineas_del_pl():
    """La misma fila que lee el tab de P&L, no un cálculo paralelo."""
    assert "from app.models.pl_line import PLLine" in FUENTE
    assert "PLLine.section ==" in FUENTE and '"REVENUES"' in FUENTE
    assert "lineas_ingreso" in _rama_checkbook(), (
        "el ingreso de la rama de checkbook no viene de `pl_lines`")


def test_los_agregados_no_entran():
    """Sumar el total junto a sus partes duplica el ingreso."""
    m = re.search(r"line_code\.notin_\(\[([^\]]*)\]\)", FUENTE)
    assert m, "no se está filtrando ningún line_code agregado"
    excluidos = m.group(1)
    for codigo in AGREGADOS:
        assert codigo in excluidos, f"{codigo} entraría como si fuera una línea"


def test_los_rotulos_de_las_lineas_llegan_a_la_pantalla():
    """Sin esto la fila encabeza `REV_ROOMS` en vez de «Rooms Revenue»."""
    assert "_nombra(detalle, ln.line_code" in FUENTE
    cola = FUENTE.split("departamentos")[-2:]
    assert any("nombres_cuenta" in t for t in cola), (
        "los rótulos de línea no se mezclan en el mapa que usa la pantalla")


def test_no_se_invento_un_reparto_por_departamento():
    """Una línea abarca varios departamentos; repartirla sería inventar dato.

    Se miran las líneas de CÓDIGO, no los comentarios: el comentario de esa
    rama nombra `OPERATING_DEPT_GROUPS` justamente para explicar por qué NO se
    usa, y una prueba que leyera el texto crudo se dispararía con la explicación
    en vez de con el hecho.
    """
    codigo = "\n".join(l for l in _rama_checkbook().splitlines()
                       if not l.strip().startswith("#"))
    assert "OPERATING_DEPT_GROUPS" not in codigo, (
        "se está atribuyendo el ingreso a departamentos: eso no está cargado")
