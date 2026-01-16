from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
import os, io, csv
import duckdb

app = FastAPI(title="AWC Efficiency Raw Data Service", version="2.2.0")

TABLE = "awc_eff"

# Columns (exact)
COL_STATE   = "STATE NAME"
COL_DIST    = "DISTRICT NAME"
COL_PROJ    = "PROJECT NAME"
COL_SECTOR  = "SECTOR NAME"
COL_AWC     = "AWC CODE"
COL_AWCNAME = "AWC NAME"

COL_ACTIVE_06 = "TOTAL ACTIVE CHILDREN (0-6 YEARS)"
COL_MEAS_06   = "TOTAL ACTIVE CHILDREN MEASURED (0-6 YEARS)"
COL_EFF_06    = "MEASURING EFFICIENCY (0-6 YEARS) (%)"
COL_SUW       = "SUW %"

COL_MEAS_05 = "TOTAL ACTIVE CHILDREN MEASURED (0-5 YEARS)"
COL_SAM     = "SAM %"
COL_MAM     = "MAM %"

# Always returned
BASE_COLS = [COL_STATE, COL_DIST, COL_PROJ, COL_SECTOR, COL_AWC, COL_AWCNAME]

# Metric lenses (reduce payload)
LENS_COLS = {
    "0_6": [COL_ACTIVE_06, COL_MEAS_06, COL_EFF_06, COL_SUW],
    "0_5": [COL_MEAS_05, COL_SAM, COL_MAM],
    "all": [COL_ACTIVE_06, COL_MEAS_06, COL_EFF_06, COL_SUW, COL_MEAS_05, COL_SAM, COL_MAM],
}

def require_con():
    if con is None:
        raise HTTPException(status_code=500, detail="DB not initialized (startup not completed)")

def normalize_lens(lens: str) -> str:
    if lens not in LENS_COLS:
        raise HTTPException(status_code=400, detail="lens must be one of: 0_6, 0_5, all")
    return lens

def normalize_order(order: str) -> str:
    o = (order or "").lower()
    if o not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="order must be 'asc' or 'desc'")
    return o

def select_cols_for_lens(lens: str) -> str:
    lens = normalize_lens(lens)
    cols = BASE_COLS + LENS_COLS[lens]
    return ", ".join([f'"{c}"' for c in cols])

def coverage_gap_06_expr() -> str:
    return f'(CAST("{COL_ACTIVE_06}" AS DOUBLE) - CAST("{COL_MEAS_06}" AS DOUBLE))'

# Sorting: allow only meaningful keys per lens
SORT_KEYS = {
    # base
    "state":    f'"{COL_STATE}"',
    "district": f'"{COL_DIST}"',
    "project":  f'"{COL_PROJ}"',
    "sector":   f'"{COL_SECTOR}"',
    "awc_code": f'"{COL_AWC}"',
    "awc_name": f'"{COL_AWCNAME}"',

    # 0-6
    "active_0_6":   f'CAST("{COL_ACTIVE_06}" AS DOUBLE)',
    "measured_0_6": f'CAST("{COL_MEAS_06}" AS DOUBLE)',
    "eff_0_6":      f'CAST("{COL_EFF_06}" AS DOUBLE)',
    "suw":          f'CAST("{COL_SUW}" AS DOUBLE)',
    "gap_0_6":      coverage_gap_06_expr(),

    # 0-5
    "measured_0_5": f'CAST("{COL_MEAS_05}" AS DOUBLE)',
    "sam":          f'CAST("{COL_SAM}" AS DOUBLE)',
    "mam":          f'CAST("{COL_MAM}" AS DOUBLE)',
}

ALLOWED_SORT_BY = {
    "0_6": {"state","district","project","sector","awc_code","awc_name","active_0_6","measured_0_6","eff_0_6","suw","gap_0_6"},
    "0_5": {"state","district","project","sector","awc_code","awc_name","measured_0_5","sam","mam"},
    "all": set(SORT_KEYS.keys()),
}

# Distinct fields for dropdowns
DISTINCT_FIELDS = {
    "state":   COL_STATE,
    "district": COL_DIST,
    "project":  COL_PROJ,
    "sector":   COL_SECTOR,
}

con: duckdb.DuckDBPyConnection | None = None

def rows_as_dicts(res):
    cols = [d[0] for d in res.description]
    return [dict(zip(cols, row)) for row in res.fetchall()]

