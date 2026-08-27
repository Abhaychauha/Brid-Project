# Bird Species Observation Analysis

Two **separate deliverables**, sharing one cleaning pipeline:

| Deliverable | File | What it's for |
|---|---|---|
| **1. EDA** | `notebooks/Bird_Species_EDA.ipynb` | Offline, narrative exploratory analysis with charts + written insights on the Forest/Grassland dataset. Already executed — open it and the charts are there. |
| **2. Streamlit Dashboard** | `app.py` | Interactive web app. **Upload any bird-monitoring workbook(s)** (Forest, Grassland, or a similarly-structured file) and it cleans the data live and builds the full dashboard — filters, KPIs, temporal/spatial/species/environmental/conservation/observer views, and a data download. |

Both use the same tested cleaning logic in `utils/data_processing.py`, so the numbers you see in the notebook and in the dashboard always agree.

## Project structure

```
bird_project/
├── app.py                          # Streamlit dashboard (deliverable 2)
├── requirements.txt
├── utils/
│   └── data_processing.py          # shared cleaning pipeline (loaders + clean_bird_data)
├── notebooks/
│   └── Bird_Species_EDA.ipynb      # EDA notebook (deliverable 1), already executed
└── data/
    ├── raw/                        # original workbooks (bundled as demo data for the app)
    │   ├── Bird_Monitoring_Data_FOREST.XLSX
    │   └── Bird_Monitoring_Data_GRASSLAND.XLSX
    └── cleaned_bird_observations.csv   # combined, cleaned dataset (for SQL loading / re-use)
```

## Running the dashboard

```bash
pip install -r requirements.txt
streamlit run app.py
```

- If you don't upload anything, the app shows the bundled Forest + Grassland demo data so it's never empty.
- Upload the **Forest** and/or **Grassland** workbook (or both, or a new one next season) via the sidebar — the app re-cleans and rebuilds the whole dashboard automatically. Multi-sheet workbooks (one sheet per park) are combined automatically.
- Every chart respects the sidebar filters (habitat, park, year, season, species, observer, watchlist-only).
- The "Data Explorer" tab lets you preview and download the filtered, cleaned data as CSV.

## Running the EDA notebook

```bash
cd notebooks
jupyter notebook Bird_Species_EDA.ipynb
```

It's already been executed end-to-end so you can also just open it and read the outputs without re-running anything, or re-run it (`Kernel → Restart & Run All`) to regenerate everything from the raw files in `data/raw/`.

## Data cleaning summary (applied by `utils/data_processing.py`)

- **Combines** all per-park sheets in each workbook into one long table.
- **Harmonises schema**: Forest's `NPSTaxonCode` and Grassland's `TaxonCode` are unified into one `TaxonCode` column; missing optional columns (e.g. `Site_Name`, `Previously_Obs`) are filled with `NaN` so the two habitats can be combined safely.
- **Removes exact duplicate rows** (the Grassland file had 1,705 of them — a data-entry artifact).
- **Parses dates/times** and derives `Month`, `Month_Name`, `Season`, `Day_of_Week`, `Start_Hour` for temporal analysis.
- **Standardises text** (trims whitespace, consistent casing on species/category fields).
- **Fills genuinely-missing `Sex`** as `"Undetermined"` (matches the label already used for birds detected by sound, not sight).
- **Coerces boolean flags** (`Flyover_Observed`, `PIF_Watchlist_Status`, `Regional_Stewardship_Status`, etc.) to true booleans.

## A note on "spatial analysis"

The source data does **not** include latitude/longitude — only `Admin_Unit_Code` (park), `Site_Name`, and `Plot_Name`. So both the notebook and the dashboard treat "spatial" analysis as grouping by park/plot (bar charts, treemaps) rather than a literal map. If you have coordinates for these plots, they can be added to `utils/data_processing.py` and a real map (e.g. `st.map` or `plotly` choropleth/scatter-mapbox) can be dropped into the "Spatial" tab of `app.py`.

## Loading into SQL (per project brief)

`data/cleaned_bird_observations.csv` is the single, cleaned, combined dataset — load it into any SQL database (e.g. `sqlite3`, Postgres) with a one-liner:

```python
import sqlite3, pandas as pd
df = pd.read_csv("data/cleaned_bird_observations.csv")
conn = sqlite3.connect("bird_observations.db")
df.to_sql("bird_observations", conn, if_exists="replace", index=False)
```
