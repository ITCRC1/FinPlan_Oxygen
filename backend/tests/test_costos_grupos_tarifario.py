# -*- coding: utf-8 -*-
"""El tarifario RACK del módulo de grupos.

Decisión del owner (2026-08-19): «la realidad debe ser Forecast 2026», y
«tomá 2027 como válidos en una tabla de rack rates y yo los edito».

La pregunta que estas pruebas contestan no es «¿el CRUD guarda?» sino **¿puede
el precio moverle el piso a alguien?** — porque si puede, el módulo entero
deja de servir: negociar un descuento bajaría el piso justo lo necesario para
que el descuento parezca aceptable.
"""
from decimal import Decimal

import pytest

from app.engine.costos_grupos import (
    TarifaRack, descuentos, factor_neto_del_rack, pisos_habitacion,
)
from app.engine.costos_grupos import MesDeCostos
from app.seed_costos_grupos import ARCHIVO_RACK, _rack_rates


def _mes(temporada="ALTA", propio="100000", oh="40000", disp=930, ocup="500"):
    return MesDeCostos(
        mes=1, temporada=temporada, dias_abiertos=31,
        revenue_por_dept={"REV_ROOMS": Decimal("300000")},
        costo_por_dept={"OPEX_ROOMS": Decimal(propio)},
        overhead_por_componente={"OH_ADMIN": Decimal(oh)},
        hab_disponibles=disp, hab_ocupadas=Decimal(ocup),
        noches_huesped=Decimal(ocup) * 2,
    )


COMP = {("ROOMS", "propio"): ["OPEX_ROOMS"], ("ROOMS", "venta"): ["OPEX_ROOMS"]}
PAR = {"management_fee_pct": "0.03", "margen_protegido_pct": "0.15",
       "metodo_absorcion": "M2", "sustainability_libre": "NO"}


# ── La razón de ser de la tabla aparte ──────────────────────────────────────

def test_EL_PISO_NO_SE_MUEVE_AUNQUE_EL_RACK_CAMBIE():
    """⚠️ **La prueba que justifica que el tarifario sea una tabla aparte.**

    Si el rack viviera en `rate_cards` del escenario, editarlo movería el
    ingreso, el ingreso movería el costo unitario y el piso se movería solo:
    conceder un descuento bajaría el piso lo suficiente para que el descuento
    pareciera aceptable. Circular y silencioso.

    Acá el rack no entra en `pisos_habitacion` ni por parámetro. Duplicarlo o
    partirlo por diez tiene que dar EXACTAMENTE el mismo piso.
    """
    meses = [_mes()]
    antes = pisos_habitacion(meses, COMP, PAR, Decimal("0.203"))

    # El rack se mueve muchísimo — y no se le pasa a `pisos_habitacion`,
    # porque esa función no lo recibe. Ese es el punto.
    for rack in ("100", "839.52", "10000"):
        racks = [TarifaRack("BL01", "Deluxe King", 1, Decimal(rack),
                            Decimal(rack) * Decimal("0.797"), Decimal("1.8"))]
        descuentos(racks, antes.con_margen)          # se usa, y no muta nada
        despues = pisos_habitacion(meses, COMP, PAR, Decimal("0.203"))
        assert despues.con_margen == antes.con_margen
        assert despues.integral == antes.integral
        assert despues.departamental == antes.departamental
        assert despues.marginal == antes.marginal


def test_mover_el_rack_SI_mueve_el_descuento():
    """El contrapunto: si nada se moviera, la tabla no serviría de nada."""
    piso = Decimal("500")
    bajo = descuentos([TarifaRack("X", "X", 1, Decimal("800"),
                                  Decimal("637.6"), Decimal("1.8"))], piso)[0]
    alto = descuentos([TarifaRack("X", "X", 1, Decimal("1600"),
                                  Decimal("1275.2"), Decimal("1.8"))], piso)[0]
    assert alto.descuento_max > bajo.descuento_max


# ── La semilla ──────────────────────────────────────────────────────────────

# ⚠️ **Estas reglas dejaron de medir a Corcovado (2026-08-21).**
#
# Comprobaban sus 96 celdas, sus ocho códigos (`BL01`, `BI02`…) y que el rack de
# `BI02` bajara de enero a setiembre. Todo eso es el tarifario de un hotel, y su
# carpeta salió de este repositorio — el despliegue es de Amarena.
#
# Lo que se conserva es la FORMA, que sí vale para cualquier propiedad: que la
# tabla se llavee por código y no por nombre, y que cubra los doce meses. Se
# mide sobre la semilla que haya; hoy no hay ninguna y la regla espera.

def test_la_semilla_del_rack_se_llavea_por_CODIGO_y_cubre_el_ano():
    """⚠️ El nombre es una etiqueta renombrable; el código es fijo por
    categoría. Llavear por nombre haría que renombrar «Deluxe King» dejara
    huérfanas sus doce tarifas sin que nada fallara.

    Y los doce meses tienen que estar: por esto la tabla es de 12 columnas y no
    de 3 temporadas — el rack BAJA en temporada baja justo cuando el piso SUBE,
    y un promedio por temporada taparía exactamente el mes que duele.
    """
    filas = _rack_rates()
    if not filas:
        pytest.skip("esta propiedad todavía no cargó su tarifario rack")
    assert all(f.get("room_type_code") for f in filas), (
        "una fila sin código: se está llaveando por nombre")
    assert sorted({int(f["mes"]) for f in filas}) == list(range(1, 13)), (
        "el tarifario no cubre los doce meses")
    # Cada categoría, sus doce meses — ni de más ni de menos.
    from collections import Counter
    por_tipo = Counter(f["room_type_code"] for f in filas)
    torcidas = {c: n for c, n in por_tipo.items() if n != 12}
    assert not torcidas, f"categorías sin sus 12 meses: {torcidas}"