def build_where(state=None, district=None, project=None, sector=None):
    clauses = []
    params = []
    if state:
        clauses.append(f'"{COL_STATE}" = ?');   params.append(state)
    if district:
        clauses.append(f'"{COL_DIST}" = ?');    params.append(district)
    if project:
        clauses.append(f'"{COL_PROJ}" = ?');    params.append(project)
    if sector:
        clauses.append(f'"{COL_SECTOR}" = ?');  params.append(sector)
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where_sql, params

def group_expr(group_by: str) -> str:
    if group_by == "district": return f'"{COL_DIST}"'
    if group_by == "project":  return f'"{COL_PROJ}"'
    if group_by == "sector":   return f'"{COL_SECTOR}"'
    if group_by == "awc":      return f'"{COL_AWC}"'
    raise HTTPException(status_code=400, detail="group_by must be one of: district, project, sector, awc")

@app.on_event("startup")
def startup():
    global con
    csv_path = os.getenv("AWC_CSV_PATH")
    if not csv_path:
        raise RuntimeError("Missing env var AWC_CSV_PATH")

    con = duckdb.connect(database=":memory:")
    con.execute(
        'CREATE OR REPLACE TABLE awc_eff AS SELECT * FROM read_csv_auto(?, header=true);',
        [csv_path],
    )

    # helper col for fast case-insensitive search
    con.execute("ALTER TABLE awc_eff ADD COLUMN IF NOT EXISTS awc_name_lc VARCHAR;")
    con.execute(f'UPDATE awc_eff SET awc_name_lc = lower("{COL_AWCNAME}");')

@app.get("/health")
def health():
    require_con()
    rows = con.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    return {"status": "ok", "rows": rows}

@app.get("/awc/{awc_code}")
def awc_detail(awc_code: str, lens: str = Query(default="all")):
    require_con()
    sel = select_cols_for_lens(lens)
    q = f"""
        SELECT {sel},
               {coverage_gap_06_expr()} AS coverage_gap_0_6
        FROM {TABLE}
        WHERE "{COL_AWC}" = ?
        LIMIT 1;
    """
    res = con.execute(q, [awc_code])
    rows = rows_as_dicts(res)
    if not rows:
        raise HTTPException(status_code=404, detail="AWC CODE not found")
    return rows[0]

@app.get("/awcs")
def list_awcs(
    lens: str = Query(default="0_6", description="0_6 | 0_5 | all"),
    state: str | None = Query(default=None),
    district: str | None = Query(default=None),
    project: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="eff_0_6"),
    order: str = Query(default="asc"),
):
    require_con()
    lens = normalize_lens(lens)
    order = normalize_order(order)

    if sort_by not in ALLOWED_SORT_BY[lens]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by for lens={lens}. Allowed: {sorted(ALLOWED_SORT_BY[lens])}"
        )

    where_sql, params = build_where(state=state, district=district, project=project, sector=sector)
    total = con.execute(f"SELECT COUNT(*) FROM {TABLE} {where_sql};", params).fetchone()[0]

    sel = select_cols_for_lens(lens)
    q = f"""
        SELECT {sel},
               {coverage_gap_06_expr()} AS coverage_gap_0_6
        FROM {TABLE}
        {where_sql}
        ORDER BY {SORT_KEYS[sort_by]} {order.upper()} NULLS LAST
        LIMIT ?
        OFFSET ?;
    """
    res = con.execute(q, params + [limit, offset])
    data = rows_as_dicts(res)
    return {"total": total, "limit": limit, "offset": offset, "lens": lens, "data": data}

@app.get(
    "/search",
    summary="Search AWC by code or name",
    description=(
        "Searches AWC CODE (prefix) and AWC NAME (contains, case-insensitive). "
        "Filters (state/district/project/sector) are supported too."
    ),
)
def search(
    query: str = Query(..., min_length=2, description="AWC CODE prefix or AWC NAME fragment"),
    lens: str = Query(default="all", description="0_6 | 0_5 | all"),
    state: str | None = Query(default=None),
    district: str | None = Query(default=None),
    project: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
):
    require_con()
    lens = normalize_lens(lens)

    q_raw = query.strip()
    q_lc = q_raw.lower()

    where_sql, params = build_where(state=state, district=district, project=project, sector=sector)

    search_clause = f'("{COL_AWC}" LIKE ? OR awc_name_lc LIKE ?)'
    search_params = [f"{q_raw}%", f"%{q_lc}%"]

    if where_sql:
        where_sql = where_sql + " AND " + search_clause
        params = params + search_params
    else:
        where_sql = "WHERE " + search_clause
        params = search_params

    sel = select_cols_for_lens(lens)
    sql = f"""
        SELECT {sel},
               {coverage_gap_06_expr()} AS coverage_gap_0_6
        FROM {TABLE}
        {where_sql}
        ORDER BY "{COL_STATE}", "{COL_DIST}", "{COL_PROJ}", "{COL_SECTOR}", "{COL_AWC}"
        LIMIT ?;
    """

    res = con.execute(sql, params + [limit])
    data = rows_as_dicts(res)
    return {"query": q_raw, "lens": lens, "count": len(data), "data": data}

