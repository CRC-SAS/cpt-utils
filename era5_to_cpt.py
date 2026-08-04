"""
Convierte un NetCDF ERA5 al formato CPT (IRI).

Pipeline:
  1. Lee config_convert.yaml
  2. Abre NetCDF mensual (y opcionalmente horario, promediando a mensual)
  3. Concatena, detecta unidades y aplica conversión si corresponde
  4. Rota longitudes de 0-360 a -180-180
  5. Recorta al bounding box definido
  6. Regrilla a la resolución definida por interpolación bilineal
  7. Escribe el archivo CPT (TSV con cabeceras específicas)

Uso:
  python era5_to_cpt.py [config_convert.yaml]

  Sin argumento, usa config_convert_HG500.yaml por defecto.
"""

import sys
import numpy as np
import xarray as xr
import yaml
from pathlib import Path

MISSING = -999
G = 9.80665

# Unidades de entrada → (factor de conversión, unidad de salida CPT)
UNIT_CONVERSION = {
    "m**2 s**-2": (1.0 / G, "gpm"),
    "m2 s-2":     (1.0 / G, "gpm"),
    "j kg-1":     (1.0 / G, "gpm"),
    "gpm":        (1.0,     "gpm"),
    "m":          (1.0,     "gpm"),
    "m s**-1":    (1.0,     "m/s"),
    "m s-1":      (1.0,     "m/s"),
    "pa s**-1":   (1.0,     "Pa/s"),
    "pa s-1":     (1.0,     "Pa/s"),
    "k":          (1.0,     "K"),
}

MONTH_ABBR = ["jan", "feb", "mar", "apr", "may", "jun",
              "jul", "aug", "sep", "oct", "nov", "dec"]


