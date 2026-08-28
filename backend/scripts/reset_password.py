# -*- coding: utf-8 -*-
"""Recuperar el acceso de un usuario — listar, cambiar clave, reactivar.

## Por qué existe (2026-08-27)

El primer administrador se crea desde la pantalla de login (`POST /auth/bootstrap`)
y esa puerta **se cierra sola** apenas existe un usuario. A partir de ahí, cambiar
una clave necesita `PATCH /auth/users/{id}`, que exige sesión de admin.

Si el único admin pierde el acceso, eso es un círculo: hace falta estar adentro
para poder volver a entrar. No había ninguna salida — este script es esa salida.

## Por qué un script y no un UPDATE a mano

La clave no se guarda en texto: es `pbkdf2_sha256$200000$<salt>$<hash>`
(`app/auth.py`). Un `UPDATE users SET password_hash='...'` con cualquier otra
cosa adentro **no da error**: guarda bien y el login sigue fallando, ahora sin
que nadie entienda por qué. Acá se usa la misma función que usa la app.

## Uso

    # 1. Apuntar a la base (NO se escribe en ningún archivo del repo)
    #    PowerShell:
    $env:DATABASE_URL = "postgresql://...la URL publica de Railway..."
    #    bash:
    export DATABASE_URL="postgresql://..."

    # 2. Ver qué usuarios hay y en qué estado
    python -m scripts.reset_password --listar

    # 3. Cambiar la clave
    python -m scripts.reset_password --email vos@ejemplo.com --clave "una nueva"

    # 4. Si además está inactivo o no es admin
    python -m scripts.reset_password --email vos@ejemplo.com --clave "una nueva" \
        --activar --rol admin

También se puede correr desde la shell del servicio en Railway, donde
`DATABASE_URL` ya está puesta y la credencial no pasa por ninguna otra parte.

⚠️ **Este script ESCRIBE.** Es la excepción a la convención de `scripts/`, que
es de solo lectura (`_sql.py` rechaza todo lo que no sea SELECT). Por eso pide
confirmación salvo que se le pase `--si`.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

#: Lo mismo que exige `POST /auth/bootstrap` y `PATCH /auth/users/{id}`. Si acá
#: fuera más permisivo, el script dejaría poner una clave que la app después
#: rechaza al cambiarla desde la pantalla.
CLAVE_MINIMA = 8


def _url_o_morir() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit(
            "Falta DATABASE_URL.\n\n"
            "  PowerShell:  $env:DATABASE_URL = \"postgresql://...\"\n"
            "  bash:        export DATABASE_URL=\"postgresql://...\"\n\n"
            "En Railway: servicio Postgres -> Variables -> DATABASE_PUBLIC_URL\n"
            "(la publica, no la interna: la interna solo resuelve dentro de Railway).")
    return url


async def _listar(db) -> int:
    from sqlalchemy import select
    from app.models.user import User

    filas = (await db.execute(select(User).order_by(User.created_at))).scalars().all()
    if not filas:
        print("\n(!) NO hay usuarios en esta base.\n")
        print("    Entonces no hace falta este script: abri la app y te va a")
        print("    ofrecer «crear el primer administrador». Esa puerta esta")
        print("    abierta justamente porque la tabla esta vacia.\n")
        return 0

    print(f"\n{len(filas)} usuario(s):\n")
    print(f"  {'correo':<38} {'rol':<20} {'activo':<7} creado")
    print(f"  {'-'*38} {'-'*20} {'-'*7} {'-'*10}")
    for u in filas:
        creado = u.created_at.date().isoformat() if u.created_at else "?"
        marca = "si" if u.active else "NO"
        print(f"  {u.email:<38} {u.role:<20} {marca:<7} {creado}")
    print()
    inactivos = [u.email for u in filas if not u.active]
    if inactivos:
        print("  (!) Inactivo(s): " + ", ".join(inactivos))
        print("      Un usuario inactivo recibe el MISMO error que una clave")
        print("      equivocada — la app no distingue, a proposito. Reactivalo")
        print("      con --activar.\n")
    if not any(u.role == "admin" and u.active for u in filas):
        print("  (!) No hay ningun admin ACTIVO: nadie puede crear usuarios")
        print("      desde la app. Usa --rol admin.\n")
    return len(filas)


async def _crear(db, email: str, clave: str, rol: str) -> None:
    """Alta de un usuario cuando el bootstrap ya se cerró.

    ⚠️ El bootstrap de la app (`POST /auth/bootstrap`) solo abre con la tabla
    VACIA. Si una instalacion quedo con usuarios que no son de nadie de la casa
    —el caso que se encontro el 2026-08-27: la base de Amarena nacio con las 9
    personas del equipo de Corcovado y ningun admin— no hay forma de entrar:
    el bootstrap esta cerrado y no hay admin que pueda dar de alta a nadie.
    Esta es la salida.
    """
    from sqlalchemy import select
    from app.auth import hash_password
    from app.models.user import User, ROLES

    if rol not in ROLES:
        raise SystemExit(f"Rol invalido {rol!r}. Validos: {', '.join(ROLES)}")

    em = email.strip().lower()
    if (await db.execute(select(User).where(User.email == em))).scalar_one_or_none():
        raise SystemExit(
            f"{em} YA existe. Para cambiarle la clave, corre lo mismo sin --crear.")

    db.add(User(email=em, name=em.split("@")[0], role=rol, active=True,
                password_hash=hash_password(clave)))
    await db.commit()
    print(f"\n[ok] Usuario CREADO: {em}  (rol={rol}, activo)")
    print("\n     Entra a la app con esa clave y cambiala desde Admin -> Usuarios.")
    print("     La clave que pasaste por linea de comandos queda en el historial")
    print("     de la terminal — no la dejes como definitiva.\n")


async def _cambiar(db, email: str, clave: str, activar: bool, rol: str | None) -> None:
    from sqlalchemy import select
    from app.auth import hash_password
    from app.models.user import User

    # ⚠️ Validar el rol ANTES de tocar el objeto. Si se valida despues de
    # asignar el hash, lo unico que evita dejar la fila a medias es que la
    # sesion cierre sin commit — funciona, pero por un efecto secundario. Un
    # `try` mal puesto mas adelante, o un commit agregado antes, lo rompe en
    # silencio y la clave queda cambiada con el rol viejo.
    if rol:
        from app.models.user import ROLES
        if rol not in ROLES:
            raise SystemExit(f"Rol invalido {rol!r}. Validos: {', '.join(ROLES)}")

    em = email.strip().lower()
    u = (await db.execute(select(User).where(User.email == em))).scalar_one_or_none()
    if not u:
        # Se listan los que sí existen: el error mas comun es un correo con otra
        # forma (mayusculas, dominio distinto), no un usuario que falta.
        otros = (await db.execute(select(User.email))).scalars().all()
        raise SystemExit(
            f"No existe el usuario {em!r}.\n"
            + ("Los que hay: " + ", ".join(otros) if otros
               else "La tabla esta vacia: abri la app y crea el primer admin."))

    antes = {"activo": u.active, "rol": u.role}
    u.password_hash = hash_password(clave)
    if activar:
        u.active = True
    if rol:
        u.role = rol
    await db.commit()

    print(f"\n[ok] Clave cambiada para {u.email}")
    if antes["activo"] != u.active:
        print(f"     activo: {antes['activo']} -> {u.active}")
    if antes["rol"] != u.role:
        print(f"     rol:    {antes['rol']} -> {u.role}")
    print("\n     Entra a la app con esa clave y cambiala desde Admin -> Usuarios.")
    print("     La clave que pasaste por linea de comandos queda en el historial")
    print("     de la terminal — no la dejes como definitiva.\n")


async def main() -> None:
    p = argparse.ArgumentParser(
        description="Recuperar acceso: listar usuarios, cambiar clave, reactivar.")
    p.add_argument("--listar", action="store_true",
                   help="solo mostrar los usuarios y su estado (no escribe nada)")
    p.add_argument("--email", help="correo del usuario a cambiar")
    p.add_argument("--clave", help=f"clave nueva (minimo {CLAVE_MINIMA} caracteres)")
    p.add_argument("--activar", action="store_true",
                   help="ademas, marcarlo activo")
    p.add_argument("--rol", help="ademas, cambiarle el rol (ej: admin)")
    p.add_argument("--crear", action="store_true",
                   help="dar de alta el usuario (falla si ya existe)")
    p.add_argument("--si", action="store_true",
                   help="no preguntar antes de escribir")
    args = p.parse_args()

    _url_o_morir()
    from app.db import SessionLocal, DATABASE_URL

    # Se muestra el host, NUNCA la URL entera: lleva la contrasena de Postgres
    # adentro y esto se pega en chats y tickets.
    host = DATABASE_URL.split("@")[-1].split("/")[0] if "@" in DATABASE_URL else "?"
    print(f"\nBase: {host}")

    async with SessionLocal() as db:
        if args.listar or not (args.email or args.clave):
            await _listar(db)
            if not (args.email or args.clave):
                print("Para cambiar una clave:")
                print("  python -m scripts.reset_password --email X --clave Y\n")
            return

        if not (args.email and args.clave):
            raise SystemExit("Hacen falta --email y --clave juntos.")
        if len(args.clave) < CLAVE_MINIMA:
            raise SystemExit(f"La clave necesita al menos {CLAVE_MINIMA} caracteres.")

        await _listar(db)
        accion = "DAR DE ALTA a" if args.crear else "CAMBIAR LA CLAVE de"
        if not args.si:
            print(f"Se va a {accion} {args.email.strip().lower()} en {host}")
            if input("Escribi 'si' para continuar: ").strip().lower() != "si":
                raise SystemExit("Cancelado. No se escribio nada.")
        if args.crear:
            await _crear(db, args.email, args.clave, args.rol or "admin")
        else:
            await _cambiar(db, args.email, args.clave, args.activar, args.rol)


if __name__ == "__main__":
    asyncio.run(main())
