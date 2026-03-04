# AGENTS.md — LASFOR (planificación y ruteo)

Este repositorio contiene la app **LASFOR**. Si sos un agente (Codex) trabajando acá, seguí estas reglas.

## Objetivo del producto
Construir una app web que reemplace un Excel complejo de ruteo, pero manteniendo el flujo operativo:
- El usuario carga datos en Excel (plantilla `IMPORT.xlsm`)
- La app importa, valida, planifica 6 días hábiles (lunes a viernes) y genera las rutas
- Deploy “para siempre” (estable) usando **Dockerfile** en Railway y persistencia con **SQLite en `/data`**

## Flujo de usuario (lo que el usuario hace)
El usuario SOLO completa manualmente en Excel:
- `TX_LINEAS_PEDIDOS`
- `TX_TURNOS`
- `TX_STOCK_DIA`
- `TX_PLAN_PROD_DIA`
- `PARAMETROS!Fecha_Entrega`
- `PARAMETROS!Dias_Habiles_Adicionales` (normalmente 5)

Maestros se actualizan ocasionalmente:
- `MA_CLIENTES`
- `MA_ARTICULOS`

## Reglas de negocio (hard requirements)
### Horizonte de planificación
- Planificar desde `Fecha_Entrega` (día 1) hasta `Dias_Habiles_Adicionales` días hábiles adicionales.
- Considerar **solo lunes a viernes**. Si Fecha_Entrega cae fin de semana, comenzar el próximo hábil.

### Disponibilidad / stock (corte duro)
- Calcular demanda total en EP por SKU del horizonte.
- Calcular disponibilidad total en EP por SKU = `Stock día 1 + suma(Producción día i)` para i en horizonte.
- Si algún SKU tiene saldo < 0 → **BLOQUEAR**: no generar rutas y mostrar reporte de faltantes.

### Turnos
- Turnos confirmados por cliente con fecha/hora (en `TX_TURNOS`).
- Soportar un campo `Pallets_Turnados`:
  - Si existe y es menor al EP total del cliente: entregar solo esa parte ese día (split parcial).
  - El resto queda backlog (sin turno) para días siguientes.
- Si un cliente con turno queda **sin asignar** ese día → la planificación falla con mensaje claro (turno incumplible).

### Capacidad / rutas
- Rutas configurables con vehículo y capacidad (EP/pallets), max clientes, max turnos por ruta.
- Asignación de un día respeta:
  - capacidad por ruta
  - max clientes por ruta
  - max turnos por ruta (solo cuenta clientes con turno)

### Secuencia
- Si `MA_CLIENTES` trae `Ruta_Default` y `Secuencia_Default`, usar como preferencia cuando sea posible.
- Si no, secuencia incremental de inserción.

## Importación desde Excel (modo seguro)
Debe existir `/importar` con:
- Upload de `IMPORT.xlsm` (o `.xlsx`)
- Checkboxes:
  - Importar operativo (diario)
  - Reemplazar operativo del escenario/semana (idempotente)
  - Importar maestros (ocasional)
  - Modo estricto (default ON): si hay cualquier error → **rollback**, no aplicar cambios
- Guardar logs de importación:
  - timestamp, semana_id, filename, status, summary JSON, `errores.csv`
- Descargar errores:
  - `/importar/<run_id>/errores.csv`

**IMPORTANTE:** antes de implementar el parser, abrir el Excel real (`IMPORT.xlsm`) con `openpyxl` y confirmar:
- nombres de hojas exactos
- layout de matrices y bloques “DÍA 1..6”
- columnas exactas

No asumir.

## Stack técnico (decisión: robustez “para siempre”)
- Backend: Python + Flask
- DB: SQLite (persistente con Railway Volume)
- Deploy: **Dockerfile** (NO Railpack/mise)
- Gunicorn como servidor WSGI.

### Persistencia en Railway
- Montar Volume en `/data`
- Variable: `DB_PATH=/data/lasfor.db`

## Rutas web mínimas
- `/` dashboard (semana activa + KPIs)
- `/health` (ok + db_path + commit sha si existe)
- `/semanas` (crear/activar semana)
- `/importar` (import seguro)
- `/clientes`, `/articulos`
- `/maestros/vehiculos`, `/maestros/rutas`
- `/autoruteo` (ejecutar)
- `/resultado` (rutas por día)

## Modelo de datos (mínimo)
Tablas:
- `config` (semana_activa)
- `semanas`
- `clientes` (con `cliente_ext_id` UNIQUE)
- `articulos` (descripcion UNIQUE)
- `pedidos` (semana_id, cliente_id, articulo_id)
- `turnos`
- `stock_dia` (importar solo día=1)
- `prod_dia`
- `vehiculos`, `rutas`
- `asignaciones`
- `import_runs`

## Entregables obligatorios
- Repo con estructura estándar:
  - `app.py`, `requirements.txt`, `Dockerfile`, `.dockerignore`, `templates/`, `static/`
- Importador adaptado al `IMPORT.xlsm` real
- Planificador multi-día con corte duro por stock + split por turnos
- README con pasos de deploy en Railway + uso

## Criterios de aceptación (tests manuales mínimos)
1) `/importar` existe (no 404).
2) Modo estricto: si falta cliente/artículo, status = STRICT_ABORT y DB no cambia.
3) Si hay faltantes de stock, `/autoruteo` no genera asignaciones y muestra faltantes por SKU.
4) Si un cliente con turno queda sin asignar, `/autoruteo` falla con mensaje claro.
5) Deploy Docker funciona (sin mise). 
6) Con Volume + DB_PATH, los datos persisten tras redeploy.

## Proceso recomendado de implementación
1) Inspeccionar `IMPORT.xlsm` y documentar mapeo real.
2) Implementar DB + UI mínima + /health.
3) Implementar importador seguro con logs y errores.csv.
4) Implementar autoruteo multi-día + bloqueo stock + split turnos.
5) Checklist de deploy (Docker + Volume).
