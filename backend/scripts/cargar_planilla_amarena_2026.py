# -*- coding: utf-8 -*-
"""La planilla 2026 de Amarena — puesto, persona y salario por departamento.

    python -m scripts.cargar_planilla_amarena_2026              # sólo mira
    python -m scripts.cargar_planilla_amarena_2026 --aplicar

**Qué es.** Las 39 posiciones del `HEADCOUNT 2026 BUDGET.xlsx` del owner, ya
mapeadas al catálogo de departamentos del app. Salario mensual **en colones** y
FTE mes por mes: el motor hace `SW = salario × FTE ÷ TC`, así que una persona
repartida entre el hotel y el Club entra **dos veces, con el salario completo en
las dos** y su FTE parcial en cada una — no se duplica el costo.

**Por qué está versionado y no se hizo sólo a mano.** Es lo que se cargó contra
producción el 2026-08-27 (escenario 2026 BUDGET Working, TC 460). El registro de
qué quedó vale tanto como el cambio: el archivo del owner traía cuatro
inconsistencias, y las decisiones que se tomaron sobre cada una están anotadas
abajo. Dentro de seis meses, «¿por qué Rosibel aparece con 1.0 y no con 1.2?» se
contesta leyendo este archivo. Es idempotente: reemplaza sólo los departamentos
que trae, y correrlo dos veces deja lo mismo.

**Este guion NO calcula.** Sólo inserta posiciones. Los conceptos (S&W, CCSS al
26,83 %, aguinaldo ÷12) los genera el motor: el botón «Recalcular y empujar al
P&L» del app, o `POST /api/scenarios/{id}/recalculate/`. Se hizo así a propósito
— reimplementar el cálculo por SQL sería una segunda verdad, y de la planilla
sale el P&L.

**Para correr el motor por `railway ssh`** hay que exportarle el
`LD_LIBRARY_PATH` que el proceso del app sí tiene y la sesión SSH no hereda; sin
él `greenlet` no encuentra `libstdc++.so.6`, SQLAlchemy no importa y el motor no
arranca. Y como el linker lee esa variable **al arrancar el proceso**, ponerla a
mitad de camino no sirve: hay que re-ejecutar (`os.execv`). El valor sale de
`/proc/1/environ`.

**El Área Recreativa (depto 270) queda vacía** — el Club Madresal la absorbió
(owner, 2026-08-27). De ahí viene la rareza del archivo fuente: la fórmula del
FTE del bloque de Madresal (`T124=SUM(T126:T147)`) incluye las dos filas del
gimnasio y la del salario (`E124=SUM(E126:E142)`) no.

**Lo que NO decide este archivo:** el TC (vive en `exchange_rates` del escenario,
ya en 460) y los parámetros de planilla — CCSS y divisor del aguinaldo — que
están en `payroll_params`.
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
import uuid

if "__file__" in globals():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

ESPERADO = "AMA"

#: Escenario destino: 2026 BUDGET Working. Se valida por id Y por (año, versión),
#: para que un id copiado de otra base no escriba en el escenario equivocado.
SCENARIO_ID = "e4540512-5b97-41c1-84db-23fc15c3d577"
ANIO, VERSION = 2026, "Working"

MESES = ["fte_jan", "fte_feb", "fte_mar", "fte_apr", "fte_may", "fte_jun",
         "fte_jul", "fte_aug", "fte_sep", "fte_oct", "fte_nov", "fte_dec"]

#: Correcciones que el owner confirmó sobre el archivo fuente (2026-08-27). El
#: Excel NO se modificó; quedan acá para que se sepa qué se cambió y por qué:
#:
#:  · fila 63  el nombre estaba mal. El salario de esa fila (₡375.000) es el de
#:    Bermúdez, y con Johan ahí el mismo Johan sumaba 1.5 FTE entre sus tres
#:    filas. Corregido: los dos quedan en 1.0.
#:  · fila 130 Diana Barrantes ya no trabaja en la propiedad → VACANTE.
#:  · fila 139 ese 0.2 de «Camarera Hotel» del Club estaba puesto a Rosibel, que
#:    ya llegaba a 1.0 con sus otras dos filas (y a otro salario). El patrón
#:    correcto es el de Gabriela Castellón: 0.8 en el hotel + 0.2 en el Club al
#:    MISMO salario. Los tres Room Attendant vacantes están en 0.8 sin su 0.2 en
#:    el Club, así que esa plaza queda VACANTE.
#:
#: Mapeos que el owner confirmó porque no se deducían del bloque: Guest
#: Experience → 0114 Concierge, el Chofer de 0.9 → 0182 Finance, Salvavidas →
#: 0186 Security.
#:
#: (depto, código, puesto, persona, salario CRC, FTE ene..dic)
POSICIONES = [
    ('0111', '0111-01', 'ASISTENTE ADMINISTRATIVA HOTEL & CLUB', 'Vacante', 550000, [0, 0, 0, 0, 0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]),
    ('0111', '0111-02', 'Front Desk Agent -Overnight', 'ESPINOZA CHACON CRISTHIAN', 475000, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]),
    ('0111', '0111-03', 'Front Desk Agent', 'CHAVES SOLANO MOISES', 450000, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]),
    ('0111', '0111-04', 'Property Manager', 'Carlos Rodriguez', 1250000, [0, 0, 0, 0, 0, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8]),
    ('0111', '0111-05', 'Front Desk Agent -Overnight', 'Vacacante', 450000, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]),
    ('0113', '0113-01', 'HOUSEKEEPING SUPERVISOR', 'ROSIBEL QUIROS BRENES', 650000, [0, 0, 0, 0, 0, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8]),
    ('0113', '0113-02', 'ROOM ATTENDANT', 'VACANTE', 375000, [0, 0, 0, 0, 0, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8]),
    ('0113', '0113-03', 'ROOM ATTENDANT', 'GABRIELA CASTELLON ROCHA', 385000, [0, 0, 0, 0, 0, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8]),
    ('0113', '0113-04', 'RUNNER HOTEL', 'JOHAN JIMENEZ QUIROS', 395000, [0, 0, 0, 0, 0, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8]),
    ('0113', '0113-05', 'ROOM ATTENDANT', 'VACANTE', 375000, [0, 0, 0, 0, 0, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8]),
    ('0113', '0113-06', 'ROOM ATTENDANT', 'VACANTE', 375000, [0, 0, 0, 0, 0, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8]),
    ('0114', '0114-01', 'Guest Experience', 'ESTEBAN CALDERON', 600000, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]),
    ('0200', '0200-01', 'OPERARIO DE MTO CLUB & HOTEL', 'FONSECA LOPEZ MARIO', 600000, [0, 0, 0, 0, 0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]),
    ('0200', '0200-02', 'OPERARIO DE MTO CLUB & HOTEL', 'BERMUDEZ VASQUEZ JOSE NELSON', 375000, [0, 0, 0, 0, 0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]),
    ('0200', '0200-03', 'JARDINERO HOTEL & CLUB', 'MARIN ARTAVIA HEINER', 430000, [0, 0, 0, 0, 0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]),
    ('0200', '0200-04', 'PISCINERO', 'VACANTE', 450000, [0, 0, 0, 0, 0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]),
    ('0182', '0182-01', 'Chofer-Transporte Empleados Y Huespedes', 'VACANTE', 500000, [0, 0, 0, 0, 0, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9]),
    ('0186', '0186-01', 'Salvavidas', 'VACANTE', 700000, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]),
    ('0161', '0161-01', 'Laundry Attendant', 'VACANTE', 450000, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]),
    ('0150', '0150-01', 'Chofer-Transporte Empleados Y Huespedes', 'VACANTE', 500000, [0, 0, 0, 0, 0, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]),
    ('260', '260-01', 'GERENTE DE OPERACIONES', 'RODRIGUEZ ARGUEDAS CARLOS', 1250000, [0, 0, 0, 0, 0, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]),
    ('260', '260-02', 'AMA DE LLAVES HOTEL', 'ROSIBEL QUIROS BRENES', 650000, [0, 0, 0, 0, 0, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]),
    ('260', '260-03', 'OPERARIO DE MTO CLUB & HOTEL', 'FONSECA LOPEZ MARIO', 600000, [0, 0, 0, 0, 0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]),
    ('260', '260-04', 'OPERARIO DE MTO CLUB & HOTEL', 'BERMUDEZ VASQUEZ JOSE NELSON', 375000, [0, 0, 0, 0, 0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]),
    ('260', '260-05', 'ASISTENTE ADMINISTRATIVA HOTEL & CLUB', 'VACANTE', 550000, [0, 0, 0, 0, 0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]),
    ('260', '260-06', 'RECEPCIONISTA NOCTURNO', 'ESPINOZA CHACON CRISTHIAN', 475000, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
    ('260', '260-07', 'HOST CLUB MADRESAL', 'DELGADO MOLINA MELISSA', 450000, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]),
    ('260', '260-08', 'GEST EXPICIENCE', 'ESTEBAN CALDERON', 600000, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
    ('260', '260-09', 'ENCARGADO DE PLAYA', 'WERLIN JIMENEZ', 135000, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]),
    ('260', '260-10', 'ENCARGADO DE CLUB', 'FARLEN ILAM', 650000, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]),
    ('260', '260-11', 'RECEPCIONISTA HOTEL', 'CHAVES SOLANO MOISES', 450000, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
    ('260', '260-12', 'JARDINERO HOTEL & CLUB', 'MARIN ARTAVIA HEINER', 430000, [0, 0, 0, 0, 0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]),
    ('260', '260-13', 'RUNNER HOTEL', 'JOHAN JIMENEZ QUIROS', 395000, [0, 0, 0, 0, 0, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]),
    ('260', '260-14', 'CAMARERA HOTEL', 'VACANTE', 385000, [0, 0, 0, 0, 0, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]),
    ('260', '260-15', 'CAMARERA HOTEL', 'GABRIELA CASTELLON ROCHA', 385000, [0, 0, 0, 0, 0, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]),
    ('260', '260-16', 'MISCELANEA CLUB MADRESAL', 'CECILIA CERDAS SANDI', 375000, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]),
    ('260', '260-17', 'PISCINERO', 'VACANTE', 450000, [0, 0, 0, 0, 0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]),
    ('260', '260-18', 'Host-in charge of Gym and Area', 'VACANTE', 450000, [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1]),
    ('260', '260-19', 'Room Attendant', 'VACANTE', 375000, [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1]),
]


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
        sc = await conn.fetchrow(
            "SELECT id, year, type, version, status FROM scenarios WHERE id=$1", SCENARIO_ID)
        if not sc:
            print(f"ABORTA: el escenario {SCENARIO_ID} no existe en esta base.")
            return 3
        if (sc["year"], sc["version"]) != (ANIO, VERSION):
            print(f"ABORTA: ese id es {sc['year']} {sc['version']!r}, "
                  f"no {ANIO} {VERSION!r}. No se escribe en el escenario equivocado.")
            return 4
        if sc["status"] == "locked":
            print("ABORTA: el escenario está bloqueado.")
            return 5

        deptos = sorted({p[0] for p in POSICIONES})
        faltan = [d for d in deptos if not await conn.fetchval(
            "SELECT 1 FROM department_catalog WHERE dept_code=$1", d)]
        if faltan:
            print(f"ABORTA: estos departamentos no están en el catálogo: {faltan}.")
            return 6

        tcs = await conn.fetch(
            "SELECT month, tc_crc_usd FROM exchange_rates WHERE scenario_id=$1 "
            "ORDER BY month", SCENARIO_ID)
        if len(tcs) != 12 or any(t["tc_crc_usd"] == 0 for t in tcs):
            print("ABORTA: al escenario le faltan tipos de cambio (o alguno está en 0). "
                  "Sin TC el salario en colones no se puede convertir.")
            return 7

        nombres = {r["dept_code"]: r["dept_name"] for r in await conn.fetch(
            "SELECT dept_code, dept_name FROM department_catalog "
            "WHERE dept_code = ANY($1::varchar[])", deptos)}
        previas = await conn.fetchval(
            "SELECT count(*) FROM payroll_positions WHERE scenario_id=$1 "
            "AND dept_code = ANY($2::varchar[])", SCENARIO_ID, deptos)

        print(f"Planilla {ANIO} de {ESPERADO} → escenario {sc['type']} "
              f"{sc['version']} ({sc['status']})")
        print(f"  {len(POSICIONES)} posiciones en {len(deptos)} departamentos")
        print(f"  TC {tcs[0]['tc_crc_usd']}  ·  se reemplazan {previas} posiciones "
              "previas de esos departamentos")
        for d in deptos:
            filas = [p for p in POSICIONES if p[0] == d]
            print(f"  {d:<6} {nombres[d]:<24} {len(filas):>2} pos · "
                  f"FTE dic {round(sum(f[5][11] for f in filas), 2):>5} · "
                  f"CRC {sum(f[4] for f in filas):>10,}")

        if not aplicar:
            print("\n(corrida en seco — agregar --aplicar)")
            return 0

        cols = (["id", "scenario_id", "hotel_id", "dept_code", "dept_name",
                 "position_code", "position_name", "employee_name", "salary_amount",
                 "salary_currency"] + MESES)
        ph = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
        inserta = f"INSERT INTO payroll_positions ({', '.join(cols)}) VALUES ({ph})"

        async with conn.transaction():
            # Reemplazo POR DEPARTAMENTO, igual que el import de Excel del app: un
            # departamento que no venga en este archivo no se toca.
            await conn.execute(
                "DELETE FROM payroll_concept_entries WHERE position_id IN ("
                "  SELECT id FROM payroll_positions WHERE scenario_id=$1 "
                "   AND dept_code = ANY($2::varchar[]))", SCENARIO_ID, deptos)
            await conn.execute(
                "DELETE FROM payroll_positions WHERE scenario_id=$1 "
                "AND dept_code = ANY($2::varchar[])", SCENARIO_ID, deptos)
            for depto, codigo, puesto, persona, salario, fte in POSICIONES:
                await conn.execute(inserta, str(uuid.uuid4()), SCENARIO_ID, ESPERADO,
                                   depto, nombres[depto], codigo, puesto, persona,
                                   salario, "CRC", *fte)

        print("\nComo quedó:")
        for r in await conn.fetch(
                "SELECT dept_code, dept_name, count(*) n, sum(salary_amount) sal, "
                "sum(fte_dec) fte FROM payroll_positions WHERE scenario_id=$1 "
                "GROUP BY dept_code, dept_name ORDER BY dept_code", SCENARIO_ID):
            print(f"  {r['dept_code']:<6} {r['dept_name']:<24} {r['n']:>2} pos · "
                  f"FTE dic {r['fte']:>7} · CRC {r['sal']:>12,.0f}")
        t = await conn.fetchrow(
            "SELECT count(*) n, sum(salary_amount) sal, sum(fte_dec) fte "
            "FROM payroll_positions WHERE scenario_id=$1", SCENARIO_ID)
        print(f"  {'TOTAL':<6} {'':<24} {t['n']:>2} pos · FTE dic {t['fte']:>7} · "
              f"CRC {t['sal']:>12,.0f}")
        print("\nFalta «Recalcular y empujar al P&L» en el app: este guion no calcula.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--aplicar", action="store_true")
    raise SystemExit(asyncio.run(main(p.parse_args().aplicar)))
