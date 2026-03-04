import csv
import io
import json
import os
import re
import sqlite3
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from flask import Flask, Response, g, redirect, render_template, request, url_for


DEFAULT_DB_PATH = "/data/lasfor.db"

app = Flask(__name__)
app.config["DB_PATH"] = os.environ.get("DB_PATH", DEFAULT_DB_PATH)

NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "p": "http://schemas.openxmlformats.org/package/2006/relationships",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


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

        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_ext_id TEXT NOT NULL UNIQUE,
            razon_social TEXT NOT NULL,
            ruta_default TEXT,
            secuencia_default INTEGER,
            activo INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS articulos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT,
            descripcion TEXT NOT NULL UNIQUE,
            ep_por_caja REAL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            semana_id INTEGER NOT NULL,
            cliente_id INTEGER NOT NULL,
            articulo_id INTEGER NOT NULL,
            ep_cantidad REAL NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS turnos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            semana_id INTEGER NOT NULL,
            cliente_id INTEGER NOT NULL,
            fecha TEXT,
            hora TEXT,
            pallets_turnados REAL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stock_dia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            semana_id INTEGER NOT NULL,
            dia INTEGER NOT NULL,
            articulo_id INTEGER NOT NULL,
            ep_cantidad REAL NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS prod_dia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            semana_id INTEGER NOT NULL,
            dia INTEGER NOT NULL,
            articulo_id INTEGER NOT NULL,
            ep_cantidad REAL NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS import_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            semana_id INTEGER,
            filename TEXT NOT NULL,
            status TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            errores_csv TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vehiculos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            capacidad_ep REAL NOT NULL,
            max_clientes INTEGER NOT NULL,
            max_turnos INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rutas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            vehiculo_id INTEGER NOT NULL,
            activa INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS asignaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            semana_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            ruta_id INTEGER NOT NULL,
            cliente_id INTEGER NOT NULL,
            ep_asignado REAL NOT NULL,
            con_turno INTEGER NOT NULL DEFAULT 0,
            turno_id INTEGER,
            secuencia INTEGER,
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


def _first_non_empty_row(rows: list[list[str]]) -> int | None:
    for idx, row in enumerate(rows):
        if any(cell.strip() for cell in row):
            return idx
    return None


def _normalize_header(header: str) -> str:
    return re.sub(r"\s+", "", header.strip().lower())


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() == "#REF!":
        return None

    text = text.replace(" ", "")
    if "," in text and "." in text:
        last_comma = text.rfind(",")
        last_dot = text.rfind(".")
        decimal_sep = "," if last_comma > last_dot else "."
        thousands_sep = "." if decimal_sep == "," else ","
        text = text.replace(thousands_sep, "")
        text = text.replace(decimal_sep, ".")
    elif "," in text:
        text = text.replace(".", "")
        text = text.replace(",", ".")
    elif "." in text:
        if re.fullmatch(r"[1-9]\d{0,2}(?:\.\d{3})+", text):
            text = text.replace(".", "")

    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _is_valid_ep_por_caja(value: float | None) -> bool:
    return value is not None and 0 < value <= 1


def _self_check_as_float() -> None:
    assert abs((_as_float("0.027777") or 0.0) - 0.027777) < 1e-9
    assert abs((_as_float("0,027777") or 0.0) - 0.027777) < 1e-9
    assert abs((_as_float("1.234,56") or 0.0) - 1234.56) < 1e-9
    assert abs((_as_float("1,234.56") or 0.0) - 1234.56) < 1e-9


def _excel_serial_to_iso(value: str) -> str | None:
    number = _as_float(value)
    if number is None:
        if value and value != "#REF!":
            return value
        return None
    origin = datetime(1899, 12, 30)
    return (origin + timedelta(days=int(number))).date().isoformat()


def _col_to_index(cell_ref: str) -> int:
    letters = ""
    for ch in cell_ref:
        if ch.isalpha():
            letters += ch
        else:
            break
    acc = 0
    for letter in letters:
        acc = acc * 26 + (ord(letter.upper()) - 64)
    return acc


