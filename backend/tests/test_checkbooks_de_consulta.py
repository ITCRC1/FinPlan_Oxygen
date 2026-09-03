# -*- coding: utf-8 -*-
"""Los checkbooks, para consultar sin entrar a Planning.

Owner, 2026-09-03: *«algunos usuarios no van a tener acceso a Planning por
obvias razones; necesito un sub-tab en Cierre mensual para poder generar los
checkbooks, la misma vista de Planning pero para visualizar qué hay a modo de
reportes: opex por departamento, salario por departamento, costo y gastos de
propietario»*.
"""
from pathlib import Path

FRONT = Path(__file__).resolve().parents[2] / "frontend"
CIERRE = FRONT / "app/month-end/pl"
VISTA = CIERRE / "Checkbooks.tsx"


def test_estan_los_CUATRO_libros_que_pidio():
    src = VISTA.read_text(encoding="utf-8")
    for clase in ("opex", "payroll", "cost", "property"):
        assert f'clase: "{clase}"' in src, f"falta el checkbook de {clase}"


def test_es_de_SOLO_LECTURA():
    """⚠️ Es la mitad del pedido: quien no debe tocar el presupuesto entra y ve
    lo mismo, sin forma de que un clic distraído cambie un número.

    Y no se resuelve escondiendo el botón de guardar: un formulario de sólo
    lectura sigue mandando lo que se escriba si alguien encuentra la ruta. Acá
    no hay un solo campo.
    """
    # ⚠️ Se mira el CÓDIGO y no el archivo entero: el comentario de arriba
    # explica por qué no hay campos que guarden, y buscar «guarda» a secas se
    # dispara con la explicación en vez de con el defecto.
    src = VISTA.read_text(encoding="utf-8")
    codigo = chr(10).join(l for l in src.splitlines()
                          if not l.lstrip().startswith(("*", "//", "/*")))
    for editable in ("<input", "<textarea", "contentEditable", "onBlur=",
                     "guardarComentario", "api.put", "api.post"):
        assert editable not in codigo, (
            f"la vista de consulta trae «{editable}»: dejó de ser de sólo "
            f"lectura")


def test_usa_el_MISMO_endpoint_que_el_desplegable_del_PL():
    """⚠️ Reusarlo no es ahorro: es lo que garantiza que lo que se ve acá SUMA
    exactamente la línea del reporte. Un endpoint propio sería una segunda
    aritmética, y el día que difiera no habría cómo saber cuál tiene razón."""
    src = VISTA.read_text(encoding="utf-8")
    assert "getDetalleDeCelda" in src


def test_dice_de_donde_sale_cada_version():
    """Un presupuesto no tiene mayor cargado; su detalle vive en el auxiliar.
    Mezclarlos sin decirlo sería peor que no mostrarlos."""
    src = VISTA.read_text(encoding="utf-8")
    assert "v.fuente" in src


def test_avisa_que_el_gasto_de_propiedad_NO_va_por_departamento():
    """Vive todo en el 0250 y se abre por cuenta. Sin el aviso, el selector de
    departamento parece roto cuando no cambia nada."""
    src = VISTA.read_text(encoding="utf-8")
    assert 'clase === "property" && dept' in src


def test_esta_en_el_MENU_y_no_en_un_sub_tab():
    """Owner, 2026-09-03, después de verlo dentro de Cierre de Mes: «favor mueve
    el checkbook afuera, donde está Full P&L Ejecutivo».

    ⚠️ No es sólo dónde se hace clic. El que no tiene acceso a Planning viene
    JUSTAMENTE a mirar un checkbook; un sub-tab lo obliga a entrar al cierre,
    elegir versiones y saber que está ahí adentro.
    """
    import json
    nav = (FRONT / "components/TopNav.tsx").read_text(encoding="utf-8")
    assert '{ key: "monthEndCheckbooks", href: "/month-end/checkbooks" }' in nav
    # Y junto a Full P&L Ejecutivo, en el menú de Cierre de Mes.
    grupo = nav[nav.index('key: "monthEnd",'):nav.index('key: "operationInsight"')]
    assert "plFullExec" in grupo and "monthEndCheckbooks" in grupo
    # Ya NO es un sub-tab.
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    assert '{ key: "checkbooks" }' not in pagina
    for idioma in ("es", "en"):
        textos = json.dumps(json.loads(
            (FRONT / f"messages/{idioma}.json").read_text(encoding="utf-8")))
        assert '"monthEndCheckbooks"' in textos, f"sin rótulo en {idioma}"


