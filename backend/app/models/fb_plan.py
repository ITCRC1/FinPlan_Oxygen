# -*- coding: utf-8 -*-
"""Planificación de A&B: del pax a la comida, y de la comida al ingreso.

**Por qué existe (owner, 2026-10-03).** *«food and beverage es un departamento
importante… la idea es que podamos calcular los ingresos acá, partiendo de las
estadísticas de rooms»*. Hasta hoy el A&B del presupuesto salía del motor de
PAQUETES (`package_configs`), que es producto de Corcovado: un Full Board de
$126 por pax/noche que esta propiedad no vende. Oxygen tenía `package_configs`
en CERO y el Food del checkbook en cero con él.

## La captura es la razón de ser de esta tabla

Multiplicar pax por el precio de las tres comidas da el techo, no el ingreso.
Medido contra el mayor de Oxygen el 2026-10-03:

    6.643 pax-noche x $126 (desayuno+almuerzo+cena) = $837.018
    Food real (12 meses corridos ago-25 a jul-26)   = $228.608

O sea que **se consume el 27% de las comidas posibles**. Sin un porcentaje de
captura por comida la pantalla devuelve cinco veces el número, y lo devuelve con
cara de estar bien calculado — que es la peor forma de estar mal.

El % va POR COMIDA y no uno solo: el desayuno del huésped se consume casi
siempre y la cena bastante menos. Un promedio los aplana y esconde cuál de las
tres es la que mueve el ingreso.

## Los externos no se modelan por comida

Quien no se hospeda no desayuna: entra a almorzar o a cenar. Modelarlo con las
mismas tres comidas obliga a inventar tres capturas más para un dato que el
hotel conoce de otra forma — cuánta gente entró y cuánto gastó en promedio.
Por eso son dos campos por mes: cantidad y ticket promedio.

## El servicio se suma aparte

Owner, 2026-10-03. Los precios que se digitan son PRE-servicio y la pantalla
agrega el 10% encima, igual que la tabla de referencia del Full Board
($126 → $138,60). Queda visible cuánto es carta y cuánto es servicio.

## Nace en cero

Misma regla que `payroll_params`: sin fila, o con la fila en cero, el ingreso de
A&B es cero y nada se mueve solo. Se llena, se mira, y recién entonces se pasa
al checkbook.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, Numeric, Integer, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ZERO = Decimal("0")
#: Servicio de ley en Costa Rica. Es el default, no una constante del motor:
#: la fila lo guarda y se puede cambiar por escenario.
DEFAULT_SERVICIO = Decimal("0.10")

#: Las tres comidas, en el orden en que se sirven. El orden es el de la pantalla
#: y el del Excel: cambiarlo acá los cambia a los dos y no hay una segunda lista.
COMIDAS = ("desayuno", "almuerzo", "cena")


class FbPlanConfig(Base):
    """Precios y captura por comida. Una fila por escenario.

    Los precios son **por pax y por comida, antes del servicio**. La captura es
    la fracción de los pax del mes que toma esa comida: `1.00` = todos,
    `0.35` = poco más de un tercio.
    """
    __tablename__ = "fb_plan_config"
    __table_args__ = (UniqueConstraint("scenario_id", name="uq_fb_plan_config"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)

    # ── Precio por pax, pre-servicio ──────────────────────────────────────────
    precio_desayuno: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO)
    precio_almuerzo: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO)
    precio_cena: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO)

    # ── Captura: qué fracción de los pax toma cada comida (0.0000 a 1.0000) ───
    captura_desayuno: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=ZERO)
    captura_almuerzo: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=ZERO)
    captura_cena: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=ZERO)

    # ── Lo que se agrega encima ───────────────────────────────────────────────
    #: Servicio sobre la comida. Se SUMA al precio digitado.
    servicio_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=DEFAULT_SERVICIO)
    #: Beverage como fracción del Food ya con servicio. Owner, 2026-10-03:
    #: «el beverage va a salir por % de Food».
    bev_pct_food: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=ZERO)

    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actualizado_por: Mapped[str] = mapped_column(String(120), default="")


class FbPlanMes(Base):
    """Los pax que NO salen de las estadísticas de Rooms. Una fila por mes.

    Los pax hospedados vienen de `scenario_stats.guests` y no se digitan acá: si
    se pudieran escribir habría dos verdades sobre el mismo mes y el día que no
    coincidan nadie sabría cuál manda.
    """
    __tablename__ = "fb_plan_mes"
    __table_args__ = (
        UniqueConstraint("scenario_id", "month", name="uq_fb_plan_mes"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    month: Mapped[int] = mapped_column(Integer)

    #: Gente que entra al restaurante sin hospedarse.
    pax_externos: Mapped[int] = mapped_column(Integer, default=0)
    #: Lo que gasta en promedio uno de ellos, pre-servicio.
    ticket_externos: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO)

    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actualizado_por: Mapped[str] = mapped_column(String(120), default="")


def calcular_mes(cfg: FbPlanConfig | None, mes: FbPlanMes | None,
                 pax_hospedados: Decimal | int) -> dict:
    """El cálculo, en un solo lugar: pax → comida → ingreso.

    Se devuelve abierto —cada comida por separado, el servicio aparte y los
    externos aparte— porque la pantalla, el Excel y la prueba muestran las
    mismas piezas. Un total sin sus partes obliga a reconstruirlas tres veces.
    """
    if cfg is None:
        return {"desayuno": ZERO, "almuerzo": ZERO, "cena": ZERO,
                "food_hospedados": ZERO, "food_externos": ZERO,
                "food_pre_servicio": ZERO, "servicio": ZERO,
                "food": ZERO, "beverage": ZERO, "total": ZERO,
                "pax_hospedados": Decimal(str(pax_hospedados or 0)),
                "pax_externos": 0, "pax_total": Decimal(str(pax_hospedados or 0))}

    pax = Decimal(str(pax_hospedados or 0))
    por_comida = {
        c: (pax * getattr(cfg, f"precio_{c}") * getattr(cfg, f"captura_{c}"))
        for c in COMIDAS
    }
    food_hosp = sum(por_comida.values(), ZERO)

    pax_ext = int(mes.pax_externos) if mes else 0
    ticket = Decimal(str(mes.ticket_externos)) if mes else ZERO
    food_ext = Decimal(pax_ext) * ticket

    pre = food_hosp + food_ext
    servicio = pre * cfg.servicio_pct
    food = pre + servicio
    beverage = food * cfg.bev_pct_food

    return {
        **por_comida,
        "food_hospedados": food_hosp,
        "food_externos": food_ext,
        "food_pre_servicio": pre,
        "servicio": servicio,
        "food": food,
        "beverage": beverage,
        "total": food + beverage,
        "pax_hospedados": pax,
        "pax_externos": pax_ext,
        "pax_total": pax + Decimal(pax_ext),
    }
