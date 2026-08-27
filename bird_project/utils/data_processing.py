"""
data_processing.py
-------------------
Reusable data cleaning / preprocessing pipeline for the Bird Species
Observation Analysis project.

This module is imported by BOTH:
  1. The EDA notebook / script (offline analysis)
  2. The Streamlit dashboard (app.py) -> so that whatever file a user
     uploads goes through the exact same, tested cleaning logic.

Design goal: the pipeline should work on:
  - The original "Bird_Monitoring_Data_FOREST.XLSX" (multi-sheet, one
    sheet per Admin_Unit_Code)
  - The original "Bird_Monitoring_Data_GRASSLAND.XLSX" (same structure)
  - Any similarly-structured excel file a user uploads later, even if
    it only has some of the columns, or a single sheet.
"""

from __future__ import annotations

import io
import re
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Column harmonisation
# ---------------------------------------------------------------------------
# The two source files are almost identical but not quite:
#   FOREST has:    Site_Name, NPSTaxonCode
#   GRASSLAND has: TaxonCode, Previously_Obs
# We map both "taxon code" variants onto a single canonical column name,
# and make sure every optional column exists (filled with NaN) so the two
# habitats can be safely concatenated.

CANONICAL_COLUMNS = [
    "Admin_Unit_Code", "Sub_Unit_Code", "Site_Name", "Plot_Name",
    "Location_Type", "Year", "Date", "Start_Time", "End_Time", "Observer",
    "Visit", "Interval_Length", "ID_Method", "Distance", "Flyover_Observed",
    "Sex", "Common_Name", "Scientific_Name", "AcceptedTSN", "TaxonCode",
    "AOU_Code", "PIF_Watchlist_Status", "Regional_Stewardship_Status",
    "Temperature", "Humidity", "Sky", "Wind", "Disturbance",
    "Previously_Obs", "Initial_Three_Min_Cnt",
]

RENAME_MAP = {
    "NPSTaxonCode": "TaxonCode",
}

BOOL_LIKE_COLUMNS = [
    "Flyover_Observed", "PIF_Watchlist_Status", "Regional_Stewardship_Status",
    "Previously_Obs", "Initial_Three_Min_Cnt",
]

TEXT_COLUMNS = [
    "Admin_Unit_Code", "Site_Name", "Plot_Name", "Location_Type",
    "Observer", "Interval_Length", "ID_Method", "Distance", "Sex",
    "Common_Name", "Scientific_Name", "AOU_Code", "Sky", "Wind",
    "Disturbance",
]


def _to_bool(series: pd.Series) -> pd.Series:
    """Coerce a messy TRUE/FALSE/1/0/yes/no-like column to real booleans,
    keeping NaN where the value is genuinely missing."""
    mapping = {
        "true": True, "false": False, "1": True, "0": False,
        "yes": True, "no": False, "t": True, "f": False,
    }

    def conv(v):
        if pd.isna(v):
            return np.nan
        if isinstance(v, (bool, np.bool_)):
            return bool(v)
        if isinstance(v, (int, float)):
            return bool(v)
        return mapping.get(str(v).strip().lower(), np.nan)

    return series.apply(conv)


def load_workbook(file_like, habitat_hint: str | None = None) -> pd.DataFrame:
    """Load every sheet of an uploaded / on-disk Excel workbook and stack
    them into a single long DataFrame.

    Parameters
    ----------
    file_like: path string, bytes, or a file-like object (e.g. what
        st.file_uploader gives you).
    habitat_hint: optional string ("Forest" / "Grassland") used as a
        fallback for the Location_Type column if a sheet is missing it.
    """
    xls = pd.ExcelFile(file_like)
    frames = []
    for sheet in xls.sheet_names:
        df = xls.parse(sheet)
        if df.empty:
            continue
        df["__source_sheet"] = sheet
        frames.append(df)

    if not frames:
        raise ValueError("No non-empty sheets were found in this workbook.")

    combined = pd.concat(frames, ignore_index=True, sort=False)

    # Harmonise column names (e.g. NPSTaxonCode -> TaxonCode)
    combined = combined.rename(columns=RENAME_MAP)

    # Make sure every canonical column exists, even if this particular
    # workbook doesn't have it, so downstream code never KeyErrors.
    for col in CANONICAL_COLUMNS:
        if col not in combined.columns:
            combined[col] = np.nan

    if habitat_hint and combined["Location_Type"].isna().all():
        combined["Location_Type"] = habitat_hint

    return combined


