# -*- coding: utf-8 -*-
"""El motor del tarifario reproduce el Excel del owner, celda por celda.

Los números de acá salen de `Presupuesto_Ojochal_2027_Modelo 1_3`, pestaña
`Origen Tarifa Rack`, escenario **Proyección 2027**. No son inventados ni
redondeados: si el motor no da exactamente eso, el motor está mal.

`MODELO_ROOMS_POR_CANAL.md` §10.2: *«Verificar que `derivar()` reproduce una
celda real»*. Acá se verifican los nueve pasos, porque cada uno alimenta al
siguiente y un error en el 3 aparece recién en el 8, disfrazado de otra cosa.

Las cinco filas de CONTROL del libro —las que deben dar cero— son pruebas
propias: son el mecanismo que el owner construyó para no confiar en el
resultado, y sería una lástima perderlo al pasar a código.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from app.engine.rack_tarifa import (derivar_mes, dias_por_temporada,
                                    dias_sin_temporada, disponibles_mes,
                                    ingreso_rack, rac_ponderado, rac_villa_mes,
                                    tarifa_del_segmento)


# ── El libro, tal cual ──────────────────────────────────────────────────────
@dataclass
class _Villa:
    villa: str
    unidades: int
    rac_pico: Decimal
    rac_alta: Decimal
    rac_verde: Decimal


@dataclass
class _Temp:
    temporada: str
    desde: date
    hasta: date


#: `Origen Tarifa Rack` filas 7–13. Once unidades en siete villas.
VILLAS = [
    _Villa("Estudio Violeta", 3, Decimal("260"), Decimal("220"), Decimal("200")),
    _Villa("Estudio Naranja", 3, Decimal("260"), Decimal("220"), Decimal("200")),
    _Villa("Villa Amarilla", 1, Decimal("286"), Decimal("240"), Decimal("230")),
    _Villa("Villa Verde", 1, Decimal("325"), Decimal("280"), Decimal("230")),
    _Villa("Villa Fucsia", 1, Decimal("325"), Decimal("280"), Decimal("230")),
    _Villa("Villa Turquesa", 1, Decimal("325"), Decimal("280"), Decimal("230")),
    _Villa("Villa Azul", 1, Decimal("325"), Decimal("280"), Decimal("230")),
]

#: Filas 18–21. «Pico» son DOS rangos: el arranque y el cierre del año.
TEMPORADAS = [
    _Temp("PICO", date(2027, 1, 1), date(2027, 1, 5)),
    _Temp("ALTA", date(2027, 1, 6), date(2027, 4, 30)),
    _Temp("VERDE", date(2027, 5, 1), date(2027, 12, 19)),
    _Temp("PICO", date(2027, 12, 20), date(2027, 12, 31)),
]

#: Fila 54–60: las noches digitadas de la Proyección 2027.
NOCHES_ENERO = {
    "AGENCIAS": 25, "DIRECT_WEB": 150, "CRC_DIRECT": 8, "DIRECT_PHONE": 0,
    "DIRECT_GROUPS": 0, "LONG_TERM": 30, "OTA": 25,
}
#: `Resumen Manual` B67:B73 — (% comisión, tarifa propia).
COMISIONES = {
    "AGENCIAS": (Decimal("0.25"), False),
    "DIRECT_WEB": (Decimal("0.10"), False),
    "CRC_DIRECT": (Decimal("0.25"), False),
    "DIRECT_PHONE": (Decimal("0.10"), False),
    "DIRECT_GROUPS": (Decimal("0.15"), False),
    "LONG_TERM": (Decimal("0"), True),
    "OTA": (Decimal("0.25"), False),
}


# ── Paso 3 · los días de cada temporada ─────────────────────────────────────
@pytest.mark.parametrize("mes,pico,alta,verde", [
    (1, 5, 26, 0),      # enero: arranca en Pico y sigue en Alta
    (2, 0, 28, 0),
    (4, 0, 30, 0),      # abril cierra la Alta
    (5, 0, 0, 31),      # mayo abre la Verde
    (12, 12, 0, 19),    # diciembre se parte: Verde hasta el 19, Pico desde el 20
])
def test_dias_por_temporada(mes, pico, alta, verde):
    """Fila 29–31. Diciembre es el que importa: parte el mes en dos."""
    d = dias_por_temporada(2027, mes, TEMPORADAS)
    assert (d.get("PICO", 0), d.get("ALTA", 0), d.get("VERDE", 0)) == (pico, alta, verde)


def test_control_f32_ningun_dia_queda_sin_temporada():
    """El CONTROL de la fila 32, que en el libro da cero los doce meses.

    Un día sin temporada no tiene tarifa: el numerador del RAC no lo cuenta y
    el denominador sí, así que el RAC del mes sale diluido sin que nada avise.
    """
    huecos = {m: dias_sin_temporada(2027, m, TEMPORADAS) for m in range(1, 13)}
    assert not any(huecos.values()), f"meses con días sin tarifa: {huecos}"


def test_el_ano_entero_cuadra():
    """17 Pico + 115 Alta + 233 Verde = 365 (fila 29–31, columna O)."""
    tot = {"PICO": 0, "ALTA": 0, "VERDE": 0}
    for m in range(1, 13):
        for k, v in dias_por_temporada(2027, m, TEMPORADAS).items():
            tot[k] += v
    assert tot == {"PICO": 17, "ALTA": 115, "VERDE": 233}
    assert sum(tot.values()) == 365


# ── Paso 4 · el RAC del mes por villa ───────────────────────────────────────
@pytest.mark.parametrize("villa,mes,esperado", [
    ("Estudio Violeta", 1, "226.45"),    # (5×260 + 26×220) / 31
    ("Estudio Violeta", 12, "223.23"),   # (12×260 + 19×200) / 31
    ("Villa Amarilla", 1, "247.42"),
    ("Villa Verde", 1, "287.26"),
    ("Villa Verde", 5, "230.00"),        # mes entero en Verde: es su RAC Verde
])
def test_rac_villa_mes(villa, mes, esperado):
    """Fila 36–42 del libro."""
    v = next(x for x in VILLAS if x.villa == villa)
    assert rac_villa_mes(v, 2027, mes, TEMPORADAS).quantize(Decimal("0.01")) \
        == Decimal(esperado)


# ── Paso 5 · el RAC ponderado y las disponibles ─────────────────────────────
@pytest.mark.parametrize("mes,esperado", [
    (1, "250.47"), (2, "243.64"), (5, "213.64"), (12, "241.65"),
])
def test_rac_ponderado(mes, esperado):
    """Fila 47. Pondera por unidades de venta, no por habitaciones."""
    assert rac_ponderado(VILLAS, 2027, mes, TEMPORADAS).quantize(Decimal("0.01")) \
        == Decimal(esperado)


def test_disponibles_son_once_unidades():
    """Fila 48: 341 en enero y 4.015 en el año. Con 16 habitaciones darían
    496 y 5.840 — ese es justo el desencuentro que documenta la hoja
    `Comparativo Inventario`."""
    assert disponibles_mes(VILLAS, 2027, 1) == 341
    assert sum(disponibles_mes(VILLAS, 2027, m) for m in range(1, 13)) == 4015


# ── Pasos 7 y 8 · de las noches al ingreso ──────────────────────────────────
def test_ingreso_rack_enero():
    """Fila 66–73: noches × RAC ponderado, y su total."""
    rac = rac_ponderado(VILLAS, 2027, 1, TEMPORADAS)
    assert ingreso_rack(25, rac) == Decimal("6261.73")      # Agencias
    assert ingreso_rack(150, rac) == Decimal("37570.38")    # Direct web
    assert ingreso_rack(8, rac) == Decimal("2003.75")       # CRC direct


def test_tarifa_neta_por_segmento():
    """Paso 8: RAC × (1 − % comisión). Long term lleva la suya."""
    rac = rac_ponderado(VILLAS, 2027, 1, TEMPORADAS)
    assert tarifa_del_segmento(rac, Decimal("0.25")) == Decimal("187.85")
    assert tarifa_del_segmento(rac, Decimal("0.10")) == Decimal("225.42")
    assert tarifa_del_segmento(rac, Decimal("0"), Decimal("75"),
                               tarifa_propia=True) == Decimal("75")


def test_sin_comision_se_vende_a_rack_y_no_gratis():
    """Un segmento sin fila de comisión NO pone el ingreso en cero.

    Es la clase de error que cuadra consigo mismo: el total baja y nada avisa.
    """
    rac = rac_ponderado(VILLAS, 2027, 1, TEMPORADAS)
    assert tarifa_del_segmento(rac, None) == rac.quantize(Decimal("0.01"))


#: Enero de la Proyección 2027, segmento por segmento: (rack, neto).
#: `Origen Tarifa Rack` filas 66–72 y 78–84.
ENERO_LIBRO = {
    "AGENCIAS":      ("6261.73", "4696.30"),
    "DIRECT_WEB":   ("37570.38", "33813.34"),
    "CRC_DIRECT":    ("2003.75", "1502.82"),
    "DIRECT_PHONE":        ("0", "0"),
    "DIRECT_GROUPS":       ("0", "0"),
    "LONG_TERM":     ("2250.00", "2250.00"),
    "OTA":           ("6261.73", "4696.30"),
}


def test_cada_segmento_reproduce_el_libro():
    """Las SIETE filas de enero, rack y neto, al centavo.

    Es la prueba que de verdad decide: si cada fila sale bien, el modelo está
    bien. Comparar sólo el total dejaría pasar dos errores que se compensan.
    """
    r = derivar_mes(VILLAS, TEMPORADAS, COMISIONES, NOCHES_ENERO, 2027, 1,
                    tarifas_propias={"LONG_TERM": Decimal("75")})
    malos = []
    for code, (rack, neto) in ENERO_LIBRO.items():
        s = r["segmentos"][code]
        if s["ingreso_rack"] != Decimal(rack):
            malos.append(f"{code} rack: {s['ingreso_rack']} ≠ {rack}")
        if s["ingreso"] != Decimal(neto):
            malos.append(f"{code} neto: {s['ingreso']} ≠ {neto}")
    assert not malos, "filas que no reproducen el libro:\n  " + "\n  ".join(malos)
    assert r["disponibles"] == 341
    assert r["dias_sin_temporada"] == 0


def test_el_total_es_la_suma_de_sus_filas():
    """Y por eso queda a UN CENTAVO del total del libro, a propósito.

    Excel suma los productos SIN redondear y redondea al mostrar: su fila 73
    dice 54.347,60 y la suma de sus propias filas visibles da 54.347,59.

    Acá se elige que el total **sea la suma de sus filas**. Cuadrar contra el
    total del libro exigiría un total que no coincide con las filas que están
    arriba de él — que es exactamente el defecto que este repo ya pagó dos
    veces: `_revenue_result_to_dict` serializaba once líneas de catorce y el
    cuadro cerraba igual, porque `total_revenue` se calculaba aparte.

    Un centavo explicable es mejor que un total que nadie puede recomponer.
    """
    r = derivar_mes(VILLAS, TEMPORADAS, COMISIONES, NOCHES_ENERO, 2027, 1,
                    tarifas_propias={"LONG_TERM": Decimal("75")})
    rack = sum(s["ingreso_rack"] for s in r["segmentos"].values())
    neto = sum(s["ingreso"] for s in r["segmentos"].values())
    assert rack == sum(Decimal(v[0]) for v in ENERO_LIBRO.values())
    assert neto == sum(Decimal(v[1]) for v in ENERO_LIBRO.values())
    # Y a un centavo del total que muestra el libro, nunca más.
    assert abs(rack - Decimal("54347.60")) <= Decimal("0.01")
    assert abs(neto - Decimal("46958.75")) <= Decimal("0.01")


def test_long_term_no_se_descuenta_dos_veces():
    """Su tarifa YA es neta: no se le aplica comisión encima.

    30 noches × $75 = $2.250, igual en rack que en neto (filas 71 y 83).
    """
    r = derivar_mes(VILLAS, TEMPORADAS, COMISIONES, {"LONG_TERM": 30}, 2027, 1,
                    tarifas_propias={"LONG_TERM": Decimal("75")})
    s = r["segmentos"]["LONG_TERM"]
    assert s["ingreso"] == Decimal("2250.00")
    assert s["ingreso_rack"] == Decimal("2250.00")
