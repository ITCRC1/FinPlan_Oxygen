# -*- coding: utf-8 -*-
"""Las categorías de habitación de Amarena — nombre, unidades y pax.

    python -m scripts.cargar_categorias_amarena              # sólo mira
    python -m scripts.cargar_categorias_amarena --aplicar

**Qué es.** Las ocho filas que siembra `app/seed.py` nacen con el código estándar
del grupo y el rótulo en blanco («Categoría 1»…). Esto les pone el nombre real de
Amarena y las unidades, y oculta las que esta propiedad no usa.

**Por qué está versionado y no se hizo sólo a mano.** Es lo que se corrió contra
producción el 2026-08-27, y el registro de qué quedó cargado vale tanto como el
cambio: dentro de seis meses, «¿de dónde salieron estos 16 cuartos?» se contesta
leyendo este archivo. Es idempotente — correrlo dos veces deja lo mismo.

**El CÓDIGO no se toca acá.** Se busca POR código y se escribe el nombre. Es la
regla del owner: el código liga la categoría entre escenarios, reportes y
propiedades, y el `PUT` de la app devuelve 409 si alguien intenta moverlo. Este
guion respeta lo mismo aunque escriba por SQL — si el código no existe, avisa; no
lo crea ni lo renombra.

**Lo que NO decide este archivo:** el `pax_per_night` del hotel (el factor que
convierte noches ocupadas en huéspedes) es otra cosa y vive en `hotels`.
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

if "__file__" in globals():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

ESPERADO = "AMA"

#: (código estándar, nombre, nombre corto, unidades). El ORDEN es el del owner y
#: es el mismo `sort_order` con el que nacieron: el importador de Excel mapea sus
#: filas por posición, así que reordenar acá reasignaría tarifas.
CATEGORIAS = [
    ("BL01", "Garden View Deluxe-Tented Villa",             "Garden View Deluxe",     8),
    ("BI02", "Beachfront Deluxe-Tented Villa",              "Beachfront Deluxe",      5),
    ("PO03", "Beachfront Master-Suite Tented Villa",        "Beachfront Master-Suite", 2),
    ("RO04", "Garden View Deluxe-Tented Villa · Accesible", "Garden View Accesible",  1),
]

#: Owner, 2026-08-27: «2 pax por habitación por ahora». Es un valor provisional
#: —se edita desde la app cuando haya el dato real por categoría— y por eso está
#: acá arriba y no escondido en el UPDATE.
PAX_MIN = PAX_MAX = 2


async def main(aplicar: bool) -> int:
    import asyncpg
    from app.db import DATABASE_URL
    from app.hotel_actual import HOTEL_ID

    if HOTEL_ID != ESPERADO:
        print(f"ABORTA: esta instalación es {HOTEL_ID!r}, no {ESPERADO!r}.")
        return 2

    conn = await asyncpg.connect(
        DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        usados = [c[0] for c in CATEGORIAS]
        faltan = [c for c in usados if not await conn.fetchval(
            "SELECT 1 FROM room_type_configs WHERE hotel_id=$1 AND code=$2", ESPERADO, c)]
        if faltan:
            print(f"ABORTA: faltan los códigos {faltan} — corré `python -m app.seed` "
                  "antes. Este guion nombra categorías, no las crea.")
            return 3

        total = sum(c[3] for c in CATEGORIAS)
        print(f"Categorías de {ESPERADO}: {len(CATEGORIAS)} activas, {total} unidades, "
              f"pax {PAX_MIN}-{PAX_MAX}")
        for code, name, _short, units in CATEGORIAS:
            print(f"  {code}  {name}  ×{units}")
        print(f"  se ocultan las demás; hotels.rooms = {total}")

        if not aplicar:
            print("\n(corrida en seco — agregar --aplicar)")
            return 0

        async with conn.transaction():
            for code, name, short, units in CATEGORIAS:
                await conn.execute(
                    "UPDATE room_type_configs SET name=$1, short_name=$2, units=$3, "
                    "pax_min=$4, pax_max=$5, active=true "
                    "WHERE hotel_id=$6 AND code=$7",
                    name, short, units, PAX_MIN, PAX_MAX, ESPERADO, code)
            # Ocultar, NO borrar: el código queda reservado y una quinta categoría
            # futura lo reusa con su nombre nuevo. Borrar liberaría el número.
            await conn.execute(
                "UPDATE room_type_configs SET pax_min=$1, pax_max=$2, active=false "
                "WHERE hotel_id=$3 AND code <> ALL($4::text[])",
                PAX_MIN, PAX_MAX, ESPERADO, usados)
            await conn.execute("UPDATE hotels SET rooms=$1 WHERE id=$2", total, ESPERADO)

        print("\nComo quedó:")
        for r in await conn.fetch(
                "SELECT sort_order, code, name, units, pax_min, pax_max, active "
                "FROM room_type_configs WHERE hotel_id=$1 ORDER BY sort_order", ESPERADO):
            estado = "" if r["active"] else "  (oculta)"
            print(f"  {r['sort_order']}. {r['code']:<5} {r['name']:<46} "
                  f"{r['units']:>2} u.  pax {r['pax_min']}-{r['pax_max']}{estado}")
        print(f"  hotels.rooms = "
              f"{await conn.fetchval('SELECT rooms FROM hotels WHERE id=$1', ESPERADO)}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--aplicar", action="store_true")
    raise SystemExit(asyncio.run(main(p.parse_args().aplicar)))
