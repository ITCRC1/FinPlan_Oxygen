# -*- coding: utf-8 -*-
"""La auditoría del detalle: cada monto del GL y en qué renglón del P&L terminó.

Owner, 2026-09-02, entregando `p&L auditoria 2026.xlsx` y `julio FORMAT
2026.xlsx`: *«necesito crear esos 2 tabs en cierre; uno para ver el detalle tal
cual el formato y el otro para ver la auditoría de los detalles»*.

## Qué contesta

Tres preguntas, en un solo viaje, para UN mes:

1. **¿De qué está hecha cada línea?** El detalle cuenta por cuenta, agrupado por
   departamento, con la naturaleza (Ingresos · Costo · Payroll · Opex · Reparto ·
   Bajo GOP) y el renglón del P&L al que cae.
2. **¿Cuadra?** Por cada línea del motor, cuánto suma su detalle y cuál es la
   diferencia. Es la columna «Dif.» del libro del owner.
3. **¿Cómo se reparte por departamento?** La matriz Ingresos / Costo / Payroll /
   Opex / Bajo GOP / Total gasto que él ya usa.

## Lo que hace válida a una auditoría

**Clasificar igual que el motor.** La atribución la hace
`pl_engine.linea_de_fila`, que reusa `group_for_dept`,
`revenue_line_for_account` y `nonop_line_for_account` — las mismas funciones que
usa `build_actual_inputs`. Repetir esas tablas acá daría un reporte que **cuadra
consigo mismo** y da el visto bueno justo cuando el P&L está mal.

⚠️ **Sólo tiene sentido sobre un escenario con detalle por cuenta**
(`actual_entries`), que es lo que dejan los actuales importados. Un BUDGET
armado en los checkbooks no tiene GL: se contesta con el detalle vacío y se
dice por qué, en vez de devolver ceros que se leerían como «no hay nada».

## Lo que NO trae, y no es un olvido

**La cuenta contable local** (`61011101 Salarios`) y el renglón del archivo
fuente. El GL que importa la app viene codificado en USALI de cuatro dígitos
—`_acct_code` exige exactamente cuatro— y la cuenta local **no se guarda con el
monto en ninguna tabla**. Inventarla sería justo lo que este libro no puede
hacer. Para tenerla haría falta que el importador la conserve; queda dicho en el
`aviso` de la respuesta para que se vea en pantalla y no sólo acá.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import select

from app.api.pl_api import _get_scenario_or_404, _monthly_results, get_session
from app.engine import pl_engine
from app.errores import ErrorApi
from app.models.actual_entry import ActualEntry
from app.models.department_catalog import DepartmentCatalog
from app.models.mapping import AccountMapping
from app.nombres_cuenta import limpiar_nombre

router = APIRouter(tags=["auditoria"])

MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]

#: Las columnas de la matriz por departamento, en el orden del libro del owner.
COLUMNAS = [pl_engine.TIPO_INGRESO, pl_engine.TIPO_COSTO, pl_engine.TIPO_PAYROLL,
            pl_engine.TIPO_OPEX, pl_engine.TIPO_REPARTO, pl_engine.TIPO_BAJO_GOP]

#: Qué naturalezas son GASTO. El reparto entra —es un crédito, resta— y el
#: ingreso no. Sin esta distinción el «total gasto» de un departamento de
#: reparto saldría bruto y no netearía.
GASTO = {pl_engine.TIPO_COSTO, pl_engine.TIPO_PAYROLL, pl_engine.TIPO_OPEX,
         pl_engine.TIPO_REPARTO, pl_engine.TIPO_BAJO_GOP}

CERO = Decimal("0")

#: Los renglones que se leen de un vistazo: los que un dueño busca primero.
#:
#: Owner, 2026-09-03: *«meté líneas bold y cuadros para que se lea bien: total
#: ingresos, total gastos, net profit, un subtotal bien identificado»*.
#:
#: ⚠️ Se marcan en el BACKEND y no en la pantalla porque el rótulo cambia
#: —«TOTAL GROSS OPERATING PROFIT» hoy, otra cosa mañana— y comparar textos en
#: el front dejaría de resaltar la línea sin que nada fallara. El `line_code`
#: es lo estable.
HITOS = {"TOTAL_REVENUES", "TOTAL_OPERATING_EXPENSES", "OPERATING_PROFIT",
         "TOTAL_OVERHEAD", "GOP", "EBITDA_BEFORE", "EBITDA_AFTER", "EBT",
         "NET_PROFIT"}

#: Nombre de cuenta cuando el asiento vino sin él.
#:
#: Owner, 2026-09-03: *«que todas las cuentas lleven nombre»*.
#:
#: Medido en producción sobre el ACTUAL Final 2026: de 115 asientos, los ÚNICOS
#: sin nombre son 13 códigos, y los trece son de planilla (60xx). No es un dato
#: perdido: la planilla no se importa del GL cuenta por cuenta, viene del bloque
#: de nómina, que trae el concepto y no su rótulo.
#:
#: ⚠️ Los nombres NO se escriben acá: se leen de `consulta_api.CONCEPTOS`, que
#: es de donde salen los mismos rótulos en Consulta y en Account Mapping. Una
#: segunda lista sería la garantía de que un día el mismo 6023 se llame
#: «Vacation Provision» en un reporte y otra cosa en el de al lado.
#:
#: Los catálogos `accounts` y `payroll_accounts` están VACÍOS en producción
#: (0 filas), así que no hay de dónde sacarlos por ahí; el día que se carguen,
#: este respaldo sigue siendo correcto porque dice lo mismo.
def _nombres_de_planilla() -> dict[str, str]:
    from app.api.consulta_api import CONCEPTOS
    return {codigo: rotulo for _campo, codigo, rotulo in CONCEPTOS}


async def _catalogo_gl(session) -> dict[tuple[str, str], str]:
    """Qué cuentas de GL puede tener cada departamento, y cómo se llaman.

    Owner, 2026-09-03: *«me gustaría todas las opciones que tiene cada
    departamento en cuanto a GL … pero que haya el 100% de los datos siempre»*.

    Sale de `account_mapping`, que es el catálogo real: 1.098 reglas sobre 27
    departamentos en producción, y **toda** cuenta del ACTUAL 2026 tiene una.
    Es una TABLA, editable sin desplegar — no una lista en el código.

    Devuelve `{(dept, cuenta): nombre}`.

    ⚠️ Sólo las reglas ACTIVAS. Una dada de baja describe cómo se clasificaba
    ANTES; ofrecerla como opción vigente invitaría a usarla de nuevo.
    """
    filas = (await session.execute(
        select(AccountMapping.dept_code, AccountMapping.account_code,
               AccountMapping.account_name_example)
        .where(AccountMapping.active_status == "YES"))).all()
    return {
        (dept or "", cuenta): (nombre or "").strip()
        for dept, cuenta, nombre in filas
    }


def _f(x) -> float:
    return float(x or 0)

#: Los doce meses, en el orden de las columnas de los checkbooks.
_MESES_COL = ["jan", "feb", "mar", "apr", "may", "jun",
              "jul", "aug", "sep", "oct", "nov", "dec"]


class _AsientoDeCheckbook:
    """Un asiento SINTETICO, armado desde los checkbooks.

    Imita lo justo de `ActualEntry` para que el resto de la auditoria no
    tenga que saber de donde salio: codigo, departamento, nombre y las doce
    columnas de mes.

    ⚠️ **No es un asiento del mayor y no se guarda en ninguna tabla.** Vive
    lo que dura la respuesta. Un presupuesto no tiene GL importado; lo que
    tiene es la cuenta contable con la que se digito cada linea del
    checkbook, y eso es lo que se muestra — sin decir que viene del mayor.
    """

    __slots__ = ("account_code", "dept_code", "account_name", "outlet",
                 "_serie", "linea_propia", "tipo_propio")

    def __init__(self, dept, cuenta, nombre, serie,
                 linea_propia=None, tipo_propio=""):
        self.account_code = cuenta
        self.dept_code = dept
        self.account_name = nombre
        self.outlet = ""
        self._serie = serie
        #: ⚠️ El INGRESO de un presupuesto se planea POR LÍNEA, no por cuenta:
        #: el checkbook guarda `REV_ROOMS`, no una 4xxx. `linea_de_fila` mira
        #: el primer dígito del código y una línea no tiene dígito, así que
        #: devolvía «sin tipo» y los ingresos se contaban como estadística —
        #: 29.472 de junio de 2027 quedaban fuera del cuadre. Cuando la fila ya
        #: sabe a qué renglón va, se respeta.
        self.linea_propia = linea_propia
        self.tipo_propio = tipo_propio

    def __getattr__(self, nombre):
        try:
            return self._serie[_MESES_COL.index(nombre)]
        except ValueError:
            raise AttributeError(nombre) from None


async def _asientos_del_checkbook(session, escenario) -> list:
    """El detalle por cuenta de una version SIN mayor: sale de los checkbooks.

    Owner, 2026-09-03: *«el presupuesto debe tener gl, siempre debe estar
    conectado a un gl»*. Y lo esta: las filas de opex y de costo se digitan
    con su `account_code` —en el BUDGET 2027 de Oxygen, cero nulos sobre 140
    filas—, y la planilla guarda los 17 conceptos, que son cuentas del mayor.
    Lo que faltaba no era el dato: era leerlo.

    ⚠️ **Reusa `_del_auxiliar`, no una copia.** Esa funcion ya resuelve las
    cuatro trampas de leer un checkbook —la cadena de departamentos padre, el
    reparto de lavanderia y cafeteria por mes, los conceptos de planilla como
    cuentas, y el ingreso por cuenta—. Reescribirlas aca daria dos lecturas
    del mismo checkbook que un dia dirian cosas distintas.
    """
    # Adentro de la funcion: `detalle_celda_api` importa de `pl_api`, igual
    # que este modulo, y a nivel de modulo se cerraria el circulo.
    from app.api.detalle_celda_api import _del_auxiliar

    fuera = []
    for clase in ("revenue", "cost", "payroll", "opex", "property"):
        r = await _del_auxiliar(session, escenario, clase, "")
        nombres = r.get("nombres") or {}
        for (dept, cuenta), serie in (r.get("series") or {}).items():
            if not cuenta:
                continue
            # ⚠️ El ingreso llega con el GRUPO pelado como llave —`ROOMS`,
            # `ACTIVITIES`—, no con una cuenta ni con la línea. La traducción
            # sale de `REVENUE_LINE_TO_REPORT_LINE`, que es **la tabla del
            # motor** y existe justo para esto: versiones cuyo ingreso viene a
            # nivel de línea, sin detalle 4xxx.
            #
            # Pegar `"REV_" + grupo` parecía equivalente y no lo es: el grupo
            # `ACTIVITIES` alimenta la línea `REV_TOURS`, así que la
            # concatenación producía `REV_ACTIVITIES` —un renglón que el
            # reporte no dibuja— y los 10.800 del año quedaban huérfanos. Una
            # tabla propia acá tendría el mismo destino la próxima vez.
            # ⚠️ Y sólo cuando la llave NO es una cuenta. El ingreso del
            # Club de Amarena llega con 4500/4501/4502 —cuentas del mayor de
            # verdad—, y traducirlas como si fueran un grupo producía
            # `REV_4500`: 17.200 huérfanos por mes. Numérica es cuenta, y la
            # resuelve `linea_de_fila` como cualquier otra.
            if clase == "revenue" and not cuenta.strip().isdigit():
                linea = pl_engine._canon(
                    pl_engine.REVENUE_LINE_TO_REPORT_LINE.get(cuenta.lower())
                    or "REV_%s" % cuenta)
                fuera.append(_AsientoDeCheckbook(
                    "", cuenta, nombres.get(linea, "") or nombres.get(cuenta, ""),
                    serie, linea_propia=linea,
                    tipo_propio=pl_engine.TIPO_INGRESO))
                continue
            fuera.append(_AsientoDeCheckbook(
                dept or "", cuenta, nombres.get(cuenta, ""), serie))
    return fuera




@router.get("/pl/{scenario_id}/auditoria/")
async def auditoria_del_mes(scenario_id: str, mes: int):
    """El detalle de UN mes, cuadrado contra las líneas del motor."""
    if not 1 <= mes <= 12:
        raise ErrorApi(422, "mes.rango_invalido")

    async with get_session() as session:
        escenario = await _get_scenario_or_404(session, scenario_id)
        col = MESES[mes - 1]

        nombres = {
            d.dept_code: d.dept_name
            for d in (await session.execute(select(DepartmentCatalog))).scalars()
        }
        rotulo_planilla = _nombres_de_planilla()
        catalogo = await _catalogo_gl(session)

        # ── 1. El detalle, fila por fila ──────────────────────────────────────
        #
        # ⚠️ Se leen TODOS los asientos, no sólo los que tienen monto, para
        # poder decir cuántos hay y qué pasó con cada uno. Owner, 2026-09-03:
        # *«que haya el 100% de los datos siempre»*. Una auditoría que descarta
        # filas en silencio no puede demostrar que no descartó nada.
        todos = list((await session.execute(select(ActualEntry).where(
            ActualEntry.scenario_id == scenario_id))).scalars())

        # Sin mayor, se auditan los checkbooks. Un BUDGET no tiene asientos
        # importados, pero SI tiene la cuenta contable de cada linea digitada
        # — ver `_asientos_del_checkbook`.
        del_checkbook = not todos
        if del_checkbook:
            todos = await _asientos_del_checkbook(session, escenario)

        detalle = []
        por_linea: dict[str, Decimal] = {}
        por_depto: dict[str, dict[str, Decimal]] = {}
        vistas: set[tuple[str, str]] = set()
        n_con_monto = n_sin_tipo = 0
        monto_sin_tipo = CERO

        def _nombre(dept: str, cuenta: str, propio: str | None = None) -> str:
            """El nombre de una cuenta. Nunca vacío.

            El orden importa: primero lo que trajo el asiento —es el nombre con
            el que vino del GL—, después el catálogo del departamento, después
            los conceptos de planilla, y recién al final el código.

            En producción, de 115 asientos los ÚNICOS sin nombre propio son 13
            códigos de planilla (60xx): no se importan del GL cuenta por cuenta,
            vienen del bloque de nómina, que trae el concepto y no su rótulo.
            """
            # ⚠️ Se LIMPIA. `account_name` y `account_name_example` traen
            # todas las variantes vistas en el mayor pegadas con barras
            # —«DEPRECIATION1 | DEPRECIATION2 | DEPRECIATION»—, y eso no es un
            # rótulo: son sesenta caracteres donde caben veinte.
            return (limpiar_nombre(propio)
                    or limpiar_nombre(catalogo.get((dept, cuenta), ""))
                    or rotulo_planilla.get(cuenta, "")
                    or f"Cuenta {cuenta}")

        for e in todos:
            monto = Decimal(str(getattr(e, col, None) or 0))
            linea = getattr(e, "linea_propia", None)
            tipo = getattr(e, "tipo_propio", "")
            if not linea:
                linea, tipo = pl_engine.linea_de_fila(e.account_code, e.dept_code)
            if not tipo:
                # 9xxx: estadística, no es plata. Se CUENTA en vez de
                # desaparecer, para que el total del mes se pueda comprobar.
                if monto != CERO:
                    n_sin_tipo += 1
                    monto_sin_tipo += monto
                continue
            vistas.add((e.dept_code, e.account_code))
            if monto == CERO:
                continue
            n_con_monto += 1
            detalle.append({
                "dept_code": e.dept_code,
                "dept_name": nombres.get(e.dept_code, e.dept_code),
                "account_code": e.account_code,
                "account_name": _nombre(e.dept_code, e.account_code, e.account_name),
                "outlet": e.outlet,
                "tipo": tipo,
                "linea": linea,
                "monto": _f(monto),
                "movimiento": True,
            })
            if linea:
                por_linea[linea] = por_linea.get(linea, CERO) + monto
            caja = por_depto.setdefault(e.dept_code, {c: CERO for c in COLUMNAS})
            caja[tipo] = caja.get(tipo, CERO) + monto

        # ── 1b. Las opciones de GL que el departamento tiene y NO usó ─────────
        #
        # Owner: *«todas las opciones que tiene cada departamento en cuanto a
        # GL»*. Sin esto sólo se ve lo que se movió, y una cuenta que DEBERÍA
        # tener monto y no lo tiene es invisible — que es el error más difícil
        # de encontrar: no se ve nada raro, se ve menos.
        #
        # ⚠️ Van marcadas `movimiento: false` y en CERO. No se inventa nada: se
        # dice que la opción existe y que este mes no se usó. La pantalla las
        # esconde con el interruptor «Compacto», que ya existe.
        #
        # Sólo de los departamentos que tienen algo este mes: ofrecer las 51
        # cuentas de un departamento que no operó llenaría el reporte de ruido.
        # ⚠️ Sólo donde el departamento SE MOVIÓ en esa naturaleza.
        #
        # Owner, 2026-09-03: *«nada que sale bien en auditoría, en la parte de
        # abajo cuando empiezan los departamentos»*. Medido en julio: el Club
        # tenía 30 cuentas de opex y 12 de planilla, casi todas en cero, y los
        # tres montos reales quedaban enterrados entre ellas.
        #
        # Ofrecer las 17 cuentas de planilla de un departamento que no tiene
        # planilla no muestra una opción: inventa un bloque entero de ruido con
        # un subtotal de cero. Las opciones sirven donde hay algo que comparar
        # —«esta cuenta la usás y aquélla no»—, no donde no hay nada.
        con_movimiento = {
            (r["dept_code"], r["tipo"]) for r in detalle if r["movimiento"]
        }
        for (dept, cuenta), nombre in sorted(catalogo.items()):
            if dept not in por_depto or (dept, cuenta) in vistas:
                continue
            linea, tipo = pl_engine.linea_de_fila(cuenta, dept)
            if not tipo or (dept, tipo) not in con_movimiento:
                continue
            detalle.append({
                "dept_code": dept,
                "dept_name": nombres.get(dept, dept),
                "account_code": cuenta,
                "account_name": _nombre(dept, cuenta, nombre),
                "outlet": None,
                "tipo": tipo,
                "linea": linea,
                "monto": 0.0,
                "movimiento": False,
            })

        detalle.sort(key=lambda r: (r["dept_code"], r["tipo"], r["account_code"]))

        # ── 2. El cuadre, POR RENGLÓN DEL REPORTE ─────────────────────────
        #
        # ⚠️ **No línea por línea, RENGLÓN por renglón**, y la diferencia no es
        # cosmética. El primer intento comparó cada `line_code` suelto y
        # reportó 37 descuadres en julio 2026, **todos falsos**, por dos
        # razones distintas:
        #
        # * los TOTALES y SUBTOTALES (`GOP`, `EBITDA_BEFORE`,
        #   `TOTAL_DEPRECIATIONS`) no tienen detalle propio: son sumas de otros
        #   renglones, así que su «detalle» siempre da cero;
        # * el vocabulario canónico parte el gasto de un departamento en varias
        #   líneas —`OPEX_FB` + `COS_FB_FOOD` + `COS_FB_BEV`— y el detalle
        #   atribuye a una sola. Cada par se descuadraba por el mismo monto con
        #   signos opuestos.
        #
        # El renglón del reporte agrupa justamente esos códigos, así que las
        # dos cosas se resuelven solas. Y es el nivel al que el owner audita:
        # él mira «Rooms», no `COS_FB_BEV`.
        #
        # La plantilla se importa de `pl_detail_api`: si cambia el reporte,
        # cambia la auditoría con él. Escribir una copia sería garantizar que
        # un día auditen cosas distintas.
        from app.api.pl_detail_api import CONSOLIDADO

        mensual = await _monthly_results(session, escenario)
        del_mes = next((m for m in mensual if m["month"] == mes), None)
        lineas_motor = {l.line_code: l for l in (del_mes or {}).get("lines", [])}

        # Los renglones DERIVADOS quedan afuera: el bloque de Operating Profit
        # es ingreso menos gasto, no se compone de asientos, y su «detalle»
        # siempre daría cero. En julio 2026 eran seis descuadres inventados.
        atribuibles = pl_engine.codigos_atribuibles()

        # ⚠️ Se recorre la plantilla ENTERA —secciones, renglones, totales y
        # blancos—, no sólo los renglones con detalle.
        #
        # Owner, 2026-09-03: *«esto es un resumen, pero favor que tenga un
        # formato de P&L, donde hay ingresos, gastos operativos, overhead; un
        # P&L formal»*.
        #
        # Antes se filtraba `tipo != "det"` y salía una lista plana en la que
        # **«Rooms» aparecía dos veces** —una por el ingreso y otra por el
        # gasto— sin nada que dijera cuál era cuál. Los $36.218,36 y los
        # $17.847,68 se leían como dos versiones del mismo número.
        #
        # La estructura la pone la MISMA plantilla que dibuja el reporte: si
        # cambia el P&L, cambia la auditoría con él.
        cuadre = []
        atribuidos: set[str] = set()
        for tipo, rotulo, codigos in CONSOLIDADO:
            if tipo == "esp":
                cuadre.append({"tipo": "esp", "linea": "", "nombre": "",
                               "seccion": "", "hito": False, "motor": None,
                               "detalle": None, "dif": None})
                continue
            if tipo == "sec":
                cuadre.append({"tipo": "sec", "linea": "", "nombre": rotulo,
                               "seccion": "", "hito": False, "motor": None,
                               "detalle": None, "dif": None})
                continue

            motor = sum((Decimal(str(lineas_motor[c].amount_usd))
                         for c in codigos if c in lineas_motor), CERO)

            # Un TOTAL o SUBTOTAL no tiene detalle propio: es la suma de otros
            # renglones. Comparar su «detalle» daría cero contra el total y
            # sería un descuadre inventado — los seis del primer intento.
            #
            # ⚠️ El `sub` estaba sin tratar y caía en la rama de detalle, así
            # que `TOTAL RENT AND MANAGEMENT FEES` y sus tres hermanos se
            # auditaban como si fueran renglones.
            if tipo in ("tot", "sub"):
                cuadre.append({"tipo": tipo, "linea": " · ".join(codigos),
                               "nombre": rotulo, "seccion": "",
                               "hito": any(c in HITOS for c in codigos),
                               "motor": _f(motor), "detalle": None, "dif": None})
                continue

            # Y un renglón DERIVADO —el bloque de Operating Profit es ingreso
            # menos gasto— tampoco se compone de asientos. Se muestra, porque
            # es parte del P&L, pero sin columnas de auditoría.
            if not any(c in atribuibles for c in codigos):
                if motor != CERO:
                    cuadre.append({"tipo": "der", "linea": " · ".join(codigos),
                                   "nombre": rotulo, "seccion": "",
                                   "hito": False, "motor": _f(motor),
                                   "detalle": None, "dif": None})
                continue

            det = sum((por_linea.get(c, CERO) for c in codigos), CERO)
            atribuidos.update(codigos)
            if motor == CERO and det == CERO:
                continue
            cuadre.append({
                "tipo": "det",
                "linea": " · ".join(codigos),
                "nombre": rotulo,
                "seccion": "",
                "hito": False,
                "motor": _f(motor),
                "detalle": _f(det),
                "dif": _f(motor - det),
            })

        # Lo que el detalle atribuye a un código que NINGÚN renglón dibuja. No
        # debería pasar; si pasa, es exactamente lo que hay que ver, porque esa
        # plata está en los totales y en ninguna fila.
        huerfanas = [(c, d) for c, d in sorted(por_linea.items())
                     if c not in atribuidos and d != CERO]
        if huerfanas:
            cuadre.append({"tipo": "esp", "linea": "", "nombre": "",
                           "seccion": "", "hito": False, "motor": None,
                           "detalle": None, "dif": None})
            cuadre.append({"tipo": "sec", "linea": "",
                           "nombre": "NO CAEN EN NINGÚN RENGLÓN", "seccion": "",
                           "hito": False, "motor": None, "detalle": None,
                           "dif": None})
            for code, det in huerfanas:
                cuadre.append({
                    "tipo": "det", "linea": code, "hito": False,
                    "nombre": "(ningún renglón lo dibuja)", "seccion": "HUERFANO",
                    "motor": 0.0, "detalle": _f(det), "dif": _f(-det)})

        # ── 3. La matriz por departamento ─────────────────────────────────────
        departamentos = []
        for dept in sorted(por_depto):
            caja = por_depto[dept]
            departamentos.append({
                "dept_code": dept,
                "dept_name": nombres.get(dept, dept),
                **{c: _f(caja.get(c, CERO)) for c in COLUMNAS},
                "total_gasto": _f(sum((caja.get(c, CERO) for c in GASTO), CERO)),
            })
        totales = {c: round(sum(d[c] for d in departamentos), 2) for c in COLUMNAS}
        totales["total_gasto"] = round(
            sum(d["total_gasto"] for d in departamentos), 2)

        # ── 3b. Los tres números de cabecera ─────────────────────────────────
        #
        # Owner, 2026-09-03: *«total ingresos, total gastos, net profit»*.
        #
        # ⚠️ **TOTAL GASTOS no existe como línea del P&L**, y no se inventa una:
        # se deduce de la identidad del propio estado —lo que entró menos lo que
        # quedó—. Sumar renglones a mano acá sería una segunda aritmética que el
        # día que se agregue un bloque al P&L dejaría de cuadrar en silencio.
        #
        # Es además el número que el owner estaba cotejando cuando encontró que
        # el Resumen 12m y el P&L diferían en los $1.121,36 de lavandería.
        def _linea(code: str) -> Decimal:
            fila = lineas_motor.get(code)
            return Decimal(str(fila.amount_usd)) if fila else CERO

        ingresos = _linea("TOTAL_REVENUES")
        neto = _linea("NET_PROFIT")
        resumen = {
            "ingresos": _f(ingresos),
            "gastos": _f(ingresos - neto),
            "neto": _f(neto),
        }

        # ── 4. La cobertura: la prueba de que no se descartó nada ────────────
        #
        # Owner, 2026-09-03: *«que haya el 100% de los datos siempre»*.
        #
        # ⚠️ Esto NO es adorno: es lo único que distingue «no hay más» de «hay
        # más y no lo estoy mostrando». Antes el endpoint filtraba los montos
        # en cero y saltaba las cuentas 9xxx sin decirlo, así que un reporte al
        # que le faltaba media hoja se veía exactamente igual que uno completo.
        #
        # `suma_detalle` tiene que dar lo mismo que sumar la columna del mes en
        # `actual_entries` menos lo estadístico. Si no da, hay un asiento que
        # este reporte no está contando y el número de arriba lo delata.
        cobertura = {
            "asientos": len(todos),
            "con_monto": n_con_monto,
            "en_cero": len(todos) - n_con_monto - n_sin_tipo,
            "estadisticos": n_sin_tipo,
            "monto_estadistico": _f(monto_sin_tipo),
            "opciones_gl": sum(1 for r in detalle if not r["movimiento"]),
            "suma_detalle": round(
                sum(r["monto"] for r in detalle if r["movimiento"]), 2),
        }

        # ── 5. Los avisos ─────────────────────────────────────────────────────
        avisos = []
        if not n_con_monto:
            avisos.append(
                "Este escenario no tiene detalle por cuenta cargado para el "
                "mes: ni asientos del mayor, ni líneas digitadas en los "
                "checkbooks con su cuenta contable.")
        elif del_checkbook:
            # ⚠️ Se DICE de dónde salió. El detalle de un presupuesto no es un
            # asiento del mayor —nadie lo contabilizó— sino la cuenta con la
            # que se planeó cada línea. Mostrarlo sin aclararlo lo haría pasar
            # por contabilidad, que es exactamente lo que este libro no puede
            # hacer.
            avisos.append(
                "El detalle sale de los checkbooks, no del mayor: es la cuenta "
                "contable con la que se planeó cada línea. Esta versión no "
                "tiene actuales importados.")
        # ⚠️ Sólo las que TIENEN movimiento. Una opción del catálogo en cero
        # que no cae en ninguna línea no es plata perdida: es una opción que no
        # se usó. Contarla acá inventaría un problema.
        huerfanos = [r for r in detalle if not r["linea"] and r["movimiento"]]
        if huerfanos:
            avisos.append(
                f"{len(huerfanos)} fila(s) no caen en ninguna línea del P&L y "
                f"por eso NO suman: revisá su departamento y su cuenta.")
        # ⚠️ `dif` es None en las secciones, los blancos, los totales y los
        # renglones derivados: esos no tienen detalle contra qué compararse.
        # Sin el `is not None`, contar descuadres revienta con un TypeError.
        descuadres = [c for c in cuadre
                      if c["dif"] is not None and abs(c["dif"]) >= 0.005]
        if descuadres:
            avisos.append(
                f"{len(descuadres)} línea(s) no cuadran contra su detalle.")

        return {
            "scenario_id": scenario_id,
            "escenario": f"{escenario.type} {escenario.version} {escenario.year}",
            "year": escenario.year,
            "mes": mes,
            "detalle": detalle,
            "cuadre": cuadre,
            "departamentos": departamentos,
            "totales": totales,
            "columnas": COLUMNAS,
            "cobertura": cobertura,
            "resumen": resumen,
            "avisos": avisos,
            "nota_cuenta_local": (
                "El GL que importa la app viene en códigos USALI de cuatro "
                "dígitos. La cuenta contable local (ej. 61011101) no se guarda "
                "junto al monto en ninguna tabla, así que no se puede mostrar "
                "sin inventarla."),
        }
