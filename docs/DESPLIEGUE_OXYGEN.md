# Desplegar Oxygen — cómo se hace hoy

> **Última revisión: 2026-09-03.**
>
> ⚠️ **`DESPLIEGUE_AMARENA.md` no aplica a este repositorio.** Quedó del clon y
> describe otra propiedad. Este archivo es el de acá.

## ⚠️ El push a GitHub está bloqueado

```
remote: Permission to ITCRC1/FinPlan_Oxygen.git denied to Bismark1973.
```

La cuenta de la máquina del Financial Controller **no es colaboradora** de este
repositorio (sí lo es del de Amarena, verificado con `git push --dry-run`), y el
owner **no tiene acceso** a la configuración de GitHub para agregarla.

**Consecuencia, y hay que decirla clara: producción corre código que este
repositorio no tiene.** Los commits viven sólo en el disco del Financial
Controller, en la rama `port/cierre-amarena` de `C:\dev\FinPlan_Oxygen`.

**No borrar esa carpeta.** Es la única copia.

Se destraba agregando a `Bismark1973` como colaborador con permiso *Write*.
Mientras tanto se despliega por Railway.

## Cómo se despliega

Cada servicio tiene su propio `railway.json` y se sube desde su subdirectorio:

```bash
cd backend && railway up --service "FinPlan_Oxygen Backend" --ci
```

```bash
cd frontend && railway up --service "FinPlan_Oxygen" --ci
```

El link de Railway es **por directorio** y hay que hacerlo una vez:

```bash
railway link --project c102d8bf-16dd-42fe-8404-d1d515fd9970 --environment production --service "FinPlan_Oxygen Backend"
```

⚠️ El nombre del backend lleva **espacio**, no guion: `FinPlan_Oxygen Backend`.

## Lo que hay que mirar ANTES de subir

El arranque es `alembic upgrade head && python -m app.seed && uvicorn`. **Si la
migración falla, el servicio no levanta** (reintenta 3 veces y se queda abajo).
El despliegue anterior sigue corriendo mientras el nuevo no arranque, así que un
fallo no deja la app caída — pero tampoco entra el cambio.

Antes de subir una migración, comparar la revisión de producción contra la
cadena local:

```sql
select version_num from alembic_version;
```

El 2026-09-03 la `138` encadenaba sobre la `137`, que es la de seguridad propia
de Oxygen. Las dos instalaciones habían creado un «137» el mismo día; la de
Amarena se renumeró a 138 al portarla.

## Verificar después

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://finplanoxygen-backend.up.railway.app/health
curl -s -o /dev/null -w "%{http_code}\n" https://finplanoxygen.up.railway.app
```

Y contra la base, que es lo que de verdad dice si el cambio entró — la receta de
`railway ssh` está en la memoria del proyecto. **Dos trampas:** el intérprete hoy
está en `/app/.venv/bin/python` y no en `/proc/1/exe`, y `recalculate_scenario`
hace su propio `commit`, así que un guion «en seco» que recalcula **ya escribió**.

## Estado de los datos (2026-09-03)

| | |
|---|---|
| `HOTEL_ID` | `OXI` — Oxygen Jungle Villas |
| Categorías | **5** activas, 13 unidades |
| Actuales | **ninguno** (`actual_entries` = 0) |
| `FORECAST Working 2026` | corte 0, sin filas de gasto |
| Presupuestos 2026 y 2027 | arrancan en **junio**; enero–mayo en cero en los datos |
| Club Madresal / Área Recreativa | no se operan |
