# -*- coding: utf-8 -*-
"""«Channel Rooms Calculation» baja como MODELO, no como fotografía.

Owner, 2026-11-02: *«necesito que esta vista se pueda bajar tal cual como se ve
pero que esté formulado en forma automático todo… que sólo se cambie ocupación
y ADR para llegar a un total»*.

La descarga anterior escribía **números**: noches e ingreso ya calculados, sin
una sola fórmula. En un archivo así mover una noche no mueve nada, y el que lo
intenta tiene que rehacer la aritmética a mano — justo lo que el archivo
debería ahorrarle.

Estas pruebas miran el archivo que sale, no el código que lo escribe: que las
celdas derivadas sean fórmulas, y que las tres reglas del sistema sigan en pie
adentro del Excel.
"""
import io
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from app.export.canal_rooms_modelo_xlsx import construir_modelo

SEGMENTOS = [
    {"code": "AGENCIAS", "nombre": "Agencias", "genera_ingreso": True},
    {"code": "OTA", "nombre": "OTA's", "genera_ingreso": True},
    {"code": "CPL", "nombre": "CPL | Uso casa | Canjes", "genera_ingreso": False},
]
#: Enero y febrero con volúmenes MUY distintos: es lo que destapa el promedio
#: de promedios. Enero 100 noches a $600, febrero 10 a $300.
ENTRADAS = {
    ("AGENCIAS", 1): {"noches": Decimal("100"), "tarifa": Decimal("600")},
    ("AGENCIAS", 2): {"noches": Decimal("10"), "tarifa": Decimal("300")},
    ("OTA", 1): {"noches": Decimal("20"), "tarifa": Decimal("500")},
    ("CPL", 1): {"noches": Decimal("5"), "tarifa": Decimal("0")},
}
DISP = {m: Decimal("403") for m in range(1, 13)}


@pytest.fixture(scope="module")
def hoja():
    datos = construir_modelo(
        hotel="Oxygen Jungle Villas", escenario="BUDGET Working 2027",
        anio=2027, segmentos=SEGMENTOS, entradas=ENTRADAS, disponibles=DISP,
        ingreso_sistema=Decimal("70000"))
    return load_workbook(io.BytesIO(datos))["Channel Rooms"]


def _fila(hoja, etiqueta):
    for r in range(1, hoja.max_row + 1):
        v = hoja.cell(row=r, column=1).value
        if v and str(v).strip() == etiqueta:
            return r
    raise AssertionError(f"no está la fila «{etiqueta}»")


def test_el_ingreso_es_formula_no_numero():
    """La prueba que separa un modelo de una fotografía."""
    datos = construir_modelo(
        hotel="H", escenario="E", anio=2027, segmentos=SEGMENTOS,
        entradas=ENTRADAS, disponibles=DISP)
    w = load_workbook(io.BytesIO(datos))["Channel Rooms"]
    r = _fila(w, "Agencias") + 3            # etiqueta, noches, tarifa, ingreso
    assert str(w.cell(row=r, column=2).value).startswith("="), (
        "el ingreso volvió a bajar como número: mover una noche no movería nada")


@pytest.mark.parametrize("etiqueta", [
    "Room nights (generan ingreso)", "Room nights totales (incl. cortesía)",
    "TOTAL INGRESOS", "ADR", "% Ocupación", "RevPAR"])
def test_todo_el_cuadro_de_totales_es_formula(hoja, etiqueta):
    r = _fila(hoja, etiqueta)
    for col in (2, 14):                     # enero y la columna del año
        assert str(hoja.cell(row=r, column=col).value).startswith("="), (
            f"«{etiqueta}» no es fórmula en la columna {col}")


def test_las_dos_entradas_son_numeros_editables(hoja):
    """Noches y tarifa se teclean: si fueran fórmula no habría qué cambiar."""
    r = _fila(hoja, "Agencias")
    assert hoja.cell(row=r + 1, column=2).value == 100     # noches
    assert hoja.cell(row=r + 2, column=2).value == 600     # tarifa
    assert hoja.cell(row=r + 1, column=2).font.color.rgb.endswith("0000FF"), (
        "las celdas que se teclean van en azul")


