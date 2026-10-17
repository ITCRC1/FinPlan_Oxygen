# -*- coding: utf-8 -*-
"""Planning → Rack Rooms Calculation: el libro del owner, puerta por puerta.

Owner, 2026-10-16: *«me interesa clonar el tab KPIs RACK y el tab Origen Tarifa
Rac y la base de datos viene desde el tab llamado Resumen Mensual. Favor crea un
modelo donde yo pueda modificar las variables inputs y que derive todo lo
demás»*.

## Qué se digita y qué sale solo

    SE DIGITA                          SALE SOLO
    unidades y RAC por villa           RAC del mes por villa
    rangos de temporada                RAC ponderado del mes
    % de comisión por segmento         tarifa neta por segmento
    noches por segmento × mes          ingreso rack, ingreso neto, ADR, RevPAR

Las seis puertas siguen ese corte: cuatro `PUT` para los cuatro inputs, un `GET`
que devuelve TODO lo derivado, y un `PATCH` que conecta el modelo al P&L.

    GET   /rack-rooms/{escenario}/              todo: inputs + derivados + KPIs
    PUT   /rack-rooms/{escenario}/villas/       unidades y RAC
    PUT   /rack-rooms/{escenario}/temporadas/   los rangos de fecha
    PUT   /rack-rooms/{escenario}/comisiones/   el % por segmento
    PUT   /rack-rooms/{escenario}/noches/       la grilla de noches
    PATCH /rack-rooms/{escenario}/fuente/       conectar o desconectar

## ⚠️ Nada llega al P&L hasta que se conecta

`PATCH .../fuente/` cambia `Scenario.rooms_source`. Hasta entonces esto se
llena, se mira y se compara sin mover un número del reporte. Es el mismo trato
que en Oxygen, y por la misma razón: un modelo nuevo tiene que poder armarse al
lado del que está en producción.

## ⚠️ Lo derivado se GUARDA, no sólo se muestra

Cada `PUT` recalcula `canal_rooms_entries` (tarifa e ingreso) con el tarifario
vigente. Esa tabla es la ESTÁNDAR —la que lee `aplicar_canales_rooms` y, aguas
abajo, Hotel Consolidation—. Si la pantalla derivara al vuelo y la tabla
quedara vieja, el consolidado mostraría el ingreso de antes del cambio y nadie
lo notaría: el total seguiría cuadrando consigo mismo.

## Las noches disponibles salen del MISMO lugar que en el otro modelo

De `RoomTypeConfig` (+ el override del escenario), igual que
`revenue_calculator`. Las unidades del tarifario NO son el denominador: son un
input de la ponderación del RAC. Cuando no coinciden, el `GET` lo dice en
`controles.unidades` en vez de elegir una — dos denominadores distintos dan dos
ocupaciones para el mismo mes, y ninguna avisa.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._candado import candado
from app.importers.registro_dep import registro_de_subida
from app.auth import get_current_user
from app.db import get_db
from app.engine.rack_tarifa import (derivar_mes, dias_del_mes,
                                    dias_por_temporada, dias_sin_temporada,
                                    kpis_rack, rac_ponderado,
                                    rac_villa_mes, traslape)
from app.errores import ErrorApi
from app.models.canal_rooms import CanalRoomsEntry, CanalSegmento, calcular_mes
from app.models.rack_rooms import RackComision, RackTemporada, RackVilla
from app.models.room_type_config import RoomTypeConfig
from app.models.scenario import Scenario

router = APIRouter()
MESES = list(range(1, 13))
FUENTES = ("tarifas", "canales")
TEMPORADAS = ("PICO", "ALTA", "VERDE")


def _d(v) -> str:
    return str(Decimal(str(v or 0)))


class _FilaEnMemoria:
    """Una fila de `canal_rooms_entries` que nunca existió en la base.

    `calcular_mes` y `derivar_mes` reciben objetos con estos cinco atributos.
    Darles un objeto suelto en vez de una fila real es lo que permite calcular
    sobre lo tecleado sin escribir una línea.
    """
    __slots__ = ("segmento_code", "month", "noches", "tarifa", "ingreso")

    def __init__(self, segmento_code, month, noches, tarifa,
                 ingreso=Decimal("0")):
        self.segmento_code = segmento_code
        self.month = month
        self.noches = noches
        self.tarifa = tarifa
        self.ingreso = ingreso


class _ComisionEnMemoria:
    """Una fila de `rack_comisiones` que no está en la sesión.

    Existe para que la previsualización no tenga que tocar —y después
    expulsar— objetos de la base. Un objeto suelto no se puede guardar por
    accidente.
    """
    __slots__ = ("segmento_code", "month", "comision_pct", "tarifa_propia")

    def __init__(self, segmento_code, month, comision_pct, tarifa_propia):
        self.segmento_code = segmento_code
        self.month = month
        self.comision_pct = comision_pct
        self.tarifa_propia = tarifa_propia


def replicar_desde_enero(actual: dict[int, Decimal], pct: Decimal) -> dict[int, Decimal]:
    """Enero pasa a `pct` y arrastra a los meses que seguían a enero.

    Owner, 2026-10-16: *«pone el primer mes y se replica a los 12 meses y
    manual se cambia el mes que probablemente cambie»*.

    ⚠️ **No arrastra a los que alguien cambió a mano.** El caso es éste: enero
    en 25 %, julio corregido a 28 % porque la agencia subió, y después enero se
    toca otra vez —a 26 %— por otra razón. Con una réplica total, julio vuelve
    a 26 % en silencio: no falla, no avisa, y el total del año sigue cuadrando
    consigo mismo.

    **Pura a propósito**: la usan el guardado y la previsualización, y las dos
    tienen que replicar igual. Si la pantalla mostrara una réplica y el botón
    hiciera otra, lo que se ve no sería lo que se guarda.
    """
    antes = actual.get(1)
    fuera = dict(actual)
    for mes in range(1, 13):
        if mes == 1 or antes is None or fuera.get(mes) == antes:
            fuera[mes] = pct
    return fuera


def comisiones_del_mes(coms, mes: int) -> dict:
    """`{code: (pct, tarifa_propia)}` para ese mes, como lo pide el motor.

    ⚠️ **Un segmento sin fila para ese mes vende A RACK**, no gratis: la
    ausencia se lee como 0 %. Lo contrario —tratarla como 100 %— pondría el
    ingreso en cero sin que nada avise.

    `tarifa_propia` es del SEGMENTO y no del mes: se toma de cualquier fila que
    lo declare, porque *Long term* no tiene RAC en enero y sí en julio.
    """
    propias = {c.segmento_code for c in coms if c.tarifa_propia}
    fuera = {c.segmento_code: (c.comision_pct, c.segmento_code in propias)
             for c in coms if int(c.month or 1) == mes}
    # Los que tienen tarifa propia tienen que estar aunque no tengan fila en
    # ESE mes: si no, el motor los trataría como un segmento de rack normal.
    for code in propias:
        fuera.setdefault(code, (Decimal("0"), True))
    return fuera


async def _escenario(db: AsyncSession, scenario_id: str) -> Scenario:
    esc = await db.get(Scenario, scenario_id)
    if not esc:
        raise ErrorApi(404, "escenario.no_encontrado")
    return esc


async def _segmentos(db: AsyncSession, hotel_id: str) -> list[CanalSegmento]:
    """El catálogo de la propiedad, tal como lo dejó la semilla.

    ⚠️ **Si está vacío, se devuelve vacío.** No se siembra acá: la semilla es
    `seed_canal_segmentos` y corre en el deploy. Sembrar desde un `GET` haría
    que la lista dependa de quién abrió primero la pantalla.
    """
    return (await db.execute(select(CanalSegmento).where(
        CanalSegmento.hotel_id == hotel_id,
        CanalSegmento.activo.is_(True)).order_by(CanalSegmento.orden)
    )).scalars().all()


async def _unidades_del_hotel(db: AsyncSession, esc: Scenario) -> int:
    """Las unidades con las que se calculan las noches DISPONIBLES.

    Mismo origen que `revenue_calculator`: los tipos activos, con el override
    del escenario si lo hay. Que el tarifario tenga su propia cuenta de
    unidades no lo vuelve el denominador — ver `controles.unidades`.
    """
    tipos = (await db.execute(select(RoomTypeConfig).where(
        RoomTypeConfig.hotel_id == esc.hotel_id,
        RoomTypeConfig.active.is_(True)))).scalars().all()
    porid = {t.id: int(t.units or 0) for t in tipos}
    from app.models.scenario_master import ScenarioMaster
    sm = (await db.execute(select(ScenarioMaster).where(
        ScenarioMaster.scenario_id == esc.id))).scalar_one_or_none()
    if sm and sm.units_json:
        import json
        try:
            porid.update({k: int(v) for k, v in json.loads(sm.units_json).items()
                          if k in porid})
        except (ValueError, TypeError):
            pass
    return sum(porid.values())


async def _cargar(db: AsyncSession, esc: Scenario):
    villas = (await db.execute(select(RackVilla).where(
        RackVilla.scenario_id == esc.id).order_by(RackVilla.orden))).scalars().all()
    temps = (await db.execute(select(RackTemporada).where(
        RackTemporada.scenario_id == esc.id).order_by(RackTemporada.desde))).scalars().all()
    coms = (await db.execute(select(RackComision).where(
        RackComision.scenario_id == esc.id))).scalars().all()
    return villas, temps, coms


async def _rederivar(db: AsyncSession, esc: Scenario, user=None) -> int:
    """Recalcula tarifa e ingreso de `canal_rooms_entries` con el tarifario.

    Devuelve cuántas filas tocó. Sin villas o sin temporadas no toca ninguna:
    el RAC daría cero y pondría todo el ingreso en cero sin que nada avise.
    """
    villas, temps, coms = await _cargar(db, esc)
    if not (villas and temps):
        return 0
    filas = (await db.execute(select(CanalRoomsEntry).where(
        CanalRoomsEntry.scenario_id == esc.id))).scalars().all()
    por_mes: dict[int, list] = {}
    for f in filas:
        por_mes.setdefault(int(f.month), []).append(f)

    tocadas = 0
    for mes, delmes in por_mes.items():
        d = derivar_mes(villas, temps, comisiones_del_mes(coms, mes),
                        {f.segmento_code: f.noches for f in delmes},
                        esc.year, mes,
                        tarifas_propias={f.segmento_code: f.tarifa for f in delmes})
        for f in delmes:
            s = d["segmentos"].get(f.segmento_code)
            if not s:
                continue
            f.tarifa, f.ingreso = s["tarifa"], s["ingreso"]
            f.actualizado_en = datetime.utcnow()
            if user is not None:
                f.actualizado_por = getattr(user, "email", "") or ""
            tocadas += 1
    return tocadas


async def _ver(db: AsyncSession, scenario_id: str) -> dict:
    esc = await _escenario(db, scenario_id)
    segs = await _segmentos(db, esc.hotel_id)
    villas, temps, coms = await _cargar(db, esc)
    unidades_hotel = await _unidades_del_hotel(db, esc)
    filas = (await db.execute(select(CanalRoomsEntry).where(
        CanalRoomsEntry.scenario_id == scenario_id))).scalars().all()
    return _armar(esc, segs, villas, temps, coms, filas, unidades_hotel)


def _armar(esc, segs, villas, temps, coms, filas, unidades_hotel) -> dict:
    """El cuadro entero a partir de lo que ya se cargó. **No toca la base.**

    ⚠️ Existe separado de `_ver` para que la PREVISUALIZACIÓN use exactamente
    este código. La pantalla deriva mientras se teclea, y si derivara por su
    cuenta en el navegador habría dos implementaciones de la misma fórmula:
    una se corrige y la otra no, y la que se ve no es la que se guarda. Este
    repo ya pagó por un segundo motor de ingresos — ver `get_monthly_revenue`.
    """
    scenario_id = esc.id
    genera = {s.code: bool(s.genera_ingreso) for s in segs}
    por_mes: dict[int, list] = {m: [] for m in MESES}
    for f in filas:
        if 1 <= int(f.month) <= 12:
            por_mes[int(f.month)].append(f)

    hay_tarifario = bool(villas and temps)
    propias = {c.segmento_code for c in coms if c.tarifa_propia}
    meses = []
    for m in MESES:
        delmes = por_mes[m]
        disp = Decimal(unidades_hotel * dias_del_mes(esc.year, m))
        dias = dias_por_temporada(esc.year, m, temps)
        rac = rac_ponderado(villas, esc.year, m, temps) if hay_tarifario else Decimal("0")

        # Lo derivado se MUESTRA sin escribir: un `GET` no tiene por qué tocar
        # la base. Lo que se guarda lo guardan los `PUT`, vía `_rederivar`.
        derivado = (derivar_mes(villas, temps, comisiones_del_mes(coms, m),
                                {f.segmento_code: f.noches for f in delmes},
                                esc.year, m,
                                tarifas_propias={f.segmento_code: f.tarifa
                                                 for f in delmes})["segmentos"]
                    if hay_tarifario and delmes else {})
        # ⚠️ Se calcula sobre lo DERIVADO, no sobre el `ingreso` que trae la
        # fila. Dos razones, y la segunda es la que hizo falta:
        #
        #   · lo guardado puede ser de antes del último cambio de RAC o de
        #     comisión, y entonces el cuadro mostraría el ingreso viejo con las
        #     noches nuevas — cuadrando consigo mismo;
        #   · una fila que todavía no existe en la base (la previsualización)
        #     no tiene ingreso que leer, y el cuadro entero salía en CERO con
        #     las noches moviéndose. Medido el 2026-10-16: al subir Agencias de
        #     25 a 60 noches en enero, las noches pasaban de 2.263 a 2.298 y el
        #     ingreso del año se iba a $0,00.
        #
        # Las filas de la base NO se tocan: se calcula sobre copias. Mutarlas
        # acá las mandaría a la base en el próximo `commit` de otra ruta.
        base = delmes
        if derivado:
            base = [_FilaEnMemoria(
                f.segmento_code, m, f.noches,
                derivado.get(f.segmento_code, {}).get("tarifa", Decimal("0")),
                derivado.get(f.segmento_code, {}).get("ingreso", Decimal("0")))
                for f in delmes]
        calc = calcular_mes(base, genera, disp)
        # El lado RACK del mes. Owner, 2026-10-16: *«no veo en el app el cálculo
        # de rooms revenue a tarifa rack, sólo veo net»*. El neto es lo que
        # entra al P&L; el rack es contra lo que se mide el descuento — sin él,
        # la comisión se queda sin denominador.
        rk = kpis_rack(derivado, {f.segmento_code: f.noches for f in delmes},
                       genera, propias, disp)
        meses.append({
            "month": m,
            "dias": dias_del_mes(esc.year, m),
            "dias_por_temporada": {t: dias.get(t, 0) for t in TEMPORADAS},
            "dias_sin_temporada": dias_sin_temporada(esc.year, m, temps),
            "rac_ponderado": _d(rac),
            "rac_por_villa": {v.villa: _d(rac_villa_mes(v, esc.year, m, temps))
                              for v in villas},
            **{k: _d(v) for k, v in calc.items() if k != "segmentos"},
            "rack": {k: _d(v) for k, v in rk.items() if k != "mix_rack"},
            "mix_rack": {c: _d(v) for c, v in rk["mix_rack"].items()},
            "segmentos": {
                c: {**{kk: _d(vv) for kk, vv in d.items()},
                    "ingreso_rack": _d(derivado.get(c, {}).get("ingreso_rack", 0))}
                for c, d in calc["segmentos"].items()},
        })

    tot_disp = sum(Decimal(x["disponibles"]) for x in meses)
    tot_n_ing = sum(Decimal(x["noches_ingreso"]) for x in meses)
    tot_n_tot = sum(Decimal(x["noches_totales"]) for x in meses)
    tot_ing = sum(Decimal(x["ingreso"]) for x in meses)
    tot_rack = sum(Decimal(s["ingreso_rack"])
                   for x in meses for s in x["segmentos"].values())
    # El año SUMA las magnitudes y RECALCULA los promedios sobre las sumas: un
    # promedio de promedios no es el promedio, y con meses de volumen distinto
    # el ADR del año sale corrido varios dólares.
    total = {
        "disponibles": _d(tot_disp), "noches_ingreso": _d(tot_n_ing),
        "noches_totales": _d(tot_n_tot), "ingreso": _d(tot_ing),
        "ingreso_rack": _d(tot_rack),
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

    # El año a precio RACK. Las magnitudes se SUMAN y los promedios se
    # recalculan sobre las sumas — un promedio de promedios no es el promedio, y
    # con meses de volumen muy distinto el ADR del año sale corrido.
    rk_anio = kpis_rack(
        {s.code: {
            "ingreso": sum((Decimal(x["segmentos"].get(s.code, {}).get("ingreso", 0))
                            for x in meses), Decimal("0")),
            "ingreso_rack": sum((Decimal(x["segmentos"].get(s.code, {}).get("ingreso_rack", 0))
                                 for x in meses), Decimal("0")),
         } for s in segs},
        {s.code: sum((Decimal(x["segmentos"].get(s.code, {}).get("noches", 0))
                      for x in meses), Decimal("0")) for s in segs},
        genera, propias, tot_disp)
    total["rack"] = {k: _d(v) for k, v in rk_anio.items() if k != "mix_rack"}
    total["mix_rack"] = {c: _d(v) for c, v in rk_anio["mix_rack"].items()}

    unidades_tarifario = sum(int(v.unidades or 0) for v in villas)
    return {
        "scenario_id": scenario_id,
        "year": esc.year,
        "locked": esc.is_locked,
        "rooms_source": getattr(esc, "rooms_source", "tarifas"),
        "conectado": getattr(esc, "rooms_source", "tarifas") == "canales",
        "hay_tarifario": hay_tarifario,
        "villas": [{"villa": v.villa, "unidades": v.unidades,
                    "rac_pico": _d(v.rac_pico), "rac_alta": _d(v.rac_alta),
                    "rac_verde": _d(v.rac_verde), "orden": v.orden}
                   for v in villas],
        "temporadas": [{"temporada": t.temporada, "desde": t.desde.isoformat(),
                        "hasta": t.hasta.isoformat()} for t in temps],
        # Una fila por segmento y mes. La pantalla muestra enero y marca los
        # meses que se apartan — ver `guardar_comisiones`.
        "comisiones": [{"segmento_code": c.segmento_code,
                        "month": int(c.month or 1),
                        "comision_pct": _d(c.comision_pct),
                        "tarifa_propia": bool(c.tarifa_propia)} for c in coms],
        "segmentos": [{"code": s.code, "nombre": s.nombre, "orden": s.orden,
                       "genera_ingreso": bool(s.genera_ingreso)} for s in segs],
        "entradas": [{"segmento_code": f.segmento_code, "month": f.month,
                      "noches": _d(f.noches), "tarifa": _d(f.tarifa),
                      "ingreso": _d(f.ingreso)} for f in filas],
        "meses": meses,
        "total": total,
        # Los CONTROLES del libro: tienen que dar cero o coincidir. Se exponen
        # para que la pantalla los muestre, en vez de que alguien los descubra
        # tres meses después en una varianza que nadie sabe explicar.
        "controles": {
            "unidades": {
                "hotel": unidades_hotel,
                "tarifario": unidades_tarifario,
                "coinciden": unidades_hotel == unidades_tarifario,
            },
            "meses_sin_temporada": [x["month"] for x in meses
                                    if x["dias_sin_temporada"]],
            "segmentos_sin_comision": sorted(
                {s.code for s in segs if s.genera_ingreso}
                - set(comisiones_del_mes(coms, 1))),
        },
    }


@router.get("/rack-rooms/{scenario_id}/")
async def ver(scenario_id: str, db: AsyncSession = Depends(get_db),
              _=Depends(get_current_user)):
    return await _ver(db, scenario_id)


# ── Los cuatro inputs ────────────────────────────────────────────────────────
class VillaBody(BaseModel):
    villa: str
    unidades: int = 0
    rac_pico: Decimal = Decimal("0")
    rac_alta: Decimal = Decimal("0")
    rac_verde: Decimal = Decimal("0")
    orden: int = 0


@router.put("/rack-rooms/{scenario_id}/villas/")
async def guardar_villas(scenario_id: str, body: list[VillaBody],
                         db: AsyncSession = Depends(get_db),
                         user=Depends(get_current_user)):
    """Reemplaza el cuadro de villas del escenario.

    ⚠️ **Reemplaza**, no mezcla: una villa que se saca de la pantalla se saca
    del tarifario. Si sólo se agregaran, borrar una villa sería imposible desde
    el UI y su RAC seguiría pesando en el ponderado sin aparecer en ningún lado.
    """
    esc = await candado(db, scenario_id)
    vistos: set[str] = set()
    for v in body:
        if int(v.unidades or 0) < 0:
            raise ErrorApi(422, "rack.unidades_negativas", villa=v.villa)
        if v.villa in vistos:
            raise ErrorApi(422, "rack.villa_repetida", villa=v.villa)
        vistos.add(v.villa)

    for f in (await db.execute(select(RackVilla).where(
            RackVilla.scenario_id == scenario_id))).scalars().all():
        await db.delete(f)
    await db.flush()
    for i, v in enumerate(body):
        db.add(RackVilla(scenario_id=scenario_id, hotel_id=esc.hotel_id,
                         villa=v.villa, unidades=v.unidades,
                         rac_pico=v.rac_pico, rac_alta=v.rac_alta,
                         rac_verde=v.rac_verde,
                         orden=v.orden if v.orden else i))
    await db.flush()
    await _rederivar(db, esc, user)
    await db.commit()
    return await _ver(db, scenario_id)


class TemporadaBody(BaseModel):
    temporada: str
    desde: date
    hasta: date


@router.put("/rack-rooms/{scenario_id}/temporadas/")
async def guardar_temporadas(scenario_id: str, body: list[TemporadaBody],
                             db: AsyncSession = Depends(get_db),
                             user=Depends(get_current_user)):
    """Los rangos de temporada. Una temporada puede traer VARIOS.

    En 2027 «Pico» son dos: el arranque y el cierre del año. Por eso la llave
    incluye `desde`, y acá se valida el TRASLAPE en vez de la repetición del
    nombre.
    """
    esc = await candado(db, scenario_id)
    rangos = []
    for t in body:
        if t.temporada not in TEMPORADAS:
            raise ErrorApi(422, "rack.temporada_desconocida",
                           temporada=t.temporada, validas=", ".join(TEMPORADAS))
        if t.hasta < t.desde:
            raise ErrorApi(422, "rack.rango_invertido", temporada=t.temporada)
        rangos.append((t.desde, t.hasta, t.temporada))
    # ⚠️ El traslape no es un detalle de prolijidad: un día en dos temporadas se
    # cuenta dos veces, el RAC del mes sale inflado y el total cuadra consigo
    # mismo. `dias_sin_temporada` ve el hueco; la superposición no la ve nadie.
    choque = traslape(rangos)
    if choque:
        a, b, desde = choque
        raise ErrorApi(422, "rack.temporadas_traslapadas",
                       a=a, b=b, desde=desde.isoformat())

    for f in (await db.execute(select(RackTemporada).where(
            RackTemporada.scenario_id == scenario_id))).scalars().all():
        await db.delete(f)
    await db.flush()
    for t in body:
        db.add(RackTemporada(scenario_id=scenario_id, hotel_id=esc.hotel_id,
                             temporada=t.temporada, desde=t.desde, hasta=t.hasta))
    await db.flush()
    await _rederivar(db, esc, user)
    await db.commit()
    return await _ver(db, scenario_id)


class ComisionBody(BaseModel):
    segmento_code: str
    comision_pct: Decimal = Decimal("0")
    tarifa_propia: bool = False
    #: 1-12, o `None` = «es la de enero y se replica al resto del año».
    month: int | None = None


@router.put("/rack-rooms/{scenario_id}/comisiones/")
async def guardar_comisiones(scenario_id: str, body: list[ComisionBody],
                             db: AsyncSession = Depends(get_db),
                             user=Depends(get_current_user)):
    """La comisión de cada segmento, por mes.

    Owner, 2026-10-16: *«pone el primer mes y se replica a los 12 meses y
    manual se cambia el mes que probablemente cambie»*.

    ## Cómo se replica, y qué NO pisa

    Una fila **sin `month`** es enero y se replica al resto del año — pero
    **sólo a los meses que todavía valían lo mismo que enero**. Los que alguien
    cambió a mano se quedan como están.

    ⚠️ **Replicar a ciegas sería pérdida de datos sin aviso.** El caso es éste:
    se pone enero en 25 %, se corrige julio a 28 % porque la agencia subió, y
    después se vuelve a tocar enero —a 26 %— por otra razón. Con una réplica
    total, julio vuelve a 26 % en silencio y el ingreso de ese mes cambia sin
    que nadie lo haya pedido. No falla, no avisa, y el total del año sigue
    cuadrando consigo mismo.

    Una fila **con `month`** toca ese mes y nada más. Es el camino del cambio
    manual, y el de la grilla de doce columnas.

    ## `tarifa_propia` es del SEGMENTO

    Se escribe igual en los doce meses: *Long term* no tiene RAC en enero y sí
    en julio. Leerlo de un mes suelto daría distinto según el mes que se mire.
    """
    esc = await candado(db, scenario_id)
    validos = {s.code for s in await _segmentos(db, esc.hotel_id)}
    for c in body:
        if c.segmento_code not in validos:
            raise ErrorApi(422, "canal.segmento_desconocido", code=c.segmento_code)
        if c.month is not None and not 1 <= c.month <= 12:
            raise ErrorApi(400, "mes.fuera_de_rango")
        # Fuera de [0,1) no es un typo inocente: con 1 el ingreso queda en cero
        # y por encima se vuelve negativo — las dos cosas cuadran solas.
        if not (Decimal("0") <= c.comision_pct < Decimal("1")):
            raise ErrorApi(422, "rack.comision_fuera_de_rango",
                           code=c.segmento_code, pct=str(c.comision_pct))

    filas = (await db.execute(select(RackComision).where(
        RackComision.scenario_id == scenario_id))).scalars().all()
    por_clave = {(f.segmento_code, int(f.month or 1)): f for f in filas}

    def _fila(code: str, mes: int) -> RackComision:
        f = por_clave.get((code, mes))
        if f is None:
            f = RackComision(scenario_id=scenario_id, hotel_id=esc.hotel_id,
                             segmento_code=code, month=mes)
            db.add(f)
            por_clave[(code, mes)] = f
        return f

    for c in body:
        if c.month is not None:
            # Un mes puntual: el cambio manual.
            f = _fila(c.segmento_code, c.month)
            f.comision_pct = c.comision_pct
        else:
            # Enero manda y arrastra a los que seguían a enero.
            actual = {m: Decimal(str(por_clave[(c.segmento_code, m)].comision_pct))
                      for m in MESES if (c.segmento_code, m) in por_clave}
            for mes, pct in replicar_desde_enero(actual, c.comision_pct).items():
                _fila(c.segmento_code, mes).comision_pct = pct
        # Del segmento, no del mes: igual en los doce.
        for mes in MESES:
            _fila(c.segmento_code, mes).tarifa_propia = c.tarifa_propia

    await db.flush()
    await _rederivar(db, esc, user)
    await db.commit()
    return await _ver(db, scenario_id)


class NocheBody(BaseModel):
    segmento_code: str
    month: int
    noches: Decimal = Decimal("0")
    #: Sólo para los segmentos de tarifa propia (Long term no tiene RAC).
    tarifa: Decimal | None = None


@router.put("/rack-rooms/{scenario_id}/noches/")
async def guardar_noches(scenario_id: str, body: list[NocheBody],
                         db: AsyncSession = Depends(get_db),
                         user=Depends(get_current_user)):
    """La grilla: noches por segmento y mes. La tarifa sale del tarifario.

    `tarifa` sólo se toma para los segmentos marcados `tarifa_propia`. Mandarla
    para los demás no hace nada, y es a propósito: si la pantalla pudiera pisar
    la tarifa derivada, el RAC dejaría de explicar el ingreso y nadie sabría
    cuál de los dos manda.
    """
    esc = await candado(db, scenario_id)
    validos = {s.code for s in await _segmentos(db, esc.hotel_id)}
    propias = {c.segmento_code for c in (await db.execute(
        select(RackComision).where(
            RackComision.scenario_id == scenario_id,
            RackComision.tarifa_propia.is_(True)))).scalars().all()}

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
        fila = actuales.get((e.segmento_code, e.month))
        if fila is None:
            fila = CanalRoomsEntry(scenario_id=scenario_id, hotel_id=esc.hotel_id,
                                   segmento_code=e.segmento_code, month=e.month)
            db.add(fila)
            actuales[(e.segmento_code, e.month)] = fila
        fila.noches = e.noches
        if e.tarifa is not None and e.segmento_code in propias:
            fila.tarifa = e.tarifa
        # `tarifa_digitada` queda en True aunque la ponga el motor: la tarifa
        # manda sobre el ingreso en los dos caminos. Ver `models/canal_rooms`.
        fila.tarifa_digitada = True
        fila.actualizado_en = datetime.utcnow()
        fila.actualizado_por = getattr(user, "email", "") or ""

    await db.flush()
    await _rederivar(db, esc, user)
    await db.commit()
    return await _ver(db, scenario_id)


class PreviewBody(BaseModel):
    """Lo que se está tecleando. Nada de esto se guarda."""
    noches: list[NocheBody] = []
    comisiones: list[ComisionBody] = []


@router.post("/rack-rooms/{scenario_id}/preview/")
async def preview(scenario_id: str, body: PreviewBody,
                  db: AsyncSession = Depends(get_db),
                  _=Depends(get_current_user)):
    """El cuadro como quedaría con lo que se está tecleando. **No escribe.**

    Owner, 2026-10-16: *«si me cambian una variable, éste debería ser el punto
    donde se cambie y todo lo demás debe actualizarse o derivarse»*.

    ⚠️ **Por qué una puerta y no una fórmula en el navegador.** Derivar en el
    front sería más rápido y tendría una fórmula duplicada: el día que cambie
    el redondeo o la regla de la tarifa propia, una de las dos se actualiza y
    la otra no — y la que se ve en pantalla deja de ser la que se guarda, sin
    fallar. Acá corre `_armar`, el mismo código del `GET`.

    ⚠️ **No está exento de la guarda de sólo lectura, y está bien.** Es un
    `POST`, así que un `viewer` recibe 403 — que es correcto: un lector no
    teclea en la grilla, así que nunca llega a pedir una previsualización.
    """
    esc = await _escenario(db, scenario_id)
    segs = await _segmentos(db, esc.hotel_id)
    villas, temps, coms = await _cargar(db, esc)
    unidades_hotel = await _unidades_del_hotel(db, esc)
    validos = {s.code for s in segs}

    # ⚠️ Se trabaja sobre COPIAS, no sobre las filas de la sesión. Cambiarle un
    # campo a una fila de la base y confiar en expulsarla después es una
    # previsualización a un descuido de volverse un guardado silencioso.
    pcts: dict[str, dict[int, Decimal]] = {}
    propia_de: dict[str, bool] = {}
    for c in coms:
        pcts.setdefault(c.segmento_code, {})[int(c.month or 1)] = Decimal(
            str(c.comision_pct or 0))
        propia_de[c.segmento_code] = propia_de.get(
            c.segmento_code, False) or bool(c.tarifa_propia)

    # Las comisiones que vengan PISAN a las guardadas; las que no vengan se
    # quedan como están. Así se puede previsualizar un cambio sin mandar las
    # siete. La REGLA de réplica es la misma del guardado (`replicar_desde_enero`).
    for c in body.comisiones:
        if c.segmento_code not in validos:
            raise ErrorApi(422, "canal.segmento_desconocido", code=c.segmento_code)
        if c.month is not None and not 1 <= c.month <= 12:
            raise ErrorApi(400, "mes.fuera_de_rango")
        actual = pcts.setdefault(c.segmento_code, {})
        if c.month is None:
            pcts[c.segmento_code] = replicar_desde_enero(actual, c.comision_pct)
        else:
            actual[c.month] = c.comision_pct
        propia_de[c.segmento_code] = c.tarifa_propia

    coms = [_ComisionEnMemoria(code, mes, meses.get(mes, Decimal("0")),
                               propia_de.get(code, False))
            for code, meses in pcts.items() for mes in range(1, 13)]

    guardadas = {(f.segmento_code, f.month): f for f in (await db.execute(
        select(CanalRoomsEntry).where(
            CanalRoomsEntry.scenario_id == scenario_id))).scalars().all()}
    propias = {c.segmento_code for c in coms if c.tarifa_propia}
    filas: list = []
    tecleadas = set()
    for e in body.noches:
        if e.segmento_code not in validos:
            raise ErrorApi(422, "canal.segmento_desconocido", code=e.segmento_code)
        if not 1 <= e.month <= 12:
            raise ErrorApi(400, "mes.fuera_de_rango")
        previa = guardadas.get((e.segmento_code, e.month))
        tarifa = (e.tarifa if (e.tarifa is not None
                               and e.segmento_code in propias)
                  else (previa.tarifa if previa else Decimal("0")))
        filas.append(_FilaEnMemoria(e.segmento_code, e.month,
                                    max(e.noches, Decimal("0")), tarifa))
        tecleadas.add((e.segmento_code, e.month))
    # Lo que no se está tecleando entra como está guardado: si no, el cuadro
    # mostraría en cero los meses que la pantalla no mandó.
    for (code, mes), f in guardadas.items():
        if (code, mes) not in tecleadas:
            filas.append(_FilaEnMemoria(code, mes, f.noches, f.tarifa))

    salida = _armar(esc, segs, villas, temps, coms, filas, unidades_hotel)
    salida["es_preview"] = True
    return salida


@router.get("/rack-rooms/{scenario_id}/plantilla.xlsx")
async def bajar_plantilla(scenario_id: str, db: AsyncSession = Depends(get_db),
                          _=Depends(get_current_user)):
    """El cuadro de entrada, para llenar en Excel y volver a subir.

    Owner, 2026-10-16: *«se baja el archivo, se actualizan los datos y se
    vuelve a subir»*.

    Trae lo que HOY está cargado, así que bajar y subir sin tocar nada no
    cambia nada. Es a propósito: una plantilla en blanco obliga a retranscribir
    y a la tercera fila ya hay un error de dedo.
    """
    from fastapi.responses import Response

    from app.export.rack_rooms_xlsx import construir_plantilla
    from app.hotel_actual import HOTEL_NAME, hotel_slug

    cuadro = await _ver(db, scenario_id)
    esc = await _escenario(db, scenario_id)
    por_seg: dict[tuple[str, int], dict] = {}
    for e in cuadro["entradas"]:
        por_seg[(e["segmento_code"], int(e["month"]))] = e
    comis: dict[tuple[str, int], dict] = {
        (c["segmento_code"], int(c["month"])): c for c in cuadro["comisiones"]}
    propia_de = {c["segmento_code"] for c in cuadro["comisiones"]
                 if c["tarifa_propia"]}

    segmentos = []
    for s in cuadro["segmentos"]:
        propia = s["code"] in propia_de
        segmentos.append({
            "code": s["code"], "nombre": s["nombre"], "propia": propia,
            "comisiones": [
                float(comis.get((s["code"], m), {}).get("comision_pct") or 0)
                for m in MESES],
            "noches": [float(por_seg.get((s["code"], m), {}).get("noches") or 0)
                       for m in MESES],
            "tarifas": [float(por_seg.get((s["code"], m), {}).get("tarifa") or 0)
                        for m in MESES],
        })

    # El pie: lo que hoy sale de esos números. No se lee de vuelta.
    ms = cuadro["meses"]
    T = cuadro["total"]
    resumen = [
        {"label": "Noches disponibles", "formato": "#,##0",
         "valores": [float(m["disponibles"]) for m in ms],
         "total": float(T["disponibles"])},
        {"label": "Ingreso neto $", "formato": "#,##0.00",
         "valores": [float(m["ingreso"]) for m in ms],
         "total": float(T["ingreso"])},
        {"label": "% Ocupación", "formato": "0.0%",
         "valores": [float(m["ocupacion"]) for m in ms],
         "total": float(T["ocupacion"])},
        {"label": "ADR", "formato": "#,##0.00",
         "valores": [float(m["adr"]) for m in ms], "total": float(T["adr"])},
        {"label": "RevPAR", "formato": "#,##0.00",
         "valores": [float(m["revpar"]) for m in ms],
         "total": float(T["revpar"])},
        {"label": "RAC ponderado", "formato": "#,##0.00",
         "valores": [float(m["rac_ponderado"]) for m in ms],
         "total": float(T["rack"]["adr_rack_sin_propias"])},
    ]

    etiqueta = " ".join(str(v) for v in (esc.type, esc.version) if v)
    xls = construir_plantilla(segmentos, HOTEL_NAME, etiqueta, esc.year, resumen)
    fn = f"{hotel_slug()}_Rooms_por_segmento_{esc.year}.xlsx".replace(" ", "-")
    return Response(
        content=xls,
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"),
        headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@router.post("/rack-rooms/{scenario_id}/upload/",
             dependencies=[Depends(registro_de_subida)])
async def subir_plantilla(scenario_id: str, archivo: UploadFile = File(...),
                          aplicar: bool = Query(False),
                          db: AsyncSession = Depends(get_db),
                          user=Depends(get_current_user)):
    """Lee la plantilla llena y dice QUÉ cambiaría. Aplica sólo si se pide.

    ⚠️ **En seco por omisión.** Subir un archivo que mueve el presupuesto
    entero y enterarse después no es aceptable: primero la lista, después el
    botón. Con `aplicar=true` se escribe.

    ⚠️ **Una celda vacía deja el valor como está.** No es un cero. Tratarla
    como cero convertiría un descuido —borrar una celda, filtrar y no darse
    cuenta— en un mes en cero, con el total cuadrando consigo mismo. Para poner
    cero hay que escribir `0`.

    Lo que no se puede aplicar NO se aplica a medias: se rechaza esa fila, se
    dice cuál y por qué, y el resto sigue.
    """
    from app.export.rack_rooms_xlsx import leer_plantilla, partir_clave

    esc = await candado(db, scenario_id)
    crudo = await archivo.read()
    if not crudo:
        raise ErrorApi(422, "rack.archivo_vacio")
    try:
        filas_archivo = leer_plantilla(crudo)
    except ValueError:
        raise ErrorApi(422, "rack.sin_encabezado")
    except Exception:
        raise ErrorApi(422, "rack.archivo_ilegible")

    segs = {s.code: s for s in await _segmentos(db, esc.hotel_id)}
    filas_com = (await db.execute(select(RackComision).where(
        RackComision.scenario_id == scenario_id))).scalars().all()
    coms = {(c.segmento_code, int(c.month or 1)): c for c in filas_com}
    propias = {c.segmento_code for c in filas_com if c.tarifa_propia}
    actuales = {(f.segmento_code, f.month): f for f in (await db.execute(
        select(CanalRoomsEntry).where(
            CanalRoomsEntry.scenario_id == scenario_id))).scalars().all()}

    cambios: list[dict] = []
    rechazos: list[dict] = []
    vistos: set[str] = set()

    def _num(v):
        """Vacío → None (no se toca). Un texto que no es número → error."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        try:
            return Decimal(str(v).replace(",", "").replace("%", "").strip())
        except (InvalidOperation, ValueError):
            raise ValueError(str(v))

    for clave, _ignorado, meses in filas_archivo:
        code, tipo = partir_clave(clave)
        if code not in segs:
            rechazos.append({"clave": clave,
                             "motivo": "no es un segmento de esta propiedad"})
            continue
        if clave in vistos:
            rechazos.append({"clave": clave,
                             "motivo": "la fila aparece dos veces en el archivo"})
            continue
        vistos.add(clave)
        if tipo == "TARIFA" and code not in propias:
            rechazos.append({"clave": clave,
                             "motivo": "este segmento no tiene tarifa propia: "
                                       "su tarifa sale del tarifario RAC"})
            continue

        if tipo == "COMISION" and code in propias:
            rechazos.append({"clave": clave,
                             "motivo": "este segmento vende a su tarifa propia: "
                                       "no tiene comisión sobre el rack"})
            continue

        for i, bruto in enumerate(meses):
            mes = i + 1
            try:
                valor = _num(bruto)
            except ValueError as e:
                rechazos.append({"clave": clave, "mes": mes,
                                 "motivo": f"«{e}» no es un número"})
                continue
            if valor is None:            # vacío = no se toca
                continue
            if valor < 0:
                rechazos.append({"clave": clave, "mes": mes,
                                 "motivo": "no puede ser negativo"})
                continue
            if tipo == "COMISION":
                if not (Decimal("0") <= valor < Decimal("1")):
                    rechazos.append({"clave": clave, "mes": mes,
                                     "motivo": f"{valor} está fuera de 0 a 1 "
                                               f"(0.25 = 25%)"})
                    continue
                fila = coms.get((code, mes))
                antes = Decimal(str(fila.comision_pct)) if fila else Decimal("0")
                if antes == valor:
                    continue
                cambios.append({"segmento": segs[code].nombre, "mes": mes,
                                "campo": "% Comisión", "antes": str(antes),
                                "ahora": str(valor)})
                if aplicar:
                    if fila is None:
                        fila = RackComision(scenario_id=scenario_id,
                                            hotel_id=esc.hotel_id,
                                            segmento_code=code, month=mes)
                        db.add(fila)
                        coms[(code, mes)] = fila
                    fila.comision_pct = valor
                continue

            fila = actuales.get((code, mes))
            campo = "Noches" if tipo == "NOCHES" else "Tarifa propia"
            antes = Decimal(str(
                (fila.noches if tipo == "NOCHES" else fila.tarifa) if fila else 0))
            if antes == valor:
                continue
            cambios.append({"segmento": segs[code].nombre, "mes": mes,
                            "campo": campo, "antes": str(antes),
                            "ahora": str(valor)})
            if aplicar:
                if fila is None:
                    fila = CanalRoomsEntry(scenario_id=scenario_id,
                                           hotel_id=esc.hotel_id,
                                           segmento_code=code, month=mes)
                    db.add(fila)
                    actuales[(code, mes)] = fila
                if tipo == "NOCHES":
                    fila.noches = valor
                else:
                    fila.tarifa = valor
                fila.tarifa_digitada = True
                fila.actualizado_en = datetime.utcnow()
                fila.actualizado_por = getattr(user, "email", "") or ""

    resumen = {"cambios": cambios, "rechazos": rechazos,
               "aplicado": bool(aplicar)}
    if not aplicar:
        # ⚠️ Nada quedó escrito, pero se tocaron objetos de la sesión al leer.
        # Se deshace para que no viajen en el `commit` de otra ruta.
        await db.rollback()
        return resumen

    await db.flush()
    await _rederivar(db, esc, user)
    await db.commit()
    resumen["cuadro"] = await _ver(db, scenario_id)
    return resumen


@router.patch("/rack-rooms/{scenario_id}/fuente/")
async def conectar(scenario_id: str, fuente: str = Form(...),
                   db: AsyncSession = Depends(get_db),
                   _=Depends(get_current_user)):
    """El interruptor: de qué modelo sale Rooms en este escenario.

    No recalcula. El número del P&L cambia en el siguiente recálculo, que es
    cuando el usuario lo pide — el mismo trato que el resto del sistema.
    """
    esc = await candado(db, scenario_id)
    if fuente not in FUENTES:
        raise ErrorApi(422, "canal.fuente_desconocida", fuente=fuente,
                       validas=", ".join(FUENTES))
    esc.rooms_source = fuente
    await db.commit()
    return {"scenario_id": scenario_id, "rooms_source": fuente,
            "nota": "canal.recalcular_despues"}
