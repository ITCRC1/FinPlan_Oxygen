# -*- coding: utf-8 -*-
"""Planning → A&B: calcular el ingreso de comida y bebida desde los pax.

Owner, 2026-10-03: *«food and beverage es un departamento importante… partir de
las estadísticas de rooms… y también hay una cantidad de pax externos… sacar los
rates de desayuno, almuerzo y cena para multiplicar por la cantidad de pax»*.

**Los pax hospedados no se digitan.** Vienen de `scenario_stats.guests`, que es
lo que la pantalla de Rooms ya calculó. Dos lugares para escribir el mismo mes
es dos verdades y ninguna manda.

**Nada se mueve solo.** El GET calcula y muestra; el P&L no cambia hasta que
alguien aprieta «pasar al checkbook», que es lo que escribe `revenue_entries`.
Es la misma separación del mixer: ver el número y aceptarlo son dos actos.
"""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._candado import candado
from app.auth import get_current_user
from app.db import get_db
from app.errores import ErrorApi
from app.models.fb_plan import FbPlanConfig, FbPlanMes, calcular_mes, COMIDAS
from app.models.scenario import Scenario

router = APIRouter()

MESES = list(range(1, 13))


def _d(v) -> str:
    return str(Decimal(str(v or 0)))


async def _pax_por_mes(db: AsyncSession, scenario_id: str) -> dict[int, Decimal]:
    """Pax hospedados del mes, desde las estadísticas del escenario.

    Un mes sin estadística devuelve 0 y no revienta: el presupuesto en
    construcción tiene meses vacíos con todo derecho.
    """
    from app.models.scenario_stat import ScenarioStat
    filas = (await db.execute(select(ScenarioStat).where(
        ScenarioStat.scenario_id == scenario_id))).scalars().all()
    return {f.month: Decimal(str(f.guests or 0)) for f in filas}


async def _factor_por_mes(db: AsyncSession, scenario_id: str) -> dict[int, Decimal]:
    """Lo que le queda al hotel después de la comisión, mes a mes.

    Es **el mismo** `compute_net_factor` que netea la tarifa de habitación. Que
    A&B tuviera su propia comisión sería tener dos verdades sobre el mismo canal
    y descubrirlo el día que no coincidan.

    Un escenario sin canales devuelve factor 1 —nadie cobra comisión— en vez de
    0, que dejaría el Food entero en cero sin que nadie lo haya pedido.
    """
    from app.models.sales_channel_config import SalesChannelConfig, compute_net_factor
    canales = (await db.execute(select(SalesChannelConfig).where(
        SalesChannelConfig.scenario_id == scenario_id))).scalars().all()
    if not canales:
        return {m: Decimal("1") for m in MESES}
    return {m: compute_net_factor(canales, m) or Decimal("1") for m in MESES}


async def _cargar(db: AsyncSession, scenario_id: str):
    cfg = (await db.execute(select(FbPlanConfig).where(
        FbPlanConfig.scenario_id == scenario_id))).scalar_one_or_none()
    meses = {m.month: m for m in (await db.execute(select(FbPlanMes).where(
        FbPlanMes.scenario_id == scenario_id))).scalars().all()}
    return cfg, meses


@router.get("/fb-plan/{scenario_id}/")
async def ver(scenario_id: str, db: AsyncSession = Depends(get_db),
              _=Depends(get_current_user)):
    esc = await db.get(Scenario, scenario_id)
    if not esc:
        raise ErrorApi(404, "escenario.no_encontrado")
    cfg, meses = await _cargar(db, scenario_id)
    pax = await _pax_por_mes(db, scenario_id)
    factor = await _factor_por_mes(db, scenario_id)

    filas, tot = [], {}
    for m in MESES:
        r = calcular_mes(cfg, meses.get(m), pax.get(m, Decimal("0")), factor[m])
        filas.append({"month": m, "net_factor": _d(factor[m]),
                      **{k: _d(v) for k, v in r.items()}})
        for k, v in r.items():
            tot[k] = tot.get(k, Decimal("0")) + Decimal(str(v))

    return {
        "scenario_id": scenario_id,
        "locked": esc.is_locked,
        "sin_estadisticas": not pax,
        "config": {
            **{f"precio_{c}": _d(getattr(cfg, f"precio_{c}")) for c in COMIDAS},
            **{f"captura_{c}": _d(getattr(cfg, f"captura_{c}")) for c in COMIDAS},
            "servicio_pct": _d(cfg.servicio_pct),
            "pct_comisionable": _d(cfg.pct_comisionable),
            "bev_pct_food": _d(cfg.bev_pct_food),
        } if cfg else None,
        "meses": filas,
        "total": {k: _d(v) for k, v in tot.items()},
    }


