# app.py — Streamlit Web App (uses MMA Lite core, no Tkinter/GDAL)

import os
import zipfile
import tempfile
from io import BytesIO
from pathlib import Path
from datetime import datetime

import streamlit as st
from mma_core import MMADownloaderLite  # <-- web-safe core

st.set_page_config(page_title="MMA Geodata Downloader (Web)", layout="wide")

st.title("🌍 MMA Geodata Downloader — Web App")
st.caption(
    "Web-safe edition for Overture, OSM, and Impact Observatory downloads. "
    "USGS elevation & raster clipping are desktop-only features."
)

with st.expander("About"):
    st.markdown(
        """
        **What this app does**
        - Pulls **live** data from:
          - Overture (roads, buildings, water, land)
          - OpenStreetMap (roads, buildings, water)
          - Impact Observatory (2019–2023 LULC) — raw tiles
        - Bundles results into a ZIP to download.

        **What this app skips (web limitations)**
        - No GDAL/Fiona/Rasterio (so no USGS elevation, no raster clipping/merging).
        - Outputs are **GeoJSON** (vector) and **GeoTIFF** (IO tiles) without post-processing.
        """
    )

# Sidebar — project + AOI
st.sidebar.header("Project")
default_name = f"MMA_Project_{datetime.now().strftime('%Y%m%d_%H%M')}"
project_name = st.sidebar.text_input("Project name (used for the ZIP)", default_name)

st.sidebar.header("AOI — WGS84 Bounds")
w = st.sidebar.number_input("West (min lon)", value=-77.20, step=0.01, format="%.6f")
s = st.sidebar.number_input("South (min lat)", value=38.80, step=0.01, format="%.6f")
e = st.sidebar.number_input("East (max lon)", value=-76.90, step=0.01, format="%.6f")
n = st.sidebar.number_input("North (max lat)", value=39.00, step=0.01, format="%.6f")
if not (w < e and s < n):
    st.sidebar.error("Bounds invalid: ensure West < East and South < North.")

st.sidebar.header("Sources")
use_overture = st.sidebar.checkbox("Overture (roads, buildings, water, land)", value=True)
use_osm = st.sidebar.checkbox("OpenStreetMap (roads, buildings, water)", value=True)
use_io = st.sidebar.checkbox("Impact Observatory (LULC 2019–2023)", value=True)

st.sidebar.header("Options")
major_roads_only = st.sidebar.checkbox("Major roads only", value=False)
io_years = st.sidebar.multiselect("IO years", [2019, 2020, 2021, 2022, 2023], default=[2023])

st.subheader("Run")
start = st.button("Start Download", disabled=not (w < e and s < n))

if start:
    tmp_root = Path(tempfile.mkdtemp(prefix="mma_web_"))
    out_dir = tmp_root / project_name
    out_dir.mkdir(parents=True, exist_ok=True)

    dl = MMADownloaderLite(
        west=w, south=s, east=e, north=n,
        major_roads_only=major_roads_only,
        io_years=io_years or [2023],
    )

    progress = st.progress(0, text="Starting…")
    logs = st.empty()

    def step(msg, pct, fn):
        try:
            logs.write(f"**{msg}**…")
            fn()
            progress.progress(pct, text=f"{msg} — done")
            st.success(f"✓ {msg}")
        except Exception as ex:
            progress.progress(pct, text=f"{msg} — skipped")
            st.warning(f"⚠ {msg} skipped: {ex}")

    pct = 0
    parts = sum([use_overture, use_osm, use_io]) or 1
    step_w = 100 // parts

    if use_overture:
        step("Overture", pct := min(100, pct + step_w), lambda: dl.download_overture(str(out_dir)))
    if use_osm:
        step("OpenStreetMap", pct := min(100, pct + step_w), lambda: dl.download_osm(str(out_dir)))
    if use_io:
        step("Impact Observatory", pct := min(100, pct + step_w), lambda: dl.download_impact_observatory(str(out_dir)))

    progress.progress(100, text="Packaging ZIP…")

    # Package to ZIP
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(out_dir):
            for f in files:
                p = Path(root) / f
                rel = p.relative_to(out_dir)
                zf.write(p, arcname=str(rel))
    buf.seek(0)

    st.success("✅ Done! Download your data below.")
    st.download_button(
        "Download ZIP",
        data=buf,
        file_name=f"{project_name}.zip",
        mime="application/zip",
    )
