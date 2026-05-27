# AWC Efficiency API + Dashboard

FastAPI + DuckDB microservice over **AWC Operational Efficiency** data, paired with a Streamlit dashboard for filtering, exploration, and operational review.

This repository is designed as a lightweight analytics service for working with Anganwadi Centre reporting data without requiring a full database server.

## What This Project Does

The project provides two connected layers:

- a **FastAPI service** that exposes queryable operational data
- a **Streamlit dashboard** that consumes the API for interactive exploration

The goal is to make AWC operational efficiency data easier to inspect, filter, and analyze for reporting, validation, and monitoring workflows.

## Why This Exists

Operational reporting datasets are often shared as CSV extracts or local files that are awkward to query repeatedly.

This project turns those files into a lightweight local analytics system by combining:

- DuckDB for fast analytical querying
- FastAPI for a clean service layer
- Streamlit for a quick user-facing dashboard

That makes it easier to move from raw reporting files to a reusable local decision-support tool.

## Architecture

Data files -> DuckDB -> FastAPI -> Streamlit dashboard

- DuckDB provides the analytical query layer
- FastAPI exposes data access endpoints
- Streamlit gives non-technical users a simple exploration interface

## Features

- Fast local analytics over AWC efficiency data
- DuckDB-backed query layer
- FastAPI endpoints for structured access
- Streamlit dashboard for filtering and exploration
- Notebook workspace for additional analysis
- Raw local data kept outside version control

## Tech Stack

- Python
- FastAPI
- DuckDB
- Streamlit
- Jupyter notebooks

## Repository Structure

- `app/` - FastAPI application and DuckDB query layer
- `awc_dashboard/` - Streamlit dashboard UI
- `notebooks/` - analysis notebooks and derived outputs
- `Raw/` - local raw CSV data (gitignored)

## Why DuckDB

DuckDB is a good fit here because it provides:

- fast local analytical queries
- simple file-based usage
- no separate database server to manage
- strong support for working with CSV and analytical workflows

For a local operational analytics service, it keeps the stack lightweight while still enabling structured querying.

## Typical Use Cases

- Explore AWC operational efficiency records interactively
- Filter data by geography or reporting slice
- Support reporting review and operational monitoring
- Prototype local analytics workflows before moving to larger infrastructure
- Feed dashboard views from a reusable API layer instead of ad hoc notebook logic

## Running the Project

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

If the API and dashboard have separate requirements files, install both as needed.

### 2. Start the FastAPI service

```bash
uvicorn app:app --reload
```

If your FastAPI entrypoint uses a different module path, replace `app:app` with the correct one.

### 3. Start the Streamlit dashboard

```bash
streamlit run awc_dashboard/app.py
```

If the dashboard entry file has a different name, adjust the path accordingly.

### 4. Open the apps

Typical local URLs:

- FastAPI docs: `http://127.0.0.1:8000/docs`
- Streamlit dashboard: `http://localhost:8501`

## Data Notes

- Raw operational datasets are expected to remain local and outside version control
- Derived or non-sensitive analysis outputs may live in `notebooks/`
- If schemas change across reporting periods, the query and dashboard logic may need small updates

## Suggested Improvements

- Add endpoint documentation with example responses
- Add dashboard screenshots to the README
- Document the expected DuckDB table/view schema
- Add a sample local setup flow with example data paths
- Add a short section on key filters and dashboard views

## Current Scope

This repository is intended as a lightweight local analytics system for operational data exploration and API-backed dashboarding.

It is not yet positioned as a hardened production service with authentication, multi-user concurrency controls, or cloud deployment automation.
