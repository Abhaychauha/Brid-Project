"""
Bird Species Observation Analysis — Interactive Streamlit Dashboard
=====================================================================
Upload one or two bird-monitoring Excel workbooks (e.g. the Forest and
Grassland survey files) and this app cleans the data on the fly and
builds a full interactive dashboard: filters, KPIs, temporal / spatial /
species / environmental / conservation / observer views, and a data
explorer with a cleaned-data download.

Run locally:
    streamlit run app.py
"""

import io
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from pathlib import Path

from utils.data_processing import (
    load_and_clean,
    combine_datasets,
    infer_habitat_from_filename,
)

# Resolve paths relative to THIS FILE's location, not the process's current
# working directory — hosting platforms (Streamlit Cloud, Docker, etc.) don't
# always launch the app with cwd set to this folder, which breaks plain
# relative paths like "data/raw/....xlsx".
APP_DIR = Path(__file__).resolve().parent
DEMO_FOREST_PATH = APP_DIR / "data" / "raw" / "Bird_Monitoring_Data_FOREST.XLSX"
DEMO_GRASSLAND_PATH = APP_DIR / "data" / "raw" / "Bird_Monitoring_Data_GRASSLAND.XLSX"

# ---------------------------------------------------------------------------
# Page config & light styling
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Bird Species Observation Dashboard",
    page_icon="🦉",
    layout="wide",
    initial_sidebar_state="expanded",
)

PRIMARY_GREEN = "#2e7d32"
ACCENT_GOLD = "#c9a227"
HABITAT_COLORS = {"Forest": "#2e7d32", "Grassland": "#c9a227"}

