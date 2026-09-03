# -*- coding: utf-8 -*-
"""El reparto de lavandería: filas en blanco y departamentos que no existen.

Owner, 2026-09-03: *«ya hice el allocation de lavandería, favor revisá porque me
está dando error cuando guardo»* · *«dice application error, a client-side
exception has occurred»*.

El backend devolvía **200 en todos los guardados** —está en el log de
producción—, así que el error era de la pantalla. Lo que encontró la revisión
fue dos filas invalidas en `laundry_allocation_config` del BUDGET 2026:

    ('',    '',      0.00, False)   <- una fila SIN departamento
    ('110', 'Rooms', 0.70, True)    <- el codigo de Rooms es `0110`, no `110`

La segunda es la cara: `110` no existe en el catálogo, así que
`group_for_dept("110")` cae en `OTHER_OVERHEAD` y los $6.886,96 repartidos no
llegan a Habitaciones.
"""
import inspect

from app.api import allocation_api
from app.engine import pl_engine


def test_una_fila_SIN_departamento_no_se_guarda():
    """⚠️ Y si venían DOS en blanco, el commit reventaba.

    El `select` no ve lo que está pendiente en la sesión, así que las dos se
    insertaban y `uq_laundry_config` las rechazaba al hacer commit. La pantalla
    agrega renglones vacíos para escribir encima: guardar antes de llenarlos no
    puede romper nada.
    """
    fuente = inspect.getsource(allocation_api.upsert_laundry_config)
    assert 'code = (row.dept_code or "").strip()' in fuente
    assert "if not code:" in fuente and "continue" in fuente
    assert "limpias[code] = row" in fuente, (
        "se dejó de deduplicar por departamento: dos filas del mismo depto en "
        "un guardado volverían a chocar contra el UNIQUE")


def test_el_codigo_de_Rooms_es_0110_y_no_110():
    """El reparto a un departamento que no existe se pierde en OTHER_OVERHEAD.

    No es un error del motor: `group_for_dept` contesta lo que puede con lo que
    le dan. Es que `110` no está en el catálogo — el de Habitaciones es `0110`.
    """
    assert pl_engine.group_for_dept("0110") == "ROOMS"
    assert pl_engine.group_for_dept("110") != "ROOMS", (
        "si `110` empezara a resolver a ROOMS, este cotejo dejaría de avisar "
        "que el código está mal escrito")


def test_el_credito_del_reparto_va_a_la_cuenta_de_ALLOCATION():
    """El crédito al departamento de origen usa una 49xx; si no, el gasto no
    netea y la lavandería seguiría contándose entera."""
    assert "4999" in pl_engine.ALLOCATION_ACCOUNTS
    assert "4900" in pl_engine.ALLOCATION_ACCOUNTS


