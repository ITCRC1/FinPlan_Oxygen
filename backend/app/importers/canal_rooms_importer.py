# -*- coding: utf-8 -*-
"""Lee el libro de Sales tal como lo mandan, sin pedirles que lo cambien.

Owner, 2026-10-15: *«hay que buscar una forma como subir los datos desde Excel
tal como los manda Sales group»*.

## La forma del archivo

`Presupuesto_Oxygen_2027_Modelo_v2`, pestaña **`Resumen Manual`**:

    fila  5  la banda del mes      Enero … Diciembre · TOTAL AÑO
    fila  6  la version            Budget 2027 | Proyección 2027 | OTB 2027 |
                                   Budget 2026 | Real 2026 | Real 2025
    col   A  segmento y metrica    «Agencias» y debajo Noches / Ingreso $ /
                                   Tarifa Promedio / % Ocupación

Seis columnas por mes, doce meses, ocho segmentos. El bloque **TOTAL AÑO** se
ignora a proposito: es la suma de los doce y volver a leerlo seria darle dos
origenes al mismo numero.

## ⚠️ Nada se busca por posicion fija

Ni la fila del segmento ni la columna del mes. El libro de Sales va a crecer
—ya trae pestañas por villa para «empezar a registrar el dato por tipo de
habitacion»— y una fila insertada arriba correria todo sin que nada avise. Se
localiza por TEXTO: la banda del mes en la fila 5, la version en la fila 6, y
el segmento por su nombre en la columna A.

## Como se reconoce un segmento

Por nombre normalizado contra el catalogo de la propiedad
(`canal_segmentos.nombre`). Un segmento del archivo que no este en el catalogo
**no se inventa**: se devuelve en `desconocidos` para que alguien decida si es
un canal nuevo o un error de tipeo. Inventarlo dejaria ingreso colgando de un
codigo que ningun reporte conoce.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from openpyxl import load_workbook

HOJA = "Resumen Manual"

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")

#: Las metricas, EXACTAMENTE como se llaman en la columna A del libro.
#: ⚠️ «Ingreso $» con el simbolo: sin el, la metrica no se reconoce y el
#: importador devuelve todas las noches y cero ingreso — que es peor que
#: fallar, porque parece que el archivo viniera vacio de plata.
METRICAS = {"noches": "noches", "ingreso $": "ingreso",
            "tarifa promedio": "tarifa", "% ocupacion": "ocupacion"}

#: Donde termina el detalle por segmento. De ahi para abajo son totales y
#: derivados, y leerlos daria dos origenes al mismo numero.
FIN_DEL_DETALLE = "totales"


def _norm(v) -> str:
    """Sin acentos, sin dobles espacios, en minuscula. Para comparar nombres."""
    if v is None:
        return ""
    t = unicodedata.normalize("NFKD", str(v))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("—", "-").replace("–", "-")
    return re.sub(r"\s+", " ", t).strip().lower()


def _dec(v) -> Decimal | None:
    if v is None or isinstance(v, str):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def versiones_del_libro(ruta) -> list[str]:
    """Las versiones que trae el archivo, en su orden. Para que el usuario elija
    cual va a cual escenario — el archivo no sabe de escenarios de FinPlan."""
    ws = load_workbook(ruta, data_only=True)[HOJA]
    # ⚠️ Solo las columnas que caen bajo una banda de MES. El bloque «TOTAL AÑO»
    # trae sus propias cabeceras —«Var Budget vs 2026», «Real+OTB 2026»— que no
    # son versiones importables sino comparaciones ya calculadas.
    vistas: list[str] = []
    bajo_mes = False
    for j in range(1, ws.max_column + 1):
        banda = _norm(ws.cell(5, j).value)
        if banda in MESES:
            bajo_mes = True
        elif banda:
            bajo_mes = False
        if not bajo_mes:
            continue
        v = ws.cell(6, j).value
        t = re.sub(r"\s+", " ", str(v)).strip() if v else ""
        if t and t.lower() != "segmento / kpi" and t not in vistas:
            vistas.append(t)
    return vistas


def leer(ruta, version: str, segmentos: dict[str, str]) -> dict:
    """Saca una version del libro: {(code, mes): {noches, tarifa, ingreso}}.

    `segmentos` — {nombre normalizado: code}, del catalogo de la propiedad.
    `version`   — tal como aparece en la fila 6 («Real 2026», «OTB 2027 10/26»…).

    Devuelve tambien `desconocidos` (segmentos del archivo sin catalogo) y
    `meses` (cuantas columnas de esa version se encontraron), para que la
    pantalla pueda mostrar que se leyo antes de escribir nada.
    """
    ws = load_workbook(ruta, data_only=True)[HOJA]
    objetivo = _norm(version)

    # ── Las columnas de esta version, mes por mes ────────────────────────────
    # La banda del mes esta en la fila 5 y sólo en su PRIMERA columna; se
    # arrastra hacia la derecha hasta la siguiente banda.
    mes_de_col: dict[int, int] = {}
    mes_actual = 0
    for j in range(1, ws.max_column + 1):
        banda = _norm(ws.cell(5, j).value)
        if banda in MESES:
            mes_actual = MESES.index(banda) + 1
        elif banda:                      # «TOTAL AÑO» u otra cosa: se corta
            mes_actual = 0
        if mes_actual:
            mes_de_col[j] = mes_actual

    cols: dict[int, int] = {}            # mes -> columna de esta version
    for j, mes in mes_de_col.items():
        if _norm(ws.cell(6, j).value) == objetivo:
            cols[mes] = j

    # ── Las filas de cada segmento ───────────────────────────────────────────
    datos: dict[tuple[str, int], dict] = {}
    desconocidos: list[str] = []
    code_actual = None
    for i in range(1, ws.max_row + 1):
        etiqueta = ws.cell(i, 1).value
        if etiqueta is None:
            continue
        crudo = str(etiqueta)
        n = _norm(crudo)
        if not n:
            continue
        # Las metricas van indentadas; el segmento no. Es como el libro los
        # separa, y es mas robusto que una lista de nombres de metrica.
        if not crudo.startswith((" ", "\t")) and n not in METRICAS:
            if n == FIN_DEL_DETALLE:
                break                    # de aca para abajo son totales
            if n == "segmento / kpi" or n.startswith(
                    ("2026 esperado", "var ", "oxygen", "unidades", "uso actual")):
                code_actual = None
                continue
            code_actual = segmentos.get(n)
            if code_actual is None and crudo.strip():
                desconocidos.append(crudo.strip())
            continue
        if code_actual is None or n not in METRICAS:
            continue
        campo = METRICAS[n]
        if campo == "ocupacion":         # se deriva, no se importa
            continue
        for mes, j in cols.items():
            v = _dec(ws.cell(i, j).value)
            if v is None:
                continue
            datos.setdefault((code_actual, mes), {})[campo] = v

    return {"datos": datos, "meses": sorted(cols), "version": version,
            "desconocidos": sorted(set(desconocidos))}
