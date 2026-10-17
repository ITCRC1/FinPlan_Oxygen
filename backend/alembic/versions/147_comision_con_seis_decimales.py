"""La comisión pasa de cuatro a seis decimales.

Revision ID: 147
Revises: 146
Create Date: 2026-10-16

Con cuatro decimales el tarifario de Oxygen reproduce el libro 2027 con
**$16.93** de diferencia sobre $1.777.873,86. No es un error de nadie: es el
paso del redondeo. `0,0001` sobre un RAC de $683 son seis centavos por noche,
y hay 3.502 noches.

    4 decimales   1.777.856,93    −16,93
    6 decimales   1.777.873,95     +0,09
    8 decimales   1.777.873,85     −0,01

Se queda en **seis**: baja el residuo a nueve centavos en el año y deja la
comisión legible —`0,230000` sigue leyéndose 23%—. Ocho no compra nada que se
note y empieza a escribir ruido en una celda que una persona teclea.

⚠️ **Esto NO cambia ningún número que ya exista.** Ampliar la escala de un
`numeric` conserva el valor: `0.2300` sigue siendo `0.230000`. Lo que cambia
es cuánto detalle se PUEDE guardar de ahora en adelante.

El origen del residuo vale la pena anotarlo, porque explica por qué el modelo
es así: en el libro del hotel lo que se teclea es el **ingreso neto**, y el
porcentaje de comisión sale de dividir. Acá es al revés —se teclea la
comisión y el ingreso se deriva—, que es lo que permite mover un canal y ver
el efecto. Cargar el libro exige entonces guardar la comisión implícita, y el
redondeo de esa división es todo el residuo que queda.
"""
import sqlalchemy as sa
from alembic import op

revision = "147"
down_revision = "146"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("rack_comisiones", "comision_pct",
                    existing_type=sa.Numeric(6, 4),
                    type_=sa.Numeric(10, 6),
                    existing_nullable=True)


def downgrade() -> None:
    # ⚠️ Vuelve a cuatro decimales: lo que tenga más se REDONDEA y no se
    # recupera. Es el camino de vuelta de una ampliación, y no es gratis.
    op.alter_column("rack_comisiones", "comision_pct",
                    existing_type=sa.Numeric(10, 6),
                    type_=sa.Numeric(6, 4),
                    existing_nullable=True)
