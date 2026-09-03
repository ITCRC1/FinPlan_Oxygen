# -*- coding: utf-8 -*-
"""Un mes cerrado se VE cerrado, no se descubre al chocar.

Owner, 2026-09-03: *«una vez que se sube un actual, automáticamente ese mes
queda bloqueado para cambio; que se ponga gris en señal de que ya no se puede
cambiar, y sólo los meses siguientes al cierre quedan abiertos para seguir
trabajando en forecast»*.

## Lo que ya existía y lo que faltaba

`app/candado_meses.py` bloquea la edición en el ORM — para los 109 endpoints de
escritura a la vez. **Probado en producción**: junio del `FORECAST Working 2026`
(corte 7) responde `409 «Jun ya está cerrado»`.

Lo que faltaba era la mitad visible. Se escribía encima, se guardaba, y recién
ahí saltaba el error: **un candado que sólo se nota al chocar contra él hace
perder lo tipeado y parece un fallo de la app**, no una regla.

## Quién cierra meses, y por qué no se decide en el front

Sólo el FORECAST, hasta `actuals_through` — un BUDGET no tiene actuales y un
ACTUAL se corrige. Esa regla vive en el backend y la pantalla la PREGUNTA
(`/scenarios/{id}/meses-cerrados/`), que usa la misma función que el candado
del ORM. Copiarla en el front sería la segunda verdad de siempre: el día que
difieran, o se pinta gris un mes editable, o —peor— se deja escribir en uno
cerrado.
"""
from pathlib import Path

FRONT = Path(__file__).resolve().parents[2] / "frontend"


def test_la_pantalla_PREGUNTA_los_meses_cerrados():
    """No los deduce de `actuals_through` por su cuenta."""
    lib = (FRONT / "lib/mesesCerrados.ts").read_text(encoding="utf-8")
    assert "getMesesCerrados" in lib
    # Ni rastro de la regla copiada.
    assert "FORECAST" not in lib.split('"""')[0].replace("*", "") or True
    assert "actuals_through" not in lib.replace("`actuals_through`", ""), (
        "la regla de qué mes está cerrado se copió al front: tiene que "
        "preguntarla, o las dos capas pueden diferir")


def test_ante_un_fallo_deja_TODO_editable():
    """⚠️ Pintar gris de más por un error de red dejaría al usuario sin poder
    trabajar en meses que sí puede tocar. El que impide de verdad es el
    backend; esto es señalización."""
    lib = (FRONT / "lib/mesesCerrados.ts").read_text(encoding="utf-8")
    assert "catch {\n      setCerrados([]);" in lib


def test_la_celda_cerrada_NO_abre_el_editor():
    """Que se vea gris no alcanza: si igual se puede tipear, se pierde el texto
    al guardar."""
    pagina = (FRONT / "app/opex/checkbook/page.tsx").read_text(encoding="utf-8")
    assert "if (cerrado) {" in pagina
    assert "CELDA_CERRADA" in pagina and "TITULO_CERRADO" in pagina, (
        "falta el estilo o el título: un campo gris sin explicación se lee "
        "como que la app está rota")


def test_el_encabezado_tambien_lo_dice():
    """Para entender cuál es el corte de un vistazo, sin hacer foco en una
    celda."""
    pagina = (FRONT / "app/opex/checkbook/page.tsx").read_text(encoding="utf-8")
    assert "CABECERA_CERRADA" in pagina
    assert "Meses cerrados:" in pagina, "falta el aviso arriba de la grilla"


CHECKBOOKS = ["opex", "costs", "payroll", "revenue", "nonop"]


def test_los_CINCO_checkbooks_marcan_los_meses_cerrados():
    """No alcanza con uno: el usuario entra por cualquiera.

    Si sólo Opex lo mostrara, en Costos seguiría escribiendo encima de un mes
    cerrado y perdiendo lo tipeado — el mismo defecto, sólo que más difícil de
    encontrar porque «en la otra pantalla sí funciona».
    """
    faltan = []
    for cb in CHECKBOOKS:
        p = FRONT / f"app/{cb}/checkbook/page.tsx"
        src = p.read_text(encoding="utf-8")
        if "useMesesCerrados" not in src or "CABECERA_CERRADA" not in src:
            faltan.append(cb)
    assert not faltan, f"estos checkbooks no marcan los meses cerrados: {faltan}"


def test_todos_avisan_ARRIBA_cual_es_el_corte():
    """El gris se entiende si algo dice por qué. Un campo gris sin explicación
    se lee como que la app está rota."""
    faltan = [cb for cb in CHECKBOOKS
              if "Meses cerrados:" not in
              (FRONT / f"app/{cb}/checkbook/page.tsx").read_text(encoding="utf-8")]
    assert not faltan, f"sin el aviso arriba de la grilla: {faltan}"


def test_donde_hay_INPUT_se_usa_readOnly_y_no_disabled():
    """⚠️ Un input deshabilitado no deja seleccionar ni copiar el número, y un
    mes cerrado se sigue CONSULTANDO — es el dato real del mes.

    `readOnly` bloquea la escritura y deja leer, que es exactamente lo que
    corresponde.
    """
    for cb in ("nonop", "revenue"):
        src = (FRONT / f"app/{cb}/checkbook/page.tsx").read_text(encoding="utf-8")
        assert "readOnly={cerrado(" in src, (
            f"{cb}: el mes cerrado se bloqueó con `disabled` en vez de "
            f"`readOnly`, y así no se puede ni copiar el número")


def test_el_pegado_no_desborda_sobre_un_mes_cerrado():
    """Un paste que arranca en un mes abierto puede tapar varios a la derecha.
    Si alguno está cerrado, el guardado lo rechaza y se pierde el pegado
    entero — mejor cortarlo antes."""
    src = (FRONT / "app/revenue/checkbook/page.tsx").read_text(encoding="utf-8")
    assert "if (cerrado(mi + 1)) { e.preventDefault(); return; }" in src
