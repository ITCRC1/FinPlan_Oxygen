"""La comisión pasa a ser por MES.

Revision ID: 145
Revises: 144
Create Date: 2026-10-16

Owner, 2026-10-16: *«pone el primer mes y se replica a los 12 meses y manual se
cambia el mes que probablemente cambie»*.

Hasta acá la comisión era UNA para todo el año (`Resumen Manual` B67:B73, una
columna). Cuando un canal cambia su comisión a mitad de año, con una sola
columna hay que poner un promedio — y el promedio no es el número de ningún
mes: el ingreso de cada mes queda mal en direcciones opuestas y el total del
año disimula los dos.

## ⚠️ La expansión preserva los números EXACTOS

Cada fila que hay se replica a los doce meses con su mismo valor. Después de
esta migración el ingreso de cada mes es idéntico al de antes: lo que cambia es
que ahora se PUEDE cambiar un mes, no que algo haya cambiado.

Una migración que dejara meses sin fila también daría el mismo total hoy —la
ausencia se lee como 0% de comisión, o sea vender a rack— pero el P&L se
movería solo, sin error y con el total cuadrando consigo mismo. Por eso se
expanden los doce.
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "145"
down_revision = "144"
branch_labels = None
depends_on = None

TABLA = "rack_comisiones"


def upgrade() -> None:
    c = op.get_bind()
    insp = sa.inspect(c)
    if not insp.has_table(TABLA):
        return
    cols = {x["name"] for x in insp.get_columns(TABLA)}
    if "month" in cols:
        return

    op.add_column(TABLA, sa.Column("month", sa.Integer(), nullable=True))

    # ⚠️ La llave vieja se suelta ANTES de expandir. Es (escenario, segmento),
    # o sea «una sola fila por segmento»: insertar el segundo mes con ella
    # puesta revienta con `duplicate key`, la migración aborta y el servicio no
    # arranca. Pasó exactamente así en el deploy del 2026-10-16.
    nombres = {u["name"] for u in insp.get_unique_constraints(TABLA)}
    if "uq_rack_comision" in nombres:
        op.drop_constraint("uq_rack_comision", TABLA, type_="unique")

    # ── La expansión: una fila por mes, con el mismo valor ──────────────────
    filas = list(c.execute(sa.text(
        f"SELECT id, scenario_id, hotel_id, segmento_code, comision_pct, "
        f"tarifa_propia FROM {TABLA}")))
    for f in filas:
        # La que ya existe pasa a ser enero; se insertan las otras once.
        c.execute(sa.text(f"UPDATE {TABLA} SET month = 1 WHERE id = :i"),
                  {"i": f.id})
        for mes in range(2, 13):
            c.execute(sa.text(
                f"INSERT INTO {TABLA} (id, scenario_id, hotel_id, "
                f"segmento_code, comision_pct, tarifa_propia, month) "
                f"VALUES (:id, :sc, :ho, :se, :pc, :tp, :mo)"),
                {"id": str(uuid.uuid4()), "sc": f.scenario_id,
                 "ho": f.hotel_id, "se": f.segmento_code,
                 "pc": f.comision_pct, "tp": f.tarifa_propia, "mo": mes})

    op.alter_column(TABLA, "month", nullable=False)
    op.create_unique_constraint("uq_rack_comision_mes", TABLA,
                                ["scenario_id", "segmento_code", "month"])


def downgrade() -> None:
    c = op.get_bind()
    insp = sa.inspect(c)
    if not insp.has_table(TABLA):
        return
    cols = {x["name"] for x in insp.get_columns(TABLA)}
    if "month" not in cols:
        return
    # Se vuelve a una fila por segmento: queda la de ENERO, que es la que el
    # usuario escribe primero y de la que salen las demás por réplica.
    c.execute(sa.text(f"DELETE FROM {TABLA} WHERE month <> 1"))
    nombres = {u["name"] for u in insp.get_unique_constraints(TABLA)}
    if "uq_rack_comision_mes" in nombres:
        op.drop_constraint("uq_rack_comision_mes", TABLA, type_="unique")
    op.drop_column(TABLA, "month")
    op.create_unique_constraint("uq_rack_comision", TABLA,
                                ["scenario_id", "segmento_code"])