def clean_bird_data(raw: pd.DataFrame, drop_exact_duplicates: bool = True) -> pd.DataFrame:
    """Apply the full cleaning / preprocessing pipeline to a raw,
    concatenated bird-observation DataFrame and return an analysis-ready
    copy. Non-destructive: does not mutate the input.
    """
    df = raw.copy()

    # --- 1. Standardise column presence -----------------------------------
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    # --- 2. Drop fully-empty helper columns / exact duplicate rows --------
    dup_count = 0
    if drop_exact_duplicates:
        subset_cols = [c for c in df.columns if c != "__source_sheet"]
        before = len(df)
        df = df.drop_duplicates(subset=subset_cols, keep="first")
        dup_count = before - len(df)

    # --- 3. Parse dates / times ---------------------------------------------
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    def parse_time(col):
        # Handles both datetime.time objects and "HH:MM:SS" strings
        parsed = pd.to_datetime(df[col].astype(str), errors="coerce", format="mixed")
        return parsed.dt.time

    for tcol in ["Start_Time", "End_Time"]:
        try:
            df[tcol] = parse_time(tcol)
        except Exception:
            pass  # leave as-is if unparseable; charts will just skip NaT

    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    # Derive Year from Date where missing / inconsistent
    df["Year"] = df["Year"].fillna(df["Date"].dt.year)

    df["Month"] = df["Date"].dt.month
    df["Month_Name"] = df["Date"].dt.month_name()
    df["Day_of_Week"] = df["Date"].dt.day_name()

    season_map = {12: "Winter", 1: "Winter", 2: "Winter",
                  3: "Spring", 4: "Spring", 5: "Spring",
                  6: "Summer", 7: "Summer", 8: "Summer",
                  9: "Fall", 10: "Fall", 11: "Fall"}
    df["Season"] = df["Month"].map(season_map)

    # Observation start hour -> useful for "time of day" analysis
    df["Start_Hour"] = df["Start_Time"].apply(
        lambda t: t.hour if pd.notna(t) and hasattr(t, "hour") else np.nan
    )

    # --- 4. Standardise text / categorical columns -------------------------
    for col in TEXT_COLUMNS:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype("string")
                .str.strip()
                .replace({"": pd.NA, "nan": pd.NA, "NaN": pd.NA})
            )

    # Common_Name / Scientific_Name -> Title Case for consistent grouping
    df["Common_Name"] = df["Common_Name"].str.title()
    df["Scientific_Name"] = df["Scientific_Name"].str.strip()

    # Sex: fill genuinely-missing sex as "Undetermined" (matches existing
    # category already used in the source data) instead of leaving NaN.
    df["Sex"] = df["Sex"].fillna("Undetermined")

    # --- 5. Boolean columns --------------------------------------------------
    for col in BOOL_LIKE_COLUMNS:
        df[col] = _to_bool(df[col])

    # --- 6. Numeric columns --------------------------------------------------
    for col in ["Temperature", "Humidity", "Visit", "AcceptedTSN", "TaxonCode"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- 7. Habitat / Location_Type normalisation --------------------------
    df["Location_Type"] = df["Location_Type"].str.title()

    # --- 8. Distance -> keep raw category but also derive an ordered code
    distance_order = {"<= 50 Meters": 0, "50 - 100 Meters": 1, "> 100 Meters": 2}
    df["Distance_Rank"] = df["Distance"].map(distance_order)

    # --- 9. Drop rows with no species identified (can't be used in
    #        species-level analysis) but KEEP a record of how many.
    missing_species = df["Common_Name"].isna().sum()

    # --- 10. Final column ordering (nice to have for CSV export) ----------
    ordered = CANONICAL_COLUMNS + [
        "Month", "Month_Name", "Day_of_Week", "Season", "Start_Hour",
        "Distance_Rank",
    ]
    ordered = [c for c in ordered if c in df.columns]
    remaining = [c for c in df.columns if c not in ordered]
    df = df[ordered + remaining]

    # Attach cleaning metadata as DataFrame attrs (handy for the dashboard
    # to display a "what did we clean" summary)
    df.attrs["duplicates_removed"] = dup_count
    df.attrs["rows_missing_species"] = int(missing_species)
    df.attrs["n_rows_final"] = len(df)

    return df


def load_and_clean(file_like, habitat_hint: str | None = None) -> pd.DataFrame:
    """Convenience wrapper: load a workbook and clean it in one call."""
    raw = load_workbook(file_like, habitat_hint=habitat_hint)
    return clean_bird_data(raw)


def combine_datasets(dfs: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate multiple already-cleaned DataFrames (e.g. Forest +
    Grassland) into one analysis-ready dataset."""
    dfs = [d for d in dfs if d is not None and not d.empty]
    if not dfs:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    combined = pd.concat(dfs, ignore_index=True, sort=False)
    return combined


def infer_habitat_from_filename(filename: str) -> str | None:
    """Best-effort guess of habitat type from an uploaded file's name."""
    name = filename.lower()
    if "forest" in name:
        return "Forest"
    if "grass" in name:
        return "Grassland"
    return None