st.markdown(
    """
    <style>
        .block-container { padding-top: 1.6rem; }
        div[data-testid="stMetric"] {
            background: rgba(46, 125, 50, 0.06);
            border: 1px solid rgba(46, 125, 50, 0.15);
            border-radius: 10px;
            padding: 0.8rem 1rem;
        }
        h1, h2, h3 { color: #1b3a1e; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Data loading (cached on file content, so re-running filters is instant)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _clean_uploaded_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    habitat_hint = infer_habitat_from_filename(filename)
    df = load_and_clean(io.BytesIO(file_bytes), habitat_hint=habitat_hint)
    df.attrs["source_filename"] = filename
    return df


@st.cache_data(show_spinner=False)
def _load_demo_data() -> pd.DataFrame:
    if not DEMO_FOREST_PATH.is_file() or not DEMO_GRASSLAND_PATH.is_file():
        st.error(
            "Demo data files are missing from the deployment "
            f"(expected at `{DEMO_FOREST_PATH}` and `{DEMO_GRASSLAND_PATH}`). "
            "Please upload a workbook using the sidebar to continue."
        )
        return pd.DataFrame()
    forest = load_and_clean(DEMO_FOREST_PATH, habitat_hint="Forest")
    grassland = load_and_clean(DEMO_GRASSLAND_PATH, habitat_hint="Grassland")
    return combine_datasets([forest, grassland])


def build_dataset(uploaded_files) -> tuple[pd.DataFrame, list[dict], bool]:
    """Returns (combined_df, per_file_cleaning_summaries, used_demo_data)."""
    if not uploaded_files:
        return _load_demo_data(), [], True

    cleaned_frames, summaries = [], []
    for f in uploaded_files:
        df = _clean_uploaded_file(f.getvalue(), f.name)
        cleaned_frames.append(df)
        summaries.append(
            {
                "file": f.name,
                "rows": len(df),
                "duplicates_removed": df.attrs.get("duplicates_removed", 0),
                "rows_missing_species": df.attrs.get("rows_missing_species", 0),
            }
        )
    combined = combine_datasets(cleaned_frames)
    return combined, summaries, False


# ---------------------------------------------------------------------------
# Sidebar — upload
# ---------------------------------------------------------------------------
st.sidebar.title("🦉 Bird Dashboard")
st.sidebar.markdown(
    "Upload your bird-monitoring workbook(s) below to generate the dashboard."
)

uploaded_files = st.sidebar.file_uploader(
    "Upload Excel workbook(s) (.xlsx)",
    type=["xlsx", "xls"],
    accept_multiple_files=True,
    help="Each workbook may contain multiple sheets (one per admin unit) — "
         "all sheets are combined automatically. Upload the Forest and/or "
         "Grassland file, or any similarly-structured survey workbook.",
)

if "use_demo_data" not in st.session_state:
    st.session_state.use_demo_data = False

st.sidebar.caption("Don't have a file handy?")
if st.sidebar.button("Load demo dataset instead"):
    st.session_state.use_demo_data = True

# ---------------------------------------------------------------------------
# Landing page — shown until the user uploads a file (or opts into the demo)
# ---------------------------------------------------------------------------
if not uploaded_files and not st.session_state.use_demo_data:
    st.title("🦉 Bird Species Observation Analysis")
    st.markdown(
        "### Upload a file to generate your dashboard\n"
        "Use the **sidebar** to upload one or two bird-monitoring Excel "
        "workbooks (e.g. Forest and/or Grassland survey data). Each "
        "workbook can contain multiple sheets — they'll be combined and "
        "cleaned automatically, and the dashboard will build itself from "
        "whatever you upload."
    )
    st.info(
        "⬅️ Upload an `.xlsx` file in the sidebar to get started, or click "
        "**\"Load demo dataset instead\"** to explore a sample Forest + "
        "Grassland (2018) dataset."
    )
    st.stop()

with st.spinner("Cleaning data..."):
    df, cleaning_summaries, used_demo = build_dataset(
        uploaded_files if uploaded_files else None
    )

if df.empty:
    st.error("No usable data was found in the uploaded file(s). Please check "
             "the workbook has at least one non-empty sheet with the expected "
             "bird-observation columns.")
    st.stop()

if used_demo:
    st.sidebar.info("Showing demo data (Forest + Grassland, 2018).")
else:
    st.sidebar.success(f"Loaded {len(uploaded_files)} file(s), "
                        f"{len(df):,} cleaned observations.")
    with st.sidebar.expander("Cleaning summary"):
        for s in cleaning_summaries:
            st.write(f"**{s['file']}**")
            st.write(f"- {s['rows']:,} rows after cleaning")
            st.write(f"- {s['duplicates_removed']} exact duplicates removed")
            if s["rows_missing_species"]:
                st.write(f"- {s['rows_missing_species']} rows missing species name")

st.sidebar.markdown("---")
st.sidebar.subheader("Filters")

habitats = sorted(df["Location_Type"].dropna().unique().tolist())
sel_habitat = st.sidebar.multiselect("Habitat type", habitats, default=habitats)

admin_units = sorted(df["Admin_Unit_Code"].dropna().unique().tolist())
sel_units = st.sidebar.multiselect("Admin unit (park)", admin_units, default=admin_units)

years = sorted(df["Year"].dropna().unique().tolist())
sel_years = st.sidebar.multiselect("Year", years, default=years)

seasons = ["Spring", "Summer", "Fall", "Winter"]
present_seasons = [s for s in seasons if s in df["Season"].dropna().unique()]
sel_seasons = st.sidebar.multiselect("Season", present_seasons, default=present_seasons)

all_species = sorted(df["Common_Name"].dropna().unique().tolist())
sel_species = st.sidebar.multiselect(
    "Species (leave empty = all)", all_species, default=[]
)

watchlist_only = st.sidebar.checkbox("PIF Watchlist species only", value=False)

observers = sorted(df["Observer"].dropna().unique().tolist())
sel_observers = st.sidebar.multiselect("Observer", observers, default=observers)

# --- apply filters -----------------------------------------------------
mask = (
    df["Location_Type"].isin(sel_habitat)
    & df["Admin_Unit_Code"].isin(sel_units)
    & df["Year"].isin(sel_years)
    & df["Season"].isin(sel_seasons)
    & df["Observer"].isin(sel_observers)
)
if sel_species:
    mask &= df["Common_Name"].isin(sel_species)
if watchlist_only:
    mask &= df["PIF_Watchlist_Status"] == True  # noqa: E712

fdf = df[mask].copy()

st.sidebar.markdown("---")
st.sidebar.caption(
    "Note: the source data has no latitude/longitude, so 'spatial' views "
    "below are grouped by park (Admin Unit) and Plot, not a literal map."
)

# ---------------------------------------------------------------------------
# Header + KPIs
# ---------------------------------------------------------------------------
st.title("Bird Species Observation Analysis")
st.caption(
    "Distribution & diversity of bird species across Forest and Grassland "
    "habitats — habitat preference, environmental drivers, and conservation "
    "signals."
)

if fdf.empty:
    st.warning("No observations match the current filters. Try widening your selection.")
    st.stop()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Observations", f"{len(fdf):,}")
k2.metric("Unique species", f"{fdf['Common_Name'].nunique():,}")
k3.metric("Admin units", f"{fdf['Admin_Unit_Code'].nunique():,}")
k4.metric("Plots surveyed", f"{fdf['Plot_Name'].nunique():,}")
watch_pct = (fdf["PIF_Watchlist_Status"] == True).mean() * 100  # noqa: E712
k5.metric("Watchlist-species obs.", f"{watch_pct:.1f}%")

st.markdown("---")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_overview, tab_temporal, tab_spatial, tab_species, tab_env, tab_conservation, tab_observer, tab_data = st.tabs(
    ["Overview", "Temporal", "Spatial", "Species", "Environmental",
     "Conservation", "Observers", "Data Explorer"]
)

# --- Overview ------------------------------------------------------------
with tab_overview:
    c1, c2 = st.columns(2)
    with c1:
        hab_counts = fdf["Location_Type"].value_counts().reset_index()
        hab_counts.columns = ["Habitat", "Observations"]
        fig = px.bar(hab_counts, x="Habitat", y="Observations", color="Habitat",
                     color_discrete_map=HABITAT_COLORS, text="Observations",
                     title="Observations by Habitat Type")
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, width='stretch')

    with c2:
        richness = fdf.groupby("Location_Type")["Common_Name"].nunique().reset_index()
        richness.columns = ["Habitat", "Unique species"]
        fig = px.bar(richness, x="Habitat", y="Unique species", color="Habitat",
                     color_discrete_map=HABITAT_COLORS, text="Unique species",
                     title="Species Richness by Habitat Type")
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, width='stretch')

    unit_summary = fdf.groupby("Admin_Unit_Code").agg(
        Observations=("Common_Name", "size"),
        Species_Richness=("Common_Name", "nunique"),
        Plots=("Plot_Name", "nunique"),
    ).reset_index().sort_values("Species_Richness", ascending=False)

    fig = px.bar(unit_summary, x="Admin_Unit_Code", y="Species_Richness",
                 color="Species_Richness", color_continuous_scale="Greens",
                 title="Species Richness by Administrative Unit (Park)",
                 labels={"Admin_Unit_Code": "Admin Unit", "Species_Richness": "Unique species"})
    st.plotly_chart(fig, width='stretch')

    with st.expander("See summary table"):
        st.dataframe(unit_summary, width='stretch')

# --- Temporal --------------------------------------------------------------
with tab_temporal:
    month_order = ["January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"]
    month_counts = (fdf["Month_Name"].value_counts()
                     .reindex(month_order).dropna().reset_index())
    month_counts.columns = ["Month", "Observations"]
    fig = px.line(month_counts, x="Month", y="Observations", markers=True,
                  title="Observations by Month")
    st.plotly_chart(fig, width='stretch')

    c1, c2 = st.columns(2)
    with c1:
        season_hab = fdf.groupby(["Season", "Location_Type"]).size().reset_index(name="Observations")
        fig = px.bar(season_hab, x="Season", y="Observations", color="Location_Type",
                     barmode="group", color_discrete_map=HABITAT_COLORS,
                     category_orders={"Season": ["Spring", "Summer", "Fall", "Winter"]},
                     title="Observations by Season & Habitat")
        st.plotly_chart(fig, width='stretch')
    with c2:
        hour_hab = (fdf.dropna(subset=["Start_Hour"])
                    .groupby(["Start_Hour", "Location_Type"]).size()
                    .reset_index(name="Observations"))
        fig = px.bar(hour_hab, x="Start_Hour", y="Observations", color="Location_Type",
                     barmode="group", color_discrete_map=HABITAT_COLORS,
                     title="Observation Start Hour — Activity Window",
                     labels={"Start_Hour": "Hour of day"})
        st.plotly_chart(fig, width='stretch')

    heat = (fdf.dropna(subset=["Month_Name"])
            .groupby(["Admin_Unit_Code", "Month_Name"]).size()
            .reset_index(name="Observations"))
    heat_pivot = heat.pivot(index="Admin_Unit_Code", columns="Month_Name", values="Observations")
    heat_pivot = heat_pivot.reindex(columns=[m for m in month_order if m in heat_pivot.columns])
    fig = px.imshow(heat_pivot, aspect="auto", color_continuous_scale="Greens",
                     title="Observation Heatmap — Admin Unit x Month",
                     labels=dict(color="Observations"))
    st.plotly_chart(fig, width='stretch')

# --- Spatial -----------------------------------------------------------
with tab_spatial:
    st.caption("No latitude/longitude in the source data — shown by Admin Unit "
               "and Plot instead of a literal map.")
    top_plots = (fdf.groupby(["Admin_Unit_Code", "Plot_Name"])
                 .agg(Observations=("Common_Name", "size"),
                      Species=("Common_Name", "nunique"))
                 .reset_index().sort_values("Species", ascending=False).head(20))
    fig = px.treemap(top_plots, path=["Admin_Unit_Code", "Plot_Name"], values="Observations",
                      color="Species", color_continuous_scale="Greens",
                      title="Top Plots by Species Richness (size = observations, color = species count)")
    st.plotly_chart(fig, width='stretch')

    fig = px.bar(top_plots.sort_values("Species"), x="Species", y="Plot_Name",
                 orientation="h", color="Admin_Unit_Code",
                 title="Top 20 Plots by Species Richness",
                 labels={"Plot_Name": "Plot", "Species": "Unique species"})
    fig.update_layout(height=600)
    st.plotly_chart(fig, width='stretch')

# --- Species -------------------------------------------------------------
with tab_species:
    top_n = st.slider("Number of top species to show", 5, 30, 15)
    top_species = fdf["Common_Name"].value_counts().head(top_n).reset_index()
    top_species.columns = ["Species", "Observations"]
    fig = px.bar(top_species.sort_values("Observations"), x="Observations", y="Species",
                 orientation="h", color="Observations", color_continuous_scale="Purples",
                 title=f"Top {top_n} Most Frequently Observed Species")
    fig.update_layout(height=max(400, top_n * 25))
    st.plotly_chart(fig, width='stretch')

    c1, c2 = st.columns(2)
    with c1:
        sex_counts = fdf["Sex"].value_counts().reset_index()
        sex_counts.columns = ["Sex", "Count"]
        fig = px.pie(sex_counts, names="Sex", values="Count", title="Sex Ratio",
                     hole=0.4)
        st.plotly_chart(fig, width='stretch')
    with c2:
        id_counts = fdf["ID_Method"].value_counts().reset_index()
        id_counts.columns = ["ID Method", "Count"]
        fig = px.bar(id_counts, x="ID Method", y="Count", color="ID Method",
                     title="Identification Method")
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, width='stretch')

# --- Environmental -------------------------------------------------------
with tab_env:
    c1, c2 = st.columns(2)
    with c1:
        fig = px.histogram(fdf, x="Temperature", color="Location_Type", marginal="box",
                            color_discrete_map=HABITAT_COLORS, barmode="overlay", opacity=0.65,
                            title="Temperature Distribution (°C)")
        st.plotly_chart(fig, width='stretch')
    with c2:
        fig = px.histogram(fdf, x="Humidity", color="Location_Type", marginal="box",
                            color_discrete_map=HABITAT_COLORS, barmode="overlay", opacity=0.65,
                            title="Humidity Distribution (%)")
        st.plotly_chart(fig, width='stretch')

    c3, c4 = st.columns(2)
    with c3:
        sky_counts = fdf["Sky"].value_counts().reset_index()
        sky_counts.columns = ["Sky", "Count"]
        fig = px.bar(sky_counts, x="Sky", y="Count", color="Sky", title="Sky Conditions")
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, width='stretch')
    with c4:
        dist_counts = fdf["Disturbance"].value_counts().reset_index()
        dist_counts.columns = ["Disturbance", "Count"]
        fig = px.bar(dist_counts, x="Disturbance", y="Count", color="Disturbance",
                     title="Disturbance Impact on Counts")
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, width='stretch')

    daily = fdf.groupby("Date").agg(
        Observations=("Common_Name", "size"),
        Avg_Temperature=("Temperature", "mean"),
    ).reset_index()
    fig = px.scatter(daily, x="Avg_Temperature", y="Observations",
                      title="Daily Observations vs Average Temperature",
                      labels={"Avg_Temperature": "Average Temperature (°C)"})
    st.plotly_chart(fig, width='stretch')

# --- Conservation ----------------------------------------------------------
with tab_conservation:
    watch = fdf[fdf["PIF_Watchlist_Status"] == True]  # noqa: E712
    st.metric("Watchlist observations", f"{len(watch):,}",
              f"{len(watch)/len(fdf)*100:.1f}% of filtered data")

    if not watch.empty:
        top_watch = watch["Common_Name"].value_counts().head(10).reset_index()
        top_watch.columns = ["Species", "Observations"]
        fig = px.bar(top_watch.sort_values("Observations"), x="Observations", y="Species",
                     orientation="h", color="Observations", color_continuous_scale="Reds",
                     title="Top PIF-Watchlist (At-Risk) Species Observed")
        st.plotly_chart(fig, width='stretch')

        watch_unit = watch.groupby("Admin_Unit_Code").size().reset_index(name="Watchlist Observations")
        fig = px.bar(watch_unit.sort_values("Watchlist Observations", ascending=False),
                     x="Admin_Unit_Code", y="Watchlist Observations", color="Watchlist Observations",
                     color_continuous_scale="Reds", title="Watchlist Observations by Admin Unit")
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No PIF-Watchlist species observations in the current filter selection.")

    steward = fdf[fdf["Regional_Stewardship_Status"] == True]  # noqa: E712
    st.caption(f"Regional Stewardship priority observations: {len(steward):,} "
               f"({len(steward)/len(fdf)*100:.1f}% of filtered data)")

# --- Observers ---------------------------------------------------------
with tab_observer:
    obs_counts = fdf["Observer"].value_counts().reset_index()
    obs_counts.columns = ["Observer", "Observations"]
    fig = px.bar(obs_counts, x="Observer", y="Observations", color="Observer",
                 title="Observations by Observer")
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, width='stretch')

    obs_species = fdf.groupby("Observer")["Common_Name"].nunique().reset_index()
    obs_species.columns = ["Observer", "Unique species logged"]
    fig = px.bar(obs_species.sort_values("Unique species logged", ascending=False),
                 x="Observer", y="Unique species logged", color="Observer",
                 title="Unique Species Logged per Observer")
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, width='stretch')

# --- Data Explorer -------------------------------------------------------
with tab_data:
    st.subheader("Filtered, cleaned data")
    st.write(f"{len(fdf):,} rows × {len(fdf.columns)} columns matching current filters.")
    st.dataframe(fdf, width='stretch', height=450)

    csv_bytes = fdf.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download filtered data as CSV",
        data=csv_bytes,
        file_name="filtered_bird_observations.csv",
        mime="text/csv",
    )

st.markdown("---")
st.caption(
    "Built for the Bird Species Observation Analysis project — Environmental "
    "Studies, Biodiversity Conservation & Ecology. Upload new workbooks any "
    "time to regenerate this dashboard with fresh data."
)
