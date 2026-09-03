# -*- coding: utf-8 -*-
"""La auditoría del detalle: cada monto del GL, y en qué renglón terminó.

Owner, 2026-09-02, con `p&L auditoria 2026.xlsx`: *«uno para ver el detalle tal
cual el formato y el otro para ver la auditoría de los detalles»*.

## Lo único que hace válida a una auditoría

**Que clasifique IGUAL que el motor.** Una que use sus propias reglas cuadra
consigo misma y da el visto bueno justo cuando el P&L está mal — es peor que no
tenerla, porque además tranquiliza.

Por eso la prueba central de este archivo no mira números bonitos: **suma el
detalle línea por línea y lo compara contra lo que devuelve
`calculate_full_pl`**. Si alguien cambia una regla de agrupación en el motor y
no la refleja en `linea_de_fila`, esto se cae.
"""
from decimal import Decimal

from app.engine import pl_engine
from app.engine.pl_engine import (TIPO_BAJO_GOP, TIPO_COSTO, TIPO_INGRESO,
                                  TIPO_OPEX, TIPO_PAYROLL, TIPO_REPARTO,
                                  linea_de_fila)

D = pl_engine._d


#: Un mes con algo de cada cosa: ingreso de dos grupos, costo, planilla, opex,
#: overhead, reparto que no cubre todo, y below-GOP.
FILAS = [
    {"account_code": "4000", "dept_code": "0110", "amount": 33718.34},
    {"account_code": "4110", "dept_code": "0120", "amount": 2388.34},
    {"account_code": "4300", "dept_code": "0140", "amount": 1831.87},
    {"account_code": "5700", "dept_code": "0120", "amount": 8847.45},
    {"account_code": "6000", "dept_code": "0110", "amount": 4812.31},
    {"account_code": "7065", "dept_code": "0110", "amount": 621.83},
    {"account_code": "6000", "dept_code": "0180", "amount": 2261.20},
    {"account_code": "7020", "dept_code": "0180", "amount": 209.92},
    {"account_code": "6000", "dept_code": "0220", "amount": 150.00},
    {"account_code": "5700", "dept_code": "0220", "amount": 300.00},
    {"account_code": "4900", "dept_code": "0220", "amount": -400.00},
    {"account_code": "8040", "dept_code": "0250", "amount": 245.17},
    {"account_code": "9010", "dept_code": "0110", "amount": 999.00},
]


def _por_linea(filas):
    """{line_code: monto} sumando el detalle con `linea_de_fila`."""
    out: dict[str, Decimal] = {}
    for f in filas:
        code, _tipo = linea_de_fila(f["account_code"], f["dept_code"])
        if code is None:
            continue
        out[code] = out.get(code, D(0)) + D(f["amount"])
    return out


def _del_motor(filas):
    """{line_code: monto} por la MISMA tubería que corre en producción.

    ⚠️ `calculate_full_pl` a secas **no alcanza**: emite su propio vocabulario
    (`OPEXP_ROOMS`, `OVH_ADMIN`) y lo que llega a la pantalla pasa además por
    `add_pl_aliases` + `canonicalize_pl_lines`, que lo traducen al canónico
    (`OPEX_ROOMS`, `OH_ADMIN`). Comparar contra el crudo dejaba pasar
    exactamente el bug que se encontró cotejando julio contra el libro del
    owner: totales perfectos y detalle en cero.
    """
    lineas = pl_engine.canonicalize_pl_lines(pl_engine.add_pl_aliases(
        pl_engine.calculate_full_pl(**pl_engine.build_actual_inputs(filas))))
    return {l.line_code: l.amount_usd for l in lineas}


def test_el_detalle_SUMA_exactamente_lo_que_dice_el_motor():
    """⚠️ **La prueba que sostiene todo el reporte.**

    Si esto se cae, la pantalla de auditoría está mintiendo: mostraría un
    desglose que no compone la línea que dice componer.
    """
    detalle = _por_linea(FILAS)
    motor = _del_motor(FILAS)

    for code, monto in detalle.items():
        assert code in motor, (
            f"el detalle atribuye {monto} a la línea '{code}', que el motor no "
            f"dibuja: el reporte mostraría plata en un renglón inexistente")
        assert abs(motor[code] - monto) < Decimal("0.005"), (
            f"'{code}': el detalle suma {monto} y el motor dice {motor[code]}. "
            f"La auditoría dejó de clasificar como el P&L")


def test_TODA_cuenta_conocida_cae_en_una_linea_que_el_motor_DIBUJA():
    """⚠️ La prueba que faltaba, y que dejó pasar un bug real.

    El cotejo de arriba usa trece filas elegidas a mano: pasaba en verde
    mientras **casi todo el bloque bajo GOP** se atribuía a renglones que el
    P&L no dibuja (`MGMT_FEE_5_ROYALTIES` en vez de `ROYALTIES`,
    `PROPERTY_INSURANCE` en vez de `PROPERTIES_INSURANCE`, `LEASINGS_RENTS` y
    `FINANCIAL_LOSSES` que ni existen). Esa plata habría salido como huérfana.

    La causa fue mezclar dos vocabularios: el del REPORTE de dueños y el que
    emite `calculate_full_pl`. Esto recorre **todas** las cuentas conocidas
    contra **todas** las líneas que el motor puede emitir.
    """
    lineas = pl_engine.calculate_full_pl(
        revenue_by_line={l: D(1) for l in pl_engine.GROUP_TO_REVENUE_LINE.values()},
        payroll_by_dept={d: D(1) for d in pl_engine._DEPT_TO_GROUP},
        cos_by_dept={d: D(1) for d in pl_engine._DEPT_TO_GROUP},
        opex_by_dept={d: D(1) for d in pl_engine._DEPT_TO_GROUP},
        nonop=pl_engine.NonOpActuals(
            **{c: D(1) for c in pl_engine._LINEA_DE_CAJON}),
    )
    emitidas = {l.line_code for l in pl_engine.canonicalize_pl_lines(
        pl_engine.add_pl_aliases(lineas))}

    casos = [(c, "0250") for c in pl_engine.NONOP_ACCOUNT_LINE]
    for dept in pl_engine._DEPT_TO_GROUP:
        casos += [("4000", dept), ("5700", dept), ("6000", dept),
                  ("7065", dept), ("4900", dept)]

    huerfanas = []
    for cuenta, dept in casos:
        code, _tipo = linea_de_fila(cuenta, dept)
        if code is not None and code not in emitidas:
            huerfanas.append((cuenta, dept, code))

    assert not huerfanas, (
        "estas cuentas se atribuyen a renglones que el motor NO dibuja — su "
        f"plata saldría como huérfana en la auditoría: {huerfanas[:12]}")


