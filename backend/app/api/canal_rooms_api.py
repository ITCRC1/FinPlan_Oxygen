# -*- coding: utf-8 -*-
"""Planning → Channel Rooms Calculation: el modelo de Rooms por segmento.

Owner, 2026-10-15: *«me gustaría que hagas otro tab para cálculo de rooms
revenue… en un sub tab en planning llamado Channel Rooms Calculation, y en sub
tab metas todos los tabs que se necesiten para poder llegar al número final ya
todo organizado… hay que dejar editable los drivers que activan los cálculos»*.

## Las cuatro puertas

    GET  /canal-rooms/segmentos/              el catalogo de la propiedad
    PUT  /canal-rooms/segmentos/              editarlo (agregar un canal nuevo)
    GET  /canal-rooms/{escenario}/            la grilla: segmento x mes
    PUT  /canal-rooms/{escenario}/            guardar noches y tarifa
    GET  /canal-rooms/{escenario}/estadisticas/   el cuadro de salida
    POST /canal-rooms/{escenario}/importar/   subir el libro de Sales
    PATCH /canal-rooms/{escenario}/fuente/    conectar o desconectar el modelo

## ⚠️ Nada llega al P&L hasta que se conecta

`PATCH .../fuente/` cambia `Scenario.rooms_source`, y recien ahi el recalculo
toma Rooms de aca (`recalculate.aplicar_canales_rooms`). Hasta entonces esto se
llena, se mira y se compara contra el modelo de tarifas sin mover un numero del
reporte — que es como el owner lo pidio: *«que funcione bien y después
conectarlo»*.

## Las noches disponibles NO se digitan

Salen de unidades x dias, igual que en el modelo de tarifas. Que el libro de
Sales las traiga calculadas no las vuelve un dato: son el denominador de la
ocupacion en los dos modelos y tener dos origenes es tener dos ocupaciones.
"""
from calendar import monthrange
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._candado import candado
from app.importers.registro_dep import registro_de_subida
from app.auth import get_current_user
from app.db import get_db
from app.errores import ErrorApi
from app.models.canal_rooms import (CanalSegmento, CanalRoomsEntry,
                                    SEGMENTOS_SEMILLA, calcular_mes, derivar)
from app.models.room_type_config import RoomTypeConfig
from app.models.scenario import Scenario

router = APIRouter()
MESES = list(range(1, 13))
FUENTES = ("tarifas", "canales")


def _d(v) -> str:
    return str(Decimal(str(v or 0)))


async def _segmentos(db: AsyncSession, hotel_id: str) -> list[CanalSegmento]:
    """El catalogo de la propiedad. Si no existe todavia, se siembra.

    Se siembra con los ocho del libro de Sales porque son los que el grupo usa,
    pero queda editable: una propiedad que venda por un canal distinto lo agrega
    y aparece en todas partes sin tocar codigo.
    """
    filas = (await db.execute(select(CanalSegmento).where(
        CanalSegmento.hotel_id == hotel_id).order_by(CanalSegmento.orden)
    )).scalars().all()
    if filas:
        return filas
    for i, (code, nombre, genera) in enumerate(SEGMENTOS_SEMILLA):
        db.add(CanalSegmento(hotel_id=hotel_id, code=code, nombre=nombre,
                             genera_ingreso=genera, orden=i))
    await db.commit()
    return (await db.execute(select(CanalSegmento).where(
        CanalSegmento.hotel_id == hotel_id).order_by(CanalSegmento.orden)
    )).scalars().all()


