# -*- coding: utf-8 -*-
"""Planning → Rack Rooms Calculation: las reglas de la puerta.

Lo que se vigila acá NO es «el endpoint contesta 200». Es que las tres cosas
que pueden salir mal **sin que nada avise** sigan cortadas:

1. una temporada que se traslapa con otra → el RAC del mes sale inflado;
2. una comisión fuera de rango → el ingreso en cero o negativo;
3. la pantalla pisando la tarifa derivada → el RAC deja de explicar el ingreso.

Las tres cuadran consigo mismas. Un total que da lo mismo que da es justo lo
que ninguna prueba de integración encuentra.
"""
import inspect
import pathlib
from datetime import date
from decimal import Decimal

import pytest

from app.api import rack_rooms_api as api
from app.engine.rack_tarifa import traslape
from app.errores import MENSAJES

FUENTE = pathlib.Path(api.__file__).read_text(encoding="utf-8")


# ── El traslape de temporadas ────────────────────────────────────────────────
def test_dos_rangos_pegados_no_se_traslapan():
    """31/mar → 1/abr es continuidad, no choque. Es el caso normal del año."""
    assert traslape([(date(2027, 1, 1), date(2027, 3, 31), "PICO"),
                     (date(2027, 4, 1), date(2027, 11, 14), "VERDE")]) is None


def test_un_dia_compartido_es_traslape():
    """El 31 de marzo en las dos: ese día se contaría DOS veces en el RAC."""
    choque = traslape([(date(2027, 1, 1), date(2027, 3, 31), "PICO"),
                       (date(2027, 3, 31), date(2027, 11, 14), "VERDE")])
    assert choque is not None
    a, b, desde = choque
    assert {a, b} == {"PICO", "VERDE"}
    assert desde == date(2027, 3, 31)


def test_la_misma_temporada_en_dos_rangos_es_valida():
    """«Pico» son DOS rangos en 2027: el arranque y el cierre del año."""
    assert traslape([(date(2027, 1, 1), date(2027, 3, 31), "PICO"),
                     (date(2027, 4, 1), date(2027, 11, 14), "VERDE"),
                     (date(2027, 11, 15), date(2027, 12, 31), "PICO")]) is None


def test_el_traslape_se_detecta_en_cualquier_orden():
    """Las filas llegan como las mandó la pantalla, no ordenadas."""
    desordenado = [(date(2027, 6, 1), date(2027, 12, 31), "VERDE"),
                   (date(2027, 1, 1), date(2027, 8, 31), "PICO")]
    assert traslape(desordenado) is not None


def test_un_rango_contenido_en_otro_tambien_choca():
    """Contenido es el peor caso: no corre el borde y se pisa entero."""
    assert traslape([(date(2027, 1, 1), date(2027, 12, 31), "VERDE"),
                     (date(2027, 6, 1), date(2027, 6, 30), "PICO")]) is not None


def test_la_puerta_de_temporadas_usa_la_funcion_del_motor():
    """La regla vive en el motor, no repetida dentro del handler.

    Si mañana alguien agrega otro camino para guardar temporadas —un
    importador, una copia de escenario— tiene que poder llamar a la MISMA
    función. Una copia dentro del endpoint se queda sin actualizar.
    """
    fuente = inspect.getsource(api.guardar_temporadas)
    assert "traslape(" in fuente
    assert "rack.temporadas_traslapadas" in fuente


# ── La comisión ──────────────────────────────────────────────────────────────
def test_la_comision_se_valida_contra_cero_y_uno():
    fuente = inspect.getsource(api.guardar_comisiones)
    assert 'Decimal("0") <= c.comision_pct < Decimal("1")' in fuente
    assert "rack.comision_fuera_de_rango" in fuente


def test_el_mensaje_de_comision_explica_la_escala():
    """«0.20 = 20%» en el texto: el error más probable es mandar 20."""
    assert "0.20" in MENSAJES["rack.comision_fuera_de_rango"]["es"]


# ── La tarifa derivada no se pisa desde la pantalla ──────────────────────────
def test_noches_solo_acepta_tarifa_de_los_segmentos_de_tarifa_propia():
    """Long term no tiene RAC; los demás NO pueden traer tarifa.

    Si la grilla pudiera mandar cualquier tarifa, el ingreso dejaría de salir
    del tarifario y nadie sabría cuál de los dos mandó.
    """
    fuente = inspect.getsource(api.guardar_noches)
    assert "e.segmento_code in propias" in fuente
    assert "RackComision.tarifa_propia.is_(True)" in fuente


