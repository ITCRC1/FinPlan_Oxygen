# -*- coding: utf-8 -*-
"""Los socios del Club se pueden subir por la plantilla del Detalle.

Owner, 2026-09-08: *«la estadística también debe traer total membresías,
membresías condicionados, membresías pagando y membresías en acuerdo de pago;
el upload debe tener estas líneas para poder subir estas estadísticas»*.

Antes existían la tabla (`ClubMembershipStat`) y la pantalla, pero no había
cómo cargarlos con el archivo mensual: la plantilla no ofrecía las filas y el
importador no las reconocía. Los cuatro conteos quedaban en cero.
"""
import inspect
import json
import pathlib

CATALOGO = (pathlib.Path(__file__).resolve().parents[1]
            / "app" / "seed_data" / "stats_catalog.json")


def _catalogo():
    return json.loads(CATALOGO.read_text(encoding="utf-8"))["cuentas"]


def test_las_cuatro_estan_en_el_catalogo():
    codigos = {c["code"]: c for c in _catalogo()}
    for code in ("9800", "9801", "9802", "9803"):
        assert code in codigos, f"falta la cuenta estadística {code}"
        assert codigos[code]["grupo"] == "9800"


def test_el_total_del_anio_NO_es_la_suma_de_los_meses():
    """⚠️ Son socios, no ingresos.

    El saldo de diciembre ES el total del año. Sumar los doce meses daría 1.500
    socios donde hay 129 — por eso `agrega` es FIN y no SUM, igual que el
    headcount. Ver `models/club_membership_stat.py`.
    """
    for c in _catalogo():
        if c["grupo"] == "9800":
            assert c["agrega"] == "FIN", (
                f"{c['code']} agrega como {c['agrega']}: el total del año "
                f"volvería a ser la suma de los doce meses")


def test_el_importador_las_manda_a_su_propia_tabla():
    """No van a `ScenarioStat` con las de habitaciones: son otra tabla."""
    from app.importers import gl_detail_importer as gl

    assert set(gl.MEMBRESIA_BY_ACCT) == {"9800", "9801", "9802", "9803"}
    assert set(gl.MEMBRESIA_BY_ACCT.values()) == {
        "total", "condicionados", "pagando", "acuerdo_pago"}
    # Y que las recoja de verdad, no solo que exista el mapa.
    assert 'blk["membresias"]' in inspect.getsource(gl)


def test_al_subir_se_escriben_en_ClubMembershipStat():
    from app.api import scenarios_api

    src = inspect.getsource(scenarios_api)
    assert "db.add(ClubMembershipStat(" in src, (
        "el importador dejó de escribir los socios: la plantilla los ofrece y "
        "el archivo los trae, pero no llegan a la base")


def test_solo_se_borra_el_mes_que_el_archivo_trae():
    """⚠️ Un archivo sin las líneas de socios NO puede dejar en cero un conteo
    que ya estaba. Es el mismo criterio que el merge usa para todo lo demás."""
    src = inspect.getsource(__import__(
        "app.api.scenarios_api", fromlist=["x"]))
    i = src.index("db.add(ClubMembershipStat(")
    bloque = src[max(0, i - 1200):i]
    assert "ClubMembershipStat.month.in_(meses_socios)" in bloque
    assert "if membresias:" in bloque


def test_las_filas_solo_salen_si_el_club_esta_habilitado():
    """El owner avisó que el Club se va cuando se opere por fuera del hotel.

    Ese día se desmarca en Provisionamiento y estas cuatro filas desaparecen
    solas. Por eso la condición NO es un `if hotel == "AMA"`.
    """
    from app.api import scenarios_api
    from app.export import detail_excel

    assert len(detail_excel.MEMBRESIA_ROWS) == 4
    src = inspect.getsource(scenarios_api.export_scenario_detail)
    assert "DeptEnablement" in src and '"260"' in src, (
        "las filas de socios dejaron de mirar si el Club está habilitado")
    assert 'HOTEL_ID == "AMA"' not in src
