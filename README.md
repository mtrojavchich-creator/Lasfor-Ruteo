# LASFOR — Paso 3: `/importar` en modo seguro

Este estado incluye el scaffold Flask + SQLite y la implementación inicial de importación segura de Excel.

## Rutas disponibles

- `/` dashboard mínimo.
- `/health` (ok + `db_path`).
- `/semanas` (crear/listar semanas y activar semana).
- `/importar` (upload `.xlsm/.xlsx` con modo seguro).
- `/importar/<run_id>/errores.csv` (descarga errores por corrida).

## `/importar` (modo seguro)

El formulario incluye:

- Upload de `IMPORT.xlsm` o `.xlsx`.
- Checkbox `Importar operativo`.
- Checkbox `Reemplazar operativo del escenario/semana`.
- Checkbox `Importar maestros`.
- Checkbox `Modo estricto` (ON por default).

Comportamiento:

- Registra cada corrida en `import_runs` con timestamp, semana activa, nombre de archivo, status, summary JSON y `errores.csv` serializado.
- Si `modo estricto` está activo y hay errores de validación, se hace rollback completo de la carga operativa/maestros (`STRICT_ABORT`), pero la corrida y su log sí quedan registrados.
- Si no está en modo estricto, inserta lo válido y deja estado `OK_WITH_ERRORS` cuando corresponda.

## Notas de parser implementado

Se parsea el archivo Excel vía XML interno (`.xlsx/.xlsm`), sin dependencias externas, cubriendo hojas:

- `MA_CLIENTES`
- `MA_ARTICULOS`
- `TX_LINEAS_PEDIDOS` (matriz cliente × artículo)
- `TX_TURNOS`
- `TX_STOCK_DIA` (bloques DÍA 1..6 por marcador en columna A)
- `TX_PLAN_PROD_DIA` (bloques DÍA 1..6 por marcador en columna A)

## Ejecutar

```bash
python app.py
```

Variables:

- `PORT` (default `8000`)
- `DB_PATH` (default `/data/lasfor.db`)
