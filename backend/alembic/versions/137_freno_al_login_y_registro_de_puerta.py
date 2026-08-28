# -*- coding: utf-8 -*-
"""freno a la fuerza bruta en el login, y registro de lo que pasa en la puerta

**Los dos huecos que tapa** (auditoría de seguridad, 2026-08-28):

1. `POST /auth/login` aceptaba **intentos ilimitados**. No había contador, ni
   demora, ni bloqueo, ni límite por IP — buscando `failed_attempts`,
   `locked_until` y `rate limit` en todo el backend no aparecía nada. Con una
   lista de correos del grupo, que son predecibles, se probaba sin resistencia.

2. **No quedaba rastro de nada de autenticación**: ni entradas, ni fallos, ni
   quién creó o desactivó a quién. El día que una cuenta apareciera usada de
   forma rara, no había con qué reconstruir qué pasó.

**Por qué el contador va en la base y no en memoria.** En memoria se borra con
cada reinicio, y Railway reinicia en cada despliegue: un freno que se quita
redesplegando no es un freno. El límite por IP sí es en memoria y es a propósito
— es un amortiguador de ráfaga, no la defensa (ver `app/api/auth_api.py`).

**El §27 del CLAUDE.md ya especificaba esto** —con estos mismos nombres de
columna— y nunca se había construido. Acá se construye la parte que frena; el
resto de ese capítulo (sesiones revocables, recuperación por correo) sigue
pendiente y está anotado en la auditoría.

Aditiva y reversible. **No cambia ningún dato existente**: las columnas nacen en
0/NULL, que es «esta cuenta no tiene fallos», y la tabla nace vacía.

Revision ID: 137
Revises: 136
"""
import sqlalchemy as sa
from alembic import op

revision = "137"
down_revision = "136"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. El contador de fallos, en `users` ──────────────────────────────────
    # `server_default` además del default del ORM: las filas que YA existen
    # necesitan un valor, y un INSERT que no pase por el ORM —un guion, una
    # carga a mano— también.
    op.add_column("users", sa.Column(
        "failed_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column(
        "locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column(
        "last_failed_at", sa.DateTime(timezone=True), nullable=True))

    # ── 2. El registro de la puerta ───────────────────────────────────────────
    # Sin llave foránea a `users` a propósito: se registran intentos con correos
    # que NO existen —que es justamente lo que hay que poder ver— y borrar un
    # usuario no puede llevarse su historial por delante.
    op.create_table(
        "auth_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("evento", sa.String(24), nullable=False),
        sa.Column("email", sa.String(160), nullable=False, server_default=""),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("actor_email", sa.String(160), nullable=False, server_default=""),
        sa.Column("ip", sa.String(64), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(300), nullable=False, server_default=""),
        sa.Column("detalle", sa.String(300), nullable=False, server_default=""),
        sa.Column("creado", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    # Las tres preguntas que se le hacen a esta tabla: «¿qué pasó con este
    # correo?», «¿cuántos fallos hubo?» y «¿qué pasó ayer?».
    op.create_index("ix_auth_events_email", "auth_events", ["email"])
    op.create_index("ix_auth_events_evento", "auth_events", ["evento"])
    op.create_index("ix_auth_events_creado", "auth_events", ["creado"])


def downgrade() -> None:
    op.drop_index("ix_auth_events_creado", table_name="auth_events")
    op.drop_index("ix_auth_events_evento", table_name="auth_events")
    op.drop_index("ix_auth_events_email", table_name="auth_events")
    op.drop_table("auth_events")
    op.drop_column("users", "last_failed_at")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_attempts")
