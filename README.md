# Paso 1 — Mapeo real de `fixtures/IMPORT.xlsm`

Este documento releva la estructura **real** del archivo `fixtures/IMPORT.xlsm` (hojas, columnas y bloques), para usarla como base del importador más adelante.

## Archivo inspeccionado
- `fixtures/IMPORT.xlsm`
- Formato: Excel macro-enabled workbook (`.xlsm`)

## Hojas detectadas (en orden)
1. `MA_CLIENTES`
2. `MA_ARTICULOS`
3. `TX_LINEAS_PEDIDOS`
4. `TX_TURNOS`
5. `TX_STOCK_DIA`
6. `TX_PLAN_PROD_DIA`

> Nota: en este archivo no aparece una hoja `PARAMETROS`.

---

## 1) `MA_CLIENTES`
- Rango usado: `A1:K448`
- Encabezados (fila 1):
  - `A` Cliente_ID
  - `B` Razon_Social
  - `C` Direccion
  - `D` Provincia
  - `E` Localidad
  - `F` CP
  - `G` Compañía de Carga
  - `H` Requiere_Turno
  - `I` Ruta_Default
  - `J` Secuencia_Default
  - `K` Activo

## 2) `MA_ARTICULOS`
- Rango usado: `A1:E123`
- Encabezados (fila 1):
  - `A` SKU
  - `B` DESCRIPCION
  - `C` UoM_Venta
  - `D` Cajas_por_pallet
  - `E` EP_por_Caja

## 3) `TX_LINEAS_PEDIDOS`
- Rango usado: `A1:AV93`
- Estructura observada:
  - Fila 1: matriz por cliente.
    - `A1` = `DESCRIPCION`
    - `B1..AV1` = nombres de clientes (cada columna representa un cliente)
  - Filas 2..93: productos/artículos en columna `A` (descripción) y cantidades por cliente en columnas `B..AV`.
- Encabezado base:
  - `A` DESCRIPCION
  - `B..AV` Clientes (nombres variables según maestro)

## 4) `TX_TURNOS`
- Rango usado: `A1:M7`
- Encabezados (fila 1):
  - `A` Fecha_Entrega
  - `B` Cliente_ID
  - `C` Turno_Confirmado
  - `D` Turno_Fecha
  - `E` Turno_Hora
  - `F` Turno_ID
  - `G` Assign_Status
  - `H` Notas
  - `I` Key_FechaCliente
  - `J` UNASSIGNED
  - `K` OK
  - `L` Pallets_Turnados
- Columna adicional observada en datos:
  - `M` aparece en filas de datos (sin encabezado en fila 1).

## 5) `TX_STOCK_DIA`
- Rango usado: `A1:F739`
- Celda combinada: `A1:F1` (texto de instrucción)
- Encabezados de bloque (fila 2):
  - `A` FECHA
  - `B` SKU
  - `C` DESCRIPCION
  - `D` CANTIDAD
  - `E` UoM
  - `F` EP_Stock

### Bloques DÍA 1..6 (verticales)
- **DÍA 1**: filas `2..124` (encabezado en fila 2, datos desde fila 3)
- **DÍA 2**: rótulo en fila `125` (`DÍA 2 - Stock automático...`), encabezado en fila `126`, datos desde `127`
- **DÍA 3**: rótulo en fila `248`, encabezado en fila `249`, datos desde `250`
- **DÍA 4**: rótulo en fila `371`, encabezado en fila `372`, datos desde `373`
- **DÍA 5**: rótulo en fila `494`, encabezado en fila `495`, datos desde `496`
- **DÍA 6**: rótulo en fila `617`, encabezado en fila `618`, datos desde `619`

## 6) `TX_PLAN_PROD_DIA`
- Rango usado: `A1:F739`
- Celda combinada: `A1:F1` (texto de instrucción)
- Encabezados de bloque (fila 2):
  - `A` FECHA
  - `B` SKU
  - `C` DESCRIPCION
  - `D` CANTIDAD
  - `E` UOM
  - `F` EP_PRODUCCION

### Bloques DÍA 1..6 (verticales)
- **DÍA 1**: filas `2..124` (encabezado en fila 2, datos desde fila 3)
- **DÍA 2**: rótulo en fila `125` (`DÍA 2 - Ingresá CANTIDAD...`), encabezado en fila `126`, datos desde `127`
- **DÍA 3**: rótulo en fila `248`, encabezado en fila `249`, datos desde `250`
- **DÍA 4**: rótulo en fila `371`, encabezado en fila `372`, datos desde `373`
- **DÍA 5**: rótulo en fila `494`, encabezado en fila `495`, datos desde `496`
- **DÍA 6**: rótulo en fila `617`, encabezado en fila `618`, datos desde `619`

---

## Observaciones para implementar el importador (próximo paso)
- `TX_LINEAS_PEDIDOS` está en formato matriz (productos x clientes), no en formato tabular por fila de pedido.
- `TX_STOCK_DIA` y `TX_PLAN_PROD_DIA` usan bloques repetidos por día en filas (no una sola tabla continua limpia).
- `TX_TURNOS` incluye `Pallets_Turnados` y una columna `M` sin encabezado visible.
- En este archivo hay celdas con `#REF!` en campos de fecha, por lo que el importador deberá validar/parsing defensivo.
