# -*- coding: utf-8 -*-
"""El armado de ingresos de Planning, para consultar.

Owner, 2026-09-03: *«necesito crear otro tab y sub tabs tal como los checkbooks,
pero necesito jalar información de Planning: inventario, noches por categoría,
rack rates, ocupación, pax, canales de ventas, net rate y total revenue; y que se
pueda consultar por escenario: actual, forecast, budget»*.
"""
import json
from pathlib import Path

FRONT = Path(__file__).resolve().parents[2] / "frontend"
VISTA = FRONT / "app/month-end/revenue-plan/page.tsx"


def test_estan_las_OCHO_vistas_que_pidio():
    src = VISTA.read_text(encoding="utf-8")
    for rotulo in ("Inventario", "Noches por categoría", "Rack rates",
                   "Ocupación", "Pax", "Canales de venta", "Net rate",
                   "Total revenue"):
        assert rotulo in src, f"falta la vista «{rotulo}»"


def test_SEIS_salen_de_un_solo_endpoint():
    """⚠️ `by-room-type` las calcula con la misma función del motor
    (`room_type_breakdown`), así que salen conciliadas entre sí. Pedir cada una
    por su lado sería seis oportunidades de que no cuadren."""
    src = VISTA.read_text(encoding="utf-8")
    assert "getRevenueByRoomType" in src
    assert src.count("getRevenueByRoomType") >= 1


def test_es_de_SOLO_LECTURA():
    """Mismo motivo que Checkbooks: quien no tiene acceso a Planning entra y ve
    lo mismo, sin poder tocar nada."""
    src = VISTA.read_text(encoding="utf-8")
    codigo = "\n".join(l for l in src.splitlines()
                       if not l.lstrip().startswith(("*", "//", "/*")))
    for editable in ("<input", "<textarea", "contentEditable", "api.put",
                     "api.post", "onBlur="):
        assert editable not in codigo, f"trae «{editable}»: dejó de ser consulta"


def test_no_se_recalcula_el_ingreso_en_la_PANTALLA():
    """⚠️ Noches × net rate ES el ingreso, y la tentación de multiplicarlo acá
    es fuerte. Pero el motor tiene reglas que no se ven —paquetes, comisión por
    canal, el mix— y una multiplicación propia daría un total que no es el del
    P&L."""
    src = VISTA.read_text(encoding="utf-8")
    assert 'dato(rt.id, m, "revenue")' in src, (
        "el ingreso dejó de venir calculado del motor")


def test_las_RAZONES_no_se_suman():
    """La ocupación y el net rate son cocientes: doce porcentajes sumados dan un
    número que no es de nadie. El año se rederiva con su numerador y su
    denominador — el mismo criterio que el ADR del cierre."""
    src = VISTA.read_text(encoding="utf-8")
    assert "d ? ocup.reduce" in src            # ocupación ponderada
    assert "n ? ing.reduce" in src             # net rate ponderado
    # Y el renglón TOTAL sólo aparece donde sumar significa algo.
    assert 'const sumable = vista === "inventario"' in src


def test_el_INVENTARIO_no_se_suma_a_lo_largo_del_ano():
    """Son las mismas habitaciones doce veces: el «total» es el inventario, no
    la suma de los doce meses."""
    src = VISTA.read_text(encoding="utf-8")
    assert "total: rt.units," in src


def test_un_ACTUAL_sin_armado_se_EXPLICA_y_no_sale_en_cero():
    """⚠️ Medido: el ACTUAL Final 2026 da cero en las cuatro categorías y en los
    doce meses —no tiene `rate_cards` ni `occupancy_budgets`— porque sus
    estadísticas reales viven a nivel de propiedad, no por categoría.

    Una tabla de ceros se leería como «no hubo ocupación». Es distinto: el dato
    existe, en otro corte.
    """
    src = VISTA.read_text(encoding="utf-8")
    assert "const sinArmado" in src
    assert "no es que la ocupación" in src.lower()


def test_un_FORECAST_avisa_que_esto_es_el_ARMADO_y_no_el_resultado():
    """En los meses cerrados el P&L usa las estadísticas cargadas: una cosa es
    lo que se presupuestó y otra lo que pasó."""
    src = VISTA.read_text(encoding="utf-8")
    assert 'esc?.type === "FORECAST"' in src
    assert "esc.actuals_through" in src


def test_esta_en_el_MENU_junto_a_Checkbooks():
    nav = (FRONT / "components/TopNav.tsx").read_text(encoding="utf-8")
    assert '{ key: "monthEndRevenuePlan", href: "/month-end/revenue-plan" }' in nav
    grupo = nav[nav.index('key: "monthEnd",'):nav.index('key: "operationInsight"')]
    assert "monthEndCheckbooks" in grupo and "monthEndRevenuePlan" in grupo
    for idioma in ("es", "en"):
        textos = json.dumps(json.loads(
            (FRONT / f"messages/{idioma}.json").read_text(encoding="utf-8")))
        assert '"monthEndRevenuePlan"' in textos, f"sin rótulo en {idioma}"


def test_una_consulta_que_falla_no_vacia_la_pantalla():
    """Que falte la configuración de canales no puede dejar sin inventario ni
    sin noches, que son otro endpoint."""
    src = VISTA.read_text(encoding="utf-8")
    assert "Promise.allSettled" in src
