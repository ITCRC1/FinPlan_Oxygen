# -*- coding: utf-8 -*-
"""Tocar una línea y ver de qué está hecha, sin salir de la pantalla.

Owner, 2026-09-03: *«toco la línea de Rooms Revenue y me abre el detalle, sin
ir… si abro payroll de Rooms se me despliegan los GL que suman eso, como un
cuadro sin salir a la otra ventana… así voy presentando y puedo ver los detalles
de una vez»*.

Y, enseguida: *«el presupuesto debe tener GL, siempre debe estar conectado a un
GL»*.
"""
import inspect
from pathlib import Path

from app.api import detalle_celda_api as api

FRONT = Path(__file__).resolve().parents[2] / "frontend"
CIERRE = FRONT / "app/month-end/pl"


def test_el_presupuesto_se_abre_POR_CUENTA_igual_que_el_actual():
    """⚠️ Y sí tiene cuenta: cada línea del checkbook lleva su `account_code`
    —opex, costo y below-GOP— y los 17 conceptos de planilla SON cuentas del
    mayor (`c6000_sw` es la 6000).

    Verificado en producción sobre Rooms: el ACTUAL y los dos BUDGET abren las
    mismas cuentas 6000, 6020, 6023… y se comparan una contra otra.
    """
    fuente = inspect.getsource(api._del_auxiliar)
    assert "account_code" in fuente
    assert "from app.api.consulta_api import CONCEPTOS" in fuente, (
        "la planilla del presupuesto dejó de abrirse por concepto, que es lo "
        "que la hace comparable cuenta contra cuenta con el mayor")


def test_cada_version_DICE_de_donde_sale_su_detalle():
    """Un ACTUAL lo trae del mayor y un presupuesto de sus auxiliares.
    Mezclarlos sin decirlo sería peor que no mostrarlos."""
    fuente = inspect.getsource(api.detalle_de_celda)
    assert '"Mayor (GL)"' in fuente and '"Auxiliar (checkbook)"' in fuente


def test_elige_la_fuente_con_la_MISMA_regla_que_el_cuadro():
    """⚠️ `lo_subido_manda` es lo que usa `gasto_por_clase` para decidir de
    dónde lee la celda. Con otro criterio, el desplegable abriría cuentas que
    no son las que suman el número que se tocó."""
    fuente = inspect.getsource(api.detalle_de_celda)
    assert "recalc.lo_subido_manda" in fuente


def test_el_departamento_sube_EN_CADENA():
    """`consolidate_dept` resuelve un escalón y hay cadenas de dos —el 0132
    cuelga del 0130 y el 0130 del 0140—. Es la misma función que usa el cuadro;
    con un escalón menos, el detalle no sumaría la celda."""
    fuente = inspect.getsource(api._padre)
    assert "for _ in range(5)" in fuente


def test_una_linea_de_ingreso_AGREGADA_no_se_disfraza_de_cuenta():
    """⚠️ `ROOMS` del checkbook agrega la 4000, la 4001 y la 4002. Ponerle una
    cuenta sería elegir una de las que agrupa.

    Sale con el nombre de la línea y marcada `agregado`, y la pantalla lo
    explica.
    """
    fuente = inspect.getsource(api._del_auxiliar)
    assert "REVENUE_LINE_ACCOUNT" in fuente
    assert '"agregado"' in fuente
    pantalla = (CIERRE / "DetalleCelda.tsx").read_text(encoding="utf-8")
    assert "v.agregado" in pantalla


def test_el_mapeo_de_linea_del_checkbook_NO_se_reescribe():
    """Sale de `REVENUE_LINE_TO_REPORT_LINE`, la misma tabla con la que el
    motor lleva el checkbook de ingreso al P&L."""
    fuente = inspect.getsource(api._del_auxiliar)
    assert "pl_engine.REVENUE_LINE_TO_REPORT_LINE" in fuente


def test_el_corte_del_desplegable_es_el_del_CUADRO():
    """⚠️ Si sumara el año entero mientras el cuadro muestra julio, los números
    no cerrarían con la celda que se tocó — y existe justamente para explicar
    esa celda."""
    pantalla = (CIERRE / "DetalleCelda.tsx").read_text(encoding="utf-8")
    # El mes sigue al cuadro; el acumulado va de enero hasta ese mes. Los dos
    # salen de `mes`, que es el del cuadro de atrás.
    assert "MESES[mes - 1], meses: [mes - 1]" in pantalla
    assert "Array.from({ length: mes }" in pantalla


