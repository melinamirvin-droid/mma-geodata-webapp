# mma_core.py — Web-safe, no-Tkinter, no-GDAL core downloader
from __future__ import annotations
import os
import json
import math
import time
from pathlib import Path
from typing import Iterable, List, Tuple, Optional, Dict

import duckdb
import pandas as pd
import requests
from shapely.geometry import mapping, Polygon, box
from pystac_client import Client

# Optional: geopandas is available (no fiona writes!)
import geopandas as gpd


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _bbox_polygon(w: float, s: float, e: float, n: float) -> Polygon:
    return box(w, s, e, n)  # WGS84 rectangle


def _write_geojson_fc(gdf: gpd.GeoDataFrame, out_path: Path) -> None:
    """
    Write a GeoJSON FeatureCollection WITHOUT using fiona/GDAL.
    """
    if gdf.empty:
        out_path.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
        return
    # Ensure WGS84
    if gdf.crs is None:
        gdf = gdf.set_crs(4326, allow_override=True)
    else:
        gdf = gdf.to_crs(4326)
    # Build FeatureCollection manually
    feats = []
    for _, row in gdf.iterrows():
        geom = None
        try:
            geom = mapping(row.geometry) if row.geometry is not None else None
        except Exception:
            geom = None
        props = {k: v for k, v in row.items() if k != "geometry"}
        feats.append({"type": "Feature", "geometry": geom, "properties": props})
    out = {"type": "FeatureCollection", "features": feats}
    out_path.write_text(json.dumps(out))


