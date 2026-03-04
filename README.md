# LASFOR — Scaffold mínimo deployable (Paso 2)

Este estado del proyecto incluye una base en Flask + SQLite lista para deploy con Docker.

## Incluye

- `app.py` con inicialización de Flask.
- Migración automática al iniciar (creación de tablas base `schema_migrations`, `config`, `semanas`).
- Rutas:
  - `/` dashboard mínimo
  - `/health` (devuelve `ok` y `db_path`)
  - `/semanas` (crear y listar semanas, con opción de activar)
- Estructura de UI mínima:
  - `templates/base.html`
  - `templates/index.html`
  - `templates/semanas.html`
  - `static/styles.css`
- Deploy con Docker:
  - `Dockerfile`
  - `.dockerignore`
  - `requirements.txt`

> Aún no se implementan `/importar`, `/autoruteo` ni la lógica de planificación.

## Ejecutar en local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Variables opcionales:

- `PORT` (default `8000`)
- `DB_PATH` (default `/data/lasfor.db`)

## Ejecutar con Docker

```bash
docker build -t lasfor .
docker run --rm -p 8000:8000 -e DB_PATH=/data/lasfor.db -v $(pwd)/data:/data lasfor
```
