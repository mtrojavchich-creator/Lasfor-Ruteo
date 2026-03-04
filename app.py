import os
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, g, redirect, render_template, request, url_for


DEFAULT_DB_PATH = "/data/lasfor.db"

app = Flask(__name__)
app.config["DB_PATH"] = os.environ.get("DB_PATH", DEFAULT_DB_PATH)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db_path = Path(app.config["DB_PATH"])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_exc: BaseException | None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS semanas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            fecha_inicio TEXT,
            fecha_entrega TEXT,
            activa INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        """
    )
    db.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (id, name, applied_at)
        VALUES (1, '0001_initial', ?)
        """,
        (datetime.utcnow().isoformat(timespec="seconds"),),
    )
    db.commit()


@app.before_request
def ensure_schema() -> None:
    init_db()


@app.route("/")
def dashboard():
    db = get_db()
    semana_activa = db.execute(
        "SELECT id, nombre, fecha_inicio, fecha_entrega FROM semanas WHERE activa = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return render_template("index.html", semana_activa=semana_activa)


@app.route("/health")
def health():
    db = get_db()
    db.execute("SELECT 1").fetchone()
    return {
        "ok": True,
        "db_path": app.config["DB_PATH"],
    }


@app.route("/semanas", methods=["GET", "POST"])
def semanas():
    db = get_db()
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        fecha_inicio = request.form.get("fecha_inicio") or None
        fecha_entrega = request.form.get("fecha_entrega") or None
        activar = request.form.get("activar") == "on"

        if nombre:
            if activar:
                db.execute("UPDATE semanas SET activa = 0")
            cursor = db.execute(
                """
                INSERT INTO semanas (nombre, fecha_inicio, fecha_entrega, activa, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    nombre,
                    fecha_inicio,
                    fecha_entrega,
                    1 if activar else 0,
                    datetime.utcnow().isoformat(timespec="seconds"),
                ),
            )
            if activar:
                db.execute(
                    "INSERT INTO config(key, value) VALUES('semana_activa', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(cursor.lastrowid),),
                )
            db.commit()

        return redirect(url_for("semanas"))

    rows = db.execute(
        "SELECT id, nombre, fecha_inicio, fecha_entrega, activa, created_at FROM semanas ORDER BY id DESC"
    ).fetchall()
    return render_template("semanas.html", semanas=rows)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
