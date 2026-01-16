import os
import requests
import pandas as pd
import streamlit as st
import altair as alt

# ------------------------
# Page config (ONLY ONCE, must be first Streamlit call)
# ------------------------
st.set_page_config(page_title="AWC Operational Efficiency Dashboard", layout="wide")

# ------------------------
# Config
# ------------------------
DEFAULT_API_BASE = os.getenv("AWC_API_BASE", "http://127.0.0.1:8000").strip().rstrip("/")

st.title("AWC Operational Efficiency Dashboard")
st.caption("Render check: app.py executed.")

# ------------------------
# Helpers
# ------------------------
@st.cache_data(ttl=60)
def api_get(base_url: str, path: str, params: dict | None = None):
    url = f"{base_url}{path}"
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()

def df_from_data(payload, key="data"):
    rows = payload.get(key, [])
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)

def fmt_int(x):
    try:
        return f"{int(x):,}"
    except Exception:
        return "—"

def fmt_pct(x):
    try:
        return f"{float(x):.2f}%"
    except Exception:
        return "—"

def clean_api_base(x: str) -> str:
    return (x or "").strip().rstrip("/")

def as_options(values: list[str], include_all=True):
    vals = [v for v in values if v and str(v).strip()]
    vals = sorted(list(dict.fromkeys(vals)), key=lambda s: s.lower())
    if include_all:
        return ["(All)"] + vals
    return vals

def selected_or_none(selection: str):
    return None if selection in (None, "", "(All)") else selection

# ------------- API helpers (cached) -------------
@st.cache_data(ttl=120)
def get_hierarchy(base_url: str, state: str | None, district: str | None, project: str | None):
    """
    Calls /hierarchy for dropdown lists in one go.
    Response shape:
      {"data": {"states": [...], "districts": [...], "projects": [...], "sectors": [...]} }
    """
    params = {"state": state, "district": district, "project": project}
    params = {k: v for k, v in params.items() if v}
    return api_get(base_url, "/hierarchy", params)

@st.cache_data(ttl=60)
def get_summary(base_url: str, lens: str, group_by: str, filters: dict):
    params = {"group_by": group_by, "lens": lens, "limit": 5000}
    params.update({k: v for k, v in filters.items() if v})
    payload = api_get(base_url, "/summary", params)
    return df_from_data(payload, key="data"), payload

@st.cache_data(ttl=30)
def get_awcs(base_url: str, params: dict):
    payload = api_get(base_url, "/awcs", params)
    return payload, df_from_data(payload, key="data")

@st.cache_data(ttl=30)
def do_search(base_url: str, query: str, lens: str, filters: dict, limit: int = 20):
    params = {"query": query, "lens": lens, "limit": limit}
    params.update({k: v for k, v in filters.items() if v})
    payload = api_get(base_url, "/search", params)
    return payload, df_from_data(payload, key="data")

# ------------------------
# Sidebar controls
# ------------------------
st.sidebar.title("Controls")

api_base_in = st.sidebar.text_input("API Base URL", value=DEFAULT_API_BASE)
API_BASE = clean_api_base(api_base_in) or DEFAULT_API_BASE

if st.sidebar.button("Clear cache"):
    st.cache_data.clear()
    st.rerun()

lens = st.sidebar.selectbox("Lens", ["0_6", "0_5", "all"], index=0)

# include "awc" since your API supports it
group_by = st.sidebar.selectbox("Group By (for summary)", ["district", "project", "sector", "awc"], index=0)

# auto grouping toggle
auto_group = st.sidebar.checkbox("Auto group (recommended)", value=True)

st.sidebar.markdown("---")

# ------------------------
# Health
# ------------------------
with st.expander("Service Status", expanded=False):
    try:
        h = api_get(API_BASE, "/health")
        st.json(h)
    except Exception as e:
        st.error(f"Health check failed: {e}")
        st.stop()

# ------------------------
# Filters (dropdowns using /hierarchy)
# ------------------------
st.sidebar.subheader("Filters (dropdowns)")

default_state = "Odisha"

# init session_state
if "state" not in st.session_state:
    st.session_state.state = default_state
if "district" not in st.session_state:
    st.session_state.district = "(All)"
if "project" not in st.session_state:
    st.session_state.project = "(All)"
if "sector" not in st.session_state:
    st.session_state.sector = "(All)"