def read_xlsx_rows(binary_content: bytes) -> dict[str, list[list[str]]]:
    sheets: dict[str, list[list[str]]] = {}
    with zipfile.ZipFile(io.BytesIO(binary_content)) as zf:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            shared_xml = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in shared_xml.findall("a:si", NS):
                shared_strings.append("".join(t.text or "" for t in si.findall(".//a:t", NS)))

        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        by_rel = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels.findall("p:Relationship", NS)}

        for sheet in workbook.findall("a:sheets/a:sheet", NS):
            name = sheet.attrib["name"]
            rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = "xl/" + by_rel[rel_id]
            ws = ET.fromstring(zf.read(target))

            out_rows: list[list[str]] = []
            for row in ws.findall("a:sheetData/a:row", NS):
                row_cells: dict[int, str] = {}
                for cell in row.findall("a:c", NS):
                    idx = _col_to_index(cell.attrib["r"])
                    cell_type = cell.attrib.get("t")
                    value_node = cell.find("a:v", NS)
                    value = ""
                    if value_node is not None and value_node.text is not None:
                        value = value_node.text
                        if cell_type == "s":
                            s_idx = int(value)
                            value = shared_strings[s_idx] if s_idx < len(shared_strings) else ""
                    row_cells[idx] = value
                if row_cells:
                    width = max(row_cells)
                    out_rows.append([row_cells.get(col, "") for col in range(1, width + 1)])
            sheets[name] = out_rows
    return sheets


def _header_index_map(header_row: list[str]) -> dict[str, int]:
    return {_normalize_header(value): idx for idx, value in enumerate(header_row)}


def _find_articulo_id(db: sqlite3.Connection, sku: str | None, descripcion: str | None) -> int | None:
    row = None
    if sku:
        row = db.execute("SELECT id FROM articulos WHERE sku = ?", (sku,)).fetchone()
    if row is None and descripcion:
        row = db.execute("SELECT id FROM articulos WHERE descripcion = ?", (descripcion,)).fetchone()
    return row["id"] if row else None


