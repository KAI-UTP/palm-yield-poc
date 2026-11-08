"""Data connectors: SAP on a schedule, a database table or query, or a file.

Every source ends as one CSV extract in the 117-column format, so the same checks and pipeline run on it.

The prototype has no SAP system to call, so SapConnector is SIMULATED: it produces the extract from the
bundled sample file, in the same format a real SAP Datasphere or OData extract would be mapped to.
Swapping in the real connection changes only `_fetch`; the pipeline after it stays the same.
"""
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SAP_CONFIG = {
    "System": "SAP S/4HANA (simulated in this prototype)",
    "Route": "SAP Datasphere replication flow to a CSV/Parquet extract",
    "Data": "Block harvest cycles: yield, fertilizer, leaf samples, pests, field conditions",
    "Schedule": "Daily at 02:00, after field data is posted",
    "Checks": "Same 117-column schema and 22 quality checks as a manual upload",
}


class SapConnector:
    simulated = True

    def __init__(self, sample_path):
        self.sample_path = Path(sample_path)

    def _fetch(self, dest):
        # Real system: query the SAP extract here. Prototype: copy the sample in the same schema.
        shutil.copyfile(self.sample_path, dest)

    def extract(self, dest_dir):
        """Pull the latest extract into dest_dir; return (file path, summary)."""
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        dest = dest_dir / f"sap_extract_{now:%Y%m%d_%H%M%S}.csv"
        self._fetch(dest)
        d = pd.read_csv(dest, encoding="utf-8-sig", usecols=lambda c: c in {"block_id", "estate_name", "harvest_cycle_no"})
        summary = {"synced_at": now.isoformat(timespec="seconds"), "rows": len(d), "blocks": int(d.block_id.nunique()),
                   "estates": int(d.estate_name.nunique()), "cycles": int(d.harvest_cycle_no.nunique()), "file": dest.name}
        return dest, summary


# ---------- Databases ----------
DB_KINDS = {"PostgreSQL": 5432, "MySQL": 3306, "SQLite file": None}
MAX_ROWS = 500_000
_TABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


def build_query(table=None, query=None):
    """A read-only SQL statement: one SELECT (or WITH ... SELECT), or SELECT * from a plain table name."""
    if query and query.strip():
        q = query.strip().rstrip(";").strip()
        if ";" in q or not re.match(r"(?is)^(select|with)\b", q):
            raise ValueError("Only one read-only SELECT query is allowed.")
        return q
    t = (table or "").strip()
    if not _TABLE.match(t):
        raise ValueError("Enter a table name such as harvest_cycle or plantation.harvest_cycle.")
    return f"SELECT * FROM {t}"


def connect(kind, host="", port=None, database="", user="", password="", sqlite_path=None):
    """Open a database connection. Drivers are pure Python, so they install anywhere."""
    if kind == "SQLite file":
        import sqlite3
        return sqlite3.connect(Path(sqlite_path).resolve().as_uri() + "?mode=ro", uri=True)
    if kind == "PostgreSQL":
        import pg8000.dbapi
        return pg8000.dbapi.connect(host=host, port=int(port or 5432), database=database, user=user, password=password, timeout=20)
    if kind == "MySQL":
        import pymysql
        return pymysql.connect(host=host, port=int(port or 3306), database=database, user=user, password=password,
                               connect_timeout=20, read_timeout=300)
    raise ValueError(f"Unknown database type: {kind}")


def read_database(conn, sql, max_rows=MAX_ROWS):
    """Run the query and return (rows as a DataFrame, whether it was cut at max_rows). Closes the connection."""
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [c[0] for c in cur.description]
        rows = cur.fetchmany(max_rows + 1)
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    return df.head(max_rows), len(df) > max_rows


def save_extract(df, dest_dir, name):
    """Write any loaded data as the CSV extract the pipeline reads."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (re.sub(r"[^A-Za-z0-9_.-]+", "_", name) + ".csv")
    df.to_csv(dest, index=False, encoding="utf-8")
    return dest
