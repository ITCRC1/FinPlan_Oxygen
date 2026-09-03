# -*- coding: utf-8 -*-
"""El Word trae TODAS las vistas activas, en el orden de la pantalla.

Owner, 2026-09-03: *«asegurate que todas las vistas estén en el Word»*, *«en el
mismo orden»*, *«pero sólo las vistas activas: las que están escondidas no se
necesitan»*.

Y antes, el 2026-09-02: *«¿por qué el Word baja unos pocos tabs y no todos los
que se ven disponibles?»* — la versión anterior armaba los capítulos en una
secuencia escrita a mano y sólo cubría nueve de los diecisiete sub-tabs.

⚠️ Con una secuencia a mano, cada sub-tab nuevo hay que acordarse de agregarlo,
y **olvidarse no falla**: el capítulo simplemente no sale. Por eso ahora es un
registro que se recorre con `VISTAS`, y por eso existe esta prueba.
"""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[2] / "frontend"
PAGINA = FRONT / "app/month-end/pl/page.tsx"

#: Sub-tabs que a propósito NO tienen capítulo, con el motivo.
SIN_CAPITULO = {
    # Es una pantalla de CONSULTA: lo que muestra depende de los filtros que se
    # elijan en el momento y de un «agrupar por» que cambia hasta las columnas.
    # Un capítulo fijo tendría que inventar una consulta.
    "consulta",
}


def _fuente() -> str:
    return PAGINA.read_text(encoding="utf-8")


def _vistas() -> list[str]:
    src = _fuente()
    bloque = src[src.index("const VISTAS = ["):src.index("] as const;")]
    return re.findall(r'\{\s*key:\s*"([a-z0-9]+)"', bloque)


def _con_capitulo() -> set[str]:
    src = _fuente()
    i = src.index("const CAPITULOS:")
    bloque = src[i:src.index("async function resumen12Cuadros")]
    return set(re.findall(r"^    ([a-z0-9]+): async \(\)", bloque, re.M))


def test_TODA_vista_tiene_capitulo():
    faltan = set(_vistas()) - _con_capitulo() - SIN_CAPITULO
    assert not faltan, (
        f"estos sub-tabs no salen en el Word: {sorted(faltan)}. Agregá su "
        f"capítulo en `CAPITULOS`, o ponelo en `SIN_CAPITULO` con el motivo")


def test_el_que_NO_tiene_capitulo_lo_dice_y_por_que():
    """Un `return []` sin explicación es indistinguible de un olvido."""
    src = _fuente()
    for clave in SIN_CAPITULO:
        i = src.index(f"    {clave}: async ()")
        cuerpo = src[i:i + 900]
        assert "no es un olvido" in cuerpo, (
            f"«{clave}» devuelve vacío sin decir por qué")


def test_el_orden_del_documento_es_el_de_la_PANTALLA():
    """No un orden propio: el documento se lee en el mismo orden en que se miró
    la pantalla."""
    src = _fuente()
    cuerpo = src[src.index("async function bajarWord()"):]
    assert "for (const clave of activos)" in cuerpo
    assert "VISTAS.map(v => v.key).filter(k => !subOcultos.includes(k))" in cuerpo


def test_solo_las_vistas_ACTIVAS():
    """Owner: «las que están escondidas no se necesitan en el Word».

    ⚠️ Y se resuelve con `subOcultos` —lo que la pantalla YA usa para dibujar—
    y no leyendo `tab_enablement` otra vez. Una segunda lectura de la misma
    decisión es una segunda oportunidad de que difieran."""
    src = _fuente()
    cuerpo = src[src.index("async function bajarWord()"):]
    assert "subOcultos.includes(k)" in cuerpo
    assert "tab_enablement" not in cuerpo


def test_el_PL_Statement_sale_en_sus_DOS_vistas():
    """Owner: «el P&L Statement tiene 2 vistas en el mismo archivo; quiero que
    despliegues una de totales y otra de vista departamental».

    En la pantalla el botón muestra una por vez; en el documento caben las dos,
    y son dos lecturas distintas del mismo mes — el total dice cuánto y el
    departamental dice de dónde."""
    src = _fuente()
    assert "[cuadroEstado(false), cuadroEstado(true)]" in src
    # Y el título distingue cuál es cuál: dos capítulos idénticos de nombre
    # serían peor que uno solo.
    assert '" — Departamental" : " — Totales"' in src


def test_un_capitulo_que_falla_no_se_lleva_el_DOCUMENTO():
    """Con doce capítulos, que uno reviente y no salga nada sería perder el
    cierre entero por un cuadro."""
    src = _fuente()
    cuerpo = src[src.index("for (const clave of activos)"):]
    assert "} catch (e) {" in cuerpo[:900]
    # ⚠️ Y SE DICE cuál se cayó. Un capítulo que desaparece en silencio es un
    # dato que falta sin aviso — que es cómo el owner terminó con un documento
    # sin el P&L Statement y sin saberlo.
    assert "afuera.push" in cuerpo[:1200]


