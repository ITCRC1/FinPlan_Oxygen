"""
Seed de una instalación: hotel, tipos de habitación, equipo, catálogo de
departamentos y el motor de mapeo del P&L.

Corre en cada arranque y es idempotente. Cada hotel es un PROYECTO APARTE
—base propia, app propia— así que este script es lo que hace que una
instalación nueva nazca funcionando en vez de nacer vacía.

Identidad del hotel, por entorno. Este repositorio es el despliegue de Amarena,
así que ese es el default —ver `app/hotel_actual.py` para por qué—, pero el
entorno manda siempre:

    HOTEL_ID=AMA HOTEL_NAME="Amarena Canvas Beach Hotel" HOTEL_SHORT_NAME=Amarena HOTEL_ROOMS=24 HOTEL_TC_USD=530.0000

    cd backend && python -m app.seed
"""
import asyncio
import os
import uuid as _uuid
from decimal import Decimal
from sqlalchemy import select, func
from app.db import engine, SessionLocal, Base
from app.models.hotel import Hotel
from app.models.room_type_config import RoomTypeConfig
from app.seed_data import room_types_estandar
from app.models.user import User
# Importar todos los modelos para que Base.metadata los registre
from app.models import Account, PayrollAccount, Scenario, ExchangeRate  # noqa

# ⚠️ NO se siembra ningún usuario. El primer administrador se crea desde la
# pantalla de login, que ofrece «crear el primer administrador» mientras la tabla
# `users` esté vacía y se cierra sola apenas exista uno (`POST /auth/bootstrap`).
#
# Este repo tenía acá las nueve personas del equipo de Corcovado —su correo real
# y una contraseña compartida en texto plano. Gateadas por hotel, así que a
# Amarena nunca le habrían entrado; pero eran datos personales y una credencial
# viva de otra propiedad, viajando en un repositorio que ya no es de ella.
# Salieron el 2026-08-21.

# Identidad del hotel de ESTA instalación. Sale del entorno; el default es
# Amarena porque este repositorio es el despliegue de Amarena — ver
# `app/hotel_actual.py`, que explica por qué NO es Corcovado.
HOTEL_ID = os.getenv("HOTEL_ID", "AMA")
HOTEL_NAME = os.getenv("HOTEL_NAME", "Amarena Canvas Beach Hotel")
HOTEL_SHORT = os.getenv("HOTEL_SHORT_NAME", "Amarena")
# ⚠️ Default 0, no 30. Un número plausible pero ajeno —las 30 de Corcovado— se
# ve perfectamente normal y está mal: se arrastra a RevPAR, a ocupación y al P&L
# sin que nada dé error. En 0 se nota que falta. La verdad se carga en
# Master Data → Provisionamiento.
HOTEL_ROOMS = int(os.getenv("HOTEL_ROOMS", "0"))
# El TC sí arranca en un valor real: es divisor de todo salario en colones y un
# 0 acá reventaría el cálculo de planilla en vez de mostrarse vacío.
HOTEL_TC = os.getenv("HOTEL_TC_USD", "530.0000")