# Fetch hierarchy based on current selections (All -> None)
try:
    cur_state = st.session_state.state or default_state
    cur_district = selected_or_none(st.session_state.district)
    cur_project = selected_or_none(st.session_state.project)

    hier = get_hierarchy(API_BASE, cur_state, cur_district, cur_project)
    data = hier.get("data", {}) or {}
except Exception as e:
    st.sidebar.error(f"Hierarchy load failed: {e}")
    data = {"states": [default_state], "districts": [], "projects": [], "sectors": []}

states = data.get("states", []) or [default_state]
districts = data.get("districts", []) or []
projects = data.get("projects", []) or []
sectors = data.get("sectors", []) or []

# ---- State dropdown (build opts -> reset stale -> select)
state_opts = as_options(states, include_all=False)

if st.session_state.state not in state_opts:
    st.session_state.state = default_state

if default_state in state_opts:
    default_state_index = state_opts.index(default_state)
else:
    state_opts = [default_state] + state_opts
    default_state_index = 0

st.session_state.state = st.sidebar.selectbox(
    "State",
    options=state_opts,
    index=state_opts.index(st.session_state.state) if st.session_state.state in state_opts else default_state_index,
)

# ---- District dropdown
district_opts = as_options(districts, include_all=True)

if st.session_state.district not in district_opts:
    st.session_state.district = "(All)"

st.session_state.district = st.sidebar.selectbox(
    "District",
    options=district_opts,
    index=district_opts.index(st.session_state.district) if st.session_state.district in district_opts else 0,
)

# ---- Project dropdown
project_opts = as_options(projects, include_all=True)

if st.session_state.project not in project_opts:
    st.session_state.project = "(All)"

st.session_state.project = st.sidebar.selectbox(
    "Project",
    options=project_opts,
    index=project_opts.index(st.session_state.project) if st.session_state.project in project_opts else 0,
)

# ---- Sector dropdown
sector_opts = as_options(sectors, include_all=True)

if st.session_state.sector not in sector_opts:
    st.session_state.sector = "(All)"

st.session_state.sector = st.sidebar.selectbox(
    "Sector",
    options=sector_opts,
    index=sector_opts.index(st.session_state.sector) if st.session_state.sector in sector_opts else 0,
)

# Build filters dict
filters = {
    "state": st.session_state.state,
    "district": selected_or_none(st.session_state.district),
    "project": selected_or_none(st.session_state.project),
    "sector": selected_or_none(st.session_state.sector),
}
filters = {k: v for k, v in filters.items() if v}

# ------------------------
# Auto group_by (keeps charts meaningful when filters narrow to a single group)
# ------------------------
effective_group_by = group_by
if auto_group:
    if filters.get("sector"):
        effective_group_by = "awc"
    elif filters.get("project"):
        effective_group_by = "sector"
    elif filters.get("district"):
        effective_group_by = "project"
    else:
        effective_group_by = group_by

if effective_group_by != group_by:
    st.sidebar.info(f"Auto Group By → {effective_group_by}")

st.sidebar.markdown("---")

# ------------------------
# Search (uses /search)
# ------------------------
st.sidebar.subheader("Search AWC")
search_q = st.sidebar.text_input("AWC code prefix or name contains", value="").strip()

if search_q:
    with st.expander("Search results", expanded=True):
        try:
            sp, df_s = do_search(API_BASE, search_q, lens="all", filters=filters, limit=25)
            if df_s.empty:
                st.info("No matches.")
            else:
                show_cols = [
                    c for c in [
                        "STATE NAME","DISTRICT NAME","PROJECT NAME","SECTOR NAME",
                        "AWC CODE","AWC NAME",
                        "MEASURING EFFICIENCY (0-6 YEARS) (%)","SUW %","SAM %","MAM %",
                        "coverage_gap_0_6"
                    ]
                    if c in df_s.columns
                ]
                st.dataframe(df_s[show_cols] if show_cols else df_s, use_container_width=True, height=260)
        except Exception as e:
            st.error(f"/search failed: {e}")

st.sidebar.markdown("---")

# ------------------------
# Sorting (single + simulated multi)
# ------------------------
st.sidebar.subheader("Sorting (AWCs)")
sort_defaults = {"0_6": "eff_0_6", "0_5": "sam", "all": "eff_0_6"}

primary_sort = st.sidebar.text_input("Primary sort_by (API)", value=sort_defaults[lens]).strip()
primary_order = st.sidebar.selectbox("Primary order", ["asc", "desc"], index=1)

