# -*- coding: utf-8 -*-
"""Qué departamentos escondió el provisionamiento, en un solo lugar.

La matriz (`dept_enablement`) se llenaba desde su pantalla y **no la leía casi
nadie**: se guardaba la decisión y los departamentos seguían apareciendo en
todos los selectores. La capa que registra estaba hecha; la que aplica, no.

Dos reglas que valen para todo el que use esto:

**La tabla es esparsa y el default es PRENDIDO.** No tener fila significa
activo. Por eso se pregunta «quién está apagado» y no «quién está prendido»: una
propiedad recién creada no tiene ninguna fila y le funciona todo.

**Esto esconde, NO borra ni resta.** Un departamento apagado desaparece de las
pantallas de carga, pero si tiene datos cargados esos datos siguen sumando en el
P&L. Es a propósito: si esconder algo cambiara el estado de resultados, sería
una forma de mover números sin dejar rastro. La pantalla de provisionamiento
avisa cuánto dato hay detrás antes de dejar apagar.
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dept_enablement import DeptEnablement


async def apagados_por_dimension(
    db: AsyncSession, hotel_id: str
) -> dict[str, list[str]]:
    """`{dimension: [dept_code, …]}` — solo lo que alguien apagó a mano."""
    out: dict[str, set[str]] = defaultdict(set)
    for r in (await db.execute(select(DeptEnablement).where(
            DeptEnablement.hotel_id == hotel_id,
            DeptEnablement.scope_kind == "DEPT",
            DeptEnablement.enabled.is_(False)))).scalars():
        out[r.dimension].add((r.scope_key or "").strip())
    return {dim: sorted(codigos) for dim, codigos in out.items()}


async def dept_apagado(
    db: AsyncSession, hotel_id: str, dept_code: str, dimension: str | None = None
) -> bool:
    """¿Este departamento está escondido?

    Sin `dimension`, contesta por el departamento entero: apagado en TODAS las
    que tenga fila. Con dimensión, contesta por esa sola. El tab del Club usa la
    primera forma —o el departamento existe en la propiedad o no— y las
    pantallas de carga la segunda.
    """
    q = select(DeptEnablement).where(
        DeptEnablement.hotel_id == hotel_id,
        DeptEnablement.scope_kind == "DEPT",
        DeptEnablement.scope_key == dept_code,
        DeptEnablement.enabled.is_(False),
    )
    if dimension:
        q = q.where(DeptEnablement.dimension == dimension)
    return (await db.execute(q)).scalars().first() is not None


# ─── Tabs y reportes (owner, 2026-08-20) ─────────────────────────────────────
#
# «No todas las propiedades van a ver todos los reportes, ya que son muchos para
# cada propiedad y se van a perder.»
#
# Vive en el MISMO archivo que los departamentos a propósito: «qué escondió el
# provisionamiento» tiene que poder contestarse en un solo lugar. Mismas dos
# reglas: tabla esparsa, default prendido.


async def tabs_apagados(db: AsyncSession, hotel_id: str,
                        perfil: str | None = None) -> dict[str, list[str]]:
    """`{"TAB": [...], "ITEM": [...]}` — sólo lo que alguien apagó a mano.

    `perfil` decide QUÉ conjunto se devuelve, y son dos preguntas distintas:

    * **`None`** — «qué está apagado para todos», que es la matriz de la
      propiedad. Es lo que edita la pantalla de provisionamiento cuando no se
      eligió ningún perfil, y lo que ve un rol sin filas propias.
    * **un perfil** — lo de la propiedad **más** lo de ese perfil. Es la unión,
      no el reemplazo: la propiedad manda sobre el perfil. Si una propiedad no
      hace Break-Even no lo hace para nadie, y dejar que un perfil lo prendiera
      sería contradecir esa decisión desde un lugar más chico.

    `""` como perfil equivale a `None` — es el mismo centinela que guarda la
    tabla, y tratarlo distinto haría que un rol vacío devolviera la unión con
    una fila que no existe.
    """
    from app.models.tab_enablement import TabEnablement

    from app.models.tab_enablement import SCOPE_KINDS

    quienes = {""} | ({perfil} if perfil else set())
    # Todos los niveles arrancan presentes y vacíos: una pantalla que pregunta
    # por `SUBTAB` no tiene que saber si alguien apagó alguno todavía.
    fuera: dict[str, set[str]] = {k: set() for k in SCOPE_KINDS}
    for r in (await db.execute(select(TabEnablement).where(
            TabEnablement.hotel_id == hotel_id,
            TabEnablement.perfil.in_(quienes)))).scalars().all():
        fuera.setdefault(r.scope_kind, set()).add(r.clave)
    return {k: sorted(v) for k, v in fuera.items()}