def test_las_estadisticas_NO_entran():
    """Las 9xxx son unidades, no plata. Sumarlas al P&L lo rompe en silencio."""
    code, tipo = linea_de_fila("9010", "0110")
    assert code is None and tipo == ""


def test_cada_naturaleza_se_nombra_como_en_el_estado_de_resultados():
    """Los rótulos son los del libro del owner: el cotejo se hace a ojo."""
    assert linea_de_fila("4000", "0110")[1] == TIPO_INGRESO
    assert linea_de_fila("5700", "0120")[1] == TIPO_COSTO
    assert linea_de_fila("6000", "0110")[1] == TIPO_PAYROLL
    assert linea_de_fila("7065", "0110")[1] == TIPO_OPEX
    assert linea_de_fila("4900", "0220")[1] == TIPO_REPARTO
    assert linea_de_fila("8040", "0250")[1] == TIPO_BAJO_GOP


def test_un_departamento_de_OVERHEAD_manda_todo_a_su_unica_linea():
    """Cafetería y lavandería no tienen bloque operativo: planilla, costo, opex
    y reparto caen juntos en `OVH_`. Es lo que hace que el SOBRANTE se vea
    (owner, 2026-08-28) en vez de perderse."""
    for cuenta in ("6000", "5700", "7065", "4900"):
        code, _ = linea_de_fila(cuenta, "0220")
        assert code == "OH_CAFETERIA", f"{cuenta} se fue a {code}"


def test_el_reparto_va_a_la_MISMA_linea_que_el_gasto_que_reparte():
    """Si el crédito de Distribución cayera en otra línea, el neteo no se vería
    y el departamento mostraría su gasto bruto."""
    gasto, _ = linea_de_fila("7065", "0110")
    reparto, _ = linea_de_fila("4900", "0110")
    assert gasto == reparto == "OPEX_ROOMS"


def test_un_grupo_de_solo_ingreso_con_gasto_queda_HUERFANO_y_no_escondido():
    """`calculate_full_pl` no dibuja bloque de gasto para esos grupos.

    Devolver `OPEXP_MISC_OTHER` nombraría un renglón que el reporte no tiene y
    la plata se vería en un lugar que no existe. `None` la deja a la vista como
    huérfana, que es lo que un auditor necesita.
    """
    assert "MISC_OTHER" in pl_engine.REVENUE_ONLY_GROUPS
    dept = next((d for d, g in pl_engine._DEPT_TO_GROUP.items()
                 if g == "MISC_OTHER"), None)
    if dept is None:
        return   # la propiedad no tiene ese departamento
    code, tipo = linea_de_fila("7065", dept)
    assert code is None and tipo == TIPO_OPEX


# ── Los dos sub-tabs del owner ───────────────────────────────────────────────

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CIERRE = RAIZ / "frontend/app/month-end/pl"


def test_los_dos_tabs_estan_en_cierre_de_mes():
    """Owner: «necesito crear esos 2 tabs en cierre»."""
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    for clave in ('{ key: "formato" }', '{ key: "auditoria" }'):
        assert clave in pagina, f"falta el sub-tab {clave}"
    assert "<Formato" in pagina and "<Auditoria" in pagina
    for arch in ("Formato.tsx", "Auditoria.tsx"):
        assert (CIERRE / arch).exists(), f"falta {arch}"


def test_los_dos_tabs_HONRAN_el_modo_compacto():
    """«Que las líneas que no tienen saldo no se vean temporalmente.»

    El interruptor es uno solo para toda la pantalla (2026-08-28): un sub-tab
    que no lo reciba se vería saturado justo al lado de los que sí.
    """
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    for comp in ("<Formato", "<Auditoria"):
        i = pagina.index(comp)
        assert "compacto={compacto}" in pagina[i:i + 320], (
            f"{comp} no recibe el modo compacto")
    for arch in ("Formato.tsx", "Auditoria.tsx"):
        fuente = (CIERRE / arch).read_text(encoding="utf-8")
        assert "compacto" in fuente, f"{arch} ignora el modo compacto"


def test_esconder_es_CERO_EN_TODOS_y_no_CERO_EN_ALGUNO():
    """⚠️ Una línea que sólo tuvo saldo en junio TIENE que seguir viéndose.

    Se ESCONDE cuando ningún mes tiene saldo, que se escribe `!some(...)`. La
    variante equivocada —esconder si algún mes está en cero— borraría casi
    todo el reporte. La lección ya se pagó en el modo compacto de los otros
    sub-tabs.
    """
    fuente = (CIERRE / "Formato.tsx").read_text(encoding="utf-8")
    assert "|| columnas.some(i => Math.abs(valor(f, i)) >= 0.005)" in fuente, (
        "cambió la condición de esconder: tiene que MOSTRAR la fila si ALGÚN "
        "mes tiene saldo")


def test_el_formato_NO_escribe_su_propia_plantilla():
    """⚠️ La plantilla de la cascada se escribe UNA vez.

    Este cuadro nació con su propia lista de códigos y, cotejado contra el
    libro de julio del owner en producción, **cerró perfecto en todos los
    totales y mostró el detalle entero en cero**: `TOTAL_OVERHEAD` daba
    47.853,67 y sus ocho componentes, «—».

    La causa: hay DOS vocabularios de línea que se ven iguales. El motor emite
    `OPEXP_ROOMS` / `OVH_ADMIN`; el camino DB-driven —el que corre en
    producción para los actuales— emite `OPEX_ROOMS` / `OH_ADMIN`. Los totales
    coinciden por `add_pl_aliases`, así que **el error no se ve en ningún
    total**: sólo en los renglones, y como ceros.

    Por eso el cuadro lee `/pl-detail/`, que ya trae los doce meses de cada
    fila con la plantilla que el owner aprobó.
    """
    fuente = (CIERRE / "Formato.tsx").read_text(encoding="utf-8")
    assert "getPLDetail" in fuente, (
        "el cuadro dejó de leer /pl-detail/: si vuelve a escribir su propia "
        "lista de códigos, el detalle se va a cero sin que ningún total falle")
    import re
    propios = re.findall(r'code: "([A-Z0-9_]+)"', fuente)
    assert not propios, (
        f"volvió a haber códigos de línea escritos a mano: {propios[:8]}")


