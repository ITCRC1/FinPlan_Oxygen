"""Cada propiedad llama a sus temporadas como las llama.

Revision ID: 146
Revises: 145
Create Date: 2026-10-16

El tarifario que se portó desde Ojochal trae TRES casillas de RAC —`rac_pico`,
`rac_alta`, `rac_verde`— porque ese hotel vende con tres niveles de tarifa.

Oxygen vende con **dos**: `Origen Tarifa Rack` del libro de 2027 dice «RAC
Alta» y «RAC Baja», y las fechas son tres rangos sobre esos dos niveles —
Alta (ene–abr), Baja (may–nov), Alta (dic)—.

## Por qué una etiqueta y no renombrar las casillas

Renombrar `rac_verde` a `rac_baja` arreglaría Oxygen y rompería Ojochal, que
tiene las tres y las llama por su nombre. Lo que cambia entre propiedades no es
cuántos niveles existen: es **cómo se llaman** y **cuántos se usan**.

Así que la casilla sigue siendo la llave técnica —el motor mapea `PICO`/`ALTA`/
`VERDE` a su tarifa en `rac_villa_mes`, y eso no se toca— y el nombre que ve el
usuario pasa a ser un dato del escenario. Oxygen va a escribir «Alta» sobre la
casilla ALTA y «Baja» sobre la VERDE, y la PICO no va a tener ningún rango: la
pantalla la esconde porque nadie la usa, no porque esté escrito que Oxygen
tiene dos.

⚠️ **La etiqueta es decorado y nada más.** Si alguna vez se la quiere usar para
decidir una tarifa, el que lea esto tiene que saber que dos escenarios pueden
tener etiquetas distintas sobre la misma casilla, y que está vacía en todo lo
que ya existe. La tarifa sale de la casilla; siempre.
"""
import sqlalchemy as sa
from alembic import op

revision = "146"
down_revision = "145"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rack_temporadas",
                  sa.Column("etiqueta", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("rack_temporadas", "etiqueta")
