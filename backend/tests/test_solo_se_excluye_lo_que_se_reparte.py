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
    assert '_CLASE_A_CAMPO = {"5": ("cost", ALLOC_EXCL_COST),' in fuente
    assert '"6": ("payroll", ALLOC_EXCL_PAYROLL)' in fuente
    assert '"7": ("opex", ALLOC_EXCL_OPEX)' in fuente
    assert "[campo] -= monto" in fuente, "no se resta lo repartido"


def test_la_resta_va_despues_de_acumular():
    """El residuo es «lo que tenía menos lo que repartió». Restando antes, el
    gasto se sumaría después y la resta no habría servido de nada."""
    fuente = _fuente()
    assert fuente.index('["payroll"] += float(total_entry(e))') < \
        fuente.index("[campo] -= monto")


def test_la_resta_solo_toca_a_los_departamentos_que_reparten():
    """Un reparto cuyo origen no está en la lista no puede achicar a nadie: sería
    una resta contra un departamento que nunca fue de allocation."""
    fuente = _fuente()
    assert "if origen in deptos_que_reparten and monto:" in fuente


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
    con su ingreso. Por eso 0161 no está en `ALLOC_EXCL_COST`, y restarle clase
    5 le quitaría un costo que nunca repartió."""
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
