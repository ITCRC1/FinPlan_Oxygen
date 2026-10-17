# -*- coding: utf-8 -*-
"""De dónde sale la tarifa: el tarifario RAC, paso a paso.

Es la pestaña `Origen Tarifa Rack` del libro del owner, en código. Cada paso
tiene su función, y cada CONTROL del Excel tiene su prueba en
`tests/test_rack_tarifa.py`.

    1  inputs por villa      unidades + RAC Pico/Alta/Verde      `RackVilla`
    2  temporadas            rangos de fecha                     `RackTemporada`
    3  días por temporada    `dias_por_temporada`                CONTROL f32
    4  RAC del mes por villa `rac_villa_mes`                     CONTROL f43
    5  RAC ponderado         `rac_ponderado`                     CONTROL f49/f50
    6  noches por segmento   `canal_rooms_entries.noches`        ← el input
    7  ingreso rack          `ingreso_rack`                      CONTROL f74
    8  ingreso neto          `ingreso_neto`                      CONTROL f88
    9  indicadores           los calcula `calcular_mes`

⚠️ **Puro: no toca la base.** Recibe listas y devuelve números, igual que
`revenue_calculator`. Así las pruebas corren sin sesión y comparan contra las
celdas del Excel sin montar nada.

## Las dos excepciones, y dónde viven

* **Long term rentals** no tiene RAC: su tarifa se digita mes a mes. Lo declara
  `RackComision.tarifa_propia`, no una lista en este archivo.
* **CPL | Uso casa | Canjes** ocupa villa y no factura. Lo declara
  `CanalSegmento.genera_ingreso`, y lo aplica `calcular_mes`.

Escribirlas acá sería la misma trampa que dejó al Club fuera del P&L: una lista
en el motor que nadie recuerda actualizar cuando aparece una propiedad nueva.
"""
from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

ZERO = Decimal("0")
CENT = Decimal("0.01")


# ── Paso 3 · los días de cada temporada en un mes ───────────────────────────
def dias_por_temporada(anio: int, mes: int, temporadas) -> dict[str, int]:
    """Cuántos días del mes cae en cada temporada.

    `temporadas` es una lista de objetos con `.temporada`, `.desde` y `.hasta`.
    Una temporada puede traer VARIOS rangos —en 2027 «Pico» son dos, enero y
    diciembre— y se suman.

    ⚠️ **Se calcula del traslape, siempre.** En el Excel los días están
    escritos dentro de la fórmula de cada villa (`=(5*$B$66+26*$B$67+…)/31`), y
    el propio libro avisa que si se cambian las fechas allá arriba, esas no se
    enteran. Acá no puede pasar.
    """
    ini = date(anio, mes, 1)
    fin = date(anio, mes, calendar.monthrange(anio, mes)[1])
    out: dict[str, int] = {}
    for t in temporadas:
        desde, hasta = t.desde, t.hasta
        a = max(ini, desde)
        b = min(fin, hasta)
        dias = (b - a).days + 1 if b >= a else 0
        if dias:
            out[t.temporada] = out.get(t.temporada, 0) + dias
    return out


def traslape(rangos):
    """El primer par de rangos que se pisa, o `None` si ninguno.

    `rangos` — iterable de `(desde, hasta, temporada)`.

    ⚠️ **El hueco y el traslape no se ven igual.** `dias_sin_temporada` denuncia
    el día que no cae en ninguna temporada, porque el denominador lo cuenta y
    el numerador no. El día que cae en DOS no deja rastro: se suma dos veces,
    el RAC del mes sale inflado y el total cuadra consigo mismo. Por eso esto
    se revisa al GUARDAR, antes de que el número exista.
    """
    orden = sorted(rangos)
    for (d1, h1, t1), (d2, h2, t2) in zip(orden, orden[1:]):
        if d2 <= h1:
            return (t1, t2, d2)
    return None


def dias_del_mes(anio: int, mes: int) -> int:
    return calendar.monthrange(anio, mes)[1]


def dias_sin_temporada(anio: int, mes: int, temporadas) -> int:
    """El CONTROL de la fila 32: tiene que dar CERO.

    Un día sin temporada es un día sin tarifa, y el RAC del mes saldría
    diluido sin que nada avise. Se expone para que la pantalla lo muestre.
    """
    return dias_del_mes(anio, mes) - sum(dias_por_temporada(anio, mes, temporadas).values())


# ── Paso 4 · el RAC del mes de una villa ────────────────────────────────────
def rac_villa_mes(villa, anio: int, mes: int, temporadas) -> Decimal:
    """(díasPico × RACpico + díasAlta × RACalta + díasVerde × RACverde) / días.

    Si un día no cae en ninguna temporada, NO se inventa tarifa para él: el
    numerador no lo cuenta y el denominador sí, así que el RAC baja — y
    `dias_sin_temporada` lo denuncia. Repartirlo en silencio escondería el
    hueco detrás de un número plausible.
    """
    dias = dias_por_temporada(anio, mes, temporadas)
    total = dias_del_mes(anio, mes)
    if not total:
        return ZERO
    rac = {
        "PICO": Decimal(str(villa.rac_pico or 0)),
        "ALTA": Decimal(str(villa.rac_alta or 0)),
        "VERDE": Decimal(str(villa.rac_verde or 0)),
    }
    num = sum(Decimal(dias.get(k, 0)) * v for k, v in rac.items())
    return num / Decimal(total)


