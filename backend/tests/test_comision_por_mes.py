# -*- coding: utf-8 -*-
"""La comisión por mes, y la réplica desde enero.

Owner, 2026-10-16: *«pone el primer mes y se replica a los 12 meses y manual se
cambia el mes que probablemente cambie»*.

## Lo que esto vigila

Una réplica que pisa el cambio manual es **pérdida de datos sin aviso**: no
falla, no avisa, y el total del año sigue cuadrando consigo mismo. Es el modo
de falla que esta pantalla no puede tener.
"""
import inspect
from decimal import Decimal

from app.api.rack_rooms_api import (comisiones_del_mes, replicar_desde_enero,
                                    _ComisionEnMemoria)

D = Decimal


# ── La réplica ───────────────────────────────────────────────────────────────
def test_enero_se_replica_a_los_doce():
    """El caso de arranque: no hay nada cargado y se escribe enero."""
    out = replicar_desde_enero({}, D("0.25"))
    assert out == {m: D("0.25") for m in range(1, 13)}


def test_enero_arrastra_a_los_que_seguian_a_enero():
    actual = {m: D("0.25") for m in range(1, 13)}
    out = replicar_desde_enero(actual, D("0.26"))
    assert set(out.values()) == {D("0.26")}


def test_la_replica_NO_pisa_el_mes_cambiado_a_mano():
    """El caso que motivó la regla, tal cual pasa:

    enero en 25 %, julio corregido a 28 % porque la agencia subió, y después
    enero se toca otra vez —a 26 %— por otra razón. Julio tiene que quedarse
    en 28 %.
    """
    actual = {m: D("0.25") for m in range(1, 13)}
    actual[7] = D("0.28")
    out = replicar_desde_enero(actual, D("0.26"))
    assert out[7] == D("0.28"), "la réplica pisó el cambio manual"
    assert out[1] == D("0.26")
    assert out[6] == D("0.26")
    assert out[12] == D("0.26")


def test_varios_meses_a_mano_sobreviven():
    actual = {m: D("0.25") for m in range(1, 13)}
    actual[3], actual[7], actual[11] = D("0.30"), D("0.28"), D("0.20")
    out = replicar_desde_enero(actual, D("0.26"))
    assert (out[3], out[7], out[11]) == (D("0.30"), D("0.28"), D("0.20"))
    assert out[2] == D("0.26")


def test_un_mes_que_coincide_por_casualidad_se_arrastra():
    """⚠️ Límite conocido y aceptado: si alguien puso julio en el MISMO valor
    que enero, la réplica no puede distinguirlo de un mes que nunca se tocó —
    no hay nada en el dato que diga cuál fue a mano.

    Se documenta en vez de inventar una marca de «tocado a mano»: esa marca se
    desincroniza sola el día que alguien edite por otra vía (la plantilla de
    Excel, una copia de escenario) y entonces miente.
    """
    actual = {m: D("0.25") for m in range(1, 13)}
    out = replicar_desde_enero(actual, D("0.26"))
    assert out[7] == D("0.26")


def test_la_replica_es_PURA():
    """No muta lo que recibe: la usan el guardado y la previsualización, y la
    previsualización no puede dejar rastro."""
    actual = {1: D("0.25"), 2: D("0.25")}
    copia = dict(actual)
    replicar_desde_enero(actual, D("0.30"))
    assert actual == copia


def test_el_guardado_y_la_previsualizacion_usan_la_MISMA_regla():
    """Si la pantalla mostrara una réplica y el botón hiciera otra, lo que se
    ve no sería lo que se guarda."""
    from app.api import rack_rooms_api as api
    assert "replicar_desde_enero(" in inspect.getsource(api.guardar_comisiones)
    assert "replicar_desde_enero(" in inspect.getsource(api.preview)


# ── Leer la comisión del mes ─────────────────────────────────────────────────
def _filas(pcts: dict[int, str], code="OTA", propia=False):
    return [_ComisionEnMemoria(code, m, D(v), propia) for m, v in pcts.items()]


def test_cada_mes_lee_SU_comision():
    """Usar la de enero para los doce devolvería el ingreso del año a la
    tarifa de enero, sin error y con el total cuadrando solo."""
    filas = _filas({m: ("0.25" if m <= 6 else "0.28") for m in range(1, 13)})
    assert comisiones_del_mes(filas, 1)["OTA"][0] == D("0.25")
    assert comisiones_del_mes(filas, 7)["OTA"][0] == D("0.28")


def test_un_mes_sin_fila_vende_A_RACK():
    """⚠️ La ausencia es 0 % de comisión, no 100 %. Tratarla como 100 % pondría
    el ingreso de ese mes en cero sin que nada avise."""
    filas = _filas({1: "0.25"})
    assert comisiones_del_mes(filas, 5) == {}
    # Y el motor, al no encontrarlo, usa 0 % — ver `tarifa_del_segmento`.


def test_la_tarifa_propia_es_del_SEGMENTO_no_del_mes():
    """*Long term* no tiene RAC en enero y sí en julio."""
    filas = _filas({1: "0"}, code="LONG_TERM", propia=True)
    for mes in (1, 7, 12):
        d = comisiones_del_mes(filas, mes)
        assert d["LONG_TERM"][1] is True, f"mes {mes}"


def test_el_de_tarifa_propia_aparece_aunque_no_tenga_fila_ese_mes():
    """Si faltara, el motor lo trataría como un segmento de rack normal y le
    inventaría una tarifa que no tiene."""
    filas = _filas({1: "0"}, code="LONG_TERM", propia=True)
    assert "LONG_TERM" in comisiones_del_mes(filas, 9)


def test_el_guardado_escribe_tarifa_propia_en_los_doce():
    """Doce filas que no coinciden darían distinto según el mes que se mire."""
    from app.api import rack_rooms_api as api
    fuente = inspect.getsource(api.guardar_comisiones)
    assert "for mes in MESES:" in fuente
    assert "tarifa_propia = c.tarifa_propia" in fuente


# ── El motor ─────────────────────────────────────────────────────────────────
def test_el_motor_pide_la_comision_del_mes():
    """`aplicar_canales_rooms` recorre los doce meses: si tomara la de enero
    para todos, el P&L del año saldría con la tarifa de enero."""
    from app.engine import recalculate
    fuente = inspect.getsource(recalculate.aplicar_canales_rooms)
    assert "comisiones_del_mes(filas_com, mes)" in fuente


def test_la_migracion_expande_a_los_doce():
    """Dejar meses sin fila daría el mismo total HOY —la ausencia es 0 %— pero
    el P&L se movería solo en cuanto alguien recalculara."""
    import pathlib
    from tests._rutas import BACKEND

    mig = (BACKEND / "alembic" / "versions" / "145_comision_por_mes.py"
           ).read_text(encoding="utf-8")
    assert "for mes in range(2, 13)" in mig
    assert "INSERT INTO" in mig