def test_un_cuadro_SIN_DATOS_no_entra_al_documento():
    """Owner, 2026-09-03: «hay cuadros que no tienen datos».

    ⚠️ Un cuadro en cero no se lee como «faltó el dato»: se lee como «el mes no
    tuvo movimiento», que es una afirmación. En el Word de julio los cinco
    cuadros por departamento salieron con un TOTAL de 0,00.
    """
    src = _fuente()
    assert "function tieneDatos(c: Cuadro): boolean" in src
    cuerpo = src[src.index("for (const clave of activos)"):]
    assert "if (tieneDatos(c)) cuadros.push(c);" in cuerpo


def test_el_Word_no_se_baja_con_la_pantalla_A_MEDIO_CARGAR():
    """La causa de fondo de aquel documento a medias.

    ⚠️ La mitad de los capítulos leen el ESTADO de la pantalla (`datos`,
    `gastos`) y la otra mitad pide lo suyo con `await`. Generado antes de que
    termine la carga, los que piden esperan y salen bien, y los que leen el
    estado salen en cero: un documento incompleto que se ve completo.
    """
    src = _fuente()
    cuerpo = src[src.index("async function bajarWord()"):]
    assert "if (!datos.length || !gastos.length)" in cuerpo[:1500]


# ─── Que cada capítulo baje el sub-tab COMPLETO (owner, 2026-09-03) ─────────
#
# «El tab de Auditoría no baja el archivo completo, sólo la primera parte.»

def test_la_AUDITORIA_baja_sus_TRES_bloques():
    """⚠️ La Auditoría son tres cuadros, no uno: si CUADRA, de QUÉ está hecho y
    CÓMO se reparte. El capítulo armaba sólo el cuadre.

    Juntarlos en una hoja mezclaría tres tablas con columnas que no tienen nada
    que ver; por eso son tres cuadros y no uno con todo pegado.
    """
    src = _fuente()
    cuerpo = src[src.index("    auditoria: async () => {"):src.index("    resumen12:")]
    assert "· Cuadre" in cuerpo
    assert "Detalle por cuenta" in cuerpo
    assert "Por departamento" in cuerpo
    assert "a.departamentos" in cuerpo and "a.totales" in cuerpo


def test_el_detalle_de_auditoria_baja_AGRUPADO():
    """Owner, 2026-09-03: «necesito que los departamentos se subdividan
    internamente por ingresos, payroll, cost y opex, y que haya espacio entre
    departamentos, para que se vea bien».

    ⚠️ El primer intento lo bajaba PLANO, con el argumento de que así se pivotea
    sin limpiar nada. Es cierto y no alcanzó: la hoja se abre para LEERLA, y
    ciento y pico de filas seguidas sin un corte no se leen.
    """
    src = _fuente()
    cuerpo = src[src.index("    auditoria: async () => {"):src.index("    resumen12:")]
    assert "const porDepto = new Map" in cuerpo
    assert "`Subtotal ${nat}`" in cuerpo
    # El renglón en blanco entre departamentos: sin él, el subtotal de uno
    # queda pegado al encabezado del siguiente y se leen como una sola cosa.
    assert 'filas.push({ label: "", es_total: false, valores: [] });' in cuerpo


def test_la_jerarquia_va_con_SANGRIA_de_Excel_y_no_con_espacios():
    """Con espacios dentro del texto, ordenar la columna o copiarla a otro lado
    se lleva la sangría puesta y el nivel deja de significar nada."""
    src = _fuente()
    cuerpo = src[src.index("    auditoria: async () => {"):src.index("    resumen12:")]
    assert "nivel: 0" in cuerpo and "nivel: 1" in cuerpo and "nivel: 2" in cuerpo


def test_las_naturalezas_van_en_orden_de_PL_tambien_en_el_Excel():
    """Que la misma auditoría se lea en dos órdenes según dónde se mire obliga
    a comprobar que son lo mismo."""
    src = _fuente()
    cuerpo = src[src.index("    auditoria: async () => {"):src.index("    resumen12:")]
    assert 'const ORDEN_NAT = ["Ingresos", "Costo de ventas", "Payroll", "Opex",' in cuerpo


def test_los_cuadros_de_DOS_bloques_bajan_los_dos():
    """Revenue Detail y F&B muestran mes Y acumulado. Bajar sólo el acumulado
    deja fuera el mes que se está cerrando — la misma mitad que faltaba en
    Auditoría."""
    src = _fuente()
    assert "const CORTES_DEL_CIERRE = () =>" in src, (
        "el par mes/acumulado dejó de estar declarado en un solo lugar, y cada "
        "capítulo puede volver a elegir uno solo por su cuenta")
    for clave in ("revdet:", "fb:"):
        cuerpo = src[src.index(f"    {clave} async () => {{"):]
        cuerpo = cuerpo[:cuerpo.index("\n    },")]
        assert "CORTES_DEL_CIERRE()" in cuerpo, f"«{clave}» baja un solo corte"


def test_el_porcentaje_de_costo_se_calcula_sobre_SU_corte():
    """Es un cociente, no una suma: promediar doce porcentajes da un número que
    no es el costo del período. Con dos cortes, cada uno tiene el suyo."""
    src = _fuente()
    cuerpo = src[src.index("    fb: async () => {"):]
    cuerpo = cuerpo[:cuerpo.index("\n    },")]
    assert "const pctCosto = (sid: string, g:" in cuerpo
    assert "ms: number[]) => {" in cuerpo, (
        "el % de costo dejó de recibir el corte: volvería a calcularse sobre "
        "un período fijo aunque la columna diga otro")
