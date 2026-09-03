# -*- coding: utf-8 -*-
"""Las cuentas de reparto son las mismas en los dos caminos del motor.

**Cómo apareció (2026-08-14).** Armando la apertura de ingreso por departamento,
la Cafetería salía con una venta de **−$71,556** y la Lavandería de **−$18,852**.
No eran ventas: son el crédito con el que un departamento de servicio interno se
vacía contra los que lo consumen.

Al mirarlo apareció que el motor tiene **dos caminos** que clasifican la misma
cuenta y no decían lo mismo:

* `account_mapping` (el mapeo por cuenta) sí conocía la `4901` y la mandaba a
  `OH_CAFETERIA`, que es lo correcto.
* `pl_engine.ALLOCATION_ACCOUNTS` **no la tenía**: solo `4900` y `4999`. Ahí la
  `4901` caía en la rama de «cualquier cosa que empiece con 4» y se sumaba como
  ingreso.

**No estaba causando daño, y eso es lo interesante.** La `4901` solo aparece en
el departamento `0220`, que ya se salta por `ACTUAL_EXCLUDED_DEPTS` — por un
motivo distinto y sin relación. O sea que lo único que evitaba un ingreso
fantasma de $71,556 era una exclusión puesta para otra cosa.

El día que la `4901` apareciera en otro departamento, o que alguien sacara el
`0220` de esa lista, la venta del año subía sola y en silencio. Verificado
después del arreglo: los seis escenarios con dato dan exactamente lo mismo que
antes.
"""
import io
import json
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SEED = RAIZ / "app" / "seed_data" / "mapping_pl.json"


def _cuentas_49_del_mapeo() -> set[str]:
    """Las 49xx que el mapeo de cuentas conoce. Son, por definición, las de
    reparto: no hay ingreso de verdad en ese rango."""
    datos = json.loads(SEED.read_text(encoding="utf-8"))
    return {str(r.get("account_code")) for r in datos["account_mapping"]
            if str(r.get("account_code", "")).startswith("49")}


def test_el_motor_conoce_todas_las_cuentas_de_reparto_del_mapeo():
    """La regla que faltaba: si el mapeo la trata como reparto, el motor también.

    Esta es la prueba que habría atajado lo de la 4901 el día que se cargó.
    """
    from app.engine.pl_engine import ALLOCATION_ACCOUNTS
    faltan = _cuentas_49_del_mapeo() - set(ALLOCATION_ACCOUNTS)
    assert not faltan, (
        f"El mapeo trata como reparto {sorted(faltan)} y `ALLOCATION_ACCOUNTS` no "
        "las conoce. En el camino que arma el P&L de actuales, esas cuentas caen "
        "en la rama de «empieza con 4» y se suman como INGRESO."
    )


def test_la_4901_esta_declarada():
    """El caso concreto, para que el arreglo no se deshaga sin que nadie note."""
    from app.engine.pl_engine import ALLOCATION_ACCOUNTS
    assert "4901" in ALLOCATION_ACCOUNTS


def test_ninguna_cuenta_de_reparto_se_lee_como_ingreso():
    """`revenue_line_for_account` es la que decide si una 4xxx es venta."""
    from app.engine.pl_engine import ALLOCATION_ACCOUNTS, revenue_line_for_account
    for c in ALLOCATION_ACCOUNTS:
        assert revenue_line_for_account(c) is None, (
            f"la cuenta de reparto {c} se estaria leyendo como ingreso"
        )


