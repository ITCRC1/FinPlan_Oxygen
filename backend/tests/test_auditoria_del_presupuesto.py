# -*- coding: utf-8 -*-
"""Auditar un presupuesto, no sólo los actuales.

Owner, 2026-09-03, mirando el BUDGET 2027 de Oxygen: *«hay tab que no tienen
información, algo está pasando con el GL, favor corregir todo eso»*.

Y antes, sobre el mismo tema: *«el presupuesto debe tener gl, siempre debe
estar conectado a un gl»*.

La Auditoría leía sólo `actual_entries`, así que sobre cualquier presupuesto
—en Amarena también, no era del port— devolvía cero filas. Pero el dato estaba:
en el BUDGET 2027, las 140 líneas de opex y costo tienen `account_code` sin un
solo nulo. Lo que faltaba no era el dato, era leerlo.

Medido contra producción cargando el módulo desde `/tmp`, sin tocar lo
desplegado: junio pasó de 0 filas a 254 —Ingresos 3, Opex 153, Payroll 81,
Costo 5, Reparto 2, Bajo GOP 10— y de 60 renglones, **0 descuadran**.
"""
import inspect

from app.api import auditoria_api as api
from app.engine import pl_engine


def test_sin_mayor_se_auditan_los_checkbooks():
    fuente = inspect.getsource(api.auditoria_del_mes)
    assert "_asientos_del_checkbook" in fuente, (
        "un presupuesto volvió a quedarse sin detalle: la Auditoría sólo mira "
        "el mayor otra vez")


def test_se_reusa_la_lectura_del_checkbook_y_no_una_copia():
    """⚠️ `_del_auxiliar` ya resuelve la cadena de departamentos padre, el
    reparto por mes y los conceptos de planilla como cuentas. Una segunda
    lectura acá terminaría diciendo algo distinto sobre el mismo checkbook."""
    assert "_del_auxiliar" in inspect.getsource(api._asientos_del_checkbook)


def test_el_ingreso_se_traduce_con_la_tabla_del_motor():
    """⚠️ Y NO pegando `"REV_" + grupo`, que es lo que se probó primero.

    El grupo `ACTIVITIES` alimenta la línea `REV_TOURS`: la concatenación
    producía `REV_ACTIVITIES`, un renglón que el reporte no dibuja, y los
    10.800 del año quedaban huérfanos. Se midió: empeoró el cuadre en vez de
    arreglarlo.
    """
    fuente = inspect.getsource(api._asientos_del_checkbook)
    assert "REVENUE_LINE_TO_REPORT_LINE" in fuente
    # La traducción que la concatenación no acierta.
    assert pl_engine.REVENUE_LINE_TO_REPORT_LINE["activities"] == "REV_TOURS"


def test_el_ingreso_del_presupuesto_no_se_cuenta_como_estadistica():
    """El ingreso llega con el grupo como llave, no con una 4xxx.
    `linea_de_fila` mira el primer dígito, y una línea no tiene dígito."""
    linea, tipo = pl_engine.linea_de_fila("ROOMS", "0110")
    assert linea is None and not tipo, (
        "si esto empieza a resolver, la fila propia del asiento sintético "
        "dejó de hacer falta y hay que revisar cuál de las dos manda")
    assert "linea_propia" in inspect.getsource(api._AsientoDeCheckbook)


def test_se_dice_que_el_detalle_no_viene_del_mayor():
    """Un presupuesto no lo contabilizó nadie: es la cuenta con la que se
    planeó. Mostrarlo sin aclararlo lo haría pasar por contabilidad."""
    fuente = inspect.getsource(api.auditoria_del_mes)
    assert "no del mayor" in fuente


def test_avisa_cuando_una_fila_llega_por_descarte():
    """⚠️ Lo que se escondió una vez se esconde otra si nadie mira.

    En el BUDGET 2027, `0150`/`7310` —el reparto de lavandería a Tour
    Activities— no tenía regla en `account_mapping`. El resolvedor cae a una
    regla genérica, y ese descarte terminaba en OPEX_ROOMS: 1.361,29 al año de
    gasto de Tours cargados a Habitaciones.

    **No daba error y el GOP cuadraba igual**, porque reclasificar entre dos
    renglones no mueve ningún total. Apareció sólo porque la auditoría cruzó
    el detalle contra el motor.
    """
    fuente = inspect.getsource(api.auditoria_del_mes)
    assert "_sin_regla_propia" in fuente, (
        "se quitó el aviso de descarte: el próximo mapeo que falte va a mover "
        "plata de departamento sin que nada lo diga")


def test_le_pregunta_al_MISMO_resolvedor_que_usa_el_pl():
    """Mirar si la fila existe en la tabla no alcanza: el orden de precedencia
    —exacta, padre, sin-departamento, descarte— es lo que decide de verdad
    adónde va la plata, y sólo el resolvedor lo sabe."""
    fuente = inspect.getsource(api._sin_regla_propia)
    assert "construir_resolvedor" in fuente
    assert '"FALLBACK"' in fuente


def test_cuenta_tambien_los_DROP_no_solo_los_descartes():
    """⚠️ Son dos formas distintas de perderse, y la segunda es peor.

    `FALLBACK` manda la plata al renglón equivocado; `DROP` —la cuenta no está
    en el mapeo para NINGÚN departamento— hace que no llegue a ninguno.

    Se encontró probando la función contra producción con una cuenta inventada
    (`7999`): no salía marcada. El primer diagnóstico fue «el aviso no dispara»,
    y era al revés — el caso de prueba estaba mal, porque `7999` da `DROP` y no
    `FALLBACK`. Pero destapó que los `DROP` no se estaban contando.
    """
    fuente = inspect.getsource(api._sin_regla_propia)
    assert '"DROP"' in fuente
