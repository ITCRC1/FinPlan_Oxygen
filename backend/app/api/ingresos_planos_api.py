# -*- coding: utf-8 -*-
"""Las líneas de ingreso que se digitan: un monto por mes y nada más.

Owner, 2026-10-08: *«todas las líneas de ingreso deben estar acá; si meto otras
que no están deben aparecer acá»*.

## El agujero que esto cierra

En modo `drivers` el checkbook **es un espejo**: cada recálculo lo reescribe
desde el modelo (`recalculate.sincronizar_ingreso_derivado`). Así que digitar
ahí no sirve — se borra, en silencio, y el P&L sigue cuadrando contra el
número equivocado. Eso le pasó al A&B de Oxygen el 2026-10-08.

La fuente de verdad de las líneas planas en ese modo es `RevenueOther`, y hasta
hoy **sólo la escribían los drivers que tenían pantalla propia**: el Spa y el
Club. El resto —Tours, Transporte, Retail, Lavandería, Innoceana, Tienda,
Misceláneos…— no tenía dónde digitarse. Medido en Oxygen: $108.521 de Tours,
$100.481 de Transporte y $47.876 de misceláneos reales, contra cero
presupuestable y ningún aviso.

## Por qué una pantalla sola y no trece

La lista sale de `OTHER_REVENUE_LINES`, que a su vez se deriva de
`REVENUE_LINES`. Una línea de ingreso nueva aparece acá **sin tocar este
archivo** — que es literalmente lo que pidió el owner. Escribir la lista a mano
sería repetir el error que dejó al Club afuera del motor.

## Lo que NO se puede tocar desde acá

Las líneas con driver propio (`_CON_DRIVER`). Su monto lo calcula otra pantalla
—el Spa con su capture rate, el Club con su cuota— y dejar que se escriban
también acá daría dos verdades: la última en guardar gana y nadie sabría cuál
fue. Se devuelven igual, marcadas y de sólo lectura, porque esconderlas haría
que el cuadro no sume el ingreso del escenario.

## Se escribe en las dos fuentes

Vía `persistir_ingreso_de_driver`, igual que cualquier driver: el monto queda
en `RevenueEntry` y en `RevenueOther`, así que el número es el mismo en los dos
modos y el departamento no tiene que saber en cuál está su escenario.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._candado import candado
from app.api._ingreso_de_driver import persistir_ingreso_de_driver
from app.auth import get_current_user
from app.db import get_db
from app.errores import ErrorApi
from app.models.revenue_entry import REVENUE_LINE_LABELS, RevenueEntry
from app.models.revenue_other import OTHER_REVENUE_LINES, RevenueOther
from app.models.scenario import Scenario

router = APIRouter()

MESES = list(range(1, 13))
_COLS = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]

#: Línea → pantalla que la calcula. Mientras tenga dueño, acá es de lectura.
_CON_DRIVER = {
    "SPA": "revenue/spa",
    "CLUB": "revenue/club",
    "CLUB_ACTIVIDAD": "revenue/club",
    "CLUB_VISITANTES": "revenue/club",
}


def _d(v) -> str:
    return str(Decimal(str(v or 0)))


async def _ver(scenario_id: str, db: AsyncSession):
    esc = await db.get(Scenario, scenario_id)
    if not esc:
        raise ErrorApi(404, "escenario.no_encontrado")

    modo = getattr(esc, "revenue_source", "drivers")
    # En `drivers` manda `RevenueOther` —el checkbook es espejo—; en `checkbook`
    # manda `RevenueEntry`, que es lo que el usuario digita. Leer siempre la
    # misma tabla mostraría una copia vieja en uno de los dos modos.
    valores: dict[str, list[Decimal]] = {}
    if modo == "checkbook":
        for e in (await db.execute(select(RevenueEntry).where(
                RevenueEntry.scenario_id == scenario_id))).scalars():
            valores[e.line.upper()] = [
                Decimal(str(getattr(e, c) or 0)) for c in _COLS]
    else:
        for o in (await db.execute(select(RevenueOther).where(
                RevenueOther.scenario_id == scenario_id))).scalars():
            fila = valores.setdefault(o.line.upper(), [Decimal("0")] * 12)
            if 1 <= o.month <= 12:
                fila[o.month - 1] = Decimal(str(o.amount_usd or 0))

    lineas = []
    for ln in OTHER_REVENUE_LINES:
        montos = valores.get(ln, [Decimal("0")] * 12)
        lineas.append({
            "line": ln,
            "label": REVENUE_LINE_LABELS.get(ln, ln),
            "driver": _CON_DRIVER.get(ln),
            "meses": [_d(v) for v in montos],
            "total": _d(sum(montos, Decimal("0"))),
        })
    return {
        "scenario_id": scenario_id,
        "locked": esc.is_locked,
        "revenue_source": modo,
        "lineas": lineas,
        "total": _d(sum((Decimal(l["total"]) for l in lineas), Decimal("0"))),
    }


@router.get("/scenarios/{scenario_id}/revenue/planos/")
async def ver(scenario_id: str, db: AsyncSession = Depends(get_db),
              _=Depends(get_current_user)):
    return await _ver(scenario_id, db)


class LineaBody(BaseModel):
    line: str
    meses: list[Decimal]


@router.put("/scenarios/{scenario_id}/revenue/planos/")
async def guardar(scenario_id: str, body: list[LineaBody],
                  db: AsyncSession = Depends(get_db),
                  _=Depends(get_current_user)):
    await candado(db, scenario_id)
    esc = await db.get(Scenario, scenario_id)
    if not esc:
        raise ErrorApi(404, "escenario.no_encontrado")

    montos: dict[str, list[Decimal]] = {}
    for fila in body:
        ln = (fila.line or "").upper()
        if ln not in OTHER_REVENUE_LINES:
            raise ErrorApi(422, "ingreso.linea_no_es_plana", linea=ln)
        if ln in _CON_DRIVER:
            raise ErrorApi(409, "ingreso.linea_con_driver",
                           linea=REVENUE_LINE_LABELS.get(ln, ln),
                           pantalla=_CON_DRIVER[ln])
        if len(fila.meses) != 12:
            raise ErrorApi(422, "ingreso.doce_meses",
                           linea=ln, cuantos=len(fila.meses))
        montos[ln] = [Decimal(str(v or 0)) for v in fila.meses]

    if montos:
        await persistir_ingreso_de_driver(db, esc, montos)
        await db.commit()
    return await _ver(scenario_id, db)