use_secondary = st.sidebar.checkbox("Secondary sort (local, current page only)", value=True)
default_secondary = "mam" if lens in ("0_5", "all") else "coverage_gap_0_6"
secondary_sort = st.sidebar.text_input("Secondary sort (local)", value=default_secondary).strip()
secondary_order = st.sidebar.selectbox("Secondary order (local)", ["asc", "desc"], index=1)

limit = st.sidebar.slider("Rows per page", 50, 500, 100, 50)
page = st.sidebar.number_input("Page", min_value=1, value=1, step=1)
offset = (page - 1) * limit

# ------------------------
# Header
# ------------------------
st.caption("Lens-based view: 0–6 (operations) vs 0–5 (nutrition). Powered by FastAPI + DuckDB.")

# ------------------------
# Summary (KPI + grouped table)
# ------------------------
st.subheader("Summary")

try:
    df_summary, summary_payload = get_summary(API_BASE, lens=lens, group_by=effective_group_by, filters=filters)
except Exception as e:
    st.error(f"/summary failed: {e}")
    st.stop()

def totals_from_summary(df: pd.DataFrame):
    out = {}

    if "active_0_6_total" in df.columns:
        out["active_0_6_total"] = df["active_0_6_total"].sum()
    if "measured_0_6_total" in df.columns:
        out["measured_0_6_total"] = df["measured_0_6_total"].sum()
    if "coverage_gap_0_6_total" in df.columns:
        out["coverage_gap_0_6_total"] = df["coverage_gap_0_6_total"].sum()

    if out.get("active_0_6_total") and out.get("measured_0_6_total") is not None:
        out["eff_0_6_weighted_pct"] = round(100.0 * out["measured_0_6_total"] / out["active_0_6_total"], 2)

    if "measured_0_5_total" in df.columns:
        out["measured_0_5_total"] = df["measured_0_5_total"].sum()

    for col in ["suw_weighted_pct", "sam_weighted_pct", "mam_weighted_pct"]:
        if col in df.columns:
            out[col] = float(df[col].median()) if pd.notna(df[col]).any() else None

    return out

kpis = totals_from_summary(df_summary) if not df_summary.empty else {}

# KPI Row 1: 0–6 metrics
if lens in ("0_6", "all"):
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Active (0–6)", fmt_int(kpis.get("active_0_6_total")))
    c2.metric("Measured (0–6)", fmt_int(kpis.get("measured_0_6_total")))
    c3.metric("Efficiency (weighted)", fmt_pct(kpis.get("eff_0_6_weighted_pct")))
    c4.metric("Coverage Gap (0–6)", fmt_int(kpis.get("coverage_gap_0_6_total")))
    c5.metric("SUW (weighted)", fmt_pct(kpis.get("suw_weighted_pct")))

# KPI Row 2: 0–5 nutrition metrics
if lens in ("0_5", "all"):
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Measured (0–5)", fmt_int(kpis.get("measured_0_5_total")))
    c2.metric("SAM (weighted)", fmt_pct(kpis.get("sam_weighted_pct")))
    c3.metric("MAM (weighted)", fmt_pct(kpis.get("mam_weighted_pct")))
    c4.metric("Groups", fmt_int(len(df_summary)))
    c5.metric("—", "—")

# ------------------------
# Ranked groups + Visualizations
# ------------------------
st.markdown("### Ranked groups")

df_rank = pd.DataFrame()
if df_summary.empty:
    st.info("No summary rows. Try loosening filters.")
else:
    if lens in ("0_6", "all") and "coverage_gap_0_6_total" in df_summary.columns:
        df_rank = df_summary.sort_values(
            by=["coverage_gap_0_6_total", "eff_0_6_weighted_pct"],
            ascending=[False, True],
            na_position="last",
        )
    elif lens in ("0_5", "all") and "sam_weighted_pct" in df_summary.columns:
        df_rank = df_summary.sort_values(
            by=["sam_weighted_pct", "mam_weighted_pct"],
            ascending=[False, False],
        )
    else:
        df_rank = df_summary.copy()

    st.dataframe(df_rank, use_container_width=True, height=350)

st.markdown("### Visualizations")

def barh(df: pd.DataFrame, label_col: str, value_col: str, title: str, top_n: int = 20):
    sub = df[[label_col, value_col]].dropna().head(top_n).copy()
    sub[label_col] = sub[label_col].astype(str)
    return (
        alt.Chart(sub)
        .mark_bar()
        .encode(
            y=alt.Y(f"{label_col}:N", sort="-x", title=None),
            x=alt.X(f"{value_col}:Q", title=title),
            tooltip=[alt.Tooltip(label_col, title="Group"), alt.Tooltip(value_col, title=title)],
        )
        .properties(height=min(520, 18 * len(sub) + 40))
    )