@app.get("/distinct", summary="Get distinct values for dropdowns with optional filters")
def distinct(
    field: str = Query(..., description="One of: state, district, project, sector"),
    state: str | None = Query(default=None),
    district: str | None = Query(default=None),
    project: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Optional substring filter (case-insensitive)"),
    limit: int = Query(default=5000, ge=1, le=20000),
):
    require_con()

    if field not in DISTINCT_FIELDS:
        raise HTTPException(status_code=400, detail=f"field must be one of: {sorted(DISTINCT_FIELDS.keys())}")

    col = DISTINCT_FIELDS[field]

    clauses = []
    params: list = []

    if state:
        clauses.append(f'"{COL_STATE}" = ?');   params.append(state)
    if district:
        clauses.append(f'"{COL_DIST}" = ?');    params.append(district)
    if project:
        clauses.append(f'"{COL_PROJ}" = ?');    params.append(project)
    if sector:
        clauses.append(f'"{COL_SECTOR}" = ?');  params.append(sector)

    clauses.append(f'"{col}" IS NOT NULL')
    clauses.append(f"trim(\"{col}\") <> ''")

    if q and q.strip():
        clauses.append(f'lower("{col}") LIKE ?')
        params.append(f"%{q.strip().lower()}%")

    where_sql = "WHERE " + " AND ".join(clauses)

    sql = f"""
        SELECT DISTINCT "{col}" AS value
        FROM {TABLE}
        {where_sql}
        ORDER BY value
        LIMIT ?;
    """
    res = con.execute(sql, params + [limit])
    values = [r[0] for r in res.fetchall()]
    return {"field": field, "count": len(values), "data": values}

@app.get("/hierarchy", summary="Fetch distinct state/district/project/sector lists in one call")
def hierarchy(
    state: str | None = Query(default=None),
    district: str | None = Query(default=None),
    project: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Optional substring filter applied to returned lists"),
    limit: int = Query(default=5000, ge=1, le=20000),
):
    require_con()

    def get(field: str, f_state=None, f_district=None, f_project=None):
        col = DISTINCT_FIELDS[field]
        clauses = [f'"{col}" IS NOT NULL', f"trim(\"{col}\") <> ''"]
        params: list = []

        if f_state:
            clauses.append(f'"{COL_STATE}" = ?'); params.append(f_state)
        if f_district:
            clauses.append(f'"{COL_DIST}" = ?'); params.append(f_district)
        if f_project:
            clauses.append(f'"{COL_PROJ}" = ?'); params.append(f_project)

        if q and q.strip():
            clauses.append(f'lower("{col}") LIKE ?')
            params.append(f"%{q.strip().lower()}%")

        sql = f"""
            SELECT DISTINCT "{col}" AS value
            FROM {TABLE}
            WHERE {" AND ".join(clauses)}
            ORDER BY value
            LIMIT ?;
        """
        res = con.execute(sql, params + [limit])
        return [r[0] for r in res.fetchall()]

    states = get("state")
    districts = get("district", f_state=state)
    projects = get("project", f_state=state, f_district=district)
    sectors = get("sector", f_state=state, f_district=district, f_project=project)

    return {
        "filters": {"state": state, "district": district, "project": project},
        "data": {
            "states": states,
            "districts": districts,
            "projects": projects,
            "sectors": sectors,
        },
    }

