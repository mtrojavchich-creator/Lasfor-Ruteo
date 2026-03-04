# LASFOR — Paso 4: autoruteo multi-día

Implementación actual en Flask + SQLite con deploy Docker.

## Rutas
- `/`, `/health`, `/semanas`
- `/importar` y `/importar/<run_id>/errores.csv`
- `/clientes`, `/articulos`
- `/maestros/vehiculos`, `/maestros/rutas`
- `/autoruteo`, `/resultado`

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
