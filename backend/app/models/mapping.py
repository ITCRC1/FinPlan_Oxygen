from sqlalchemy import Boolean, Column, Integer, String, UniqueConstraint
from app.db import Base


class ReportLineConfig(Base):
    __tablename__ = "report_line_config"

    id = Column(String(36), primary_key=True)
    report_id = Column(String(50), nullable=False, index=True)
    display_order = Column(Integer, nullable=False)
    line_code = Column(String(60), nullable=False)
    section = Column(String(80), nullable=False)
    line_name = Column(String(150), nullable=False)
    line_type = Column(String(20), nullable=False)   # HEADER|MAPPED|CALCULATED|KPI
    parent_line_code = Column(String(60), nullable=True)
    calculation_logic = Column(String(250), nullable=True)
    format_hint = Column(String(30), nullable=True)
    active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("report_id", "line_code", name="uq_report_line_code"),
    )


class AccountMapping(Base):
    __tablename__ = "account_mapping"

    id = Column(String(36), primary_key=True)
    active_status = Column(String(10), nullable=False, default="YES")  # YES|REVIEW|NO
    report_id = Column(String(50), nullable=False, index=True)
    report_line_code = Column(String(60), nullable=False, index=True)
    report_line_name = Column(String(150), nullable=True)
    report_section = Column(String(80), nullable=True)
    display_order = Column(Integer, nullable=True)
    source_origin = Column(String(60), nullable=True)
    source_department = Column(String(100), nullable=True)
    account_code = Column(String(20), nullable=False)
    account_name_example = Column(String(200), nullable=True)
    financial_nature = Column(String(20), nullable=False)   # Revenue|Expense
    rollup_operator = Column(String(10), nullable=False, default="SUM")
    sign_rule = Column(String(250), nullable=True)
    notes = Column(String(500), nullable=True)
    dept_code = Column(String(10), nullable=True)   # numeric dept code, e.g. "0110"

    # Vigencia de la regla, `YYYY-MM` inclusive. NULL = sin límite por ese lado.
    #
    # Existe porque el mapeo CAMBIA y los reportes ya enviados no pueden cambiar
    # con él: si la plata solo se mueve entre dos filas del MISMO subtotal, el
    # reporte sigue cuadrando y el cambio no se nota — que es el peor caso.
    #
    # El caso que lo trajo (D9: la 7120 partida en jul-2026 entre `OH_ADMIN` y
    # `OH_CC_COMMISSIONS`) se dio de baja el 2026-08-27; el owner no quiere la
    # comisión de tarjeta en su propia línea. Hoy NINGUNA regla usa vigencia. El
    # mecanismo se queda: es la única forma de versionar el mapeo.
    vigente_desde = Column(String(7), nullable=True)
    vigente_hasta = Column(String(7), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "report_id", "source_department", "account_code", "source_origin",
            "vigente_desde",
            name="uq_account_mapping",
        ),
    )

    def vigente_en(self, periodo: str | None) -> bool:
        """¿Rige esta regla en `periodo` (`YYYY-MM`)?

        `periodo=None` significa «la vigente hoy»: las reglas con corte de
        vigencia pasado quedan afuera, que es lo que el P&L del día a día
        necesita. Sin esto, la regla vieja y la nueva de la 7120 conviven y
        cuál gana depende del orden físico de las filas.
        """
        if periodo is None:
            return self.vigente_hasta is None
        if self.vigente_desde and periodo < self.vigente_desde:
            return False
        if self.vigente_hasta and periodo > self.vigente_hasta:
            return False
        return True
