"""El modelo de Rooms por RAC y segmento: las tablas.

Revision ID: 144
Revises: 143
Create Date: 2026-10-16

Dos grupos, y la diferencia importa:

**Las ESTÁNDAR** — `canal_segmentos` y `canal_rooms_entries`. Son idénticas a
las de Oxygen, campo por campo. Owner, 2026-10-16: *«debes hacer tablas
estándares porque después todo esto hay que consolidarlo en Hotel Consolida»*.
Aguas abajo —`aplicar_canales_rooms` → `RevenueResult` → `get_monthly_revenue`,
que es la puerta que lee Hotel Consolidation— las cuatro propiedades tienen que
ser indistinguibles.

**Las de OJOCHAL** — `rack_temporadas`, `rack_villas`, `rack_comisiones`. Son la
capa de ENTRADA que deriva la tarifa. En Oxygen se digitan noches **y** tarifa;
acá se digitan sólo noches y la tarifa sale del tarifario RAC. No cambian nada
de lo que viaja al consolidado: sólo de dónde sale el número.

⚠️ `scenarios.rooms_source` entra con default `'tarifas'`, que es el modelo de
siempre. **Esta migración no le cambia el modelo a ningún escenario**: conectar
el nuevo es un acto explícito del usuario, escenario por escenario.
"""
from alembic import op
import sqlalchemy as sa

revision = "144"
down_revision = "142"
branch_labels = None
depends_on = None


def _tiene(c, tabla: str) -> bool:
    return sa.inspect(c).has_table(tabla)


def upgrade() -> None:
    c = op.get_bind()

    # ── Las estándar ────────────────────────────────────────────────────────
    if not _tiene(c, "canal_segmentos"):
        op.create_table(
            "canal_segmentos",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
            sa.Column("code", sa.String(30), nullable=False),
            sa.Column("nombre", sa.String(80), nullable=False, server_default=""),
            sa.Column("genera_ingreso", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("orden", sa.Integer, nullable=False, server_default="0"),
            sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.UniqueConstraint("hotel_id", "code", name="uq_canal_segmento"),
        )

    if not _tiene(c, "canal_rooms_entries"):
        op.create_table(
            "canal_rooms_entries",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("scenario_id", sa.String(36),
                      sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
            sa.Column("segmento_code", sa.String(30), nullable=False),
            sa.Column("month", sa.Integer, nullable=False),
            sa.Column("noches", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("tarifa", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("ingreso", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("tarifa_digitada", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("actualizado_en", sa.DateTime, nullable=True),
            sa.Column("actualizado_por", sa.String(120), nullable=False, server_default=""),
            sa.UniqueConstraint("scenario_id", "segmento_code", "month",
                                name="uq_canal_rooms_entry"),
        )

    # ── La capa del tarifario, de Ojochal ───────────────────────────────────
    if not _tiene(c, "rack_temporadas"):
        op.create_table(
            "rack_temporadas",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("scenario_id", sa.String(36),
                      sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
            sa.Column("temporada", sa.String(10), nullable=False),
            sa.Column("desde", sa.Date, nullable=False),
            sa.Column("hasta", sa.Date, nullable=False),
            # `desde` entra en la llave porque una temporada puede tener VARIOS
            # rangos: en 2027 «Pico» son dos, el arranque y el cierre del año.
            sa.UniqueConstraint("scenario_id", "temporada", "desde",
                                name="uq_rack_temporada"),
        )

    if not _tiene(c, "rack_villas"):
        op.create_table(
            "rack_villas",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("scenario_id", sa.String(36),
                      sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
            sa.Column("villa", sa.String(60), nullable=False),
            # Unidades de VENTA, no habitaciones: en Ojochal son 11 contra 16.
            sa.Column("unidades", sa.Integer, nullable=False, server_default="0"),
            sa.Column("rac_pico", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("rac_alta", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("rac_verde", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("orden", sa.Integer, nullable=False, server_default="0"),
            sa.UniqueConstraint("scenario_id", "villa", name="uq_rack_villa"),
        )

    if not _tiene(c, "rack_comisiones"):
        op.create_table(
            "rack_comisiones",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("scenario_id", sa.String(36),
                      sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
            sa.Column("segmento_code", sa.String(30), nullable=False),
            sa.Column("comision_pct", sa.Numeric(6, 4), nullable=False, server_default="0"),
            sa.Column("tarifa_propia", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("scenario_id", "segmento_code", name="uq_rack_comision"),
        )

    # ── El interruptor ──────────────────────────────────────────────────────
    cols = {x["name"] for x in sa.inspect(c).get_columns("scenarios")}
    if "rooms_source" not in cols:
        op.add_column("scenarios", sa.Column(
            "rooms_source", sa.String(10), nullable=False, server_default="tarifas"))


def downgrade() -> None:
    c = op.get_bind()
    cols = {x["name"] for x in sa.inspect(c).get_columns("scenarios")}
    if "rooms_source" in cols:
        op.drop_column("scenarios", "rooms_source")
    for t in ("rack_comisiones", "rack_villas", "rack_temporadas",
              "canal_rooms_entries", "canal_segmentos"):
        if _tiene(c, t):
            op.drop_table(t)
