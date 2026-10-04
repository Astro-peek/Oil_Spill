"""Prototype desktop GUI for the oil spill AI. Run from the project root: .venv/bin/python gui.py

Pick a Sentinel-1 VV/VH GeoTIFF, press Run, see the detected oil in red plus the measurements.
Everything heavy is done by oilspill.ai_pipeline; this file only collects inputs and shows results.
"""
from datetime import datetime
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
import rasterio
from PIL import Image

from oilspill.predict_scene import to_uint8

PREVIEW = 520


def preview_image(image_path, mask_path, size=PREVIEW):
    """VV band as greyscale with detected oil painted red, downsampled for display."""
    with rasterio.open(image_path) as src:
        vv = src.read(1, out_shape=(size, size), masked=True).astype(np.float32).filled(np.nan)
    with rasterio.open(mask_path) as src:
        oil = src.read(1, out_shape=(size, size)) == 1
    rgb = np.repeat(to_uint8(vv)[..., None], 3, axis=2)
    rgb[oil] = (0.4 * rgb[oil] + [153, 0, 0]).astype(np.uint8)
    return Image.fromarray(rgb)


def format_result(r, out):
    s = r['summary']
    lines = [f"Image: {s['image']}",
             f"Oil detected: {'YES' if s['detected'] else 'no'}"]
    v = r.get('scene_verification')
    if v:
        lines.append(f"Look-alike filter: score {v['score']:.3f} (cut-off {v['threshold']:.3f}) "
                     f"-> {'accepted' if v['accepted'] else 'REJECTED'}")
    if s['detected']:
        lines.append(f"Slicks: {s['n_slicks']}   total area: {s['total_area_km2']:.2f} km²")
    for inc in r['incidents']:
        g = inc['geometry']
        lines += ['', f"— Slick {inc['slick_id'] + 1} —",
                  f"  centre      {g['centroid_lat']:.4f} N, {g['centroid_lon']:.4f} E",
                  f"  area        {g['area_km2']:.2f} km²    perimeter {g['perimeter_km']:.1f} km",
                  f"  length      {g['major_axis_km']:.2f} km   width {g['minor_axis_km']:.2f} km",
                  f"  direction   {g['orientation_deg']:.0f}°    elongation {g['elongation']}"]
        if inc['drift_status'] != 'completed':
            lines.append(f"  drift       not run ({inc['drift_status']})")
            continue
        d = inc['drift']
        origins = d['origins']
        if d['timing_resolved_all_members']:
            o = origins[0]
            lines.append(f"  origin      {o['lat']:.4f} N, {o['lon']:.4f} E, ~{o['hours_back']:.1f} h before image")
        else:
            lines.append(f"  origin      time unresolved, {len(origins)} candidate points kept")
        if inc['attribution_status'] != 'completed':
            lines.append(f"  ships       not run ({inc['attribution_status']})")
        elif not inc['vessels']:
            lines.append('  ships       none near the origin')
        else:
            lines.append('  top ships (score 0-100, a lead, not proof):')
            for ship in inc['vessels'][:5]:
                lines.append(f"    {ship['score']:6.1f}  {ship['VesselName']} ({ship['MMSI']})  "
                             f"closest {ship['cpa_km']} km, AIS gap over origin: {ship['gap_covers_origin']}")
    lines += ['', f"Files saved in: {out}"]
    return '\n'.join(lines)