async def _disponibles(db: AsyncSession, esc: Scenario) -> dict[int, Decimal]:
    """Noches disponibles por mes: unidades x dias del mes.

    Mismo calculo que el motor de tarifas, y a proposito: si los dos caminos
    tuvieran denominadores distintos, la ocupacion cambiaria al cambiar de
    modelo sin que se hubiera movido una noche.
    """
    tipos = (await db.execute(select(RoomTypeConfig).where(
        RoomTypeConfig.hotel_id == esc.hotel_id,
        RoomTypeConfig.active.is_(True)))).scalars().all()
    unidades = sum(int(t.units or 0) for t in tipos)
    from app.models.scenario_master import ScenarioMaster
    sm = (await db.execute(select(ScenarioMaster).where(
        ScenarioMaster.scenario_id == esc.id))).scalar_one_or_none()
    if sm and sm.units_json:
        import json
        try:
            porid = {t.id: int(t.units or 0) for t in tipos}
            porid.update({k: int(v) for k, v in json.loads(sm.units_json).items()
                          if k in porid})
            unidades = sum(porid.values())
        except (ValueError, TypeError):
            pass
    return {m: Decimal(unidades * monthrange(esc.year, m)[1]) for m in MESES}


async def _ver(scenario_id: str, db: AsyncSession) -> dict:
    esc = await db.get(Scenario, scenario_id)
    if not esc:
        raise ErrorApi(404, "escenario.no_encontrado")
    segs = await _segmentos(db, esc.hotel_id)
    genera = {s.code: bool(s.genera_ingreso) for s in segs}
    disp = await _disponibles(db, esc)

    filas = (await db.execute(select(CanalRoomsEntry).where(
        CanalRoomsEntry.scenario_id == scenario_id))).scalars().all()
    por_mes: dict[int, list] = {m: [] for m in MESES}
    for f in filas:
        if 1 <= int(f.month) <= 12:
            por_mes[int(f.month)].append(f)

    meses, anio = [], None
    for m in MESES:
        calc = calcular_mes(por_mes[m], genera, disp[m])
        meses.append({
            "month": m,
            **{k: _d(v) for k, v in calc.items() if k != "segmentos"},
            "segmentos": {c: {kk: _d(vv) for kk, vv in d.items()}
                          for c, d in calc["segmentos"].items()},
        })
        anio = calc if anio is None else anio

    # El total del año se SUMA; el ADR y el RevPAR se recalculan sobre las sumas,
    # porque un promedio de promedios no es el promedio.
    tot_n_ing = sum(Decimal(x["noches_ingreso"]) for x in meses)
    tot_n_tot = sum(Decimal(x["noches_totales"]) for x in meses)
    tot_ing = sum(Decimal(x["ingreso"]) for x in meses)
    tot_disp = sum(Decimal(x["disponibles"]) for x in meses)
    total = {
        "disponibles": _d(tot_disp), "noches_ingreso": _d(tot_n_ing),
        "noches_totales": _d(tot_n_tot), "ingreso": _d(tot_ing),
        "ocupacion": _d(tot_n_ing / tot_disp if tot_disp else 0),
        "ocupacion_total": _d(tot_n_tot / tot_disp if tot_disp else 0),
        "adr": _d(tot_ing / tot_n_ing if tot_n_ing else 0),
        "revpar": _d(tot_ing / tot_disp if tot_disp else 0),
        "segmentos": {
            s.code: {
                "noches": _d(sum(Decimal(x["segmentos"].get(s.code, {}).get("noches", 0))
                                 for x in meses)),
                "ingreso": _d(sum(Decimal(x["segmentos"].get(s.code, {}).get("ingreso", 0))
                                  for x in meses)),
            } for s in segs},
    }
    return {
        "scenario_id": scenario_id,
        "locked": esc.is_locked,
        "rooms_source": getattr(esc, "rooms_source", "tarifas"),
        "conectado": getattr(esc, "rooms_source", "tarifas") == "canales",
        "year": esc.year,
        "segmentos": [{"code": s.code, "nombre": s.nombre, "orden": s.orden,
                       "genera_ingreso": bool(s.genera_ingreso)} for s in segs],
        "meses": meses,
        "total": total,
        "entradas": [{"segmento_code": f.segmento_code, "month": f.month,
                      "noches": _d(f.noches), "tarifa": _d(f.tarifa),
                      "ingreso": _d(f.ingreso),
                      "tarifa_digitada": bool(f.tarifa_digitada)} for f in filas],
    }


