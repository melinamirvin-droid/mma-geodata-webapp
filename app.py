# app.py — Streamlit Web Edition (no GDAL needed)

import os
import zipfile
import tempfile
from io import BytesIO
from pathlib import Path
from datetime import datetime

import streamlit as st

# -----------------------------
# Import your downloader class
# -----------------------------
from geodata_download_mma_v4 import GeoDataDownloaderPro  # same file in repo root


# -----------------------------
# Make the class "web safe"
# (GDAL/Rasterio/Fiona are not available on Streamlit Cloud)
# We gently stub any heavy functions if they exist.
# -----------------------------
def _web_stub(*args, **kwargs):
    # Called when a GDAL-only function is requested on web
    print("⛔ Skipping GDAL-dependent function in web deployment.")
    return None

# List of methods in your class that might rely on GDAL/Rasterio on desktop.
# We only patch ones that exist, so this is safe even if names differ.
for maybe_heavy in [
    "download_usgs_elevation",
    "merge_rasters",
    "clip_with_gdal",
    "clip_raster_to_bounds",
    "reproject_raster",
]:
    if hasattr(GeoDataDownloaderPro, maybe_heavy):
        setattr(GeoDataDownloaderPro, maybe_heavy, _web_stub)

# Also, if your class uses any flags to control raster work, try to disable them.
# We'll set attributes if present; otherwise it's a no-op.
setattr(GeoDataDownloaderPro, "allow_gdal", False)
setattr(GeoDataDownloaderPro, "use_rasterio", False)


# -----------------------------
# Streamlit page config / header
# -----------------------------
st.set_page_config(page_title="MMA Geodata Downloader (Web)", layout="wide")
st.title("🌍 MMA Geodata Downloader — Web App")
st.caption(
    "Web-safe edition that fetches live Overture, OSM, and Impact Observatory data. "
    "USGS elevation & raster clipping are disabled here (no GDAL in Streamlit Cloud)."
)

with st.expander("What’s this?"):
    st.write(
        """
        This web app bundles downloads into a ZIP you can save. It pulls **live** data:
        - **Overture** (buildings, roads, water, land) via DuckDB/httpfs
        - **OSM** (via OSMnx / Overpass)
        - **Impact Observatory** land cover (2019–2023) via STAC

        > If you need elevation (USGS 3DEP) and raster clipping/merging, use the **desktop app** build.
        """
    )


# -----------------------------
# Sidebar controls
# -----------------------------
st.sidebar.header("Project & AOI")

default_name = f"MMA_Project_{datetime.now().strftime('%Y%m%d_%H%M')}"
project_name = st.sidebar.text_input("Project name (used for the ZIP)", default_name)

st.sidebar.subheader("Area of Interest (WGS84 bounds)")
colW, colS = st.sidebar.columns(2)
colE, colN = st.sidebar.columns(2)

west = colW.number_input("West (min lon)", value=-77.20, step=0.01, format="%.6f")
south = colS.number_input("South (min lat)", value=38.80, step=0.01, format="%.6f")
east = colE.number_input("East (max lon)", value=-76.90, step=0.01, format="%.6f")
north = colN.number_input("North (max lat)", value=39.00, step=0.01, format="%.6f")

st.sidebar.caption("Tip: keep the box modest in size for faster downloads.")


st.sidebar.header("Sources")
use_overture = st.sidebar.checkbox("Overture (buildings, roads, land, water)", value=True)
use_osm = st.sidebar.checkbox("OpenStreetMap (OSM)", value=True)
use_io = st.sidebar.checkbox("Impact Observatory (2019–2023)", value=True)

st.sidebar.divider()
st.sidebar.header("Options")

# These toggles are passed to your class if it supports them; otherwise ignored.
major_roads_only = st.sidebar.checkbox("Major roads only (Overture/OSM)", value=False)
apply_tile_buffer = st.sidebar.checkbox("Apply 0.02° tile buffer (if implemented)", value=False)

