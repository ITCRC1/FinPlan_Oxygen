# -*- coding: utf-8 -*-
"""EL ORIGEN DEL REPARTO MUESTRA SU RESIDUO: NI CERO NI TODO.

Cafetería (0220) y Lavandería (0161) reparten su gasto a los departamentos que
usan el servicio. El P&L por Departamento los sacaba **enteros** de los totales
—`ALLOC_EXCL_PAYROLL/OPEX/COST`— para no contarlos dos veces. Eso rompe en dos
casos, y los dos pierden plata sin dar error:

 1. **Sin reparto cargado** la exclusión no mueve el gasto de lugar: lo borra.
    Medido en el Working 2026 de Amarena el 2026-08-27, la planilla de
    Lavandería —US$9.838,52— desaparecía del reporte y no reaparecía en ningún
    departamento. La planilla del reporte daba 252.694,15 contra los 262.532,67
    del auxiliar. Se destapó al poner las sumatorias por columna: hasta entonces
    el número no estaba en pantalla y no había contra qué cuadrarlo.

 2. **Con reparto parcial**, el sobrante también se perdía.

Owner, 2026-08-27: «DEBE APARECER COMO OVERHEAD AL MENOS» · «cuando ya tengamos
lavandería fija, se hará el allocation pero CUALQUIER SALDO NO ALOCADO debe
salir como overhead».

La regla que queda es una sola, sin banderas: al departamento se le RESTA lo que
efectivamente repartió, por clase. Sin repartos la resta es cero y el gasto sale
completo; con un reparto total el residuo es cero y la fila desaparece sola.
"""
from __future__ import annotations

import inspect

from app.engine.pl_engine import (OPERATING_GROUP_ORDER, OVERHEAD_GROUP_ORDER,
                                  group_for_dept)
from app.importers.gl_detail_importer import (ALLOC_EXCL_COST, ALLOC_EXCL_OPEX,
                                              ALLOC_EXCL_PAYROLL)


def _fuente() -> str:
    from app.api.scenarios_api import pl_by_dept

    return inspect.getsource(pl_by_dept)


def test_ya_no_se_excluye_el_departamento_entero():
    """La exclusión en bloque es lo que borraba el gasto. Si vuelve, vuelve el
    agujero: el `continue` dentro del bucle no deja rastro de lo que sacó."""
    fuente = _fuente()
    for const in ("ALLOC_EXCL_OPEX", "ALLOC_EXCL_COST", "ALLOC_EXCL_PAYROLL"):
        assert f"in {const}:" not in fuente, (
            f"volvió a saltarse el departamento entero con {const}")
        assert f"e.dept_code in {const}" not in fuente


def test_se_resta_lo_repartido_por_clase():
    """6025 es planilla, 7310/7685 opex y 5301 costo: restar todo de una sola
    columna dejaría una en negativo y otra intacta."""
    fuente = _fuente()
    assert '_CLASE_A_CAMPO = {"5": "cost", "6": "payroll", "7": "opex"}' in fuente
    assert "-= monto" in fuente, "no se resta lo repartido"


def test_la_resta_va_despues_de_acumular():
    """El residuo es «lo que tenía menos lo que repartió». Restando antes, el
    gasto se sumaría después y la resta no habría servido de nada."""
    fuente = _fuente()
    assert fuente.index('["payroll"] += float(total_entry(e))') < \
        fuente.index("_CLASE_A_CAMPO[clase]] -= monto")


def test_la_resta_la_manda_el_reparto_y_no_la_declaracion():
    """Se le resta a quien REPARTIÓ, no a quien está declarado que reparte.

    Hasta el 2026-11-20 la resta exigía que el origen estuviera en
    `DEPTOS_DE_REPARTO`, que declara `{"0161": {"6","7"}}` — sin la clase 5. Y
    el motor sí reparte el 5301 de lavandería: en el Budget 2027 de Oxygen
    $601,53 salían de 0161 y llegaban al destino sin que a 0161 se le restara
    nada, así que ese gasto quedaba contado dos veces.

    Las filas de `allocation_entries` son el registro de la plata que se movió;
    la declaración es una intención. Para restar manda el registro.
    """
    fuente = _fuente()
    assert "deptos_que_reparten" not in fuente, (
        "volvió a condicionar la resta a la declaración")
    # Los nombres aparecen en los comentarios —que cuentan esta historia—, así
    # que no alcanza con buscarlos: lo que no puede volver es que DECIDAN.
    for const in ("ALLOC_EXCL_COST", "ALLOC_EXCL_PAYROLL", "ALLOC_EXCL_OPEX"):
        assert f"in {const}" not in fuente, f"{const} volvió a condicionar"
        assert f"{const})" not in fuente, f"{const} volvió a usarse"
    assert "if monto:" in fuente, "la resta tiene que ser incondicional"


