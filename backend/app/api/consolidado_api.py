# -*- coding: utf-8 -*-
"""P&L de ESTA propiedad, por API, de solo lectura.

**Para qué (owner, 2026-08-14).** Las propiedades son despliegues aparte con
bases aparte, y eso no se toca. Lo que faltaba era poder *jalar* el resultado de
cada una desde afuera para sumarlas donde el dueño quiera — Excel, Power BI, un
tablero propio, o la app de otra propiedad.

**Por qué así y no con un recolector.** La primera idea era que un backend fuera
a buscar a los otros tres; eso obliga a que UN hotel guarde las llaves de los
demás, y si lo comprometen se ven los cuatro. Acá cada propiedad solo sabe
responder por lo suyo: nadie guarda llaves ajenas, y quien consolida es el de
afuera. Además sirve desde el primer hotel, no desde el segundo.

**El contrato.** Este formato es el mismo en las cuatro propiedades: identidad,
escenario usado, y cada línea del P&L con sus 12 meses y el anual, en USD, más
los KPIs. Si cambia, cambia en las cuatro — por eso hay prueba de su forma.

**Qué NO sale por acá:** ningún asiento del mayor. (Hasta el 2026-11-11 tampoco
salían planilla por persona ni nombres; ese día el owner pidió posiciones con
nombre y salario — ver `consolidado_planilla_api`.) Por acá: totales por
línea y, en `/consolidado/gl/` (traído de CWL
el 2026-11-10 para el Excel en vivo), el mayor por mes: una fila por
(departamento × cuenta) con sus doce meses —sumas, nunca movimientos—.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.errores import ErrorApi
from app.auth import lector_del_consolidado
from app.db import get_session
from app.hotel_actual import HOTEL_ID, HOTEL_NAME
from app.models.scenario import Scenario

router = APIRouter()

TIPOS = ("BUDGET", "FORECAST", "ACTUAL")

# Versión del contrato. Sube cuando cambie la FORMA de la respuesta, para que un
# consolidador viejo pueda darse cuenta en vez de leer campos que ya no están.
CONTRATO = 1


@router.get("/consolidado/propia/")
async def consolidado_propia(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto, la más reciente"),
    quien: str = Depends(lector_del_consolidado),
):
    """El P&L de esta propiedad, listo para consolidar."""
    tipo = tipo.upper()
    if tipo not in TIPOS:
        raise ErrorApi(422, "consolidado.tipo_invalido", tipos=", ".join(TIPOS))

    from app.api import pl_api

    async with get_session() as session:
        q = select(Scenario).where(
            Scenario.hotel_id == HOTEL_ID,
            Scenario.year == year,
            Scenario.type == tipo,
        )
        if version:
            q = q.where(Scenario.version == version)
        escenario = (await session.execute(
            q.order_by(Scenario.created_at.desc()))).scalars().first()

        if escenario is None:
            # 404 y no una respuesta vacía: un consolidador que recibe ceros los
            # suma como si fueran ceros de verdad, y el grupo queda mal sin que
            # nada lo delate.
            if version:
                raise ErrorApi(404, "consolidado.sin_escenario_version",
                               propiedad=HOTEL_NAME, tipo=tipo,
                               version=version, anio=year)
            raise ErrorApi(404, "consolidado.sin_escenario",
                           propiedad=HOTEL_NAME, tipo=tipo, anio=year)

        mensual = await pl_api._monthly_results(session, escenario)
        anual = pl_api._aggregate(mensual, 12)

        # Se arma por CÓDIGO de línea, no por posición: dos propiedades pueden
        # tener líneas distintas (una sin Spa, otra sin Club) y la suma del que
        # consolida tiene que cuadrar igual.
        por_mes: dict[str, list[float]] = {}
        for m in mensual:
            for ln in m["lines"]:
                serie = por_mes.setdefault(ln.line_code, [0.0] * 12)
                serie[m["month"] - 1] += float(ln.amount_usd)

        lineas = [{
            "line_code": ln["line_code"],
            "line_name": ln["line_name"],
            "section": ln["section"],
            "meses": por_mes.get(ln["line_code"], [0.0] * 12),
            "anual": float(ln["amount_usd"]),
        } for ln in anual["lines"]]

        return {
            "contrato": CONTRATO,
            "hotel_id": HOTEL_ID,
            "hotel_name": HOTEL_NAME,
            "year": year,
            "tipo": tipo,
            "escenario": {
                "id": escenario.id,
                "version": escenario.version,
                "status": escenario.status,
                # Cuál es el último mes con dato real. Un consolidador que mezcla
                # propiedades con cortes distintos tiene que poder verlo.
                "actuals_through": getattr(escenario, "actuals_through", None),
            },
            "moneda": "USD",
            "kpis": anual.get("kpis", {}),
            # Noches de cada mes (Hotel Consolidation, 2026-10-14): con el
            # anual solo, el ADR y la ocupación mensual de un Forecast que vive
            # en el P&L —sin detalle por tipo— no se pueden reconstruir. Campo
            # nuevo; no cambia ninguno de los que ya estaban.
            "kpis_mes": [{
                "month": m["month"],
                "rooms_available": float((m["kpis"] or {}).get("rooms_available") or 0),
                "rooms_occupied": float((m["kpis"] or {}).get("rooms_occupied") or 0),
                "guests": float((m["kpis"] or {}).get("guests") or 0),
            } for m in mensual],
            "lineas": lineas,
            "leido_por": quien,
        }


@router.get("/consolidado/escenarios/")
async def consolidado_escenarios(quien: str = Depends(lector_del_consolidado)):
    """Qué hay para jalar. Sin esto, el de afuera tiene que adivinar años y tipos."""
    async with get_session() as session:
        filas = (await session.execute(
            select(Scenario).where(Scenario.hotel_id == HOTEL_ID)
            .order_by(Scenario.year.desc(), Scenario.type, Scenario.created_at.desc())
        )).scalars().all()
    return {
        "contrato": CONTRATO,
        "hotel_id": HOTEL_ID,
        "hotel_name": HOTEL_NAME,
        "escenarios": [{
            "year": e.year, "tipo": e.type, "version": e.version, "status": e.status,
        } for e in filas],
    }


def _escoger_escenario(escenarios: list, tipo: str, version: str | None):
    """El escenario a entregar. Sin versión: para FORECAST el marcado ★ Current
    (o el más reciente si no hay marca); para ACTUAL el real, nunca un espejo
    de Pre-Cierre (Oxygen no los tiene; se deja por paridad con CWL)."""
    if version:
        return next((e for e in escenarios if e.version == version), None)
    if tipo == "ACTUAL":
        escenarios = [e for e in escenarios if not getattr(e, "es_precierre", False)]
    if tipo == "FORECAST":
        marcado = [e for e in escenarios if getattr(e, "is_current_forecast", False)]
        if marcado:
            return marcado[0]
    return escenarios[0] if escenarios else None


@router.get("/consolidado/gl/")
async def consolidado_gl(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    catalogo: bool = Query(False, description="Incluir en cero las cuentas del mapeo que el escenario no usó"),
    quien: str = Depends(lector_del_consolidado),
):
    """Las cuentas del mayor por mes, para un Excel que se actualiza solo.

    Owner, 2026-11-10: *«necesito formatear esto para poder desde excel bajar
    estos datos con refresh, con varias versiones»*.

    ⚠️ **Reusa `gl_api._grilla`, el MISMO armado que el botón Excel de la
    pantalla.** Una segunda lectura que "hace lo mismo" termina dando otra
    cifra el día que una de las dos cambia, y la diferencia aparece en un
    archivo que alguien ya mandó. Acá lo que baja Power Query es,
    literalmente, lo que muestra el reporte.

    Se resuelve por **año + tipo + versión**, no por UUID: en el Excel la
    versión se escribe como se llama ("Working", "Final"), que es lo que el
    usuario sabe. Sin versión manda el mismo criterio del resto del
    consolidado -- el ★ Current del forecast, el ACTUAL real y nunca el espejo
    del Pre-Cierre.

    Una fila por (departamento × cuenta) con sus doce meses y el anual, y el
    mismo signo del reporte: **el ingreso va NEGATIVO** (es crédito), así que
    la suma de todas las filas es la utilidad cambiada de signo.
    """
    from app.api import gl_api

    tipo = tipo.upper()
    if tipo not in TIPOS:
        raise ErrorApi(422, "consolidado.tipo_invalido", tipos=", ".join(TIPOS))

    async with get_session() as session:
        escenarios = (await session.execute(
            select(Scenario).where(Scenario.hotel_id == HOTEL_ID, Scenario.year == year,
                                   Scenario.type == tipo)
            .order_by(Scenario.created_at.desc()))).scalars().all()
        escenario = _escoger_escenario(list(escenarios), tipo, version)
        if escenario is None:
            if version:
                raise ErrorApi(404, "consolidado.sin_escenario_version",
                               propiedad=HOTEL_NAME, tipo=tipo, version=version, anio=year)
            raise ErrorApi(404, "consolidado.sin_escenario", propiedad=HOTEL_NAME, tipo=tipo, anio=year)

        grilla, fuente, completo, _cmp, _sec, n_cat, n_vacias = await gl_api._grilla(
            session, escenario, catalogo=catalogo)

    return {
        "contrato": CONTRATO,
        "hotel_id": HOTEL_ID,
        "hotel_name": HOTEL_NAME,
        "year": year,
        "tipo": tipo,
        "escenario": {
            "id": escenario.id, "version": escenario.version,
            "status": escenario.status, "source_mode": escenario.source_mode,
            "actuals_through": escenario.actuals_through or 0,
        },
        "fuente": fuente,
        "completo": completo,
        "cuentas_catalogo": n_cat,
        "cuentas_sin_movimiento": n_vacias,
        "signo": "revenue_credit",
        "cuentas": [{
            "dept": r["dept_code"], "dept_name": r["dept_name"],
            "cuenta": r["account_code"], "nombre": r["account_name"],
            "seccion": r["pl_section"], "linea": r["pl_line_code"],
            "renglon": r["pl_line_name"], "categoria": r["categoria"],
            "naturaleza": ("Revenue"
                           if (r["pl_section"] or "").strip().upper() == "REVENUES"
                           else "Expense"),
            # La columna `Status` del mapeo. `_grilla` solo resuelve con reglas
            # ACTIVAS, asi que una fila con renglon viene de una regla activa;
            # una sin renglon es plata del mayor que el P&L no ve -- y eso es
            # mas util saberlo que ver un "YES" en todas.
            "estado": "YES" if r["pl_line_code"] else "SIN MAPEO",
            # COMO la resolvio: exact · parent · dept-agnostic · FALLBACK · DROP.
            # FALLBACK llega por descarte y puede moverse de renglon solo el dia
            # que aparezca una segunda regla.
            "mapeo": r["mapeo"],
            "por_linea": bool(r.get("por_linea")),
            "sin_movimiento": bool(r.get("sin_movimiento")),
            "meses": [float(x or 0) for x in r["meses"]],
            "anual": float(r["total"] or 0),
        } for r in grilla],
    }


# ── Estadísticas de habitaciones para el Excel en vivo ───────────────────────

#: (clave, nombre, unidad) en el orden de la pestaña.
INDICADORES = [
    ("units", "Unidades (habitaciones)", "hab"),
    ("rooms_available", "Total rooms available", "noches"),
    ("rooms_occupied", "Rooms occupied", "noches"),
    ("guests", "Huéspedes", "pax"),
    ("occupancy_pct", "% Ocupación", "%"),
    ("adr", "ADR (habitaciones)", "USD"),
    ("rooms_revenue", "Ingreso de habitaciones", "USD"),
    ("total_revenue", "Ingreso total", "USD"),
    ("adr_total", "ADR ingreso total (ingreso total / ocupadas)", "USD"),
    ("revpar", "RevPAR (ingreso total / disponibles)", "USD"),
    ("revpar_rooms", "RevPAR habitaciones (ADR × ocupación)", "USD"),
]


def _monto(lineas, codigo: str) -> float:
    total = 0.0
    for ln in lineas:
        lc = ln["line_code"] if isinstance(ln, dict) else getattr(ln, "line_code", "")
        if lc == codigo:
            total += float(ln["amount_usd"] if isinstance(ln, dict) else ln.amount_usd)
    return total


def indicadores_del_periodo(kpis: dict, lineas, dias: int) -> dict[str, float]:
    """Los indicadores de un mes (o del año) desde los KPIs y las líneas del P&L.

    ADR, ocupación y RevPAR son los MISMOS del encabezado del P&L
    (`pl_api`): el ADR sale de las estadísticas del escenario y no de la línea
    REV_ROOMS (un no-show no ocupa habitación), y el RevPAR es ingreso TOTAL /
    disponibles (owner, 2026-09-08). Lo nuevo se deriva de esos:
    unidades = disponibles / días, ADR total = ingreso total / ocupadas y el
    RevPAR de habitaciones = ADR × ocupación.
    """
    disp = float(kpis.get("rooms_available") or 0)
    ocup = float(kpis.get("rooms_occupied") or 0)
    occ = float(kpis.get("occupancy_pct") or 0)
    adr = float(kpis.get("adr") or 0)
    total = _monto(lineas, "TOTAL_REVENUES")
    return {
        "units": round(disp / dias, 2) if dias else 0.0,
        "rooms_available": disp,
        "rooms_occupied": ocup,
        "guests": float(kpis.get("guests") or 0),
        "occupancy_pct": occ,
        "adr": adr,
        "rooms_revenue": _monto(lineas, "REV_ROOMS"),
        "total_revenue": total,
        "adr_total": (total / ocup) if ocup else 0.0,
        "revpar": float(kpis.get("revpar") or 0),
        "revpar_rooms": adr * occ,
    }


@router.get("/consolidado/estadisticas/")
async def consolidado_estadisticas(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Estadísticas de habitaciones por mes y del año, para el Excel en vivo.

    Owner, 2026-11-11: *«un tab de estadísticas de rooms, total rooms
    available, units, rooms occupied, % ocupación, ADR, ADR total revenue,
    RevPAR»*. Reusa `pl_api._monthly_results` y `pl_api._aggregate`, lo mismo
    que `/consolidado/propia/`: el Excel muestra los números del encabezado
    del P&L, no otros.
    """
    import calendar

    from app.api import pl_api

    tipo = tipo.upper()
    if tipo not in TIPOS:
        raise ErrorApi(422, "consolidado.tipo_invalido", tipos=", ".join(TIPOS))
    async with get_session() as session:
        escenarios = (await session.execute(
            select(Scenario).where(Scenario.hotel_id == HOTEL_ID, Scenario.year == year,
                                   Scenario.type == tipo)
            .order_by(Scenario.created_at.desc()))).scalars().all()
        escenario = _escoger_escenario(list(escenarios), tipo, version)
        if escenario is None:
            if version:
                raise ErrorApi(404, "consolidado.sin_escenario_version",
                               propiedad=HOTEL_NAME, tipo=tipo, version=version, anio=year)
            raise ErrorApi(404, "consolidado.sin_escenario", propiedad=HOTEL_NAME, tipo=tipo, anio=year)
        mensual = await pl_api._monthly_results(session, escenario)
        anual = pl_api._aggregate(mensual, 12)

    por_mes = {m["month"]: indicadores_del_periodo(
        m["kpis"] or {}, m["lines"], calendar.monthrange(year, m["month"])[1]) for m in mensual}
    del_anio = indicadores_del_periodo(anual.get("kpis") or {}, anual["lines"],
                                       366 if calendar.isleap(year) else 365)
    return {
        "contrato": CONTRATO,
        "hotel_id": HOTEL_ID,
        "hotel_name": HOTEL_NAME,
        "year": year,
        "tipo": tipo,
        "escenario": {"id": escenario.id, "version": escenario.version,
                      "status": escenario.status,
                      "actuals_through": escenario.actuals_through or 0},
        "indicadores": [{
            "clave": k, "nombre": n, "unidad": u,
            "meses": [round(por_mes.get(i, {}).get(k, 0.0), 4) for i in range(1, 13)],
            "anual": round(del_anio[k], 4),
        } for k, n, u in INDICADORES],
    }
