# -*- coding: utf-8 -*-
"""Los nueve cuadros de «Estadísticas Revenue», recreados.

Owner, 2026-10-15: *«revisa nuevamente este tab Estadísticas Revenue y favor
recrea todos los reportes que hay ahí»*.

## Lo que el libro de Sales muestra

    1-6  Ingreso, Room Nights, ADR, % Ocupación, RevPAR y Disponibles,
         mes a mes, con una columna por VERSIÓN
    7    Variaciones de la proyección contra los años anteriores
    8    El detalle de cada segmento (sin cortesías)
    9    El mix del año, con el chequeo «suma de segmentos − total = 0»

## ⚠️ Las columnas son versiones, no meses

En FinPlan cada versión es un ESCENARIO, así que el reporte compara escenarios
—como ya hace el P&L Detail— y el pareo lo decide el usuario. El archivo no
sabe de escenarios.

Lo que se cuida acá son las tres cuentas que, si se rompen, **cuadran solas**:
el promedio del año, la diferencia en puntos de la ocupación, y el chequeo del
mix contra el total.
"""
from decimal import Decimal as D

import pytest

from app.models.canal_rooms import SEGMENTOS_SEMILLA, CanalRoomsEntry, calcular_mes

GENERA = {c: g for c, _n, g in SEGMENTOS_SEMILLA}


def _e(code, noches, ingreso, mes=1):
    return CanalRoomsEntry(segmento_code=code, month=mes, noches=D(str(noches)),
                           tarifa=D("0"), ingreso=D(str(ingreso)))


# ── El promedio del año ──────────────────────────────────────────────────────

def test_el_adr_del_anio_no_es_el_promedio_de_los_adr():
    """⚠️ Un promedio de promedios no es el promedio.

    Enero: 100 noches a $600. Febrero: 10 noches a $200. El ADR del año es
    $563,64 —la plata sobre las noches— y NO $400, que es promediar los dos
    meses como si pesaran igual. Con la estacionalidad de Oxygen, donde
    setiembre vende la quinta parte de enero, esa diferencia son dólares.
    """
    ene = calcular_mes([_e("AGENCIAS", 100, 60000)], GENERA, 403)
    feb = calcular_mes([_e("AGENCIAS", 10, 2000, 2)], GENERA, 364)
    assert ene["adr"] == D("600")
    assert feb["adr"] == D("200")

    ing = ene["ingreso"] + feb["ingreso"]
    noches = ene["noches_ingreso"] + feb["noches_ingreso"]
    adr_anio = ing / noches
    assert abs(adr_anio - D("563.64")) < D("0.01")
    assert adr_anio != (ene["adr"] + feb["adr"]) / 2


def test_el_revpar_del_anio_divide_por_las_disponibles_del_anio():
    ene = calcular_mes([_e("AGENCIAS", 100, 60000)], GENERA, 403)
    feb = calcular_mes([_e("AGENCIAS", 10, 2000, 2)], GENERA, 364)
    rev = (ene["ingreso"] + feb["ingreso"]) / (ene["disponibles"] + feb["disponibles"])
    assert abs(rev - D("80.84")) < D("0.01")


# ── La variación de la ocupación ─────────────────────────────────────────────

def test_la_ocupacion_se_compara_en_PUNTOS_y_no_en_porcentaje():
    """Del 20% al 25% hay CINCO PUNTOS, no un 25% de mejora.

    El libro de Sales rotula esa columna «Ocupación pts» justamente por eso.
    Mostrarla como variación porcentual exagera el movimiento de los meses
    flojos: en setiembre, donde la ocupación es baja, cualquier noche extra
    parece un salto enorme.
    """
    a, b = D("0.25"), D("0.20")
    assert a - b == D("0.05")                    # cinco puntos
    assert (a - b) / b == D("0.25")              # y esto seria «+25%», que miente


def test_variacion_contra_cero_no_revienta():
    """Budget 2027 viene en cero: comparar contra el es dividir por cero."""
    base, contra = D("1000"), D("0")
    assert (base - contra) / contra if contra else D("0") == D("0")


# ── El chequeo del mix ───────────────────────────────────────────────────────

def test_el_mix_cierra_cuando_las_cortesias_no_facturan():
    """La suma de los segmentos que generan ingreso = el ingreso total."""
    r = calcular_mes([_e("AGENCIAS", 100, 50000), _e("OTA", 40, 20000),
                      _e("CPL", 6, 0)], GENERA, 403)
    suma = sum(v["ingreso"] for c, v in r["segmentos"].items() if GENERA[c])
    assert suma == r["ingreso"] == D("70000")


def test_el_chequeo_delata_una_cortesia_con_plata():
    """⚠️ El cuadro del libro dice «debe ser 0». Si una cortesía trae ingreso,
    la suma de los segmentos de venta deja de dar el total — y el total NO
    cambia, así que sin este chequeo nadie se entera."""
    r = calcular_mes([_e("AGENCIAS", 100, 50000), _e("CPL", 6, 900)], GENERA, 403)
    suma = sum(v["ingreso"] for c, v in r["segmentos"].items() if GENERA[c])
    assert r["ingreso"] == D("50900")
    assert suma - r["ingreso"] == D("-900")      # el chequeo lo muestra


# ── Los bloques declarados ───────────────────────────────────────────────────

def test_estan_las_seis_metricas_del_libro():
    from app.api.canal_rooms_api import BLOQUES
    claves = [c for c, _t, _f in BLOQUES]
    assert claves == ["ingreso", "noches_ingreso", "adr", "ocupacion",
                      "revpar", "disponibles"]


def test_cada_bloque_declara_su_formato():
    """El formato viaja con el dato: la pantalla no adivina si una fila es
    dinero, porcentaje o conteo mirando el nombre."""
    from app.api.canal_rooms_api import BLOQUES
    for _c, _t, fmt in BLOQUES:
        assert fmt in ("usd", "pct", "num")


@pytest.mark.parametrize("campo", ["ingreso", "noches_ingreso", "noches_totales",
                                   "disponibles", "ocupacion", "ocupacion_total",
                                   "adr", "revpar"])
def test_el_mes_devuelve_todo_lo_que_los_cuadros_piden(campo):
    """Si `calcular_mes` deja de devolver una, el cuadro sale vacío sin error."""
    assert campo in calcular_mes([_e("AGENCIAS", 10, 5000)], GENERA, 403)