async def _anio(db: AsyncSession, esc: Scenario) -> dict:
    """Los doce meses de UN escenario, ya calculados. Pieza del comparativo."""
    segs = await _segmentos(db, esc.hotel_id)
    genera = {x.code: bool(x.genera_ingreso) for x in segs}
    disp = await _disponibles(db, esc)
    filas = (await db.execute(select(CanalRoomsEntry).where(
        CanalRoomsEntry.scenario_id == esc.id))).scalars().all()
    por_mes: dict[int, list] = {m: [] for m in MESES}
    for f in filas:
        if 1 <= int(f.month) <= 12:
            por_mes[int(f.month)].append(f)
    meses = {m: calcular_mes(por_mes[m], genera, disp[m]) for m in MESES}

    # El año: las magnitudes se SUMAN y los promedios se recalculan sobre las
    # sumas. Un promedio de promedios no es el promedio — con meses de volumen
    # muy distinto, el ADR del año saldria corrido varios dolares.
    n_ing = sum(meses[m]["noches_ingreso"] for m in MESES)
    n_tot = sum(meses[m]["noches_totales"] for m in MESES)
    ing = sum(meses[m]["ingreso"] for m in MESES)
    d_tot = sum(meses[m]["disponibles"] for m in MESES)
    anio = {
        "disponibles": d_tot, "noches_ingreso": n_ing, "noches_totales": n_tot,
        "ingreso": ing,
        "ocupacion": (n_ing / d_tot) if d_tot else Decimal(0),
        "ocupacion_total": (n_tot / d_tot) if d_tot else Decimal(0),
        "adr": (ing / n_ing) if n_ing else Decimal(0),
        "revpar": (ing / d_tot) if d_tot else Decimal(0),
        "segmentos": {
            c: {"noches": sum(meses[m]["segmentos"].get(c, {}).get("noches", Decimal(0))
                              for m in MESES),
                "ingreso": sum(meses[m]["segmentos"].get(c, {}).get("ingreso", Decimal(0))
                               for m in MESES)}
            for c in genera},
    }
    return {"meses": meses, "anio": anio, "segmentos": segs}


#: Las metricas que el libro de Sales muestra mes a mes, en su orden.
BLOQUES = (("ingreso", "TOTAL INGRESOS ($)", "usd"),
           ("noches_ingreso", "ROOM NIGHTS (noches que generan ingreso)", "num"),
           ("adr", "TARIFA PROMEDIO · ADR ($)", "usd"),
           ("ocupacion", "% OCUPACIÓN", "pct"),
           ("revpar", "RevPAR ($)", "usd"),
           ("disponibles", "HABITACIONES DISPONIBLES", "num"))


