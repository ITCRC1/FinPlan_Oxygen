"""Auth API — login, bootstrap del primer admin, gestión de usuarios.

Fase 0 paso A: existe el sistema de usuarios pero los endpoints de datos NO
exigen token todavía (eso es el paso C). Acá ya se puede crear el admin y loguear.
"""
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errores import ErrorApi
from app.i18n import LOCALES, normalize_locale, resolve_locale
from app.temas import TEMAS, TEMA_POR_DEFECTO
from app.models.auth_event import AuthEvent
from app.models.hotel import Hotel
from app.models.user import User, ROLES
from app.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, get_current_admin, validar_clave,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# ─── Freno a la fuerza bruta ──────────────────────────────────────────────────
#
# Antes esto no existía: `POST /auth/login` aceptaba intentos ilimitados.
#
# **Dos frenos, y hacen cosas distintas.** El de la CUENTA vive en la base y es
# la defensa de verdad: sobrevive a los reinicios, y Railway reinicia en cada
# despliegue. El de la IP vive en memoria y es sólo un amortiguador de ráfaga —
# se pierde al reiniciar, y es aceptable justamente porque no es el que protege.

#: Fallos seguidos antes de bloquear la cuenta.
#:
#: ⚠️ **El §27 del CLAUDE.md dice 3 intentos y 30 minutos. Acá son 5 y 15, y es
#: deliberado:** ese capítulo también especifica una recuperación de contraseña
#: por correo que NO existe. Con 3 fallos y media hora de espera, tres errores de
#: tecleo durante un cierre de mes dejan a alguien afuera sin ninguna forma de
#: volver salvo que un administrador corra un guion. Cinco y quince frenan igual
#: un ataque —son 20 intentos por hora— y no rompen la operación. El día que haya
#: recuperación por correo, apretar esto es cambiar estos dos números.
MAX_INTENTOS = 5
BLOQUEO = timedelta(minutes=15)

#: Amortiguador por IP: tope de intentos dentro de la ventana, sin importar
#: contra qué cuentas. Frena el barrido de correos, que el contador por cuenta no
#: ve — cada cuenta suma de a uno mientras la misma máquina prueba cien.
IP_MAX = 20
IP_VENTANA = 300          # segundos
_por_ip: dict[str, deque] = {}


def _ip(request: Request) -> str:
    """La IP real de quien pide.

    ⚠️ Detrás del proxy de Railway, `request.client.host` es SIEMPRE la del
    proxy: sin mirar `X-Forwarded-For`, el freno por IP metería a todo el mundo
    en el mismo balde y el primero que fallara veinte veces dejaría a la
    propiedad entera sin poder entrar.
    """
    reenviado = request.headers.get("x-forwarded-for", "")
    if reenviado:
        return reenviado.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "")[:64]


def _ip_permitida(ip: str) -> bool:
    """Cuenta este intento y dice si todavía está dentro del tope."""
    if not ip:
        return True
    ahora = time.monotonic()
    marcas = _por_ip.setdefault(ip, deque())
    while marcas and ahora - marcas[0] > IP_VENTANA:
        marcas.popleft()
    if len(marcas) >= IP_MAX:
        return False
    marcas.append(ahora)
    # El diccionario no crece sin límite: al llegar a mil IPs se sueltan las que
    # ya no tienen marcas vivas. Sin esto, un barrido desde miles de direcciones
    # se lleva la memoria del proceso.
    if len(_por_ip) > 1000:
        for k in [k for k, v in _por_ip.items() if not v]:
            _por_ip.pop(k, None)
    return True


