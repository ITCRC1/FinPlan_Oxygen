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


def test_la_auditoria_le_pasa_el_horizonte_al_backend():
    """Owner, 2026-09-08: *«toda auditoría debe responder a si es mes, YTD o
    full year»*.

    Al principio el ámbito llegaba al componente y ahí se moría: se usaba sólo
    para escribir «la auditoría es mensual». Eso obedecía a medias —el rótulo
    cambiaba, los números no—, que es la forma más cara de no obedecer.
    """
    aud = (CIERRE / "Auditoria.tsx").read_text(encoding="utf-8")
    assert "getAuditoria(scenarioId, mes, horizonte)" in aud
    assert "la auditoría es mensual" not in aud


def test_el_horizonte_esta_en_las_dependencias_de_la_carga():
    """⚠️ Sin `horizonte` en el `useCallback`, cambiar de mes a YTD no volvía a
    pedir nada: la pantalla mostraba el período anterior con el rótulo nuevo,
    que es peor que no cambiar nada."""
    aud = (CIERRE / "Auditoria.tsx").read_text(encoding="utf-8")
    i = aud.index("getAuditoria(scenarioId, mes, horizonte)")
    assert "[scenarioId, mes, horizonte]" in aud[i:i + 1200]


def test_el_rotulo_del_periodo_lo_dice_el_backend():
    """Sólo el backend sabe qué meses acumuló. Un texto armado en la pantalla
    podría decir «Acumulado a Julio» mientras abajo hay otra cosa, y nada
    fallaría."""
    aud = (CIERRE / "Auditoria.tsx").read_text(encoding="utf-8")
    assert "datos?.periodo" in aud


def test_el_excel_del_cierre_baja_el_mismo_periodo_que_la_pantalla():
    """El botón de Excel llama al endpoint por su cuenta. Si bajara siempre el
    mes suelto, el archivo diría «Julio» mientras la pantalla muestra el
    acumulado — y quien lo abra mañana no tiene cómo notarlo."""
    pagina = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    assert "getAuditoria(id, mes, horizonte)" in pagina
    assert "${a.periodo}" in pagina