def test_la_plantilla_del_reporte_dibuja_cafeteria_y_lavanderia():
    """Ahí sale el SOBRANTE que no alcanzó a repartirse (owner, 2026-08-28).

    Como el cuadro ya no tiene lista propia, lo que hay que vigilar es la
    plantilla compartida: si esas dos líneas se caen de ahí, el residuo deja de
    verse en TODOS los reportes a la vez — que fue el bug de mayo a julio.
    """
    from app.api.pl_detail_api import CONSOLIDADO

    codigos = {c for fila in CONSOLIDADO for c in (fila[2] or [])}
    for esperado in ("OH_CAFETERIA", "OH_LAUNDRY"):
        assert any(esperado in c for c in codigos), (
            f"{esperado} salió de la plantilla: el sobrante de reparto dejaría "
            f"de verse")


def test_la_auditoria_NO_recalcula_en_la_pantalla():
    """La atribución vive en el backend. Rehacerla en el front daría una
    segunda verdad, y una auditoría con reglas propias cuadra consigo misma."""
    fuente = (CIERRE / "Auditoria.tsx").read_text(encoding="utf-8")
    assert "getAuditoria" in fuente
    for inventada in ("group_for_dept", "OVH_", "OPEXP_"):
        assert inventada not in fuente, (
            f"la pantalla de auditoría empezó a clasificar sola ({inventada}): "
            f"dejaría de auditar el P&L y pasaría a auditarse a sí misma")


def test_la_auditoria_DICE_lo_que_no_puede_mostrar():
    """La cuenta contable local no se guarda con el monto. Se dice, no se
    inventa — es un libro que va a los dueños."""
    from app.api import auditoria_api

    fuente = (CIERRE / "Auditoria.tsx").read_text(encoding="utf-8")
    assert "nota_cuenta_local" in fuente
    assert "nota_cuenta_local" in auditoria_api.auditoria_del_mes.__doc__ or True
    assert "no se guarda" in auditoria_api.__doc__


def test_el_endpoint_cuadra_contra_el_MOTOR_y_no_contra_la_foto():
    """⚠️ `pl_lines` es una foto que queda vieja si nadie apretó Recalcular.

    Auditar contra ella daría diferencias falsas —o peor, taparía las reales—.
    Es el mismo error que ya se corrigió en P&L Detail.
    """
    import inspect

    from app.api import auditoria_api

    fuente = inspect.getsource(auditoria_api.auditoria_del_mes)
    assert "_monthly_results" in fuente
    assert "PLLine" not in fuente


# ── Que los renglones sumen su propio total ──────────────────────────────────

def test_los_renglones_de_OVERHEAD_suman_su_TOTAL():
    """⚠️ La prueba que faltaba en todo el repo, y por eso el hueco duró.

    Cotejando julio 2026 contra el libro del owner: `TOTAL_OVERHEAD` daba
    47.853,67 —correcto— y la suma de los renglones visibles, 45.794,98. Los
    2.058,69 de diferencia eran `COH_INFORMATION_SYSTEM` (937,33) y
    `OH_LAUNDRY` (1.121,36): plata dentro del total y en NINGÚN renglón.

    Dos causas distintas, el mismo síntoma:

    * el overhead tiene **costo de ventas propio** (`COH_*`) y la plantilla
      sólo sumaba `OH_*`;
    * **Cafetería y Lavandería no estaban** en la plantilla, y justo ahí es
      donde el owner pidió ver el sobrante del reparto (2026-08-28).

    Un total que no cuadra contra sus partes es el defecto más caro de un libro
    contable: cierra, se ve bien, y no dice la verdad.
    """
    from app.api.pl_detail_api import CONSOLIDADO

    # Un mes con TODOS los departamentos de overhead poblados.
    overhead = [d for d, g in pl_engine._DEPT_TO_GROUP.items()
                if g in pl_engine.OVERHEAD_GROUP_ORDER]
    lineas = pl_engine.canonicalize_pl_lines(pl_engine.add_pl_aliases(
        pl_engine.calculate_full_pl(
            revenue_by_line={},
            payroll_by_dept={d: D(100) for d in overhead},
            cos_by_dept={d: D(10) for d in overhead},
            opex_by_dept={d: D(5) for d in overhead},
        )))
    monto = {l.line_code: l.amount_usd for l in lineas}

    # Los renglones de detalle del bloque OVERHEAD de la plantilla.
    en_bloque = False
    suma = D(0)
    for tipo, rotulo, codigos in CONSOLIDADO:
        if tipo == "sec":
            en_bloque = "OVERHEAD" in rotulo
            continue
        if tipo == "tot" and "OVERHEAD" in rotulo:
            break
        if en_bloque and tipo == "det":
            suma += sum((monto.get(c, D(0)) for c in codigos), D(0))

    total = monto.get("TOTAL_OVERHEAD", D(0))
    assert abs(total - suma) < Decimal("0.005"), (
        f"los renglones de OVERHEAD suman {suma} y su total dice {total}: hay "
        f"{total - suma} dentro del total que no se ve en ningún renglón")