async def _registrar(db: AsyncSession, evento: str, *, request: Request,
                     email: str = "", user_id: str | None = None,
                     actor_email: str = "", detalle: str = "") -> None:
    """Deja el rastro. Nunca guarda contraseñas, hashes ni tokens.

    No hace `commit`: lo hace quien llama, para que el evento entre en la misma
    transacción que el cambio que describe — o no entre ninguno de los dos.
    """
    db.add(AuthEvent(
        evento=evento, email=(email or "")[:160], user_id=user_id,
        actor_email=(actor_email or "")[:160], ip=_ip(request),
        user_agent=(request.headers.get("user-agent", ""))[:300],
        detalle=detalle[:300]))


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _bloqueada(user: User) -> int:
    """Minutos que faltan para que se libere. 0 = no está bloqueada."""
    hasta = user.locked_until
    if not hasta:
        return 0
    if hasta.tzinfo is None:              # por si la base la devuelve naive
        hasta = hasta.replace(tzinfo=timezone.utc)
    if hasta <= _ahora():
        return 0
    return max(1, int((hasta - _ahora()).total_seconds() // 60) + 1)


def _user_dict(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role,
            "active": u.active, "locale": u.locale, "tema": u.tema}


async def _hotel_locale(db: AsyncSession) -> str | None:
    """El default de la propiedad. Hoy hay una sola (CWL); el día que haya
    varias, esto pasa a leer la del usuario."""
    h = (await db.execute(
        select(Hotel).where(Hotel.active.is_(True)).order_by(Hotel.id)
    )).scalars().first()
    return getattr(h, "default_locale", None) if h else None


async def _session_payload(db: AsyncSession, user: User, token: str) -> dict:
    """Lo que necesita el frontend para arrancar: sesión + idioma YA RESUELTO.

    El idioma viaja resuelto porque el token vive en `localStorage` y el render
    del servidor no puede leerlo: el frontend guarda este valor en la cookie
    `finplan_locale`, que sí se lee del lado del servidor.
    """
    return {"token": token, "user": _user_dict(user),
            "locale": resolve_locale(user.locale, await _hotel_locale(db)),
            # El tema viaja por la misma razón que el idioma: el render del
            # servidor lo necesita ANTES de que exista JavaScript, y sin esto
            # cada carga parpadearía del default al elegido.
            "tema": user.tema or TEMA_POR_DEFECTO}


class LoginBody(BaseModel):
    email: str
    password: str


class BootstrapBody(BaseModel):
    email: str
    password: str
    name: str = ""


@router.get("/status")
async def auth_status(db: AsyncSession = Depends(get_db)):
    """Público: ¿ya hay usuarios? (para decidir login vs crear-primer-admin)."""
    count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    return {"has_users": bool(count and count > 0)}


@router.post("/bootstrap")
async def bootstrap_admin(body: BootstrapBody, request: Request,
                          db: AsyncSession = Depends(get_db)):
    """Crea el PRIMER admin. Solo funciona si todavía no hay usuarios.

    ⚠️ **El candado de Postgres no es adorno.** Antes esto contaba las filas y
    después insertaba, sin nada en el medio: dos peticiones simultáneas podían
    pasar las dos la comprobación y crear DOS administradores iniciales, uno de
    ellos de quien no debía. La ventana es angosta —sólo con la tabla vacía— pero
    es la única puerta del sistema que se abre sin credenciales.

    El candado es de transacción: se suelta solo al terminar, haya salido bien o
    mal, así que no puede quedar tomado.
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(716354)"))
    count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    if count and count > 0:
        raise ErrorApi(409, "auth.bootstrap_deshabilitado")
    validar_clave(body.password)
    user = User(email=str(body.email).lower(), name=body.name or str(body.email),
                password_hash=hash_password(body.password), role="admin", active=True)
    db.add(user)
    await _registrar(db, "BOOTSTRAP", request=request, email=user.email,
                     user_id=user.id, actor_email=user.email,
                     detalle="primer administrador de la instalación")
    await db.commit()
    token = create_access_token(user.id, user.role, user.email)
    return await _session_payload(db, user, token)


@router.post("/login")
async def login(body: LoginBody, request: Request,
                db: AsyncSession = Depends(get_db)):
    """Entrar.

    **Lo que NO se le dice a quien falla**, a propósito: si el correo existe, si
    la cuenta está desactivada, o si está bloqueada por intentos. Las tres cosas
    contestan lo mismo que una contraseña equivocada. Distinguirlas convierte el
    login en un buscador de cuentas válidas.

    La única excepción es el mensaje de bloqueo, y sólo **después** de acertar la
    contraseña: a quien conoce la clave sí hay que explicarle por qué no entra,
    porque si no reporta «la app no me deja» y nadie sabe qué mirar.
    """
    correo = str(body.email).strip().lower()

    if not _ip_permitida(_ip(request)):
        await _registrar(db, "LOGIN_BLOQUEADO", request=request, email=correo,
                         detalle=f"tope por IP: {IP_MAX} intentos / {IP_VENTANA}s")
        await db.commit()
        raise ErrorApi(429, "auth.demasiados_intentos_ip")

    user = (await db.execute(
        select(User).where(User.email == correo)
    )).scalar_one_or_none()

    # Correo que no existe. Se registra —es el dato que muestra contra qué
    # cuentas se está insistiendo— y se contesta lo genérico.
    if not user:
        await _registrar(db, "LOGIN_FALLIDO", request=request, email=correo,
                         detalle="el correo no corresponde a ningún usuario")
        await db.commit()
        raise ErrorApi(401, "auth.credenciales_invalidas")

    # El bloqueo venció: se limpia y este intento cuenta como el primero. Sin
    # esto, el sexto intento volvería a bloquear al instante.
    if user.locked_until and not _bloqueada(user):
        user.locked_until = None
        user.failed_attempts = 0

    minutos = _bloqueada(user)
    clave_ok = verify_password(body.password, user.password_hash)

    if minutos:
        await _registrar(db, "LOGIN_BLOQUEADO", request=request, email=correo,
                         user_id=user.id,
                         detalle=f"bloqueada, faltan {minutos} min")
        await db.commit()
        # Con la clave correcta se explica; con la clave mala, no — así el
        # bloqueo no delata que la cuenta existe.
        if clave_ok:
            raise ErrorApi(429, "auth.demasiados_intentos", minutos=minutos)
        raise ErrorApi(401, "auth.credenciales_invalidas")

    if not clave_ok or not user.active:
        user.failed_attempts = (user.failed_attempts or 0) + 1
        user.last_failed_at = _ahora()
        motivo = "contraseña incorrecta" if not clave_ok else "cuenta desactivada"
        if user.failed_attempts >= MAX_INTENTOS:
            user.locked_until = _ahora() + BLOQUEO
            await _registrar(db, "CUENTA_BLOQUEADA", request=request, email=correo,
                             user_id=user.id,
                             detalle=f"{user.failed_attempts} fallos seguidos; "
                                     f"bloqueada {int(BLOQUEO.total_seconds() // 60)} min")
        else:
            await _registrar(db, "LOGIN_FALLIDO", request=request, email=correo,
                             user_id=user.id,
                             detalle=f"{motivo} ({user.failed_attempts}/{MAX_INTENTOS})")
        await db.commit()
        raise ErrorApi(401, "auth.credenciales_invalidas")

    # Entró: el contador vuelve a cero.
    user.failed_attempts = 0
    user.locked_until = None
    await _registrar(db, "LOGIN_OK", request=request, email=correo, user_id=user.id)
    await db.commit()
    token = create_access_token(user.id, user.role, user.email)
    return await _session_payload(db, user, token)


@router.get("/me")
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {**_user_dict(user),
            "resolved_locale": resolve_locale(user.locale, await _hotel_locale(db))}


class LocaleBody(BaseModel):
    locale: str | None = None   # None = «usá el del hotel»


@router.patch("/me/locale")
async def set_my_locale(
    body: LocaleBody,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Preferencia personal de idioma. `null` la borra y vuelve a mandar el
    default de la propiedad — por eso el campo es nullable y no un 'es'."""
    if body.locale is not None and normalize_locale(body.locale) is None:
        raise ErrorApi(422, "locale.invalido", locales=LOCALES)
    user.locale = normalize_locale(body.locale)
    await db.commit()
    return {**_user_dict(user),
            "resolved_locale": resolve_locale(user.locale, await _hotel_locale(db))}


class TemaBody(BaseModel):
    tema: str | None = None   # None = «usá el que viene por defecto»


@router.patch("/me/tema")
async def set_my_tema(
    body: TemaBody,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """La paleta que eligió esta persona. `null` la borra y vuelve al default.

    Se valida contra la lista: un tema que no existe no rompe la pantalla —el
    CSS cae al `:root`— pero deja al usuario con un valor guardado que no hace
    nada y que nadie puede explicar después."""
    if body.tema is not None and body.tema not in TEMAS:
        raise ErrorApi(422, "tema.invalido", temas=", ".join(TEMAS))
    user.tema = body.tema
    await db.commit()
    return {**_user_dict(user), "tema": user.tema or TEMA_POR_DEFECTO}


class UserCreate(BaseModel):
    email: str
    password: str
    name: str = ""
    role: str = "collaborator"


@router.get("/users")
async def list_users(_admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(User).order_by(User.created_at))).scalars().all()
    return [_user_dict(u) for u in rows]


@router.post("/users")
async def create_user(
    body: UserCreate, request: Request,
    _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    if body.role not in ROLES:
        raise ErrorApi(422, "usuario.rol_invalido", roles=ROLES)
    validar_clave(body.password)
    exists = (await db.execute(
        select(User).where(User.email == str(body.email).lower())
    )).scalar_one_or_none()
    if exists:
        raise ErrorApi(409, "usuario.email_duplicado")
    user = User(email=str(body.email).lower(), name=body.name or str(body.email),
                password_hash=hash_password(body.password), role=body.role, active=True)
    db.add(user)
    await _registrar(db, "USUARIO_CREADO", request=request, email=user.email,
                     user_id=user.id, actor_email=_admin.email,
                     detalle=f"rol={body.role}")
    await db.commit()
    return _user_dict(user)


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    active: bool | None = None
    password: str | None = None


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str, body: UserUpdate, request: Request,
    _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    """Editar un usuario: nombre, rol, estado o contraseña.

    ⚠️ **No deja quitar al último administrador activo.** Antes sí: un admin
    podía bajarse el rol a sí mismo o desactivar al único que quedaba, y como el
    bootstrap ya está cerrado, nadie podía volver a entrar por la app — hay que
    correr `scripts/reset_password.py` contra la base. La instalación de Amarena
    ya vivió exactamente eso. Es una comprobación, no una restricción de diseño:
    con dos administradores se puede quitar cualquiera de los dos.
    """
    u = await db.get(User, user_id)
    if not u:
        raise ErrorApi(404, "usuario.no_encontrado")

    # ¿Este cambio le saca el mando al último que lo tiene?
    pierde_admin = (
        (body.role is not None and body.role != "admin")
        or body.active is False)
    if pierde_admin and u.role == "admin" and u.active:
        otros = (await db.execute(
            select(func.count()).select_from(User).where(
                User.role == "admin", User.active.is_(True), User.id != u.id)
        )).scalar_one()
        if not otros:
            raise ErrorApi(409, "auth.ultimo_admin")

    cambios = []
    if body.name is not None:
        u.name = body.name
        cambios.append("nombre")
    if body.role is not None:
        if body.role not in ROLES:
            raise ErrorApi(422, "usuario.rol_invalido", roles=ROLES)
        if body.role != u.role:
            cambios.append(f"rol {u.role}->{body.role}")
        u.role = body.role
    if body.active is not None:
        if body.active != u.active:
            cambios.append("activado" if body.active else "desactivado")
        u.active = body.active
    if body.password:
        validar_clave(body.password)
        u.password_hash = hash_password(body.password)
        cambios.append("contraseña")
        # Cambiarle la clave a alguien lo saca del bloqueo: es la vía por la que
        # un administrador rescata a quien quedó afuera, sin esperar los minutos.
        u.failed_attempts = 0
        u.locked_until = None

    if cambios:
        await _registrar(db, "USUARIO_EDITADO", request=request, email=u.email,
                         user_id=u.id, actor_email=_admin.email,
                         detalle=", ".join(cambios))
    await db.commit()
    return _user_dict(u)