if not df_rank.empty:
    if len(df_rank) <= 1:
        st.info("Not enough groups to plot. Try relaxing filters or change Group By (or disable Auto group).")
    else:
        label_col = "group_key" if "group_key" in df_rank.columns else df_rank.columns[0]

        if lens in ("0_6", "all") and "coverage_gap_0_6_total" in df_rank.columns:
            st.markdown("**Top groups by Coverage Gap (0–6)**")
            st.altair_chart(barh(df_rank, label_col, "coverage_gap_0_6_total", "Coverage Gap (0–6)"), use_container_width=True)

        if lens in ("0_6", "all") and "suw_weighted_pct" in df_rank.columns:
            st.markdown("**Top groups by SUW% (weighted)**")
            st.altair_chart(barh(df_rank, label_col, "suw_weighted_pct", "SUW% (weighted)"), use_container_width=True)

        if lens in ("0_5", "all") and "sam_weighted_pct" in df_rank.columns:
            st.markdown("**Top groups by SAM% (weighted)**")
            st.altair_chart(barh(df_rank, label_col, "sam_weighted_pct", "SAM% (weighted)"), use_container_width=True)

        if lens in ("0_5", "all") and "mam_weighted_pct" in df_rank.columns:
            st.markdown("**Top groups by MAM% (weighted)**")
            st.altair_chart(barh(df_rank, label_col, "mam_weighted_pct", "MAM% (weighted)"), use_container_width=True)

# ------------------------
# AWC list table
# ------------------------
st.subheader("AWC Rows")

awcs_params = {
    "lens": lens,
    "limit": int(limit),
    "offset": int(offset),
    "sort_by": primary_sort or sort_defaults[lens],
    "order": primary_order,
}
awcs_params.update(filters)

try:
    awcs_payload, df_awcs = get_awcs(API_BASE, awcs_params)
except Exception as e:
    st.error(f"/awcs failed: {e}")
    st.stop()

total = awcs_payload.get("total", 0)

# Local secondary sort (current page only)
if use_secondary and not df_awcs.empty and secondary_sort in df_awcs.columns:
    asc1 = (primary_order == "asc")
    asc2 = (secondary_order == "asc")
    cols = [c for c in [primary_sort, secondary_sort] if c in df_awcs.columns]
    if cols:
        df_awcs = df_awcs.sort_values(by=cols, ascending=[asc1, asc2][:len(cols)], na_position="last")

if lens == "0_5":
    df_awcs = df_awcs.drop(columns=["coverage_gap_0_6"], errors="ignore")

st.caption(f"Showing {len(df_awcs)} rows out of {total:,} total. Page {page} (offset={offset}).")
st.dataframe(df_awcs, use_container_width=True, height=420)

# Efficiency distribution chart (Altair)
if lens in ("0_6", "all") and "eff_0_6" in df_awcs.columns and not df_awcs.empty:
    st.markdown("### Efficiency distribution (current page)")
    tmp = df_awcs[["eff_0_6"]].dropna().copy()
    if not tmp.empty:
        chart = (
            alt.Chart(tmp)
            .mark_bar()
            .encode(
                x=alt.X("eff_0_6:Q", bin=alt.Bin(maxbins=20), title="Efficiency (0–6)"),
                y=alt.Y("count():Q", title="Count"),
                tooltip=[alt.Tooltip("count():Q", title="Count")],
            )
            .properties(height=220)
        )
        st.altair_chart(chart, use_container_width=True)

# ------------------------
# Export
# ------------------------
st.subheader("Export")
export_params = {"lens": lens, "sort_by": awcs_params["sort_by"], "order": awcs_params["order"]}
export_params.update(filters)

export_url = f"{API_BASE}/export"
st.write("Use the same filters as above to export CSV.")

colA, colB = st.columns([1, 3])
with colA:
    if st.button("Fetch CSV"):
        try:
            r = requests.get(export_url, params=export_params, timeout=120)
            r.raise_for_status()
            st.download_button(
                "Download awcs_export.csv",
                data=r.content,
                file_name="awcs_export.csv",
                mime="text/csv",
            )
        except Exception as e:
            st.error(f"Export failed: {e}")

with colB:
    st.code(f"GET {export_url}", language="text")
    st.json(export_params)