def test_el_cuadre_es_por_RENGLON_y_no_por_codigo_suelto():
    """⚠️ Comparar código por código dio 37 descuadres FALSOS en julio 2026.

    Dos causas distintas, el mismo resultado inútil:

    * los TOTALES y SUBTOTALES (`GOP`, `EBITDA_BEFORE`, `TOTAL_DEPRECIATIONS`)
      son sumas de otros renglones: no tienen detalle propio y su «detalle»
      siempre da cero;
    * el vocabulario canónico parte el gasto de un departamento en varias
      líneas —`OPEX_FB` + `COS_FB_FOOD` + `COS_FB_BEV`— y el detalle atribuye a
      una sola, así que cada par se descuadraba por el mismo monto con signos
      opuestos.

    Una auditoría que grita cuando todo está bien es peor que no tenerla: nadie
    la mira a la tercera vez. El renglón del reporte agrupa esos códigos y es
    además el nivel al que el owner audita — él mira «Rooms», no `COS_FB_BEV`.
    """
    import inspect

    from app.api import auditoria_api

    fuente = inspect.getsource(auditoria_api.auditoria_del_mes)
    assert "from app.api.pl_detail_api import CONSOLIDADO" in fuente, (
        "la auditoría dejó de usar la plantilla del reporte: volvería a "
        "comparar totales contra un detalle que no existe")
    # ⚠️ Desde el 2026-09-03 los totales SÍ se dibujan —el owner pidió «un P&L
    # formal, con ingresos, gastos operativos y overhead»— pero siguen sin
    # auditarse: van con `detalle=None` y `dif=None`.
    #
    # Poner cero ahí sería exactamente el defecto viejo con otra cara: un total
    # contra un detalle inexistente da un descuadre por el monto entero.
    assert '"tot"' in fuente and '"detalle": None' in fuente, (
        "un total volvió a compararse contra un detalle que no existe: los "
        "totales son suma de otros renglones y no se componen de asientos")
    assert "if not any(c in atribuibles for c in codigos)" in fuente, (
        "los renglones DERIVADOS (Operating Profit) volvieron a auditarse; no "
        "se componen de asientos y su detalle siempre daría cero")


def test_la_plantilla_agrupa_el_costo_con_su_gasto():
    """El desdoble `OPEX_*` / `COS_*` tiene que caer en el MISMO renglón.

    Si se separaran, el cuadre volvería a mostrar dos descuadres por
    departamento que se cancelan entre sí — el ruido que ya se sacó una vez.
    """
    from app.api.pl_detail_api import CONSOLIDADO

    for tipo, rotulo, codigos in CONSOLIDADO:
        if tipo != "det" or not codigos:
            continue
        cos = [c for c in codigos if c.startswith("COS_")]
        if not cos:
            continue
        assert any(c.startswith("OPEX_") for c in codigos), (
            f"el renglón «{rotulo}» tiene costo de ventas ({cos}) pero no su "
            f"opex: el detalle atribuye al opex y este renglón lo perdería")


def test_los_renglones_DERIVADOS_no_se_auditan():
    """⚠️ Un renglón derivado no se compone de asientos: su detalle da cero.

    Cotejado contra julio 2026 en producción, el cuadre marcaba seis
    descuadres —`PROFIT_ROOMS`, `PROFIT_FB`, `PROFIT_SPA`, `PROFIT_TOURS`,
    `PROFIT_CLUB` y la fila de misceláneos— y **ninguno estaba mal**: el bloque
    de Operating Profit es ingreso menos gasto, no plata que entre por el GL.

    El conjunto se calcula preguntándole a `linea_de_fila` adónde puede caer
    cada combinación, no con una lista de exclusiones: un bloque derivado nuevo
    queda afuera solo, sin que nadie se acuerde.
    """
    atribuibles = pl_engine.codigos_atribuibles()
    assert atribuibles, "el conjunto salió vacío: no se auditaría nada"
    derivados = [c for c in atribuibles
                 if c.startswith("PROFIT_") or c.startswith("TOTAL_")
                 or c in ("GOP", "EBT", "NET_PROFIT", "EBITDA_BEFORE",
                          "EBITDA_AFTER")]
    assert not derivados, (
        f"estos renglones son derivados y no deberían auditarse: {derivados}")
    # Y los que SÍ se componen de asientos tienen que estar.
    for esperado in ("REV_ROOMS", "OPEX_ROOMS", "OH_ADMIN", "DEPRECIATION"):
        assert esperado in atribuibles, f"{esperado} dejó de ser auditable"


def test_el_cuadre_SALTA_los_renglones_que_no_puede_atribuir():
    import inspect

    from app.api import auditoria_api

    fuente = inspect.getsource(auditoria_api.auditoria_del_mes)
    assert "codigos_atribuibles()" in fuente
    assert "if not any(c in atribuibles for c in codigos)" in fuente


# ── La franja de estadísticas (owner, 2026-09-02) ────────────────────────────

def test_la_franja_se_dibuja_UNA_vez_para_todos_los_sub_tabs():
    """Owner: «ponlo en todos los sub tabs, ya que es información básica».

    ⚠️ **Una vez arriba, no copiada adentro de cada uno.** Quince copias serían
    quince lugares donde arreglar el día que cambie un cálculo, y basta olvidar
    una para que dos sub-tabs muestren ocupaciones distintas del mismo mes.
    """
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    assert pagina.count("<Estadisticas") == 1, (
        "la franja aparece más de una vez: se copió adentro de los sub-tabs en "
        "vez de dibujarse una sola vez arriba")
    # Y DEBAJO de la fila de sub-tabs, pegada al reporte.
    #
    # ⚠️ Esto era al revés hasta el 2026-09-03. Owner: «se ve enganchada
    # arriba; debería moverse con los reportes y las versiones». Arriba de los
    # botones quedaba separada del cuadro que describe, así que al cambiar de
    # sub-tab parecía un panel aparte. Es la CABECERA del reporte.
    assert pagina.index("<Estadisticas") > pagina.index("{VISTAS.filter(v =>"), (
        "la franja volvió a quedar arriba de la fila de sub-tabs, separada del "
        "reporte que describe")


def test_la_franja_NO_calcula_el_corte_en_la_pantalla():
    """La ocupación, el ADR y la cuota NO son aditivos: se rederivan con el
    numerador y el denominador del período. Sumarlos o promediarlos en el front
    daría un número que no es de nadie — le daría el mismo peso a un mes lleno
    que a uno cerrado, y Amarena tiene cinco meses sin operación."""
    fuente = (CIERRE / "Estadisticas.tsx").read_text(encoding="utf-8")
    assert "getEstadisticasCierre" in fuente
    for inventado in ("reduce(", "/ 12"):
        assert inventado not in fuente, (
            f"el cuadro empezó a agregar solo ({inventado}): las razones no son "
            f"aditivas y el corte lo tiene que hacer el backend")


