# Planilla: Categoria, filtros, pestaña Resumen y deptos apagados

**Origen:** FinPlan CWL, 2026-11-22 (todo en producción y verificado).
**Destino:** FinPlan Amarena (AMA), FinPlan Oxygen (OXY) y FinPlan Gardens / Ojochal.
**Qué se porta:** el código, nada de datos. Lo que en CWL fue de datos no se repite:
el roster de Isaac, el borrado de las posiciones del Club y del Área Recreativa y las
excepciones de Categoria de RRHH.

---

## 1. Los commits, en orden

Se cherry-pickean del repo de CWL (`git fetch cwl main`, con el remote apuntando a
`C:\Users\User\Documents\FinPlan_CWL`) **en este orden**:

| # | Commit | Qué hace |
|---|---|---|
| 1 | `efcbc02` | En la plantilla de planilla, el **nombre del colaborador** (col E) se puede editar y el import lo lee |
| 2 | `d0f8a87` | **Categoria** (Operaciones / Administrativo / Gerencial) y **SubCategoria** (On Property / Outside) en cada posición. Migración nueva, columnas V y W del Excel con lista y autofiltro |
| 3 | `ab97a37` | Bajar el Excel **filtrado por Categoria**. Al subirlo se reemplazan **solo** las posiciones de ese filtro |
| 4 | `1c1722a` | Los deptos **apagados** en el provisionamiento (dimensión PAYROLL) no salen en el Excel, y si se sube un Excel viejo sus filas se ignoran (`ignored_depts`) |
| 5 | `52f3deb` | El botón **Recalcular** de la planilla vuelve a leer el depto al terminar. Antes, después de subir, «Totales dept» quedaba en blanco |
| 6 | `d5b2f06` | Pestaña **Resumen** en el Excel |
| 7 | `980c9a0` | Opción «Operaciones + Gerencial». El #8 la quita, pero se aplica igual para que el #8 entre limpio |
| 8 | `6c12009` | Filtro por **SubCategoria**: On Property / Outside |

## 2. Lo que hay que adaptar en cada hotel

1. **Migración `165_categoria_de_la_posicion.py`.** En CWL es la revisión `165` con
   `down_revision = "164"`. En cada hotel hay que renombrarla al número siguiente de
   **su** cabeza:

   | Hotel | Cabeza al 22-nov | Nueva revisión |
   |---|---|---|
   | AMA | 155 | 156 |
   | OXY | 152 | 153 |
   | Gardens | 154 | 155 |

   Antes de renombrar, confirmar la cabeza con `ls backend/alembic/versions`: puede
   haber cambiado desde el 22-nov. La migración solo agrega `categoria` y
   `subcategoria` (`String(20)`, nullable) a `payroll_positions`.
2. **`DEFECTO_POR_DEPTO`** (`backend/app/models/payroll_position.py`). Sale del archivo de
   RRHH de CWL y se deja igual en los tres hoteles, porque el catálogo de
   departamentos es el mismo en todo el grupo:

   | Depto | Categoria / SubCategoria |
   |---|---|
   | 0181 | Gerencial / Outside |
   | 0112, 0182, 0183, 0184, 0190, 0191, 0230 | Administrativo / Outside |
   | Todo lo demás | Operaciones / On Property |

   Es solo el valor por defecto. Cada posición se corrige en las columnas V y W del Excel.
3. **Conflictos esperables.**
   - `payroll_api.py` y `frontend/lib/api.ts` difieren bastante entre hoteles.
     Resolver a mano conservando lo del hotel y agregando lo nuevo.
   - `textos.py` y `messages/*.json`: claves nuevas, sin pisar las del hotel.
   - `payroll_excel.py` es casi idéntico al de CWL (2 líneas de diferencia).
4. **Tests.** `backend/tests/test_planilla_categoria.py` tiene que quedar en verde. Es
   independiente del hotel; si falla algo, es una adaptación pendiente, no la prueba.
   Correr también `pytest -k "payroll or planilla or excel"` y comparar contra `main`
   **antes** del port: una falla que ya estaba antes no es de este cambio.
5. **Frontend.** Correr `npx tsc --noEmit -p .` en `frontend/`.

## 3. Cómo queda para el usuario

**La lista al lado de «⬇ Excel»** (pantalla Planilla → Checkbook):
- Todas las categorías
- **On Property**: operativos y gerenciales en sitio
- **Outside**: administrativos y gerenciales fuera
- Solo Operaciones · Solo Administrativo · Solo Gerencial

**El Excel:**
- **Pestaña Planilla:** columnas A..U como antes. Agrega **V = Categoria** y
  **W = SubCategoria**, editables con lista, y autofiltro en el encabezado (funciona con
  la hoja protegida). Si se bajó con filtro, la **fila 2** lo dice («Solo Categoria: …»
  o «Solo SubCategoria: …») y el import lo lee de ahí.
- **Pestaña Resumen:** un renglón por depto con Headcount, Salario mensual ₡,
  Salario mensual US$, SW anual US$ y HC por mes (la suma de FTE, con el cero en
  blanco). Al final va el **TOTAL**. Son **fórmulas** sobre la pestaña Planilla: si se
  edita un FTE, el Resumen se mueve solo. Headcount y salario cuentan solo las
  posiciones con FTE en al menos un mes.