class App:
    def __init__(self, root):
        self.root, self.result, self.photo = root, None, None
        root.title('Oil Spill AI — prototype')
        form = ttk.Frame(root, padding=10)
        form.grid(row=0, column=0, sticky='ns')
        view = ttk.Frame(root, padding=10)
        view.grid(row=0, column=1, sticky='nsew')
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        self.vars = {}
        row = 0
        for key, label, types in [('image', 'SAR image (VV+VH .tif) *', [('GeoTIFF', '*.tif *.tiff')]),
                                  ('currents', 'Ocean currents (.nc)', [('NetCDF', '*.nc')]),
                                  ('wind', 'Wind (.nc)', [('NetCDF', '*.nc')]),
                                  ('ais', 'Ship AIS (.csv)', [('CSV', '*.csv')])]:
            ttk.Label(form, text=label).grid(row=row, column=0, columnspan=2, sticky='w', pady=(6, 0))
            self.vars[key] = tk.StringVar()
            ttk.Entry(form, textvariable=self.vars[key], width=34).grid(row=row+1, column=0, sticky='we')
            ttk.Button(form, text='…', width=3,
                       command=lambda k=key, t=types: self.vars[k].set(filedialog.askopenfilename(filetypes=t) or self.vars[k].get())
                       ).grid(row=row+1, column=1)
            row += 2

        ttk.Label(form, text='Image time, UTC (needed for drift)').grid(row=row, column=0, columnspan=2, sticky='w', pady=(6, 0))
        self.vars['when'] = tk.StringVar()
        ttk.Entry(form, textvariable=self.vars['when']).grid(row=row+1, column=0, columnspan=2, sticky='we')
        row += 2

        self.demo, self.verifier, self.cpu = tk.BooleanVar(), tk.BooleanVar(), tk.BooleanVar()
        for var, text in [(self.demo, 'Demo drift (synthetic currents)'),
                          (self.verifier, 'Look-alike filter (fewer false alarms)'),
                          (self.cpu, 'Use CPU only')]:
            ttk.Checkbutton(form, text=text, variable=var).grid(row=row, column=0, columnspan=2, sticky='w', pady=(6, 0))
            row += 1

        for key, label, default in [('threshold', 'Oil threshold (0-1)', '0.5'),
                                    ('min_area', 'Ignore slicks smaller than (km²)', '0.05'),
                                    ('hours', 'Drift hours (forward and back)', '24')]:
            ttk.Label(form, text=label).grid(row=row, column=0, sticky='w', pady=(6, 0))
            self.vars[key] = tk.StringVar(value=default)
            ttk.Entry(form, textvariable=self.vars[key], width=7).grid(row=row, column=1, pady=(6, 0))
            row += 1

        self.run_button = ttk.Button(form, text='Run analysis', command=self.start)
        self.run_button.grid(row=row, column=0, columnspan=2, sticky='we', pady=(14, 4))
        self.status = ttk.Label(form, text='Choose an image to start.', wraplength=260)
        self.status.grid(row=row+1, column=0, columnspan=2, sticky='w')

        self.canvas = tk.Label(view, text='Preview appears here\n(red = detected oil)',
                               width=PREVIEW // 8, height=PREVIEW // 18, relief='groove')
        self.canvas.grid(row=0, column=0, sticky='n')
        self.text = tk.Text(view, width=70, height=34, font=('monospace', 10))
        self.text.grid(row=0, column=1, sticky='nsew', padx=(10, 0))
        view.columnconfigure(1, weight=1)
        view.rowconfigure(0, weight=1)

    def start(self):
        v = {k: var.get().strip() for k, var in self.vars.items()}
        if not v['image']:
            messagebox.showwarning('Missing image', 'Choose a SAR image first.')
            return
        try:
            threshold, min_area, hours = float(v['threshold']), float(v['min_area']), float(v['hours'])
        except ValueError:
            messagebox.showerror('Invalid number', 'Threshold, area and hours must be numbers.')
            return
        if self.demo.get() and not v['when']:
            v['when'] = '2026-01-01T12:00:00Z'  # demo forcing is synthetic, so any clock time works
            self.vars['when'].set(v['when'])
        out = Path('runs/gui') / datetime.now().strftime('%Y%m%d-%H%M%S')
        self.run_button.state(['disabled'])
        self.status.config(text='Running… (first run loads the model)')
        args = (v, threshold, min_area, hours, out)
        threading.Thread(target=self.work, args=args, daemon=True).start()
        self.root.after(300, self.poll)

    def work(self, v, threshold, min_area, hours, out):
        # Imported here so the window opens instantly; torch takes a few seconds to load.
        from oilspill.ai_pipeline import AnalysisConfig, OilSpillAI
        try:
            config = AnalysisConfig(threshold=threshold, min_area_km2=min_area, forecast_hours=hours,
                                    hindcast_hours=hours,
                                    verifier='runs/scene_verifier/verifier.json' if self.verifier.get() else None)
            ai = OilSpillAI(config, device='cpu' if self.cpu.get() else None)
            result = ai.analyze(v['image'], out, v['when'] or None, v['currents'] or None,
                                v['wind'] or None, v['ais'] or None, self.demo.get())
            self.result = ('ok', result, out, v['image'])
        except Exception as exc:  # shown to the user instead of dying silently in a thread
            self.result = ('error', f'{type(exc).__name__}: {exc}', out, None)

    def poll(self):
        if self.result is None:
            self.root.after(300, self.poll)
            return
        kind, payload, out, image = self.result
        self.result = None
        self.run_button.state(['!disabled'])
        if kind == 'error':
            self.status.config(text='Failed.')
            messagebox.showerror('Analysis failed', payload)
            return
        self.status.config(text=f"Done. {payload['summary']['n_slicks']} slick(s) found.")
        from PIL import ImageTk
        self.photo = ImageTk.PhotoImage(preview_image(image, out/'mask.tif'))
        self.canvas.config(image=self.photo, text='', width=PREVIEW, height=PREVIEW)
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', format_result(payload, out))


if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