@router.get("/canal-rooms/{scenario_id}/estadisticas/")
async def estadisticas(scenario_id: str, comparar: str = "",
                       db: AsyncSession = Depends(get_db),
                       _=Depends(get_current_user)):
    """Los nueve cuadros de «Estadísticas Revenue», comparando versiones.

    Owner, 2026-10-15: *«revisa nuevamente este tab Estadísticas Revenue y
    favor recrea todos los reportes que hay ahí»*.

    ⚠️ **Las columnas son VERSIONES, no meses.** En el libro de Sales son seis
    —Budget 2027, Proyección, OTB, Budget 2026, Real+OTB 2026, Real 2025— y en
    FinPlan cada una es un ESCENARIO. Por eso el reporte recibe `comparar`: el
    archivo no sabe de escenarios y quien decide el pareo es el usuario.

    `Real+OTB 2026` no necesita logica propia: en FinPlan es el Forecast con su
    corte de actuales, que ya mezcla real y proyectado por diseño.
    """
    base = await db.get(Scenario, scenario_id)
    if not base:
        raise ErrorApi(404, "escenario.no_encontrado")
    ids = [scenario_id] + [x for x in comparar.split(",") if x.strip()]
    vistos, orden = set(), []
    for i in ids:                       # sin repetir, conservando el orden
        if i not in vistos:
            vistos.add(i)
            orden.append(i)

    cols, datos = [], {}
    for sid in orden:
        esc = await db.get(Scenario, sid)
        if not esc:
            continue
        cols.append({"scenario_id": sid, "year": esc.year,
                     "etiqueta": f"{esc.type} {esc.version} {esc.year}"})
        datos[sid] = await _anio(db, esc)
    if not cols:
        raise ErrorApi(404, "escenario.no_encontrado")

    def celda(sid, mes, campo):
        d = datos[sid]
        v = d["anio"][campo] if mes == 13 else d["meses"][mes][campo]
        return _d(v)

    # ── 1 a 6 · las metricas mes a mes ──────────────────────────────────────
    bloques = [{
        "clave": campo, "titulo": titulo, "formato": fmt,
        "filas": [{"month": m,
                   "valores": [celda(c["scenario_id"], m, campo) for c in cols]}
                  for m in MESES + [13]],
    } for campo, titulo, fmt in BLOQUES]

    # ── 7 · variaciones de la BASE contra cada comparado ────────────────────
    def var(sid, mes, campo, puntos=False):
        a = Decimal(celda(orden[0], mes, campo))
        b = Decimal(celda(sid, mes, campo))
        if puntos:                       # ocupacion: la diferencia es en PUNTOS
            return _d(a - b)
        return _d((a - b) / b) if b else "0"

    variaciones = {
        "contra": [c for c in cols[1:]],
        "metricas": [("ingreso", "Ingreso %", False), ("noches_ingreso", "Room Nights %", False),
                     ("adr", "ADR %", False), ("ocupacion", "Ocupación pts", True)],
        "filas": [{"month": m, "valores": [
            {"scenario_id": c["scenario_id"],
             "v": [var(c["scenario_id"], m, campo, pts)
                   for campo, _et, pts in (("ingreso", "", False),
                                           ("noches_ingreso", "", False),
                                           ("adr", "", False),
                                           ("ocupacion", "", True))]}
            for c in cols[1:]]} for m in MESES + [13]],
    }

    # ── 8 · por segmento, sin los que no generan ingreso ────────────────────
    segs = datos[orden[0]]["segmentos"]

    def seg_val(sid, mes, code, campo):
        d = datos[sid]
        src = d["anio"] if mes == 13 else d["meses"][mes]
        return _d(src["segmentos"].get(code, {}).get(campo, 0))

    por_segmento = [{
        "code": sg.code, "nombre": sg.nombre,
        "filas": [{"month": m,
                   "ingreso": [seg_val(c["scenario_id"], m, sg.code, "ingreso")
                               for c in cols],
                   "noches": [seg_val(c["scenario_id"], m, sg.code, "noches")
                              for c in cols]}
                  for m in MESES + [13]],
    } for sg in segs if sg.genera_ingreso]

    # ── 9 · mix del año, y el chequeo contra el total ───────────────────────
    tot_por_col = [Decimal(datos[c["scenario_id"]]["anio"]["ingreso"]) for c in cols]
    suma_seg = [sum(Decimal(datos[c["scenario_id"]]["anio"]["segmentos"]
                            .get(sg.code, {}).get("ingreso", 0))
                    for sg in segs if sg.genera_ingreso) for c in cols]
    mix = {
        "filas": [{
            "code": sg.code, "nombre": sg.nombre,
            "ingreso": [_d(datos[c["scenario_id"]]["anio"]["segmentos"]
                           .get(sg.code, {}).get("ingreso", 0)) for c in cols],
            "mix": [_d((Decimal(datos[c["scenario_id"]]["anio"]["segmentos"]
                                .get(sg.code, {}).get("ingreso", 0)) / t) if t else 0)
                    for c, t in zip(cols, suma_seg)],
        } for sg in segs if sg.genera_ingreso],
        "total_segmentos": [_d(v) for v in suma_seg],
        "total_ingresos": [_d(v) for v in tot_por_col],
        # ⚠️ El chequeo del libro de Sales: la suma de los segmentos contra el
        # total. Distinto de cero significa que hay ingreso en un segmento que
        # el cuadro no esta mostrando — o cortesias con plata, que no deberian.
        "chequeo": [_d(a - b) for a, b in zip(suma_seg, tot_por_col)],
    }

    return {"scenario_id": scenario_id, "columnas": cols, "bloques": bloques,
            "variaciones": variaciones, "por_segmento": por_segmento, "mix": mix}


