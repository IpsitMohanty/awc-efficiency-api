# AWC Efficiency API + Dashboard

A lightweight DuckDB-backed FastAPI service over AWC Operational Efficiency data,
plus a Streamlit dashboard that consumes the API.

## Repo structure

- `app/` — FastAPI app (DuckDB query layer + endpoints)
- `awc_dashboard/` — Streamlit dashboard UI
- `notebooks/` — analysis notebooks + derived outputs (non-sensitive)
- `Raw/` — local-only raw CSV (gitignored)