def test_se_cierra_con_ESCAPE():
    """Está pensado para presentar: buscar la X con el mouse se nota."""
    pantalla = (CIERRE / "DetalleCelda.tsx").read_text(encoding="utf-8")
    assert 'e.key === "Escape"' in pantalla


def test_NO_hay_fondo_oscuro():
    """Owner, 2026-09-03: «que la ventana que se abre se pueda mover para darle
    visibilidad al número que se quiere presentar».

    ⚠️ La primera versión era un modal con velo encima. Con eso, poder
    arrastrarla NO SIRVE DE NADA: el cuadro de atrás queda igual de tapado,
    sólo que por el velo en vez de por el panel. Sacar el velo es lo que hace
    que moverla signifique algo.
    """
    pantalla = (CIERRE / "DetalleCelda.tsx").read_text(encoding="utf-8")
    assert "rgba(15,20,28" not in pantalla, "volvió el velo del modal"
    assert "position: \"fixed\", inset: 0" not in pantalla


def test_la_ventana_SE_MUEVE():
    """Y con eventos de PUNTERO, no de mouse: esto se presenta también desde
    una pantalla táctil y `pointer*` cubre los dos con el mismo código."""
    pantalla = (CIERRE / "DetalleCelda.tsx").read_text(encoding="utf-8")
    assert "onPointerDown={alAgarrar}" in pantalla
    assert "setPointerCapture" in pantalla, (
        "sin capturar el puntero, mover rápido suelta la ventana a mitad de "
        "camino cuando el cursor sale del encabezado")
    assert 'touchAction: "none"' in pantalla


def test_la_ventana_no_se_puede_perder_fuera_de_la_pantalla():
    """Una ventana arrastrada más allá del borde no se recupera sin recargar."""
    pantalla = (CIERRE / "DetalleCelda.tsx").read_text(encoding="utf-8")
    assert "window.innerWidth - 120" in pantalla
    assert "window.innerHeight - 44" in pantalla


def test_salen_el_MES_y_el_ACUMULADO():
    """Owner: «sólo sale el mes, pero no el acumulado; debés ponerlo, hay
    espacio».

    ⚠️ Los dos cortes se calculan sobre la MISMA serie de doce meses que manda
    el backend —el mes es una posición y el acumulado la suma hasta ahí—, así
    que no son dos consultas y no pueden diferir entre sí.
    """
    pantalla = (CIERRE / "DetalleCelda.tsx").read_text(encoding="utf-8")
    assert "const cortes" in pantalla
    assert "`YTD ${MESES[mes - 1]}`" in pantalla
    assert "colSpan={cortes.length}" in pantalla


def test_con_el_ano_completo_NO_se_repite_la_columna():
    """Dos columnas iguales invitan a buscarles la diferencia."""
    pantalla = (CIERRE / "DetalleCelda.tsx").read_text(encoding="utf-8")
    assert 'if (horizonte === "full")' in pantalla


def test_solo_se_marca_lo_que_de_verdad_ABRE():
    """Un adorno que no hace nada al tocarlo es peor que no tenerlo."""
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    assert "CLASE_DE[f.code] ? ABRIBLE : undefined" in pagina


def test_la_celda_abrible_SE_VE_sin_pasar_el_mouse():
    """Owner, 2026-09-03, con la función ya desplegada: «no se ve nada».

    ⚠️ El primer intento fue un subrayado punteado en `--text-disabled`, que en
    una tabla de doscientos números es invisible. En una presentación nadie va
    tanteando la pantalla con el mouse: la marca tiene que estar antes de
    tocar.

    Y no puede ser color: en un estado de resultados el color ya significa otra
    cosa —rojo es negativo—, así que un renglón azul se leería como un dato
    distinto de los de al lado.
    """
    css = (FRONT / "app/globals.css").read_text(encoding="utf-8")
    assert ".fin-abrible" in css
    assert ".fin-abrible::after" in css, "no hay marca visible sin hover"
    assert ".fin-abrible:hover" in css, "no hay respuesta al pasar el mouse"


def test_el_total_del_desplegable_se_dibuja():
    """Tiene que dar exactamente la celda que se tocó. Si no da, el desplegable
    está explicando otra cosa — y sin el renglón no hay forma de notarlo."""
    pantalla = (CIERRE / "DetalleCelda.tsx").read_text(encoding="utf-8")
    assert ">TOTAL<" in pantalla.replace("\n", "").replace(" ", "")


