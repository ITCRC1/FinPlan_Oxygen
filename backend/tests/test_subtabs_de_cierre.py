# -*- coding: utf-8 -*-
"""Qué sub-tabs de Cierre de Mes se ven, y para quién.

Owner, 2026-09-02: *«esta vista la van a ver los dueños; me gustaría tener la
opción de poder esconder y visualizar a mi manera, poder quitar y poner tabs sin
borrarlas, sólo para dejar lo importante para el dueño»*.

Es la MISMA matriz que la barra (`tab_enablement`) con un tercer nivel,
`SUBTAB`, así que hereda sus reglas ya probadas — y estas pruebas vigilan que
las herede de verdad.
"""
from pathlib import Path

from app.models.tab_enablement import SCOPE_KINDS

RAIZ = Path(__file__).resolve().parents[2]
CIERRE = RAIZ / "frontend/app/month-end/pl"


def test_SUBTAB_es_un_nivel_propio():
    """⚠️ No es un `ITEM`. Son tres decisiones distintas: «esta propiedad no
    hace Break-Even», «no usa el reporte a la Junta» y «en el cierre no quiero
    que el dueño vea el Flow Through». Metiéndolos en el mismo nivel, apagar un
    sub-tab podría apagar una entrada del menú que se llame igual."""
    assert SCOPE_KINDS == ["TAB", "ITEM", "SUBTAB"]


def test_el_default_sigue_siendo_PRENDIDO():
    """La tabla es esparsa: sin fila, se ve.

    El día que esto se despliega no cambia nada en ninguna propiedad, y un
    sub-tab nuevo nace visible. Al revés —nacer oculto— sería peor: se
    construye algo, nadie lo ve, y nadie sabe que existe para prenderlo.
    """
    import inspect

    from app.api import _apagados

    fuente = inspect.getsource(_apagados.tabs_apagados)
    assert "sólo lo que alguien apagó" in fuente
    # Y todos los niveles llegan presentes, aunque estén vacíos: la pantalla no
    # tiene que saber si alguien apagó alguno todavía.
    assert "{k: set() for k in SCOPE_KINDS}" in fuente


def test_se_puede_esconder_TODO_sin_quedarse_afuera():
    """⚠️ El botón que abre el panel NO es un sub-tab.

    Si lo fuera, «Esconder todas» dejaría la pantalla sin forma de volver — y
    la única salida sería tocar la base. Es la misma propiedad que hace seguro
    apagar la pantalla de administración de la barra.
    """
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    i = pagina.index("setPanelVistas(x => !x)")
    # El botón vive en la fila, no dentro del `.map` de VISTAS.
    assert "VISTAS.filter" in pagina[:i], (
        "el botón de Vistas quedó antes del filtro: revisá que no sea un "
        "sub-tab más")
    assert "⚙ Vistas" in pagina


def test_el_sub_tab_ABIERTO_no_se_saca_de_la_fila():
    """Si alguien esconde el sub-tab en el que está parado, quitarle el botón lo
    dejaría mirando un cuadro sin saber cuál es."""
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    assert "!subOcultos.includes(v.key) || v.key === vista" in pagina


def test_la_pantalla_pide_su_vista_SIN_perfil():
    """Sin perfil, el backend contesta por el rol de quien llama.

    ⚠️ Es lo que hace que cada quien vea su vista sin que esta pantalla tenga
    que saber de roles. Mandar `perfil=""` acá le daría a todos la matriz de la
    propiedad y el filtro por perfil no se aplicaría nunca.
    """
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    assert "getTabsApagados(HOTEL_ID)\n" in pagina


def test_el_panel_SI_manda_el_perfil_aunque_este_vacio():
    """Al revés que la pantalla: sin mandarlo, el admin editaría SU vista
    creyendo que edita la de la propiedad."""
    panel = (CIERRE / "VistasVisibles.tsx").read_text(encoding="utf-8")
    assert "getTabsApagados(HOTEL_ID, perfil)" in panel
    assert "saveTabsApagados(HOTEL_ID," in panel


def test_el_panel_cura_los_TRES_niveles():
    """Owner, 2026-09-02: «del menú y sub menú, y todo lo de adentro».

    La pantalla `/admin/tabs` ya hacía los reportes, pero está en otro lado y
    con otro criterio de entrada. Curar lo que ve un dueño es UNA tarea, y
    partirla en dos pantallas obliga a acordarse de que la otra existe.

    ⚠️ **No es una copia**: los dos caminos escriben en la misma tabla por el
    mismo endpoint, así que no pueden divergir.
    """
    panel = (CIERRE / "VistasVisibles.tsx").read_text(encoding="utf-8")
    for kind in ('"TAB"', '"ITEM"', '"SUBTAB"'):
        assert f'scope_kind: {kind}' in panel, f"el panel no cura {kind}"
    assert "import { NAV }" in panel, (
        "el panel dejó de leer el catálogo de la barra: una lista propia sería "
        "una segunda lista que hay que acordarse de actualizar")


def test_el_catalogo_del_menu_NO_se_copia_en_el_panel():
    """Este proyecto ya pagó DOS veces por una lista escrita a mano —el Club
    desaparecía del P&L, y siete de quince líneas de ingreso faltaban en Master
    Data—. `NAV` es la única lista de lo que existe."""
    panel = (CIERRE / "VistasVisibles.tsx").read_text(encoding="utf-8")
    assert "NAV.map(g =>" in panel
    # Nada de claves de menú escritas a mano.
    for inventado in ('"reports"', '"ownerReport"', '"breakEven"'):
        assert inventado not in panel, (
            f"apareció una clave del menú escrita a mano ({inventado}): un "
            f"reporte nuevo no saldría en este panel")


