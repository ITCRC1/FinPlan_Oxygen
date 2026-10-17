# -*- coding: utf-8 -*-
"""El tarifario RAC: la capa que DERIVA la tarifa de `canal_rooms_entries`.

**De dónde sale (owner, 2026-10-15/16).** Del libro
`Presupuesto_Ojochal_2027_Modelo 1_3`, pestañas `Origen Tarifa Rack` y
`KPIs Rack`: *«yo simulé la lógica del cálculo para llegar a la tarifa rack y
después a la neta»* · *«crea un modelo donde yo pueda modificar las variables
inputs y que derive todo lo demás»*.

## ⚠️ Esto NO es un modelo paralelo

Owner, 2026-10-16: *«debes hacer tablas estándares porque después todo esto hay
que consolidarlo en Hotel Consolida»*.

Las tablas que guardan el resultado son **las mismas de Oxygen y de las demás
propiedades**: `canal_segmentos` y `canal_rooms_entries`. De ahí sale
`aplicar_canales_rooms` → `RevenueResult` → `get_monthly_revenue`, que es la
puerta que lee Hotel Consolidation. Ese camino no se toca.

Lo que agregan estas tres tablas es **de dónde viene la tarifa**:

    Oxygen   → se digitan noches Y tarifa
    Ojochal  → se digitan NOCHES; la tarifa sale del RAC y la comisión

Es una capa de ENTRADA que llena `canal_rooms_entries.tarifa` e `ingreso`.
Aguas abajo, las cuatro propiedades son idénticas.

## La cadena, tal cual el Excel

    1  por villa      unidades + RAC Pico/Alta/Verde      `RackVilla`
    2  temporadas     rangos de fecha                     `RackTemporada`
    3  días/temporada traslape mes × temporada              derivado
    4  RAC del mes    (díasP×RACp + díasA×RACa + díasV×RACv) / días
    5  RAC ponderado  Σ(RAC villa × unidades) / Σ unidades
    6  noches         `canal_rooms_entries.noches`        ← el único input
    7  ingreso RACK   noches × RAC ponderado
    8  ingreso NETO   rack × (1 − % comisión)             `RackComision`
    9  indicadores    %Occ · ADR · RevPAR

El Paso 8 es el que escribe `canal_rooms_entries`: `tarifa` = RAC × (1 − %) e
`ingreso` = noches × tarifa. Lo que queda guardado es **el neto**, que es lo
que el P&L y el consolidado tienen que ver. El rack queda derivable desde el
RAC, y se muestra en la pantalla al lado del neto.

## Por qué el tarifario va POR ESCENARIO

El Budget 2027 se congela al aprobarse. Si el RAC viviera en la propiedad, el
tarifario 2028 le cambiaría los números a un presupuesto ya cerrado —y en
silencio, porque el ingreso se deriva—. Por escenario, copiar un escenario se
lleva su tarifario y el viejo queda intacto.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (Boolean, Date, ForeignKey, Integer, Numeric, String,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

#: Las tres temporadas del tarifario. El nombre es la llave, no el orden: en
#: 2027 «Pico» son DOS rangos (1–5 ene y 20–31 dic).
TEMPORADAS = ("PICO", "ALTA", "VERDE")


class RackTemporada(Base):
    """Las fechas de cada temporada, por escenario.

    ⚠️ **En el Excel los días de cada temporada están escritos DENTRO de la
    fórmula** de cada villa (`=(5*$B$66+26*$B$67+0*$B$68)/31`), y el propio
    libro avisa en `Origen Tarifa Rack!D18` que si se cambian las fechas allá
    arriba, esas no se enteran. Acá no puede pasar: los días salen del
    traslape, siempre.
    """

    __tablename__ = "rack_temporadas"
    __table_args__ = (
        UniqueConstraint("scenario_id", "temporada", "desde",
                         name="uq_rack_temporada"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    temporada: Mapped[str] = mapped_column(String(10))
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date] = mapped_column(Date)
    #: Cómo llama ESTA propiedad a esta casilla. Oxygen pone «Baja» sobre la
    #: casilla VERDE; Ojochal pone «Verde». Es decorado: la tarifa sale de
    #: `temporada`, nunca de acá. Vacía = se usa el nombre de la casilla.
    etiqueta: Mapped[str | None] = mapped_column(String(20), nullable=True)


class RackVilla(Base):
    """Unidades y tarifario RAC de cada villa, por escenario.

    Es la pestaña de villa del libro: `B2` (unidades) y `B66:B68` (los tres
    RAC). Owner: *«que los datos estén en los sub tabs por si acaso hay que
    editar cada uno de ellos»*.

    ⚠️ **`unidades` es la UNIDAD DE VENTA, no la habitación.** En Ojochal
    Verde, Fucsia y Turquesa tienen 2 habitaciones y Azul 3, pero se venden
    enteras: **11 unidades contra 16 habitaciones**. Las noches disponibles de
    este modelo salen de las unidades, y por eso dan 4.015 y no 5.840. La hoja
    `Comparativo Inventario` del libro lo detalla villa por villa.
    """

    __tablename__ = "rack_villas"
    __table_args__ = (
        UniqueConstraint("scenario_id", "villa", name="uq_rack_villa"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    #: El nombre de la categoría, igual que `room_type_configs.name`.
    villa: Mapped[str] = mapped_column(String(60))
    unidades: Mapped[int] = mapped_column(Integer, default=0)
    rac_pico: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    rac_alta: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    rac_verde: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    orden: Mapped[int] = mapped_column(Integer, default=0)


class RackComision(Base):
    """El % de comisión implícita de cada segmento, por escenario.

    Es `Resumen Manual` B67:B73, pero **por mes**: doce filas por segmento.
    Se llama *implícita* porque no es lo que factura la agencia: es cuánto se
    aleja del rack el precio al que ese segmento realmente vende.

    ⚠️ **Un segmento sin fila acá vende a rack**, no gratis: la ausencia se lee
    como 0% de comisión. Lo contrario —tratarla como 100%— pondría el ingreso
    en cero sin que nada avise.

    `tarifa_propia = True` saca al segmento de la cadena del RAC: su tarifa se
    digita mes a mes en `canal_rooms_entries.tarifa` (es el caso de *Long term
    rentals*, que no tiene RAC). No es una excepción escrita en el motor: es
    una columna, para que una propiedad pueda declarar la suya.
    """

    __tablename__ = "rack_comisiones"
    __table_args__ = (
        UniqueConstraint("scenario_id", "segmento_code", "month",
                         name="uq_rack_comision_mes"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    segmento_code: Mapped[str] = mapped_column(String(30))
    #: 1-12. Son DOCE filas por segmento, una por mes.
    #:
    #: Owner, 2026-10-16: *«pone el primer mes y se replica a los 12 meses y
    #: manual se cambia el mes que probablemente cambie»*. Con una sola columna
    #: para todo el año, un canal que cambia su comisión a mitad de año obliga
    #: a poner un promedio — y el promedio no es el número de ningún mes: deja
    #: el ingreso mal en direcciones opuestas y el total del año lo disimula.
    month: Mapped[int] = mapped_column(Integer, default=1)
    #: 0.25 = 25%. No se usa si `tarifa_propia`.
    comision_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0"))
    #: ⚠️ Es del SEGMENTO, no del mes: *Long term* no tiene RAC en enero y sí en
    #: julio. Está repetido en las doce filas porque la fila es por mes, y el
    #: que escribe lo pone igual en las doce —lo vigila
    #: `test_comision_por_mes.py`—. Leerlo de un mes suelto daría distinto
    #: según el mes que se mire.
    tarifa_propia: Mapped[bool] = mapped_column(Boolean, default=False)