@router.get("/canal-rooms/{scenario_id}/")
async def ver(scenario_id: str, db: AsyncSession = Depends(get_db),
              _=Depends(get_current_user)):
    return await _ver(scenario_id, db)


class EntradaBody(BaseModel):
    segmento_code: str
    month: int
    noches: Decimal = Decimal("0")
    tarifa: Decimal = Decimal("0")
    ingreso: Decimal = Decimal("0")
    tarifa_digitada: bool = True


@router.put("/canal-rooms/{scenario_id}/")
async def guardar(scenario_id: str, body: list[EntradaBody],
                  db: AsyncSession = Depends(get_db),
                  user=Depends(get_current_user)):
    await candado(db, scenario_id)
    esc = await db.get(Scenario, scenario_id)
    if not esc:
        raise ErrorApi(404, "escenario.no_encontrado")
    validos = {s.code for s in await _segmentos(db, esc.hotel_id)}

    actuales = {(f.segmento_code, f.month): f for f in (await db.execute(
        select(CanalRoomsEntry).where(
            CanalRoomsEntry.scenario_id == scenario_id))).scalars().all()}

    for e in body:
        if e.segmento_code not in validos:
            raise ErrorApi(422, "canal.segmento_desconocido", code=e.segmento_code)
        if not 1 <= e.month <= 12:
            raise ErrorApi(400, "mes.fuera_de_rango")
        if e.noches < 0:
            raise ErrorApi(422, "canal.noches_negativas",
                           code=e.segmento_code, mes=e.month)
        tarifa, ingreso = derivar(e.noches, e.tarifa, e.ingreso, e.tarifa_digitada)
        fila = actuales.get((e.segmento_code, e.month))
        if fila is None:
            fila = CanalRoomsEntry(scenario_id=scenario_id, hotel_id=esc.hotel_id,
                                   segmento_code=e.segmento_code, month=e.month)
            db.add(fila)
        fila.noches = e.noches
        fila.tarifa = tarifa
        fila.ingreso = ingreso
        fila.tarifa_digitada = e.tarifa_digitada
        fila.actualizado_en = datetime.utcnow()
        fila.actualizado_por = getattr(user, "email", "") or ""

    await db.commit()
    return await _ver(scenario_id, db)


@router.patch("/canal-rooms/{scenario_id}/fuente/")
async def conectar(scenario_id: str, fuente: str = Form(...),
                   db: AsyncSession = Depends(get_db),
                   _=Depends(get_current_user)):
    """El interruptor: de que modelo sale Rooms en este escenario.

    No recalcula. El numero del P&L cambia en el siguiente recalculo, que es
    cuando el usuario lo pide — el mismo trato que el resto del sistema.
    """
    await candado(db, scenario_id)
    if fuente not in FUENTES:
        raise ErrorApi(422, "canal.fuente_desconocida", fuente=fuente,
                       validas=", ".join(FUENTES))
    esc = await db.get(Scenario, scenario_id)
    if not esc:
        raise ErrorApi(404, "escenario.no_encontrado")
    esc.rooms_source = fuente
    await db.commit()
    return {"scenario_id": scenario_id, "rooms_source": fuente,
            "nota": "canal.recalcular_despues"}