io_years = st.sidebar.multiselect(
    "IO Years",
    options=[2019, 2020, 2021, 2022, 2023],
    default=[2023],
)

st.sidebar.divider()
st.sidebar.write("**Disabled in web build:** USGS Elevation 10m/30m, raster clipping/merging.")


# -----------------------------
# Main area
# -----------------------------
st.subheader("Download")
st.write(
    "Set your options in the sidebar, then click **Start Download**. "
    "When finished, a ZIP button will appear below."
)

# Validate bounds
bounds_ok = (west < east) and (south < north)
if not bounds_ok:
    st.error("AOI bounds are invalid: ensure West < East and South < North.")

start = st.button("Start Download", disabled=not bounds_ok)

# -----------------------------
# Run downloads
# -----------------------------
if start and bounds_ok:
    # Temporary working directory for this request
    tmp_root = Path(tempfile.mkdtemp(prefix="mma_web_"))
    out_dir = tmp_root / project_name
    out_dir.mkdir(parents=True, exist_ok=True)

    # Create the downloader
    dl = GeoDataDownloaderPro()

    # If your class expects to *set* AOI somewhere, try common patterns:
    # (We don't know your exact API; these are safe attempts.)
    for attr_name in ["aoi_bounds", "aoi_wsen", "bounds", "bbox"]:
        if hasattr(dl, attr_name):
            setattr(dl, attr_name, (west, south, east, north))
    # If it exposes a setter method, call it
    for setter in ["set_aoi_bounds", "set_bounds", "set_bbox"]:
        if hasattr(dl, setter) and callable(getattr(dl, setter)):
            try:
                getattr(dl, setter)(west, south, east, north)
            except Exception:
                pass

    # Pass optional flags if your class supports them
    if hasattr(dl, "major_roads_only"):
        setattr(dl, "major_roads_only", major_roads_only)
    if hasattr(dl, "tile_buffer_deg") and apply_tile_buffer:
        setattr(dl, "tile_buffer_deg", 0.02)
    if hasattr(dl, "io_years") and io_years:
        setattr(dl, "io_years", io_years)

    log = st.empty()
    progress = st.progress(0, text="Starting…")

    # Helper to run a source safely
    def _run_step(step_name, func, p):
        try:
            log.write(f"**{step_name}** …")
            func()
            progress.progress(p, text=f"{step_name} — done")
            st.success(f"✓ {step_name} complete")
        except Exception as e:
            progress.progress(p, text=f"{step_name} — skipped/failed")
            st.warning(f"⚠ {step_name} skipped: {e}")

    # Wrap calls so they write into the project folder
    def overture_call():
        # Expect your implementation to create its own "Overture" folder within out_dir
        dl.download_overture_data(str(out_dir))

    def osm_call():
        dl.download_osm_data(str(out_dir))

    def io_call():
        # If your method accepts years/bounds internally, it should read dl.io_years / dl.aoi
        dl.download_io_data(str(out_dir))

    # Execute selected sources (USGS intentionally omitted for web)
    step_total = sum([use_overture, use_osm, use_io]) or 1
    step_weight = 100 // step_total

    pct = 0
    if use_overture:
        _run_step("Overture", overture_call, pct := min(100, pct + step_weight))
    if use_osm:
        _run_step("OpenStreetMap (OSM)", osm_call, pct := min(100, pct + step_weight))
    if use_io:
        _run_step("Impact Observatory", io_call, pct := min(100, pct + step_weight))

    progress.progress(100, text="Packaging results…")

    # -----------------------------
    # Zip the outputs for download
    # -----------------------------
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(out_dir):
            for f in files:
                full = Path(root) / f
                rel = full.relative_to(out_dir)
                zf.write(full, arcname=str(rel))
    zip_buffer.seek(0)

    st.success("✅ All done! Download your results below.")
    st.download_button(
        "Download ZIP",
        data=zip_buffer,
        file_name=f"{project_name}.zip",
        mime="application/zip",
    )

    st.caption(f"Temp workspace: {tmp_root} (auto-cleared by the platform).")
