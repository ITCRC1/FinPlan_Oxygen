# -*- coding: utf-8 -*-
"""Saca de esta instalación lo que dejaron los primeros deploys del clon.

    python -m scripts.limpiar_arranque_amarena              # sólo mira, no escribe
    python -m scripts.limpiar_arranque_amarena --aplicar

**Qué encontró la auditoría del 2026-08-27, en la base de producción de Amarena:**

* La ficha del hotel **CWL** —Corcovado Wilderness Lodge, 30 habitaciones— y sus
  filas repartidas por siete tablas: los 6 tipos de habitación con sus nombres y
  unidades reales, las 96 tarifas RACK, la composición de costos, las
  temporadas, los parámetros y la configuración de Guillermo.
* Cuatro categorías de AMA —`SH01`..`SH04`, «Nueva categoría», 0 unidades, tres
  ocultas— que son clics de prueba.

Lo primero es de otra propiedad y ensucia cualquier reporte que no filtre por
hotel. Lo segundo **quema el correlativo**: mientras esas cuatro estén, una
categoría nueva nace `SH05` en vez del código estándar del grupo, y el código no
se puede cambiar después (el `PUT` devuelve 409).

**Dos seguros, a propósito:**

1. Se niega a correr si `HOTEL_ID` no es `AMA`. Este mismo archivo en la
   instalación de Corcovado borraría Corcovado.
2. Se niega a borrar una categoría que tenga algo colgando. Un `units=0` no
   alcanza como prueba de que está vacía: lo que importa es si alguien ya cargó
   tarifas, ocupación o noches contra ese `id`.

Todo lo que borra lo escribe antes en un JSON (`--respaldo`), fila por fila.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

# Cuando se corre como archivo, `backend/` tiene que estar en la ruta. Cuando se
# corre canalizado (`cat guion.py | python -`, que es como llega al contenedor de
# Railway) no hay `__file__` y el directorio actual ya es `/app`, así que no hay
# nada que agregar.
if "__file__" in globals():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

#: La propiedad de ESTA instalación. Cualquier otra cosa aborta.
ESPERADO = "AMA"

#: Lo que dejaron los primeros deploys. Se borra por `hotel_id`, no por lista de
#: tablas escrita a mano: una tabla nueva con `hotel_id` entra sola.
AJENO = "CWL"


async def _tablas_con_hotel(conn) -> list[str]:
    filas = await conn.fetch(
        "SELECT c.table_name FROM information_schema.columns c "
        "JOIN information_schema.tables t ON t.table_name = c.table_name "
        " AND t.table_schema = 'public' AND t.table_type = 'BASE TABLE' "
        "WHERE c.table_schema = 'public' AND c.column_name = 'hotel_id' "
        "  AND c.table_name <> 'hotels' "
        "ORDER BY c.table_name")
    return [f["table_name"] for f in filas]


async def _dependen_de(conn, ids: list[str]) -> dict[str, int]:
    """Cuántas filas cuelgan de esas categorías, tabla por tabla.

    Mira `room_type_id` de tipo texto — que es como está modelado el vínculo.
    Una tabla que lo guarde de otra forma no la ve, y por eso el resumen se
    imprime siempre: el que corre esto tiene que poder leerlo antes de aplicar.
    """
    if not ids:
        return {}
    cols = await conn.fetch(
        "SELECT c.table_name, c.data_type FROM information_schema.columns c "
        "JOIN information_schema.tables t ON t.table_name = c.table_name "
        " AND t.table_schema = 'public' AND t.table_type = 'BASE TABLE' "
        "WHERE c.table_schema = 'public' AND c.column_name = 'room_type_id' "
        "ORDER BY c.table_name")
    fuera: dict[str, int] = {}
    for c in cols:
        if c["data_type"] not in ("character varying", "text", "uuid"):
            continue
        n = await conn.fetchval(
            f'SELECT count(*) FROM "{c["table_name"]}" '
            "WHERE room_type_id::text = ANY($1::text[])", ids)
        if n:
            fuera[c["table_name"]] = n
    return fuera


async def main(aplicar: bool, respaldo: pathlib.Path) -> int:
    import asyncpg
    from app.db import DATABASE_URL
    from app.hotel_actual import HOTEL_ID

    if HOTEL_ID != ESPERADO:
        print(f"ABORTA: esta instalación es {HOTEL_ID!r}, no {ESPERADO!r}. "
              "Este guion sólo corre en Amarena.")
        return 2

    conn = await asyncpg.connect(
        DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://"))
    guardado: dict[str, list] = {}
    total = 0
    try:
        # ── 1. Las categorías de prueba de AMA ────────────────────────────────
        pruebas = await conn.fetch(
            "SELECT * FROM room_type_configs WHERE hotel_id = $1 "
            "ORDER BY sort_order", ESPERADO)
        ids = [r["id"] for r in pruebas]
        colgando = await _dependen_de(conn, ids)
        print(f"Categorías de {ESPERADO}: {len(pruebas)}")
        for r in pruebas:
            print(f"  sort={r['sort_order']} code={r['code'] or '(vacío)'} "
                  f"units={r['units']} active={r['active']} — {r['name']}")
        if colgando:
            print("ABORTA: hay datos colgando de esas categorías — "
                  + ", ".join(f"{t}={n}" for t, n in colgando.items()))
            print("Borrarlas dejaría esas filas apuntando a nada. "
                  "Revisar a mano antes de seguir.")
            return 3
        print("  nada cuelga de ellas ✓")
        guardado["room_type_configs"] = [dict(r) for r in pruebas]
        total += len(pruebas)

        # ── 2. Todo lo de la propiedad ajena ──────────────────────────────────
        print(f"\nFilas de {AJENO} en esta base:")
        for tabla in await _tablas_con_hotel(conn):
            filas = await conn.fetch(
                f'SELECT * FROM "{tabla}" WHERE hotel_id = $1', AJENO)
            if filas:
                print(f"  {tabla}: {len(filas)}")
                guardado[f"{AJENO}.{tabla}"] = [dict(r) for r in filas]
                total += len(filas)
        ficha = await conn.fetch("SELECT * FROM hotels WHERE id = $1", AJENO)
        if ficha:
            print(f"  hotels: 1 — {ficha[0]['name']} ({ficha[0]['rooms']} hab.)")
            guardado[f"{AJENO}.hotels"] = [dict(r) for r in ficha]
            total += 1

        print(f"\nTOTAL a borrar: {total} filas")
        if not aplicar:
            print("\n(corrida en seco — no se escribió nada; agregar --aplicar)")
            return 0

        texto = json.dumps(guardado, indent=2, ensure_ascii=False, default=str)
        if str(respaldo) == "-":
            # El contenedor de Railway es efímero: un archivo ahí se va con el
            # próximo deploy. Por stdout el respaldo llega a quien lo corre.
            print("\n----- RESPALDO JSON -----")
            print(texto)
            print("----- FIN RESPALDO -----\n")
        else:
            respaldo.write_text(texto, encoding="utf-8")
            print(f"\nRespaldo escrito: {respaldo}")

        # Una sola transacción: o sale todo o no sale nada. A mitad de camino
        # quedaría un hotel sin sus tipos, que es peor que no haber empezado.
        async with conn.transaction():
            n = await conn.execute(
                "DELETE FROM room_type_configs WHERE hotel_id = $1", ESPERADO)
            print(f"  categorías de {ESPERADO}: {n}")
            for tabla in await _tablas_con_hotel(conn):
                n = await conn.execute(
                    f'DELETE FROM "{tabla}" WHERE hotel_id = $1', AJENO)
                if not n.endswith(" 0"):
                    print(f"  {tabla}: {n}")
            n = await conn.execute("DELETE FROM hotels WHERE id = $1", AJENO)
            print(f"  hotels: {n}")

        quedan = await conn.fetchval(
            "SELECT count(*) FROM room_type_configs WHERE hotel_id = $1", ESPERADO)
        ajenas = await conn.fetchval("SELECT count(*) FROM hotels WHERE id = $1", AJENO)
        print(f"\nVerificación: categorías de {ESPERADO} = {quedan} (esperado 0), "
              f"ficha de {AJENO} = {ajenas} (esperado 0)")
        print("Ahora corré `python -m app.seed` para sembrar los códigos estándar.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--aplicar", action="store_true",
                   help="escribe de verdad (sin esto sólo informa)")
    p.add_argument("--respaldo", default="respaldo_limpieza.json",
                   help="dónde dejar las filas borradas")
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a.aplicar, pathlib.Path(a.respaldo))))