def test_todo_put_vuelve_a_derivar():
    """Los cuatro inputs cambian la tarifa; los cuatro tienen que rederivar.

    `canal_rooms_entries` es la tabla ESTÁNDAR: la que lee el motor y, aguas
    abajo, Hotel Consolidation. Un `PUT` que no rederiva deja el consolidado
    mostrando el ingreso de antes del cambio, con el total cuadrando solo.
    """
    for fn in (api.guardar_villas, api.guardar_temporadas,
               api.guardar_comisiones, api.guardar_noches):
        assert "_rederivar(" in inspect.getsource(fn), fn.__name__


def test_el_get_no_escribe():
    """`_ver` deriva para MOSTRAR. Si escribiera, abrir la pantalla de un
    escenario enllavado lo modificaría."""
    for fn in (api._ver, api._armar):
        fuente = inspect.getsource(fn)
        for escribe in ("db.add(", "db.delete(", "db.commit(", "_rederivar("):
            assert escribe not in fuente, f"{fn.__name__}: {escribe}"


def test_rederivar_no_toca_nada_sin_tarifario():
    """Sin villas o sin temporadas el RAC da cero. Escribir ese cero pondría
    todo el ingreso en cero sin que nada avise."""
    fuente = inspect.getsource(api._rederivar)
    assert "if not (villas and temps):" in fuente
    assert "return 0" in fuente


# ── El candado y la guarda ───────────────────────────────────────────────────
def test_todo_lo_que_escribe_pasa_por_el_candado():
    """Un escenario enllavado no se edita por esta puerta tampoco."""
    for fn in (api.guardar_villas, api.guardar_temporadas,
               api.guardar_comisiones, api.guardar_noches, api.conectar):
        assert "await candado(db, scenario_id)" in inspect.getsource(fn), fn.__name__


def test_el_router_se_monta_con_la_guarda():
    from app import main
    linea = next(ln for ln in inspect.getsource(main).splitlines()
                 if "include_router(rack_rooms_router" in ln)
    assert "dependencies=_guard" in linea


# ── El interruptor ───────────────────────────────────────────────────────────
def test_conectar_no_recalcula():
    """Cambiar de modelo no mueve el P&L hasta que el usuario recalcula.

    Es el mismo trato que el resto del sistema: el número cambia cuando alguien
    lo pide, no cuando alguien prendió un interruptor.
    """
    fuente = inspect.getsource(api.conectar)
    assert "recalculate" not in fuente
    assert "canal.recalcular_despues" in fuente


def test_las_fuentes_validas_son_las_del_modelo():
    assert api.FUENTES == ("tarifas", "canales")


# ── Los controles del libro se exponen ───────────────────────────────────────
def test_el_get_expone_los_tres_controles():
    """El libro del owner tiene controles que tienen que dar cero. Si no se
    muestran, el hueco aparece tres meses después en una varianza."""
    fuente = inspect.getsource(api._armar)
    for control in ('"unidades"', '"meses_sin_temporada"',
                    '"segmentos_sin_comision"'):
        assert control in fuente, control


def test_las_disponibles_no_salen_del_tarifario():
    """Las unidades del tarifario ponderan el RAC; NO son el denominador.

    Dos orígenes para las noches disponibles son dos ocupaciones para el mismo
    mes, y ninguna de las dos avisa cuál es.
    """
    assert "_unidades_del_hotel" in inspect.getsource(api._ver)
    assert "unidades_hotel" in inspect.getsource(api._armar)
    fuente = inspect.getsource(api._unidades_del_hotel)
    assert "RoomTypeConfig" in fuente
    assert "RackVilla" not in fuente


def test_el_control_de_unidades_compara_los_dos():
    """No elige una: dice las dos y si coinciden."""
    fuente = inspect.getsource(api._armar)
    assert '"hotel": unidades_hotel' in fuente
    assert '"tarifario": unidades_tarifario' in fuente


# ── Los mensajes existen ─────────────────────────────────────────────────────
@pytest.mark.parametrize("clave", [
    "canal.segmento_desconocido", "canal.noches_negativas",
    "canal.fuente_desconocida", "canal.recalcular_despues",
    "rack.unidades_negativas", "rack.villa_repetida",
    "rack.temporada_desconocida", "rack.rango_invertido",
    "rack.temporadas_traslapadas", "rack.comision_fuera_de_rango",
])
def test_cada_error_tiene_mensaje_en_los_dos_idiomas(clave):
    """Un `ErrorApi` con clave inexistente contesta la clave pelada: el usuario
    lee «rack.villa_repetida» y no entiende nada."""
    assert clave in MENSAJES
    assert MENSAJES[clave]["es"] and MENSAJES[clave]["en"]


