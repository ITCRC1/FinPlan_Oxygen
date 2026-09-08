# -*- coding: utf-8 -*-
"""El mes lo elige la pantalla, no cada sub-tab.

Owner, 2026-09-08: *«el único que debe escoger es la parte de arriba y todo lo
de abajo debe responder a ese mandato; hay una variable intermedia para escoger
pero no debe aplicar ya que el sistema se confunde»*.

La Auditoría tenía su propio `useState(mesInicial)`. Esa forma lee la prop **una
sola vez**, al montarse: al cambiar el mes arriba, la auditoría seguía mostrando
el de cuando se abrió la pestaña. Los dos selectores decían cosas distintas y
ninguno avisaba — y el de abajo ganaba, que es el que nadie estaba mirando.
"""
import pathlib
import re

CIERRE = (pathlib.Path(__file__).resolve().parents[2]
          / "frontend" / "app" / "month-end" / "pl")


def _sub_tabs():
    """Los componentes del cierre. `page.tsx` NO: ahí vive el selector bueno."""
    return [p for p in CIERRE.glob("*.tsx") if p.name != "page.tsx"]


def test_ningun_sub_tab_tiene_su_propio_selector_de_mes():
    culpables = []
    for p in _sub_tabs():
        codigo = "\n".join(
            l for l in p.read_text(encoding="utf-8").splitlines()
            if not l.lstrip().startswith(("//", "*", "/*")))
        if re.search(r"<select[^>]*value=\{mes\}", codigo):
            culpables.append(p.name)
    assert not culpables, (
        f"{culpables} volvieron a poner un selector de mes propio: compite con "
        f"el de la pantalla y gana el que nadie mira")


def test_ningun_sub_tab_guarda_el_mes_en_estado_propio():
    """⚠️ `useState(mesInicial)` es la forma exacta que causó el bug: copia la
    prop al montar y no vuelve a mirarla."""
    culpables = []
    for p in _sub_tabs():
        codigo = "\n".join(
            l for l in p.read_text(encoding="utf-8").splitlines()
            if not l.lstrip().startswith(("//", "*", "/*")))
        if re.search(r"useState\(\s*mes(Inicial)?\s*\)", codigo):
            culpables.append(p.name)
    assert not culpables, f"{culpables} copian el mes a estado propio"


def test_la_auditoria_recibe_el_mes_y_el_horizonte():
    aud = (CIERRE / "Auditoria.tsx").read_text(encoding="utf-8")
    assert "mes: number;" in aud
    assert 'horizonte?: "month" | "ytd" | "full"' in aud
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    assert "mes={mes}" in pagina and "horizonte={horizonte}" in pagina


def test_la_auditoria_dice_que_es_mensual_cuando_el_ambito_no_lo_es():
    """El endpoint cuadra UN mes contra las líneas del motor de ESE mes. En YTD
    o año completo no puede sumar, así que dice cuál mes está mirando en vez de
    aparentar que respondió al ámbito."""
    aud = (CIERRE / "Auditoria.tsx").read_text(encoding="utf-8")
    assert "la auditoría es mensual" in aud
