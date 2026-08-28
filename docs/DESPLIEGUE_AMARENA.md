# Desplegar Amarena — checklist

> **Qué es este repositorio.** Un clon de FinPlan CWL preparado para **Amarena
> Canvas Beach Hotel**. El código es el mismo motor; lo que cambió es que la
> identidad por defecto ya no es Corcovado y que los datos de Corcovado salieron.
>
> **Estado: en cero y listo para desplegar.** Sin usuarios, sin tipos de
> habitación, sin escenarios, sin tarifas. Con el motor contable completo.

---

## Qué significa «en cero» acá

No es «vacío e inservible». Al arrancar, el seed repone **la maquinaria
contable** —que no es de ningún hotel en particular— y **nada más**:

| Se siembra solo, en cada arranque | No se siembra: lo carga el owner |
|---|---|
| `account_mapping` (el ruteo del P&L) | Usuarios |
| `report_line_config` | Los NOMBRES de las categorías |
| `department_catalog` | Tarifas, ocupación, canales |
| `stat_accounts` (cuentas 9xxx) | Planilla |
| `market_codes` | Checkbooks (OPEX, costos) |
| `canales_comerciales` (catálogo) | Escenarios |
| `owners_q` (las 48 filas del reporte) | Paquete y experiencias |

Eso es lo que hace que la carga histórica tenga dónde aterrizar: **sin el mapeo,
un GL subido no cae en ninguna línea del P&L.**

---

## Despliegue en Railway — los tres servicios

Un solo proyecto de Railway con **tres servicios**: Postgres, backend y
frontend. Los dos últimos salen del mismo repo, cambiando el *Root Directory*.

```
Proyecto «FinPlan Amarena»
├── Postgres          ← base propia, no se comparte con ninguna propiedad
├── backend           Root Directory: backend    (FastAPI)
└── frontend          Root Directory: frontend   (Next.js)
```

### Paso 1 — Postgres

*New Project* → **Deploy PostgreSQL**. Nada que configurar: Railway expone
`DATABASE_URL` y el backend la normaliza a `postgresql+asyncpg://` solo
(`app/db.py`).

### Paso 2 — Crear los dos servicios y **sacarles el dominio primero**

*New* → *GitHub Repo* → este repo. Repetirlo dos veces, y en cada uno:

| Servicio | Settings → Root Directory | Watch Paths (opcional) |
|---|---|---|
| `backend` | `backend` | `backend/**` |
| `frontend` | `frontend` | `frontend/**` |

En cada servicio: *Settings → Networking → **Generate Domain***.

⚠️ **Sacar los dos dominios ANTES de cargar variables.** Cada servicio necesita
la URL del otro —el frontend apunta al backend, el backend autoriza al frontend
por CORS— y si se cargan a medias hay que redesplegar de nuevo.

*Watch Paths* evita que un cambio del frontend redespliegue el backend, que
además vuelve a correr las migraciones.

### Paso 3 — Variables del backend

| Variable | Valor | Si falta |
|---|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | **No arranca** |
| `SECRET_KEY` | uno nuevo, ver abajo | Firma con una clave pública conocida |
| `CORS_ORIGINS` | `https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}` | **El navegador bloquea TODO** |
| `HOTEL_ID` | `AMA` | Default `AMA` — ya correcto |
| `HOTEL_NAME` | `Amarena Canvas Beach Hotel` | Default correcto |
| `HOTEL_SHORT_NAME` | `Amarena` | Default correcto |
| `HOTEL_ROOMS` | **el real** | Default `0`, y el seed lo avisa |
| `HOTEL_TC_USD` | el TC del día | Default `530.0000` |

`${{Postgres.DATABASE_URL}}` y `${{frontend.RAILWAY_PUBLIC_DOMAIN}}` son
*reference variables* de Railway: se resuelven solas y siguen al servicio si
cambia de dominio. **El nombre entre llaves es el del servicio** — si lo llamaste
distinto, ajustalo.

