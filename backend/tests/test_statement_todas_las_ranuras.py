# -*- coding: utf-8 -*-
"""El P&L Statement muestra TODAS las versiones elegidas, no dos.

Owner, 2026-09-03: *«no metiste el escenario Forecast; favor meterlo en las
líneas, quitar esas y poner»* —señalando las dos columnas de «% Rev»—.

⚠️ Este cuadro era el ÚNICO de la pantalla cableado a dos escenarios (`idA` e
`idB`). Los demás sub-tabs ya dibujan una columna por ranura ocupada, y los
datos del tercero **ya se cargaban**: lo que faltaba era pedirlos.
"""
from pathlib import Path

FRONT = Path(__file__).resolve().parents[2] / "frontend"
PAGINA = FRONT / "app/month-end/pl/page.tsx"


def _estado() -> str:
    """El bloque del P&L Statement: de su tabla al pie."""
    src = PAGINA.read_text(encoding="utf-8")
    i = src.index('<th rowSpan={2} style={{ ...TH, textAlign: "left"')
    return src[i:src.index("estadoPieConPrev")]


def test_el_encabezado_dibuja_una_columna_por_RANURA():
    bloque = _estado()
    assert "usadas.slice(0, trasVariacion).map((u, j) => (" in bloque
    assert "usadas.slice(trasVariacion).map(u => (" in bloque


def test_el_ancho_del_bloque_no_es_un_numero_a_mano():
    """⚠️ Con `colSpan={6}` fijo, agregar el Forecast dejaba el título del
    bloque corrido una columna y el cuadro entero desalineado."""
    bloque = _estado()
    assert "colSpan={usadas.length + 2}" in bloque, (
        "el ancho del bloque volvió a ser un número escrito a mano")


def test_las_SUB_FILAS_traen_las_mismas_columnas_que_su_concepto():
    """Cuando el concepto pasó a una columna por ranura y el desglose se quedó
    en dos, cada número salía debajo del encabezado del de al lado — que es
    peor que no mostrarlo."""
    bloque = _estado()
    assert "const subCelda = (u:" in bloque
    assert bloque.count("usadas.slice(0, trasVariacion)") >= 2


def test_salieron_las_dos_columnas_de_pct_Rev_por_escenario():
    """Eran el mismo porcentaje repetido por escenario, y es lo que el owner
    marcó para sacar."""
    bloque = _estado()
    assert "% Rev Bud" not in bloque
    assert "pctRev(vB, gB" not in bloque, (
        "volvió la columna «% Rev» del segundo escenario")


def test_se_QUEDA_el_pct_Rev_del_año_anterior():
    """Ése no es una repetición: compara contra otro año, y es la única columna
    del cuadro que mira hacia atrás."""
    bloque = _estado()
    assert 'pctRev(prevPL, prevGasto, f.code, "ytd")' in bloque


def test_el_EXCEL_baja_lo_que_se_esta_viendo():
    """⚠️ Este proyecto ya pagó una vez por un Excel que no era la pantalla
    (owner, 2026-08-27: «el excel no baja lo que está viendo»). Dejar el par
    fijo en el export mientras la pantalla dibuja tres sería repetirlo."""
    src = PAGINA.read_text(encoding="utf-8")
    # ⚠️ La firma lleva un parámetro desde el 2026-09-03 (`conDepto`), así que
    # buscar `cuadroEstado()` con paréntesis vacío fallaba por el cambio de
    # firma y no por la regla.
    i = src.index("function cuadroEstado(")
    cuadro = src[i:src.index("function cuadroSummary")]
    assert "usadas.slice(0, trasVariacion)" in cuadro
    assert "% Rev Budget" not in cuadro
    # Y el subtítulo nombra a todas, no a dos.
    assert 'usadas.map(u => etiqueta(u.id)).join(" · ")' in cuadro
