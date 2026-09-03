"""Qué escenario se puede borrar y qué escenario no.

Owner, 2026-09-03: *«¿debería `Working-VIEJO` dejar de estar protegido?»* —
*«sí, ajustalo»*.

La regla era `"working" in version`, una subcadena, y eso protegía de más:
cualquier copia con la palabra adentro quedaba imborrable **para siempre**,
porque el DELETE la rechazaba y la pantalla ni siquiera mostraba el botón.
"""
from pathlib import Path

from app.api.scenarios_api import _scenario_summary, is_protected_version

FRONT = Path(__file__).resolve().parents[2] / "frontend"


def test_los_dos_entregables_siguen_protegidos():
    """Lo que la regla existe para cuidar. Si esto se cae, se puede borrar el
    presupuesto del año."""
    for v in ("Working", "Final"):
        assert is_protected_version(v), v


def test_una_copia_al_lado_SI_se_puede_borrar():
    """⚠️ El motivo del cambio.

    Rehacer el Working dejando el viejo al lado es lo normal; lo que no es
    normal es quedarse con el viejo en la lista para siempre.
    """
    for v in ("Working-VIEJO", "Working viejo", "Working copia",
              "Final anterior", "Working 2026 v1"):
        assert not is_protected_version(v), f"{v!r} quedó protegido de más"


def test_el_espacio_y_las_mayusculas_no_desprotegen():
    """Un `Working ` con espacio de más o un `WORKING` de un import SÍ son el
    entregable — el nombre se normaliza antes de comparar."""
    for v in ("  Working  ", "WORKING", "wOrKiNg", "final", " Final"):
        assert is_protected_version(v), repr(v)


def test_ni_vacio_ni_nulo_revientan():
    assert not is_protected_version("")
    assert not is_protected_version(None)  # type: ignore[arg-type]


def test_el_escenario_le_DICE_a_la_pantalla_si_se_puede_borrar():
    """Sin esto, la pantalla tiene que deducirlo del nombre — que es de donde
    salió este defecto."""
    class Falso:
        id = "x"; hotel_id = "AMA"; year = 2026; type = "BUDGET"
        version = "Working-VIEJO"; status = "draft"; is_locked = False
        actuals_through = 0; created_by = None; created_at = None

    assert _scenario_summary(Falso())["protected"] is False
    Falso.version = "Working"
    assert _scenario_summary(Falso())["protected"] is True


def test_ninguna_pantalla_vuelve_a_deducir_la_regla_del_NOMBRE():
    """⚠️ Guardia contra la segunda verdad.

    Estuvo escrita tres veces —el backend y dos pantallas, cada una con su
    propio regex—. Mientras coincidían no se notaba; el día que difirieran, el
    botón de borrar iba a aparecer sobre un entregable o a esconderse sobre una
    copia. Que es exactamente lo que pasó.
    """
    culpables = []
    for p in FRONT.rglob("*.tsx"):
        if "node_modules" in str(p):
            continue
        for n, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            # Los comentarios pueden NOMBRAR la regla vieja para explicar
            # por qué se fue; lo que no puede volver es el código.
            if linea.strip().startswith(("*", "//", "/*")):
                continue
            if "working" in linea.lower() and "final" in linea.lower() \
                    and ("test(" in linea or "match(" in linea
                         or "includes(" in linea or "/i" in linea):
                culpables.append(f"{p.relative_to(FRONT)}:{n}")
    assert not culpables, (
        "estas pantallas deducen del nombre si un escenario está protegido; "
        f"usá `s.protected`, que lo manda el backend: {culpables}")