Generar el `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

⚠️ **No reusar el de Corcovado.** Firma los tokens de sesión: con el mismo
secreto en dos instalaciones, un token de una vale en la otra.

⚠️ **`CORS_ORIGINS` es la que más confunde cuando falta**: el backend responde
200 a `curl` y la app igual no carga nada, porque el bloqueo lo hace el
navegador. Va la URL **exacta y con `https://`**, sin barra al final. Si más
adelante hay dominio propio, van los dos separados por coma.

El arranque corre solo (`Procfile` / `railway.json`):
`alembic upgrade head` → `python -m app.seed` → `uvicorn`.

### Paso 4 — Variables del frontend

| Variable | Valor |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://${{backend.RAILWAY_PUBLIC_DOMAIN}}/api` |
| `NEXT_PUBLIC_HOTEL_ID` | `AMA` |
| `NEXT_PUBLIC_HOTEL_NAME` | `Amarena Canvas Beach Hotel` |
| `NEXT_PUBLIC_HOTEL_SHORT_NAME` | `Amarena` |

⚠️ **`NEXT_PUBLIC_API_URL` es el error que ya pasó una vez.** Sin ella el deploy
queda **verde** apuntando a `localhost`: se ve desplegado y no funciona. Y ya
termina en `/api` — agregarle otro da 404.

⚠️ **Las `NEXT_PUBLIC_*` se hornean en el build, no se leen al arrancar.**
Cambiar una y reiniciar no hace nada: hay que **redesplegar** para que entre.

⚠️ El prefijo `NEXT_PUBLIC_` es obligatorio: sin él Next no expone la variable al
navegador y llega `undefined`.

### Paso 5 — Redesplegar los dos

Con las variables puestas, *Deploy* en backend y frontend. El orden no importa;
lo que importa es que ninguno quede con el build viejo.

### (Opcional) Cuarto servicio — el cron de Guillermo

Solo si se va a usar el supervisor. Mismo repo, Root Directory `backend`, y en
*Settings* cargar la config de `backend/railway.cron.json`:

* Start command: `python -m app.guillermo.cron`
* Cron schedule: `*/30 * * * *`
* Restart policy: **Never** (un proceso que no termina apaga el cron entero)

Variables: las mismas del backend, más `ANTHROPIC_API_KEY` y `SMTP_HOST` /
`SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` si se quieren los
correos. **Sin este servicio la app funciona igual**; lo único que no corre es
la ronda automática.

---

## 3. El primer administrador

**No hay que insertar nada en la base ni correr ningún script.**

1. Abrir la app desplegada. Cae en `/login`.
2. Como la tabla `users` está vacía, la pantalla ofrece **«crear el primer
   administrador»** en vez del login.
3. Llenar correo, nombre y contraseña (mínimo 8 caracteres).
4. Queda creado con rol `admin` y la sesión abierta.

Esa puerta (`POST /auth/bootstrap`) **se cierra sola** apenas existe el primer
usuario: a partir de ahí devuelve 409 y los demás usuarios se crean desde
**Admin → Usuarios**, que ya exige sesión de admin.

> La contraseña la conoce solo quien la crea. No se anota en este repositorio —
> ver «Códigos y contraseñas» abajo.

---

## 4. Cargar la propiedad, en este orden

1. **Master Data → Provisionamiento**: nombre, habitaciones, tipo de cambio.
2. **Tipos de habitación**: las ocho categorías ya vienen sembradas con los
   códigos estándar del grupo (`BL01`, `BI02`, `PO03`, `RO04`, `BI05`, `BL06`,
   `SH07`, `SH08`), con el rótulo en blanco («Categoría 1»…) y en 0 unidades.
   **Lo único que se hace acá es renombrarlas y ponerles las unidades.**
   ⚠️ **El código no se mueve nunca**: es lo que liga la categoría entre
   escenarios, reportes y propiedades. El nombre se puede editar; el código y el
   orden no. Una categoría que esta propiedad no use se OCULTA, no se borra.
   Si hicieran falta más de ocho, la novena sigue el correlativo (`SH09`).
