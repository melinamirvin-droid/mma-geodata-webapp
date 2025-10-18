import streamlit as st
import os
import zipfile
import tempfile
from pathlib import Path
from io import BytesIO
from geodata_download_mma_v4 import GeoDataDownloaderPro  # reuse your existing class

st.set_page_config(page_title="MMA Geodata Downloader", layout="wide")

st.title("🌍 MMA Geodata Downloader WebApp")

st.write(
    """
    Select your desired data sources and resolution, then click **Download**.
    This app fetches live data from Overture, OSM, Impact Observatory, and USGS.
    """
)

# Create a temporary directory for downloads
temp_dir = Path(tempfile.mkdtemp())

# UI for folder name
folder_name = st.text_input("Project Name", "My_Project")

# Checkboxes for sources
st.subheader("Select Data Sources:")
sources = {
    "Overture (Buildings, Roads, Water, Land)": st.checkbox("Overture"),
    "OpenStreetMap": st.checkbox("OSM"),
    "Impact Observatory (Land Cover)": st.checkbox("Impact Observatory"),
    "USGS Elevation (10m / 30m)": st.checkbox("USGS Elevation"),
}

# Elevation resolution option
resolution = st.radio("USGS Resolution", ["10m", "30m"], index=1)

# Download button
if st.button("Download Data"):
    st.info("Downloading selected data... this may take a few minutes.")
    downloader = GeoDataDownloaderPro()

    # Build main folder
    parent_dir = temp_dir / folder_name
    parent_dir.mkdir(exist_ok=True)

    # Call each method conditionally
    if sources["Overture (Buildings, Roads, Water, Land)"]:
        downloader.download_overture_data(str(parent_dir))
    if sources["OpenStreetMap"]:
        downloader.download_osm_data(str(parent_dir))
    if sources["Impact Observatory (Land Cover)"]:
        downloader.download_io_data(str(parent_dir))
    if sources["USGS Elevation (10m / 30m)"]:
        downloader.download_usgs_elevation(str(parent_dir), res=resolution)

    # Zip results
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(parent_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, parent_dir)
                zf.write(full_path, rel_path)
    zip_buffer.seek(0)

    st.success("✅ Download complete! Click below to save your data.")
    st.download_button(
        label="Download ZIP",
        data=zip_buffer,
        file_name=f"{folder_name}.zip",
        mime="application/zip",
    )