def test_la_ventana_ABRE_JUNTO_a_la_linea_que_se_toco():
    """Owner, 2026-09-03: «se queda arriba… si estás muy abajo debés ir hasta
    arriba a buscarlo; creo que debe salir muy cercano de donde está la
    fuente».

    ⚠️ Un cuadro de sesenta filas se recorre hasta el final, y una ventana que
    aparece fuera de la vista se lee como que **no pasó nada** — no como que se
    abrió en otro lado.
    """
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    assert pagina.count("origen: { x: e.clientX, y: e.clientY }") >= 3, (
        "algún punto de entrada dejó de mandar dónde se tocó, y esa ventana "
        "vuelve a abrir arriba de todo")
    pantalla = (CIERRE / "DetalleCelda.tsx").read_text(encoding="utf-8")
    assert "celda.origen ? { x: celda.origen.x + 14" in pantalla


def test_y_si_no_entra_abajo_se_ACOMODA_sola():
    """Abrir junto al clic no alcanza: tocando una línea del final, la ventana
    nace por debajo del borde. El alto real no se sabe hasta que está dibujada,
    así que se mide y se sube.

    ⚠️ En `useLayoutEffect` y no en `useEffect`: el de diseño corre ANTES de
    pintar, así que no se ve el salto.
    """
    pantalla = (CIERRE / "DetalleCelda.tsx").read_text(encoding="utf-8")
    assert "useLayoutEffect" in pantalla
    assert "y + caja.height > window.innerHeight - margen" in pantalla
    assert "x + caja.width > window.innerWidth - margen" in pantalla


def test_acomodarla_NO_le_gana_al_usuario():
    """Reacomodarla cuando ya la movió a mano sería quitársela de donde la
    puso. Corre una sola vez, al abrir."""
    pantalla = (CIERRE / "DetalleCelda.tsx").read_text(encoding="utf-8")
    assert "const acomodada = useRef(false);" in pantalla
    assert "if (acomodada.current" in pantalla


def test_la_ventana_sale_del_arbol_con_un_PORTAL():
    """⚠️ La razón por la que «está siempre arriba» sobrevivió a pasarle la
    posición del clic.

    `components/Transicion.tsx` envuelve CADA página en `.pag-entra`, que lleva
    una animación sobre `transform` con `fill-mode: both`. **Un ancestro con
    transform se vuelve el bloque contenedor de sus descendientes
    `position: fixed`**, así que el `top` se medía desde el tope del contenido
    de la página y no desde el de la pantalla.

    No alcanza con corregir la hoja de estilos: bastaría un `transform` nuevo en
    cualquier contenedor para que el defecto volviera sin que nada fallara.
    Fuera del árbol, la ventana es inmune.
    """
    pantalla = (CIERRE / "DetalleCelda.tsx").read_text(encoding="utf-8")
    assert "createPortal" in pantalla
    assert "document.body" in pantalla
    # Y no revienta al dibujar en el servidor, donde `document` no existe.
    assert "if (!montado) return null;" in pantalla


def test_la_animacion_de_pagina_sigue_creando_bloque_contenedor():
    """La prueba de arriba mide una consecuencia; ésta mide la CAUSA, para que
    se entienda por qué existe el portal el día que alguien lo quiera quitar."""
    css = (FRONT / "app/globals.css").read_text(encoding="utf-8")
    assert ".pag-entra { animation:" in css
    assert "transform: translateY(8px)" in css
    trans = (FRONT / "components/Transicion.tsx").read_text(encoding="utf-8")
    assert 'className="pag-entra"' in trans


def test_no_se_da_por_ACOMODADA_mientras_carga():
    """Con «cargando…» el panel mide sesenta píxeles. Medirlo ahí y darlo por
    acomodado deja la ventana colgando fuera de la pantalla en cuanto llegan
    las filas."""
    pantalla = (CIERRE / "DetalleCelda.tsx").read_text(encoding="utf-8")
    assert "!celda.origen || !datos) return;" in pantalla


# ─── Que el desplegable SUME la celda (owner, 2026-09-03) ───────────────────
#
# «No están saliendo todos los datos en el pop-up… por ejemplo Spa, no veo nada
# en Budget 2026.»
#
# Comprobadas las 120 celdas de 2026 contra `gasto_por_clase`: eran 15 las que
# no cuadraban, por DOS causas, y las dos eran lo mismo — el desplegable no
# replicaba algo que el cuadro sí hace.

