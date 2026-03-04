# Resumen layout de `fixtures/IMPORT.xlsm`

Este README resume el layout del fixture `fixtures/IMPORT.xlsm` para el parser de importación.

## Hojas (orden real)
1. `MA_CLIENTES`
2. `MA_ARTICULOS`
3. `TX_LINEAS_PEDIDOS`
4. `TX_TURNOS`
5. `TX_STOCK_DIA`
6. `TX_PLAN_PROD_DIA`

> No aparece hoja `PARAMETROS` en este fixture.

## Bloques `DÍA 1..6`

### `TX_STOCK_DIA`
- Hoja en bloques verticales repetidos por día.
- Estructura por bloque: fila de rótulo (`DÍA n`, excepto día 1), fila de encabezados, filas de datos.
- Encabezados del bloque: `FECHA`, `SKU`, `DESCRIPCION`, `CANTIDAD`, `UoM`, `EP_Stock`.
- Ubicación de bloques:
  - `DÍA 1`: encabezado fila 2, datos desde fila 3.
  - `DÍA 2`: rótulo fila 125, encabezado fila 126, datos desde 127.
  - `DÍA 3`: rótulo fila 248, encabezado fila 249, datos desde 250.
  - `DÍA 4`: rótulo fila 371, encabezado fila 372, datos desde 373.
  - `DÍA 5`: rótulo fila 494, encabezado fila 495, datos desde 496.
  - `DÍA 6`: rótulo fila 617, encabezado fila 618, datos desde 619.

### `TX_PLAN_PROD_DIA`
- Misma lógica de bloques verticales que `TX_STOCK_DIA`.
- Encabezados del bloque: `FECHA`, `SKU`, `DESCRIPCION`, `CANTIDAD`, `UOM`, `EP_PRODUCCION`.
- Ubicación de bloques:
  - `DÍA 1`: encabezado fila 2, datos desde fila 3.
  - `DÍA 2`: rótulo fila 125, encabezado fila 126, datos desde 127.
  - `DÍA 3`: rótulo fila 248, encabezado fila 249, datos desde 250.
  - `DÍA 4`: rótulo fila 371, encabezado fila 372, datos desde 373.
  - `DÍA 5`: rótulo fila 494, encabezado fila 495, datos desde 496.
  - `DÍA 6`: rótulo fila 617, encabezado fila 618, datos desde 619.

## Nota rápida de las otras hojas
- `MA_CLIENTES`: tabla de clientes (campos maestros, ruta y secuencia por defecto).
- `MA_ARTICULOS`: tabla de artículos (SKU, descripción y factores de conversión).
- `TX_LINEAS_PEDIDOS`: matriz (`DESCRIPCION` en columna A; clientes en columnas B..).
- `TX_TURNOS`: tabla de turnos confirmados (incluye `Pallets_Turnados`).
