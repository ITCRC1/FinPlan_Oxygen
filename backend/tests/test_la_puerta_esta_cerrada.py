# -*- coding: utf-8 -*-
"""LOS HUECOS DE SEGURIDAD QUE SE TAPARON, Y QUE NO SE PUEDEN DESTAPAR SOLOS.

Auditoría del 2026-08-28. Cada prueba de acá corresponde a un hallazgo, y está
escrita para que **volver atrás cueste una prueba en rojo** y no una revisión
manual seis meses después.

Lo que NO se prueba acá: que `SECRET_KEY` esté puesta en Railway. Eso es
configuración del despliegue, no del código — el código ya se niega a arrancar
sin ella, y eso sí se prueba.
"""
import ast
import importlib
import os
import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]


# ─────────────────────────────────────────────────────────────────────────────
# C-1 · La llave que firma las sesiones
# ─────────────────────────────────────────────────────────────────────────────

def test_sin_secret_key_en_un_servidor_no_arranca():
    """Un despliegue sin `SECRET_KEY` tiene que CAER, no seguir andando.

    Antes caía a `dev-secret-change-me`, que está escrito en el repositorio:
    cualquiera podía firmarse un token de administrador. Y no se notaba, porque
    la app funcionaba perfecto.
    """
    from app.auth import _secreto

    previo = {k: os.environ.get(k) for k in
              ("SECRET_KEY", "RAILWAY_ENVIRONMENT", "VERCEL")}
    try:
        os.environ.pop("SECRET_KEY", None)
        os.environ["RAILWAY_ENVIRONMENT"] = "production"
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _secreto()

        # Y con el valor de desarrollo puesto a mano, tampoco: es el mismo
        # secreto público, sólo que escrito en la variable.
        os.environ["SECRET_KEY"] = "dev-secret-change-me"
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _secreto()

        os.environ["SECRET_KEY"] = "una-llave-propia-y-larga-de-verdad"
        assert _secreto() == "una-llave-propia-y-larga-de-verdad"
    finally:
        for k, v in previo.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_en_local_sigue_andando_sin_variable():
    """El desarrollo no se rompe: la exigencia es sólo en el servidor."""
    from app.auth import _secreto

    previo = {k: os.environ.get(k) for k in
              ("SECRET_KEY", "RAILWAY_ENVIRONMENT", "VERCEL")}
    try:
        for k in previo:
            os.environ.pop(k, None)
        assert _secreto() == "dev-secret-change-me"
    finally:
        for k, v in previo.items():
            if v is not None:
                os.environ[k] = v


# ─────────────────────────────────────────────────────────────────────────────
# C-2 · Freno a la fuerza bruta
# ─────────────────────────────────────────────────────────────────────────────

def test_el_contador_de_fallos_vive_en_la_base():
    """En memoria se borra en cada despliegue, y Railway despliega seguido.

    Un freno que se quita redesplegando no es un freno.
    """
    from app.models.user import User

    for col in ("failed_attempts", "locked_until", "last_failed_at"):
        assert col in User.__table__.columns, f"falta la columna {col} en `users`"


def test_el_login_mira_el_bloqueo_y_cuenta_los_fallos():
    """Se lee el AST del endpoint: que el freno esté REALMENTE en el camino.

    Una constante declarada y nunca usada deja la prueba en verde y la puerta
    abierta, que es la forma en que este tipo de arreglo se deshace solo.
    """
    fuente = (RAIZ / "app" / "api" / "auth_api.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    login = next((n for n in ast.walk(arbol)
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == "login"), None)
    assert login, "no existe el endpoint `login`"
    cuerpo = ast.dump(login)
    assert "_bloqueada" in cuerpo, "el login no consulta el bloqueo"
    assert "failed_attempts" in cuerpo, "el login no cuenta los fallos"
    assert "locked_until" in cuerpo, "el login no fija el bloqueo"
    assert "_ip_permitida" in cuerpo, "el login no aplica el freno por IP"


def test_el_freno_por_ip_corta_la_rafaga():
    from app.api.auth_api import IP_MAX, _ip_permitida, _por_ip

    _por_ip.pop("203.0.113.7", None)
    for i in range(IP_MAX):
        assert _ip_permitida("203.0.113.7"), f"cortó en el intento {i + 1}"
    assert not _ip_permitida("203.0.113.7"), "no cortó al pasarse del tope"
    _por_ip.pop("203.0.113.7", None)


