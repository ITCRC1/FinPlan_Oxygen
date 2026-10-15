# -*- coding: utf-8 -*-
"""Rooms por canal: el modelo alternativo, y el interruptor para engancharlo.

Owner, 2026-10-15: *«no tenemos historial de ventas totales, ocupación y tarifa
porque no hay históricos por tipo de habitación como sí tengo en FinPlan CWL…
Sales and Marketing me proponen hacerlo de otra manera, por canal»* ·
*«debemos tener la opción de poder calcular Total Rooms en forma alternativa y
poder conectarlo… para Oxygen y Ojochal este sería el modelo preferido… sin
embargo para CWL, al tener buenos históricos, trabajaríamos con el que tenemos»*.

## Tres piezas

1. `canal_segmentos` — el catálogo de segmentos de venta, POR PROPIEDAD. No es
   una lista en el código: una propiedad que venda por un canal nuevo lo agrega
   y aparece en la grilla, el reporte y el importador sin tocar nada.
2. `canal_rooms_entries` — noches, tarifa e ingreso por segmento × mes ×
   escenario. Las seis «versiones» del libro de Sales son seis escenarios de
   FinPlan, que es como el resto del sistema ya compara.
3. `scenarios.rooms_source` — el interruptor: `tarifas` (el modelo de rack por
   tipo de habitación, que es lo que hay hoy) o `canales` (este).

## ⚠️ El default es `tarifas`

Aditiva de verdad: **ninguna propiedad cambia de modelo por esta migración**.
CWL sigue con el suyo, que es el bueno para quien tiene historia por tipo de
habitación. El cambio se hace escenario por escenario y a mano.

Revision ID: 142
Revises: 141
"""
import sqlalchemy as sa
from alembic import op

revision = "142"
down_revision = "141"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "canal_segmentos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        # False = ocupa villa pero NO entra al denominador del ADR.
        sa.Column("genera_ingreso", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("hotel_id", "code", name="uq_canal_segmento"),
    )
    op.create_table(
        "canal_rooms_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("segmento_code", sa.String(30), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("noches", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tarifa", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("ingreso", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("tarifa_digitada", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("actualizado_en", sa.DateTime(), nullable=True),
        sa.Column("actualizado_por", sa.String(120), nullable=False,
                  server_default=""),
        sa.UniqueConstraint("scenario_id", "segmento_code", "month",
                            name="uq_canal_rooms_entry"),
    )
    # ⚠️ Default `tarifas`: nadie cambia de modelo por esta migración.
    op.add_column("scenarios", sa.Column(
        "rooms_source", sa.String(10), nullable=False, server_default="tarifas"))


def downgrade() -> None:
    op.drop_column("scenarios", "rooms_source")
    op.drop_table("canal_rooms_entries")
    op.drop_table("canal_segmentos")
