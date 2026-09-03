# -*- coding: utf-8 -*-
"""Una respuesta sin cuerpo no se parsea como JSON.

Owner, 2026-09-03, borrando un escenario: *«json falló, no se borró»*.

**Se había borrado.** `DELETE /scenarios/{id}/` contesta `204 No Content`, que
por definición no trae cuerpo, y el cliente hacía `res.json()` igual: sobre un
cuerpo vacío eso tira «Unexpected end of JSON input».

⚠️ El borrado ya había ocurrido y el error salía DESPUÉS, al leer la respuesta.
La pantalla mostraba un fallo de algo que había funcionado — y el usuario
volvía a intentarlo, o daba por perdido un trabajo que estaba hecho. Es de los
peores errores que puede dar una app: mentir sobre el resultado.
"""
import inspect
from pathlib import Path

from app.api import scenarios_api

FRONT = Path(__file__).resolve().parents[2] / "frontend"


def test_hay_endpoints_que_contestan_204():
    """Si ninguno contestara 204, la guarda del cliente sobraría. Contestan."""
    fuente = inspect.getsource(scenarios_api)
    assert "status_code=204" in fuente


def test_el_cliente_NO_parsea_una_respuesta_vacia():
    api = (FRONT / "lib/api.ts").read_text(encoding="utf-8")
    assert 'res.status === 204' in api, (
        "el cliente volvió a parsear todo como JSON: un DELETE que funciona "
        "se vería como un error")
    # El content-length tambien, porque no todos los servidores mandan los dos.
    assert 'res.headers.get("content-length") === "0"' in api


def test_la_guarda_va_ANTES_del_res_json():
    """Después no serviría de nada: el `res.json()` ya habría tirado."""
    api = (FRONT / "lib/api.ts").read_text(encoding="utf-8")
    assert api.index("res.status === 204") < api.index("return res.json()")
