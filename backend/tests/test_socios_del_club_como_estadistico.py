# -*- coding: utf-8 -*-
"""
LOS SOCIOS DEL CLUB SON UN ESTADÍSTICO, Y SU CUOTA SE PONDERA COMO EL ADR.

## Por qué existe (2026-08-27)

Owner: *«mete la estadística de Club Madresal sobre número de miembros por mes,
pagando»* y *«pon precio promedio por miembro como estadístico»*.

El conteo ya vivía en `club_membership_stats` y se veía en el P&L Full Detail,
pero no viajaba con los KPIs, que es donde se lee junto a la ocupación y el ADR
—y es donde explica la cuota de `REV_CLUB`.

## Las dos reglas que esto vigila

**El conteo NO se suma.** Son socios, no ingresos: el valor de un período es el
SALDO del último mes. Sumar los doce daría 1.500 socios donde hay 129. Es la
misma regla que ya documenta `ClubMembershipStat` y que en el Excel de Amarena
comparten sólo cuatro filas.

**La cuota SÍ se pondera, y por SOCIOS-MES.** Es el ADR de este negocio: ingreso
sobre unidades vendidas, donde la unidad es un socio durante un mes. Dividir el
ingreso del año entre los socios de diciembre daría la cuota ANUAL disfrazada de
mensual, y un socio que entra en octubre contaría como si hubiera pagado los
doce meses.

Medido contra los datos reales de Amarena: diciembre 129 socios y $27,090 →
$210.00 exactos; el año 725 socios-mes y $150,040 → $206.95. La diferencia entre
las dos es justamente lo que la ponderación captura.

## Y por qué no hay ningún `if hotel == "AMA"`

El owner avisó que el Club se va a operar por fuera del hotel. La clave no se
manda cuando no hay socios cargados, así que el día que salga los renglones se
apagan solos — sin tocar código y sin que nadie tenga que acordarse.
"""
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1]
API = (RAIZ / "app" / "api" / "pl_api.py").read_text(encoding="utf-8")
PANTALLA = (RAIZ.parent / "frontend" / "app" / "month-end" / "pl" /
            "page.tsx").read_text(encoding="utf-8")
JUNTA = (RAIZ.parent / "frontend" / "app" / "reports" / "junta" /
         "bloques.tsx").read_text(encoding="utf-8")


def _bloque_club() -> str:
    """El trozo de `_aggregate_selected` que arma los KPIs del Club."""
    assert "club_pagando" in API
    return API.split('if any("club_pagando"')[1].split("lines = []")[0]


def test_el_conteo_es_el_saldo_del_ultimo_mes_no_la_suma():
    bloque = _bloque_club()
    m = re.search(r'kpis\["club_pagando"\]\s*=\s*([^\n]+)', bloque)
    assert m, "no se encontró de dónde sale el conteo del período"
    fuente = m.group(1)
    assert "sel[-1]" in fuente, (
        "el conteo tiene que ser el saldo del ÚLTIMO mes; sumar los doce daría "
        "1.500 socios donde hay 129")
    assert "sum(" not in fuente


def test_la_cuota_se_divide_entre_socios_mes():
    bloque = _bloque_club()
    assert "club_socios_mes" in bloque
    m = re.search(r'kpis\["club_cuota_promedio"\]\s*=\s*\((.*?)\)\s*if', bloque, re.S)
    assert m, "no se encontró el cálculo de la cuota"
    calculo = m.group(1)
    assert "REV_CLUB" in calculo, "la cuota no sale del ingreso del Club"
    assert "socios_mes" in calculo, (
        "la cuota se está dividiendo entre algo que no son socios-mes: con el "
        "saldo de diciembre daría la cuota anual disfrazada de mensual")


def test_los_socios_mes_son_la_suma_de_los_meses():
    """El denominador SÍ es aditivo, aunque el conteo no lo sea."""
    bloque = _bloque_club()
    m = re.search(r"socios_mes\s*=\s*([^\n]+)", bloque)
    assert m and "sum(" in m.group(1)


def test_no_se_divide_entre_cero():
    assert "if socios_mes else 0.0" in _bloque_club()


def test_la_clave_no_viaja_cuando_no_hay_club():
    """Sin socios cargados no se manda nada — ni un cero.

    Un cero se lee como «no hay socios»; la ausencia dice «no hay Club», que es
    otra cosa y es la verdad en las propiedades que no lo tienen.
    """
    monthly = API.split("socios = {")[1].split("return out")[0]
    assert "if socios:" in monthly, (
        "se estaría poniendo la clave siempre, y toda propiedad sin Club vería "
        "los renglones en cero")


def test_la_pantalla_no_pregunta_por_el_hotel():
    """La visibilidad sale del DATO, no de un `if hotel === "AMA"`."""
    assert "hayClub" in PANTALLA
    assert 'club_pagando != null' in PANTALLA
    bloque = PANTALLA.split("const hayClub")[1].split("];")[0]
    assert "AMA" not in bloque and "HOTEL_ID" not in bloque, (
        "la visibilidad del Club no puede depender del hotel: el owner avisó "
        "que se va a operar por fuera y entonces hay que tocar código")


def test_los_dos_renglones_estan_rotulados():
    assert "Socios pagando" in PANTALLA
    assert "Cuota promedio por socio" in PANTALLA


# ── La presentacion a la Junta (owner, 2026-08-27) ────────────────────────────

def test_la_junta_muestra_los_socios_y_la_cuota():
    assert "Miembros del Club (pagando)" in JUNTA
    assert "Miembros del Club (total)" in JUNTA
    assert "Cuota promedio por miembro" in JUNTA


def test_la_junta_esconde_las_filas_sin_dato():
    """Un «Miembros del Club: 0» en la lámina de una propiedad sin Club no es un
    dato: se lee como que el Club existe y se quedó vacío."""
    assert "soloSi" in JUNTA
    assert "hayClub" in JUNTA and "hayTotalDeClub" in JUNTA
    # Y la tabla tiene que RESPETARLO, no solo declararlo.
    assert "filasTodas.filter(f => !f.soloSi || f.soloSi(vs))" in JUNTA


def test_el_total_de_la_junta_espera_a_tener_dato():
    """`club_total` llega en 0 mientras nadie lo cargue — y un 0 al lado de 129
    pagando invita a leer que el Club perdio a todos sus socios."""
    bloque = JUNTA.split("const hayTotalDeClub")[1].split(";")[0]
    assert "> 0" in bloque, "la fila del total se dibujaría con el conteo en cero"


def test_la_junta_no_pregunta_por_el_hotel():
    bloque = JUNTA.split("const hayClub")[1].split(";")[0]
    assert "AMA" not in bloque and "HOTEL_ID" not in bloque