def test_la_pantalla_nueva_REUSA_el_componente():
    """Una segunda versión de la misma tabla es cómo terminan mostrando números
    distintos."""
    pag = (FRONT / "app/month-end/checkbooks/page.tsx").read_text(encoding="utf-8")
    assert 'import Checkbooks from "@/app/month-end/pl/Checkbooks"' in pag


def test_su_EXCEL_baja_los_cuatro_libros_completos():
    """⚠️ Los cuatro y con TODOS los departamentos, no lo que esté filtrado en
    pantalla: un archivo que sale distinto según el filtro del momento no se
    puede archivar."""
    pag = (FRONT / "app/month-end/checkbooks/page.tsx").read_text(encoding="utf-8")
    assert 'getDetalleDeCelda([scenarioId], clase, "")' in pag
    for clase in ("opex", "payroll", "cost", "property"):
        assert f'"{clase}"' in pag


def test_los_cuatro_libros_son_SUB_TABS_de_segundo_nivel():
    """Owner, 2026-09-03: «puede ser que se ponga un sub tab CHECKBOOKS e
    internamente se pongan las 4 en sub tab del sub».

    ⚠️ Van con subrayado y no como los botones-pastilla de la fila de arriba:
    dos filas de pastillas idénticas se leen como UN solo nivel, y entonces
    «Opex» del checkbook parece hermano de «Opex x Depto», que es otro reporte.
    La forma tiene que decir cuál está adentro de cuál.
    """
    src = VISTA.read_text(encoding="utf-8")
    assert "2px solid var(--brand)" in src
    assert '2px solid transparent' in src
    # Y no el fondo lleno de la fila de arriba.
    assert 'background: clase === l.clase ? "var(--brand)"' not in src


def test_cada_fila_trae_SU_departamento():
    """Owner, 2026-09-03: «los checkbooks deben estar por departamentos, si no
    no se puede saber a qué corresponde; puede ser todos, pero internamente
    separados».

    ⚠️ La llave del endpoint era la CUENTA sola, así que la 7065 de
    Habitaciones y la 7065 del Club caían en la misma fila y el resultado no era
    de nadie. Y las dos se llaman «Cleaning Supplies»: sin el departamento son
    filas idénticas con montos distintos.
    """
    import inspect

    from app.api import detalle_celda_api as api
    for fn in (api._del_mayor, api._del_auxiliar):
        assert "(dept, cuenta)" in inspect.getsource(fn), (
            f"{fn.__name__} volvió a indexar por cuenta sola")
    resp = inspect.getsource(api.detalle_de_celda)
    assert '"dept_code": dept' in resp and '"dept_name"' in resp


def test_el_REPARTO_tambien_lleva_su_departamento_destino():
    """El reparto que llega a Habitaciones no es el mismo que llega al Club.
    Con la llave sin departamento los dos caían en una sola fila."""
    import inspect

    from app.api import detalle_celda_api as api
    fuente = inspect.getsource(api._del_auxiliar)
    assert "out.setdefault((destino, cuenta)" in fuente


def test_las_opciones_del_selector_salen_de_LOS_DATOS():
    """⚠️ Owner: «sólo existe la opción Todos, no hay más opciones».

    El selector se llenaba de `gasto-por-clase`, que sólo devuelve los nombres
    de departamento cuando se le pide el DETALLE — y la pantalla lo pedía sin
    detalle, así que llegaba vacío.

    Ahora salen de las filas del propio libro, que además es mejor: ofrecer los
    sesenta y cinco del catálogo en un libro que usa ocho hace buscar el que
    sirve entre los que no.
    """
    src = VISTA.read_text(encoding="utf-8")
    assert "for (const f of datos?.filas ?? [])" in src
    assert "vistos.set(f.dept_code" in src
    # Y se pide el libro COMPLETO una vez; el filtro es local.
    assert 'getDetalleDeCelda(scenarioIds, clase, "")' in src


def test_la_tabla_se_corta_por_departamento_con_su_SUBTOTAL():
    """Con seis departamentos abiertos, sin subtotal no hay forma de saber
    cuánto pesa cada uno sin sumar a mano."""
    src = VISTA.read_text(encoding="utf-8")
    assert "Subtotal {g.code}" in src
    assert "grupos.flatMap(g => [" in src


def test_un_departamento_que_ya_no_existe_no_deja_la_tabla_VACIA():
    """Al cambiar de libro, el departamento elegido puede no estar en el nuevo:
    la tabla quedaría vacía sin decir por qué."""
    src = VISTA.read_text(encoding="utf-8")
    assert "if (dept && !opciones.some(([c]) => c === dept)) setDept(\"\");" in src