def test_el_reparto_que_llega_es_gasto_del_que_lo_recibe():
    """`total_exp` tiene que incluir `alloc`. Si no, se resta en una punta y no
    se suma en la otra.

    Medido en el Budget 2027 de Oxygen el 2026-11-20: el GOP por departamento
    daba $1.113.767,01 contra los $1.074.303,40 del P&L oficial —$39.463,61
    arriba, exactamente lo repartido que sí se restaba al origen—. Nada fallaba:
    cada fila cuadraba consigo misma y el neto de los repartos seguía dando
    cero. Mientras 0161 estuvo en cero la diferencia era cero.
    """
    fuente = _fuente()
    assert 'total_exp = d["payroll"] + operating + d["alloc"]' in fuente, (
        "el reparto que llega volvió a quedarse fuera del gasto")


def test_la_4999_no_se_resta():
    """Es el espejo del reparto —el crédito que vuelve al origen—. Restarla
    además de las cuentas de clase sería restar dos veces, y el departamento
    quedaría en negativo por el monto repartido."""
    fuente = _fuente()
    assert 'cuenta == "4999"' in fuente
    i = fuente.index('cuenta == "4999"')
    assert "continue" in fuente[i:i + 120]


def test_el_reparto_se_mide_POR_MES():
    """Un reparto de junio no puede achicar el gasto de enero. En la vista de un
    mes suelto eso sería un agujero del tamaño del mes entero."""
    fuente = _fuente()
    i = fuente.index("repartido: dict[tuple[str, str], float] = {}")
    assert "e.month not in months" in fuente[i:i + 400]


def test_el_origen_se_lee_del_departamento_ORIGEN():
    """`target_dept` es a dónde LLEGA el reparto; lo que se achica es de dónde
    SALE. Restarle al destino sería el error exactamente al revés."""
    fuente = _fuente()
    i = fuente.index("repartido: dict[tuple[str, str], float] = {}")
    trozo = fuente[i:i + 500]
    assert "e.source_dept" in trozo
    assert "e.target_dept" not in trozo


def test_la_lavanderia_cae_en_el_bloque_de_overhead():
    """Lo que pidió el owner. Si `LAUNDRY_OPS` estuviera en la lista operativa,
    aparecería arriba, entre los que generan ingresos, con un GOP negativo del
    tamaño de su planilla."""
    grupo = group_for_dept("0161")
    assert grupo == "LAUNDRY_OPS"
    assert grupo in OVERHEAD_GROUP_ORDER
    assert grupo not in OPERATING_GROUP_ORDER


def test_la_cafeteria_sigue_la_misma_regla():
    """No es un parche para Lavandería: Cafetería (0220) pasa por lo mismo, y su
    grupo también vive en overhead."""
    assert "0220" in ALLOC_EXCL_PAYROLL
    assert "0220" in ALLOC_EXCL_OPEX
    assert "0220" in ALLOC_EXCL_COST
    assert group_for_dept("0220") in OVERHEAD_GROUP_ORDER


def test_la_lavanderia_no_reparte_su_costo_de_ventas():
    """0161 es SPLIT: la lavandería interna (6xxx y 7xxx) se reparte, pero el
    Laundry Services que se le vende al huésped es OPERATIVO y su costo se queda
    con su ingreso. Por eso 0161 no está en `ALLOC_EXCL_COST`.

    ⚠️ **La declaración y el motor no coinciden, y gana el motor.** Medido en
    producción el 2026-11-20, el Budget 2027 de Oxygen tiene una fila de reparto
    con origen 0161 y cuenta 5301 por $601,53: el motor SÍ repartió clase 5 de
    lavandería, contra lo que dice esta regla. Mientras el P&L por Departamento
    se guiaba por la declaración, ese costo se restaba en ninguna parte y se
    contaba dos veces.

    El reporte ahora sigue las filas de `allocation_entries` —la plata que se
    movió— y no esta lista. Queda pendiente decidir lo otro: si la regla es la
    correcta, el que tiene que dejar de repartir clase 5 es el motor."""
    assert "0161" in ALLOC_EXCL_PAYROLL
    assert "0161" in ALLOC_EXCL_OPEX
    assert "0161" not in ALLOC_EXCL_COST


def test_el_residuo_es_la_resta_y_nada_mas():
    """La aritmética de la regla, sin base de datos: gasto − repartido, y cuando
    el reparto cubre todo el residuo es cero y la fila se cae sola (el reporte
    salta los departamentos cuyo total es cero)."""
    gasto, repartido_total, repartido_parcial = 9838.52, 9838.52, 4000.00
    assert round(gasto - repartido_total, 2) == 0.00
    assert round(gasto - repartido_parcial, 2) == 5838.52
    assert round(gasto - 0.0, 2) == 9838.52