- **El import lee solo la primera pestaña.** Un Excel viejo, sin V/W, sigue subiendo.

**Subir un Excel filtrado reemplaza solo lo que trae el filtro.** Ejemplo: Recepción baja
«Solo Operaciones» y lo sube, y los Gerencial de Recepción no se tocan. Cuidados:
- Si se copian las filas a otro Excel donde la fila 2 dice otra cosa, el import lo toma
  como completo y reemplaza el depto entero.
- Toda subida recrea las posiciones y se lleva sus conceptos manuales (horas extra,
  cafetería, vivienda). Esto ya pasaba antes.
- Después de subir hay que **recalcular**.

## 4. Verificación del deploy

- **Backend:** `/health` del hotel → `git_sha` igual al commit y `migraciones_al_dia: true`.
- **Frontend:** bajar los chunks de `/payroll/checkbook` y buscar el literal
  `sub:On Property`. El nombre o hash del chunk no sirve para comprobarlo.
- **Prueba real:** bajar el Excel del Working del hotel y abrir la pestaña Resumen. El
  TOTAL de headcount tiene que coincidir con el número de posiciones con FTE > 0.

---

## 5. Segunda tanda (mismo día): Contract Labour y editar posiciones

Van **después** de los 8 de arriba, en este orden:

| # | Commit | Qué hace |
|---|---|---|
| 9 | `2003d7c` | **Cuenta 6031 Contract Labour.** Se marca por posición con un check (`payroll_positions.contract_labour`): al crear la posición, como «CL» en la vista por posición y en la columna **X** del Excel. La posición marcada manda salario × FTE (÷ TC) a 6031 y queda **fuera de todo**: ni BASE, ni CCSS, ni aguinaldo, ni vacaciones, ni INS, ni beneficios. En el P&L va con los salarios (6000) del mismo depto. Migración **166** |
| 10 | `58189f2` | **Editar una posición ya creada**: botón ✎ con depto (se muda con sus conceptos), código (sin repetir), puesto, colaborador, tipo, salario, moneda, Categoria/SubCategoria, Contract Labour y los 12 FTE. El salario también se edita directo en la fila, y la **moneda (col H)** queda editable en el Excel |

**Lo que hay que adaptar:**

1. **Migración `166_contract_labour.py`.** Renumerarla al número que siga a la migración del port anterior en cada hotel:

   | Hotel | Revisión | Revises |
   |---|---|---|
   | AMA | 157 | 156 |
   | OXY | 154 | 153 |
   | Gardens | 156 | 155 |

   Antes de renombrar, confirmar con la cabeza real del repo. Agrega dos columnas: `payroll_positions.contract_labour` y `payroll_concept_entries.c6031_contract_labour`.
2. **`backend/app/seed_data/mapping_pl.json` es de cada hotel.** No se copia el de CWL. Al commit #9 le va a dar conflicto en ese archivo, o lo trae con las reglas de CWL. Hay que quedarse con el JSON **del hotel** y aplicarle la misma transformación: por cada fila con `account_code == "6000"` agregar justo debajo una copia con `account_code: "6031"`, `account_name_example: "Contract Labour"` y la nota. Se saltea donde ya exista una 6031 para el mismo `report_id + dept_code + source_origin`. Cada hotel ya trae una 6031 (Tours). Se escribe con `json.dumps(indent=2, ensure_ascii=False)` y el salto de línea final, para que el diff sean solo las filas nuevas. Es la regla del seed: el JSON manda sobre `account_mapping`.
3. **`CUENTA_ALIAS = {"6031": "6000"}`** en `pl_engine.construir_resolvedor`. Es la red de seguridad: sin ella, toda la 6031 de todos los deptos cae por FALLBACK en Tours.
4. **Pruebas que contaban 17 cuentas de planilla.** Ahora son 18 (17 + 6031). El commit #9 las ajusta en CWL, y en cada hotel puede haber alguna propia que también cuente 17. `test_budget_traceability` lee el **Excel histórico** de mapeo, que no tiene la 6031: el commit le agrega la excepción por alias.
5. **Las ~12 listas de conceptos** donde vive la 6031:
   - `PAYROLL_ALL_COLS` (recalculate, allocation_api, rooms_sets_api)
   - `consulta_api.CONCEPTOS`
   - `payroll_position_report_api`
   - `conceptos_por_depto_excel.FILAS`
   - `informes/extraccion`
   - `scenarios_api._PAYROLL_NAMES`
   - `payroll_calculator`
   - el salario del club en `pl_detail_api`
   - `gl_detail_importer` (la 6031 va a `c6031_contract_labour`)
   - `CONCEPTS` del front

   Si el hotel tiene alguna lista propia que CWL no tiene, agregarle la 6031 al lado de la 6000.
6. **Integrity:** cada hotel tiene que crear la cuenta 6031 Contract Labour para que los reales caigan ahí.

**Verificación:**
- `/health` con `alembic` en la revisión nueva.
- Contar las reglas 6031 en `account_mapping` de producción: tiene que dar una por cada 6000 (~25).
- Buscar en el bundle de `/payroll/checkbook` el literal `editPositionHelp`.