async def seed():
    # El esquema lo crea Alembic ('alembic upgrade head'). El seed SOLO inserta
    # datos — nunca crea tablas (evita choques de índices duplicados con Alembic).
    async with SessionLocal() as db:
        # Hotel CWL
        hotel = await db.get(Hotel, HOTEL_ID)
        if not hotel:
            hotel = Hotel(
                id=HOTEL_ID,
                name=HOTEL_NAME,
                short_name=HOTEL_SHORT,
                rooms=HOTEL_ROOMS,
                tc_usd_default=Decimal(HOTEL_TC),
                closed_months="",     # sin meses cerrados — todos se calculan por fórmula
                active=True,
            )
            db.add(hotel)
            print(f"✓ Hotel {HOTEL_ID} creado ({HOTEL_NAME})")
        else:
            print(f"  Hotel {HOTEL_ID} ya existe — omitido")

        # Tipos de habitación: se siembran los CÓDIGOS del estándar del grupo,
        # con el nombre en blanco. Los códigos (`BL01`, `BI02`…) son los MISMOS
        # en todas las propiedades porque son lo que liga una categoría entre
        # escenarios, reportes y hoteles — el reporte de Junta cruza por código,
        # no por id ni por nombre (owner, 2026-08-27).
        #
        # ⚠️ Lo que NO se siembra son los NOMBRES. Poner acá los de Corcovado
        # dejaría las noches reales de otra propiedad guardadas bajo una
        # categoría que no es suya. El rótulo se edita en Master Data → Tipos de
        # habitación, y es lo único que se edita: el código y la posición quedan
        # clavados al crearse (el PUT devuelve 409).
        #
        # Se aplica UNA sola vez, cuando el hotel no tiene ninguna categoría.
        # No reafirma: si ya hay filas, este bloque no las toca. Un seed que
        # renombrara en cada arranque le pisaría al owner lo que acaba de cargar.
        result = await db.execute(
            select(RoomTypeConfig).where(RoomTypeConfig.hotel_id == HOTEL_ID)
        )
        existing_types = result.scalars().all()
        if existing_types:
            print(f"  Tipos de habitación ya existen ({len(existing_types)}) — omitidos")
        else:
            for fila in room_types_estandar():
                db.add(RoomTypeConfig(
                    id=str(_uuid.uuid4()), hotel_id=HOTEL_ID,
                    sort_order=fila["sort_order"], code=fila["code"],
                    name=fila["name"], short_name=fila["short_name"],
                    units=fila["units"], pax_min=fila["pax_min"],
                    pax_max=fila["pax_max"], active=True,
                ))
            codigos = ", ".join(f["code"] for f in room_types_estandar())
            print(f"  {HOTEL_ID}: {len(room_types_estandar())} categorías estándar "
                  f"sembradas ({codigos}) — renombralas en Master Data")

        # Usuarios: ninguno. El primer admin se crea desde la pantalla de login
        # (ver el comentario de arriba). Que la tabla esté vacía es lo que
        # habilita ese formulario.
        usuarios = (await db.execute(select(func.count()).select_from(User))).scalar_one()
        if usuarios:
            print(f"  {usuarios} usuario(s) ya existen — el bootstrap está cerrado")
        else:
            print("  Sin usuarios — abrí la app y creá el primer administrador")

        await db.commit()

    # department_catalog (universo canónico de deptos, derivado de las constantes)
    try:
        from app.seed_department_catalog import seed as seed_dept_catalog
        await seed_dept_catalog()
    except Exception as e:  # no romper el boot si la migración aún no corrió
        print(f"  department_catalog seed omitido: {e}")

    # Motor de mapeo del P&L. Va al final porque es lo más pesado (899 filas) y
    # porque nada de lo anterior depende de él.
    try:
        from app.seed_mapping import seed_mapping
        async with SessionLocal() as db:
            await seed_mapping(db)
    except Exception as e:
        print(f"  seed de mapeo omitido: {e}")

    # Reporte `Owners Q` (tab Reports): las 48 filas, el ruteo de las 68
    # `Línea P&L` y la capacidad. Va DESPUÉS del mapeo porque el gate de
    # cobertura se mide contra las reglas que aquél acaba de sembrar.
    try:
        from app.seed_owners_q import seed_owners_q, verificar_cobertura
        async with SessionLocal() as db:
            r = await seed_owners_q(db)
            await db.commit()
            cob = await verificar_cobertura(db)
        print(f"  owners_q: {r['filas']['total']} filas "
              f"({r['filas']['nuevas']} nuevas, {r['filas']['cambiadas']} actualizadas), "
              f"{r['ruteo']['total']} líneas ruteadas, "
              f"{r['capacidad']['nuevas']} meses de capacidad")
        if cob["ok"]:
            print(f"  owners_q cobertura ✓ {cob['lineas_ruteadas']} líneas ruteadas")
        else:
            # No se rompe el arranque —dejaría la app entera abajo— pero grita.
            # El endpoint del reporte SÍ falla si la cobertura no está.
            print(f"  ⚠️  owners_q COBERTURA INCOMPLETA — huérfanas: {cob['huerfanas']} "
                  f"destino inexistente: {cob['destino_inexistente']}")
        if cob["ruteadas_sin_regla"]:
            print(f"  owners_q: ruteadas sin reglas todavía: {cob['ruteadas_sin_regla']}")
    except Exception as e:
        print(f"  seed de owners_q omitido: {e}")

    # Catálogo de cuentas estadísticas (clase 9). Igual que el mapeo: la lista de
    # verdad vive en git, no en la base. NO sale de la tabla `accounts`, que está
    # vacía en producción (ver app/seed_stats.py).
    try:
        from app.seed_stats import seed_stats
        async with SessionLocal() as db:
            r = await seed_stats(db)
            await db.commit()
        print(f"  stat_accounts: {r['total']} cuentas "
              f"({r['nuevas']} nuevas, {r['cambiadas']} actualizadas)")
        if r["sobran"]:
            print(f"  ⚠️  cuentas estadísticas en base que no están en el JSON: "
                  f"{r['sobran']} (no se borran)")
    except Exception as e:
        print(f"  seed de estadísticas omitido: {e}")

    # Market codes de Opera. NO pisa lo que el owner edite en la app.
    try:
        from app.seed_market_codes import seed_market_codes
        async with SessionLocal() as db:
            r = await seed_market_codes(db)
            await db.commit()
        print(f"  market_codes: {r['total']} códigos ({r['nuevos']} nuevos)")
    except Exception as e:
        print(f"  seed de market codes omitido: {e}")

    # Canales comerciales: la lista que decide quién cobra.
    try:
        from app.seed_canales_comerciales import seed_canales
        async with SessionLocal() as db:
            r = await seed_canales(db)
            await db.commit()
        print(f"  canales_comerciales: {r['total']} ({r['nuevos']} nuevos)")
    except Exception as e:
        print(f"  seed de canales omitido: {e}")

    # Costos para negociación de grupos: el mapa de temporadas y los
    # parámetros del modelo. No pisa lo que el owner edite en la app.
    try:
        from app.seed_costos_grupos import (
            seed_composicion, seed_costos_grupos, seed_tarifas_rack)
        async with SessionLocal() as db:
            r = await seed_costos_grupos(db)
            await db.commit()
            rc = await seed_composicion(db)
            await db.commit()
            rr = await seed_tarifas_rack(db)
            await db.commit()
        print(f"  costos_grupos: {rc['filas']} lineas de composicion "
              f"({rc['nuevas']} nuevas)")
        print(f"  costos_grupos: {rr['filas']} tarifas rack "
              f"({rr['nuevas']} nuevas)")
        print(f"  costos_grupos: {r['temporadas']} temporadas "
              f"({r['temporadas_nuevas']} nuevas), {r['parametros']} parámetros "
              f"({r['parametros_nuevos']} nuevos)")
    except Exception as e:
        print(f"  seed de costos_grupos omitido: {e}")

    # Configuración de Guillermo. ⚠️ El manifiesto de reportes esperados NO se
    # siembra: su contenido es la decisión D-1 del owner y no se inventa. Un
    # manifiesto inventado haría que Guillermo reclamara archivos que nadie
    # prometió y diera por completo lo que no lo está.
    try:
        from app.seed_guillermo import seed_guillermo, seed_manifiesto
        async with SessionLocal() as db:
            rg = await seed_guillermo(db)
            await db.commit()
            rm = await seed_manifiesto(db)
            await db.commit()
        print(f"  guillermo: {rg['total']} parámetros ({rg['nuevos']} nuevos)")
        print(f"  guillermo: {rm['total']} reportes esperados ({rm['nuevos']} nuevos)")
    except Exception as e:
        print(f"  seed de guillermo omitido: {e}")

    # Break-Even: los departamentos y la clasificacion fijo/variable.
    #
    # ATENCION: entro aca el 2026-08-20. Antes se cargaba con un script a mano
    # que NADIE llamaba, asi que un clon levantaba con las dos tablas vacias, y
    # eso no da error: Break-Even muestra ceros y Costos de Grupos pierde el
    # `be_section` con que separa PAYROLL de COST OF SALES. Cero se lee igual
    # que "no gasto".
    #
    # Es por propiedad: sin `seed_data/<HOTEL_ID>/break_even/` no siembra nada y
    # NO hereda los porcentajes de Corcovado.
    try:
        from app.seed_break_even import seed_break_even
        async with SessionLocal() as db:
            rb = await seed_break_even(db)
            await db.commit()
        if rb["sembrado"]:
            print(f"  break_even: {rb['departamentos']} departamentos "
                  f"({rb['departamentos_nuevos']} nuevos), {rb['reglas']} reglas "
                  f"({rb['reglas_nuevas']} nuevas)")
        else:
            print(f"  break_even: {rb['hotel']} no trae semilla - se carga en la app")
    except Exception as e:
        print(f"  seed de break_even omitido: {e}")

    print("\n✅ Seed completado.")
    print(f"   Hotel: {HOTEL_ID} — {HOTEL_NAME} ({HOTEL_ROOMS} hab., TC {HOTEL_TC})")
    if HOTEL_ROOMS == 0:
        print("   ⚠️  HOTEL_ROOMS=0 — cargá el número real en Master Data → Provisionamiento")
    print("   Próximos pasos: 1) abrí la app y creá el primer administrador")
    print("                   2) Master Data → Provisionamiento y Tipos de habitación")
    print("                   3) POST /api/scenarios/ para crear el primer Budget")


if __name__ == "__main__":
    asyncio.run(seed())
