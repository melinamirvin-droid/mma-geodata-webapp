# geodata_download_mma_v3.02.0.py
"""
MMA Geodata Downloader – v3.02.0
Modern UI with military contractor styling
- Overture / OSM / Impact Observatory (2019–2023)
- USGS 3DEP Elevation (10 m, 30 m) via TNM API
- Project foldering: <Base>/<ProjectName>/{Overture, OSM, IO, Elevation}
- Geotiles: precise pick; grid overlay; translucent selection
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from tkintermapview import TkinterMapView
import threading, os, math, json, tempfile, shutil
from datetime import datetime

class GeoDataDownloaderPro:
    def __init__(self, root):
        self.root = root
        self.root.title("MMA Geodata Downloader v3.02.0")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 800)

        # Modern color palette
        self.colors = {
            'bg': '#f8f9fa', 'panel': '#ffffff', 'ink': '#1e293b',
            'muted': '#64748b', 'line': '#e2e8f0', 'accent': '#c9a961',
            'dark': '#0f172a', 'dark2': '#1e293b'
        }
        self.root.configure(bg=self.colors['bg'])

        # State Variables
        self.base_dir = tk.StringVar(value=os.path.expanduser("~/Downloads"))
        self.project_name = tk.StringVar(value="MMA_Geodata")
        self.vector_format = tk.StringVar(value="GPKG")
        self.west = tk.DoubleVar(value=-77.2)
        self.south = tk.DoubleVar(value=38.7)
        self.east = tk.DoubleVar(value=-76.6)
        self.north = tk.DoubleVar(value=39.1)
        
        self.src_overture = tk.BooleanVar(value=True)
        self.src_osm = tk.BooleanVar(value=True)
        self.src_impact = tk.BooleanVar(value=True)
        self.src_elev = tk.BooleanVar(value=True)
        self.elev_res = tk.StringVar(value="10m")
        
        self.ov_buildings = tk.BooleanVar(value=True)
        self.ov_roads = tk.BooleanVar(value=True)
        self.ov_places = tk.BooleanVar(value=False)
        self.ov_land = tk.BooleanVar(value=False)
        self.ov_water_poly = tk.BooleanVar(value=False)
        self.ov_water_line = tk.BooleanVar(value=False)
        self.ov_roads_major_only = tk.BooleanVar(value=False)
        
        self.osm_buildings = tk.BooleanVar(value=True)
        self.osm_roads = tk.BooleanVar(value=True)
        self.osm_places = tk.BooleanVar(value=False)
        self.osm_land = tk.BooleanVar(value=False)
        self.osm_water_poly = tk.BooleanVar(value=False)
        self.osm_water_line = tk.BooleanVar(value=False)
        self.osm_roads_major_only = tk.BooleanVar(value=False)
        
        self.use_geotiles = tk.BooleanVar(value=False)
        self.geotile_buffer = tk.BooleanVar(value=True)
        self.show_grid = tk.BooleanVar(value=True)
        self.selected_tiles = set()
        self.shift_down = False
        
        self.io_years = {y: tk.BooleanVar(value=(y == "2023")) for y in ["2023", "2022", "2021", "2020", "2019"]}
        
        self.map_widget = None
        self.aoi_polygon = None
        self.tile_overlays = {}
        self.grid_lines = []
        self.is_downloading = False
        
        self.build_ui()
        self.root.bind("<Shift_L>", lambda e: self._set_shift(True))
        self.root.bind("<KeyRelease-Shift_L>", lambda e: self._set_shift(False))
        self.root.bind("<Shift_R>", lambda e: self._set_shift(True))
        self.root.bind("<KeyRelease-Shift_R>", lambda e: self._set_shift(False))

    def build_ui(self):
        # Header
        header = tk.Frame(self.root, bg=self.colors['panel'], height=80)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="MMA GEODATA DOWNLOADER", font=("Rajdhani", 24, "bold"),
                bg=self.colors['panel'], fg=self.colors['ink']).pack(pady=(20, 0), padx=20, anchor=tk.W)
        tk.Label(header, text="Overture • OSM • Impact Observatory • USGS 3DEP", font=("Rajdhani", 11),
                bg=self.colors['panel'], fg=self.colors['muted']).pack(padx=20, anchor=tk.W)

        # Main content
        content = tk.Frame(self.root, bg=self.colors['bg'])
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        left = tk.Frame(content, bg=self.colors['bg'], width=420)
        left.pack(side=tk.LEFT, fill=tk.BOTH, padx=5)
        left.pack_propagate(False)
        self.build_left(left)
        
        right = tk.Frame(content, bg=self.colors['bg'])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        self.build_right(right)

    def build_left(self, parent):
        canvas = tk.Canvas(parent, bg=self.colors['bg'], highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=self.colors['bg'])
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)

        # Data Sources
        self.section(inner, "Data Source")
        src = tk.Frame(inner, bg=self.colors['panel'], relief=tk.FLAT)
        src.pack(fill=tk.X, pady=(0, 10), padx=2)
        for text, var in [("Impact Observatory", self.src_impact), ("OpenStreetMap (OSM)", self.src_osm),
                         ("Overture", self.src_overture), ("USGS SRTM Elevation", self.src_elev)]:
            ttk.Checkbutton(src, text=text, variable=var).pack(anchor=tk.W, padx=15, pady=3)

        # Output
        self.section(inner, "💾 Output Location")
        out = tk.Frame(inner, bg=self.colors['panel'], relief=tk.FLAT)
        out.pack(fill=tk.X, pady=(0, 10), padx=2)
        tk.Button(out, textvariable=self.base_dir, command=self.browse_base, bg="#f8f9fa",
                 fg=self.colors['muted'], font=("Courier New", 9), anchor=tk.W, relief=tk.FLAT).pack(
            fill=tk.X, padx=15, pady=10, ipady=5)
        fmt_f = tk.Frame(out, bg=self.colors['panel'])
        fmt_f.pack(fill=tk.X, padx=15, pady=(0, 15))
        for f in [("SHP", "SHP"), ("GPKG", "GPKG")]:
            tk.Radiobutton(fmt_f, text=f[0], variable=self.vector_format, value=f[1],
                          bg=self.colors['panel'], font=("Inter", 9, "bold")).pack(side=tk.LEFT, padx=5)

        # Download Options
        opt_head = tk.Frame(inner, bg=self.colors['panel'], relief=tk.FLAT)
        opt_head.pack(fill=tk.X, pady=(0, 2), padx=2)
        tk.Button(opt_head, text="Download Options ▼", command=self.toggle_opts, bg=self.colors['panel'],
                 fg=self.colors['ink'], font=("Rajdhani", 14, "bold"), relief=tk.FLAT, anchor=tk.W).pack(
            fill=tk.X, padx=15, pady=10)
        self.opts_frame = tk.Frame(inner, bg=self.colors['panel'])

        # Coordinates
        self.section(inner, "📍 AOI Coordinates")
        coord = tk.Frame(inner, bg=self.colors['panel'], relief=tk.FLAT)
        coord.pack(fill=tk.X, pady=(0, 10), padx=2)
        grid = tk.Frame(coord, bg=self.colors['panel'])
        grid.pack(fill=tk.X, padx=15, pady=10)
        for i, (lbl, var) in enumerate([("West", self.west), ("East", self.east),
                                        ("South", self.south), ("North", self.north)]):
            tk.Entry(grid, textvariable=var, font=("Courier New", 9), bg="#f8f9fa", relief=tk.FLAT).grid(
                row=i//2, column=i%2, padx=3, pady=3, sticky="ew")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        geo = tk.Frame(coord, bg=self.colors['panel'])
        geo.pack(fill=tk.X, padx=15, pady=(5, 10))
        tk.Checkbutton(geo, text="Download by Geotile?", variable=self.use_geotiles,
                      bg="#f8f9fa", font=("Inter", 8)).pack(anchor=tk.W, fill=tk.X, pady=2)
        tk.Checkbutton(geo, text="Buffer by 0.02 Degrees?", variable=self.geotile_buffer,
                      bg="#f8f9fa", font=("Inter", 8)).pack(anchor=tk.W, fill=tk.X, pady=2)
        self.tile_lbl = tk.Label(geo, text="0 tiles selected", font=("Inter", 8),
                                bg=self.colors['panel'], fg=self.colors['muted'])
        self.tile_lbl.pack(anchor=tk.W, pady=5)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    def section(self, parent, title):
        f = tk.Frame(parent, bg=self.colors['panel'], relief=tk.FLAT)
        f.pack(fill=tk.X, pady=(10, 2), padx=2)
        tk.Label(f, text=title, font=("Rajdhani", 14, "bold"), bg=self.colors['panel'],
                fg=self.colors['ink']).pack(anchor=tk.W, padx=15, pady=(15, 10))

    def toggle_opts(self):
        if self.opts_frame.winfo_ismapped():
            self.opts_frame.pack_forget()
        else:
            self.opts_frame.pack(fill=tk.X, pady=(0, 10), padx=2)
            self.populate_opts()

    def populate_opts(self):
        for w in self.opts_frame.winfo_children():
            w.destroy()
        tk.Label(self.opts_frame, text="ELEVATION RESOLUTION", font=("Inter", 8, "bold"),
                bg=self.colors['panel'], fg=self.colors['muted']).pack(anchor=tk.W, padx=15, pady=(10, 5))
        ef = tk.Frame(self.opts_frame, bg=self.colors['panel'])
        ef.pack(fill=tk.X, padx=15, pady=(0, 10))
        for r in ["10m", "30m"]:
            tk.Radiobutton(ef, text=r, variable=self.elev_res, value=r, bg=self.colors['panel'],
                          font=("Inter", 9)).pack(side=tk.LEFT, padx=5)
        tk.Label(self.opts_frame, text="OVERTURE LAYERS", font=("Inter", 8, "bold"),
                bg=self.colors['panel'], fg=self.colors['muted']).pack(anchor=tk.W, padx=15, pady=(10, 5))
        og = tk.Frame(self.opts_frame, bg=self.colors['panel'])
        og.pack(fill=tk.X, padx=15)
        for i, (l, v) in enumerate([("Buildings", self.ov_buildings), ("Roads", self.ov_roads),
                                    ("Places", self.ov_places), ("Land", self.ov_land),
                                    ("Water (poly)", self.ov_water_poly), ("Water (line)", self.ov_water_line)]):
            tk.Checkbutton(og, text=l, variable=v, bg="#f8f9fa", font=("Inter", 8)).grid(
                row=i//2, column=i%2, sticky=tk.W, padx=3, pady=2)
        tk.Checkbutton(self.opts_frame, text="Major roads only", variable=self.ov_roads_major_only,
                      bg="#f8f9fa", font=("Inter", 8)).pack(anchor=tk.W, padx=15, pady=2)
        tk.Label(self.opts_frame, text="OSM LAYERS", font=("Inter", 8, "bold"),
                bg=self.colors['panel'], fg=self.colors['muted']).pack(anchor=tk.W, padx=15, pady=(10, 5))
        osmg = tk.Frame(self.opts_frame, bg=self.colors['panel'])
        osmg.pack(fill=tk.X, padx=15)
        for i, (l, v) in enumerate([("Buildings", self.osm_buildings), ("Roads", self.osm_roads),
                                    ("Places", self.osm_places), ("Land", self.osm_land),
                                    ("Water (poly)", self.osm_water_poly), ("Water (line)", self.osm_water_line)]):
            tk.Checkbutton(osmg, text=l, variable=v, bg="#f8f9fa", font=("Inter", 8)).grid(
                row=i//2, column=i%2, sticky=tk.W, padx=3, pady=2)
        tk.Checkbutton(self.opts_frame, text="Major roads only", variable=self.osm_roads_major_only,
                      bg="#f8f9fa", font=("Inter", 8)).pack(anchor=tk.W, padx=15, pady=2)
        tk.Label(self.opts_frame, text="IMPACT OBSERVATORY YEARS", font=("Inter", 8, "bold"),
                bg=self.colors['panel'], fg=self.colors['muted']).pack(anchor=tk.W, padx=15, pady=(10, 5))
        yf = tk.Frame(self.opts_frame, bg=self.colors['panel'])
        yf.pack(fill=tk.X, padx=15, pady=(0, 15))
        for y, v in self.io_years.items():
            tk.Checkbutton(yf, text=y, variable=v, bg="#f8f9fa", font=("Inter", 8)).pack(side=tk.LEFT, padx=3)

    def build_right(self, parent):
        map_f = tk.Frame(parent, bg=self.colors['panel'], relief=tk.FLAT)
        map_f.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        tk.Label(map_f, text="AOI VIEWER", font=("Rajdhani", 16, "bold"), bg=self.colors['panel'],
                fg=self.colors['ink']).pack(anchor=tk.W, padx=15, pady=10)
        self.map_widget = TkinterMapView(map_f, corner_radius=0)
        self.map_widget.set_tile_server("https://a.tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.map_widget.add_left_click_map_command(self.on_map_click)
        self.map_widget.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        self.fit_map_to_aoi()
        
        btn_f = tk.Frame(parent, bg=self.colors['panel'], relief=tk.FLAT)
        btn_f.pack(fill=tk.X, pady=(0, 10))
        self.dl_btn = tk.Button(btn_f, text="DOWNLOAD DATA", command=self.start_download,
                               bg=self.colors['accent'], fg=self.colors['dark'],
                               font=("Rajdhani", 14, "bold"), relief=tk.FLAT, height=2)
        self.dl_btn.pack(fill=tk.X)
        
        log_f = tk.Frame(parent, bg=self.colors['panel'], relief=tk.FLAT)
        log_f.pack(fill=tk.BOTH, expand=True)
        tk.Label(log_f, text="Download Log", font=("Rajdhani", 14, "bold"), bg=self.colors['panel'],
                fg=self.colors['ink']).pack(anchor=tk.W, padx=15, pady=(15, 5))
        self.console = scrolledtext.ScrolledText(log_f, font=("Courier New", 9), bg="#0f172a",
                                                fg="#94a3b8", relief=tk.FLAT, wrap="word", height=8)
        self.console.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        self.log("Ready. Click tiles on map to select (hold Shift for rectangle selection).")

    def browse_base(self):
        d = filedialog.askdirectory(initialdir=self.base_dir.get())
        if d:
            self.base_dir.set(d)
            self.log(f"Output: {d}")

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.console.insert("end", f"[{ts}] {msg}\n")
        self.console.see("end")
        self.root.update_idletasks()

    def _root_out(self):
        root = os.path.join(self.base_dir.get(), self.project_name.get().strip() or "MMA_Geodata")
        for sub in ("Overture", "OSM", "IO", "Elevation"):
            os.makedirs(os.path.join(root, sub), exist_ok=True)
        return root

    def _subdir(self, key):
        return os.path.join(self._root_out(), key)

    def fit_map_to_aoi(self):
        lat_c = (self.south.get() + self.north.get()) / 2.0
        lon_c = (self.west.get() + self.east.get()) / 2.0
        self.map_widget.set_position(lat_c, lon_c)
        self.map_widget.set_zoom(8)
        self._draw_aoi_outline()

    def _draw_aoi_outline(self):
        if self.aoi_polygon:
            try:
                self.aoi_polygon.delete()
            except:
                pass
        ring = [(self.south.get(), self.west.get()), (self.south.get(), self.east.get()),
                (self.north.get(), self.east.get()), (self.north.get(), self.west.get())]
        try:
            self.aoi_polygon = self.map_widget.set_polygon(ring, outline_color=self.colors['accent'], border_width=2)
        except:
            pass

    def _set_shift(self, val):
        self.shift_down = val

    def on_map_click(self, lat_lon):
        lat, lon = float(lat_lon[0]), float(lat_lon[1])
        tile_lat = max(-90, min(89, math.floor(lat)))
        tile_lon = max(-180, min(179, math.floor(lon)))
        
        if self.shift_down and hasattr(self, "_last_tile"):
            lat0, lon0 = self._last_tile
            lat_min, lat_max = sorted([lat0, tile_lat])
            lon_min, lon_max = sorted([lon0, tile_lon])
            added = 0
            for la in range(lat_min, lat_max + 1):
                for lo in range(lon_min, lon_max + 1):
                    if (la, lo) not in self.selected_tiles:
                        self.selected_tiles.add((la, lo))
                        added += 1
                        self._draw_tile_highlight(la, lo)
            self.log(f"Selected {added} tiles. Total: {len(self.selected_tiles)}")
        else:
            key = (tile_lat, tile_lon)
            if key in self.selected_tiles:
                self.selected_tiles.remove(key)
                self._erase_tile_highlight(tile_lat, tile_lon)
            else:
                self.selected_tiles.add(key)
                self._draw_tile_highlight(tile_lat, tile_lon)
            self._last_tile = (tile_lat, tile_lon)
            self.log(f"Total: {len(self.selected_tiles)} tiles")
        
        self.tile_lbl.config(text=f"{len(self.selected_tiles)} tiles selected")

    def _draw_tile_highlight(self, la, lo):
        ring = [(la, lo), (la, lo + 1), (la + 1, lo + 1), (la + 1, lo)]
        try:
            p = self.map_widget.set_polygon(ring, fill_color="#c9a96155",
                                           outline_color=self.colors['accent'], border_width=2)
            self.tile_overlays[(la, lo)] = p
        except:
            pass

    def _erase_tile_highlight(self, la, lo):
        p = self.tile_overlays.pop((la, lo), None)
        if p:
            try:
                p.delete()
            except:
                pass

    @staticmethod
    def _tile_name(la_ll, lo_ll):
        return f"{'N' if la_ll >= 0 else 'S'}{abs(la_ll)}{'E' if lo_ll >= 0 else 'W'}{abs(lo_ll)}"

    @staticmethod
    def _tile_bbox(la_ll, lo_ll, buffer_deg=0.0):
        w = max(-180.0, lo_ll - buffer_deg)
        s = max(-90.0, la_ll - buffer_deg)
        e = min(180.0, lo_ll + 1 + buffer_deg)
        n = min(90.0, la_ll + 1 + buffer_deg)
        return (w, s, e, n)

    def start_download(self):
        if self.is_downloading:
            messagebox.showwarning("Working", "Download in progress")
            return
        if not (self.src_overture.get() or self.src_osm.get() or self.src_impact.get() or self.src_elev.get()):
            messagebox.showerror("Error", "Select at least one source")
            return
        
        self._root_out()
        self.is_downloading = True
        self.dl_btn.config(text="⏳ DOWNLOADING...")
        threading.Thread(target=self._run_downloads, daemon=True).start()

    def _run_downloads(self):
        try:
            self.log("\n" + "=" * 60)
            self.log("Starting downloads...")
            
            if self.use_geotiles.get() and self.selected_tiles:
                for (la, lo) in sorted(list(self.selected_tiles)):
                    tname = self._tile_name(la, lo)
                    buf = 0.02 if self.geotile_buffer.get() else 0.0
                    w, s, e, n = self._tile_bbox(la, lo, buffer_deg=buf)
                    self.log(f"\nTile {tname}: W{w:.4f} S{s:.4f} E{e:.4f} N{n:.4f}")
                    self._download_for_bbox(w, s, e, n, suffix=tname)
            else:
                w, s, e, n = self.west.get(), self.south.get(), self.east.get(), self.north.get()
                self._download_for_bbox(w, s, e, n, suffix=None)
            
            self.log("\n" + "=" * 60)
            self.log("✅ DOWNLOAD COMPLETE")
            messagebox.showinfo("Complete", f"Files saved:\n{self._root_out()}")
        except Exception as e:
            self.log(f"❌ Error: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            self.is_downloading = False
            self.dl_btn.config(text="DOWNLOAD DATA")

    def _download_for_bbox(self, w, s, e, n, suffix=None):
        if self.src_overture.get():
            self._dl_overture_bbox(w, s, e, n, suffix)
        if self.src_osm.get():
            self._dl_osm_bbox(w, s, e, n, suffix)
        if self.src_impact.get():
            self._dl_impact_bbox(w, s, e, n, suffix)
        if self.src_elev.get():
            self._dl_elevation_bbox(w, s, e, n, suffix)

    # Download implementations from original script
    def _dl_overture_bbox(self, w, s, e, n, suffix=None):
        import subprocess, sys
        try:
            import duckdb, geopandas as gpd
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "duckdb", "geopandas", "pyarrow", "-q"])
            import duckdb, geopandas as gpd
        from shapely.geometry import box

        fmt = self.vector_format.get()
        driver = "GPKG" if fmt == "GPKG" else "ESRI Shapefile"
        major = {"motorway", "trunk", "primary", "secondary"}
        bbox = {'xmin': w, 'ymin': s, 'xmax': e, 'ymax': n}
        aoi = box(w, s, e, n)

        def out_path(label):
            name = f"Overture_{label}"
            if suffix:
                name += f"_{suffix}"
            ext = 'gpkg' if driver == 'GPKG' else 'shp'
            return os.path.join(self._subdir("Overture"), f"{name}.{ext}")

        def save_gdf(gdf, label, facc=None, post=None):
            if gdf is None or len(gdf) == 0:
                self.log(f"  ⚠ No {label}")
                return
            try:
                gdf = gdf.set_geometry('geometry', crs='EPSG:4326')
            except:
                pass
            gdf = gdf.clip(aoi)
            if post:
                gdf = post(gdf)
            if gdf is None or len(gdf) == 0:
                self.log(f"  ⚠ No {label} after clip")
                return
            if facc:
                gdf["CODE"] = facc if isinstance(facc, str) else gdf.apply(facc, axis=1)
            gdf.to_file(out_path(label), driver=driver)
            self.log(f"  ✓ {label} ({len(gdf):,}) -> {os.path.basename(out_path(label))}")

        def run_query(theme, ftype):
            conn = duckdb.connect(':memory:')
            conn.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
            pq = os.path.join(tempfile.gettempdir(), f"tmp_{theme}_{ftype}_{os.getpid()}.parquet")
            q = f"""
            COPY (SELECT * FROM read_parquet('s3://overturemaps-us-west-2/release/2025-09-24.0/theme={theme}/type={ftype}/*', hive_partitioning=1)
              WHERE bbox.xmin <= {bbox['xmax']} AND bbox.xmax >= {bbox['xmin']}
                AND bbox.ymin <= {bbox['ymax']} AND bbox.ymax >= {bbox['ymin']}
            ) TO '{pq}' (FORMAT PARQUET);
            """
            conn.execute(q)
            conn.close()
            if not os.path.exists(pq):
                return None
            gdf = gpd.read_parquet(pq)
            try:
                os.remove(pq)
            except:
                pass
            return gdf

        if self.ov_buildings.get():
            self.log("Overture: Buildings...")
            g = run_query("buildings", "building")
            save_gdf(g, "Buildings", facc="AL015")

        if self.ov_roads.get():
            self.log("Overture: Roads...")
            g = run_query("transportation", "segment")

            def road_post(df):
                if self.ov_roads_major_only.get():
                    col = "class" if "class" in df.columns else ("subclass" if "subclass" in df.columns else None)
                    if col:
                        df = df[df[col].isin(major)]
                return df

            save_gdf(g, "Roads", facc="AP030", post=road_post)

        if self.ov_places.get():
            self.log("Overture: Places...")
            g = run_query("places", "place")
            save_gdf(g, "Places", facc="BH080")

        if self.ov_land.get():
            self.log("Overture: Land...")
            g = run_query("base", "land")
            save_gdf(g, "Land", facc="BH080")

        if self.ov_water_poly.get() or self.ov_water_line.get():
            self.log("Overture: Water...")
            g = run_query("base", "water")
            if g is not None and len(g):
                if self.ov_water_poly.get():
                    polys = g[g.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
                    def water_poly_code(row):
                        for c in ("subclass", "class", "name"):
                            if c in row and isinstance(row[c], str):
                                v = row[c].lower()
                                if any(k in v for k in ["ocean", "sea", "tidal", "coast"]):
                                    return "BA040"
                        return "BH080"
                    save_gdf(polys, "Water_polygons", facc=water_poly_code)
                if self.ov_water_line.get():
                    lines = g[g.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
                    save_gdf(lines, "Water_lines", facc="BH140")

    def _dl_osm_bbox(self, w, s, e, n, suffix=None):
        import subprocess, sys
        try:
            import osmnx as ox
            import geopandas as gpd
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "osmnx", "geopandas", "-q"])
            import osmnx as ox
            import geopandas as gpd

        fmt = self.vector_format.get()
        driver = "GPKG" if fmt == "GPKG" else "ESRI Shapefile"
        bbox = (s, n, w, e)
        major = {"motorway", "trunk", "primary", "secondary"}

        def out_path(label):
            name = f"OSM_{label}"
            if suffix:
                name += f"_{suffix}"
            ext = 'gpkg' if driver == 'GPKG' else 'shp'
            return os.path.join(self._subdir("OSM"), f"{name}.{ext}")

        def save(df, label, code):
            if df is None or df.empty:
                self.log(f"  ⚠ No {label}")
                return
            try:
                if df.crs is None:
                    df.set_crs(epsg=4326, inplace=True)
                else:
                    df = df.to_crs(4326)
            except:
                pass
            df["CODE"] = code if isinstance(code, str) else df.apply(code, axis=1)
            df.to_file(out_path(label), driver=driver)
            self.log(f"  ✓ {label} ({len(df):,}) -> {os.path.basename(out_path(label))}")

        if self.osm_buildings.get():
            self.log("OSM: Buildings...")
            try:
                b = ox.features_from_bbox(*bbox, tags={"building": True})
                b = b[b.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
                save(b, "Buildings", "AL015")
            except Exception as e:
                self.log(f"  ❌ Buildings failed: {e}")

        if self.osm_roads.get():
            self.log("OSM: Roads...")
            try:
                r = ox.features_from_bbox(*bbox, tags={"highway": True})
                r = r[r.geometry.geom_type.isin(["LineString", "MultiLineString"])]
                if self.osm_roads_major_only.get() and not r.empty:
                    def is_major(v):
                        if isinstance(v, list):
                            return any(x in major for x in v)
                        return v in major
                    if "highway" in r.columns:
                        r = r[r["highway"].apply(is_major)]
                save(r, "Roads", "AP030")
            except Exception as e:
                self.log(f"  ❌ Roads failed: {e}")

        if self.osm_places.get():
            self.log("OSM: Places...")
            try:
                pois = ox.features_from_bbox(*bbox, tags={"amenity": True, "shop": True, "tourism": True})
                save(pois, "Places", "BH080")
            except Exception as e:
                self.log(f"  ❌ Places failed: {e}")

        if self.osm_land.get():
            self.log("OSM: Land...")
            try:
                land = ox.features_from_bbox(*bbox, tags={"landuse": True})
                land = land[land.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
                save(land, "Land", "BH080")
            except Exception as e:
                self.log(f"  ❌ Land failed: {e}")

        if self.osm_water_poly.get():
            self.log("OSM: Water polygons...")
            try:
                wp = ox.features_from_bbox(*bbox, tags={"natural": "water"})
                wp = wp[wp.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
                def wp_code(row):
                    for c in ("water", "waterway", "name"):
                        if c in row and isinstance(row[c], str):
                            v = row[c].lower()
                            if any(k in v for k in ["ocean", "sea", "tidal", "coast"]):
                                return "BA040"
                            if any(k in v for k in ["lake", "pond", "reservoir"]):
                                return "BH080"
                    return "BH080"
                save(wp, "Water_polygons", wp_code)
            except Exception as e:
                self.log(f"  ❌ Water polygons failed: {e}")

        if self.osm_water_line.get():
            self.log("OSM: Water lines...")
            try:
                wl = ox.features_from_bbox(*bbox, tags={"waterway": True})
                wl = wl[wl.geometry.geom_type.isin(["LineString", "MultiLineString"])]
                save(wl, "Water_lines", "BH140")
            except Exception as e:
                self.log(f"  ❌ Water lines failed: {e}")

    def _dl_impact_bbox(self, w, s, e, n, suffix=None):
        import subprocess, sys
        try:
            from pystac_client import Client
            import rasterio
            from rasterio.merge import merge
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pystac-client", "rasterio", "-q"])
            from pystac_client import Client
            import rasterio
            from rasterio.merge import merge

        bbox = [w, s, e, n]
        years = [y for y, v in self.io_years.items() if v.get()]
        self.log(f"Impact bbox: {bbox}; years: {', '.join(years)}")
        catalog = Client.open("https://api.impactobservatory.com/stac-aws")

        for year in years:
            try:
                self.log(f"Impact: {year}...")
                search = catalog.search(collections=["io-10m-annual-lulc"], bbox=bbox, datetime=f"{year}-01-01/{year}-12-31")
                items = list(search.items())
                if not items:
                    self.log(f"  ⚠ No tiles for {year}")
                    continue

                import rasterio
                tmpdir = tempfile.mkdtemp(prefix="io_", dir=tempfile.gettempdir())
                tiles = []
                for i, it in enumerate(items):
                    asset = None
                    for _, v in it.assets.items():
                        if hasattr(v, "href"):
                            asset = v
                            break
                    if not asset:
                        continue
                    tpath = os.path.join(tmpdir, f"t_{i}.tif")
                    with rasterio.open(asset.href) as src:
                        win = rasterio.windows.from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], transform=src.transform)
                        data = src.read(1, window=win)
                        if data.size == 0:
                            continue
                        prof = src.profile.copy()
                        prof.update({
                            'height': data.shape[0], 'width': data.shape[1],
                            'transform': rasterio.windows.transform(win, src.transform),
                            'compress': 'lzw'
                        })
                        with rasterio.open(tpath, 'w', **prof) as dst:
                            dst.write(data, 1)
                    tiles.append(tpath)

                if not tiles:
                    self.log(f"  ⚠ No data after clip for {year}")
                    shutil.rmtree(tmpdir, ignore_errors=True)
                    continue

                name = f"LULC_{year}"
                if suffix:
                    name += f"_{suffix}"
                out = os.path.join(self._subdir("IO"), f"{name}.tif")

                if len(tiles) == 1:
                    shutil.move(tiles[0], out)
                else:
                    srcs = [rasterio.open(t) for t in tiles]
                    mos, tr = merge(srcs)
                    meta = srcs[0].meta.copy()
                    for s_ in srcs:
                        s_.close()
                    meta.update({'height': mos.shape[1], 'width': mos.shape[2], 'transform': tr, 'compress': 'lzw'})
                    with rasterio.open(out, 'w', **meta) as dst:
                        dst.write(mos)
                shutil.rmtree(tmpdir, ignore_errors=True)
                self.log(f"  ✓ Saved {os.path.basename(out)}")
            except Exception as e:
                self.log(f"  ❌ Impact {year} failed: {e}")

    def _dl_elevation_bbox(self, w, s, e, n, suffix=None):
        import subprocess, sys
        try:
            import requests, rasterio
            from rasterio.merge import merge
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "rasterio", "-q"])
            import requests
            import rasterio
            from rasterio.merge import merge

        want = "1/3 arc-second" if self.elev_res.get() == "10m" else "1 arc-second"
        datasets = "3DEPElevation,Elevation"
        url = "https://tnmaccess.nationalmap.gov/api/v1/products"
        params = {
            "datasets": datasets,
            "bbox": f"{w},{s},{e},{n}",
            "prodFormats": "GeoTIFF",
            "max": 100
        }
        self.log(f"USGS 3DEP: {self.elev_res.get()}...")

        try:
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            items = r.json().get("items", [])
            
            def matches(it):
                txt = " ".join([str(it.get(k, "")) for k in ("title", "summary", "type")]).lower()
                if "1/3 arc-second" in txt and want == "1/3 arc-second":
                    return True
                if "1 arc-second" in txt and want == "1 arc-second":
                    return True
                return "GeoTIFF" in " ".join(it.get("formats", []))
            
            items = [it for it in items if matches(it)]
            if not items:
                self.log("  ⚠ No elevation tiles")
                return

            tmpdir = tempfile.mkdtemp(prefix="elev_", dir=tempfile.gettempdir())
            tifs = []
            for i, it in enumerate(items):
                link = None
                for l in [it.get("downloadURL", "")] + (it.get("urls", []) or []):
                    if isinstance(l, str) and l.lower().endswith(".tif"):
                        link = l
                        break
                if not link:
                    continue
                tpath = os.path.join(tmpdir, f"elev_{i}.tif")

                with requests.get(link, stream=True, timeout=120) as rr:
                    rr.raise_for_status()
                    with open(tpath, "wb") as f:
                        for chunk in rr.iter_content(1 << 20):
                            if chunk:
                                f.write(chunk)

                try:
                    with rasterio.open(tpath) as src:
                        win = rasterio.windows.from_bounds(w, s, e, n, transform=src.transform)
                        data = src.read(1, window=win, boundless=True, fill_value=src.nodata or -9999)
                        if data.size == 0:
                            continue
                        prof = src.profile.copy()
                        prof.update({
                            'height': data.shape[0], 'width': data.shape[1],
                            'transform': rasterio.windows.transform(win, src.transform),
                            'compress': 'lzw'
                        })
                        ctif = os.path.join(tmpdir, f"clip_{i}.tif")
                        with rasterio.open(ctif, 'w', **prof) as dst:
                            dst.write(data, 1)
                        tifs.append(ctif)
                except:
                    tifs.append(tpath)

            if not tifs:
                self.log("  ⚠ No elevation data after clip")
                shutil.rmtree(tmpdir, ignore_errors=True)
                return

            name = f"USGS_3DEP_{self.elev_res.get()}"
            if suffix:
                name += f"_{suffix}"
            out = os.path.join(self._subdir("Elevation"), f"{name}.tif")

            if len(tifs) == 1:
                shutil.move(tifs[0], out)
            else:
                srcs = [rasterio.open(t) for t in tifs]
                mos, tr = merge(srcs)
                meta = srcs[0].meta.copy()
                for s_ in srcs:
                    s_.close()
                meta.update({'height': mos.shape[1], 'width': mos.shape[2], 'transform': tr, 'compress': 'lzw'})
                with rasterio.open(out, 'w', **meta) as dst:
                    dst.write(mos)

            shutil.rmtree(tmpdir, ignore_errors=True)
            self.log(f"  ✓ Saved {os.path.basename(out)}")
        except Exception as e:
            self.log(f"  ❌ Elevation failed: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = GeoDataDownloaderPro(root)
    root.mainloop()