def import_data(
    db: sqlite3.Connection,
    sheets: dict[str, list[list[str]]],
    *,
    semana_id: int,
    import_operativo: bool,
    import_maestros: bool,
    replace_operativo: bool,
) -> tuple[dict[str, int], list[dict[str, str]]]:
    now = datetime.utcnow().isoformat(timespec="seconds")
    summary = {
        "clientes": 0,
        "articulos": 0,
        "pedidos": 0,
        "turnos": 0,
        "stock_rows": 0,
        "prod_rows": 0,
    }
    errors: list[dict[str, str]] = []

    if import_maestros:
        cliente_rows = sheets.get("MA_CLIENTES", [])
        if not cliente_rows:
            errors.append({"sheet": "MA_CLIENTES", "error": "Hoja requerida para maestros no encontrada"})
        else:
            header = _header_index_map(cliente_rows[0])
            for idx, row in enumerate(cliente_rows[1:], start=2):
                cliente_ext = row[header.get("cliente_id", -1)].strip() if "cliente_id" in header and len(row) > header["cliente_id"] else ""
                razon = row[header.get("razon_social", -1)].strip() if "razon_social" in header and len(row) > header["razon_social"] else ""
                if not cliente_ext or not razon:
                    continue
                ruta_default = row[header["ruta_default"]].strip() if "ruta_default" in header and len(row) > header["ruta_default"] else None
                secuencia_raw = row[header["secuencia_default"]].strip() if "secuencia_default" in header and len(row) > header["secuencia_default"] else ""
                secuencia = int(_as_float(secuencia_raw)) if _as_float(secuencia_raw) is not None else None
                activo_raw = row[header["activo"]].strip().upper() if "activo" in header and len(row) > header["activo"] else "SI"
                activo = 0 if activo_raw in {"0", "NO", "FALSE"} else 1
                db.execute(
                    """
                    INSERT INTO clientes (cliente_ext_id, razon_social, ruta_default, secuencia_default, activo, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cliente_ext_id) DO UPDATE SET
                        razon_social=excluded.razon_social,
                        ruta_default=excluded.ruta_default,
                        secuencia_default=excluded.secuencia_default,
                        activo=excluded.activo,
                        updated_at=excluded.updated_at
                    """,
                    (cliente_ext, razon, ruta_default, secuencia, activo, now),
                )
                summary["clientes"] += 1

        articulo_rows = sheets.get("MA_ARTICULOS", [])
        if not articulo_rows:
            errors.append({"sheet": "MA_ARTICULOS", "error": "Hoja requerida para maestros no encontrada"})
        else:
            header = _header_index_map(articulo_rows[0])
            for row_n, row in enumerate(articulo_rows[1:], start=2):
                sku = row[header.get("sku", -1)].strip() if "sku" in header and len(row) > header["sku"] else ""
                descripcion = row[header.get("descripcion", -1)].strip() if "descripcion" in header and len(row) > header["descripcion"] else ""
                cajas_raw = (
                    row[header.get("cajas_por_pallet", -1)].strip()
                    if "cajas_por_pallet" in header and len(row) > header["cajas_por_pallet"]
                    else ""
                )
                ep_raw = row[header.get("ep_por_caja", -1)].strip() if "ep_por_caja" in header and len(row) > header["ep_por_caja"] else ""
                cajas_por_pallet = _as_float(cajas_raw)
                ep_por_caja = _as_float(ep_raw)
                if not _is_valid_ep_por_caja(ep_por_caja) and cajas_por_pallet and cajas_por_pallet > 0:
                    ep_por_caja = 1 / cajas_por_pallet
                if not _is_valid_ep_por_caja(ep_por_caja):
                    ep_por_caja = None
                    if descripcion:
                        errors.append(
                            {
                                "sheet": "MA_ARTICULOS",
                                "error": f"EP/caja inválido para artículo {descripcion} (fila {row_n})",
                            }
                        )
                if not descripcion:
                    continue
                db.execute(
                    """
                    INSERT INTO articulos (sku, descripcion, ep_por_caja, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(descripcion) DO UPDATE SET
                        sku=excluded.sku,
                        ep_por_caja=excluded.ep_por_caja,
                        updated_at=excluded.updated_at
                    """,
                    (sku or None, descripcion, ep_por_caja, now),
                )
                summary["articulos"] += 1

    if import_operativo:
        if replace_operativo:
            db.execute("DELETE FROM pedidos WHERE semana_id = ?", (semana_id,))
            db.execute("DELETE FROM turnos WHERE semana_id = ?", (semana_id,))
            db.execute("DELETE FROM stock_dia WHERE semana_id = ?", (semana_id,))
            db.execute("DELETE FROM prod_dia WHERE semana_id = ?", (semana_id,))

        pedidos_rows = sheets.get("TX_LINEAS_PEDIDOS", [])
        if not pedidos_rows:
            errors.append({"sheet": "TX_LINEAS_PEDIDOS", "error": "Hoja no encontrada"})
        else:
            header = pedidos_rows[0]
            for col in range(1, len(header)):
                cliente_nombre = header[col].strip()
                if not cliente_nombre:
                    continue
                cli = db.execute("SELECT id FROM clientes WHERE razon_social = ?", (cliente_nombre,)).fetchone()
                if cli is None:
                    errors.append({"sheet": "TX_LINEAS_PEDIDOS", "error": f"Cliente no existe en maestros: {cliente_nombre}"})
                    continue
                for row_n, row in enumerate(pedidos_rows[1:], start=2):
                    descripcion = row[0].strip() if row else ""
                    if not descripcion:
                        continue
                    cajas_raw = row[col] if len(row) > col else ""
                    cajas = _as_float(cajas_raw)
                    if cajas is None or cajas <= 0:
                        continue
                    art = db.execute(
                        "SELECT id, ep_por_caja FROM articulos WHERE descripcion = ?",
                        (descripcion,),
                    ).fetchone()
                    if art is None:
                        errors.append({"sheet": "TX_LINEAS_PEDIDOS", "error": f"Artículo no existe: {descripcion} (fila {row_n})"})
                        continue
                    ep_por_caja = art["ep_por_caja"]
                    if not _is_valid_ep_por_caja(ep_por_caja):
                        errors.append(
                            {
                                "sheet": "TX_LINEAS_PEDIDOS",
                                "error": f"Artículo sin EP/caja válido: {descripcion} (fila {row_n})",
                            }
                        )
                        continue
                    ep_cantidad = cajas * ep_por_caja
                    db.execute(
                        """
                        INSERT INTO pedidos (semana_id, cliente_id, articulo_id, ep_cantidad, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (semana_id, cli["id"], art["id"], ep_cantidad, now),
                    )
                    summary["pedidos"] += 1

        turnos_rows = sheets.get("TX_TURNOS", [])
        if not turnos_rows:
            errors.append({"sheet": "TX_TURNOS", "error": "Hoja no encontrada"})
        else:
            header = _header_index_map(turnos_rows[0])
            for row in turnos_rows[1:]:
                cliente_ext = row[header.get("cliente_id", -1)].strip() if "cliente_id" in header and len(row) > header["cliente_id"] else ""
                if not cliente_ext:
                    continue
                cliente = db.execute("SELECT id FROM clientes WHERE cliente_ext_id = ?", (cliente_ext,)).fetchone()
                if cliente is None:
                    errors.append({"sheet": "TX_TURNOS", "error": f"Cliente_ID inexistente: {cliente_ext}"})
                    continue
                fecha = _excel_serial_to_iso(row[header.get("turno_fecha", -1)]) if "turno_fecha" in header and len(row) > header["turno_fecha"] else None
                hora = row[header.get("turno_hora", -1)].strip() if "turno_hora" in header and len(row) > header["turno_hora"] else None
                pallets_turnados = _as_float(row[header.get("pallets_turnados", -1)]) if "pallets_turnados" in header and len(row) > header["pallets_turnados"] else None
                db.execute(
                    """
                    INSERT INTO turnos (semana_id, cliente_id, fecha, hora, pallets_turnados, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (semana_id, cliente["id"], fecha, hora or None, pallets_turnados, now),
                )
                summary["turnos"] += 1

        for sheet_name, table_name, key_name in [
            ("TX_STOCK_DIA", "stock_dia", "stock_rows"),
            ("TX_PLAN_PROD_DIA", "prod_dia", "prod_rows"),
        ]:
            rows = sheets.get(sheet_name, [])
            if not rows:
                errors.append({"sheet": sheet_name, "error": "Hoja no encontrada"})
                continue
            current_day = 1
            for row in rows[1:]:
                a_val = row[0].strip() if row else ""
                if "DÍA" in a_val.upper() or "DIA" in a_val.upper():
                    day_match = re.search(r"(\d+)", a_val)
                    if day_match:
                        current_day = int(day_match.group(1))
                    continue
                if a_val.upper() == "FECHA":
                    continue
                sku = row[1].strip() if len(row) > 1 else ""
                descripcion = row[2].strip() if len(row) > 2 else ""
                cantidad = _as_float(row[3]) if len(row) > 3 else None
                ep_val = _as_float(row[5]) if len(row) > 5 else None
                if not sku and not descripcion:
                    continue
                articulo_id = _find_articulo_id(db, sku or None, descripcion or None)
                if articulo_id is None:
                    errors.append({"sheet": sheet_name, "error": f"SKU/Artículo inexistente: {sku or descripcion}"})
                    continue
                if ep_val is None:
                    art = db.execute("SELECT ep_por_caja FROM articulos WHERE id = ?", (articulo_id,)).fetchone()
                    ep_por_caja = art["ep_por_caja"] if art else None
                    if cantidad is not None and _is_valid_ep_por_caja(ep_por_caja):
                        ep_val = cantidad * ep_por_caja
                if ep_val is None:
                    continue
                db.execute(
                    f"INSERT INTO {table_name} (semana_id, dia, articulo_id, ep_cantidad, created_at) VALUES (?, ?, ?, ?, ?)",
                    (semana_id, current_day, articulo_id, ep_val, now),
                )
                summary[key_name] += 1

    return summary, errors


def _errors_to_csv(errors: list[dict[str, str]]) -> str:
    if not errors:
        return "sheet,error\n"
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["sheet", "error"])
    writer.writeheader()
    writer.writerows(errors)
    return output.getvalue()