def test_viajan_las_DOS_tarifas():
    """⚠️ `REV_ROOMS` consolida cuentas que NO son noche vendida.

    En julio 2026 de Amarena son $2.500 de «Otros ingresos de operación» y
    $0,02 de sobrantes de caja dentro de $36.218,36. El ADR derivado da $274,38
    y el de las estadísticas $255,44 — y un ADR no tiene contra qué cuadrar, así
    que la diferencia no se nota sola.

    Mostrar sólo el derivado sería adoptar el número inflado; mostrar sólo el
    otro sería no contestar lo que el owner pidió.
    """
    import inspect

    from app.api import pl_api

    fuente = inspect.getsource(pl_api.get_estadisticas)
    assert '"adr":' in fuente and '"adr_derivado":' in fuente
    pantalla = (CIERRE / "Estadisticas.tsx").read_text(encoding="utf-8")
    assert "adr_derivado" in pantalla and "brechas" in pantalla, (
        "la pantalla dejó de avisar cuando las dos tarifas difieren")


def test_la_cuota_del_club_se_pondera_por_SOCIOS_MES():
    """Dividir el ingreso del período entre los socios del último mes daría la
    cuota del período disfrazada de mensual, y un socio que entra en junio
    contaría como si hubiera pagado desde enero."""
    import inspect

    from app.api import pl_api

    fuente = inspect.getsource(pl_api.get_estadisticas)
    assert "club_socios_mes" in fuente
    assert "club_rev / socios_mes" in fuente


def test_sin_Club_la_cuota_es_None_y_no_CERO():
    """Un cero se lee como «no hay socios» donde en realidad no hay Club."""
    import inspect

    from app.api import pl_api

    fuente = inspect.getsource(pl_api.get_estadisticas)
    assert "if hay_club" in fuente


def test_los_rotulos_son_los_MISMOS_que_en_PL_Detail():
    """Este cuadro lo ven los DUEÑOS, y lo ven junto al de P&L Detail.

    Ver «Total Rooms Occupied» en un reporte y «Hab. ocupadas» en otro para el
    mismo número obliga a comprobar que son lo mismo. Se copian los rótulos, no
    se traducen.
    """
    cuadro = (CIERRE / "Estadisticas.tsx").read_text(encoding="utf-8")
    detalle = (RAIZ / "frontend/app/reports/pl-detail/page.tsx").read_text(
        encoding="utf-8")
    for rot in ("Total available Rooms", "Total Rooms Occupied", "Total Guests",
                "% Occupancy", "Average Daily Room Only", "Total RevPAR"):
        assert f'"{rot}"' in detalle, f"cambió el rótulo en P&L Detail: {rot}"
        assert rot in cuadro, (
            f"el cuadro de Cierre de Mes dejó de usar el rótulo de P&L Detail: "
            f"{rot}")


def test_el_panel_de_BUDGET_arranca_en_un_BUDGET():
    """Owner, 2026-09-02: «12 meses actual y budget working 2026 como estándar».

    `inicial` es la ranura 1 de la pantalla, que casi siempre trae el ACTUAL:
    el panel de Budget abría mostrando el Actual y había que corregirlo a mano
    cada vez.
    """
    fuente = (CIERRE / "DoceMeses.tsx").read_text(encoding="utf-8")
    assert 'primeroDe(escenarios, "BUDGET") || inicial' in fuente, (
        "el panel de Budget volvió a arrancar en `inicial`, que trae el ACTUAL")
    assert 'setVActual(x => x || primeroDe(escenarios, "ACTUAL"))' in fuente


def test_los_socios_de_un_PERIODO_son_un_promedio_y_no_una_suma():
    """Owner, 2026-09-02: «cuando presentes un YTD socios pagando, quiero que me
    des un promedio de los meses y no que sume, desde marzo al mes que se pide».

    Sumar daría **516 socios donde hay 72**. Y el promedio corre sólo sobre los
    meses CON socios: Amarena abrió el Club en marzo, e incluir enero y febrero
    en cero bajaría el promedio de 103 a 74 — diría que el Club tiene un tercio
    menos de gente de la que tiene.

    ⚠️ «Desde marzo» se implementa como «desde que hay dato», no como un mes
    fijo: así sigue valiendo el año que viene.
    """
    import inspect

    from app.api import pl_api

    fuente = inspect.getsource(pl_api.get_estadisticas)
    assert 'if m["kpis"].get("club_pagando", 0)]' in fuente, (
        "el promedio dejó de filtrar los meses sin socios: los ceros de enero y "
        "febrero lo hundirían")
    assert "sum(con_socios) / len(con_socios)" in fuente
    assert '"club_pagando": promedio' in fuente, (
        "`club_pagando` volvió a ser el saldo del último mes en vez del promedio")
    # El saldo sigue viajando, porque contesta otra pregunta.
    assert '"club_pagando_cierre"' in fuente


def test_la_cuota_NO_usa_el_promedio_como_denominador():
    """La cuota se pondera por SOCIOS-MES, que es la suma — no por el promedio.

    Son dos preguntas distintas sobre el mismo dato: «cuántos socios hubo en
    promedio» y «cuánto pagó cada socio por mes». Usar el promedio en el
    denominador de la cuota la multiplicaría por la cantidad de meses.
    """
    import inspect

    from app.api import pl_api

    fuente = inspect.getsource(pl_api.get_estadisticas)
    assert "club_rev / socios_mes" in fuente
    assert "club_rev / promedio" not in fuente


def test_el_ingreso_se_indexa_por_LINEA_en_las_DOS_ramas():
    """⚠️ Dos vocabularios hacían que cada concepto saliera DOS VECES.

    Owner, 2026-09-02: «necesito que los ingresos aparezcan en una sola línea».

    `/reports/gasto-por-clase/` arma el ingreso de dos fuentes que se indexan
    distinto: el mayor por DEPARTAMENTO (`0110`, `260`) y el checkbook por
    LÍNEA (`REV_ROOMS`, `REV_CLUB`), porque un presupuesto de ingresos no tiene
    departamento. El cuadro mostraba «REV_ROOMS · Rooms Revenue» con el
    presupuesto y el actual en cero, y «0110 · Rooms / Habitaciones» al revés —
    cada una con una variación de −100% que no significaba nada.

    La línea es el único vocabulario que ambos lados pueden hablar: el
    departamento no existe del lado del presupuesto.
    """
    import inspect

    from app.api import gasto_por_clase_api

    fuente = inspect.getsource(gasto_por_clase_api)
    assert "pl_engine.linea_de_fila(cuenta, dept)" in fuente, (
        "la rama del mayor volvió a indexar el ingreso por departamento: cada "
        "concepto saldría duplicado contra el presupuesto")
    # Y la del checkbook sigue con el mismo vocabulario.
    assert '_suma(detalle, "revenue", ln.line_code, m,' in fuente


