# -*- coding: utf-8 -*-
"""Posiciones, checkbook de planilla y checkbook de OPEX para el Excel en vivo.

Owner, 2026-11-11: *«puedes meter el tab de posiciones por mes y su costo y
además el checkbook de gastos y checkbook de planilla»*.

⚠️ **Esto cambia una regla del consolidado, y la cambió el owner.** El
`consolidado_api` nació (2026-08-14) diciendo que por la llave de solo lectura
NO salían planilla por persona ni nombres. El 2026-11-11, preguntado
explícitamente —«un puesto con una sola persona muestra el salario de esa
persona a cualquiera que tenga la llave»—, el owner eligió **«con nombre y
salario»**. Quien tenga la llave ve la planilla persona por persona: la llave
se reparte con ese cuidado.

**Las cifras salen del MISMO armado que la pantalla.** Posiciones y planilla
reusan `payroll_position_report_api.planilla_por_posicion` —el reporte
«Planilla por código de posición»—; el OPEX lee `opex_entries` como el
checkbook. Una segunda lectura «que hace lo mismo» termina dando otra cifra el
día que una de las dos cambia.

Se resuelve por **año + tipo + versión**, con el mismo criterio del resto del
consolidado (`_escoger_escenario`): el ★ Current del forecast, el ACTUAL real.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.errores import ErrorApi
from app.auth import lector_del_consolidado
from app.db import get_session
from app.hotel_actual import HOTEL_ID, HOTEL_NAME
from app.models.scenario import Scenario

router = APIRouter()

TIPOS = ("BUDGET", "FORECAST", "ACTUAL")
CONTRATO = 1


async def _escenario(session, year: int, tipo: str, version: str | None) -> Scenario:
    from app.api.consolidado_api import _escoger_escenario

    tipo = tipo.upper()
    if tipo not in TIPOS:
        raise ErrorApi(422, "consolidado.tipo_invalido", tipos=", ".join(TIPOS))
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
    return escenario


def _cabecera(escenario: Scenario, tipo: str) -> dict:
    return {
        "contrato": CONTRATO,
        "hotel_id": HOTEL_ID,
        "hotel_name": HOTEL_NAME,
        "year": escenario.year,
        "tipo": tipo.upper(),
        "escenario": {"id": escenario.id, "version": escenario.version,
                      "status": escenario.status,
                      "actuals_through": escenario.actuals_through or 0},
    }


# ── Armado puro (sin base): lo que se prueba ─────────────────────────────────

def filas_posiciones(reporte: dict) -> list[dict]:
    """Una fila por posición: FTE y costo de cada mes.

    El costo del mes es la suma de los 17 conceptos de ESE mes, el mismo número
    que viaja al P&L. El anual es la suma de los doce meses ya redondeados, así
    la fila cuadra contra sus propias columnas.
    """
    claves = [c["key"] for c in reporte["conceptos"]]
    out = []
    for f in reporte["rows"]:
        costo = [round(sum(f["meses"][k][m] for k in claves), 2) for m in range(12)]
        out.append({
            "dept": f["dept_code"], "dept_name": f["dept_name"],
            "codigo": f["position_code"], "puesto": f["position_name"],
            "empleado": f["employee_name"], "tipo_plaza": f.get("employee_type", ""),
            "moneda": f["salary_currency"], "salario": f["salary_amount"],
            "fte": f["fte"], "fte_prom": f["fte_prom"],
            "costo": costo, "costo_anual": round(sum(costo), 2),
            "devengado": f["devengado"], "cargas": f["cargas"],
            "beneficios": f["beneficios"],
        })
    return out


def filas_planilla(reporte: dict) -> list[dict]:
    """El checkbook de planilla: posición × concepto × mes.

    Solo los conceptos con alguna cifra en el año: los 17 conceptos de cada
    posición, la mayoría en cero, harían una tabla de miles de filas vacías.
    """
    out = []
    for f in reporte["rows"]:
        for c in reporte["conceptos"]:
            meses = f["meses"][c["key"]]
            if not any(abs(v) > 0.004 for v in meses):
                continue
            out.append({
                "dept": f["dept_code"], "dept_name": f["dept_name"],
                "codigo": f["position_code"], "puesto": f["position_name"],
                "empleado": f["employee_name"],
                "cuenta": c["code"], "concepto": c["label"], "grupo": c["grupo"],
                "meses": [round(v, 2) for v in meses],
                "anual": round(sum(round(v, 2) for v in meses), 2),
            })
    return out


def filas_opex(entradas, nombres_dept: dict[str, str]) -> list[dict]:
    """El checkbook de OPEX: cuenta × detalle × mes, en USD.

    Una línea en colones trae el dólar DERIVADO con el TC de cada mes (mig 077)
    — el mismo que suma el P&L —; la moneda va en su columna para que se sepa.
    """
    out = []
    for e in entradas:
        meses = [round(float(e.get_month(m) or 0), 2) for m in range(1, 13)]
        out.append({
            "dept": e.dept_code, "dept_name": nombres_dept.get(e.dept_code, ""),
            "cuenta": e.account_code, "nombre": e.account_name or "",
            "detalle": e.detail_code or "", "detalle_desc": e.detail_desc or "",
            "moneda": e.currency or "USD",
            "meses": meses, "anual": round(sum(meses), 2),
        })
    out.sort(key=lambda r: (r["dept"], r["cuenta"], r["detalle"]))
    return out


def filas_costos(entradas, nombres_dept: dict[str, str]) -> list[dict]:
    """El checkbook de costo de ventas (clase 5): depto × cuenta × mes, en USD.

    Owner, 2026-11-11 (Ojochal): «mete tambien el checkbook de costos de
    ventas». Los montos son los guardados —los que suma el P&L—: una línea con
    driver ya viene recalculada (% del ingreso, por noche, por huésped…), y el
    modo y el driver van en sus columnas para que se vea de dónde sale la cifra.
    Una línea en colones trae el dólar derivado con el TC de cada mes, como el OPEX.
    """
    out = []
    for e in entradas:
        meses = [round(float(e.get_month(m) or 0), 2) for m in range(1, 13)]
        out.append({
            "dept": e.dept_code, "dept_name": nombres_dept.get(e.dept_code, ""),
            "cuenta": e.account_code, "nombre": e.account_name or "",
            "modo": e.calc_mode or "MANUAL", "driver": e.driver_type or "",
            "tasa": float(e.driver_pct_or_rate or 0),
            "linea_ingreso": e.revenue_line_ref or "",
            "moneda": e.currency or "USD",
            "meses": meses, "anual": round(sum(meses), 2),
        })
    out.sort(key=lambda r: (r["dept"], r["cuenta"]))
    return out


# ── Endpoints ────────────────────────────────────────────────────────────────

async def _reporte_planilla(session, escenario: Scenario) -> dict:
    from app.api.payroll_position_report_api import planilla_por_posicion
    from app.models.payroll_position import PayrollPosition

    rep = await planilla_por_posicion(escenario.id, dept="", db=session)
    # El reporte de la pantalla no trae el tipo de plaza; se agrega acá sin
    # tocar su contrato.
    tipos = dict((await session.execute(
        select(PayrollPosition.id, PayrollPosition.employee_type)
        .where(PayrollPosition.scenario_id == escenario.id))).all())
    for f in rep["rows"]:
        f["employee_type"] = tipos.get(f["position_id"], "") or ""
    return rep


@router.get("/consolidado/posiciones/")
async def consolidado_posiciones(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Posiciones por mes: FTE y costo, con nombre y salario (owner, 2026-11-11)."""
    async with get_session() as session:
        escenario = await _escenario(session, year, tipo, version)
        rep = await _reporte_planilla(session, escenario)
    return {**_cabecera(escenario, tipo), "posiciones": filas_posiciones(rep)}