@router.post("/canal-rooms/{scenario_id}/versiones-del-archivo/",
             dependencies=[Depends(registro_de_subida)])
async def versiones_del_archivo(scenario_id: str, archivo: UploadFile = File(...),
                                _=Depends(get_current_user)):
    """Que versiones trae el libro, para que el usuario elija cual importar.

    El archivo no sabe de escenarios de FinPlan: trae «Real 2026», «OTB 2027
    10/26»… y quien decide a que escenario va cada una es el usuario.
    """
    import tempfile
    from app.importers.canal_rooms_importer import versiones_del_libro
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(await archivo.read())
        ruta = tmp.name
    return {"versiones": versiones_del_libro(ruta)}


@router.post("/canal-rooms/{scenario_id}/importar/",
             dependencies=[Depends(registro_de_subida)])
async def importar(scenario_id: str, archivo: UploadFile = File(...),
                   version: str = Form(...), aplicar: bool = Form(False),
                   db: AsyncSession = Depends(get_db),
                   user=Depends(get_current_user)):
    """Sube una version del libro de Sales a este escenario.

    ⚠️ `aplicar=False` (el default) solo LEE y devuelve lo que encontro. Nada se
    escribe hasta que alguien lo mira y vuelve con `aplicar=True`: un importador
    que escribe antes de mostrar es un importador en el que no se puede confiar
    cuando dice que todo salio bien.
    """
    import tempfile
    from app.importers.canal_rooms_importer import leer, _norm

    await candado(db, scenario_id)
    esc = await db.get(Scenario, scenario_id)
    if not esc:
        raise ErrorApi(404, "escenario.no_encontrado")
    segs = await _segmentos(db, esc.hotel_id)
    catalogo = {_norm(s.nombre): s.code for s in segs}

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(await archivo.read())
        ruta = tmp.name
    res = leer(ruta, version, catalogo)
    if not res["datos"]:
        raise ErrorApi(422, "canal.version_vacia", version=version)

    resumen = {"version": version, "meses": res["meses"],
               "desconocidos": res["desconocidos"], "celdas": len(res["datos"]),
               "noches": _d(sum(d.get("noches", 0) for d in res["datos"].values())),
               "ingreso": _d(sum(d.get("ingreso", 0) for d in res["datos"].values())),
               "aplicado": False}
    if not aplicar:
        return resumen

    actuales = {(f.segmento_code, f.month): f for f in (await db.execute(
        select(CanalRoomsEntry).where(
            CanalRoomsEntry.scenario_id == scenario_id))).scalars().all()}
    for (code, mes), d in res["datos"].items():
        noches = d.get("noches", Decimal("0"))
        # El libro trae el ingreso ya calculado; la tarifa es su promedio. Se
        # guarda el ingreso como vino y la tarifa se deriva — al reves se
        # perderia el centavo del redondeo contra el reporte de Sales.
        tarifa, ingreso = derivar(noches, d.get("tarifa"), d.get("ingreso"),
                                  tarifa_digitada="ingreso" not in d)
        fila = actuales.get((code, mes))
        if fila is None:
            fila = CanalRoomsEntry(scenario_id=scenario_id, hotel_id=esc.hotel_id,
                                   segmento_code=code, month=mes)
            db.add(fila)
        fila.noches, fila.tarifa, fila.ingreso = noches, tarifa, ingreso
        fila.tarifa_digitada = "ingreso" not in d
        fila.actualizado_en = datetime.utcnow()
        fila.actualizado_por = getattr(user, "email", "") or ""
    await db.commit()
    resumen["aplicado"] = True
    return resumen