class ConfigBody(BaseModel):
    precio_desayuno: Decimal = Decimal("0")
    precio_almuerzo: Decimal = Decimal("0")
    precio_cena: Decimal = Decimal("0")
    captura_desayuno: Decimal = Decimal("0")
    captura_almuerzo: Decimal = Decimal("0")
    captura_cena: Decimal = Decimal("0")
    servicio_pct: Decimal = Decimal("0.10")
    pct_comisionable: Decimal = Decimal("0")
    bev_pct_food: Decimal = Decimal("0")


class MesBody(BaseModel):
    month: int
    pax_externos: int = 0
    ticket_externos: Decimal = Decimal("0")


class GuardarBody(BaseModel):
    config: ConfigBody
    meses: list[MesBody] = []


@router.put("/fb-plan/{scenario_id}/")
async def guardar(scenario_id: str, body: GuardarBody,
                  db: AsyncSession = Depends(get_db),
                  user=Depends(get_current_user)):
    await candado(db, scenario_id)

    # La captura es una fracción: un 35 escrito donde va 0,35 multiplicaría el
    # ingreso por cien y la pantalla lo mostraría sin pestañear.
    for c in COMIDAS:
        v = getattr(body.config, f"captura_{c}")
        if v < 0 or v > 1:
            raise ErrorApi(422, "fb.captura_fuera_de_rango", comida=c, valor=float(v))
    if body.config.servicio_pct < 0 or body.config.servicio_pct > 1:
        raise ErrorApi(422, "fb.servicio_fuera_de_rango",
                       valor=float(body.config.servicio_pct))
    # Comisionable es una fracción de la venta, igual que la captura: un 50
    # escrito donde va 0,50 dejaría el Food en negativo.
    if body.config.pct_comisionable < 0 or body.config.pct_comisionable > 1:
        raise ErrorApi(422, "fb.comisionable_fuera_de_rango",
                       valor=float(body.config.pct_comisionable))
    if body.config.bev_pct_food < 0:
        raise ErrorApi(422, "fb.bev_negativo", valor=float(body.config.bev_pct_food))

    cfg, meses = await _cargar(db, scenario_id)
    if cfg is None:
        cfg = FbPlanConfig(scenario_id=scenario_id)
        db.add(cfg)
    for campo, valor in body.config.model_dump().items():
        setattr(cfg, campo, valor)
    cfg.actualizado_en = datetime.utcnow()
    cfg.actualizado_por = getattr(user, "email", "") or ""

    for m in body.meses:
        if m.month < 1 or m.month > 12:
            raise ErrorApi(400, "mes.fuera_de_rango")
        fila = meses.get(m.month)
        if fila is None:
            fila = FbPlanMes(scenario_id=scenario_id, month=m.month)
            db.add(fila)
        fila.pax_externos = m.pax_externos
        fila.ticket_externos = m.ticket_externos
        fila.actualizado_en = datetime.utcnow()
        fila.actualizado_por = getattr(user, "email", "") or ""

    await db.commit()
    return await ver(scenario_id, db)


@router.post("/fb-plan/{scenario_id}/pasar-al-checkbook/")
async def pasar_al_checkbook(scenario_id: str, db: AsyncSession = Depends(get_db),
                             _=Depends(get_current_user)):
    """Escribe FOOD y BEVERAGE del checkbook con lo que calculó esta pantalla.

    Sólo esas dos líneas. Las demás del checkbook —Spa, Tours, Laundry— son de
    otro dueño y no tienen por qué moverse porque acá se cambió un precio.
    """
    await candado(db, scenario_id)
    from app.models.revenue_entry import RevenueEntry

    cfg, meses = await _cargar(db, scenario_id)
    if cfg is None:
        raise ErrorApi(422, "fb.sin_configuracion")
    pax = await _pax_por_mes(db, scenario_id)
    factor = await _factor_por_mes(db, scenario_id)

    MES_COL = ["jan", "feb", "mar", "apr", "may", "jun",
               "jul", "aug", "sep", "oct", "nov", "dec"]
    calc = {m: calcular_mes(cfg, meses.get(m), pax.get(m, Decimal("0")), factor[m])
            for m in MESES}

    actuales = {e.line.upper(): e for e in (await db.execute(
        select(RevenueEntry).where(RevenueEntry.scenario_id == scenario_id)
    )).scalars().all()}

    escritas = {}
    for linea, clave in (("FOOD", "food"), ("BEVERAGE", "beverage")):
        fila = actuales.get(linea)
        if fila is None:
            esc = await db.get(Scenario, scenario_id)
            fila = RevenueEntry(scenario_id=scenario_id,
                                hotel_id=esc.hotel_id, line=linea)
            db.add(fila)
        total = Decimal("0")
        for i, m in enumerate(MESES):
            v = Decimal(str(calc[m][clave])).quantize(Decimal("0.01"))
            setattr(fila, MES_COL[i], v)
            total += v
        escritas[linea] = str(total)

    await db.commit()
    return {"scenario_id": scenario_id, "escritas": escritas,
            "nota": "fb.recalcular_despues"}
