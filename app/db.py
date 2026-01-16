import os
import duckdb

# Column names exactly as in your CSV
COLS = {
    "state": "STATE NAME",
    "district": "DISTRICT NAME",
    "project": "PROJECT NAME",
    "sector": "SECTOR NAME",
    "awc_code": "AWC CODE",
    "awc_name": "AWC NAME",
    "active_0_6": "TOTAL ACTIVE CHILDREN (0-6 YEARS)",
    "measured_0_6": "TOTAL ACTIVE CHILDREN MEASURED (0-6 YEARS)",
    "eff_0_6": "MEASURING EFFICIENCY (0-6 YEARS) (%)",
    "suw": "SUW %",
    "measured_0_5": "TOTAL ACTIVE CHILDREN MEASURED (0-5 YEARS)",
    "sam": "SAM %",
    "mam": "MAM %",
}

# Allowlist for sorting (client uses these keys)
SORT_KEYS = {
    "state": COLS["state"],
    "district": COLS["district"],
    "project": COLS["project"],
    "sector": COLS["sector"],
    "awc_code": COLS["awc_code"],
    "awc_name": COLS["awc_name"],
    "active_0_6": COLS["active_0_6"],
    "measured_0_6": COLS["measured_0_6"],
    "eff_0_6": COLS["eff_0_6"],
    "suw": COLS["suw"],
    "sam": COLS["sam"],
    "mam": COLS["mam"],
    "measured_0_5": COLS["measured_0_5"],
    # derived-per-row
    "coverage_gap": f'("{COLS["active_0_6"]}" - "{COLS["measured_0_6"]}")',
}

TABLE = "awc_eff"

def get_conn() -> duckdb.DuckDBPyConnection:
    # In-memory is simplest; switch to a file if you want persistence:
    # duckdb.connect("awc_eff.duckdb")
    return duckdb.connect(database=":memory:")

def init_db(con: duckdb.DuckDBPyConnection) -> None:
    csv_path = os.getenv("AWC_CSV_PATH")
    if not csv_path:
        raise RuntimeError("Missing env var AWC_CSV_PATH (path to CSV).")

    # Read CSV into a table once at startup.
    # `read_csv_auto` auto-detects types; good enough for this raw service.
    con.execute(f"""
        CREATE OR REPLACE TABLE {TABLE} AS
        SELECT * FROM read_csv_auto(?, header=true);
    """, [csv_path])

def build_where(filters: dict) -> tuple[str, list]:
    clauses = []
    params = []

    # Exact-match filters only (raw service). Add ILIKE later if needed.
    for key, col in [
        ("state", COLS["state"]),
        ("district", COLS["district"]),
        ("project", COLS["project"]),
        ("sector", COLS["sector"]),
        ("awc_code", COLS["awc_code"]),
    ]:
        val = filters.get(key)
        if val is not None and val != "":
            clauses.append(f'"{col}" = ?')
            params.append(val)

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where_sql, params