def test_el_bloqueo_se_mide_en_minutos_que_faltan():
    from datetime import datetime, timedelta, timezone

    from app.api.auth_api import _bloqueada
    from app.models.user import User

    u = User(email="x@y.z", password_hash="x")
    u.locked_until = None
    assert _bloqueada(u) == 0, "sin fecha no hay bloqueo"

    u.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert _bloqueada(u) == 0, "un bloqueo vencido no bloquea"

    u.locked_until = datetime.now(timezone.utc) + timedelta(minutes=10)
    assert 1 <= _bloqueada(u) <= 11, "debería faltar cerca de 10 minutos"

    # Una fecha sin zona horaria —como la devuelven algunos motores— no puede
    # reventar el login con un TypeError.
    u.locked_until = (datetime.now(timezone.utc) + timedelta(minutes=10)).replace(tzinfo=None)
    assert _bloqueada(u) > 0


# ─────────────────────────────────────────────────────────────────────────────
# M-1 · CORS
# ─────────────────────────────────────────────────────────────────────────────

def test_no_vuelve_el_comodin_de_vercel():
    """Cualquier página en `*.vercel.app` podía pedirle datos con credenciales."""
    fuente = (RAIZ / "app" / "main.py").read_text(encoding="utf-8")
    activo = [ln for ln in fuente.splitlines()
              if "allow_origin_regex" in ln and not ln.lstrip().startswith("#")]
    assert not activo, (
        "volvió el comodín de CORS. Una propiedad en Vercel agrega su URL "
        f"exacta a CORS_ORIGINS:\n  {activo}")


# ─────────────────────────────────────────────────────────────────────────────
# M-3 · La documentación de la API
# ─────────────────────────────────────────────────────────────────────────────

def test_la_documentacion_se_apaga_en_el_servidor():
    """`/docs` y `/openapi.json` publican el mapa completo de la API."""
    fuente = (RAIZ / "app" / "main.py").read_text(encoding="utf-8")
    for clave in ("docs_url", "redoc_url", "openapi_url"):
        assert clave in fuente, f"`{clave}` no se controla: queda pública"
    assert "_EN_SERVIDOR" in fuente


# ─────────────────────────────────────────────────────────────────────────────
# M-4 · Dependencias
# ─────────────────────────────────────────────────────────────────────────────

def test_las_dependencias_estan_fijadas():
    """Con `>=`, cada build resuelve versiones nuevas por su cuenta."""
    req = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
    sueltas = [ln.strip() for ln in req.splitlines()
               if ln.strip() and not ln.strip().startswith("#")
               and "==" not in ln]
    assert not sueltas, f"estas no están fijadas: {sueltas}"


# ─────────────────────────────────────────────────────────────────────────────
# M-5 · Registro de la puerta
# ─────────────────────────────────────────────────────────────────────────────

def test_existe_el_registro_y_no_guarda_credenciales():
    from app.models.auth_event import EVENTOS, AuthEvent

    columnas = set(AuthEvent.__table__.columns.keys())
    for c in ("evento", "email", "ip", "creado", "detalle", "actor_email"):
        assert c in columnas, f"falta `{c}` en auth_events"

    prohibidas = {"password", "password_hash", "clave", "token", "hash"}
    assert not (columnas & prohibidas), (
        "el registro de seguridad no puede guardar credenciales: "
        f"{columnas & prohibidas}")

    for e in ("LOGIN_OK", "LOGIN_FALLIDO", "CUENTA_BLOQUEADA", "USUARIO_EDITADO"):
        assert e in EVENTOS


