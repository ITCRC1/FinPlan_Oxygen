# -*- coding: utf-8 -*-
"""Con qué escenarios abre la app, y por qué nunca más el 2035.

Owner, 2026-09-03: *«siempre de primero actual, segundo budget 2026 y después
forecast 2026. siempre entro y están 2035 y otras versiones. quiero que estén
ahí fijas, y si yo quiero cambiarlo, yo lo hago. Además estas mismas versiones
quiero que las siembres en todos los sub tabs»*.

⚠️ Este defecto ya se «arregló» dos veces (14-ago y 19-ago) y volvió las dos
veces, por dos caminos distintos. Estas pruebas cierran los dos.
"""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[2] / "frontend"
PREF = FRONT / "lib/escenarioPreferido.ts"
CIERRE = FRONT / "app/month-end/pl"
SUBTABS = ["Auditoria", "DoceMeses", "Formato", "ResumenDoceMeses"]


def test_cada_papel_abre_DONDE_EL_OWNER_PIDIO():
    """La regla del owner, escrita en UN solo lugar.

    ⚠️ **No son todos el mismo año, y esa es la regla.** Esta prueba exigia
    `2026` para los tres y se llamaba `..._apuntan_a_2026`; el 2026-10-03 el
    owner movio el BUDGET a 2027 Working —«quiero que en planning dejes
    esclavizado Budget 2027 Working»— porque ese año dejo de estar en cero, y la
    prueba se quedo pidiendo el año viejo. Quedo en rojo dos dias diciendo que
    el codigo estaba mal cuando el codigo era lo unico al dia.

    El ACTUAL y el FORECAST siguen en 2026: el actual es el año que se esta
    cerrando y el forecast el que se esta trabajando. El historial de POR QUE
    esta en `test_escenario_por_defecto.py`, que es donde se lee la decision.
    """
    src = PREF.read_text(encoding="utf-8")
    bloque = src[src.index("export const PREFERENCIA"):src.index("export const GENERACION")]
    ESPERADO = {"actual": "2026", "budget": "2027", "forecast": "2026"}
    for rol, anio in ESPERADO.items():
        m = re.search(rol + r":\s*\{[^}]*year:\s*(\d{4})", bloque)
        assert m, f"no encontré el año de {rol}"
        assert m.group(1) == anio, (
            f"{rol} abre en {m.group(1)} y el owner pidió {anio}")


def test_la_limpieza_alcanza_a_la_memoria_de_CIERRE_DE_MES():
    """⚠️ La razón por la que el 2035 volvía.

    Cierre de Mes guarda sus cuatro ranuras juntas bajo `finplan.month-end.pl`
    —con PUNTOS—, y la limpieza de generación sólo barría `finplan_esc_`. Así,
    un id de Working 2035 elegido una vez sobrevivía a todos los cambios de
    regla: lo guardado le gana al default, en silencio y para siempre.
    """
    src = PREF.read_text(encoding="utf-8")
    limpieza = src[src.index("export function limpiarSiEsDeOtraGeneracion"):]
    limpieza = limpieza[:limpieza.index("\n}")]
    assert 'startsWith("finplan")' in limpieza, (
        "la limpieza volvió a mirar sólo un prefijo angosto; la memoria de "
        "Cierre de Mes queda afuera y el escenario viejo se queda pegado")
    # Y sin desloguear a nadie.
    assert "SAGRADAS" in limpieza and "finplan_token" in src


def test_cierre_de_mes_LIMPIA_antes_de_leer_lo_guardado():
    """De nada sirve la limpieza si la pantalla lee su memoria sin pasar por
    ella."""
    src = (CIERRE / "page.tsx").read_text(encoding="utf-8")
    i_limpia = src.index("limpiarSiEsDeOtraGeneracion()")
    i_lee = src.index("getItem(MEMORIA)")
    assert i_limpia < i_lee, (
        "la pantalla lee su memoria antes de limpiarla: el id viejo gana")


def test_ningun_subtab_elige_por_ORDEN_DE_LISTA():
    """⚠️ El otro camino por el que volvía el 2035.

    Los cuatro sub-tabs traían su propia copia de
    `escenarios.find(s => s.type === tipo)` —«el primero de ese tipo»— y
    `GET /scenarios/` ordena por año DESCENDENTE: el primer BUDGET es el
    Working 2035. Cada sub-tab abría en un presupuesto real, vacío y de otro
    año, sin que nada fallara.
    """
    culpables = []
    for f in SUBTABS:
        src = (CIERRE / f"{f}.tsx").read_text(encoding="utf-8")
        cuerpo = src[src.index("function primeroDe"):]
        cuerpo = cuerpo[:cuerpo.index("\n}")]
        if "sembrarTres" not in cuerpo:
            culpables.append(f)
    assert not culpables, (
        f"estos sub-tabs eligen por orden de lista en vez de por la regla del "
        f"owner: {culpables}")


def test_los_cuatro_subtabs_siembran_las_TRES_versiones():
    """Owner: «lo más probable que haga análisis de 3 versiones»."""
    faltan = [f for f in SUBTABS
              if "sembrarTres" not in (CIERRE / f"{f}.tsx").read_text(encoding="utf-8")]
    assert not faltan, f"sin la siembra compartida: {faltan}"


def test_la_siembra_devuelve_VACIO_y_no_cualquier_cosa():
    """Un papel que no existe deja la ranura vacía.

    ⚠️ Caer en «el primero que haya» es cómo se ve un dato equivocado como si
    fuera el bueno. Una ranura vacía se ve vacía.
    """
    src = PREF.read_text(encoding="utf-8")
    bloque = src[src.index("export function sembrarTres"):]
    assert bloque.count('?.id ?? ""') == 3