@app.get("/summary")
def summary(
    group_by: str = Query(..., description="district|project|sector|awc"),
    lens: str = Query(default="0_6", description="0_6 | 0_5 | all"),
    state: str | None = Query(default=None),
    district: str | None = Query(default=None),
    project: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
):
    require_con()
    lens = normalize_lens(lens)

    gexpr = group_expr(group_by)
    where_sql, params = build_where(state=state, district=district, project=project, sector=sector)

    # Weighted aggregations:
    # - For 0–6 efficiency: weighted by Active(0–6) via sum(measured)/sum(active)
    # - For SUW% (0–6): weighted by Active(0–6)
    # - For SAM/MAM (0–5): weighted by Measured(0–5)
    select_parts = [
        f"{gexpr} AS group_key",
        "COUNT(*) AS awc_rows",
    ]

    if lens in ("0_6", "all"):
        select_parts += [
            f'SUM(CAST("{COL_ACTIVE_06}" AS DOUBLE)) AS active_0_6_total',
            f'SUM(CAST("{COL_MEAS_06}" AS DOUBLE))   AS measured_0_6_total',
            f"""
            CASE
              WHEN SUM(CAST("{COL_ACTIVE_06}" AS DOUBLE)) = 0 THEN NULL
              ELSE ROUND(100.0 * SUM(CAST("{COL_MEAS_06}" AS DOUBLE)) / SUM(CAST("{COL_ACTIVE_06}" AS DOUBLE)), 2)
            END AS eff_0_6_weighted_pct
            """,
            f'SUM(CAST("{COL_ACTIVE_06}" AS DOUBLE) - CAST("{COL_MEAS_06}" AS DOUBLE)) AS coverage_gap_0_6_total',
            f"""
            CASE
              WHEN SUM(CAST("{COL_ACTIVE_06}" AS DOUBLE)) = 0 THEN NULL
              ELSE ROUND(SUM(CAST("{COL_SUW}" AS DOUBLE) * CAST("{COL_ACTIVE_06}" AS DOUBLE)) / SUM(CAST("{COL_ACTIVE_06}" AS DOUBLE)), 2)
            END AS suw_weighted_pct
            """,
        ]

    if lens in ("0_5", "all"):
        select_parts += [
            f'SUM(CAST("{COL_MEAS_05}" AS DOUBLE)) AS measured_0_5_total',
            f"""
            CASE
              WHEN SUM(CAST("{COL_MEAS_05}" AS DOUBLE)) = 0 THEN NULL
              ELSE ROUND(SUM(CAST("{COL_SAM}" AS DOUBLE) * CAST("{COL_MEAS_05}" AS DOUBLE)) / SUM(CAST("{COL_MEAS_05}" AS DOUBLE)), 2)
            END AS sam_weighted_pct
            """,
            f"""
            CASE
              WHEN SUM(CAST("{COL_MEAS_05}" AS DOUBLE)) = 0 THEN NULL
              ELSE ROUND(SUM(CAST("{COL_MAM}" AS DOUBLE) * CAST("{COL_MEAS_05}" AS DOUBLE)) / SUM(CAST("{COL_MEAS_05}" AS DOUBLE)), 2)
            END AS mam_weighted_pct
            """,
        ]

    q = f"""
        SELECT
            {", ".join(select_parts)}
        FROM {TABLE}
        {where_sql}
        GROUP BY 1
        ORDER BY group_key
        LIMIT ?;
    """
    res = con.execute(q, params + [limit])
    data = rows_as_dicts(res)
    return {
        "group_by": group_by,
        "lens": lens,
        "filters": {"state": state, "district": district, "project": project, "sector": sector},
        "count": len(data),
        "data": data
    }

@app.get("/export")
def export_csv(
    lens: str = Query(default="all", description="0_6 | 0_5 | all"),
    state: str | None = Query(default=None),
    district: str | None = Query(default=None),
    project: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    sort_by: str = Query(default="awc_code"),
    order: str = Query(default="asc"),
):
    require_con()
    lens = normalize_lens(lens)
    order = normalize_order(order)

    if sort_by not in ALLOWED_SORT_BY[lens]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by for lens={lens}. Allowed: {sorted(ALLOWED_SORT_BY[lens])}"
        )

    where_sql, params = build_where(state=state, district=district, project=project, sector=sector)
    sel = select_cols_for_lens(lens)

    q = f"""
        SELECT {sel},
               {coverage_gap_06_expr()} AS coverage_gap_0_6
        FROM {TABLE}
        {where_sql}
        ORDER BY {SORT_KEYS[sort_by]} {order.upper()} NULLS LAST;
    """

    def iter_csv():
        res = con.execute(q, params)
        cols = [d[0] for d in res.description]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(cols)
        for row in res.fetchall():
            writer.writerow(row)
        yield buf.getvalue()

    return StreamingResponse(
        iter_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="awcs_export.csv"'},
    )
