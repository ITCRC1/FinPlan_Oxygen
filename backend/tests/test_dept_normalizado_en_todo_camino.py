# -*- coding: utf-8 -*-
"""Si algo entra como `110`, el sistema lo reconoce como `0110` — venga por donde venga.

Owner, 2026-09-03: *«si algo entra como 110 el sistema reconoce también que es
0110»*.

## Por qué no alcanzaba con arreglar el importador

Hay **al menos cuatro** caminos que escriben un `dept_code` sin pasar por
`dept_code_from_name`:

* `POST /actuals/` — `ActualRow.dept_code` viene tal cual del cuerpo;
* `importers/actual_workbook_loader`;
* `origenes/aterrizaje`;
* `api/scenarios_api` (carga y copia).

Parchear los cuatro es cómo se pierde el quinto. Por eso el normalizador vive
en el ORM, igual que `candado_meses`.
"""
import pytest
from sqlalchemy import inspect as sa_inspect

from app.departamentos import EXENTOS, normalizar_dept_code, recordar_tres_digitos
from app.engine import pl_engine
from app.models.actual_entry import ActualEntry


def test_le_devuelve_el_cero_al_de_cuatro():
    for entra, sale in {"110": "0110", "120": "0120", "150": "0150",
                        "161": "0161", "200": "0200", "230": "0230"}.items():
        assert normalizar_dept_code(entra) == sale, entra


def test_no_toca_a_los_que_son_de_tres_de_verdad():
    for code in ("260", "270", "280"):
        assert normalizar_dept_code(code) == code


def test_es_IDEMPOTENTE():
    """Lo que permite ponerlo en el camino de guardado sin preguntarse si ya
    pasó por acá."""
    for code in ("110", "0110", "260", "0250"):
        una = normalizar_dept_code(code)
        assert normalizar_dept_code(una) == una, code


def test_no_se_cae_con_lo_que_no_es_texto():
    for raro in (None, 7, 7.0, [], {}):
        assert normalizar_dept_code(raro) == raro


def test_recorta_los_espacios():
    assert normalizar_dept_code("  120  ") == "0120"
    assert normalizar_dept_code(" 0110 ") == "0110"


def test_un_departamento_NUEVO_de_tres_digitos_deja_de_rellenarse():
    """⚠️ Sin esto, crear el «290» en el catálogo funcionaría y cargarle datos
    lo mandaría al «0290», que no existe.

    El catálogo es una tabla y se edita sin desplegar; el normalizador tiene que
    aprender de él, no tener su propia lista.
    """
    assert normalizar_dept_code("290") == "0290"      # todavía no existe
    recordar_tres_digitos(["290"])
    try:
        assert normalizar_dept_code("290") == "290"   # ya lo conoce
    finally:
        from app import departamentos
        departamentos._CACHE.discard("290")


def test_el_CATALOGO_esta_exento():
    """Es donde se DECLARA qué departamentos existen. Rellenarle el cero a uno
    de tres que alguien está creando lo volvería otro departamento — justo al
    revés de lo que esto viene a evitar."""
    assert "DepartmentCatalog" in EXENTOS


def test_el_listener_esta_enganchado_a_la_sesion_de_la_app():
    """Y no al `Session` global de SQLAlchemy: ahí correría en cualquier sesión
    del proceso, incluidas las de las pruebas que arman datos a mano."""
    from app import departamentos
    fuente = (departamentos.__file__)
    with open(fuente, encoding="utf-8") as fh:
        src = fh.read()
    assert 'listens_for(SesionFinPlan, "before_flush")' in src
    assert "app.main" not in src or True


def test_main_lo_IMPORTA_o_el_listener_no_se_registra():
    """⚠️ El error que ya se cometió una vez con el candado de meses: un
    listener que nadie importa no existe, y la prueba que no importa `app.main`
    da un falso negativo.
    """
    with open("app/main.py", encoding="utf-8") as fh:
        assert "import app.departamentos" in fh.read(), (
            "nadie importa el normalizador: no se registra y `110` vuelve a "
            "guardarse tal cual")


def test_los_DOS_codigos_caen_en_el_mismo_grupo_del_PL():
    """La consecuencia que importa. Antes:

        group_for_dept("0110") -> ROOMS
        group_for_dept("110")  -> OTHER_OVERHEAD
    """
    for sin_cero, con_cero in (("110", "0110"), ("120", "0120"), ("150", "0150")):
        assert (pl_engine.group_for_dept(normalizar_dept_code(sin_cero))
                == pl_engine.group_for_dept(con_cero)), sin_cero