@router.get("/consolidado/planilla/")
async def consolidado_planilla(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Checkbook de planilla: posición × concepto (6000–6030) × mes."""
    async with get_session() as session:
        escenario = await _escenario(session, year, tipo, version)
        rep = await _reporte_planilla(session, escenario)
    return {**_cabecera(escenario, tipo), "lineas": filas_planilla(rep)}


@router.get("/consolidado/opex/")
async def consolidado_opex(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Checkbook de OPEX: departamento × cuenta × detalle × mes, en USD."""
    from app.models.department_catalog import DepartmentCatalog
    from app.models.opex_entry import OpexEntry

    async with get_session() as session:
        escenario = await _escenario(session, year, tipo, version)
        entradas = (await session.execute(
            select(OpexEntry).where(OpexEntry.scenario_id == escenario.id))).scalars().all()
        nombres = dict((await session.execute(
            select(DepartmentCatalog.dept_code, DepartmentCatalog.dept_name))).all())
    return {**_cabecera(escenario, tipo), "lineas": filas_opex(entradas, nombres)}


@router.get("/consolidado/costos/")
async def consolidado_costos(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Checkbook de costo de ventas (clase 5): departamento × cuenta × mes, en USD."""
    from app.models.cost_entry import CostEntry
    from app.models.department_catalog import DepartmentCatalog

    async with get_session() as session:
        escenario = await _escenario(session, year, tipo, version)
        entradas = (await session.execute(
            select(CostEntry).where(CostEntry.scenario_id == escenario.id))).scalars().all()
        nombres = dict((await session.execute(
            select(DepartmentCatalog.dept_code, DepartmentCatalog.dept_name))).all())
    return {**_cabecera(escenario, tipo), "lineas": filas_costos(entradas, nombres)}


# ── Detalles y catálogo de OPEX para el checkbook en vivo ────────────────────
# En CWL viven en `export/opex_excel.py` y `api/opex_api.py`, junto con el
# Excel de subida que allá se cambió. En Oxygen ese Excel NO cambia: el
# endpoint solo necesita traducir un código de detalle a su seg3 de Integrity
# y saber qué cuentas tiene cada depto. Mismas reglas que CWL.

#: Cuentas que llevan 21 detalles, de 800 a 820 (owner, 2026-11-23, en CWL).
DETALLES_HASTA_820 = {"7150", "7625", "7660", "7670", "7675"}


def _seg3_de(detail_code) -> str:
    """Código de detalle de FinPlan → tercer segmento de Integrity (800–810).
    Un 8xx pasa tal cual; un «001» es el 801; vacío o raro, el 800."""
    c = str(detail_code or "").strip()
    if not c:
        return "800"
    if len(c) == 3 and c.startswith("8"):
        return c
    try:
        return f"8{int(c):02d}"
    except ValueError:
        return "800"


def _seg3_de_la_cuenta(account_code: str) -> list[str]:
    """Los detalles de una cuenta en seg3: 800–810, o 800–820 en las de arriba."""
    tope = 20 if str(account_code).strip() in DETALLES_HASTA_820 else 10
    return [str(800 + n) for n in range(tope + 1)]


async def _catalogo_opex(session) -> dict[str, dict[str, str]]:
    """`{depto: {cuenta 7xxx: nombre}}` según el mapeo ACTIVO (el catálogo de
    FinPlan: cada cuenta con su renglón del P&L). Las reglas en NO quedan afuera:
    invitarían a presupuestar en una cuenta que el P&L no rutea."""
    from app.models.mapping import AccountMapping
    out: dict[str, dict[str, str]] = {}
    for m in (await session.execute(select(AccountMapping).where(
            AccountMapping.active_status == "YES",
            AccountMapping.account_code.like("7%"),
            AccountMapping.dept_code.is_not(None)))).scalars():
        cod = (m.account_code or "").strip()
        if len(cod) == 4 and cod.isdigit() and (m.dept_code or "").strip():
            out.setdefault(m.dept_code.strip(), {}).setdefault(
                cod, (m.account_name_example or "").strip())
    return out


# ── El checkbook de OPEX en el formato del owner ──────────────────────────────
# Owner, 2026-11-23, con «FORMATO DE CHECKBOOK Budget 2027.xlsx»: «quiero
# automatizar este mismo formato… para que yo pueda actualizar desde Excel y tenga
# los datos ahí mismo». Una hoja por depto; por cuenta, tres filas de año (Actual
# 2025 · Forecast 2026 · Budget 2027), los detalles 800–810 (u 820) del Budget y,
# en la fila TOTAL, el Actual 2026 YTD y el Forecast 2026 del año.
#
# ⚠️ El real va por CUENTA, no por detalle: el mayor con detalle (seg3) solo está
# cargado desde agosto 2026; antes el real entró por cuenta × depto.
#
# Las cifras salen de los MISMOS armados que las pantallas: el Budget de
# `opex_entries` (el checkbook), el real y el forecast de `gl_api._grilla` (el
# reporte «GL Accounts by Month»), y el esqueleto —qué cuentas y qué detalles
# tiene cada hoja— de las MISMAS reglas que el Excel de subida de OPEX.

def _hoja_de(dept: str, hojas: set[str]) -> str:
    """El depto de la hoja donde cae un depto del mayor: él mismo, o su primer
    padre que tenga hoja (0191 Marketing → 0190 Ventas, 0182 Finanzas → 0180)."""
    from app.engine import pl_engine
    if dept in hojas:
        return dept
    for padre in pl_engine._cadena_de_padres(dept):
        if padre in hojas:
            return padre
    return dept


#: Los cinco lugares del libro (owner, 2026-11-23: «cuando ya empiece el año, pongo
#: forecast en los meses y budget viene donde está YTD y forecast»). Cada uno se
#: elige en Config con tipo · año · versión (· hasta mes, en V y W).
LUGARES = ("MES", "F1", "F2", "V", "W", "X")   # X: el Budget del mes (owner, 2026-11-23)


async def _serie_del_lugar(session, esc, hojas_set):
    """Las cifras de UN escenario para el libro: por cuenta y, en 7xxx, por detalle.

    Regla de cada mes:
    * mes REAL (todo el ACTUAL; en el FORECAST, hasta `actuals_through`): sale del
      mayor (`gl_api._grilla`, el reporte GL by Month). El detalle sale de
      `mayor_movimientos` (seg3) y lo que el mayor no traiga con detalle cae en el
      800, para que los detalles sumen la cuenta.
    * mes PROYECTADO (Budget; Forecast después del corte): sale del checkbook
      (`opex_entries` por detalle, `cost_entries` por cuenta) —lo que el owner
      carga—, sin los repartos que el GL le suma a algunas cuentas 7.
    """
    from sqlalchemy import text as _sql
    from app.api import gl_api
    from app.models.cost_entry import CostEntry
    from app.models.opex_entry import OpexEntry

    if esc.type == "ACTUAL":
        corte = 12
    elif esc.type == "FORECAST":
        corte = int(esc.actuals_through or 0)
    else:
        corte = 0
    cuenta: dict[tuple, list[float]] = {}
    detalle: dict[tuple, list[float]] = {}
    desc: dict[tuple, str] = {}

    def suma(d, k, i, v):
        d.setdefault(k, [0.0] * 12)[i] += float(v or 0)

    if corte:
        for r in (await gl_api._grilla(session, esc))[0]:
            cta = str(r["account_code"] or "")
            if not (cta[:1] in ("5", "7") and len(cta) == 4):
                continue
            k = (_hoja_de(str(r["dept_code"] or ""), hojas_set), cta)
            for i in range(corte):
                suma(cuenta, k, i, r["meses"][i])
        for seg2, seg1, seg3, mes, monto in (await session.execute(_sql(
                "select seg2, seg1, split_part(cuenta, '-', 3), mes, sum(debito - credito) "
                "from mayor_movimientos where hotel_id = :h and anio = :a and seg1 like '7%' "
                "and mes <= :c group by 1, 2, 3, 4"),
                {"h": esc.hotel_id, "a": esc.year, "c": corte})).all():
            if not (seg3 and seg3.isdigit() and len(seg3) == 3) or seg3 == "000":
                seg3 = "800"
            suma(detalle, (_hoja_de(seg2, hojas_set), seg1, seg3), int(mes) - 1, monto)
        # El detalle del mayor SOLO donde la cuenta está en el reporte. Los deptos
        # de reparto (0161 lavandería, 0220 comedor) tienen movimiento línea a
        # línea, pero el GL by Month los excluye (ALLOCATION_EXCLUDE): sin este
        # filtro sus detalles sumaban $2.2M que ninguna cuenta tenía.
        detalle = {k: v for k, v in detalle.items() if (k[0], k[1]) in cuenta}
        # Lo que el mayor no traiga con detalle (meses sin mayor línea a línea, o
        # diferencias de redondeo) cae en el 800: los detalles suman la cuenta.
        for (d, cta), meses in cuenta.items():
            if not cta.startswith("7"):
                continue
            for i in range(corte):
                con_det = sum(v[i] for (dd, cc, _), v in detalle.items() if dd == d and cc == cta)
                resto = meses[i] - con_det
                if abs(resto) > 0.005:
                    suma(detalle, (d, cta, "800"), i, resto)
    if corte < 12:
        for e in (await session.execute(select(OpexEntry).where(
                OpexEntry.scenario_id == esc.id))).scalars():
            k3 = (e.dept_code, e.account_code, _seg3_de(e.detail_code))
            if e.detail_desc:
                desc[k3] = e.detail_desc
            for i in range(corte, 12):
                v = e.get_month(i + 1)
                suma(detalle, k3, i, v)
                suma(cuenta, (e.dept_code, e.account_code), i, v)
        for c in (await session.execute(select(CostEntry).where(
                CostEntry.scenario_id == esc.id))).scalars():
            for i in range(corte, 12):
                suma(cuenta, (c.dept_code, c.account_code), i, c.get_month(i + 1))
    return cuenta, detalle, desc, corte


def _lugares_por_defecto(year: int, version: str, fcst_version):
    """Lo que el libro mostraba antes de poder elegir (y lo que pide un libro viejo)."""
    return {"MES": ("BUDGET", year, version, 12), "F1": ("ACTUAL", year - 2, None, 12),
            "F2": ("FORECAST", year - 1, fcst_version, 12), "V": ("ACTUAL", year - 1, None, 12),
            "W": ("FORECAST", year - 1, fcst_version, 12), "X": ("BUDGET", year - 1, None, 12)}


@router.get("/consolidado/checkbook-opex/")
async def consolidado_checkbook_opex(
    year: int = Query(2027, ge=2000, le=2100, description="Año del Budget (libros v1–v3)"),
    version: str = Query("Working", description="Versión del Budget (libros v1–v3)"),
    fcst_version: str | None = Query(None, description="Versión del Forecast (libros v1–v3)"),
    m_tipo: str | None = None, m_anio: int | None = None, m_ver: str | None = None,
    f1_tipo: str | None = None, f1_anio: int | None = None, f1_ver: str | None = None,
    f2_tipo: str | None = None, f2_anio: int | None = None, f2_ver: str | None = None,
    v_tipo: str | None = None, v_anio: int | None = None, v_ver: str | None = None,
    v_hasta: int | None = None, v_modo: str | None = None,
    w_tipo: str | None = None, w_anio: int | None = None, w_ver: str | None = None,
    w_hasta: int | None = None, w_modo: str | None = None,
    x_tipo: str | None = None, x_anio: int | None = None, x_ver: str | None = None,
    x_hasta: int | None = None, x_modo: str | None = None,
    quien: str = Depends(lector_del_consolidado),
):
    """Esqueleto + series del checkbook de OPEX y costo para el formato del owner.

    Cada lugar del libro (MES, F1, F2, V, W) es un escenario elegido en Config:
    tipo · año · versión (vacía o «★» = la vigente; «Pre-Cierre» se pide por su
    nombre) y, para V y W, hasta qué mes se suma. Sin parámetros de lugar responde
    como el libro original: Budget en los meses, Actual año-2, Forecast año-1,
    Actual YTD y Forecast del año.
    """
    from app.api.provisioning_api import depts_habilitados
    from app.models.cost_entry import CostEntry
    from app.models.department_catalog import DepartmentCatalog
    from app.models.mapping import AccountMapping
    from app.models.opex_entry import OpexEntry

    def _ver(x):
        x = (x or "").strip()
        return None if x in ("", "★", "*") else x

    lugares = _lugares_por_defecto(year, version, fcst_version)
    pedidos = {"MES": (m_tipo, m_anio, m_ver, None), "F1": (f1_tipo, f1_anio, f1_ver, None),
               "F2": (f2_tipo, f2_anio, f2_ver, None), "V": (v_tipo, v_anio, v_ver, v_hasta),
               "W": (w_tipo, w_anio, w_ver, w_hasta), "X": (x_tipo, x_anio, x_ver, x_hasta)}
    for k, (t, a, ver, h) in pedidos.items():
        if t and t.strip():
            lugares[k] = (t.strip().upper(), int(a or year), _ver(ver), int(h or 12))
    # V y W: el MES solo, o ACUMULADO de enero al mes. El Pre-Cierre trae solo el
    # mes que se está cerrando (owner, 2026-11-23: «precierre solo sirve para
    # revisar mes, no sirve para acumulado»): con él manda el mes, diga lo que diga.
    modos = {"V": (v_modo or "ACUMULADO").strip().upper(), "W": (w_modo or "ACUMULADO").strip().upper(),
             "X": (x_modo or "ACUMULADO").strip().upper()}
    for k in modos:
        if (lugares[k][2] or "").lower().replace("-", "").replace(" ", "") == "precierre":
            modos[k] = "MES"

    async with get_session() as session:
        tipo_m, anio_m, ver_m, _ = lugares["MES"]
        esc_mes = await _escenario(session, anio_m, tipo_m, ver_m)
        nombres = dict((await session.execute(
            select(DepartmentCatalog.dept_code, DepartmentCatalog.dept_name))).all())
        catalogo = await _catalogo_opex(session)
        apagados = await depts_habilitados(session, esc_mes.hotel_id, "OPEX") or set()

        # Esqueleto: hojas, cuentas 7 (con detalles) y cuentas 5 de cada depto.
        entradas = (await session.execute(
            select(OpexEntry).where(OpexEntry.scenario_id == esc_mes.id))).scalars().all()
        costos_e = (await session.execute(
            select(CostEntry).where(CostEntry.scenario_id == esc_mes.id))).scalars().all()
        cuentas: dict[str, dict[str, str]] = {}
        for e in entradas:
            cuentas.setdefault(e.dept_code, {}).setdefault(e.account_code, e.account_name or "")
        for d, cs in catalogo.items():
            if d in apagados:
                continue
            for a, n in cs.items():
                cuentas.setdefault(d, {}).setdefault(a, n)
                if not cuentas[d][a]:
                    cuentas[d][a] = n
        cuentas = {d: v for d, v in cuentas.items()
                   if d not in apagados or any(e.dept_code == d for e in entradas)}
        hojas_set = set(cuentas)
        cat_costo: dict[str, dict[str, str]] = {}
        for m in (await session.execute(select(AccountMapping).where(
                AccountMapping.active_status == "YES",
                AccountMapping.account_code.like("5%"),
                AccountMapping.dept_code.is_not(None)))).scalars():
            cod = (m.account_code or "").strip()
            if len(cod) == 4 and cod.isdigit() and (m.dept_code or "").strip():
                cat_costo.setdefault(m.dept_code.strip(), {}).setdefault(
                    cod, (m.account_name_example or "").strip())
        for c in costos_e:
            cat_costo.setdefault(c.dept_code, {}).setdefault(c.account_code, c.account_name or "")

        filas: list[dict] = []
        info: dict[str, dict] = {}

        def fila(serie, dept, cuenta, detalle, meses, desc="", hasta=12):
            meses = [round(float(x or 0), 2) for x in meses]
            if modos.get(serie) == "MES":
                anual = meses[hasta - 1]
            else:
                anual = sum(meses[:hasta])
            filas.append({"clave": f"{dept}|{cuenta}|{detalle}|{serie}", "serie": serie,
                          "dept": dept, "cuenta": cuenta, "detalle": detalle, "desc": desc,
                          "meses": meses, "anual": round(anual, 2)})

        usados: dict[tuple, set[str]] = {}
        for lugar in LUGARES:
            tipo, anio, ver, hasta = lugares[lugar]
            try:
                esc = await _escenario(session, anio, tipo, ver)
            except Exception:
                info[lugar] = {"tipo": tipo, "year": anio, "version": ver or "",
                               "hasta": hasta, "error": "no existe"}
                continue
            cuenta, detalle, desc, corte = await _serie_del_lugar(session, esc, hojas_set)
            for (d, cta), meses in cuenta.items():
                if d in hojas_set:
                    fila(lugar, d, cta, "", meses, hasta=hasta)
            for (d, cta, det), meses in detalle.items():
                if d in hojas_set:
                    fila(lugar, d, cta, det, meses, desc.get((d, cta, det), ""), hasta=hasta)
                    if any(abs(x) > 0.005 for x in meses) or lugar == "MES":
                        usados.setdefault((d, cta), set()).add(det)
            info[lugar] = {"tipo": tipo, "year": anio, "version": esc.version, "hasta": hasta,
                           "modo": modos.get(lugar, ""),
                           "actuals_through": corte if tipo == "FORECAST" else 0}

    # Todos los detalles ACTIVOS de cada cuenta (owner, 2026-11-23): el rango de la
    # cuenta (800–810, o 800–820) + los que use cualquiera de los escenarios.
    hojas = []
    for d in sorted(cuentas):
        cs = []
        for a, n in sorted(cuentas[d].items()):
            det = set(_seg3_de_la_cuenta(a)) | usados.get((d, a), set())
            cs.append({"cuenta": a, "nombre": n, "detalles": sorted(det)})
        costo = [{"cuenta": a, "nombre": n} for a, n in sorted(cat_costo.get(d, {}).items())]
        hojas.append({"dept": d, "dept_name": nombres.get(d, d), "cuentas": cs, "costos": costo})
    return {**_cabecera(esc_mes, esc_mes.type), "lugares": info, "series": info,
            "hojas": hojas, "filas": filas + _claves_viejas(filas)}


def _claves_viejas(filas: list[dict]) -> list[dict]:
    """Los libros v1–v3 buscan BUD (meses), ACT, FCT e YTD: se entregan también con
    esos nombres para que sigan actualizando hasta que se cambien por el nuevo."""
    equiv = {"MES": "BUD", "F1": "ACT", "F2": "FCT", "V": "YTD"}
    out = []
    for f in filas:
        nuevo = equiv.get(f["serie"])
        if nuevo:
            out.append({**f, "serie": nuevo,
                        "clave": f"{f['dept']}|{f['cuenta']}|{f['detalle']}|{nuevo}"})
    return out
