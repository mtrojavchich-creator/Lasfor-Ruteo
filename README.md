# LASFOR — Paso 4: autoruteo multi-día

Implementación actual en Flask + SQLite con deploy Docker.

## Rutas
- `/`, `/health`, `/semanas`
- `/importar` y `/importar/<run_id>/errores.csv`
- `/clientes`, `/articulos`
- `/maestros/vehiculos`, `/maestros/rutas`
- `/autoruteo`, `/resultado`

## Importador (nota de conversión y locale)
- `MA_ARTICULOS` parsea `cajas_por_pallet` y `ep_por_caja` con parser numérico robusto para formatos `0.027777`, `0,027777`, `1.234,56` y `1,234.56`.
- Si `ep_por_caja` es inválido/vacío, usa fallback `1 / cajas_por_pallet` cuando ese dato es válido.
- En `TX_LINEAS_PEDIDOS`, la matriz se interpreta como **cajas** y se convierte a EP con `ep = cajas * ep_por_caja` del artículo antes de guardar en `pedidos.ep_cantidad`.

## Autoruteo implementado
- Horizonte hábil: desde `Fecha_Entrega` de semana activa + 5 días hábiles adicionales (L–V).
- Corte duro de stock: si para algún SKU `stock día 1 + producción horizonte < demanda total`, bloquea sin generar rutas.
- Turnos obligatorios por fecha/hora (`TX_TURNOS`).
- Split por `Pallets_Turnados`: si es menor al pendiente del cliente, entrega parcial y deja backlog.
- Si un turno no puede asignarse en su día por capacidad/restricciones, falla con mensaje claro.
- Asignación respeta capacidad EP por ruta, máximo de clientes y máximo de turnos por ruta.

## Deploy
- `Dockerfile` con Gunicorn en `${PORT:-8000}`.
- Persistencia con `DB_PATH=/data/lasfor.db`.

## Ejecutar local
```bash
python app.py
```