def _get_semana_activa(db: sqlite3.Connection) -> sqlite3.Row | None:
    return db.execute(
        "SELECT id, nombre, fecha_inicio, fecha_entrega FROM semanas WHERE activa = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()


def _business_horizon(fecha_entrega: str, dias_adicionales: int = 5) -> list[str]:
    start = datetime.fromisoformat(fecha_entrega).date()
    while start.weekday() >= 5:
        start += timedelta(days=1)
    days = [start]
    cursor = start
    while len(days) < dias_adicionales + 1:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            days.append(cursor)
    return [d.isoformat() for d in days]


def _run_autoruteo(db: sqlite3.Connection, semana_id: int) -> tuple[bool, str]:
    semana = db.execute("SELECT id, fecha_entrega FROM semanas WHERE id = ?", (semana_id,)).fetchone()
    if semana is None or not semana["fecha_entrega"]:
        return False, "La semana activa no tiene Fecha_Entrega cargada."

    horizon = _business_horizon(semana["fecha_entrega"], 5)
    horizon_days = {idx + 1: date for idx, date in enumerate(horizon)}

    stock_rows = db.execute(
        """
        SELECT a.descripcion AS sku, SUM(s.ep_cantidad) AS stock_ep
        FROM stock_dia s
        JOIN articulos a ON a.id = s.articulo_id
        WHERE s.semana_id = ? AND s.dia = 1
        GROUP BY a.id
        """,
        (semana_id,),
    ).fetchall()
    prod_rows = db.execute(
        """
        SELECT a.descripcion AS sku, SUM(p.ep_cantidad) AS prod_ep
        FROM prod_dia p
        JOIN articulos a ON a.id = p.articulo_id
        WHERE p.semana_id = ? AND p.dia BETWEEN 1 AND ?
        GROUP BY a.id
        """,
        (semana_id, len(horizon)),
    ).fetchall()
    demand_rows = db.execute(
        """
        SELECT a.descripcion AS sku, SUM(pe.ep_cantidad) AS demand_ep
        FROM pedidos pe
        JOIN articulos a ON a.id = pe.articulo_id
        WHERE pe.semana_id = ?
        GROUP BY a.id
        """,
        (semana_id,),
    ).fetchall()

    stock_by_sku = {row["sku"]: row["stock_ep"] or 0.0 for row in stock_rows}
    prod_by_sku = {row["sku"]: row["prod_ep"] or 0.0 for row in prod_rows}
    shortages: list[str] = []
    for row in demand_rows:
        sku = row["sku"]
        demand = row["demand_ep"] or 0.0
        available = stock_by_sku.get(sku, 0.0) + prod_by_sku.get(sku, 0.0)
        saldo = available - demand
        if saldo < -1e-9:
            shortages.append(f"{sku}: faltan {abs(saldo):.2f} EP")
    if shortages:
        return False, "Stock insuficiente (corte duro): " + "; ".join(shortages)

    rutas = db.execute(
        """
        SELECT r.id, r.nombre, v.capacidad_ep, v.max_clientes, v.max_turnos
        FROM rutas r
        JOIN vehiculos v ON v.id = r.vehiculo_id
        WHERE r.activa = 1
        ORDER BY r.id
        """
    ).fetchall()
    if not rutas:
        return False, "No hay rutas activas configuradas."

    backlog_rows = db.execute(
        """
        SELECT c.id AS cliente_id, c.razon_social, c.ruta_default, c.secuencia_default, SUM(p.ep_cantidad) AS ep_total
        FROM pedidos p
        JOIN clientes c ON c.id = p.cliente_id
        WHERE p.semana_id = ?
        GROUP BY c.id
        """,
        (semana_id,),
    ).fetchall()
    backlog = {row["cliente_id"]: row["ep_total"] or 0.0 for row in backlog_rows}
    clientes_meta = {
        row["cliente_id"]: {
            "nombre": row["razon_social"],
            "ruta_default": row["ruta_default"],
            "secuencia_default": row["secuencia_default"] or 999999,
        }
        for row in backlog_rows
    }

    turnos_rows = db.execute(
        """
        SELECT t.id, t.cliente_id, t.fecha, t.hora, t.pallets_turnados, c.razon_social
        FROM turnos t
        JOIN clientes c ON c.id = t.cliente_id
        WHERE t.semana_id = ?
        ORDER BY t.fecha, t.hora, t.id
        """,
        (semana_id,),
    ).fetchall()
    turnos_por_dia: dict[str, list[sqlite3.Row]] = {}
    for turno in turnos_rows:
        if turno["fecha"]:
            turnos_por_dia.setdefault(turno["fecha"], []).append(turno)

    db.execute("DELETE FROM asignaciones WHERE semana_id = ?", (semana_id,))
    now = datetime.utcnow().isoformat(timespec="seconds")

    for day_number, day in horizon_days.items():
        day_state = {
            route["id"]: {
                "cap_left": route["capacidad_ep"],
                "clients": set(),
                "turnos": 0,
                "nombre": route["nombre"],
                "max_clientes": route["max_clientes"],
                "max_turnos": route["max_turnos"],
            }
            for route in rutas
        }

        def can_assign(route_id: int, cliente_id: int, ep: float, con_turno: bool) -> bool:
            state = day_state[route_id]
            if ep > state["cap_left"] + 1e-9:
                return False
            if cliente_id not in state["clients"] and len(state["clients"]) >= state["max_clientes"]:
                return False
            if con_turno and state["turnos"] >= state["max_turnos"]:
                return False
            return True

        def apply_assign(route_id: int, cliente_id: int, ep: float, con_turno: bool, turno_id: int | None) -> None:
            state = day_state[route_id]
            state["cap_left"] -= ep
            if cliente_id not in state["clients"]:
                state["clients"].add(cliente_id)
            if con_turno:
                state["turnos"] += 1
            secuencia = len(state["clients"])
            db.execute(
                """
                INSERT INTO asignaciones (semana_id, fecha, ruta_id, cliente_id, ep_asignado, con_turno, turno_id, secuencia, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (semana_id, day, route_id, cliente_id, ep, 1 if con_turno else 0, turno_id, secuencia, now),
            )
            backlog[cliente_id] = max(0.0, backlog.get(cliente_id, 0.0) - ep)

        for turno in turnos_por_dia.get(day, []):
            cliente_id = turno["cliente_id"]
            pendiente = backlog.get(cliente_id, 0.0)
            if pendiente <= 0:
                continue
            pallets_turnados = turno["pallets_turnados"]
            if pallets_turnados is not None and pallets_turnados > 0 and pallets_turnados < pendiente:
                requerido = pallets_turnados
            else:
                requerido = pendiente

            chosen = None
            pref = clientes_meta.get(cliente_id, {}).get("ruta_default")
            rutas_ordenadas = sorted(rutas, key=lambda r: (0 if pref and r["nombre"] == pref else 1, r["id"]))
            for route in rutas_ordenadas:
                if can_assign(route["id"], cliente_id, requerido, True):
                    chosen = route
                    break
            if chosen is None:
                return False, f"Turno incumplible para cliente {turno['razon_social']} el día {day}."
            apply_assign(chosen["id"], cliente_id, requerido, True, turno["id"])

        clientes_sin_turno = [cid for cid, ep in backlog.items() if ep > 0]
        clientes_sin_turno.sort(
            key=lambda cid: (
                0 if clientes_meta[cid].get("ruta_default") else 1,
                clientes_meta[cid]["secuencia_default"],
                clientes_meta[cid]["nombre"],
            )
        )

        for cliente_id in clientes_sin_turno:
            ep = backlog.get(cliente_id, 0.0)
            if ep <= 0:
                continue
            preferred = clientes_meta[cliente_id].get("ruta_default")
            chosen = None
            rutas_ordenadas = sorted(rutas, key=lambda r: (0 if preferred and r["nombre"] == preferred else 1, r["id"]))
            for route in rutas_ordenadas:
                if can_assign(route["id"], cliente_id, ep, False):
                    chosen = route
                    break
            if chosen:
                apply_assign(chosen["id"], cliente_id, ep, False, None)

    db.commit()
    remanente = sum(backlog.values())
    if remanente > 1e-9:
        return True, f"Autoruteo ejecutado con backlog remanente de {remanente:.2f} EP fuera del horizonte."
    return True, f"Autoruteo OK. Horizonte: {horizon[0]} a {horizon[-1]}."


@app.route("/")
def dashboard():
    db = get_db()
    semana_activa = _get_semana_activa(db)
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


@app.route("/clientes")
def clientes():
    db = get_db()
    rows = db.execute(
        "SELECT cliente_ext_id, razon_social, ruta_default, secuencia_default, activo FROM clientes ORDER BY razon_social"
    ).fetchall()
    return render_template("clientes.html", clientes=rows)


@app.route("/articulos")
def articulos():
    db = get_db()
    rows = db.execute("SELECT sku, descripcion, ep_por_caja FROM articulos ORDER BY descripcion").fetchall()
    return render_template("articulos.html", articulos=rows)


@app.route("/maestros/vehiculos", methods=["GET", "POST"])
def maestros_vehiculos():
    db = get_db()
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        capacidad_ep = _as_float(request.form.get("capacidad_ep", "")) or 0.0
        max_clientes = int(_as_float(request.form.get("max_clientes", "")) or 0)
        max_turnos = int(_as_float(request.form.get("max_turnos", "")) or 0)
        if nombre and capacidad_ep > 0 and max_clientes > 0:
            db.execute(
                """
                INSERT INTO vehiculos (nombre, capacidad_ep, max_clientes, max_turnos, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(nombre) DO UPDATE SET
                    capacidad_ep=excluded.capacidad_ep,
                    max_clientes=excluded.max_clientes,
                    max_turnos=excluded.max_turnos,
                    updated_at=excluded.updated_at
                """,
                (nombre, capacidad_ep, max_clientes, max_turnos, datetime.utcnow().isoformat(timespec="seconds")),
            )
            db.commit()
        return redirect(url_for("maestros_vehiculos"))

    rows = db.execute("SELECT id, nombre, capacidad_ep, max_clientes, max_turnos FROM vehiculos ORDER BY nombre").fetchall()
    return render_template("vehiculos.html", vehiculos=rows)


@app.route("/maestros/rutas", methods=["GET", "POST"])
def maestros_rutas():
    db = get_db()
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        vehiculo_id = int(_as_float(request.form.get("vehiculo_id", "")) or 0)
        activa = 1 if request.form.get("activa") == "on" else 0
        if nombre and vehiculo_id > 0:
            db.execute(
                """
                INSERT INTO rutas (nombre, vehiculo_id, activa, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(nombre) DO UPDATE SET
                    vehiculo_id=excluded.vehiculo_id,
                    activa=excluded.activa,
                    updated_at=excluded.updated_at
                """,
                (nombre, vehiculo_id, activa, datetime.utcnow().isoformat(timespec="seconds")),
            )
            db.commit()
        return redirect(url_for("maestros_rutas"))

    vehiculos = db.execute("SELECT id, nombre FROM vehiculos ORDER BY nombre").fetchall()
    rutas = db.execute(
        """
        SELECT r.id, r.nombre, r.activa, v.nombre AS vehiculo
        FROM rutas r JOIN vehiculos v ON v.id = r.vehiculo_id
        ORDER BY r.nombre
        """
    ).fetchall()
    return render_template("rutas.html", vehiculos=vehiculos, rutas=rutas)


@app.route("/autoruteo", methods=["GET", "POST"])
def autoruteo():
    db = get_db()
    semana = _get_semana_activa(db)
    message = None
    status = None
    if request.method == "POST":
        if semana is None:
            status = "error"
            message = "No hay semana activa."
        else:
            ok, message = _run_autoruteo(db, semana["id"])
            status = "ok" if ok else "error"
    return render_template("autoruteo.html", semana=semana, message=message, status=status)


@app.route("/resultado")
def resultado():
    db = get_db()
    semana = _get_semana_activa(db)
    if semana is None:
        return render_template("resultado.html", dias=[])

    rows = db.execute(
        """
        SELECT a.fecha, r.nombre AS ruta, c.razon_social AS cliente, a.ep_asignado, a.con_turno, a.secuencia
        FROM asignaciones a
        JOIN rutas r ON r.id = a.ruta_id
        JOIN clientes c ON c.id = a.cliente_id
        WHERE a.semana_id = ?
        ORDER BY a.fecha, r.nombre, a.secuencia, c.razon_social
        """,
        (semana["id"],),
    ).fetchall()

    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(row["fecha"], []).append(row)
    dias = [(fecha, grouped[fecha]) for fecha in sorted(grouped.keys())]
    return render_template("resultado.html", dias=dias)


@app.route("/importar", methods=["GET", "POST"])
def importar():
    db = get_db()
    message = None
    if request.method == "POST":
        uploaded = request.files.get("archivo")
        strict_mode = request.form.get("modo_estricto") == "on"
        import_operativo = request.form.get("import_operativo") == "on"
        replace_operativo = request.form.get("replace_operativo") == "on"
        import_maestros = request.form.get("import_maestros") == "on"

        if uploaded is None or not uploaded.filename:
            message = "Debes seleccionar un archivo .xlsm o .xlsx"
        elif not uploaded.filename.lower().endswith((".xlsm", ".xlsx")):
            message = "Formato inválido. Solo se acepta .xlsm o .xlsx"
        else:
            raw = uploaded.read()
            try:
                sheets = read_xlsx_rows(raw)
            except Exception as exc:
                message = f"No se pudo leer el Excel: {exc}"
                sheets = {}

            if message is None:
                active = db.execute("SELECT value FROM config WHERE key = 'semana_activa'").fetchone()
                semana_id = int(active["value"]) if active and active["value"] else None
                if semana_id is None:
                    message = "No hay semana activa. Activá una semana en /semanas antes de importar."
                else:
                    status = "OK"
                    errors: list[dict[str, str]] = []
                    summary: dict[str, int] = {}

                    try:
                        db.execute("SAVEPOINT import_data")
                        summary, errors = import_data(
                            db,
                            sheets,
                            semana_id=semana_id,
                            import_operativo=import_operativo,
                            import_maestros=import_maestros,
                            replace_operativo=replace_operativo,
                        )
                        if strict_mode and errors:
                            db.execute("ROLLBACK TO import_data")
                            status = "STRICT_ABORT"
                        elif errors:
                            status = "OK_WITH_ERRORS"
                        db.execute("RELEASE import_data")
                    except Exception as exc:
                        db.execute("ROLLBACK TO import_data")
                        db.execute("RELEASE import_data")
                        status = "FAILED"
                        errors.append({"sheet": "SYSTEM", "error": str(exc)})
                        summary = {"clientes": 0, "articulos": 0, "pedidos": 0, "turnos": 0, "stock_rows": 0, "prod_rows": 0}

                    errores_csv = _errors_to_csv(errors)
                    run = db.execute(
                        """
                        INSERT INTO import_runs (created_at, semana_id, filename, status, summary_json, errores_csv)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            datetime.utcnow().isoformat(timespec="seconds"),
                            semana_id,
                            uploaded.filename,
                            status,
                            json.dumps(summary, ensure_ascii=False),
                            errores_csv,
                        ),
                    )
                    db.commit()
                    message = f"Importación finalizada con estado {status}. Run ID: {run.lastrowid}."

    runs = db.execute(
        "SELECT id, created_at, semana_id, filename, status, summary_json FROM import_runs ORDER BY id DESC LIMIT 20"
    ).fetchall()
    return render_template("importar.html", runs=runs, message=message)


@app.route("/importar/<int:run_id>/errores.csv")
def importar_errores(run_id: int):
    db = get_db()
    run = db.execute("SELECT errores_csv FROM import_runs WHERE id = ?", (run_id,)).fetchone()
    if run is None:
        return Response("run_id no encontrado", status=404)
    return Response(
        run["errores_csv"],
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=errores_run_{run_id}.csv"},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
