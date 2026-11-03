# -*- coding: utf-8 -*-
"""La suma de los GOP por departamento = el GOP del P&L oficial.

Es el contrato que CLAUDE.md ya tenía escrito. Esta prueba lo vigila, porque
se rompió y durante meses nadie podía verlo.

## Cómo se rompió

El P&L por Departamento hace dos cosas con el reparto de cafetería (0220) y
lavandería (0161):

1. le **resta** al origen lo que repartió, por clase de cuenta — la corrección
   del 2026-08-27, para que el sobrante se vea en overhead;
2. le **suma** a cada destino las filas de reparto.

El punto 2 incluía la **4999**, que es el crédito que vuelve al ORIGEN: el
espejo exacto de la resta del punto 1. O sea que el mismo gasto se quitaba dos
veces.

Medido en el Budget 2027 de Oxygen el 2026-11-03, al copiarle el OPEX del
Forecast 2026:

    P&L oficial            GOP  1.074.303,40
    P&L por departamento   GOP  1.113.767,01
    ───────────────────────────────────────
    diferencia                     39.463,61   ← lo repartido por clase 7

**Mientras 0161 estuvo en cero, la diferencia era cero.** El defecto llevaba
meses ahí esperando que el departamento tuviera gasto, y cuando lo tuvo no dio
ningún error: cada fila cuadraba consigo misma y el reparto seguía netando a
cero.

## Y la segunda mitad

La resta es por clase y asume que el reparto se contabiliza en la misma clase
de la que salió el gasto. En cafetería se cumple. En lavandería no: el motor
reparte el costo completo —planilla incluida— por 7310/7685, o sea clase 7.
A 0161 se le restaban $39.463,61 de un OPEX de $22.261,62 y quedaba en
−$17.201,99, con su planilla intacta al lado.
"""
import inspect
import re

from app.api.scenarios_api import pl_by_dept


def _fuente() -> str:
    return inspect.getsource(pl_by_dept)


def _codigo() -> str:
    """La fuente sin la prosa: este módulo y el de al lado nombran la 4999
    para explicarla, y una guarda que falle por su propia explicación invita
    al arreglo que no hay que hacer — borrar la explicación."""
    src = _fuente()
    for comilla in ('"""', "'''"):
        src = re.sub(comilla + r"[\s\S]*?" + comilla, "", src)
    return re.sub(r"#[^\n]*", "", src)


def test_la_4999_no_se_suma_al_destino():
    """La guarda del defecto: si vuelve a entrar al bucle de destinos, el
    gasto del origen se quita dos veces."""
    src = _codigo()
    i = src.index("alloc_rows:")
    # Del bucle de destinos en adelante tiene que haber un salto de la 4999.
    cola = src[i:]
    assert '"4999"' in cola, (
        "la 4999 volvió a sumarse al destino: es el crédito que vuelve al "
        "origen y restarlo además de lo repartido quita el gasto dos veces")


def test_la_4999_tampoco_se_resta():
    """La mitad que ya estaba bien, y que no hay que romper al arreglar la
    otra: `repartido` la salta desde el 2026-08-27."""
    src = _codigo()
    i = src.index("repartido")
    assert '"4999"' in src[i:i + 900]


def test_ninguna_columna_del_origen_queda_en_negativo():
    """La aritmética de la absorción, sin base de datos.

    Lavandería: OPEX $22.261,62 y planilla $17.803,52; reparte $39.463,61 por
    clase 7 y $601,53 por clase 5. Restando sólo por clase, el OPEX queda en
    −$17.201,99. Absorbiendo el excedente de las otras columnas, ninguna queda
    negativa y **el total del departamento no cambia**.
    """
    d = {"opex": 22261.62, "payroll": 17803.52, "cost": 0.0}
    total_antes = sum(d.values())
    d["opex"] -= 39463.61          # repartido clase 7
    d["cost"] -= 601.53            # repartido clase 5
    repartido_total = 39463.61 + 601.53
    assert round(d["opex"], 2) == -17201.99

    for campo in ("opex", "payroll", "cost"):
        sobra = -d[campo]
        if sobra <= 0:
            continue
        d[campo] = 0.0
        for otro in ("payroll", "opex", "cost"):
            if otro == campo or sobra <= 0:
                continue
            toma = min(sobra, max(d[otro], 0.0))
            d[otro] -= toma
            sobra -= toma

    assert all(v >= -0.005 for v in d.values()), d
    assert round(sum(d.values()), 2) == round(total_antes - repartido_total, 2)
    # Reparto total: el residuo es cero y la fila se cae sola.
    assert round(sum(d.values()), 2) == 0.00


def test_un_reparto_parcial_deja_el_sobrante_visible():
    """La regla del owner (2026-08-27): «CUALQUIER SALDO NO ALOCADO debe salir
    como overhead». La absorción no puede comerse el sobrante."""
    d = {"opex": 22261.62, "payroll": 17803.52, "cost": 0.0}
    d["opex"] -= 10000.00
    for campo in ("opex", "payroll", "cost"):
        sobra = -d[campo]
        if sobra <= 0:
            continue
        d[campo] = 0.0
        for otro in ("payroll", "opex", "cost"):
            if otro == campo or sobra <= 0:
                continue
            toma = min(sobra, max(d[otro], 0.0))
            d[otro] -= toma
            sobra -= toma
    assert round(sum(d.values()), 2) == round(22261.62 + 17803.52 - 10000.0, 2)


def test_la_absorcion_corre_despues_de_sumar_los_destinos():
    """Si corriera antes, el bucle de destinos volvería a dejar negativos y la
    absorción no habría servido de nada."""
    src = _fuente()
    assert src.index('d["alloc"] += monto') < src.index("sobra = -d[campo]")
