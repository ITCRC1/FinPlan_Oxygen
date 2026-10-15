# -*- coding: utf-8 -*-
"""Rooms por CANAL: el modelo alternativo para las propiedades sin histórico.

Owner, 2026-10-15: *«actualmente la forma de sacar el ingreso es derivando la
tarifa a partir de la tarifa rack por tipo de habitación y por mes… sin embargo
no tenemos historial de ventas totales, ocupación y tarifa de los históricos
porque no hay históricos por tipo de habitación como sí tengo en FinPlan CWL…
Sales and Marketing me proponen hacerlo de otra manera, por canal»*.

## Los dos modelos, y por qué conviven

    por TARIFA (el actual)   rack por tipo de habitación × ocupación × factor
                             de canal → ingreso. Necesita historia POR TIPO DE
                             HABITACIÓN para calibrarse.

    por CANAL (este)         noches y tarifa promedio POR SEGMENTO DE VENTA
                             → ingreso. Necesita historia por canal, que es lo
                             que el PMS sí sabe dar.

CWL tiene la primera porque alguien la construyó mes a mes durante años. Oxygen,
Ojochal y Amarena no la tienen y no la van a tener hacia atrás: empezar a
llevarla por canal desde 2027 es el camino realista. **Los dos modelos quedan,
y cada propiedad engancha el suyo** (`Scenario.rooms_source`).

## La forma del dato viene del archivo de Sales

`Presupuesto_Oxygen_2027_Modelo_v2`, pestaña `Resumen Manual`: ocho segmentos ×
cuatro métricas × doce meses, en seis versiones. Se digitan **noches** y
**tarifa promedio**; el ingreso se deriva (`D9 = D8*D10` en el original).

## ⚠️ CPL / uso casa / canjes no entra en el ADR

Es el detalle que hace que el cuadro cierre o no. Esas noches **ocupan una
villa pero no generan ingreso**, así que el libro de Sales las separa:

    noches ocupadas (generan ingreso) = los siete segmentos de venta
    noches ocupadas (incl. CPL)       = + las de cortesía
    ADR    = ingreso / noches que GENERAN ingreso
    RevPAR = ingreso / habitaciones disponibles

Meterlas en el denominador del ADR lo diluye y el número deja de ser comparable
contra el PMS. Por eso cada segmento declara `genera_ingreso` y el motor lo
respeta — no es una lista de excepciones escrita a mano.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (String, Integer, Numeric, Boolean, ForeignKey,
                        UniqueConstraint, DateTime)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ZERO = Decimal("0")

#: Los ocho segmentos del libro de Sales, en su orden. `genera_ingreso=False`
#: saca al segmento del denominador del ADR — ver el docstring del módulo.
SEGMENTOS_SEMILLA: tuple[tuple[str, str, bool], ...] = (
    ("AGENCIAS",      "Agencias",                       True),
    ("DIRECT_WEB",    "Direct (website / Rsv)",         True),
    ("CRC_DIRECT",    "Costa Rica Collection direct",   True),
    ("DIRECT_PHONE",  "Direct — phone / email / social", True),
    ("DIRECT_GROUPS", "Direct groups",                  True),
    ("EXEC_DIRECT",   "Executive personal direct",      True),
    ("OTA",           "OTA's",                          True),
    ("CPL",           "CPL | Uso casa | Canjes",        False),
)


class CanalSegmento(Base):
    """El catálogo de segmentos de venta. Por propiedad, editable.

    No se escribe a mano en el motor: una propiedad que venda por un canal que
    las demás no tienen lo agrega acá y aparece en la grilla, en el reporte y
    en el importador sin tocar código. Es la misma regla que
    `OTHER_REVENUE_LINES`, por la misma razón: la lista escrita a mano fue la
    que dejó al Club afuera del P&L.
    """
    __tablename__ = "canal_segmentos"
    __table_args__ = (
        UniqueConstraint("hotel_id", "code", name="uq_canal_segmento"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    code: Mapped[str] = mapped_column(String(30))
    nombre: Mapped[str] = mapped_column(String(80))
    #: False = ocupa villa pero NO entra al denominador del ADR (CPL, canjes).
    genera_ingreso: Mapped[bool] = mapped_column(Boolean, default=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CanalRoomsEntry(Base):
    """Noches y tarifa de un segmento, en un mes, de un escenario.

    **El ingreso se guarda calculado**, no sólo derivado al vuelo: el libro de
    Sales permite digitar el ingreso directo en las versiones históricas (donde
    la tarifa es el promedio que sale del PMS, no un precio de lista) y
    recalcularlo desde noches × tarifa perdería el centavo del redondeo contra
    el reporte original.

    `tarifa_digitada` dice cuál de los dos mandó, para que la pantalla muestre
    en amarillo lo que se digitó y en negro lo que salió de una cuenta.
    """
    __tablename__ = "canal_rooms_entries"
    __table_args__ = (
        UniqueConstraint("scenario_id", "segmento_code", "month",
                         name="uq_canal_rooms_entry"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    segmento_code: Mapped[str] = mapped_column(String(30))
    month: Mapped[int] = mapped_column(Integer)

    noches: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO)
    tarifa: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO)
    ingreso: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=ZERO)
    #: True = el usuario digitó la tarifa y el ingreso se derivó.
    #: False = digitó el ingreso y la tarifa es el promedio resultante.
    tarifa_digitada: Mapped[bool] = mapped_column(Boolean, default=True)

    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actualizado_por: Mapped[str] = mapped_column(String(120), default="")


def derivar(noches, tarifa, ingreso, tarifa_digitada: bool) -> tuple[Decimal, Decimal]:
    """Cierra el triángulo noches / tarifa / ingreso en un solo lugar.

    Devuelve `(tarifa, ingreso)` ya consistentes. Cuál de los dos manda lo dice
    `tarifa_digitada`; el que no mandó se recalcula. Con noches en cero los dos
    quedan en cero y no se divide por nada.
    """
    n = Decimal(str(noches or 0))
    if not n:
        return ZERO, Decimal(str(ingreso or 0)) if not tarifa_digitada else ZERO
    if tarifa_digitada:
        t = Decimal(str(tarifa or 0))
        return t, (n * t).quantize(Decimal("0.01"))
    i = Decimal(str(ingreso or 0))
    return (i / n).quantize(Decimal("0.01")), i


def calcular_mes(entradas: list, genera: dict[str, bool],
                 disponibles) -> dict:
    """Los totales del mes, con la regla del CPL.

    `entradas`  — las filas del mes (una por segmento).
    `genera`    — {code: genera_ingreso}, del catálogo.
    `disponibles` — noches disponibles del mes (unidades × días).

    ⚠️ `noches_ingreso` excluye los segmentos de cortesía y es el denominador
    del ADR. `noches_totales` los incluye y sirve para la ocupación real de la
    villa. Confundirlos diluye el ADR y lo vuelve incomparable contra el PMS.
    """
    disp = Decimal(str(disponibles or 0))
    n_ing = n_tot = ingreso = ZERO
    por_segmento: dict[str, dict] = {}
    for e in entradas:
        n = Decimal(str(e.noches or 0))
        i = Decimal(str(e.ingreso or 0))
        n_tot += n
        ingreso += i
        if genera.get(e.segmento_code, True):
            n_ing += n
        por_segmento[e.segmento_code] = {
            "noches": n, "tarifa": Decimal(str(e.tarifa or 0)), "ingreso": i,
            "ocupacion": (n / disp) if disp else ZERO,
        }
    return {
        "disponibles": disp,
        "noches_ingreso": n_ing,
        "noches_totales": n_tot,
        "ingreso": ingreso,
        "ocupacion": (n_ing / disp) if disp else ZERO,
        "ocupacion_total": (n_tot / disp) if disp else ZERO,
        "adr": (ingreso / n_ing) if n_ing else ZERO,
        "revpar": (ingreso / disp) if disp else ZERO,
        "segmentos": por_segmento,
    }