def test_la_cortesia_no_cobra_y_es_por_formula(hoja):
    """⚠️ Cero por FÓRMULA, no por celda vacía.

    Vacía invita a escribir una tarifa, y el archivo empezaría a cobrar lo que
    el sistema regala — sin error y con el total cuadrando consigo mismo.
    """
    r = _fila(hoja, "CPL | Uso casa | Canjes")
    assert hoja.cell(row=r + 2, column=2).value == "—", (
        "la cortesía no debe tener una tarifa editable")
    assert hoja.cell(row=r + 3, column=2).value == "=0"


def test_la_cortesia_queda_fuera_del_ADR_y_dentro_de_la_ocupacion(hoja):
    """La regla del sistema, metida en las fórmulas del archivo."""
    r_cpl = _fila(hoja, "CPL | Uso casa | Canjes") + 1
    cobran = hoja.cell(row=_fila(hoja, "Room nights (generan ingreso)"),
                       column=2).value
    todas = hoja.cell(row=_fila(hoja, "Room nights totales (incl. cortesía)"),
                      column=2).value
    assert f"B{r_cpl}" not in cobran, "la cortesía entró al denominador del ADR"
    assert f"B{r_cpl}" in todas, "la cortesía salió de la ocupación"


def test_el_total_del_anio_divide_no_promedia(hoja):
    """⚠️ Un promedio de los doce ADR no es el ADR del año.

    Con enero a 100 noches y febrero a 10, promediar $600 y $300 da $450 y el
    número correcto es $572,73. El archivo tiene que DIVIDIR el ingreso del año
    entre las noches del año.
    """
    r = _fila(hoja, "Agencias") + 2         # la tarifa promedio
    f = str(hoja.cell(row=r, column=14).value)
    assert "/" in f and "AVERAGE" not in f.upper(), (
        f"la tarifa del año se está promediando: {f}")
    esperado = (100 * 600 + 10 * 300) / 110
    assert round(esperado, 2) == 572.73     # el número que tiene que dar


def test_el_adr_del_anio_tambien_divide(hoja):
    f = str(hoja.cell(row=_fila(hoja, "ADR"), column=14).value)
    assert "/" in f and "AVERAGE" not in f.upper()


def test_el_control_compara_contra_el_sistema(hoja):
    """El termómetro: cuánto se aparta el archivo del presupuesto cargado."""
    r = _fila(hoja, "Ingreso del sistema al bajar el archivo")
    assert hoja.cell(row=r, column=14).value == 70000
    assert str(hoja.cell(row=r + 1, column=14).value).startswith("=")


def test_sin_ingreso_del_sistema_no_se_dibuja_el_control():
    """Un control contra un número que no se pasó mentiría en silencio."""
    datos = construir_modelo(
        hotel="H", escenario="E", anio=2027, segmentos=SEGMENTOS,
        entradas=ENTRADAS, disponibles=DISP)
    w = load_workbook(io.BytesIO(datos))["Channel Rooms"]
    etiquetas = {str(w.cell(row=r, column=1).value or "").strip()
                 for r in range(1, w.max_row + 1)}
    assert "Ingreso del sistema al bajar el archivo" not in etiquetas


def test_el_objetivo_arranca_igual_al_modelo(hoja):
    """Si arrancara en blanco habría que retranscribir doce meses antes de
    poder comparar nada."""
    r = _fila(hoja, "% Ocupación objetivo")
    assert str(hoja.cell(row=r, column=2).value).startswith("="), (
        "el objetivo tiene que arrancar apuntando al modelo")


def test_el_objetivo_no_toca_el_modelo(hoja):
    """Las noches del modelo no pueden salir de la ocupación objetivo: si lo
    hicieran, dos celdas dirían cuántas noches hay y nadie sabría cuál manda."""
    r_obj = _fila(hoja, "% Ocupación objetivo")
    r_noches = _fila(hoja, "Agencias") + 1
    assert not str(hoja.cell(row=r_noches, column=2).value).startswith("="), (
        "las noches del modelo se volvieron derivadas del objetivo")
    assert r_obj > r_noches