def test_el_reparto_entra_como_OPEX_en_las_dos_ramas():
    """⚠️ La causa de 14 de los 15 descuadres.

    Desde que `gasto_por_clase` dejó de descartar los departamentos de reparto,
    la celda de opex incluye los asientos de distribución. Sin ellos acá, el
    desplegable quedaba corto en TODO departamento que consume lavandería o
    cafetería. Medido en el BUDGET 2026: Rooms 7.023,06 de menos, el Club
    1.768,31, y la propia lavandería mostraba un cuadro VACÍO sobre una celda
    de −9.838,52.
    """
    mayor = inspect.getsource(api._del_mayor)
    assert "CUENTAS_DE_REPARTO" in mayor
    aux = inspect.getsource(api._del_auxiliar)
    assert "AllocationEntry" in aux
    assert "alloc" in aux.lower()


def test_los_asientos_de_reparto_van_por_MES_y_no_por_columnas():
    """`AllocationEntry` tiene una fila por mes; los checkbooks tienen doce
    columnas. Tratarlos igual pone todo el año en enero."""
    aux = inspect.getsource(api._del_auxiliar)
    assert "int(a.month or 0)" in aux


def test_el_ingreso_SIN_LINEA_se_indexa_por_departamento():
    """⚠️ El descuadre número 15.

    `gasto_por_clase` hace `clave_rev = ln_rev or FUSION_INGRESO.get(dept, dept)`.
    Sin la segunda mitad, el ingreso del Área Recreativa (270) —que no resuelve
    a ninguna línea— abría un cuadro vacío sobre una celda de $350,41.
    """
    mayor = inspect.getsource(api._del_mayor)
    assert "FUSION_INGRESO.get(dept, dept)" in mayor


def test_las_tablas_compartidas_se_IMPORTAN_y_no_se_copian():
    """Dos copias de `CUENTAS_DE_REPARTO` o de `FUSION_INGRESO` es cómo el
    desplegable termina sumando algo distinto del número que se tocó."""
    fuente = (Path(api.__file__)).read_text(encoding="utf-8")
    assert "from app.api.gasto_por_clase_api import" in fuente
    # Y no reescritas acá.
    assert '"4999"' not in fuente and '"0161": "0162"' not in fuente


# ─── El forecast vivo: actuales hasta el corte, proyectado después ──────────
#
# Owner, 2026-09-03: «hay que revisar el checkbook Forecast 2026, porque ése
# está compuesto por actuales y por forecast; cómo se está manejando esto en
# esta vista».

def test_un_FORECAST_mezcla_actuales_y_proyectado():
    """⚠️ No se estaba manejando: el endpoint leía el checkbook del forecast
    para los DOCE meses, y el P&L usa el ACTUAL hasta el corte.

    Medido en el FORECAST Working 2026 (corte julio), opex de Habitaciones:

        desplegable  0  0  0     0     0  11.892  17.714 | 17.546 …
        el cuadro    0  0  0    25  1.513   2.185   8.329 | 17.546 …

    De agosto en adelante coincidían al centavo; hasta julio no. Eran **38
    celdas** del forecast que no sumaban su propia línea del P&L — y no
    aparecieron antes porque la comprobación de 120 celdas usó los tres
    primeros escenarios y el forecast quedó afuera.
    """
    fuente = inspect.getsource(api.detalle_de_celda)
    assert 'escenario.type == "FORECAST"' in fuente
    assert "recalc.linked_actual_scenario" in fuente


def test_cada_mes_sale_de_UNA_sola_fuente():
    """Sumar las dos contaría dos veces lo mismo en los meses cerrados."""
    fuente = inspect.getsource(api.detalle_de_celda)
    assert "real[i] if i < corte else propia[i]" in fuente


def test_se_DICE_hasta_donde_llegan_los_actuales():
    """Doce columnas iguales harían leer como presupuesto lo que ya pasó."""
    fuente = inspect.getsource(api.detalle_de_celda)
    assert '"actuals_through": corte' in fuente
    assert "Actual hasta {MESES_ES[corte - 1]}" in fuente
    pantalla = (CIERRE / "Checkbooks.tsx").read_text(encoding="utf-8")
    assert "v.actuals_through ?? 0" in pantalla
    assert '"Actual cargado"' in pantalla