def load_config(path="config_convert.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)


def normalize_dims(da):
    rename = {}
    for dim in da.dims:
        dl = dim.lower()
        if dl in ("lat", "latitude", "y"):
            rename[dim] = "latitude"
        elif dl in ("lon", "longitude", "x"):
            rename[dim] = "longitude"
        elif dl in ("time", "valid_time", "t"):
            rename[dim] = "time"
    return da.rename(rename)


def detect_conversion(da):
    units = da.attrs.get("units", "").lower().strip()
    result = UNIT_CONVERSION.get(units)
    if result is None:
        print(f"  Advertencia: unidades '{units}' no reconocidas, no se aplica conversión.")
        return 1.0, units
    factor, cpt_units = result
    return factor, cpt_units


def open_monthly(path, cfg):
    ds = xr.open_dataset(path)
    da = ds[cfg["variable"]["name"]]
    plevel = cfg["variable"]["pressure_level"]
    if plevel is not None:
        plevel_dim = next((d for d in da.dims if "pressure" in d.lower() or "level" in d.lower()), None)
        if plevel_dim:
            da = da.sel({plevel_dim: plevel}, drop=True)
    da = normalize_dims(da)
    drop = [c for c in da.coords if c not in da.dims]
    return da.drop_vars(drop)


def open_hourly(path, cfg):
    da = open_monthly(path, cfg)
    return da.resample(time="MS").mean()


def lon_0360_to_180(da):
    da = da.assign_coords(longitude=((da["longitude"] + 180) % 360 - 180))
    da = da.sortby("longitude")
    edge = da.sel(longitude=-180.0).assign_coords(longitude=180.0)
    return xr.concat([da, edge], dim="longitude")


def apply_bbox(da, bbox):
    lat_min = bbox.get("lat_min") or float(da["latitude"].min())
    lat_max = bbox.get("lat_max") or float(da["latitude"].max())
    lon_min = bbox.get("lon_min") or float(da["longitude"].min())
    lon_max = bbox.get("lon_max") or float(da["longitude"].max())
    return da.sel(latitude=slice(lat_max, lat_min), longitude=slice(lon_min, lon_max))


def regrid(da, resolution):
    lat_out = np.arange(float(da["latitude"].max()), float(da["latitude"].min()) - 1e-6, -resolution)
    lon_out = np.arange(float(da["longitude"].min()), float(da["longitude"].max()) + 1e-6, resolution)
    return da.interp(latitude=lat_out, longitude=lon_out, method="linear")


def value_format(da):
    """Determina el formato numérico según el rango de los datos."""
    finite = da.values[np.isfinite(da.values)]
    finite = finite[finite != MISSING]
    if len(finite) == 0:
        return "{:12.2f}"
    max_abs = float(np.abs(finite).max())
    if max_abs >= 100:
        return "{:12.2f}"
    elif max_abs >= 1:
        return "{:12.4f}"
    else:
        return "{:12.6f}"


def write_cpt(da, output_path, cfg, cpt_units):
    plevel   = cfg["variable"]["pressure_level"] or 0.0
    var_name = cfg["variable"]["name"]
    times    = da["time"].values
    lats     = da["latitude"].values
    lons     = da["longitude"].values
    nrow, ncol = len(lats), len(lons)
    time_strs = [np.datetime_as_string(t, unit="M") for t in times]
    fmt = value_format(da)

    with open(output_path, "w") as f:
        f.write("xmlns:cpt=http://iri.columbia.edu/CPT/v10/\n")
        f.write("cpt:nfields=1\n")
        f.write("cpt:T\t" + "\t".join(time_strs) + "\n")

        for i, ts in enumerate(time_strs):
            f.write(
                f"cpt:field={var_name}, cpt:P={plevel:.1f} mb, cpt:T={ts}, "
                f"cpt:nrow={nrow}, cpt:ncol={ncol}, "
                f"cpt:row=Y, cpt:col=X, cpt:units={cpt_units}, cpt:missing={MISSING}\n"
            )
            f.write("\t" + "\t".join(f"{lon:.1f}" for lon in lons) + "\n")

            data = da.isel(time=i).values
            for lat, row in zip(lats, data):
                f.write(f"{lat:.1f}\t" + "\t".join(fmt.format(v) for v in row) + "\n")


def build_output_path(cfg, da=None):
    out_dir = Path(cfg["output"]["dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    if cfg["output"]["filename"]:
        return out_dir / cfg["output"]["filename"]
    prefix = Path(cfg["input"]["monthly"]).stem.split("_")[0]
    if da is not None:
        t0    = da["time"].values[0].astype("datetime64[M]").astype(object)
        t1    = da["time"].values[-1].astype("datetime64[M]").astype(object)
        month = MONTH_ABBR[int(str(t0)[5:7]) - 1]
        return out_dir / f"{prefix}_{month}_{str(t0)[:4]}_{str(t1)[:4]}.csv"
    return out_dir / f"{prefix}.csv"


def main(config_path="config_convert.yaml"):
    cfg = load_config(config_path)

    print("Leyendo archivo mensual ...")
    da = open_monthly(cfg["input"]["monthly"], cfg)

    if cfg["input"].get("hourly"):
        print("Leyendo archivo horario y promediando a mensual ...")
        da_hourly = open_hourly(cfg["input"]["hourly"], cfg)
        print("Concatenando ...")
        da = xr.concat([da, da_hourly], dim="time").sortby("time")

    factor, cpt_units = detect_conversion(da)
    print(f"Convirtiendo unidades (factor={factor:.8f}) → {cpt_units} ...")
    da = (da * factor).astype("float32")

    print("Rotando longitudes a -180/180 ...")
    da = lon_0360_to_180(da)

    print("Aplicando bounding box ...")
    da = apply_bbox(da, cfg["grid"].get("bbox") or {})

    res = cfg["grid"]["resolution"]
    print(f"Regrillando a {res}° ...")
    da = regrid(da, res).fillna(MISSING)

    output_path = build_output_path(cfg, da)
    print(f"Escribiendo {output_path} ...")
    write_cpt(da, output_path, cfg, cpt_units)
    print("Listo.")


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config_convert_HG500.yaml"
    main(config_path)