def test_el_login_y_las_altas_dejan_rastro():
    fuente = (RAIZ / "app" / "api" / "auth_api.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    for nombre in ("login", "bootstrap_admin", "create_user", "update_user"):
        fn = next((n for n in ast.walk(arbol)
                   if isinstance(n, ast.AsyncFunctionDef) and n.name == nombre), None)
        assert fn, f"no existe `{nombre}`"
        assert "_registrar" in ast.dump(fn), f"`{nombre}` no registra nada"


# ─────────────────────────────────────────────────────────────────────────────
# B-1 · Política de contraseña
# ─────────────────────────────────────────────────────────────────────────────

def test_la_clave_se_valida_en_un_solo_lugar():
    """Estaba copiada en tres endpoints más el guion de recuperación.

    Con la regla repetida, el sitio que quede más permisivo es el que manda:
    alcanza con entrar por ahí.
    """
    fuente = (RAIZ / "app" / "api" / "auth_api.py").read_text(encoding="utf-8")
    assert "len(body.password) < 8" not in fuente, "quedó una validación suelta"
    assert fuente.count("validar_clave(") >= 3

    guion = (RAIZ / "scripts" / "reset_password.py").read_text(encoding="utf-8")
    assert "from app.auth import CLAVE_MINIMA" in guion, (
        "el guion volvió a definir su propio mínimo; el más chico es el que manda")


@pytest.mark.parametrize("mala", [
    "corta", "1234567890", "password123", "aaaaaaaaaaaa", "",
])
def test_las_claves_flojas_se_rechazan(mala):
    from app.auth import validar_clave
    from app.errores import ErrorApi

    with pytest.raises(ErrorApi):
        validar_clave(mala)


def test_una_clave_razonable_pasa():
    from app.auth import validar_clave

    validar_clave("caballo-bateria-grapa7")   # no levanta nada


# ─────────────────────────────────────────────────────────────────────────────
# B-3 · El último administrador
# ─────────────────────────────────────────────────────────────────────────────

def test_no_se_puede_quitar_al_ultimo_admin():
    """Con el bootstrap cerrado y sin admin, nadie vuelve a entrar por la app.

    La instalación de Amarena ya vivió exactamente eso.
    """
    fuente = (RAIZ / "app" / "api" / "auth_api.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "update_user")
    cuerpo = ast.dump(fn)
    assert "ultimo_admin" in cuerpo, "no se comprueba que quede algún admin"
    assert "pierde_admin" in cuerpo


# ─────────────────────────────────────────────────────────────────────────────
# B-4 · La carrera del primer administrador
# ─────────────────────────────────────────────────────────────────────────────

def test_el_bootstrap_toma_un_candado():
    """Contar y después insertar, sin nada en el medio, deja pasar a dos.

    Es la única puerta del sistema que se abre sin credenciales.
    """
    fuente = (RAIZ / "app" / "api" / "auth_api.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "bootstrap_admin")
    assert "pg_advisory_xact_lock" in ast.dump(fn)


# ─────────────────────────────────────────────────────────────────────────────
# La migración
# ─────────────────────────────────────────────────────────────────────────────

def test_la_migracion_del_freno_existe_y_es_reversible():
    """⚠️ Se busca por NOMBRE, no por numero.

    Antes esta guarda exigia el archivo `137_...` exacto, y el numero no es el
    mismo en todas las instalaciones: cada una fue agregando sus migraciones en
    otro orden, asi que el mismo cambio es la 137 en una y la 138 en otra.
    Atarse al numero hacia fallar a una instalacion que TIENE la migracion,
    solo que numerada distinto — un rojo que no dice nada del sistema.

    Lo que de verdad importa es que exista, que encadene con la anterior, y que
    sepa volver atras.
    """
    versiones = RAIZ / "alembic" / "versions"
    candidatas = sorted(versiones.glob("*_freno_al_login_y_registro_de_puerta.py"))
    assert candidatas, "falta la migración del freno al login"
    assert len(candidatas) == 1, "hay dos copias de la misma migración: %s" % candidatas
    texto = candidatas[0].read_text(encoding="utf-8")
    # Encadenada con la anterior, sea cual sea su numero.
    import re
    m = re.search(r'^down_revision = "(\d+)"$', texto, re.M)
    assert m, "la migración no dice de cuál cuelga"
    anterior = m.group(1)
    assert sorted(versiones.glob("%s_*.py" % anterior)), (
        "cuelga de la %s, que no existe: alembic tendría un hueco" % anterior)
    assert "def downgrade" in texto
    for col in ("failed_attempts", "locked_until", "last_failed_at"):
        assert col in texto
    assert "auth_events" in texto

    # Nadie más puede colgar del MISMO padre: dos hijas son dos cabezas, y dos
    # cabezas rompen `alembic upgrade head` en el arranque, que es como se
    # despliega. El padre se lee de la propia migración —no se escribe acá— por
    # la misma razón por la que el archivo se busca por nombre.
    hijas = [p.name for p in versiones.glob("*.py")
             if 'down_revision = "%s"' % anterior in p.read_text(encoding="utf-8")]
    assert hijas == [candidatas[0].name], (
        "hay más de una migración sobre la %s: %s" % (anterior, hijas))
