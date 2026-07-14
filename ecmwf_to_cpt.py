"""
Convierte un NetCDF de pronóstico estacional ECMWF (SEAS5) al formato CPT (IRI).

Pipeline:
  1. Lee config_convert.yaml
  2. Abre el NetCDF estacional (dims: number, forecast_reference_time, forecastMonth,
     latitude, longitude)
  3. Promedia sobre miembros de ensamble (ignorando NaN: los años hindcast tienen menos
     miembros que los operativos y CDS rellena con NaN hasta el máximo)
  4. Si la variable es precipitación (tprate, en m/s), convierte a mm/día
  5. Promedia sobre los leadtime_month (mismo peso para cada uno)
  6. Reutiliza rotación de longitudes, bbox, regrillado y escritura CPT de netcdf_to_cpt.py

Uso:
  python ecmwf_to_cpt.py [config_convert.yaml]
"""

import sys
import xarray as xr

from netcdf_to_cpt import (
    MISSING, MONTH_ABBR, load_config, normalize_dims, detect_conversion,
    apply_bbox, regrid, write_cpt,
)
from pathlib import Path

# Variables que vienen como tasa en m/s y deben convertirse a mm/día
PRECIP_VARS = {"tprate"}
MM_PER_DAY_FACTOR = 1000.0 * 86400.0  # m/s -> mm/día


def lon_0360_to_180(da):
    """Rota longitudes de 0-360 a -180/180. A diferencia de ERA5, la grilla de SEAS5
    está centrada en celdas (0.5, 1.5, ...) por lo que -180/180 nunca son puntos de
    grilla exactos y no hace falta duplicar el borde."""
    da = da.assign_coords(longitude=((da["longitude"] + 180) % 360 - 180))
    return da.sortby("longitude")


def open_seasonal(path, cfg):
    ds = xr.open_dataset(path)
    da = normalize_dims(ds[cfg["variable"]["name"]])
    drop = [c for c in da.coords if c not in da.dims]
    return da.drop_vars(drop)


def build_output_path(cfg, da):
    out_dir = Path(cfg["output"]["dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    if cfg["output"]["filename"]:
        return out_dir / cfg["output"]["filename"]
    prefix = Path(cfg["input"]["seasonal"]).stem.split("_")[0]
    t0 = da["time"].values[0].astype("datetime64[M]").astype(object)
    t1 = da["time"].values[-1].astype("datetime64[M]").astype(object)
    month = MONTH_ABBR[int(str(t0)[5:7]) - 1]
    return out_dir / f"{prefix}_{month}_{str(t0)[:4]}_{str(t1)[:4]}.csv"


def main(config_path="config_convert_ecmwf.yaml"):
    cfg = load_config(config_path)
    var_name = cfg["variable"]["name"]

    print("Leyendo archivo estacional ...")
    da = open_seasonal(cfg["input"]["seasonal"], cfg)

    print("Promediando miembros de ensamble ...")
    da = da.mean(dim="number", skipna=True, keep_attrs=True)

    if var_name in PRECIP_VARS:
        units = da.attrs.get("units", "")
        print(f"  Convirtiendo precipitación ({units}) a mm/día ...")
        da = da * MM_PER_DAY_FACTOR
        cpt_units = "mm/day"
    else:
        factor, cpt_units = detect_conversion(da)
        print(f"  Convirtiendo unidades (factor={factor:.8f}) → {cpt_units} ...")
        da = da * factor

    print("Promediando leadtime months ...")
    da = da.mean(dim="forecastMonth", skipna=True)
    da = da.rename({"forecast_reference_time": "time"}).astype("float32")

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
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config_convert_ecmwf.yaml"
    main(config_path)
