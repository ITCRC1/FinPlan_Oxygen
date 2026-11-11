# -*- coding: utf-8 -*-
"""Arma `seed_data/stats_integrity_<HOTEL>.json` a partir del catálogo de CWL.

Owner, 2026-11-11: «necesitamos terminar esto» (el catálogo de estadísticas de
Integrity de Amarena, Garden y Oxygen).

**De dónde sale.** El «STATS CWL 2027.xlsx» de Integrity no es de CWL: es el
catálogo de cuentas del GRUPO («Cargado al 19 de Setiembre del 2024», 9,292
cuentas de clase 9). Con él y la homologación aprobada por el owner se armó
`stats_integrity_CWL.json`. Todo lo que no son noches (covers, spa, tours,
transporte, kilos, horas por depto y puesto) es del grupo y vale igual para
cualquier hotel: se copia tal cual.

**Lo que es de cada hotel: las noches (9000).** Su llave es la del ingreso de
habitaciones: depto · segmento de Opera (N3) · FIT/Grupo (N4) · N5 · día (N6)
· tipo de habitación (N7). Los segmentos son la estructura común de canales
del grupo; el N7 es la POSICIÓN del tipo de habitación en FinPlan
(`room_type_configs` por `sort_order`, igual que `stats_integrity_api.plan`).
Se crea una cuenta por segmento y por tipo ACTIVO; los segmentos sin tipo
(No Show, Pets, Day Use) llevan N7 = 00.

⚠️ Las 9000 son PROPUESTA («CREAR EN INTEGRITY»): todavía no existen en el
catálogo de Integrity. Antes de crearlas, contabilidad tiene que confirmar que
el N7 de las cuentas 4000 del hotel sigue el mismo orden.

    python scripts/generar_stats_integrity.py <cwl.json> <tipos_y_deptos.json> <salida.json>

`tipos_y_deptos.json`: {"hotel": "AMA", "tipos": [{sort_order, code, name,
units, dept_code, active}], "deptos": {codigo: nombre}} — se lee de la base.
"""
import json
import sys

NOMBRES_HOTEL = {"AMA": "Amarena", "OJO": "Ojochal (Garden)", "OXI": "Oxygen", "CWL": "CWL"}


def generar(cwl: dict, hotel: dict) -> dict:
    hid = hotel["hotel"]
    deptos = hotel.get("deptos") or {}
    tipos = sorted(hotel["tipos"], key=lambda t: t["sort_order"])

    otras = []
    for c in cwl["cuentas"]:
        if c["grupo"] == "9000":
            continue
        c = dict(c)
        if deptos.get(c["depto"]):
            c["depto_nombre"] = deptos[c["depto"]]
        otras.append(c)

    # Una plantilla por segmento, sacada de las noches de CWL en 0110.
    noches_cwl = [c for c in cwl["cuentas"] if c["grupo"] == "9000" and c["depto"] == "0110"]
    plantillas: dict[str, dict] = {}
    for c in noches_cwl:
        seg = c["clave"].split("-")[2]
        n7 = c["clave"].split("-")[5]
        p = plantillas.setdefault(seg, {"base": c, "por_tipo": False})
        if n7 != "00":
            p["por_tipo"] = True
            p["base"] = c

    noches = []
    for seg in sorted(plantillas):
        p = plantillas[seg]
        b = p["base"]
        _, _, n3, n4, n5, _ = b["clave"].split("-")
        seg_nombre = b["descripcion"].split(" · ")[0]
        destinos = []
        if p["por_tipo"]:
            for i, t in enumerate(tipos, 1):
                if t.get("active") and int(t.get("units") or 0) > 0:
                    destinos.append(((t.get("dept_code") or "0110"), f"{i:02d}",
                                     f"{t.get('code') or ''} {t['name']}".strip()))
        else:
            for d in sorted({(t.get("dept_code") or "0110") for t in tipos
                             if t.get("active") and int(t.get("units") or 0) > 0}):
                destinos.append((d, "00", "Sin tipo"))
        for d, n7, rotulo in destinos:
            clave = f"9000-{d}-{n3}-{n4}-{n5}-{n7}"
            noches.append({
                **b,
                "clave": clave,
                "codigo": f"9000-{d}-{n3}-{n4}-{n5}-DD-{n7}",
                "descripcion": f"{seg_nombre} · {b['nivel4']} · {rotulo}",
                "depto": d,
                "depto_nombre": deptos.get(d, b["depto_nombre"]),
                "nivel7": f"{n7} {rotulo}",
                "cuenta_ingreso": (f"4000-{d}-{n3}-{n4}-{n5}-DD-{n7}" if b.get("cuenta_ingreso") else ""),
                "en_integrity": False,
                "estado_finplan": "CREAR EN INTEGRITY",
            })

    cuentas = noches + otras
    grupos: dict[str, dict] = {}
    for g, info in cwl["grupos"].items():
        n = sum(1 for c in cuentas if c["grupo"] == g)
        if n:
            grupos[g] = {**info, "cuentas": n}
    nombre = NOMBRES_HOTEL.get(hid, hid)
    return {
        "_nota": [
            f"Catálogo de estadísticas (clase 9) de Integrity para FinPlan {nombre} (2026-11-11).",
            "Generado por scripts/generar_stats_integrity.py desde stats_integrity_CWL.json: el «STATS CWL 2027.xlsx»",
            "es el catálogo del GRUPO (9,292 cuentas), así que covers, spa, tours, kilos y horas valen igual acá.",
            "Las noches (9000) se rehacen con los tipos de habitación de este hotel: N7 = posición del tipo en FinPlan",
            "(sort_order). Son PROPUESTA («CREAR EN INTEGRITY»): contabilidad confirma el N7 contra las cuentas 4000.",
            "`clave` = el código de Integrity SIN el nivel 6 (el día). Solo lectura: no alimenta el P&L ni ningún escenario.",
        ],
        "hotel": hid,
        "version": "2026-11-11",
        "grupos": grupos,
        "cuentas": cuentas,
    }


if __name__ == "__main__":
    cwl = json.load(open(sys.argv[1], encoding="utf-8"))
    hotel = json.load(open(sys.argv[2], encoding="utf-8"))
    out = generar(cwl, hotel)
    with open(sys.argv[3], "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    n = [c for c in out["cuentas"] if c["grupo"] == "9000"]
    print(f"{out['hotel']}: {len(out['cuentas'])} cuentas, {len(out['grupos'])} grupos, {len(n)} noches")