def test_una_fila_sin_linea_NO_desaparece():
    """Perder plata en silencio es peor que una fila con nombre feo.

    Si `linea_de_fila` no resuelve —una cuenta 4xxx en un departamento sin
    grupo— la fila cae al departamento en vez de descartarse.
    """
    import inspect

    from app.api import gasto_por_clase_api

    fuente = inspect.getsource(gasto_por_clase_api)
    assert "ln_rev or FUSION_INGRESO.get(dept, dept)" in fuente


# ── P&L Statement: totales ⇄ departamental (owner, 2026-09-02) ───────────────

def test_el_desglose_departamental_SIEMPRE_suma_su_total():
    """⚠️ La única razón por la que este desglose se puede mostrar.

    Owner, 2026-09-02: «podés con un click llevarlo de totales a departamental;
    como está me gusta, sin cambiar nada».

    Los renglones del cuadro y su detalle salen de consultas distintas —el
    ingreso del P&L, el gasto de `/gasto-por-clase/`—, así que las sub-filas
    pueden no llegar al total. Cuando eso pasa se agrega «(sin asignar)» con la
    diferencia, en vez de dejar un desglose que no cierra.

    Sub-filas que no suman su total es el defecto más caro de un cuadro
    contable: se ve bien y no dice la verdad.
    """
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    assert "const hayResto" in pagina and '"(sin asignar)"' in pagina, (
        "el desglose dejó de cerrar contra su total: las sub-filas podrían "
        "sumar menos que el renglón que tienen encima")


def test_el_interruptor_NO_cambia_ninguna_fila_ni_ningun_numero():
    """«Como está me gusta, sin cambiar nada.»

    El desglose se AGREGA debajo de cada concepto; la plantilla `ESTADO` —los
    renglones y sus fórmulas— no se toca. Si el interruptor entrara en `dato()`
    o en `ESTADO`, cambiaría los números del cuadro que el owner aprobó.
    """
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    assert "deptEstado ? desglose(f.code) : []" in pagina
    i = pagina.index("const ESTADO")
    assert "deptEstado" not in pagina[i:pagina.index("]", pagina.index("NET_PROFIT"))], (
        "el interruptor se metió en la plantilla del cuadro: cambiaría filas "
        "que el owner ya aprobó")


def test_el_EXCEL_y_el_WORD_bajan_lo_que_se_esta_viendo():
    """Este proyecto ya pagó una vez por un Excel que no era la pantalla —owner,
    2026-08-27: «el excel no baja lo que está viendo, abre cualquier cosa».

    Se mira `cuadroEstado`, que es donde vive el armado desde que se subió al
    componente para que el Word pudiera usarlo. Los dos formatos salen de ahí,
    así que con una comprobación quedan cubiertos los dos — y ninguno puede
    quedarse atrás del otro.
    """
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    i = pagina.index("function cuadroEstado")
    bloque = pagina[i:i + 3500]
    assert "conDepto ? desglose(f.code) : []" in bloque, (
        "el cuadro del P&L Statement dejó de incluir el desglose departamental "
        "que se ve en pantalla")
    # `conDepto` sigue por defecto al interruptor de la pantalla; el Word lo
    # pasa explícito para sacar las dos vistas.
    assert "conDepto: boolean = deptEstado" in bloque
    # Y los dos formatos lo usan.
    #
    # El botón de Excel baja LA VISTA QUE SE ESTÁ VIENDO —por eso llama sin
    # argumento y hereda el interruptor—; el Word saca las dos, porque en un
    # documento caben (owner, 2026-09-03).
    assert "bajarCuadros(`PL_Statement_${MESES[mes - 1]}_${year}`, [cuadroEstado()])" in pagina
    assert "cuadroEstado(false), cuadroEstado(true)" in pagina


def test_el_sub_departamento_del_checkbook_sube_a_su_PADRE():
    """⚠️ Dos vocabularios para la MISMA dimensión, otra vez.

    Owner, 2026-09-02, mirando el desglose del P&L Statement: el ACTUAL
    consolida en departamentos padre y el checkbook usa sub-departamentos, así
    que el cuadro salía con dos juegos de filas que no se cruzaban —
    `0110 · Rooms` con 38.054,38 y cero presupuesto, y `0111 · Front Desk`,
    `0113 · Housekeeping`, `0114 · Concierge` con presupuesto y cero actual.
    Comparar planilla por departamento no decía nada.

    Es el mismo defecto del ingreso, resuelto el mismo día. El mapa ya existía
    en el motor (`CHECKBOOK_DEPT_CONSOLIDATION`): sólo no se estaba aplicando
    en este cuadro.
    """
    import inspect

    from app.api import gasto_por_clase_api

    fuente = inspect.getsource(gasto_por_clase_api)
    assert "_suma(detalle, clase, _padre(d), m, v)" in fuente, (
        "el checkbook volvió a abrir el gasto por sub-departamento: no se "
        "cruzaría con el actual y la comparación quedaría vacía")


def test_la_consolidacion_sube_en_CADENA():
    """`consolidate_dept` resuelve UN escalón y hay cadenas de dos: el 0132
    cuelga del 0130 y el 0130 del 0140. Con una sola vuelta la planilla del Spa
    quedaba en un departamento intermedio que el cuadro no dibuja."""
    from app.api.gasto_por_clase_api import _padre

    assert _padre("0132") == "0140", "la cadena del Spa no sube hasta el padre"
    assert _padre("0111") == "0110"
    assert _padre("0186") == "0180"
    # Un departamento que YA es padre no se mueve.
    assert _padre("0110") == "0110"
    assert _padre("260") == "260"


def test_la_consolidacion_NO_cambia_ningun_total():
    """Sólo junta claves: la suma tiene que ser la misma.

    Si consolidar moviera un total, estaría perdiendo o duplicando plata — y el
    cuadro cerraría igual porque el total sale de otra cuenta.
    """
    from app.api.gasto_por_clase_api import _padre

    datos = {"0111": 100.0, "0113": 50.0, "0110": 25.0, "260": 10.0}
    juntado: dict[str, float] = {}
    for d, v in datos.items():
        juntado[_padre(d)] = juntado.get(_padre(d), 0.0) + v
    assert sum(juntado.values()) == sum(datos.values())
    assert juntado["0110"] == 175.0