def test_las_claves_que_usa_el_codigo_estan_todas_en_el_catalogo():
    """Se leen del fuente: una clave nueva mal escrita no falla en pruebas,
    falla delante del usuario."""
    import re
    usadas = set(re.findall(r'ErrorApi\(\d+,\s*"([a-z_]+\.[a-z_0-9]+)"', FUENTE))
    faltan = sorted(usadas - set(MENSAJES))
    assert not faltan, f"claves sin mensaje: {faltan}"


# ── El catálogo de segmentos no se siembra desde un GET ──────────────────────
def test_la_pantalla_no_siembra_segmentos():
    """La semilla corre en el deploy. Sembrar desde un `GET` haría que la lista
    dependa de quién abrió primero la pantalla."""
    fuente = inspect.getsource(api._segmentos)
    assert "db.add(" not in fuente
    assert "commit" not in fuente

# ── La previsualización ──────────────────────────────────────────────────────
def test_la_previsualizacion_NO_escribe():
    """Una previsualización que guarda es peor que ninguna: el usuario estaría
    editando el presupuesto mientras explora un «¿y si…?»."""
    fuente = inspect.getsource(api.preview)
    for escribe in ("db.add(", "db.delete(", "db.commit(", "db.flush(",
                    "_rederivar("):
        assert escribe not in fuente, escribe


def test_la_previsualizacion_NO_toca_filas_de_la_sesion():
    """Trabaja sobre COPIAS, no sobre las filas de la base.

    La primera versión le cambiaba el campo a la fila real y la expulsaba
    después. Funcionaba, pero dejaba la pantalla a un descuido de volverse un
    guardado silencioso: basta un `return` temprano, una excepción o una rama
    nueva antes del `expunge` para que el cambio viaje en el `commit` de otra
    ruta. Con copias no hay nada que expulsar.
    """
    fuente = inspect.getsource(api.preview)
    assert "_ComisionEnMemoria(" in fuente
    for muta in ("fila.comision_pct =", "fila.tarifa_propia =",
                 "c.comision_pct =", "db.expunge("):
        assert muta not in fuente, muta


def test_la_previsualizacion_usa_el_MISMO_armado_que_el_GET():
    """Si derivara por su cuenta habría dos implementaciones de la fórmula: una
    se corrige y la otra no, y lo que se ve deja de ser lo que se guarda."""
    assert "_armar(" in inspect.getsource(api.preview)
    assert "_armar(" in inspect.getsource(api._ver)


def test_el_armado_no_toca_la_base():
    """`_armar` recibe todo cargado. Es lo que permite calcular sobre filas que
    nunca existieron."""
    fuente = inspect.getsource(api._armar)
    for toca in ("await db", "session.execute", "db.add(", "db.commit("):
        assert toca not in fuente, toca


def test_lo_no_tecleado_entra_como_esta_guardado():
    """Mandar sólo la celda que cambió no puede poner en cero los otros once
    meses."""
    assert "if (code, mes) not in tecleadas" in inspect.getsource(api.preview)


def test_la_previsualizacion_respeta_la_tarifa_propia():
    """Igual que al guardar: la tarifa sólo se toma en los segmentos sin RAC."""
    assert "e.segmento_code in propias" in inspect.getsource(api.preview)

def test_el_cuadro_se_calcula_sobre_lo_DERIVADO():
    """El defecto que esto persigue: el cuadro en CERO con las noches moviéndose.

    `calcular_mes` leía el `ingreso` guardado en la fila. Una fila de
    previsualización todavía no existe en la base, así que no tiene ingreso que
    leer — y el cuadro entero salía en $0,00 mientras las noches subían. Medido
    el 2026-10-16: subir Agencias de 25 a 60 noches en enero movía las noches
    del año de 2.263 a 2.298 y el ingreso a cero.

    También arregla el caso de la base: un `ingreso` guardado de antes del
    último cambio de RAC o de comisión mostraría el ingreso viejo con las
    noches nuevas, cuadrando consigo mismo.
    """
    fuente = inspect.getsource(api._armar)
    assert "if derivado:" in fuente
    assert "calcular_mes(base," in fuente


def test_el_armado_no_muta_las_filas_de_la_base():
    """Se calcula sobre COPIAS. Mutar la fila de la sesión la mandaría a la
    base en el `commit` de cualquier otra ruta — un `GET` que escribe."""
    fuente = inspect.getsource(api._armar)
    assert "_FilaEnMemoria(" in fuente
    for muta in ("f.ingreso =", "f.tarifa =", "fila.ingreso ="):
        assert muta not in fuente, muta