3. **Paquete / experiencias / canales**: nacen en blanco a propósito.
4. **Escenarios**: crear el primero. ⚠️ No usar «crear copiando» sin revisar el
   origen.
5. Planilla, checkbooks de OPEX y costos, tarifas.

---

## 5. Verificar que nació sano

```bash
curl -s https://<backend-de-amarena>/health
```

Y en la base:

```sql
SELECT id, name, rooms FROM hotels;
-- tiene que decir AMA. Si dice CWL, HOTEL_ID no llegó y hay que corregirlo
-- ANTES de cargar nada: todo lo que se cargue después cuelga de ese id.

SELECT count(*) FROM users;              -- 0 antes del bootstrap, 1 después
SELECT count(*) FROM room_type_configs;  -- 8: los códigos estándar del grupo
SELECT count(*) FROM account_mapping;    -- ~1.172: el motor, que sí se siembra
```

Si `account_mapping` da 0, el seed no corrió y el P&L va a salir en blanco sin
explicar por qué.

---

## Lo que se sacó de este repositorio, y por qué

Al clonar, todo esto viajaba desde Corcovado (2026-08-21):

| Qué | Por qué salió |
|---|---|
| `app/seed_data/CWL/` | Tarifario, experiencias (San Pedrillo, Sierpe/Drake), canales, clasificación de break-even. Estaban en el camino por el que el arranque **siembra la base** |
| `data/Budget 2025W*.xlsx`, `data/raw/Actual P&L May 2026.pdf` | El presupuesto y el P&L reales de Corcovado |
| Los 9 usuarios del equipo en `app/seed.py` | Correos de personas reales y una contraseña compartida en texto plano — una credencial viva de otra propiedad |
| Defaults `CWL` / `Corcovado` / 30 habitaciones / `finplan_cwl` | Una variable que no llegara hacía nacer esta instalación como Corcovado, **sin error** |

Lo que **se quedó**, porque no es de nadie en particular:

* `app/seed_data/*.json` — el motor del P&L, las cuentas estadísticas, el orden
  de la plantilla, el reporte Owners Q.
* `data/formato_mapping_reporte_app.xlsx` — la definición del mapeo.
* `tests/fixtures/*` — modelos de referencia congelados para verificar el motor.
  **Un fixture no llega nunca a la base de datos; una semilla sí.**

⚠️ **Sigue acá el manifiesto de Guillermo de Corcovado** (`seed_guillermo.py`,
`MANIFIESTOS["CWL"]`). Está gateado por hotel —Amarena recibe `[]`— y sirve de
ejemplo del formato. Si se prefiere que no esté, se saca sin consecuencias.

---

## Este repo es un clon, no un despliegue del repo compartido

El diseño original (ver [`CLONAR_PROPIEDAD.md`](CLONAR_PROPIEDAD.md)) era **un
repo, desplegado N veces con variables distintas**, justamente para que un
arreglo se hiciera una vez. Al ser un clon, eso ya no pasa solo:

> **Un arreglo hecho en FinPlan CWL no llega acá, y uno hecho acá no llega
> allá.** Hay que portarlo a mano, y si nadie lo hace las propiedades divergen
> sin que nada avise.

No es un bloqueador —el sistema funciona igual— pero conviene decidir quién
sincroniza y cada cuánto. La alternativa, si en algún momento se quiere volver
al modelo original, es desplegar el repo de CWL dos veces con variables
distintas en vez de mantener dos repos.

---

## Códigos, contraseñas y usuarios maestros

**Nunca en este archivo.** Está en el repositorio: una contraseña o un
`SECRET_KEY` real committeado queda en el historial de git para siempre, aunque
se borre después.

Van en un archivo aparte que **no se commitea**: `docs/CREDENTIALS.local.md`.