def test_los_cuadros_de_validacion_no_se_llevan_la_pantalla():
    """Owner, 2026-09-03: «cuando doy guardar y recalcular me saca de la
    pantalla y me da error».

    ⚠️ En React una excepción al dibujar **desmonta el árbol entero**. Esta
    pantalla tiene varios cuadros de validación, cada uno leyendo un pedazo
    distinto de la respuesta; que uno se rompa —por un departamento que no está
    en el catálogo, o por una llave vacía— dejaba al usuario sin pantalla y sin
    la configuración que acababa de escribir.

    Con la red puesta, el cuadro que falla se vuelve un aviso CON SU MOTIVO y
    los demás siguen. No tapa el error: lo muestra, que es más de lo que decía
    la pantalla en blanco.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2] / "frontend"
    pagina = (raiz / "app/allocations/config/page.tsx").read_text(encoding="utf-8")
    assert pagina.count("<BloqueSeguro") == 2
    assert pagina.count("</BloqueSeguro>") == 2, (
        "quedó una red sin cerrar: el bloque siguiente entraría adentro")

    red = (raiz / "components/BloqueSeguro.tsx").read_text(encoding="utf-8")
    assert "getDerivedStateFromError" in red, (
        "sin ese método la clase no atrapa nada — es la única forma que da "
        "React de capturar un error de render")
    assert "componentDidCatch" in red
    assert "this.state.error.message" in red, (
        "la red dejó de mostrar el motivo: volveríamos a un callejón sin pista")


def test_la_condicion_del_bloque_va_GUARDADA():
    """⚠️ Un `ErrorBoundary` NO atrapa la condición que decide su hijo.

    `{cond && <Boundary>…</Boundary>}` — y también
    `<Boundary>{cond && …}</Boundary>` — evalúan `cond` en el render del PADRE,
    para construir el elemento hijo. Si `cond` revienta, el error ocurre antes
    de que la red exista y la pantalla se cae igual.

    Es exactamente lo que pasó: se puso la red alrededor de los dos cuadros y el
    owner siguió viendo «Application error». La condición leía
    `summary.CAFETERIA` y `breakdown.total_cost` sin guarda.
    """
    from pathlib import Path

    pagina = (Path(__file__).resolve().parents[2]
              / "frontend/app/allocations/config/page.tsx").read_text(encoding="utf-8")
    assert "summary?.CAFETERIA\n        && Object.keys" in pagina, (
        "la condición volvió a leer `summary.CAFETERIA` sin guarda: si la clave "
        "no viene, la pantalla se cae ANTES de que la red pueda atraparlo")
    assert "breakdown?.total_cost?.some(" in pagina


def test_la_ruta_tiene_su_propia_pantalla_de_error():
    """`error.tsx` es del framework y envuelve TODA la ruta, incluido el cuerpo
    del componente — donde una red puesta a mano no llega.

    Y muestra el mensaje: «see the browser console» obliga a abrir las
    herramientas de desarrollo para poder reportar un problema.
    """
    from pathlib import Path

    err = Path(__file__).resolve().parents[2] / "frontend/app/error.tsx"
    assert err.exists(), "se fue la pantalla de error de la app"
    fuente = err.read_text(encoding="utf-8")
    assert "error.message" in fuente, "dejó de mostrar el motivo"
    assert "está guardado" in fuente, (
        "se fue el aviso de que lo guardado se guardó — es lo primero que el "
        "usuario necesita saber cuando la pantalla se cae")


def test_el_endpoint_de_calculate_NO_manda_monthly_y_la_pantalla_lo_sabe():
    """⚠️ El bug que dejaba la pantalla en blanco al apretar Recalcular.

    `POST /allocations/{id}/calculate/` devolvía `monthly` cuando tenía su
    propia implementación. Al pasar a delegar en `_recalc_allocations` —el mismo
    paso del recálculo completo, para que las dos rutas protejan igual los meses
    cerrados— la clave dejó de viajar. **La pantalla siguió leyéndola**, y de
    ahí salía «Cannot read properties of undefined (reading 'laundry')».

    El tipo la marca opcional a propósito: así el compilador obliga a preguntar
    antes de usarla, y el mismo error no puede volver en silencio.
    """
    import inspect
    from pathlib import Path

    from app.api import allocation_api

    fuente = inspect.getsource(allocation_api.calculate_allocations)
    assert '"monthly"' not in fuente, (
        "si el endpoint volvió a mandar `monthly`, actualizá el tipo del "
        "front: hoy está marcado opcional porque no viaja")

    raiz = Path(__file__).resolve().parents[2] / "frontend"
    api = (raiz / "lib/api.ts").read_text(encoding="utf-8")
    assert "monthly?: {" in api, (
        "`monthly` dejó de ser opcional: el compilador ya no obliga a "
        "preguntar y el crash puede volver")

    # Cada uso tiene que estar guardado: o con `?.`, o detrás de un `if` en la
    # misma línea. Se mira línea por línea porque prohibir la cadena a secas
    # daría un falso positivo justo en el uso correcto.
    pagina = (raiz / "app/allocations/config/page.tsx").read_text(encoding="utf-8")
    sueltos = [
        ln.strip() for ln in pagina.splitlines()
        if "calcResult.monthly." in ln
        and "calcResult?.monthly" not in ln
        and "calcResult.monthly?" not in ln
        and "calcResult.monthly &&" not in ln
    ]
    assert not sueltos, (
        "estos usos de `monthly` no están guardados y volverían a dejar la "
        f"pantalla en blanco: {sueltos}")


def test_se_puede_BORRAR_una_fila_de_la_matriz():
    """Owner, 2026-09-03: corrigió el código de Habitaciones de `110` a `0110` y
    la fila vieja quedó pegada — **la pantalla no tenía forma de borrar**.

    Los kilos pasaron a sumar 1,70 en vez de 1,00 y el reparto se partió en dos,
    con Rooms llevándose la mitad de lo que le tocaba. Hubo que sacarla por la
    base.

    ⚠️ `dept` va como PARÁMETRO y no en la ruta: la fila que más hay que poder
    borrar es la del departamento VACÍO —un renglón en blanco guardado sin
    llenar— y `.../config//` no es una URL: el servidor la normaliza y la fila
    queda inalcanzable justo en el caso que más importa.
    """
    import inspect

    from app.api import allocation_api

    fuente = inspect.getsource(allocation_api.borrar_fila_config)
    assert 'dept: str = ""' in fuente, (
        "`dept` volvió a la ruta: la fila sin departamento quedaría "
        "inalcanzable")
    # Sirve para las dos matrices, no solo lavandería.
    assert '"laundry": LaundryAllocationConfig' in fuente
    assert '"cafeteria": CafeteriaAllocationConfig' in fuente
    # Y respeta el candado del escenario, como todo lo que escribe.
    assert "await candado(session, scenario_id)" in fuente


def test_borrar_NO_recalcula():
    """Saca la fila y deja los asientos. Rehacer el reparto es el botón de al
    lado — así se puede limpiar la matriz sin mover números hasta estar
    conforme."""
    import inspect

    from app.api import allocation_api

    fuente = inspect.getsource(allocation_api.borrar_fila_config)
    assert "_recalc_allocations" not in fuente
    assert "calculate" not in fuente.split('"""')[2]


def test_la_pantalla_borra_en_el_SERVIDOR():
    """Quitar la fila de la lista local y guardar NO la borraría: el guardado
    hace upsert fila por fila y no sabe que una desapareció. Es exactamente lo
    que dejó pegada la `110`."""
    from pathlib import Path

    pagina = (Path(__file__).resolve().parents[2]
              / "frontend/app/allocations/config/page.tsx").read_text(encoding="utf-8")
    assert "borrarFilaReparto(tipo, scenarioId, dept)" in pagina
    assert pagina.count('borrarFila("laundry"') == 1
    assert pagina.count('borrarFila("cafeteria"') == 1
