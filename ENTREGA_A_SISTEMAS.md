# Para quien tenga acceso a GitHub — cómo subir esto

**Fecha: 2026-09-03.** Escrito para alguien que llega en frío.

---

## Lo primero, en una línea

**Producción ya corre este código. GitHub no lo tiene.** Siete commits viven
sólo en el disco de esta máquina. Falta un `git push` que la cuenta de acá no
tiene permiso para hacer.

```
remote: Permission to ITCRC1/FinPlan_Oxygen.git denied to Bismark1973.
```

⚠️ **No borrar `C:\dev\FinPlan_Oxygen`.** Es la única copia de esos commits.

---

## Cómo se destraba

En GitHub → `ITCRC1/FinPlan_Oxygen` → **Settings** → **Collaborators** →
**Add people** → `Bismark1973` → permiso **Write**.

O lo empuja directo quien ya tenga acceso, con el repositorio de esta máquina.

---

## El comando

`main` ya está adelantado y **listo para empujar**. Es un avance lineal sobre
`origin/main`, sin commit de fusión ni conflictos que resolver:

```bash
cd C:\dev\FinPlan_Oxygen && git push origin main
```

Si prefieren revisarlo antes por Pull Request, la misma historia está en una
rama aparte:

```bash
cd C:\dev\FinPlan_Oxygen && git push origin port/cierre-amarena
```

**Nada más hay que hacer.** No hay que compilar, ni migrar, ni redesplegar: eso
ya está en producción.

---

## Qué se está subiendo

Siete commits sobre `21dda29`, **104 archivos, +15.737 líneas**.

| Commit | Qué trae |
|---|---|
| `7ed163b` | El cierre mensual construido en Amarena, traído entero |
| `e3b9c2f` | El encabezado de la migración 138, que decía otros números |
| `7f66bcf` | Auditar un presupuesto, no sólo los actuales |
| `9bfeec9` | Avisar cuando la plata llega a un renglón por descarte; identidad `OXI` |
| `945c05b` | Documentación del despliegue y las decisiones del owner |
| `4e9c0c6` | El aviso cuenta también los `DROP` |
| `deadef9` | Los pendientes de configuración salen en el Chequeo |

Cada commit explica **por qué**, no sólo qué. Los que tocan plata dicen qué
número se movió y contra qué se verificó.

---

## Cómo comprobar que está sano antes de empujar

```bash
cd C:\dev\FinPlan_Oxygen\backend && .venv\Scripts\python.exe -m pytest -q
```

Al 2026-09-03: **4230 pasan, 36 saltadas, 0 fallan.**

```bash
cd C:\dev\FinPlan_Oxygen\frontend && npm run build
```

Y los servicios en vivo:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://finplanoxygen-backend.up.railway.app/health
```

---

## ⚠️ Si el push falla por conflicto

Significa que alguien más subió algo a `main` desde el 2026-09-03. **No forzar.**
Se rebasa y se vuelve a probar:

```bash
cd C:\dev\FinPlan_Oxygen && git pull --rebase origin main
```

Después correr las pruebas otra vez **antes** de empujar. Un `--force` acá
borraría trabajo ajeno y dejaría producción corriendo algo que el repo no
describe — que es justamente el problema que este archivo existe para cerrar.

---

## Contexto que conviene tener

La migración `138` **ya está aplicada** en la base de producción. El arranque
del servicio es `alembic upgrade head && python -m app.seed && uvicorn`, así que
cuando el push dispare un despliegue, la migración se encuentra ya corrida y no
hace nada. No hay riesgo de doble aplicación.

El resto del detalle —cómo se despliega, qué mirar antes, y el estado de los
datos— está en [`docs/DESPLIEGUE_OXYGEN.md`](docs/DESPLIEGUE_OXYGEN.md).
