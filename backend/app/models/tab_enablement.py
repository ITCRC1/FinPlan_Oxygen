# -*- coding: utf-8 -*-
"""Qué tabs y reportes ve CADA propiedad.

Owner, 2026-08-20: *«no todas las propiedades van a ver todos los reportes, ya
que son muchos para cada propiedad y se van a perder»* · *«así como los
departamentos se van a limitar, así se van a limitar los reportes y los tabs
principales»* · *«todo debe poderse esconder y habilitar»*.

Medido ese día: la barra tiene **13 tabs y 96 entradas**. Una propiedad nueva
abre con las 96.

**Es el mismo patrón que `dept_enablement`, a propósito.** Dos matrices de
provisionamiento con reglas distintas serían dos cosas que hay que aprender por
separado, y la de departamentos ya está probada:

* **La tabla es ESPARSA y el default es PRENDIDO.** No tener fila significa
  visible. Por eso se pregunta «qué está apagado» y no «qué está prendido»: el
  día que esto se despliega no cambia nada en ninguna propiedad, y una
  propiedad nueva ve todo.
* **Prender BORRA la fila** en vez de escribir `visible=true`, así la tabla
  contiene sólo lo que alguien apagó a mano.
* Y **un reporte nuevo nace VISIBLE**. Al revés —nacer oculto— sería peor: se
  construye algo, nadie lo ve, y nadie sabe que existe para poder prenderlo.

⚠️ **Esto ESCONDE de la barra; NO es un permiso.** La ruta sigue respondiendo:
quien escriba la URL entra igual, y el endpoint contesta lo mismo. Es
navegación, no seguridad — si hace falta impedir el acceso, eso son roles, no
esta tabla. El permiso de verdad vive en `app/perfiles.py`, y las dos capas se
complementan: una ordena la vista, la otra impide el cambio.

**Y también por PERFIL** (owner, 2026-08-26: *«vistas limitadas por perfil»*).
La columna `perfil` con `""` = «para todos» agrega el segundo eje sin cambiar
ninguna de las dos reglas de arriba. Ver la migración 137.

Y esa misma propiedad es la que hace seguro poder apagarlo **todo**, incluida la
pantalla que administra esto: aunque se esconda, se vuelve entrando a su URL.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

#: Qué se está apagando.
#:
#: * `TAB`    — un tab de primer nivel de la barra
#: * `ITEM`   — una entrada de su menú (una pantalla o un reporte)
#: * `SUBTAB` — una vista DENTRO de una pantalla, como los quince sub-tabs de
#:   Cierre de Mes
#:
#: ⚠️ Son tres niveles y no uno porque son tres decisiones distintas. «Esta
#: propiedad no hace Break-Even» no es lo mismo que «no usa el reporte a la
#: Junta», y ninguna de las dos es «en el cierre no quiero que el dueño vea el
#: Flow Through» (owner, 2026-09-02: *«esta vista la van a ver los dueños; me
#: gustaría poder quitar y poner tabs sin borrarlas, sólo para dejar lo
#: importante»*).
SCOPE_KINDS = ["TAB", "ITEM", "SUBTAB"]


class TabEnablement(Base):
    """Una fila = algo que ESTA propiedad NO ve. Sin fila, se ve."""

    __tablename__ = "tab_enablement"
    __table_args__ = (
        UniqueConstraint("hotel_id", "scope_kind", "clave", "perfil",
                         name="uq_tab_enablement"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    scope_kind: Mapped[str] = mapped_column(String(8), default="ITEM")
    #: La `key` de la barra (`reports`, `ownerReport`…).
    #:
    #: ⚠️ **El catálogo de lo que existe vive en la barra, no acá.** Copiarlo al
    #: backend sería una segunda lista que habría que acordarse de actualizar, y
    #: este proyecto ya pagó dos veces por una lista escrita a mano. Acá sólo se
    #: guarda lo apagado; una clave que ya no exista en la barra no rompe nada,
    #: simplemente no esconde nada.
    clave: Mapped[str] = mapped_column(String(60))
    #: Para QUIÉN está apagado. `""` = para todos los perfiles.
    #:
    #: ⚠️ **El centinela es `""` y no `NULL` a propósito.** En Postgres dos NULL
    #: no chocan en un UNIQUE: con la columna nullable, la misma clave se podría
    #: apagar dos veces «para todos» y la tabla dejaría de tener una fila por
    #: decisión.
    #:
    #: Un usuario ve la unión de dos conjuntos: lo apagado para su propiedad
    #: (`""`) más lo apagado para su perfil. **La propiedad manda sobre el
    #: perfil**: si una propiedad no hace Break-Even, no lo hace para nadie, y
    #: prenderlo para un perfil sería contradecir esa decisión desde un lugar
    #: más chico.
    perfil: Mapped[str] = mapped_column(String(20), default="")

    #: Siempre `False`. La columna existe para poder leer una fila y entender
    #: qué significa sin ir al docstring.
    visible: Mapped[bool] = mapped_column(Boolean, default=False)

    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    actualizado_por: Mapped[str] = mapped_column(String(120), default="")
