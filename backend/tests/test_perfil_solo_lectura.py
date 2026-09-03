# -*- coding: utf-8 -*-
"""El perfil `viewer` ve todo y no escribe nada.

Owner, 2026-08-26: *«sería por perfil: editor, view»*.

Son pruebas **estructurales**: leen el código fuente en vez de levantar la app.
La razón es la misma que en las demás guardas del repo — lo que hay que blindar
no es «este endpoint contesta 403» sino **«la guarda sigue enganchada en la
única puerta»**. Una prueba de integración pasa igual el día que alguien monte
un router nuevo sin `_guard`; ésta no.
"""
import inspect

from fastapi import FastAPI

from app import main, perfiles
from app.models.user import ROLES


def test_viewer_es_un_rol_asignable():
    """Sin esto, crear el usuario devolvería 422 y el perfil no existiría."""
    assert "viewer" in ROLES
    assert "viewer" in perfiles.PERFILES_SIN_ESCRITURA


def test_la_guarda_esta_en_la_unica_puerta():
    """`solo_lectura` tiene que ir en `_guard`, no repartido por endpoint.

    Es la misma lección del candado del escenario: 197 `if` sueltos son 197
    oportunidades de olvidarse, y el olvido **deja escribir** en vez de fallar.
    """
    fuente = inspect.getsource(main)
    assert "Depends(solo_lectura)" in fuente, (
        "la guarda de sólo lectura salió de _guard: un `viewer` volvería a "
        "poder editar planilla, subir actuales y recalcular")


def test_todo_router_de_datos_lleva_la_guarda_completa():
    """Ningún router de datos puede montarse sin `_guard`.

    Se cuenta sobre el fuente y no sobre `app.routes` porque lo que importa es
    cómo se monta, no qué rutas quedaron: un `include_router` sin
    `dependencies=_guard` es exactamente el agujero que esto vigila.
    """
    fuente = inspect.getsource(main)
    sin_guarda = [
        ln.strip() for ln in fuente.splitlines()
        if ln.strip().startswith("app.include_router(")
        and "dependencies=_guard" not in ln
    ]
    # Los públicos a propósito: login, el consolidado (tiene su propia llave)
    # y los que declaran su guarda aparte.
    permitidos = ("auth_router", "consolidado_router")
    for ln in sin_guarda:
        assert any(p in ln for p in permitidos), (
            f"router montado sin _guard y no está en la lista de públicos: {ln}")


def test_no_frena_las_lecturas():
    """`GET` y `HEAD` nunca se bloquean: un lector tiene que poder leer."""
    assert "GET" not in perfiles.ESCRITURA
    assert "HEAD" not in perfiles.ESCRITURA
    assert perfiles.ESCRITURA == {"POST", "PUT", "PATCH", "DELETE"}


def test_las_preferencias_de_la_persona_quedan_fuera():
    """Idioma y paleta son del usuario, no del libro contable.

    Cuelgan de `auth_router`, que va sin `_guard`. Si algún día se mudaran a un
    router con guarda, un `viewer` no podría cambiar su propio idioma — y ésta
    es la prueba que lo diría.
    """
    fuente = inspect.getsource(main)
    linea = next(ln for ln in fuente.splitlines()
                 if "include_router(auth_router" in ln)
    assert "dependencies=_guard" not in linea


def test_el_403_dice_cual_es_el_perfil():
    """Un 403 pelado manda a leer logs. El mensaje nombra el perfil."""
    from app.errores import MENSAJES

    assert "auth.solo_lectura" in MENSAJES
    for idioma in ("es", "en"):
        assert "{perfil}" in MENSAJES["auth.solo_lectura"][idioma]


def test_el_admin_no_se_toco():
    """Agregar un perfil no puede ampliar quién administra.

    Misma regla que con `guillermo_approver`: un rol nuevo NO hereda los
    endpoints de administración por estar en la lista.
    """
    from app.auth import get_current_admin

    assert '!= "admin"' in inspect.getsource(get_current_admin)


# ── Las excepciones: POST que no escriben ────────────────────────────────────
#
# Un lector tiene que poder bajar un Excel y cotizar un grupo. Las tres rutas
# son `POST` sólo porque el cuadro (o la cotización) no cabe en una URL.


def test_las_rutas_exentas_EXISTEN():
    """Una ruta exenta mal escrita no falla: simplemente no exime, y el lector
    se queda sin poder bajar reportes sin que nadie entienda por qué.

    Se arman desde los routers y no desde `app.routes` porque esta versión de
    FastAPI monta los routers de forma perezosa (`_IncludedRouter`) y las rutas
    concretas no existen hasta que entra una petición.
    """
    from app.api.costos_grupos_sim_api import router as sim
    from app.api.export_api import router as exp

    reales = {"/api" + r.path for r in list(exp.routes) + list(sim.routes)}
    assert not (perfiles.SIN_EFECTO - reales), (
        f"rutas exentas que no existen: "
        f"{sorted(perfiles.SIN_EFECTO - reales)}")


def test_toda_ruta_exenta_es_un_POST_que_no_escribe():
    """⚠️ El criterio no admite matices: el endpoint NO puede tocar la base.

    Se verifica leyendo el fuente: si alguna de estas funciones empieza a
    `db.add`, `db.delete` o `db.commit`, deja de ser una lectura disfrazada y
    la exención se vuelve un agujero que ninguna prueba de permisos encuentra
    —desde afuera se ve idéntica a un `GET`—.
    """
    from app.api import costos_grupos_sim_api, export_api

    for mod in (export_api, costos_grupos_sim_api):
        for nombre, fn in vars(mod).items():
            if not callable(fn) or nombre.startswith("_"):
                continue
            try:
                fuente = inspect.getsource(fn)
            except (TypeError, OSError):
                continue
            if "@router.post" not in fuente:
                continue
            for escribe in ("db.add(", "db.delete(", "db.commit(",
                            "session.add(", "await db.merge("):
                assert escribe not in fuente, (
                    f"{mod.__name__}.{nombre} está exento de la guarda de "
                    f"sólo lectura pero escribe ({escribe}): un `viewer` "
                    f"podría modificar datos")


def test_la_exencion_se_compara_contra_la_PLANTILLA_de_la_ruta():
    """`request.url.path` trae los ids ya resueltos y se puede engañar con un
    `startswith`. La plantilla es la del router — misma lección que el candado."""
    fuente = inspect.getsource(perfiles.solo_lectura)
    assert 'request.scope.get("route")' in fuente
    assert "in SIN_EFECTO" in fuente


def test_la_lista_de_exentas_es_CORTA():
    """No es una prueba de estilo: cada excepción es un endpoint que un lector
    puede llamar. Si la lista crece, es que se está usando para tapar un
    problema de diseño y no para nombrar tres casos reales."""
    assert len(perfiles.SIN_EFECTO) <= 5, (
        "la lista de exentas creció: revisá si esos endpoints de verdad no "
        "escriben, o si hace falta otro mecanismo")
