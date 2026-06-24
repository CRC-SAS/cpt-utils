"""
Convierte un NetCDF de geopotencial ERA5 al formato CPT (IRI).

Pipeline:
  1. Lee config.yaml
  2. Abre NetCDF mensual (y opcionalmente horario, promediando a mensual)
  3. Concatena, detecta unidades y convierte a gpm
  4. Rota longitudes de 0-360 a -180-180
  5. Recorta al bounding box definido
  6. Regrilla a la resolución definida por interpolación bilineal
  7. Escribe el archivo CPT (TSV con cabeceras específicas)

Uso:
  python netcdf_to_cpt.py [config.yaml]
"""

import sys
import numpy as np
import xarray as xr
import yaml
from pathlib import Path

MISSING = -999
G = 9.80665

# Unidades conocidas de geopotencial y su factor de conversión a gpm
UNIT_CONVERSION = {
    "m**2 s**-2": 1.0 / G,
    "m2 s-2":     1.0 / G,
    "j kg-1":     1.0 / G,
    "gpm":        1.0,
    "m":          1.0,
}


def load_config(path="config_convert.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)


def normalize_dims(da):
    """Renombra lat/lon/time a nombres canónicos usando cf_xarray."""
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
    factor = UNIT_CONVERSION.get(units)
    if factor is None:
        print(f"  Advertencia: unidades '{units}' no reconocidas, no se aplica conversión.")
        factor = 1.0
    return factor


def open_monthly(path, cfg):
    ds = xr.open_dataset(path)
    da = ds[cfg["variable"]["name"]]
    plevel = cfg["variable"]["pressure_level"]
    if plevel is not None:
        plevel_dim = next((d for d in da.dims if "pressure" in d.lower() or "level" in d.lower()), None)
        if plevel_dim:
            da = da.sel({plevel_dim: plevel}, drop=True)
    da = normalize_dims(da)
    # Elimina coordenadas escalares o auxiliares que pueden diferir entre archivos
    drop = [c for c in da.coords if c not in da.dims]
    return da.drop_vars(drop)


def open_hourly(path, cfg):
    da = open_monthly(path, cfg)  # misma lógica de apertura
    return da.resample(time="MS").mean()


def lon_0360_to_180(da):
    da = da.assign_coords(longitude=((da["longitude"] + 180) % 360 - 180))
    da = da.sortby("longitude")
    # Cierre periódico: duplica -180° como +180°
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


def write_cpt(da, output_path, cfg):
    plevel = cfg["variable"]["pressure_level"] or 0.0
    var_name = cfg["variable"]["name"]
    times = da["time"].values
    lats  = da["latitude"].values
    lons  = da["longitude"].values
    nrow, ncol = len(lats), len(lons)
    time_strs = [np.datetime_as_string(t, unit="M") for t in times]

    with open(output_path, "w") as f:
        f.write("xmlns:cpt=http://iri.columbia.edu/CPT/v10/\n")
        f.write("cpt:nfields=1\n")
        f.write("cpt:T\t" + "\t".join(time_strs) + "\n")

        for i, ts in enumerate(time_strs):
            f.write(
                f"cpt:field={var_name}, cpt:P={plevel:.1f} mb, cpt:T={ts}, "
                f"cpt:nrow={nrow}, cpt:ncol={ncol}, "
                f"cpt:row=Y, cpt:col=X, cpt:units=gpm, cpt:missing={MISSING}\n"
            )
            f.write("\t" + "\t".join(f"{lon:.1f}" for lon in lons) + "\n")

            data = da.isel(time=i).values
            for lat, row in zip(lats, data):
                f.write(f"{lat:.1f}\t" + "\t".join(f"{v:12.2f}" for v in row) + "\n")


MONTH_ABBR = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]

def build_output_path(cfg, da=None):
    out_dir = Path(cfg["output"]["dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    if cfg["output"]["filename"]:
        return out_dir / cfg["output"]["filename"]
    prefix = Path(cfg["input"]["monthly"]).stem.split("_")[0]
    if da is not None:
        t0 = da["time"].values[0].astype("datetime64[M]").astype(object)
        t1 = da["time"].values[-1].astype("datetime64[M]").astype(object)
        month = MONTH_ABBR[int(str(t0)[5:7]) - 1]
        return out_dir / f"{prefix}_{month}_{str(t0)[:4]}_{str(t1)[:4]}.csv"
    return out_dir / f"{prefix}.csv"


def main(config_path="config.yaml"):
    cfg = load_config(config_path)

    print("Leyendo archivo mensual ...")
    da = open_monthly(cfg["input"]["monthly"], cfg)

    if cfg["input"].get("hourly"):
        print("Leyendo archivo horario y promediando a mensual ...")
        da_hourly = open_hourly(cfg["input"]["hourly"], cfg)
        print("Concatenando ...")
        da = xr.concat([da, da_hourly], dim="time").sortby("time")

    factor = detect_conversion(da)
    print(f"Convirtiendo a gpm (factor = {factor:.8f}) ...")
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
    write_cpt(da, output_path, cfg)
    print("Listo.")


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config_convert.yaml"
    main(config_path)