def test_elegir_un_tab_NO_lo_esconde():
    """La casilla esconde el tab entero; el nombre sólo elige cuál se mira.

    Con un solo botón, entrar a un tab para ver sus reportes lo escondería — y
    el usuario no tendría forma de entender por qué desapareció del menú.
    """
    panel = (CIERRE / "VistasVisibles.tsx").read_text(encoding="utf-8")
    assert "setGrupo(g.key)" in panel
    assert 'scope_kind: "TAB", clave: g.key' in panel


def test_esconder_NO_es_un_permiso_y_la_pantalla_lo_dice():
    """La ruta sigue respondiendo: quien conozca la URL entra igual. Para
    impedir el cambio está el perfil `viewer`. Decirlo evita que alguien crea
    que esconder un sub-tab protege un dato."""
    panel = (CIERRE / "VistasVisibles.tsx").read_text(encoding="utf-8")
    assert "no es un permiso" in panel.lower()
    assert "Sólo lectura" in panel


# ── El resumen de una página (owner, 2026-09-02) ─────────────────────────────

def test_el_resumen_muestra_los_DOS_cuadros_a_la_vez():
    """Owner: «y abajo haces lo mismo pero para budget para que se pueda ver» ·
    «los 2 cuadros a la vez».

    No son dos paneles que se alternan como en el sub-tab de 12 meses: ahí la
    gracia era una versión a lo largo del año, y acá es poder mirar el Actual y
    el Budget sin cambiar de pestaña.
    """
    fuente = (CIERRE / "ResumenDoceMeses.tsx").read_text(encoding="utf-8")
    assert 'bloque("ACTUAL"' in fuente and 'bloque("BUDGET"' in fuente
    # Los dos se dibujan, no se elige uno.
    i = fuente.index("return (\n    <div>")
    cuerpo = fuente[i:i + 400]
    assert "ACTUAL" in cuerpo and "BUDGET" in cuerpo


def test_los_dos_cuadros_comparten_las_COLUMNAS():
    """⚠️ Con columnas propias, la primera de arriba sería marzo y la de abajo
    junio —el Actual se movió de marzo a julio y el Budget de junio a
    diciembre—, una sobre otra invitando a compararlas.

    Se pierde algo de ancho y se gana que mirar hacia abajo signifique algo.
    """
    fuente = (CIERRE / "ResumenDoceMeses.tsx").read_text(encoding="utf-8")
    assert "vivo(arriba.datos, i) || vivo(abajo.datos, i)" in fuente, (
        "cada cuadro volvió a elegir sus propios meses: las columnas dejarían "
        "de alinearse entre el Actual y el Budget")
    # Y la tabla recibe las columnas de afuera, no las calcula.
    assert "function Tabla({ datos, columnas }" in fuente


def test_el_NET_no_se_confunde_con_el_GOP():
    """`Total Expenses` incluye el gasto de propiedad, así que `Net` es el
    resultado DESPUÉS de propiedad. En el P&L Statement el gasto de propiedad
    va debajo del GOP: leer uno donde dice el otro cambia el número por miles."""
    fuente = (CIERRE / "ResumenDoceMeses.tsx").read_text(encoding="utf-8")
    assert "no es el GOP" in fuente, (
        "se fue el aviso de que Net no es GOP: son dos totales distintos con "
        "aspecto de ser el mismo")
    assert "d.payroll[i] + d.cost[i] + d.opex[i] + d.property[i]" in fuente


# ── El Word (owner, 2026-09-02) ──────────────────────────────────────────────

def test_el_Word_no_copia_ningun_calculo():
    """⚠️ Cada capítulo sale del MISMO constructor que usa la pantalla.

    El P&L Statement calculaba dentro de su vista, así que el documento no
    podía armarlo sin copiarlo: se subió `cuadroEstado` al componente. El
    Resumen 12m exporta `armar` y `filasResumen` desde su propio módulo. Una
    copia sería una segunda verdad en un reporte que ven los dueños.
    """
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    # ⚠️ Desde el 2026-09-03 los capítulos salen de un REGISTRO recorrido en
    # el orden de `VISTAS`, no de una secuencia escrita a mano — ver
    # `test_word_todas_las_vistas`. Lo que se sigue exigiendo es lo mismo: que
    # el capítulo use el constructor de la pantalla y no una copia.
    assert "cuadroEstado(false), cuadroEstado(true)" in pagina, (
        "el capítulo del P&L Statement dejó de usar el constructor de la "
        "pantalla")
    assert "armar as armarResumen, filasResumen" in pagina, (
        "el Resumen 12m se está rearmando en el Word en vez de importar su "
        "propio constructor")

    resumen = (CIERRE / "ResumenDoceMeses.tsx").read_text(encoding="utf-8")
    assert "export function filasResumen" in resumen
    assert "const FILAS = filasResumen(datos);" in resumen, (
        "la tabla dejó de usar `filasResumen`: la pantalla y el documento "
        "podrían dibujar líneas distintas")


def test_los_capitulos_salen_de_los_tabs_ACTIVOS():
    """«Siempre deben salir los tabs que estén activos en la vista.»

    ⚠️ No se relee `tab_enablement`: se filtra `VISTAS` por `subOcultos`, que
    es lo mismo que dibuja la fila de sub-tabs. Una segunda lectura de la misma
    decisión es una segunda oportunidad de que difieran.
    """
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    assert "VISTAS.map(v => v.key).filter(k => !subOcultos.includes(k))" in pagina


def test_un_escenario_que_falla_no_se_lleva_el_documento():
    """El Resumen pide datos aparte: si un escenario falla, el resto de los
    capítulos tiene que salir igual. Un documento a medias sirve; ninguno, no."""
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    assert "el resto del documento sale igual" in pagina
