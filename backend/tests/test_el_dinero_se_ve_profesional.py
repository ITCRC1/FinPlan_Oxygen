# -*- coding: utf-8 -*-
"""El dinero en pantalla: con signo, con separador, y el negativo en rojo.

Owner, 2026-10-08: *«que todo esto tenga formato profesional… que se vean bien
con el signo de dólares y formateado»* y *«todos los negativos deben estar en
rojo»*. Es además la regla del design system (CLAUDE.md §26.9: *«NÚMERO
NEGATIVO: siempre en rojo»*).

## Lo que se encontró

El checkbook de ingresos mostraba `90766.98` en cada celda al lado de un total
en `$1,074,207.63`. Doce columnas sin separador son ilegibles justo donde más
importa: nadie distingue 90.766 de 907.669 de un vistazo.

Y `fmtUsd` devolvía **`$-1,234.56`** — el signo detrás del símbolo. Se ve en
cualquier línea que pueda ir en negativo, y es de esas cosas que un contador
nota al instante.

## Qué cuida este archivo

Las dos piezas que resolvieron eso, porque son chicas y fáciles de desarmar sin
querer. No cuida que cada pantalla las use: eso se ve en el navegador, y hay
cuarenta formateadores de dinero en la aplicación que `<Monto>` envuelve sin
tocar.
"""
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[2] / "frontend"
FMT = FRONT / "lib" / "fmt.ts"
MONTO = FRONT / "components" / "Monto.tsx"
INPUT = FRONT / "components" / "InputMoneda.tsx"


def _src(p: Path) -> str:
    assert p.exists(), f"falta {p.name}"
    return p.read_text(encoding="utf-8")


# ── El signo va antes del simbolo ────────────────────────────────────────────

def test_fmt_usd_pone_el_signo_antes_del_simbolo():
    """`-$1,234.56`, no `$-1,234.56`. Lo segundo es lo que devolvia antes."""
    s = _src(FMT)
    assert '"-$"' in s, "fmtUsd ya no arma el negativo como «-$»"
    # La forma vieja: pegar "$" delante del numero ya formateado con su signo.
    assert '"$" + n.toLocaleString' not in s, (
        "volvio el «$» delante del numero con signo: da $-1,234.56")


def test_fmt_usd_separa_los_miles():
    """Sin separador, doce columnas de seis cifras son ilegibles."""
    s = _src(FMT)
    assert "toLocaleString" in s and "en-US" in s


# ── El negativo se reconoce escrito de cualquier forma ───────────────────────

def test_monto_reconoce_las_cuatro_formas_del_negativo():
    """Hay cerca de cuarenta formateadores de dinero en la aplicacion y cada
    uno escribe el negativo a su manera. `<Monto>` los envuelve a todos sin
    tocarlos, asi que tiene que reconocer las cuatro."""
    s = _src(MONTO)
    assert 'startsWith("-")' in s, "el guion normal: -1,234.56"
    assert 'startsWith("−")' in s, "el menos tipografico: −1,234.56"
    assert 'startsWith("(")' in s, "el parentesis contable: ($1,234)"
    assert "[-−]" in s, "la forma vieja de fmtUsd: $-1,234.56"


def test_monto_no_pinta_la_raya_de_vacio():
    """`—` no es un numero. Si entrara por «empieza con guion» —que no es el
    mismo caracter— toda celda vacia saldria en rojo."""
    s = _src(MONTO)
    assert "—" in s, "falta la nota sobre la raya larga"


def test_monto_usa_el_token_del_design_system():
    """El rojo sale de `--negative`, no de un hex suelto: cambiar el tema tiene
    que cambiarlo tambien aca."""
    assert "var(--negative" in _src(MONTO)


# ── La celda editable también ────────────────────────────────────────────────

def test_la_celda_editable_colorea_el_negativo():
    s = _src(INPUT)
    assert "esNegativo" in s, "InputMoneda dejo de mirar el signo"
    assert "var(--negative" in s


def test_la_celda_editable_se_lee_formateada_y_se_edita_en_crudo():
    """Las dos mitades del arreglo. Si se cae una, o no se lee o no se escribe."""
    s = _src(INPUT)
    assert "fmtUsd" in s and "money2" in s
    assert "foco ? crudo : fmtUsd(crudo)" in s, (
        "se perdio el cambio entre leer formateado y editar en crudo")


def test_la_celda_editable_tiene_ancho_minimo():
    """⚠️ Sin esto la columna corta el numero: un `width: 100%` dentro de una
    celda no le da ancho propio, y al pasar de `90766.98` a `-$90,766.98` el
    ultimo digito desaparece sin que nada lo avise. Medido en el banco de
    pruebas el 2026-10-08: 108px entran `-$200,000.00`."""
    assert "minWidth: 108" in _src(INPUT)


def test_la_celda_editable_no_es_type_number():
    """Las flechitas del navegador se disparan con la rueda del mouse estando
    sobre la celda: un scroll distraido cambia un presupuesto."""
    import re
    # Sin el comentario de cabecera, que EXPLICA por que no se usa `type="number"`
    # y haria pasar la prueba por la razon equivocada.
    s = re.sub(r"/\*.*?\*/", "", _src(INPUT), flags=re.S)
    assert 'type="text"' in s
    assert 'type="number"' not in s


# ── Las pantallas que ya decidian un color no se pisan ───────────────────────

@pytest.mark.parametrize("pantalla", [
    "app/month-end/pl/page.tsx",
    "app/reports/pl-by-dept/page.tsx",
])
def test_la_varianza_conserva_su_color_de_negocio(pantalla):
    """⚠️ En un GASTO, una variacion negativa es AHORRO y va en VERDE
    (CLAUDE.md §26.8). El envoltorio de `<Monto>` se salteo a proposito las
    celdas que ya calculan su color: pintarlas de rojo por ser negativas seria
    contradecir la regla que el propio sistema aplica."""
    s = _src(FRONT / pantalla)
    assert "var(--positive" in s or "positive" in s, (
        f"{pantalla} dejo de distinguir favorable de desfavorable")
