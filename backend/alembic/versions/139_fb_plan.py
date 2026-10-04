# -*- coding: utf-8 -*-
"""Planificación de A&B: pax → comida → ingreso.

Owner, 2026-10-03: *«food and beverage es un departamento importante…
necesito crear un sub tab en planning para calcular estos ingresos… partir de
las estadísticas de rooms, rooms occupied y total pax por mes. y también hay una
cantidad de pax externos»*.

Hasta hoy el A&B del presupuesto salía del motor de PAQUETES, que es producto de
Corcovado: un Full Board de $126 por pax/noche que Oxygen no vende. El resultado
era `package_configs` vacío y la línea Food del checkbook en cero.

## Dos tablas y no una

`fb_plan_config` es por ESCENARIO —precios y captura no cambian de mes— y
`fb_plan_mes` es por mes, porque los pax externos sí. Meterlas juntas obligaría
a repetir los seis números de la carta doce veces, y a que alguien los
desincronice.

## Los pax hospedados NO están acá, a propósito

Salen de `scenario_stats.guests`. Si se pudieran digitar habría dos verdades
sobre el mismo mes y el día que no coincidan nadie sabría cuál manda — que es
exactamente lo que pidió el owner al decir «partir de las estadísticas de
rooms».

Aditiva y reversible: dos tablas nuevas, nada que exista cambia.

Revision ID: 139
Revises: 138
"""
import sqlalchemy as sa
from alembic import op

revision = "139"
down_revision = "138"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fb_plan_config",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        # Precio por pax y por comida, ANTES del servicio.
        sa.Column("precio_desayuno", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("precio_almuerzo", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("precio_cena", sa.Numeric(12, 2), nullable=False, server_default="0"),
        # Qué fracción de los pax del mes toma esa comida.
        sa.Column("captura_desayuno", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("captura_almuerzo", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("captura_cena", sa.Numeric(6, 4), nullable=False, server_default="0"),
        # El servicio se SUMA al precio digitado (owner, 2026-10-03).
        sa.Column("servicio_pct", sa.Numeric(6, 4), nullable=False, server_default="0.10"),
        # Beverage = fracción del Food ya con servicio.
        sa.Column("bev_pct_food", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("actualizado_en", sa.DateTime(), nullable=True),
        sa.Column("actualizado_por", sa.String(120), nullable=False, server_default=""),
        sa.UniqueConstraint("scenario_id", name="uq_fb_plan_config"),
    )
    op.create_table(
        "fb_plan_mes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("pax_externos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ticket_externos", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("actualizado_en", sa.DateTime(), nullable=True),
        sa.Column("actualizado_por", sa.String(120), nullable=False, server_default=""),
        sa.UniqueConstraint("scenario_id", "month", name="uq_fb_plan_mes"),
    )


def downgrade() -> None:
    op.drop_table("fb_plan_mes")
    op.drop_table("fb_plan_config")
