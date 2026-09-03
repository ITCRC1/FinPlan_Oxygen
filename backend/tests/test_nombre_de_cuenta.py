# -*- coding: utf-8 -*-
"""El rótulo de una cuenta: que exista, y que quepa.

Owner, 2026-09-03, sobre «Property x Cuenta»: *«sin nombre el GL y el texto se
sobrepone en los datos»*. Son dos defectos en el mismo cuadro.
"""
from pathlib import Path

from app.nombres_cuenta import limpiar_nombre, nombre_de_cuenta

FRONT = Path(__file__).resolve().parents[2] / "frontend"


def test_de_todas_las_variantes_queda_UNA():
    """`account_name_example` es una columna de EJEMPLOS y fue acumulando cada
    variante vista en el mayor. Sirve para rastrear una regla; como rótulo son
    sesenta caracteres donde caben veinte."""
    casos = {
        "DEPRECIATION1 | DEPRECIATION2 | DEPRECIATION4 | DEPRECIATION": "DEPRECIATION",
        "RENT1 | RENT": "RENT",
        "FINES AND OTHER NON-DEDUCTIBLE EXPENSES1 | FINES AND OTHER "
        "NON-DEDUCTIBLE EXPENSES": "FINES AND OTHER NON-DEDUCTIBLE EXPENSES",
        "EXCHANGE GAIN/LOSSES1 | EXCHANGE GAIN/LOSSES": "EXCHANGE GAIN/LOSSES",
    }
    for crudo, esperado in casos.items():
        assert limpiar_nombre(crudo) == esperado, crudo


def test_no_se_elige_el_PRIMERO_sino_el_que_esta_limpio():
    """⚠️ El primero suele ser justo el que tiene el sufijo del mayor
    (`DEPRECIATION1`); el bueno es el que no lo tiene."""
    assert limpiar_nombre("DEPRECIATION1 | DEPRECIATION") == "DEPRECIATION"
    assert limpiar_nombre("DEPRECIATION | DEPRECIATION1") == "DEPRECIATION"


def test_si_NINGUNO_esta_limpio_se_le_quita_el_numero():
    """El caso real del 8015: las cinco variantes tienen sufijo."""
    crudo = ("PROPERTY INSURANCE1 | PROPERTY INSURANCE2 | PROPERTY INSURANCE3 "
             "| PROPERTY INSURANCE4 | PROPERTY INSURANCE5")
    assert limpiar_nombre(crudo) == "PROPERTY INSURANCE"
    assert limpiar_nombre("OWNERS FEE1") == "OWNERS FEE"


def test_no_le_come_los_numeros_a_un_nombre_que_es_asi():
    """Sólo se quita el sufijo cuando NO hay ninguna variante limpia."""
    assert limpiar_nombre("MGMT FEE 3 | MGMT FEE") == "MGMT FEE"
    assert limpiar_nombre("CAPITAL RESERVE") == "CAPITAL RESERVE"


def test_nunca_devuelve_vacio():
    """Una fila con monto y sin nombre obliga a buscar el código en otro lado."""
    assert nombre_de_cuenta("8020") == "Cuenta 8020"
    assert nombre_de_cuenta("6023") == "Vacation Provision"   # concepto de planilla
    assert nombre_de_cuenta("8000", catalogo={"8000": "RENT1 | RENT"}) == "RENT"


def test_busca_el_codigo_aunque_el_DEPARTAMENTO_no_calce():
    """⚠️ `nonop_entries` no guarda departamento, y su `account_name` está
    vacío en las 18 filas de producción. Sin esta búsqueda por código suelto,
    el 8000 y el 8020 salían como número pelado."""
    cat = {("0250", "8020"): "CAPITAL RESERVE"}
    assert nombre_de_cuenta("8020", catalogo=cat, dept="") == "CAPITAL RESERVE"


def test_el_cuadro_de_propiedad_tiene_respaldo_de_CATALOGO():
    src = (Path(__file__).resolve().parents[1]
           / "app/api/gasto_por_clase_api.py").read_text(encoding="utf-8")
    assert "AccountMapping" in src and "limpiar_nombre" in src


def test_la_auditoria_usa_el_MISMO_limpiador():
    """Dos limpiadores es cómo la misma cuenta termina llamándose distinto en
    dos pantallas."""
    src = (Path(__file__).resolve().parents[1]
           / "app/api/auditoria_api.py").read_text(encoding="utf-8")
    assert "from app.nombres_cuenta import limpiar_nombre" in src


def test_el_rotulo_NO_puede_salirse_de_su_celda():
    """⚠️ La tabla es `table-layout: fixed`, y ahí el texto que no entra no se
    recorta solo: se dibuja ENCIMA de la columna de al lado. Que es exactamente
    lo que el owner vio.
    """
    src = (FRONT / "app/month-end/pl/page.tsx").read_text(encoding="utf-8")
    i = src.index('{k === null ? "TOTAL" : rotulo(k)}')
    # ⚠️ La ventana creció al 2026-09-03: la celda pasó a ser clicable —abre el
    # detalle por cuenta— y el `onClick` empujó el estilo hacia arriba.
    celda = src[max(0, i - 1100):i]
    assert "overflowWrap" in celda, (
        "la celda del rótulo volvió a no contener su texto: en una tabla fija "
        "se monta sobre los montos")
    assert "title={k === null ? undefined" in celda