def test_la_apertura_de_ingreso_excluye_las_mismas():
    """El reporte de cierre de mes tiene su propia lista. Si se separan, la
    pantalla y el P&L empiezan a contar distinto — que es como empezo todo."""
    src = io.open(RAIZ / "app" / "api" / "gasto_por_clase_api.py", encoding="utf-8").read()
    m = re.search(r"CUENTAS_DE_REPARTO = \{([^}]*)\}", src)
    assert m, "el reporte perdio su lista de cuentas de reparto"
    del_reporte = {x.strip().strip('"\'') for x in m.group(1).split(",") if x.strip()}
    from app.engine.pl_engine import ALLOCATION_ACCOUNTS
    assert del_reporte == set(ALLOCATION_ACCOUNTS), (
        f"el reporte excluye {sorted(del_reporte)} y el motor {sorted(ALLOCATION_ACCOUNTS)}. "
        "Tienen que ser la misma lista: si no, el total por departamento deja de "
        "amarrar con TOTAL_REVENUES."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Fusión de la lavandería en la apertura de INGRESO (owner, 2026-08-14).
#
# El 0162 factura y el 0161 lleva el gasto y lo reparte. Pero el ingreso venía
# cargado en los dos según el año y la versión: se movió el dato donde se pudo
# —los escenarios en borrador— y los cuatro enllavados no se pueden tocar sin
# abrir una foto histórica.
#
# Fusionarlos en la VISTA resuelve las dos cosas: una sola fila de venta de
# lavandería en todas las versiones y todos los años, sin importar cómo quedó
# cargada. Verificado contra producción en los seis escenarios con dato: el 0161
# queda en cero y el 0162 se lleva todo.
# ─────────────────────────────────────────────────────────────────────────────

def test_la_lavanderia_se_fusiona_solo_en_ingreso():
    from app.api.gasto_por_clase_api import FUSION_INGRESO
    assert FUSION_INGRESO == {"0161": "0162"}, (
        "cambió la fusión de departamentos de ingreso sin actualizar esta prueba"
    )


def test_los_pozos_de_reparto_no_salen_en_el_gasto():
    """0220, 0161 y 0162 no son departamentos que el dueño mire por separado:
    su costo ya viaja dentro de los que los consumen."""
    from app.api.gasto_por_clase_api import EXCLUIR_DE_GASTO
    assert EXCLUIR_DE_GASTO == {"0220", "0161", "0162"}


def test_el_INGRESO_de_la_lavanderia_no_se_pierde():
    """La primera version cortaba antes de mirar la clase de cuenta y se llevaba
    puesto el INGRESO de la lavanderia: la venta del año bajaba 3,450 sin que
    nada lo dijera.

    ⚠️ Desde el 2026-09-03 los departamentos de reparto ya NO se excluyen del
    gasto —se cuentan y su credito 49xx los netea, ver
    `test_el_SOBRANTE_del_reparto_se_cuenta`—, asi que la vieja linea de filtro
    no existe. Lo que se sigue exigiendo es lo mismo: que un 4xxx que no sea de
    reparto entre como ingreso.
    """
    src = io.open(RAIZ / "app" / "api" / "gasto_por_clase_api.py", encoding="utf-8").read()
    assert 'cuenta.startswith("4") and detalle is not None' in src
    assert "cuenta not in CUENTAS_DE_REPARTO" in src, (
        "el ingreso dejo de distinguir las cuentas de reparto: o se pierde la "
        "venta de lavanderia, o el credito de distribucion entra como venta")


def test_el_SOBRANTE_del_reparto_se_cuenta():
    """⚠️ Lo que este cuadro perdia, medido contra el P&L en produccion:

        ACTUAL 2026    may 2.090,32 · jun 4.146,54 · jul 1.121,36
        BUDGET 2026    entre 1.361 y 1.493, TODOS los meses

    El costo de lavanderia esta en el mayor, pero el departamento se descartaba
    entero porque «se reparte». Y un ACTUAL no se reparte —se sube como vino—,
    asi que no habia nada que lo devolviera. El motor no lo descarta: lo que no
    alcanzo a repartirse queda en overhead (`OH_LAUNDRY`), que es la regla del
    owner del 2026-08-28.

    La plata que faltaba iba contra el gasto, o sea que el mes se veia MEJOR de
    lo que fue.
    """
    src = io.open(RAIZ / "app" / "api" / "gasto_por_clase_api.py", encoding="utf-8").read()
    assert "if cuenta in CUENTAS_DE_REPARTO:" in src, (
        "la rama del mayor dejo de netear con el credito de distribucion")
    assert "alloc_by_dept" in src, (
        "la rama del checkbook dejo de sumar los asientos de reparto")


def test_un_mes_CERRADO_del_forecast_saca_el_gasto_del_ACTUAL():
    """⚠️ El tercer descuadre, y el mas grande.

    Este endpoint leia siempre el mayor del PROPIO escenario, y un forecast no
    tiene mayor: caia siempre al checkbook. En el FORECAST Working 2026 con
    corte en julio:

        mar/abr/may -> 0 en el cuadro contra 12.189 / 25.851 / 56.027 en el P&L
        jun/jul     -> 42.658 y 12.370 DE MAS, mostrando lo presupuestado
                       sobre meses que ya cerraron

    La mezcla es la misma que hace `compute_pl_month`: hasta `actuals_through`
    manda el ACTUAL enlazado. Rehacerla con otro criterio es como el resumen y
    el P&L terminan contando dos historias.
    """
    src = io.open(RAIZ / "app" / "api" / "gasto_por_clase_api.py", encoding="utf-8").read()
    assert "linked_actual_scenario" in src
    assert 'escenario.type == "FORECAST" and m <= (escenario.actuals_through or 0)' in src


def test_la_fusion_solo_se_aplica_al_ingreso():
    """En gasto los tres estan excluidos, asi que no hay nada que fusionar: si
    la fusion apareciera ahi, seria señal de que alguien los volvio a mostrar."""
    src = io.open(RAIZ / "app" / "api" / "gasto_por_clase_api.py", encoding="utf-8").read()
    lineas = src.splitlines()
    idx = [i for i, l in enumerate(lineas) if "FUSION_INGRESO.get" in l]
    assert len(idx) == 1, f"la fusion se aplica en {len(idx)} lugares"
    # Se mira el BLOQUE, no la linea: la fusion dejo de caber en un renglon
    # cuando el ingreso paso a indexarse por linea (2026-09-02), y fijar el
    # texto exacto habria hecho fallar esto sin que la regla se moviera.
    bloque = chr(10).join(lineas[max(0, idx[0] - 6): idx[0] + 3])
    assert '"revenue"' in bloque, (
        "la fusion 0161->0162 salio del bloque de INGRESO: si se aplicara al "
        "gasto, estaria mostrando departamentos que son pozos de reparto")
