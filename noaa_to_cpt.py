"""
Convierte datos de SST (NOAA ERSST v5 + OISST v2.1) al formato CPT (IRI).

Pipeline:
  1. Lee config_convert_noaa.yaml
  2. Para cada año del período, obtiene el valor del mes objetivo:
     - año <= ersst_last_year: ERSST v5 (un archivo por año-mes, grilla 2°)
     - año con el mes objetivo ya completo en el archivo mensual OISST: OISST mensual
     - año en curso con el mes objetivo incompleto: promedio de los diarios OISST
       disponibles (sin mínimo de días exigido)
  3. Cada año se rota (0-360 → -180/180) y regrilla a una malla común alineada a
     polos/bordes ANTES de concatenar entre años, porque ERSST (2°) y OISST (0.25°)
     tienen grillas nativas distintas
  4. Escribe el archivo CPT (unidades Celsius_scale, sin nivel de presión)

Reutiliza de era5_to_cpt.py: carga de config, normalización de dims, bounding box.
Reutiliza de ecmwf_to_cpt.py: regrid_edge_aligned() y su lon_0360_to_180() y
format_grid(), porque ninguna de las tres fuentes NOAA tiene puntos de grilla exactos
en los bordes/polos (igual que SEAS5).

Uso:
  python noaa_to_cpt.py [config_convert_noaa.yaml]
"""

import sys
from pathlib import Path

import numpy as np
import xarray as xr

from era5_to_cpt import MISSING, MONTH_ABBR, load_config, normalize_dims, apply_bbox
from ecmwf_to_cpt import regrid_edge_aligned, format_grid, lon_0360_to_180

CPT_UNITS = "Celsius_scale"


def _drop_extra_coords(da):
    drop = [c for c in da.coords if c not in da.dims]
    return da.drop_vars(drop)


def open_ersst(cfg, year, month):
    path = Path(cfg["input"]["ersst_dir"]) / f"ersst.v5.{year}{month}.nc"
    ds = xr.open_dataset(path)
    da = ds[cfg["variable"]["name"]]
    if "lev" in da.dims:
        da = da.isel(lev=0, drop=True)
    da = _drop_extra_coords(normalize_dims(da))
    return da.isel(time=0, drop=True)


def open_oisst_monthly(cfg, year, month):
    ds = xr.open_dataset(cfg["input"]["oisst_monthly"])
    da = _drop_extra_coords(normalize_dims(ds[cfg["variable"]["name"]]))
    target = np.datetime64(f"{year}-{month}-01")
    if target not in da["time"].values:
        return None
    return da.sel(time=target, drop=True)


def open_oisst_daily_mean(cfg, year, month):
    ds = xr.open_dataset(cfg["input"]["oisst_daily"])
    da = _drop_extra_coords(normalize_dims(ds[cfg["variable"]["name"]]))
    days = da.sel(time=f"{year}-{month}")
    return days.mean(dim="time", skipna=True)


def _add_dateline_duplicate(da, bbox):
    """SST_original.csv (la referencia de la experta) usa 361 columnas de longitud
    (-180 a 180 inclusive, con el meridiano duplicado en ambos extremos), a
    diferencia de la referencia de ECMWF que regrid_edge_aligned() replica por
    defecto (360 columnas, sin duplicado). Se agrega acá, solo para SST."""
    lon_min = bbox.get("lon_min") or -180.0
    lon_max = bbox.get("lon_max") or 180.0
    if lon_min > -180.0 or lon_max < 180.0:
        return da
    edge = da.sel(longitude=da["longitude"].min()).assign_coords(longitude=180.0)
    return xr.concat([da, edge], dim="longitude")


def process_year(cfg, year):
    p = cfg["period"]
    month = p["month"]

    if year <= p["ersst_last_year"]:
        print(f"  {year}-{month}: ERSST")
        da = open_ersst(cfg, year, month)
    else:
        da = open_oisst_monthly(cfg, year, month)
        if da is not None:
            print(f"  {year}-{month}: OISST mensual")
        else:
            print(f"  {year}-{month}: OISST diario (mes en curso, promedio parcial)")
            da = open_oisst_daily_mean(cfg, year, month)

    # ERSST/OISST traen latitud ascendente (-90→90); apply_bbox (heredado de ERA5)
    # espera descendente (90→-90), como ERA5/SEAS5. Se reordena solo acá para no
    # tocar era5_to_cpt.py.
    da = da.sortby("latitude", ascending=False)
    da = lon_0360_to_180(da)
    da = apply_bbox(da, cfg["grid"].get("bbox") or {})
    res = cfg["grid"]["resolution"]
    da = regrid_edge_aligned(da, res, cfg["grid"].get("bbox")).fillna(MISSING)
    da = _add_dateline_duplicate(da, cfg["grid"].get("bbox") or {})
    return da.expand_dims(time=[np.datetime64(f"{year}-{month}-01")])


def build_year_series(cfg):
    p = cfg["period"]
    years = range(p["year_start"], p["year_end"] + 1)
    slices = [process_year(cfg, year) for year in years]
    return xr.concat(slices, dim="time").astype("float32")


def build_output_path(cfg):
    out_dir = Path(cfg["output"]["dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    if cfg["output"]["filename"]:
        return out_dir / cfg["output"]["filename"]
    p = cfg["period"]
    month = MONTH_ABBR[int(p["month"]) - 1]
    return out_dir / f"SST_{month}_{p['year_start']}_{p['year_end']}.csv"


def write_cpt_noaa(da, output_path):
    lats = da["latitude"].values
    lons = da["longitude"].values
    nrow, ncol = len(lats), len(lons)
    time_strs = [np.datetime_as_string(t, unit="M") for t in da["time"].values]

    with open(output_path, "w") as f:
        f.write("xmlns:cpt=http://iri.columbia.edu/CPT/v10/\n")
        f.write("cpt:nfields=1\n")
        f.write("cpt:T\t" + "\t".join(time_strs) + "\n")

        for i, ts in enumerate(time_strs):
            f.write(
                f"cpt:field=SST, cpt:T={ts}, cpt:nrow={nrow}, cpt:ncol={ncol}, "
                f"cpt:row=Y, cpt:col=X, cpt:units={CPT_UNITS}, cpt:missing={MISSING}\n"
            )
            f.write("\t" + "\t".join(f"{lon:.1f}" for lon in lons) + "\n")

            data = da.isel(time=i).values
            formatted = format_grid(data)
            for lat, frow in zip(lats, formatted):
                f.write(f"{lat:.1f}\t" + "\t".join(frow) + "\n")


def main(config_path="config_convert_noaa.yaml"):
    cfg = load_config(config_path)

    print("Construyendo serie interanual (ERSST + OISST), regrillando cada año a la malla común ...")
    da = build_year_series(cfg)

    output_path = build_output_path(cfg)
    print(f"Escribiendo {output_path} ...")
    write_cpt_noaa(da, output_path)
    print("Listo.")


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config_convert_noaa.yaml"
    main(config_path)