# ── Paso 5 · el RAC ponderado por unidades ──────────────────────────────────
def rac_ponderado(villas, anio: int, mes: int, temporadas) -> Decimal:
    """Σ(RAC villa × unidades) / Σ unidades.

    ⚠️ Pondera por UNIDADES DE VENTA, no por habitaciones. En Ojochal Verde,
    Fucsia y Turquesa tienen 2 habitaciones y Azul 3, pero se venden enteras:
    11 unidades contra 16 habitaciones. Ponderar por habitación le daría a las
    villas grandes un peso que no tienen en la venta.
    """
    tot_u = sum(int(v.unidades or 0) for v in villas)
    if not tot_u:
        return ZERO
    num = sum(rac_villa_mes(v, anio, mes, temporadas) * Decimal(int(v.unidades or 0))
              for v in villas)
    return num / Decimal(tot_u)


def disponibles_mes(villas, anio: int, mes: int) -> int:
    """Unidades × días del mes. El denominador de la ocupación y del RevPAR."""
    return sum(int(v.unidades or 0) for v in villas) * dias_del_mes(anio, mes)


# ── Pasos 7 y 8 · de las noches al ingreso, rack y neto ─────────────────────
def tarifa_del_segmento(rac: Decimal, comision_pct, tarifa_propia_mes=None,
                        tarifa_propia: bool = False) -> Decimal:
    """La tarifa NETA a la que vende ese segmento, para MOSTRAR.

    * con `tarifa_propia` → la que se digitó ese mes (Long term no tiene RAC);
    * si no → RAC × (1 − % comisión implícita).

    ⚠️ **El ingreso NO se calcula desde acá.** Ver `ingreso_neto_segmento`: el
    descuento se aplica al ingreso, no a la tarifa. Redondear la tarifa a
    centavos y después multiplicarla por las noches daba **45 centavos de menos**
    en enero contra el libro — chico, pero es un sesgo sistemático a la baja y
    crece con el volumen.

    ⚠️ **Sin fila de comisión se vende A RACK, no gratis.** La ausencia se lee
    como 0%. Tratarla como 100% pondría el ingreso en cero y el total seguiría
    cuadrando consigo mismo.
    """
    if tarifa_propia:
        return Decimal(str(tarifa_propia_mes or 0))
    pct = Decimal(str(comision_pct or 0))
    return (rac * (Decimal("1") - pct)).quantize(CENT)


def ingreso_rack(noches, rac: Decimal) -> Decimal:
    return (Decimal(str(noches or 0)) * rac).quantize(CENT)


def ingreso_neto(noches, tarifa: Decimal) -> Decimal:
    """Noches × una tarifa YA dada. Es el camino del segmento de tarifa propia."""
    return (Decimal(str(noches or 0)) * tarifa).quantize(CENT)


def ingreso_neto_segmento(noches, rac: Decimal, comision_pct) -> Decimal:
    """(noches × RAC) × (1 − comisión), redondeado UNA vez al final.

    ⚠️ **El descuento va sobre el ingreso, no sobre la tarifa.** Es como lo
    hace el libro (`Origen Tarifa Rack` fila 78: `=C66*(1-$B78)`, donde C66 es
    el ingreso rack) y no es un detalle de gusto: materializar una tarifa neta
    redondeada a centavos y multiplicarla por las noches pierde hasta medio
    centavo POR NOCHE, siempre para abajo. En enero eran 45 centavos sobre
    $46.958; sobre un año entero y cuatro propiedades deja de ser anécdota.

    La tarifa neta existe igual —`tarifa_del_segmento`— pero para mostrar y
    para guardar, no para calcular.
    """
    pct = Decimal(str(comision_pct or 0))
    bruto = Decimal(str(noches or 0)) * rac
    return (bruto * (Decimal("1") - pct)).quantize(CENT)


