# -*- coding: utf-8 -*-
"""El orden de los sub-tabs de Cierre de Mes.

Owner, 2026-09-03: *«vamos a cambiar el orden de los sub tabs: primero es P&L
Statement, segundo Auditoría, tercero Resumen 12m, sigue 12 meses, y el tab P&L
pasa de último»*.

Es el orden del CIERRE, no el de cómo se fueron construyendo: se abre con el
estado de resultados, se comprueba que cuadre, se mira el año, y recién después
vienen las aperturas por departamento.
"""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[2] / "frontend"
PAGINA = FRONT / "app/month-end/pl/page.tsx"


def _claves() -> list[str]:
    src = PAGINA.read_text(encoding="utf-8")
    bloque = src[src.index("const VISTAS = ["):src.index("] as const;")]
    return re.findall(r'\{\s*key:\s*"([a-z0-9]+)"', bloque)


def test_los_cuatro_primeros_son_los_que_pidio_el_owner():
    assert _claves()[:4] == ["estado", "auditoria", "resumen12", "doce"]


def test_el_PL_viejo_queda_de_ultimo():
    """Lo reemplazó `estado`. Se conserva, no se borra: sigue siendo un cuadro
    que alguien puede querer abrir."""
    assert _claves()[-1] == "pl"


def test_no_se_perdio_ningun_sub_tab_al_reordenar():
    """⚠️ Reordenar a mano una lista de dieciocho es como desaparece uno sin
    que nada falle: el sub-tab simplemente deja de estar."""
    claves = _claves()
    esperados = {
        "pl", "revenue", "payroll", "cost", "opex", "property", "consulta",
        "flow", "simple", "summary", "estado", "revdet", "fb", "doce",
        "formato", "auditoria", "resumen12",
    }
    assert set(claves) == esperados, (
        f"faltan {esperados - set(claves)}; sobran {set(claves) - esperados}")
    assert len(claves) == len(set(claves)), "hay un sub-tab repetido"


def test_la_pantalla_ABRE_con_el_primero_de_la_lista():
    """⚠️ El defecto que este cambio podía dejar: con `useState<Vista>("pl")`
    escrito a mano, reordenar los sub-tabs habría dejado la pantalla abriendo en
    el que el owner mandó al FINAL. Nada falla; sólo abre en el cuadro
    equivocado, que es de los errores que nadie reporta como error.
    """
    src = PAGINA.read_text(encoding="utf-8")
    assert "const VISTA_INICIAL: Vista = VISTAS[0].key;" in src
    assert 'useState<Vista>("pl")' not in src


def test_cada_sub_tab_tiene_su_ROTULO():
    """Un `key` sin traducción sale en pantalla como `tab_loquesea`."""
    import json
    es = json.loads((FRONT / "messages/es.json").read_text(encoding="utf-8"))
    plano = json.dumps(es)
    for k in _claves():
        assert f'"tab_{k}"' in plano, f"el sub-tab «{k}» no tiene rótulo"