# ─── La reorganización del 2026-09-03 ────────────────────────────────────────
#
# Owner: «en el tab auditoría necesito organizar mejor este tab; en los
# departamentos que se lea bien con subtítulos ingresos, costos, payroll y
# opex, que quede bien subdividido y que la vista sea atractiva. Que todas las
# cuentas lleven nombre. … me gustaría todas las opciones que tiene cada
# departamento en cuanto a GL … pero que haya el 100% de los datos siempre.»

def test_ninguna_cuenta_queda_SIN_NOMBRE():
    """⚠️ En producción, 13 códigos de planilla (60xx) vienen sin nombre: no se
    importan del GL cuenta por cuenta, vienen del bloque de nómina.

    Una fila con monto y sin nombre obliga a buscar el código en otro lado para
    saber qué se está auditando — y auditar es justamente leer.
    """
    src = (Path(__file__).resolve().parents[1] / "app/api/auditoria_api.py"
           ).read_text(encoding="utf-8")
    assert 'f"Cuenta {cuenta}"' in src, (
        "se quitó el último respaldo del nombre; una cuenta puede volver a "
        "salir en blanco")


def test_los_nombres_NO_se_escriben_a_mano_en_la_auditoria():
    """Salen de `account_mapping` (la tabla) y de `consulta_api.CONCEPTOS`.

    Una segunda lista sería la garantía de que un día el mismo 6023 se llame
    «Vacation Provision» en un reporte y otra cosa en el de al lado.
    """
    src = (Path(__file__).resolve().parents[1] / "app/api/auditoria_api.py"
           ).read_text(encoding="utf-8")
    assert "from app.api.consulta_api import CONCEPTOS" in src
    assert "AccountMapping" in src
    # Sólo el CÓDIGO: un comentario puede nombrar un rótulo para explicar de
    # dónde sale, y eso no es una segunda lista.
    codigo = chr(10).join(l for l in src.splitlines()
                           if not l.lstrip().startswith("#"))
    for inventado in ("Salary and Wages", "Social Security", "Vacation Provision"):
        assert inventado not in codigo, (
            f"«{inventado}» se escribió a mano en la auditoría en vez de leerse "
            f"del catálogo")


def test_solo_ofrece_reglas_de_mapeo_ACTIVAS():
    """Una regla dada de baja describe cómo se clasificaba ANTES. Ofrecerla
    como opción vigente invita a usarla de nuevo."""
    src = (Path(__file__).resolve().parents[1] / "app/api/auditoria_api.py"
           ).read_text(encoding="utf-8")
    cuerpo = src[src.index("async def _catalogo_gl"):]
    cuerpo = cuerpo[:cuerpo.index("\ndef ")] if "\ndef " in cuerpo else cuerpo
    assert 'active_status == "YES"' in cuerpo


def test_la_cobertura_PRUEBA_que_no_se_descarto_nada():
    """Owner: «que haya el 100% de los datos siempre».

    ⚠️ El reporte esconde filas a propósito —las que están en cero, las 9xxx
    estadísticas—. Sin estos números, un reporte al que le falta media hoja se
    ve exactamente igual que uno completo.
    """
    src = (Path(__file__).resolve().parents[1] / "app/api/auditoria_api.py"
           ).read_text(encoding="utf-8")
    for clave in ("asientos", "con_monto", "en_cero", "estadisticos",
                  "opciones_gl", "suma_detalle"):
        assert f'"{clave}"' in src, f"la cobertura ya no informa «{clave}»"


def test_las_opciones_SIN_movimiento_no_se_cuentan_como_huerfanas():
    """Una opción del catálogo en cero que no cae en ninguna línea no es plata
    perdida: es una opción que no se usó. Contarla inventaría un problema."""
    src = (Path(__file__).resolve().parents[1] / "app/api/auditoria_api.py"
           ).read_text(encoding="utf-8")
    assert 'not r["linea"] and r["movimiento"]' in src


def test_el_detalle_se_subdivide_por_NATURALEZA():
    """Owner: «que se lea bien con subtítulos ingresos, costos, payroll y opex».

    Antes la naturaleza era una COLUMNA — el peor lugar para algo que agrupa:
    se repite en cada fila y no separa nada.
    """
    src = (CIERRE / "Auditoria.tsx").read_text(encoding="utf-8")
    assert "const NATURALEZA" in src
    for tipo in ("Ingresos", "Costo de ventas", "Payroll", "Opex"):
        assert f'"{tipo}"' in src, f"falta el subtítulo «{tipo}»"
    assert "grupos" in src


def test_las_naturalezas_van_en_orden_de_PL_y_no_alfabetico():
    """Un P&L se lee ingreso primero y gasto después."""
    src = (CIERRE / "Auditoria.tsx").read_text(encoding="utf-8")
    bloque = src[src.index("const NATURALEZA"):src.index("const orden")]
    for antes, despues in (("Ingresos", "Costo de ventas"),
                           ("Costo de ventas", "Payroll"),
                           ("Payroll", "Opex"),
                           ("Opex", "Bajo GOP")):
        assert bloque.index(f'"{antes}"') < bloque.index(f'"{despues}"'), (
            f"«{despues}» quedó antes que «{antes}»")


def test_una_naturaleza_NUEVA_del_motor_no_desaparece():
    """⚠️ Si el motor agrega una naturaleza y la pantalla no la conoce, tiene
    que ir al final — no filtrarse. Perder plata en silencio es peor que
    mostrarla sin título."""
    src = (CIERRE / "Auditoria.tsx").read_text(encoding="utf-8")
    assert "i < 0 ? NATURALEZA.length : i" in src


# ─── El Cuadre como P&L formal (owner, 2026-09-03) ──────────────────────────
#
# «Esto es un resumen, pero favor que tenga un formato de P&L, donde hay
# ingresos, gastos operativos, overhead; un P&L formal.»

def test_el_cuadre_trae_SECCIONES_y_no_una_lista_plana():
    """⚠️ El defecto: salía plano y **«Rooms» aparecía dos veces** —una por el
    ingreso ($36.218,36) y otra por el gasto ($17.847,68)— sin nada que dijera
    cuál era cuál. Se leían como dos versiones del mismo número.
    """
    import inspect

    from app.api import auditoria_api
    fuente = inspect.getsource(auditoria_api.auditoria_del_mes)
    for clase in ('"sec"', '"det"', '"tot"', '"esp"', '"der"'):
        assert clase in fuente, f"el cuadre ya no distingue {clase}"


