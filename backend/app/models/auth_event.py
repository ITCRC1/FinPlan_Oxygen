# -*- coding: utf-8 -*-
"""Registro de lo que pasa en la puerta: entradas, fallos y altas de usuario.

**Por qué existe.** No quedaba rastro de NADA de autenticación — ni entradas, ni
intentos fallidos, ni quién creó o desactivó a quién. El día que una cuenta
aparezca usada de forma rara no había con qué reconstruir qué pasó ni desde
dónde. Auditar el dato contable sin auditar la puerta deja la mitad de la
historia.

**No es lo mismo que `audit_api`**, que es trazabilidad contable
(cuenta×departamento → línea del P&L). Esto es seguridad.

**Qué NO se guarda, a propósito:** ninguna contraseña, ningún hash, ningún
token. Un registro que copia credenciales convierte una lectura de tabla en una
filtración. Del intento fallido sólo queda el correo con el que se intentó.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

#: Los eventos que se registran. Es una lista cerrada para que la tabla se pueda
#: agrupar y filtrar; un texto libre se vuelve inservible en seis meses.
EVENTOS = (
    "LOGIN_OK",          # entró
    "LOGIN_FALLIDO",     # clave incorrecta, o correo que no existe
    "LOGIN_BLOQUEADO",   # se rechazó por bloqueo activo
    "CUENTA_BLOQUEADA",  # este intento fue el que disparó el bloqueo
    "BOOTSTRAP",         # se creó el primer administrador
    "USUARIO_CREADO",
    "USUARIO_EDITADO",   # rol, estado o contraseña
)


class AuthEvent(Base):
    __tablename__ = "auth_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    evento: Mapped[str] = mapped_column(String(24), index=True)
    #: El correo con el que se intentó. Se guarda AUNQUE no exista el usuario —
    #: es justamente el dato que sirve para ver contra qué cuentas se insiste.
    email: Mapped[str] = mapped_column(String(160), default="", index=True)
    #: Nulo cuando el correo no corresponde a nadie.
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    #: Quién ejecutó la acción, cuando no es la misma persona (altas y ediciones
    #: las hace un administrador sobre otra cuenta).
    actor_email: Mapped[str] = mapped_column(String(160), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    #: Texto corto para el contexto: qué campos cambiaron, cuántos intentos van.
    detalle: Mapped[str] = mapped_column(String(300), default="")
    creado: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True)

    def __repr__(self) -> str:
        return f"<AuthEvent {self.evento} {self.email}>"