class MMADownloaderLite:
    """
    Minimal downloader intended for Streamlit Cloud.
    - Overture via DuckDB httpfs + spatial
    - OSM via OSMnx (returns GeoDataFrames; we export to .geojson using to_json)
    - Impact Observatory via STAC (download raw GeoTIFFs; no clipping/merging)
    No raster/GDAL operations; no Tkinter.
    """

    def __init__(
        self,
        west: float,
        south: float,
        east: float,
        north: float,
        major_roads_only: bool = False,
        io_years: Optional[List[int]] = None,
    ):
        self.w, self.s, self.e, self.n = west, south, east, north
        self.poly = _bbox_polygon(west, south, east, north)
        self.major_roads_only = major_roads_only
        self.io_years = io_years or [2023]

    # ------------------------------
    # OVERTURE (GeoParquet on S3)
    # ------------------------------
    def download_overture(self, out_dir: str) -> List[Path]:
        """
        Downloads Overture subsets (roads, buildings, water, land) intersecting the bbox,
        and writes them as GeoJSON (no GDAL).
        """
        base_out = Path(out_dir) / "Overture"
        _ensure_dir(base_out)

        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs;")
        con.execute("INSTALL spatial; LOAD spatial;")

        # Choose a stable release; update if you like
        release = "2024-09-24.0"  # works well with parquet layout
        urls = {
            # theme=transportation/type=segment — road segments
            "roads": f"https://overturemaps-us-west-2.s3.amazonaws.com/release/{release}/theme=transportation/type=segment/*.parquet",
            # theme=buildings/type=building
            "buildings": f"https://overturemaps-us-west-2.s3.amazonaws.com/release/{release}/theme=buildings/type=building/*.parquet",
            # theme=water/type=water
            "water": f"https://overturemaps-us-west-2.s3.amazonaws.com/release/{release}/theme=water/type=water/*.parquet",
            # theme=base/type=land
            "land": f"https://overturemaps-us-west-2.s3.amazonaws.com/release/{release}/theme=base/type=land/*.parquet",
        }

        bbox_sql = (
            f"ST_GeomFromText('POLYGON(({self.w} {self.s}, {self.e} {self.s}, "
            f"{self.e} {self.n}, {self.w} {self.n}, {self.w} {self.s}))', 4326)"
        )

        written: List[Path] = []

        # Roads
        where_major = ""
        if self.major_roads_only:
            # Overture segment has "class" and "subclass" fields
            where_major = " AND COALESCE(class,'') IN ('motorway','trunk','primary','secondary')"

        for layer, url in urls.items():
            try:
                q = f"""
                    SELECT
                        *, ST_AsWKB(geometry) AS geom_wkb
                    FROM read_parquet('{url}', hive_partitioning=1)
                    WHERE ST_Intersects(geometry, {bbox_sql})
                    {where_major if layer == 'roads' else ''}
                    LIMIT 200000  -- guard rails
                """
                df = con.execute(q).fetch_df()
                if df.empty:
                    # write empty
                    _write_geojson_fc(gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), base_out / f"{layer}.geojson")
                    continue

                # Build GeoDataFrame from WKB
                gdf = gpd.GeoDataFrame(
                    df.drop(columns=["geometry"], errors="ignore"),
                    geometry=gpd.GeoSeries.from_wkb(df["geom_wkb"], crs="EPSG:4326"),
                    crs="EPSG:4326",
                )

                _write_geojson_fc(gdf, base_out / f"{layer}.geojson")
                written.append(base_out / f"{layer}.geojson")
            except Exception as e:
                # still create an empty placeholder so zips are predictable
                _write_geojson_fc(gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), base_out / f"{layer}.geojson")
        con.close()
        return written

    # ------------------------------
    # OSM (via OSMnx)
    # ------------------------------
    def download_osm(self, out_dir: str) -> List[Path]:
        """
        Downloads OSM features (roads, buildings, water) for bbox.
        Exports as GeoJSON via GeoPandas .to_json().
        """
        import osmnx as ox

        base_out = Path(out_dir) / "OSM"
        _ensure_dir(base_out)

        north, south, east, west = self.n, self.s, self.e, self.w

        written: List[Path] = []

        # Roads
        try:
            if self.major_roads_only:
                tags = {"highway": ["motorway", "trunk", "primary", "secondary"]}
            else:
                tags = {"highway": True}
            gdf_roads = ox.features_from_bbox(north, south, east, west, tags)
            (base_out / "roads.geojson").write_text(gdf_roads.to_json())
            written.append(base_out / "roads.geojson")
        except Exception:
            (base_out / "roads.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": []}))

        # Buildings
        try:
            gdf_bldg = ox.features_from_bbox(north, south, east, west, {"building": True})
            (base_out / "buildings.geojson").write_text(gdf_bldg.to_json())
            written.append(base_out / "buildings.geojson")
        except Exception:
            (base_out / "buildings.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": []}))

        # Water (natural=water, waterway, coastline)
        try:
            tags_water = [{"natural": "water"}, {"water": True}, {"waterway": True}, {"landuse": "reservoir"}]
            gdf_list = []
            for t in tags_water:
                try:
                    gdf_list.append(ox.features_from_bbox(north, south, east, west, t))
                except Exception:
                    pass
            if gdf_list:
                gdf_water = pd.concat(gdf_list, ignore_index=True)
                # normalize to GeoDataFrame
                gdf_water = gpd.GeoDataFrame(gdf_water, geometry="geometry", crs=gdf_list[0].crs)
                (base_out / "water.geojson").write_text(gdf_water.to_json())
                written.append(base_out / "water.geojson")
            else:
                (base_out / "water.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": []}))
        except Exception:
            (base_out / "water.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": []}))

        return written

    # ------------------------------
    # Impact Observatory (STAC) — raw TIFFs
    # ------------------------------
    def download_impact_observatory(self, out_dir: str) -> List[Path]:
        """
        Downloads intersecting IO LULC TIFFs for selected years.
        We do not clip/merge; we just save the intersecting tiles.
        """
        base_out = Path(out_dir) / "IO"
        _ensure_dir(base_out)

        # API and bbox polygon in GeoJSON
        stac_url = "https://api.impactobservatory.com/stac-aws"
        client = Client.open(stac_url)

        bbox = [self.w, self.s, self.e, self.n]
        results: List[Path] = []

        # IO collections naming pattern (common: "io-lulc-YYYY")
        for year in self.io_years:
            try:
                coll_id = f"io-lulc-{year}"
                search = client.search(collections=[coll_id], bbox=bbox, max_items=100)
                items = list(search.get_items())
                if not items:
                    continue
                year_dir = base_out / str(year)
                _ensure_dir(year_dir)
                for it in items:
                    # prefer "data" asset; fallback to first asset
                    assets = it.get_assets()
                    href = None
                    if "data" in assets:
                        href = assets["data"].href
                    else:
                        # fallback to first asset
                        href = next(iter(assets.values())).href if assets else None
                    if not href:
                        continue
                    # stream download
                    fn = year_dir / f"{it.id}.tif"
                    with requests.get(href, stream=True, timeout=60) as r:
                        r.raise_for_status()
                        with open(fn, "wb") as f:
                            for chunk in r.iter_content(chunk_size=1 << 20):
                                if chunk:
                                    f.write(chunk)
                    results.append(fn)
            except Exception:
                pass
        return results