def test_la_semilla_no_trae_tarifas_negativas_ni_netos_mayores_al_rack():
    """Un neto por encima del rack daría una comisión negativa y un factor
    mayor que 1 — el mismo defecto que tiene `compute_net_factor`."""
    for f in _rack_rates():
        rack, neto = Decimal(f["rack"]), Decimal(f["neto"])
        assert rack > 0, f
        assert 0 < neto <= rack, f


# ── El factor neto ──────────────────────────────────────────────────────────

def test_el_factor_neto_SIEMPRE_queda_entre_cero_y_uno():
    """⚠️ `compute_net_factor(channels)` devuelve **9,5639** en producción para
    los 36 canales del Budget Working 2027. Un factor mayor que 1 multiplicaría
    el ingreso por nueve. El módulo saca el suyo del tarifario a propósito.

    ⚠️ Antes esto se medía sobre el tarifario de Corcovado, y de paso fijaba su
    valor (0,79–0,80). Al salir esa semilla del repositorio la guarda se habría
    ido con ella — justo la guarda que protege de un ×9. Ahora se mide sobre
    tarifas construidas acá, así que **no depende de que ninguna propiedad haya
    cargado nada** y vale para todas: mientras el neto no supere al rack, el
    factor tiene que caer entre 0 y 1.
    """
    racks = [
        TarifaRack("AA01", "Categoría A", 1, Decimal("1000"), Decimal("800"), Decimal("2")),
        TarifaRack("BB02", "Categoría B", 2, Decimal("500"), Decimal("350"), Decimal("2")),
        TarifaRack("CC03", "Categoría C", 3, Decimal("250"), Decimal("250"), Decimal("1")),
    ]
    fn = factor_neto_del_rack(racks)
    assert fn is not None
    assert Decimal("0") < fn < Decimal("1"), f"factor fuera de rango: {fn}"


def test_el_factor_neto_de_la_semilla_es_menor_que_uno():
    """La misma regla, sobre el tarifario que la propiedad haya cargado."""
    filas = _rack_rates()
    if not filas:
        pytest.skip("esta propiedad todavía no cargó su tarifario rack")
    racks = [TarifaRack(f["room_type_code"], f["nombre"], f["orden"],
                        Decimal(f["rack"]), Decimal(f["neto"]), Decimal(f["pax"]))
             for f in filas if int(f["mes"]) == 1]
    fn = factor_neto_del_rack(racks)
    assert fn is not None
    assert Decimal("0") < fn < Decimal("1")


# ── La tabla del módulo NO es la del escenario ──────────────────────────────

def test_el_motor_del_modulo_no_lee_los_rate_cards_del_escenario():
    """⚠️ Hay DOS tarifarios en la app y editar el equivocado es el error
    fácil. `/revenue/rack-rates` mueve el ingreso del presupuesto; éste no
    mueve nada. Que el motor del módulo no importe `RateCard` es lo que lo
    sostiene."""
    import inspect

    from app.engine import costos_grupos

    fuente = inspect.getsource(costos_grupos.tarifas_rack)
    assert "CfgTarifaRack" in fuente
    assert "RateCard" not in fuente
    # Y no recibe `scenario_id`: no hay forma de apuntarlo a un escenario.
    firma = inspect.signature(costos_grupos.tarifas_rack)
    assert "scenario_id" not in firma.parameters


def test_la_pantalla_avisa_que_no_es_el_otro_tarifario():
    """Tener dos tablas de rack sin explicar la diferencia es cómo se edita la
    equivocada. La pantalla lo tiene que decir, no sólo el código."""
    import io
    import os

    ruta = os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                        "app", "cost", "pisos", "page.tsx")
    txt = io.open(ruta, encoding="utf-8").read()
    assert "rack-rates" in txt or "Rack Rates" in txt
    assert "no mueve" in txt.lower()


# ── Lo que la pantalla tiene que confesar ───────────────────────────────────

def test_un_piso_1_estimado_llega_marcado_hasta_la_pantalla():
    """Un Piso 1 que parece medido y no lo está es peor que no tenerlo."""
    meses = [_mes()]
    sin_venta = {("ROOMS", "propio"): ["OPEX_ROOMS"]}
    p = pisos_habitacion(meses, sin_venta, PAR, Decimal("0.203"))
    assert p.marginal_estimado is True

    import io
    import os
    ruta = os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                        "app", "cost", "pisos", "page.tsx")
    txt = io.open(ruta, encoding="utf-8").read()
    assert "marginal_estimado" in txt


@pytest.mark.parametrize("temporada", ["ALTA", "MEDIA", "BAJA"])
def test_el_descuento_maximo_nunca_pasa_del_cien_por_ciento(temporada):
    """Un descuento del 100% sería regalar la habitación. Con un piso positivo
    la fórmula no puede llegar ahí; la prueba fija esa propiedad."""
    p = pisos_habitacion([_mes(temporada=temporada)], COMP, PAR, Decimal("0.203"))
    assert p.con_margen > 0
    d = descuentos([TarifaRack("X", "X", 1, Decimal("999999"),
                               Decimal("797000"), Decimal("1.8"))],
                   p.con_margen)[0]
    assert d.descuento_max < Decimal("1")
