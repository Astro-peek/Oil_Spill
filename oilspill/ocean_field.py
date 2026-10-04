"""Strict regular-grid NetCDF current/wind sampling in metres per second.

Accepts common ERA5 and Copernicus coordinate names. Missing coverage is an error,
never silent zero velocity or repeated boundary time.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr
from scipy.interpolate import RegularGridInterpolator


class CoverageError(ValueError):
    pass


class NetCDFVectorField:
    def __init__(self, path, acquired_at, u_var='uo', v_var='vo'):
        with xr.open_dataset(path) as source:
            rename = {a: b for a, b in [('longitude', 'lon'), ('latitude', 'lat'), ('valid_time', 'time')]
                      if a in source.coords and b not in source.coords}
            ds = source.rename(rename)
            if u_var not in ds or v_var not in ds:
                raise ValueError(f'Missing velocity variables {u_var}/{v_var}')
            ds = ds[[u_var, v_var]]
            if 'depth' in ds.dims:
                ds = ds.sel(depth=0, method='nearest')
            for dim in list(ds.dims):
                if dim not in {'time', 'lat', 'lon'}:
                    if ds.sizes[dim] != 1:
                        raise ValueError(f'Unsupported vector field dimension: {dim}')
                    ds = ds.isel({dim: 0})
            for coord in ['time', 'lat', 'lon']:
                if coord not in ds.coords or ds[coord].ndim != 1 or ds.sizes[coord] < 2:
                    raise ValueError(f'{coord} must have at least two regular-grid coordinates')
                ds = ds.sortby(coord)
                if len(np.unique(ds[coord])) != ds.sizes[coord]:
                    raise ValueError(f'Duplicate {coord} coordinates')
            for var in [u_var, v_var]:
                units = str(ds[var].attrs.get('units', '')).lower().replace(' ', '')
                if units not in {'m/s', 'ms-1', 'ms**-1', 'ms^-1'}:
                    raise ValueError(f'{var} requires explicit m/s units; got {units!r}')
                if set(ds[var].dims) != {'time', 'lat', 'lon'}:
                    raise ValueError(f'{var} must vary over time, lat, lon')
            self.ds = ds.load()
        self.u_var, self.v_var = u_var, v_var
        self.t0 = pd.to_datetime(acquired_at, utc=True).tz_localize(None)
        self.path = str(Path(path))
        seconds = (self.ds.time.values.astype('datetime64[ns]') - np.datetime64(self.t0, 'ns')) / np.timedelta64(1, 's')
        self.grid = (seconds, self.ds.lat.values, self.ds.lon.values)
        self.interpolators = [RegularGridInterpolator(self.grid, self.ds[var].transpose('time', 'lat', 'lon').values,
                                                      bounds_error=True) for var in [u_var, v_var]]

    def __call__(self, lon, lat, t):
        lon, lat = np.broadcast_arrays(np.asarray(lon, float), np.asarray(lat, float))
        if float(self.ds.lon.min()) >= 0:
            lon = lon % 360
        else:
            lon = (lon + 180) % 360 - 180
        when = np.datetime64(self.t0 + pd.Timedelta(seconds=float(t)), 'ns')
        if when < self.ds.time.values.min() or when > self.ds.time.values.max():
            raise CoverageError(f'Velocity field does not cover {when}')
        if (np.any(lon < float(self.ds.lon.min())) or np.any(lon > float(self.ds.lon.max()))
                or np.any(lat < float(self.ds.lat.min())) or np.any(lat > float(self.ds.lat.max()))):
            raise CoverageError('Particle trajectory left the velocity field spatial coverage')
        points = np.column_stack([np.full(lon.size, float(t)), lat.ravel(), lon.ravel()])
        u, v = [interpolator(points).reshape(lon.shape) for interpolator in self.interpolators]
        if not np.isfinite(u).all() or not np.isfinite(v).all():
            raise CoverageError('Velocity interpolation encountered land or missing values')
        return u, v

    def provenance(self):
        return {'file': self.path, 'u_variable': self.u_var, 'v_variable': self.v_var,
                'units': 'm/s', 'time_start': str(self.ds.time.values.min()),
                'time_end': str(self.ds.time.values.max()),
                'bounds': [float(self.ds.lon.min()), float(self.ds.lat.min()),
                           float(self.ds.lon.max()), float(self.ds.lat.max())]}
