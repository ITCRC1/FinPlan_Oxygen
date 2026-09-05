# -*- coding: utf-8 -*-
"""
EL ADR NO PUEDE DEPENDER DE CUÁNDO SE APRETÓ RECALCULAR.

Owner, 2026-09-05: *«necesito que derives el ADR y todos los kpi que dependen de
recalculo»*.

`scenario_stats.adr` es una columna guardada que sólo se refresca en el
recálculo (`_persist_room_stats`). Entre que se mueve una tarifa y que se
recalcula, el P&L de doce meses mostraba un ADR viejo **al lado del ingreso
nuevo** — y el endpoint mensual, que sí deriva, mostraba otro número para el
mismo mes.

Estas pruebas fijan las cuatro reglas de `engine/kpis.py`. Ver
`docs/PENDIENTES.md` A4 para por qué el numerador nunca es la línea del P&L.
"""
from decimal import Decimal

from app.engine.kpis import kpis_de_habitaciones


def test_el_adr_sale_del_ingreso_y_no_del_guardado():
    """Con ingreso y noches, se deriva: el guardado queda ignorado.

    Es el caso que motivó todo — el guardado ($400) es de un recálculo viejo y
    el ingreso ya se movió.
    """
    k = kpis_de_habitaciones(
        rooms_available=300, rooms_occupied=Decimal("200"), guests=Decimal("380"),
        ingreso_habitaciones=Decimal("100000"), adr_guardado=Decimal("400"),
    )
    assert k["adr"] == 500.0, "debía derivar 100.000 / 200, no arrastrar el 400"


def test_sin_ingreso_queda_el_guardado_y_no_un_cero():
    """El ACTUAL: la estadística viene del PMS y el ingreso puro no existe.

    ⚠️ Lo importante no es que respete el número: es que **no ponga cero**. Un
    cero se lee como dato, no como dato que falta. Es la regla de la casa —no
    inventar— aplicada al revés: tampoco borrar.
    """
    k = kpis_de_habitaciones(
        rooms_available=300, rooms_occupied=Decimal("200"), guests=Decimal("380"),
        ingreso_habitaciones=None, adr_guardado=Decimal("477.34"),
    )
    assert k["adr"] == 477.34


def test_sin_noches_ocupadas_tampoco_se_fabrica_una_tarifa():
    """Sin denominador no hay tarifa: se respeta el guardado en vez de dividir."""
    k = kpis_de_habitaciones(
        rooms_available=300, rooms_occupied=Decimal("0"), guests=Decimal("0"),
        ingreso_habitaciones=Decimal("100000"), adr_guardado=Decimal("450"),
    )
    assert k["adr"] == 450.0
    assert k["occupancy_pct"] == 0.0


def test_la_ocupacion_sale_de_las_noches_aunque_la_columna_diga_otra_cosa():
    """`occupancy_pct` guardada podía no coincidir con las dos noches de SU MISMA
    fila. Mandan las noches."""
    k = kpis_de_habitaciones(
        rooms_available=300, rooms_occupied=Decimal("150"), guests=Decimal("300"),
        ingreso_habitaciones=Decimal("75000"),
        occupancy_guardada=Decimal("0.9"),   # vieja, de otro recálculo
    )
    assert k["occupancy_pct"] == 0.5


def test_se_mantiene_la_identidad_revpar_igual_adr_por_ocupacion():
    """RevPAR = ADR × ocupación, también cuando el ADR cayó al guardado.

    Si el RevPAR se derivara del ingreso mientras el ADR viene del guardado, los
    tres números no cerrarían entre ellos y la pantalla se contradiría sola.
    """
    for ingreso, guardado in ((Decimal("100000"), Decimal("400")),
                              (None, Decimal("477.34"))):
        k = kpis_de_habitaciones(
            rooms_available=300, rooms_occupied=Decimal("200"), guests=Decimal("380"),
            ingreso_habitaciones=ingreso, adr_guardado=guardado,
        )
        esperado = k["adr"] * k["occupancy_pct"]
        assert abs(k["revpar"] - esperado) < 1e-9, (ingreso, k)


def test_un_mes_cerrado_no_revienta():
    """Escenario vacío / mes cerrado: todo en cero y sin división por cero."""
    k = kpis_de_habitaciones(
        rooms_available=0, rooms_occupied=0, guests=0,
        ingreso_habitaciones=None, adr_guardado=None, occupancy_guardada=None,
    )
    assert k == {"rooms_available": 0, "rooms_occupied": 0.0, "guests": 0.0,
                 "occupancy_pct": 0.0, "adr": 0.0, "revpar": 0.0}