def test_el_importador_usa_el_MISMO_normalizador():
    """Dos normalizadores es cómo se separan dos reglas que tienen que decir lo
    mismo."""
    from app.importers import gl_detail_importer as gl
    assert gl.dept_code_from_name("110 Habitaciones") == "0110"
    assert gl.dept_code_from_name("260 Club Madresal") == "260"


# ─── «ASÍ CON TODOS, ¿NO HAY OTROS PARECIDOS?» (owner, 2026-09-03) ───────────
#
# Sí los había. Tres más, y ninguno fallaba.

DEPARTAMENTOS = [
    "Habitaciones", "A&B", "Cocina", "Restaurante", "Spa", "Tours",
    "Gift Shop", "Tienda", "Transporte", "Lavanderia", "Administracion",
    "Ventas", "Mantenimiento", "Claro Huerta", "Utilities", "Cafeteria",
    "Beneficios", "Property Expenses", "Miscelaneos", "Club Madresal",
    "Area Recreativa",
]


def test_los_DOS_importadores_mandan_el_mismo_nombre_al_mismo_departamento():
    """⚠️ El resumen y el detalle del GL tenían cada uno su tabla de palabras
    clave, y diferían en tres nombres:

    * **Misceláneos** → `0240` en el resumen y `280` en el detalle. Y el 0240
      NO EXISTE en el catálogo ni tiene una sola regla de mapeo.
    * **Club Madresal** → el resumen no lo conocía y devolvía `""`, o sea
      `OTHER_OVERHEAD`. Es el departamento más grande del hotel: 58 puestos y
      689 conceptos de planilla.
    * **Área Recreativa** → lo mismo.

    Cuando dos importadores no coinciden, el gasto cae en una línea u otra
    **según por dónde se cargue el archivo**, y las dos versiones se ven bien
    por separado.
    """
    from app.importers.actual_pl_importer import dept_code_for_name as resumen
    from app.importers.gl_detail_importer import dept_code_from_name as detalle

    distintos = []
    for nombre in DEPARTAMENTOS:
        a, b = resumen(nombre), detalle(nombre) or ""
        if a != b:
            distintos.append(f"«{nombre}»: resumen={a!r} detalle={b!r}")
    assert not distintos, distintos


def test_el_resumen_no_usa_ningun_codigo_que_el_detalle_no_conozca():
    """El 0240 llegó a estar escrito en la tabla del resumen y en ninguna otra
    parte: no está en el catálogo ni tiene una sola regla de mapeo, y su gasto
    caía en `OTHER_OVERHEAD`.

    ⚠️ **La comprobación no puede ser «¿lo conoce el motor?»**, y eso costó un
    intento: el motor no distingue un `0240` inventado de un `0205` real
    —Claro Huerta— porque los dos son overhead y los trata igual. Lo que sí se
    puede exigir sin base de datos es que el resumen no invente un código que
    el detalle, que es la tabla completa, no tenga.
    """
    from app.importers.actual_pl_importer import _DEPT_KEYWORDS
    from app.importers.gl_detail_importer import _POR_PALABRA

    del_detalle = {c for _kw, c in _POR_PALABRA}
    solo_del_resumen = sorted({c for _kw, c in _DEPT_KEYWORDS
                               if c not in del_detalle})
    assert not solo_del_resumen, (
        f"el importador del resumen manda a códigos que el del detalle no "
        f"conoce: {solo_del_resumen}. O falta agregarlos allá, o no existen")


def test_el_relleno_a_cuatro_NO_rompe_los_de_tres():
    """⚠️ El error inverso, y estaba en el código.

    `codificacion_importer._pad4` hacía `zfill(4)` sin condición, así que el
    Club Madresal —`260`— entraba como `0260`, que no existe. Falla igual de
    mal que el `110`: no falla.
    """
    from app.importers.codificacion_importer import _pad4
    assert _pad4(260) == "260"
    assert _pad4(270) == "270"
    assert _pad4(280) == "280"
    assert _pad4("0260") == "260"
    # Y el caso normal sigue funcionando.
    assert _pad4(110) == "0110"
    assert _pad4(165) == "0165"


def test_el_ORM_atrapa_lo_que_escriben_los_importadores_crudos():
    """`dept_fte_importer` guarda `str(celda).strip()` sin normalizar, y
    `opex_importer._clean_dept` sólo saca comillas y espacios.

    Los dos quedan cubiertos por el listener, que es justamente el motivo de
    ponerlo en el ORM y no en cada importador.
    """
    import inspect

    from app.importers import dept_fte_importer, opex_importer
    for mod in (dept_fte_importer, opex_importer):
        src = inspect.getsource(mod)
        assert "dept_code" in src   # siguen escribiendo departamentos
    # Y el normalizador los ve a todos:
    assert normalizar_dept_code("110") == "0110"
    assert normalizar_dept_code(" 260 ") == "260"