# ── El mes entero, listo para escribir en `canal_rooms_entries` ─────────────
def kpis_rack(segmentos: dict, noches_por_segmento: dict, genera: dict,
              propias: set, disponibles) -> dict:
    """El bloque «KPIs A PRECIO RACK» del libro, y el de «RACK vs NETO».

    `segmentos` — lo que devuelve `derivar_mes`: {code: {tarifa, ingreso,
    ingreso_rack}}.

    Devuelve los dos lados del mismo mes. El NETO es lo que entra al P&L; el
    RACK es contra lo que se mide el descuento — sin él, «vendimos a $177» no
    se puede comparar con nada y la comisión deja de tener denominador.

    ## ⚠️ El ADR Rack se muestra DOS veces, y no es redundancia

    `adr_rack` divide por TODAS las noches que facturan. `adr_rack_sin_propias`
    saca los segmentos de tarifa propia —Long term, que no tiene RAC— y por eso
    da el RAC ponderado puro. Mezclarlos hace parecer que el tarifario bajó
    cuando lo único que pasó es que se vendieron más noches largas: en 2027 son
    **$209,70 contra $231,29**, y la segunda es la que se compara contra el
    tarifario del año.

    ## ⚠️ Las noches de cortesía no entran en ningún denominador de tarifa

    Ocupan villa, así que cuentan para la ocupación, pero no facturan: meterlas
    acá diluye el ADR en los dos lados.
    """
    disp = Decimal(str(disponibles or 0))
    rack = neto = ZERO
    n_fact = n_propias = n_cortesia = ZERO
    rack_propias = ZERO
    for code, d in segmentos.items():
        n = Decimal(str(noches_por_segmento.get(code, 0) or 0))
        if not genera.get(code, True):
            n_cortesia += n
            continue
        rack += d["ingreso_rack"]
        neto += d["ingreso"]
        n_fact += n
        if code in propias:
            n_propias += n
            rack_propias += d["ingreso_rack"]
    n_sin_propias = n_fact - n_propias
    comision = rack - neto
    return {
        "ingreso_rack": rack,
        "ingreso_neto": neto,
        "noches_facturadas": n_fact,
        "noches_tarifa_propia": n_propias,
        "noches_cortesia": n_cortesia,
        "adr_rack": (rack / n_fact) if n_fact else ZERO,
        # El RAC ponderado puro: sin los que no tienen tarifario.
        "adr_rack_sin_propias": ((rack - rack_propias) / n_sin_propias)
                                if n_sin_propias else ZERO,
        "revpar_rack": (rack / disp) if disp else ZERO,
        "adr_neto": (neto / n_fact) if n_fact else ZERO,
        "revpar_neto": (neto / disp) if disp else ZERO,
        "comision_usd": comision,
        "comision_pct": (comision / rack) if rack else ZERO,
        # Lo que queda del rack después del canal. Es `1 − comisión`, y va
        # aparte porque es el número que el owner mira para negociar.
        "pct_rack_retenido": (neto / rack) if rack else ZERO,
        "mix_rack": {code: ((d["ingreso_rack"] / rack) if rack else ZERO)
                     for code, d in segmentos.items()
                     if genera.get(code, True)},
    }


def derivar_mes(villas, temporadas, comisiones: dict, noches_por_segmento: dict,
                anio: int, mes: int, tarifas_propias: dict | None = None,
                genera: dict | None = None) -> dict:
    """Todo el paso 1→8 de un mes, en una llamada.

    Devuelve por segmento `{tarifa, ingreso, ingreso_rack}` más el RAC del mes
    y las noches disponibles. Lo que se GUARDA en `canal_rooms_entries` es la
    tarifa y el ingreso NETOS: es lo que el P&L y el consolidado tienen que
    ver. El rack queda derivable desde el RAC y se muestra al lado.

    `comisiones` — {code: (pct, tarifa_propia)}
    `noches_por_segmento` — {code: noches}
    `tarifas_propias` — {code: tarifa} sólo para los de tarifa propia.
    `genera` — {code: genera_ingreso} del catálogo. Un segmento de CORTESÍA
        ocupa la villa y **no cobra**: tarifa, ingreso e ingreso rack en cero.

    ⚠️ **La cortesía hay que apagarla acá, no después.** Sin `genera`, un
    segmento sin comisión cargada se lee como 0 % —o sea «vende a rack»— y el
    CPL entra al ingreso a tarifa publicada. En Oxygen 2027 eso eran 138
    noches y **$79.355** que el P&L daba por cobrados. No falla nada: el total
    cuadra consigo mismo, la ocupación sale bien, y sólo el ADR queda raro
    —porque esas noches suman al numerador y no al denominador—.
    """
    rac = rac_ponderado(villas, anio, mes, temporadas)
    tp = tarifas_propias or {}
    gen = genera or {}
    out = {}
    for code, noches in noches_por_segmento.items():
        if not gen.get(code, True):
            out[code] = {"tarifa": ZERO, "ingreso": ZERO, "ingreso_rack": ZERO}
            continue
        pct, propia = comisiones.get(code, (ZERO, False))
        t = tarifa_del_segmento(rac, pct, tp.get(code), propia)
        if propia:
            # Su tarifa YA es neta: no se le aplica comisión encima, y su rack
            # es su propio ingreso porque no tiene tarifario contra el cual
            # compararse.
            neto = ingreso_neto(noches, t)
            bruto = neto
        else:
            neto = ingreso_neto_segmento(noches, rac, pct)
            bruto = ingreso_rack(noches, rac)
        out[code] = {"tarifa": t, "ingreso": neto, "ingreso_rack": bruto}
    return {
        "rac_ponderado": rac,
        "disponibles": disponibles_mes(villas, anio, mes),
        "dias_sin_temporada": dias_sin_temporada(anio, mes, temporadas),
        "segmentos": out,
    }
