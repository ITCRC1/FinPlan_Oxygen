# -*- coding: utf-8 -*-
"""RECALCULAR EL OPEX AL TIPO DE CAMBIO DEL BUDGET.

**El agujero que esto tapa.** El dólar de una línea en colones se calcula cuando
la línea se importa (`_derivar_importadas`) o cuando se edita
(`_derivar_si_es_crc`), con el TC de ese momento. No había ninguna acción para
refrescarlas después. Si el tipo de cambio del budget cambia —lo normal mientras
un presupuesto se construye— esas líneas se quedan con el dólar viejo: los
colones que se ven en pantalla dicen una cosa y el P&L, que lee los dólares,
dice otra. Nada falla y nada avisa. La única salida era volver a tocar cada línea
a mano.

Owner (2026-08-27), planificando el 2027: «realmente la mayoría de gastos son
colones… ya en Budget 2027 los ponemos en colones y que convierta al tipo de
cambio». O sea que el año que viene esto deja de ser un caso de borde y pasa a
ser el camino principal.
"""
from __future__ import annotations

from decimal import Decimal

from app.models.opex_entry import OpexEntry

MESES = ("jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec")


def _linea(currency: str, **kw) -> OpexEntry:
    e = OpexEntry(id="x", scenario_id="esc", hotel_id="AMA", dept_code="0200",
                  account_code="7065", detail_code="800", currency=currency)
    for m in MESES:
        setattr(e, m, Decimal(str(kw.get(m, 0))))
        setattr(e, f"crc_{m}", Decimal(str(kw.get(f"crc_{m}", 0))))
    return e


def test_una_linea_en_colones_se_convierte_al_tc():
    e = _linea("CRC", crc_jun=460000)
    assert e.derivar_usd(6, Decimal("460")) == Decimal("1000.0000")


def test_el_tc_nuevo_da_un_dolar_nuevo():
    """El punto entero de la acción: cambiar el TC tiene que mover el dólar."""
    e = _linea("CRC", crc_jun=460000, jun=1000)
    assert e.derivar_usd(6, Decimal("500")) == Decimal("920.0000")


def test_una_linea_en_dolares_no_se_toca():
    """Convertir un gasto que YA está en dólares sería inventar un efecto
    cambiario que no existe. El monto vuelve tal cual, con cualquier TC."""
    e = _linea("USD", jun=1000)
    assert e.derivar_usd(6, Decimal("460")) == Decimal("1000")
    assert e.derivar_usd(6, Decimal("999")) == Decimal("1000")


def test_un_tc_en_cero_no_inventa_un_monto():
    """Mejor cero que una división por un TC que no existe."""
    e = _linea("CRC", crc_jun=460000)
    assert e.derivar_usd(6, Decimal("0")) == Decimal("0")


def test_el_tc_es_el_del_MES_no_el_de_enero():
    """El TC puede variar mes a mes y la conversión también: junio se convierte
    con el TC de junio. Tomar uno solo para el año desalinea once meses."""
    e = _linea("CRC", crc_jun=460000, crc_dec=460000)
    assert e.derivar_usd(6, Decimal("460")) == Decimal("1000.0000")
    assert e.derivar_usd(12, Decimal("520")) == Decimal("884.6154")


def test_el_endpoint_existe_y_exige_tipo_de_cambio():
    """Sin TC no se puede convertir nada: mejor un 400 que explica que doce
    meses de ceros escritos en silencio."""
    import inspect

    from app.api.opex_api import recalcular_al_tc_del_budget

    fuente = inspect.getsource(recalcular_al_tc_del_budget)
    assert "tc.sin_tipos_de_cambio" in fuente, "no valida que haya TC"
    assert "assert_editable" in fuente, "correría sobre un escenario enllavado"
    assert "_derivar_importadas" in fuente, (
        "no reusa la derivación del import: serían dos fórmulas para lo mismo")


def test_esta_registrado_en_la_api():
    from app.main import app

    rutas = app.openapi()["paths"]
    assert "/api/opex/{scenario_id}/recalcular-tc/" in rutas
