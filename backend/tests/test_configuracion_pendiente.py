# -*- coding: utf-8 -*-
"""Los pendientes de configuración salen en el Chequeo de la propiedad.

Owner, 2026-09-03: *«guardá esos pendientes en Oxígeno, cuando entre directo me
salgan»*.

Son seis puntos que **no dan error ni descuadran un total**, así que no aparecen
por ningún otro lado: el tipo de cambio que salta entre años, las vistas
escondidas para todos, que nadie tenga perfil de sólo lectura, los parámetros
que existen para unos escenarios y no para otros, y no tener actuales cargados.
"""
import inspect

from app.api import chequeo_api as api


def test_el_chequeo_incluye_la_configuracion_pendiente():
    assert "configuracion" in inspect.getsource(api.chequeo)


def test_se_calcula_contra_la_base_y_NO_es_una_lista_escrita():
    """⚠️ Una lista de pendientes envejece: se arregla el punto, nadie la
    actualiza, y la pantalla sigue pidiendo algo que ya está hecho.

    Preguntando cada vez, el punto desaparece solo el día que se cierra — y
    vuelve solo si alguien lo desconfigura.
    """
    fuente = inspect.getsource(api.chequeo)
    i = fuente.index("faltas: list[str] = []")
    bloque = fuente[i:i + 4000]
    for tabla in ("exchange_rates", "tab_enablement", "users",
                  "payroll_params", "actual_entries"):
        assert tabla in bloque, (
            f"el pendiente de {tabla} dejó de mirarse contra la base")


def test_las_vistas_escondidas_se_cuentan_solo_las_de_TODOS():
    """Una vista apagada para UN perfil es una decisión, no un pendiente.
    El centinela del perfil «para todos» es la cadena vacía, no NULL."""
    fuente = inspect.getsource(api.chequeo)
    assert "coalesce(perfil, '') = ''" in fuente


def test_los_textos_estan_en_los_dos_idiomas():
    from app.textos import TEXTOS
    for clave in ("chequeo.config_titulo", "chequeo.config_hay",
                  "chequeo.config_ok", "chequeo.config_porque",
                  "chequeo.config_tc", "chequeo.config_vistas",
                  "chequeo.config_viewer", "chequeo.config_params",
                  "chequeo.config_actuales"):
        assert clave in TEXTOS, clave
        assert TEXTOS[clave].get("es") and TEXTOS[clave].get("en"), clave
