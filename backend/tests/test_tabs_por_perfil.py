# -*- coding: utf-8 -*-
"""Las vistas limitadas **por perfil**, y las tres formas de romperlas.

Owner, 2026-08-26: *«con vistas limitadas por perfil»*.

Lo que se blinda acá no es que la consulta corra —eso lo dice cualquier prueba—
sino las tres decisiones que, si alguien las deshace sin darse cuenta, fallan
**en silencio**: el centinela, la unión, y la diferencia entre «no vino perfil» y
«vino vacío».
"""
import inspect

from app.api import _apagados, provisioning_api
from app.models.tab_enablement import TabEnablement


def test_el_centinela_es_vacio_y_no_NULL():
    """⚠️ En Postgres **dos NULL no chocan en un UNIQUE**.

    Con la columna nullable, la misma clave se podría apagar dos veces «para
    todos» y la tabla dejaría de tener una fila por decisión. Nada lo avisaría:
    la pantalla mostraría lo mismo y la basura se acumularía sola.
    """
    col = TabEnablement.__table__.c.perfil
    assert col.nullable is False, (
        "`perfil` quedó nullable: el UNIQUE deja de impedir duplicados «para "
        "todos», porque dos NULL no chocan en Postgres")
    assert col.default.arg == ""


def test_el_UNIQUE_incluye_el_perfil():
    """Sin esto no se puede apagar la misma clave para dos perfiles distintos."""
    uq = next(c for c in TabEnablement.__table__.constraints
              if getattr(c, "name", "") == "uq_tab_enablement")
    assert {c.name for c in uq.columns} == {
        "hotel_id", "scope_kind", "clave", "perfil"}


def test_la_lectura_es_UNION_y_no_reemplazo():
    """La propiedad manda sobre el perfil.

    Si un perfil pudiera *prender* lo que la propiedad apagó, una decisión
    chica contradiría a una grande: «esta propiedad no hace Break-Even» dejaría
    de ser cierto para quien tuviera una fila propia.
    """
    fuente = inspect.getsource(_apagados.tabs_apagados)
    assert 'quienes = {""} | ' in fuente, (
        "la lectura dejó de incluir las filas de la propiedad: un perfil con "
        "filas propias empezaría a VER lo que la propiedad apagó")
    assert ".in_(quienes)" in fuente


def test_el_perfil_vacio_no_agrega_nada():
    """`""` y `None` tienen que dar lo mismo: es el mismo centinela.

    Tratarlos distinto haría que un rol vacío pidiera la unión con una fila que
    no existe — y devolvería un conjunto que no es de nadie.
    """
    fuente = inspect.getsource(_apagados.tabs_apagados)
    assert '({perfil} if perfil else set())' in fuente


def test_no_vino_perfil_NO_es_lo_mismo_que_vino_vacio():
    """La diferencia que evita que la pantalla se edite a sí misma.

    Sin ella, un admin que abre `/admin/tabs` recibe SU vista y cree que es la
    de la propiedad: apagaría algo «para todos» partiendo de un estado que sólo
    era suyo.
    """
    fuente = inspect.getsource(provisioning_api.leer_tabs)
    assert "perfil: str | None = None" in fuente
    assert "usuario.role if perfil is None else perfil" in fuente


def test_al_guardar_se_filtra_por_el_perfil_editado():
    """⚠️ Si el filtro no llevara el perfil, apagar algo para lectores borraría
    la fila global con el mismo nombre — la decisión de la propiedad se
    perdería desde una pantalla que dice estar tocando un perfil."""
    fuente = inspect.getsource(provisioning_api.guardar_tabs)
    assert "TabEnablement.perfil == perfil" in fuente
    assert "perfil=perfil" in fuente, (
        "la fila nueva se guarda sin perfil: quedaría apagado para todos")


def test_el_perfil_que_llega_se_valida():
    """Un rol inventado guardaría filas que nadie va a leer nunca."""
    fuente = inspect.getsource(provisioning_api.guardar_tabs)
    assert "perfil not in ROLES" in fuente


def test_la_barra_solo_se_repinta_con_la_matriz_de_la_propiedad():
    """Avisar siempre haría que un admin configurando la vista del lector viera
    SU barra esconderse — un cambio que además es mentira: al recargar vuelve."""
    from pathlib import Path

    fuente = Path(__file__).resolve().parents[2].joinpath(
        "frontend/lib/tabsVisibles.ts").read_text(encoding="utf-8")
    assert "if (!perfil) suscriptores.forEach" in fuente
