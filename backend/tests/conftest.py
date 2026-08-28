# -*- coding: utf-8 -*-
"""Fixtures compartidas.

## `semillero` — probar el mecanismo de semillas sin el dato de nadie

Las semillas por propiedad viven en `app/seed_data/<HOTEL_ID>/`, y varias
pruebas cuidaban ese mecanismo leyendo la carpeta de Corcovado: pedían
`semilla("paquete", "CWL")` y comprobaban que trajera algo.

Este repositorio es el despliegue de **Amarena**, y la carpeta de Corcovado
salió de acá el 2026-08-21 — su tarifario, sus experiencias (el tour a San
Pedrillo, el transporte Sierpe/Drake) y su clasificación de break-even son el
producto de otro hotel y no tienen por qué viajar en este repo.

Pero lo que esas pruebas cuidaban **sigue importando**, y no es el dato: es que
una propiedad sin carpeta reciba `None` en vez de la lista de la propiedad de al
lado, y que los números lleguen como `Decimal` y no como `float`. Las dos cosas
se prueban igual de bien —mejor, incluso— contra una propiedad inventada.

`XXX` es esa propiedad inventada. No existe ni va a existir: si algún día se
abre una quinta propiedad real, no se va a llamar así.
"""
import json
import pathlib

import pytest


@pytest.fixture
def semillero(tmp_path, monkeypatch):
    """Un `seed_data/` de mentira con una sola propiedad, `XXX`.

    Devuelve la raíz temporal por si la prueba necesita agregarle archivos.
    """
    import app.seed_data as sd

    # `semilla()` resuelve `_RAIZ / hotel_id / …` en cada llamada, así que
    # cambiar el módulo alcanza — no hay que recargar nada.
    monkeypatch.setattr(sd, "_RAIZ", tmp_path)
    # Y la propiedad ambiente, para las rutas que piden la semilla sin nombrar
    # hotel (`semilla("paquete")` a secas, que es como la llaman los endpoints).
    monkeypatch.setattr(sd, "HOTEL_ID", "XXX")

    xxx = tmp_path / "XXX"
    xxx.mkdir()

    # Los números van como TEXTO, igual que en los archivos reales: es lo que
    # permite reconstruirlos como Decimal sin pasar por float.
    (xxx / "paquete.json").write_text(json.dumps({
        "FOOD": {"rate_per_pax_night": "100.0000", "bev_food_ratio": "0.3000",
                 "is_commissionable": True},
        "ACTIVITIES": {"rate_per_pax_night": "50.0000", "is_commissionable": True},
    }), encoding="utf-8")

    (xxx / "canales.json").write_text(json.dumps([
        {"channel": "TA", "mix_pct": "0.500000", "commission_pct": "0.250000"},
        {"channel": "DIRECT", "mix_pct": "0.500000", "commission_pct": "0.000000"},
    ]), encoding="utf-8")

    (xxx / "experiencias.json").write_text(json.dumps([
        {"nombre": "Experiencia de prueba", "es_base": True},
    ]), encoding="utf-8")

    # Códigos con cero adelante: son LLAVES, no cantidades. Si alguien los
    # convierte a número, «0113» se vuelve 113 y el departamento deja de existir.
    # ⚠️ `fte` va como NÚMERO y `source`/`legacy` como TEXTO, a propósito: es la
    # forma de los archivos reales. El FTE se suma; el código de departamento se
    # compara, y convertirlo le comería el cero de adelante.
    (xxx / "reasignaciones_salario.json").write_text(json.dumps({
        "reasignaciones": [
            {"name": "PUESTO DE PRUEBA", "legacy": "0113",
             "source": "0113", "target": "0120", "fte": 1.0},
        ]
    }), encoding="utf-8")

    (xxx / "driver_rates.json").write_text(json.dumps({
        "tarifas": {"food": "10.00", "nights_per_stay": "3"}
    }), encoding="utf-8")

    # `code` y `name`, que es lo que lee `opex_api._catalogo_de_arranque`.
    (xxx / "opex_accounts.json").write_text(json.dumps({
        "cuentas": [{"code": "7005", "name": "CUENTA DE PRUEBA"}]
    }), encoding="utf-8")

    (xxx / "canales_mix.json").write_text(json.dumps({
        "canales": ["Directo", "Agencia"]
    }), encoding="utf-8")

    return tmp_path


@pytest.fixture
def raiz_semillas() -> pathlib.Path:
    """La carpeta real de semillas, para las pruebas que miran su forma."""
    import app.seed_data as sd
    return pathlib.Path(sd.__file__).parent
