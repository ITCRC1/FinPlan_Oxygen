# -*- coding: utf-8 -*-
"""A&B: el servicio sale del ingreso y entra la parte que sí lleva comisión.

Owner, 2026-10-07, sobre el 10%: *«no, 10% no se considera un ingreso, es un tip
que se colecta para los empleados pagado por el cliente, es tipo impuesto»*.
La 139 lo sumaba al Food. Estaba mal: el hotel cobra ese dinero y lo entrega, no
se lo queda. Desde acá el servicio se sigue mostrando —hay que saber cuánto se
recauda— pero **no suma al ingreso**.

Y sobre la comisión: *«es probable que las comidas se vendan en paquetes a
agencia, entonces se ve afectado por el descuento… pero es como un factor, decir
de todas las ventas 50% lleva comisión y el otro no… y los externos no llevan
descuento»*. De ahí sale `pct_comisionable`: qué fracción de la comida del
huésped viaja dentro de un paquete de agencia. Esa parte —y sólo esa— se netea
con el MISMO factor de canal que ya usa la tarifa de habitación
(`compute_net_factor`), para que no haya dos comisiones distintas conviviendo.

⚠️ **La comisión se netea del ingreso, no se gasta.** Verificado contra el mayor
el 2026-10-07: la cuenta 7080 Commissions tiene **$2.537,28 en todo 2026 y $0 en
2025** sobre $1,3 millones de habitaciones. Si fuera gasto serían seis cifras.
Por eso descontar acá NO duplica nada — y por eso el histórico contra el que se
calibró ya viene neto.

## Nace en cero, como todo en este módulo

`server_default="0"` significa «nada lleva comisión» mientras nadie lo diga.
Es el default que no inventa: con 0 el Food es el bruto, que es exactamente lo
que la 139 calculaba antes de esta columna.

Aditiva y reversible: una columna nueva con default; nada que exista cambia de
valor.

Revision ID: 141
Revises: 140
"""
import sqlalchemy as sa
from alembic import op

revision = "141"
down_revision = "140"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fb_plan_config",
        sa.Column("pct_comisionable", sa.Numeric(6, 4),
                  nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("fb_plan_config", "pct_comisionable")
