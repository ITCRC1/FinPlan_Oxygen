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

## El servicio NO es ingreso

Owner, 2026-10-07: *«el 10% no se considera un ingreso, es un tip que se colecta
para los empleados pagado por el cliente, es tipo impuesto»*. La primera versión
lo sumaba al Food. El hotel cobra ese dinero y lo entrega — no se lo queda. Hoy
se calcula y se muestra, para saber cuánto se recauda, pero **no entra al
ingreso ni a la base del beverage**.

## Sólo una parte de la comida lleva comisión

Owner, 2026-10-07: *«es probable que las comidas se vendan en paquetes a
agencia, entonces se ve afectado por el descuento… pero es como un factor, decir
de todas las ventas 50% lleva comisión y el otro no… y los externos no llevan
descuento»*.

De ahí `pct_comisionable`: la fracción de la comida del huésped que viaja dentro
de un paquete de agencia. Esa parte —y sólo esa— se netea con el **mismo factor
de canal que la tarifa de habitación** (`compute_net_factor`), para que no
convivan dos comisiones distintas en el mismo presupuesto. El externo paga en
la puerta: no lleva descuento nunca.

⚠️ **La comisión se netea del ingreso, no se gasta.** Medido en el mayor el
2026-10-07: la cuenta 7080 Commissions tiene $2.537,28 en todo 2026 y $0 en 2025
sobre $1,3 millones de habitaciones. Si fuera gasto serían seis cifras. Por eso
descontar acá no duplica nada, y por eso el histórico contra el que se calibró
ya viene neto.

## El cuadre contra el que se calibró (2026-10-07)

Doce meses corridos ago-25 a jul-26, con el descuento de canal real de Oxygen
(TA 55% al 20%, Directo 45% al 10% → factor neto 0,845 → 15,5%):

    desayuno $20 captura 100%  +  almuerzo $45 al 16%  +  cena $60 al 16%
    = $36,80 bruto por pax  ·  50% comisionable  →  $33,95 neto por pax
    6.122 pax x $33,95 + externos (50 x $35 x 12) = $228.830
    Food real del período                         = $228.608   ·  dif 0,1%

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

    # ── Lo que NO es ingreso ──────────────────────────────────────────────────
    #: Servicio sobre la comida. Se cobra al cliente y se entrega al personal:
    #: se calcula y se muestra, pero NO suma al ingreso (owner, 2026-10-07).
    servicio_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=DEFAULT_SERVICIO)

    # ── Lo que se descuenta ───────────────────────────────────────────────────
    #: Fracción de la comida del huésped que va dentro de un paquete de agencia
    #: y por lo tanto carga la comisión del canal. El resto, y el externo
    #: completo, se cobran sin descuento.
    pct_comisionable: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=ZERO)

    # ── Lo que arrastra el Food ───────────────────────────────────────────────
    #: Beverage como fracción del Food ya neto. Owner, 2026-10-03: «el beverage
    #: va a salir por % de Food».
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
                 pax_hospedados: Decimal | int,
                 net_factor: Decimal | None = None) -> dict:
    """El cálculo, en un solo lugar: pax → comida → ingreso.

    El orden importa y es el que pidió el owner: **primero el precio de carta,
    después el descuento, y el servicio nunca entra**::

        bruto    = pax x precio_carta x captura        (las tres comidas)
        descuento= bruto x comisionable x (1 - factor) (sólo esa fracción)
        externos = pax_ext x ticket                    (sin descuento)
        FOOD     = bruto - descuento + externos        ← el ingreso
        servicio = (bruto + externos) x servicio_pct   ← se cobra, no es ingreso
        BEVERAGE = FOOD x bev_pct_food

    `net_factor` es lo que le queda al hotel después de la comisión del canal
    —el mismo `compute_net_factor` de la tarifa de habitación—. Sin él se asume
    1 (nadie cobra comisión), que es el default honesto: un factor inventado
    movería el ingreso sin que nadie lo haya escrito.

    Se devuelve abierto —cada comida por separado, el descuento aparte, el
    servicio aparte y los externos aparte— porque la pantalla, el Excel y la
    prueba muestran las mismas piezas. Un total sin sus partes obliga a
    reconstruirlas tres veces.
    """
    pax = Decimal(str(pax_hospedados or 0))
    pax_ext = int(mes.pax_externos) if mes else 0
    ticket = Decimal(str(mes.ticket_externos)) if mes else ZERO

    if cfg is None:
        # Sin configuración no hay carta, pero el externo tampoco se cobra solo:
        # su ticket vive en la fila del mes y sin precios no hay nada que netear.
        return {c: ZERO for c in COMIDAS} | {
            "food_bruto": ZERO, "descuento": ZERO, "food_hospedados": ZERO,
            "food_externos": ZERO, "servicio": ZERO,
            "food": ZERO, "beverage": ZERO, "total": ZERO,
            "pax_hospedados": pax, "pax_externos": pax_ext,
            "pax_total": pax + Decimal(pax_ext),
        }

    # 1 · El bruto: precio de carta por la fracción que de verdad se consume.
    por_comida = {
        c: (pax * getattr(cfg, f"precio_{c}") * getattr(cfg, f"captura_{c}"))
        for c in COMIDAS
    }
    bruto = sum(por_comida.values(), ZERO)

    # 2 · El descuento: sólo sobre la parte que viaja con agencia.
    factor = Decimal("1") if net_factor is None else Decimal(str(net_factor))
    comisionable = Decimal(str(getattr(cfg, "pct_comisionable", ZERO) or ZERO))
    descuento = bruto * comisionable * (Decimal("1") - factor)
    food_hosp = bruto - descuento

    # 3 · El externo paga en la puerta: ni comisión ni paquete.
    food_ext = Decimal(pax_ext) * ticket

    food = food_hosp + food_ext

    # 4 · El servicio se cobra sobre lo que el cliente ve en la cuenta —el
    #     precio de carta—, no sobre lo que queda después de la comisión. No
    #     suma al ingreso: se recauda y se entrega.
    servicio = (bruto + food_ext) * cfg.servicio_pct

    beverage = food * cfg.bev_pct_food

    return {
        **por_comida,
        "food_bruto": bruto,
        "descuento": descuento,
        "food_hospedados": food_hosp,
        "food_externos": food_ext,
        "servicio": servicio,
        "food": food,
        "beverage": beverage,
        "total": food + beverage,
        "pax_hospedados": pax,
        "pax_externos": pax_ext,
        "pax_total": pax + Decimal(pax_ext),
    }