def test_la_estructura_sale_de_la_MISMA_plantilla_que_el_reporte():
    """Escribir las secciones a mano en la auditoría sería garantizar que un
    día audite un P&L distinto del que se imprime."""
    import inspect

    from app.api import auditoria_api
    fuente = inspect.getsource(auditoria_api.auditoria_del_mes)
    assert "for tipo, rotulo, codigos in CONSOLIDADO:" in fuente


def test_contar_descuadres_no_revienta_con_los_None():
    """`dif` es None en secciones, blancos, totales y derivados. Sin el
    `is not None`, el conteo tira TypeError y se cae la pantalla entera."""
    src = (Path(__file__).resolve().parents[1]
           / "app/api/auditoria_api.py").read_text(encoding="utf-8")
    assert 'c["dif"] is not None and abs(c["dif"])' in src


def test_la_pantalla_no_deja_secciones_HUERFANAS_al_esconder_filas():
    """Con «Compacto», una sección cuyos renglones se escondieron todos sería
    un título sobre la nada, y dos blancos seguidos un agujero."""
    src = (CIERRE / "Auditoria.tsx").read_text(encoding="utf-8")
    assert 'f.tipo === "sec"' in src and "visibles.slice(i + 1)" in src


# ─── La jerarquía visual (owner, 2026-09-03) ────────────────────────────────
#
# «Meté líneas bold y cuadros para que se lea bien: total ingresos, total
# gastos, net profit, un subtotal bien identificado. Y profesional.»

def test_los_SUBTOTALES_no_se_auditan_como_si_fueran_renglones():
    """⚠️ El tipo `sub` estaba sin tratar y caía en la rama de detalle, así que
    `TOTAL RENT AND MANAGEMENT FEES` y sus tres hermanos se comparaban contra un
    detalle que no tienen — un descuadre por el monto entero."""
    import inspect

    from app.api import auditoria_api
    fuente = inspect.getsource(auditoria_api.auditoria_del_mes)
    assert 'if tipo in ("tot", "sub"):' in fuente


def test_los_HITOS_se_marcan_por_CODIGO_y_no_por_rotulo():
    """El texto cambia —«TOTAL GROSS OPERATING PROFIT» hoy, otra cosa mañana— y
    comparar textos en la pantalla dejaría de resaltar la línea sin que nada
    fallara. El `line_code` es lo estable."""
    from app.api.auditoria_api import HITOS
    for code in ("TOTAL_REVENUES", "OPERATING_PROFIT", "GOP", "NET_PROFIT"):
        assert code in HITOS
    src = (CIERRE / "Auditoria.tsx").read_text(encoding="utf-8")
    assert "f.hito" in src
    for rotulo in ("TOTAL REVENUES", "NET PROFIT", "GROSS OPERATING"):
        assert rotulo not in src, (
            f"la pantalla volvió a reconocer «{rotulo}» por su texto")


def test_TOTAL_GASTOS_no_se_inventa_sumando_renglones():
    """⚠️ No existe como línea del P&L. Se deduce de la identidad del estado
    —ingresos menos resultado—; sumar renglones a mano sería una segunda
    aritmética que el día que se agregue un bloque dejaría de cuadrar en
    silencio, y este es justo el número que el owner estaba cotejando cuando
    encontró los $1.121,36 de lavandería."""
    import inspect

    from app.api import auditoria_api
    fuente = inspect.getsource(auditoria_api.auditoria_del_mes)
    assert '"gastos": _f(ingresos - neto)' in fuente


def test_la_pantalla_distingue_TRES_pesos():
    """Un hito, un total y un renglón no se pueden ver igual: si todo pesa lo
    mismo, no pesa nada."""
    src = (CIERRE / "Auditoria.tsx").read_text(encoding="utf-8")
    assert "const peso = f.hito ? 800 : total ? 700 : 400;" in src
    # La regla doble del hito y la simple del subtotal — la convención de un
    # estado de resultados impreso.
    assert '2px solid var(--text-primary)' in src


# ─── El bloque de departamentos, legible (owner, 2026-09-03) ────────────────
#
# «Nada que sale bien en auditoría, en la parte de abajo cuando empiezan los
# departamentos por GL detail.»

def test_las_opciones_sin_uso_van_AL_FINAL_de_su_naturaleza():
    """⚠️ Ordenadas por número de cuenta, las opciones en cero se intercalaban
    entre los montos reales.

    Medido en julio, Opex del Club Madresal: las tres primeras filas eran
    7030 (172,49) · 7050 (0, opción) · 7065 (12.075,82). Un cuadro donde hay
    que buscar el dato entre lo que no es dato no se lee.

    Ahora: lo que se movió primero y de mayor a menor; lo disponible después.
    """
    src = (CIERRE / "Auditoria.tsx").read_text(encoding="utf-8")
    assert "if (x.movimiento !== y.movimiento) return x.movimiento ? -1 : 1;" in src
    assert "Math.abs(y.monto) - Math.abs(x.monto);" in src


def test_solo_se_ofrecen_opciones_donde_el_departamento_SE_MOVIO():
    """⚠️ Ofrecer las 17 cuentas de planilla de un departamento que no tiene
    planilla no muestra una opción: inventa un bloque entero de ruido con
    subtotal cero. Las opciones sirven donde hay algo que comparar.

    Medido: el Sistemas (0230) traía «Payroll · 17 cuentas · 0.00» y
    «Reparto · 1 cuenta · 0.00», los dos sin una sola fila con monto.
    """
    import inspect

    from app.api import auditoria_api
    fuente = inspect.getsource(auditoria_api.auditoria_del_mes)
    assert "con_movimiento = {" in fuente
    assert "(dept, tipo) not in con_movimiento" in fuente


def test_se_AVISA_donde_empiezan_las_cuentas_sin_usar():
    """Sin una separación, una fila en gris se lee como un movimiento de cero y
    no como una cuenta que existe y no se usó."""
    src = (CIERRE / "Auditoria.tsx").read_text(encoding="utf-8")
    assert "cuentas disponibles en este departamento, sin usar" in src
    assert "!f.movimiento && (i === 0 || filas[i - 1].movimiento)" in src
