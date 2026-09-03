# -*- coding: utf-8 -*-
"""El gasto por CLASE de cuenta, mes a mes.

**Qué es (owner, 2026-08-14).** Las cuatro líneas del pie de su cuadro de cierre
son un corte por naturaleza del gasto, y la regla es tan simple como suena:

    Total Payroll and Benefits  →  todas las cuentas 6
    Total Cost                  →  todas las cuentas 5
    Total Operating Expenses    →  todas las cuentas 7
    Total Property Expenses     →  todas las cuentas 8

**Por qué no salía del P&L.** Las líneas del P&L están cortadas por
DEPARTAMENTO, no por naturaleza: `OPEX_ROOMS`, `OPEX_FB`… Sumarlas no da «todas
las 7», porque la planilla y el costo de esos mismos departamentos entran en la
misma línea. Es otro eje, y por eso necesita su propia consulta.

**De dónde sale, según el tipo de escenario:**

* BUDGET y FORECAST → de los checkbooks de la app (planilla, costo, opex) y del
  mini-checkbook de below-GOP para la clase 8.
* ACTUAL → del detalle del GL (`actual_entries`), por el primer dígito de la
  cuenta.

Los dos caminos coexisten en el mismo escenario a propósito: un forecast puede
tener meses reales cargados y meses proyectados, y hay que sumar los dos.

Devuelve **los doce meses**, no un agregado: quien llama arma mes, YTD o año sin
volver a preguntar. Sumar doce números en el cliente es gratis; doce viajes no.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.errores import ErrorApi
from app.auth import get_current_user
from app.db import get_session
from app.engine import pl_engine
from app.models.mapping import AccountMapping
from app.nombres_cuenta import limpiar_nombre
from app.engine import recalculate as recalc
from app.models.actual_entry import ActualEntry
from app.models.belowgop_account_entry import BelowGopAccountEntry
from app.models.nonop_entry import NonOpEntry
from app.models.pl_line import PLLine
from app.models.scenario import Scenario

router = APIRouter()

ZERO = Decimal("0")
MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]

# Cuentas de REPARTO. Son clase 4 pero NO son ingreso: es el credito con el que
# un departamento de servicio interno —Cafeteria, Lavanderia— se vacia contra los
# departamentos que lo consumen.
#
# Sin excluirlas, la apertura de ingreso mostraba «0220 Cafeteria -71,556» y
# «0161 Lavanderia -18,852» como si fueran ventas negativas (owner, 2026-08-14).
#
# ⚠️ Ojo con la 4901: el motor solo conoce 4900 y 4999
# (`pl_engine.ALLOCATION_ACCOUNTS`), y los libros reales usan tambien la 4901
# para la Cafeteria. Queda anotado — puede estar contandose como ingreso en el
# P&L, y eso es otra investigacion.
CUENTAS_DE_REPARTO = {"4900", "4901", "4999"}

# Departamentos que se FUSIONAN en la apertura de INGRESO (owner, 2026-08-14).
#
# La lavanderia esta partida a proposito: el 0162 factura y el 0161 lleva el
# gasto y lo reparte. Pero el ingreso venia cargado en los dos, segun el año y la
# version. Se movio el dato donde se pudo —los escenarios en borrador— y los
# enllavados no se pueden tocar sin abrir una foto historica.
#
# Fusionarlos EN LA VISTA resuelve las dos cosas de una: la venta de lavanderia
# sale en una sola fila en todas las versiones y todos los años, sin importar
# como quedo cargada.
#
# **Solo en ingreso.** En gasto siguen separados, que es justo el punto de
# tenerlos partidos: el 0161 tiene que poder cerrar en cero contra su reparto.
FUSION_INGRESO = {"0161": "0162"}

# Departamentos que NO salen en el GASTO: son POZOS de reparto. Su costo ya esta
# dentro de los departamentos que lo consumen, asi que mostrarlo aparte lo cuenta
# dos veces a la vista.
#
#   0220  Cafeteria  — viaja en la planilla de cada depto por el concepto 6025
#   0161  Lavanderia (operacion) — se reparte por la 4900
#   0162  Lavanderia (ingreso)   — es la cara de venta del mismo servicio
#
# Los tres SOLO se excluyen del gasto. En INGRESO la lavanderia si sale, en una
# sola linea: el 0161 se fusiona en el 0162 (ver FUSION_INGRESO).
#
# Es la misma razon por la que el motor excluye el 0220 del P&L de actuales
# (`pl_engine.ACTUAL_EXCLUDED_DEPTS`).
EXCLUIR_DE_GASTO = {"0220", "0161", "0162"}

# El nombre de cada clase, tal como lo escribe el owner en su cuadro.
CLASES = {
    "payroll": "Total Payroll and Benefits",   # 6xxx
    "cost": "Total Cost",                      # 5xxx
    "opex": "Total Operating Expenses",        # 7xxx
    "property": "Total Property Expenses",     # 8xxx
}


def _nombra(destino: dict, clave: str, nombre: str):
    """Guarda el nombre de una cuenta la primera vez que se la ve.

    El gasto de propiedad se abre por cuenta, y una lista de numeros sueltos
    —8005, 8020, 8040— no le dice nada a nadie (owner, 2026-08-14).

    ⚠️ El nombre se LIMPIA antes de guardarlo. `account_name` y
    `account_name_example` traen todas las variantes que aparecieron en el
    mayor pegadas con barras —«DEPRECIATION1 | DEPRECIATION2 | DEPRECIATION4 |
    DEPRECIATION»—, que son sesenta caracteres donde caben veinte: el rótulo se
    montaba encima de los montos (owner, 2026-09-03).
    """
    limpio = limpiar_nombre(nombre)
    if limpio:
        destino.setdefault("__nombres__", {}).setdefault(clave, limpio)


def _padre(dept: str) -> str:
    """El departamento del P&L al que pertenece un sub-departamento.

    ⚠️ **Sube en CADENA.** `pl_engine.consolidate_dept` resuelve un escalon, y
    hay cadenas de dos: el 0132 cuelga del 0130 y el 0130 del 0140. Con una
    sola vuelta la planilla del Spa quedaba en un departamento intermedio que
    el cuadro no dibuja.

    El tope de vueltas evita un ciclo si alguien deja mal el catalogo: mejor
    quedarse en el ultimo codigo bueno que colgar el reporte.
    """
    visto = set()
    for _ in range(5):
        padre = pl_engine.consolidate_dept(dept)
        if padre == dept or padre in visto:
            return dept
        visto.add(dept)
        dept = padre
    return dept


def _suma(destino: dict, clase: str, clave: str, mes: int, monto):
    """Acumula en {clase: {clave: [12 meses]}}. `clave` es el departamento, o la
    cuenta cuando se trata de la clase 8 —el gasto de propiedad se mira por
    cuenta del mayor, no por departamento, porque vive todo en el mismo."""
    if not monto:
        return
    serie = destino.setdefault(clase, {}).setdefault(clave or "(sin depto)", [0.0] * 12)
    serie[mes - 1] += float(monto)


async def _por_mes(session, scenario_id: str, detalle: dict | None = None) -> list[dict]:
    """Los cuatro totales, mes por mes. Si se pasa `detalle`, lo llena con la
    apertura por departamento (y por cuenta, para la clase 8)."""
    filas = []

    # Se necesita el escenario, no sólo su id: el tipo y `actuals_through`
    # deciden de dónde sale el gasto de cada mes — ver la mezcla más abajo.
    escenario = await session.get(Scenario, scenario_id)
    if escenario is None:
        return filas

    # Clase 8 del presupuesto: vive en su propio checkbook, con la cuenta en la
    # fila. Se lee una vez y se reparte por mes, en vez de doce consultas.
    #
    # ⚠️ **`NonOpEntry`, que es lo que lee el P&L — y no `BelowGopAccountEntry`.**
    #
    # Owner, 2026-09-03, cotejando su Excel: el gasto de propiedad daba
    # $116.207,21 en el P&L y $20.585,21 en este cuadro. No era un error de
    # calculo: el below-GOP vive en DOS tablas y cada pantalla leia una. Los
    # honorarios (8005) tenian 68.337,08 en una y 18.915,01 en la otra, y cual
    # numero veias dependia de por que pantalla entraras.
    #
    # `recalculate.belowgop_by_line` siembra las lineas del P&L desde
    # `NonOpEntry`: esa es la fuente. Este cuadro pasa a leer la misma, asi las
    # dos pantallas no pueden contar versiones distintas del mismo gasto.
    #
    # El NOMBRE de cada cuenta se sigue buscando en la tabla vieja: `NonOpEntry`
    # lo trae casi siempre vacio, y una lista de 8005, 8015, 8020 no le dice
    # nada a nadie.
    below = (await session.execute(select(NonOpEntry).where(
        NonOpEntry.scenario_id == scenario_id))).scalars().all()
    nombres_bg = {
        (e.account_code or "").strip(): e.account_name
        for e in (await session.execute(select(BelowGopAccountEntry).where(
            BelowGopAccountEntry.scenario_id == scenario_id))).scalars()
        if e.account_name
    }

    # Las lineas de INGRESO del P&L, por mes. Se leen una vez, no doce.
    #
    # `TOTAL_REVENUES` y `SEC_REVENUES` son agregados —el total y el encabezado
    # de la seccion—: incluirlos duplicaria el ingreso en el cuadro, y el error
    # se veria como «el doble», que es de los que pasan desapercibidos porque
    # todo sigue sumando consigo mismo.
    lineas_ingreso: dict[int, list] = {}
    if detalle is not None:
        for ln in (await session.execute(select(PLLine).where(
                PLLine.scenario_id == scenario_id,
                PLLine.section == "REVENUES",
                PLLine.line_code.notin_(["TOTAL_REVENUES", "SEC_REVENUES"]),
        ))).scalars().all():
            lineas_ingreso.setdefault(ln.month, []).append(ln)
            _nombra(detalle, ln.line_code, ln.line_name or "")

    # Las lineas de INGRESO del P&L, por mes. Se leen una vez, no doce.
    #
    # `TOTAL_REVENUES` y `SEC_REVENUES` son agregados —el total y el encabezado
    # de la seccion—: incluirlos duplicaria el ingreso en el cuadro, y el error
    # se veria como «el doble», que es de los que pasan desapercibidos porque
    # todo sigue sumando consigo mismo.
    lineas_ingreso: dict[int, list] = {}
    if detalle is not None:
        for ln in (await session.execute(select(PLLine).where(
                PLLine.scenario_id == scenario_id,
                PLLine.section == "REVENUES",
                PLLine.line_code.notin_(["TOTAL_REVENUES", "SEC_REVENUES"]),
        ))).scalars().all():
            lineas_ingreso.setdefault(ln.month, []).append(ln)
            _nombra(detalle, ln.line_code, ln.line_name or "")

    # El nombre de cada cuenta 8xxx. `actual_rows_for_month` devuelve solo
    # codigo, depto y monto, asi que el nombre se busca aparte — una vez, no una
    # por mes.
    if detalle is not None:
        for f in (await session.execute(select(ActualEntry).where(
                ActualEntry.scenario_id == scenario_id))).scalars().all():
            if (f.account_code or "").startswith("8"):
                _nombra(detalle, f.account_code, f.account_name or "")
        # ⚠️ `NonOpEntry.account_name` está VACÍO en las 18 filas de producción,
        # en los tres escenarios. Sin un respaldo, el 8000 y el 8020 salían
        # como número pelado — que es justo lo que este bloque vino a evitar.
        #
        # El catálogo sí los tiene: 8000 es RENT y 8020 es CAPITAL RESERVE. Se
        # lee UNA vez, no una por cuenta.
        del_catalogo = {
            (m.account_code or "").strip(): m.account_name_example
            for m in (await session.execute(select(AccountMapping).where(
                AccountMapping.active_status == "YES",
                AccountMapping.account_code.like("8%")))).scalars()
        }
        for e in below:
            cod = str(e.account_code or "")
            _nombra(detalle, cod,
                    e.account_name or nombres_bg.get(cod, "")
                    or del_catalogo.get(cod, ""))

    for m in range(1, 13):
        col = MESES[m - 1]
        payroll = cost = opex = prop = ZERO

        # ⚠️ Las dos fuentes NO se suman: se ELIGE una, igual que hace el motor
        # en `compute_pl_month`. Un escenario puede tener las dos cargadas —el
        # Actual tiene checkbooks Y detalle del GL— y sumarlas da exactamente el
        # doble. Se probó contra produccion: daba 2,100,673 de planilla donde el
        # cuadro del owner dice 1,170,402.
        #
        # Manda el GL cuando el mes lo tiene, porque es el dato real; si no hay,
        # se cae a los checkbooks, que es lo proyectado.
        # ⚠️ **En un mes CERRADO de un forecast, el gasto sale del ACTUAL.**
        #
        # Owner, 2026-09-03, comparando dos cuadros. Este endpoint leía siempre
        # el mayor del PROPIO escenario, y un forecast no tiene mayor: caía
        # siempre al checkbook. Resultado, en el FORECAST Working 2026 con
        # corte en julio:
        #
        #     marzo, abril, mayo -> 0 en el cuadro y 12.189 / 25.851 / 56.027
        #                           en el P&L (el forecast no tiene checkbook
        #                           de esos meses; el ACTUAL sí tiene el mayor)
        #     junio, julio       -> 42.658 y 12.370 DE MÁS: mostraba lo
        #                           presupuestado sobre meses que ya cerraron
        #
        # Los dos cuadros salían de datos distintos y ninguno decía cuál. La
        # mezcla es la misma que hace `compute_pl_month`: hasta
        # `actuals_through` manda el ACTUAL enlazado, y de ahí en adelante el
        # propio escenario. Rehacerla acá con otro criterio sería exactamente
        # cómo el resumen y el P&L terminan contando dos historias.
        origen_gl = scenario_id
        if escenario.type == "FORECAST" and m <= (escenario.actuals_through or 0):
            enlazado = await recalc.linked_actual_scenario(session, escenario)
            if enlazado is not None:
                origen_gl = enlazado.id

        filas_gl = await recalc.actual_rows_for_month(session, origen_gl, m)
        if filas_gl:
            for r in filas_gl:
                cuenta = str(r["account_code"] or "")
                dept = str(r.get("dept_code") or "")
                monto = Decimal(str(r["amount"] or 0))
                # El TOTAL de la clase suma todo; lo que se filtra es la
                # apertura. Si se filtrara el total, la pantalla dejaria de
                # amarrar con el P&L y no habria como notarlo.
                # El pozo de reparto sale del TOTAL tambien, no solo de la
                # apertura. Si saliera solo de la apertura, el renglon TOTAL del
                # cuadro no sumaria sus propias filas — y un total que no cuadra
                # con lo que tiene encima es peor que no tenerlo.
                #
                # ⚠️ Solo del GASTO. La primera version cortaba antes de mirar la
                # clase y se llevaba puesto el INGRESO de la lavanderia: la venta
                # del año bajaba 3,450 sin que nada lo dijera.
                # ⚠️ El gasto de un departamento de REPARTO se cuenta, y su
                # crédito de distribución lo netea. Antes se descartaba el
                # departamento entero, y eso PERDÍA PLATA:
                #
                # el ACTUAL tiene el costo de Lavandería en el mayor —$1.121,36
                # en julio 2026, entre planilla y suministros— pero **cero
                # asientos de reparto**, porque un histórico no se reparte: se
                # sube como vino. La exclusión se lo llevaba y nada lo devolvía.
                #
                # Resultado: este cuadro decía 119.032,01 de gasto donde el P&L
                # dice 120.153,37. Y la diferencia iba contra el resultado, o
                # sea que el mes se veía MEJOR de lo que fue.
                #
                # El motor no lo descarta: lo que no alcanzó a repartirse queda
                # en overhead (`OH_LAUNDRY`), que es la regla del owner del
                # 2026-08-28 —«si tiene saldo que aparezca esa diferencia en
                # overhead»—. Acá se hace lo mismo por aritmética: el costo
                # entra y el crédito 49xx lo saca, así que en un escenario CON
                # reparto la cuenta da lo mismo que antes, y en uno sin reparto
                # ya no desaparece el sobrante.
                if cuenta in CUENTAS_DE_REPARTO:
                    opex += monto
                    if detalle is not None:
                        _suma(detalle, "opex", _padre(dept), m, monto)
                    continue
                if cuenta.startswith("5"):
                    cost += monto
                    if detalle is not None: _suma(detalle, "cost", dept, m, monto)
                elif cuenta.startswith("6"):
                    payroll += monto
                    if detalle is not None: _suma(detalle, "payroll", dept, m, monto)
                elif cuenta.startswith("7"):
                    opex += monto
                    if detalle is not None: _suma(detalle, "opex", dept, m, monto)
                elif cuenta.startswith("8"):
                    prop += monto
                    # Clase 8 por CUENTA, no por departamento.
                    if detalle is not None:
                        _suma(detalle, "property", cuenta, m, monto)
                elif (cuenta.startswith("4") and detalle is not None
                        and cuenta not in CUENTAS_DE_REPARTO):
                    # ⚠️ **El ingreso se indexa por LINEA, no por departamento**,
                    # y es lo que hace que el cuadro tenga una fila por concepto.
                    #
                    # Owner, 2026-09-02: *«necesito que los ingresos aparezcan en
                    # una sola linea; podes consolidar las lineas para no verlas
                    # separadas por tipo de ingreso»*.
                    #
                    # Las dos ramas de este endpoint traen el ingreso de fuentes
                    # que se indexan distinto: el mayor por DEPARTAMENTO (0110,
                    # 260…) y el checkbook por LINEA (`REV_ROOMS`, `REV_CLUB`…),
                    # porque un presupuesto de ingresos no tiene departamento.
                    # Con dos vocabularios el mismo concepto salia DOS VECES —
                    # «REV_ROOMS · Rooms Revenue» con el presupuesto y el actual
                    # en cero, y «0110 · Rooms / Habitaciones» al reves— y cada
                    # una mostraba una variacion de -100%.
                    #
                    # La linea es el unico vocabulario que ambos lados pueden
                    # hablar: el departamento no existe del lado del presupuesto.
                    # `linea_de_fila` la resuelve con las mismas funciones del
                    # motor y devuelve el codigo CANONICO, que es el que trae
                    # `pl_lines` en la otra rama.
                    ln_rev, _tipo = pl_engine.linea_de_fila(cuenta, dept)
                    # Sin linea no se descarta: se cae al departamento. Perder
                    # plata en silencio seria peor que una fila con nombre feo.
                    clave_rev = ln_rev or FUSION_INGRESO.get(dept, dept)
                    _suma(detalle, "revenue", clave_rev, m, monto)
        else:
            pbd = await recalc.payroll_by_dept(session, scenario_id, m)
            cbd = await recalc.cos_by_dept(session, scenario_id, m)
            obd = await recalc.opex_by_dept(session, scenario_id, m)
            # ⚠️ El gasto de los departamentos de reparto SE CUENTA, y su
            # crédito de distribución lo netea. Sacarlos de un lado y no sumar
            # el otro perdía el SOBRANTE: lo que no alcanzó a repartirse.
            #
            # Medido en el BUDGET 2026: entre 1.361 y 1.493 por mes, todos los
            # meses. El motor lo pone en overhead (`OH_LAUNDRY`) —regla del
            # owner del 2026-08-28: «si tiene saldo que aparezca esa diferencia
            # en overhead»— y acá desaparecía, así que el mes se veía mejor de
            # lo que era.
            abd = await recalc.alloc_by_dept(session, scenario_id, m)
            payroll = sum(pbd.values(), ZERO)
            cost = sum(cbd.values(), ZERO)
            opex = sum(obd.values(), ZERO) + sum(abd.values(), ZERO)
            prop = sum((Decimal(str(getattr(e, col) or 0)) for e in below), ZERO)
            if detalle is not None:
                # El reparto entra en la apertura de opex, igual que en el
                # total: si saliera sólo del total, el renglón TOTAL del cuadro
                # no sumaría sus propias filas.
                obd = {**obd, **{d: obd.get(d, ZERO) + v for d, v in abd.items()}}

                def _abrir(clase, datos):
                    for d, v in datos.items():
                        # ⚠️ **El sub-departamento se sube a su padre.**
                        #
                        # Owner, 2026-09-02, mirando el desglose: el ACTUAL
                        # consolida en departamentos padre y el checkbook usa
                        # sub-departamentos, asi que el cuadro salia con dos
                        # juegos de filas que no se cruzaban — `0110 · Rooms`
                        # con 38.054,38 y cero presupuesto, y `0111 · Front
                        # Desk`, `0113 · Housekeeping`, `0114 · Concierge` con
                        # presupuesto y cero actual. Comparar planilla por
                        # departamento no decia nada.
                        #
                        # Es el mismo defecto que el del ingreso, resuelto el
                        # mismo dia: dos vocabularios para la misma dimension.
                        # `consolidate_dept` es el mapa que el motor YA usa en
                        # el camino de checkbook (`CHECKBOOK_DEPT_CONSOLIDATION`),
                        # asi que el cuadro pasa a agrupar como el P&L.
                        #
                        # No cambia ningun total: solo junta claves.
                        _suma(detalle, clase, _padre(d), m, v)
                _abrir("payroll", pbd)
                _abrir("cost", cbd)
                _abrir("opex", obd)
                for e in below:
                    _suma(detalle, "property", str(e.account_code or ""), m,
                          Decimal(str(getattr(e, col) or 0)))
                # ⚠️ El INGRESO de un presupuesto armado con checkbooks NO tiene
                # departamento: se carga por LINEA (Rooms, Spa, Tours, Club…), y
                # una linea como ROOMS abarca cinco departamentos
                # (`OPERATING_DEPT_GROUPS`). Repartirla entre ellos seria inventar
                # una atribucion que nadie cargo.
                #
                # Antes esta rama simplemente no abria el ingreso, y el tab
                # «Revenue x Depto» salia vacio con el aviso «los presupuestos
                # armados solo con drivers no tienen detalle» — falso cuando SI
                # hay checkbook de ingresos (owner, 2026-08-27: «¿y por que aca
                # si sale?», mostrando el P&L con las mismas cifras).
                #
                # Sale de `pl_lines`, que es de donde las lee el tab de P&L. Es a
                # proposito: los dos cuadros muestran el mismo numero porque leen
                # la misma fila, no porque dos calculos coincidan.
                for ln in lineas_ingreso.get(m, []):
                    _suma(detalle, "revenue", ln.line_code, m,
                          Decimal(str(ln.amount_usd or 0)))

        filas.append({
            "month": m,
            "payroll": float(payroll), "cost": float(cost),
            "opex": float(opex), "property": float(prop),
            "total": float(payroll + cost + opex + prop),
        })
    return filas


@router.get("/gasto-por-clase/")
async def gasto_por_clase(
    scenarios: str = Query(..., description="ids separados por coma"),
    detalle: bool = Query(False, description="agrega la apertura por departamento"),
    _=Depends(get_current_user),
):
    """Los cuatro totales por clase, doce meses, para varios escenarios.

    Con `detalle=true` agrega la apertura: por departamento en planilla, costo,
    opex e ingreso; por CUENTA del mayor en gasto de propiedad, porque ahi todo
    vive en el mismo departamento y abrirlo por depto no diria nada."""
    ids = [x.strip() for x in scenarios.split(",") if x.strip()]
    if not ids:
        raise ErrorApi(422, "escenarios.requerido")
    salida = []
    async with get_session() as s:
        for sid in ids:
            e = await s.get(Scenario, sid)
            if e is None:
                continue   # un id que ya no existe no tumba la comparacion
            det: dict = {} if detalle else None
            meses = await _por_mes(s, sid, det)
            salida.append({
                "scenario_id": sid, "type": e.type,
                "version": e.version, "year": e.year,
                "meses": meses, "detalle": det,
                "nombres_cuenta": (det or {}).pop("__nombres__", {}) if det else {},
            })

    nombres: dict[str, str] = {}
    if detalle:
        from app.models.department_catalog import DepartmentCatalog
        async with get_session() as s:
            for d in (await s.execute(select(DepartmentCatalog))).scalars().all():
                nombres[d.dept_code] = d.dept_name
        # Los rótulos de las LINEAS de ingreso viajan en el mismo mapa que los de
        # departamento porque es el que la pantalla consulta para encabezar cada
        # fila. No chocan: un departamento es `0110` o `260`, una línea es
        # `REV_ROOMS`. Sin esto la fila diría «REV_ROOMS» a secas.
        for e in salida:
            nombres.update(e.get("nombres_cuenta") or {})
    return {"clases": CLASES, "escenarios": salida, "departamentos": nombres}
