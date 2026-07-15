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
  6. Regrilla a una malla alineada a los polos/bordes (90 a -90, -180 a 180), extrapolando
     en latitud e interpolando "envolviendo" el dateline en longitud
  7. Reutiliza bbox y carga de config de era5_to_cpt.py; formato CPT propio (G13.6)

Uso:
  python ecmwf_to_cpt.py [config_convert.yaml]
"""

import sys
import numpy as np
import xarray as xr

from era5_to_cpt import (
    MISSING, MONTH_ABBR, load_config, normalize_dims, detect_conversion,
    apply_bbox,
)
from pathlib import Path

# Variables que vienen como tasa en m/s y deben convertirse a mm/día
PRECIP_VARS = {"tprate"}
MM_PER_DAY_FACTOR = 1000.0 * 86400.0  # m/s -> mm/día

# Nombre de campo CPT y standard_name CF por variable, validado contra el formato
# de referencia de la experta (ECMWF_PP_original.csv). Solo se usa en este pipeline
# (SEAS5); era5_to_cpt.py / ERA5 no se toca.
FIELD_INFO = {
    "tprate": ("prcp", "lwe_precipitation_rate"),
    "t2m":    ("temp", "air_temperature"),
}


def format_grid(values):
    """Formatea una grilla 2D replicando el descriptor Fortran G13.6 que usa el
    formato de referencia del CPT/IRI: ancho fijo 13, 6 cifras significativas,
    alternando entre notación fija y científica según la magnitud de cada valor."""
    values = np.asarray(values, dtype=np.float64)
    nonzero = values != 0
    d_exp = np.zeros(values.shape, dtype=int)
    d_exp[nonzero] = np.floor(np.log10(np.abs(values[nonzero]))).astype(int) + 1
    fixed_mask = nonzero & (d_exp >= 0) & (d_exp <= 6)

    flat = values.ravel()
    flat_fixed = fixed_mask.ravel()
    flat_dexp = d_exp.ravel()
    out = np.empty(flat.shape, dtype=object)
    for i in range(flat.size):
        if flat_fixed[i]:
            decimals = 6 - int(flat_dexp[i])
            out[i] = f"{flat[i]:.{decimals}f}".rjust(9) + "    "
        else:
            out[i] = f"{flat[i]:13.6E}"
    return out.reshape(values.shape)


def write_cpt_seasonal(da, output_path, cfg, cpt_units, lead_months, start_dates, target_labels):
    """Escribe el archivo CPT (TSV) para el pipeline SEAS5, con cpt:L/cpt:S por
    temporada objetivo, nombre de campo CPT y formato numérico G13.6."""
    var_name = cfg["variable"]["name"]
    field_name, standard_name = FIELD_INFO.get(var_name, (var_name, None))
    lats = da["latitude"].values
    lons = da["longitude"].values
    nrow, ncol = len(lats), len(lons)

    with open(output_path, "w") as f:
        f.write("xmlns:cpt=http://iri.columbia.edu/CPT/v10/\n")
        if standard_name:
            f.write("xmlns:cf=http://cf-pcmdi.llnl.gov/documents/cf-conventions/1.4/\n")
        f.write("cpt:nfields=1\n")
        f.write("cpt:T\t" + "\t".join(target_labels) + "\n")

        for i, ts in enumerate(target_labels):
            attrs = [
                f"cpt:field={field_name}",
                f"cpt:L={lead_months[i]:.1f} months",
                f"cpt:S={start_dates[i]}",
                f"cpt:nrow={nrow}", f"cpt:ncol={ncol}",
                "cpt:row=Y", "cpt:col=X", f"cpt:units={cpt_units}",
            ]
            if standard_name:
                attrs.append(f"cf:standard_name={standard_name}")
            attrs.append(f"cpt:missing={MISSING}")
            attrs.append(f"cpt:T={ts}")
            f.write(", ".join(attrs) + "\n")
            f.write("\t" + "\t".join(f"{lon:.1f}" for lon in lons) + "\n")

            data = da.isel(time=i).values
            formatted = format_grid(data)
            for lat, frow in zip(lats, formatted):
                f.write(f"{lat:.1f}\t" + "\t".join(frow) + "\n")


def lon_0360_to_180(da):
    """Rota longitudes de 0-360 a -180/180. La grilla de SEAS5 está centrada en
    celdas (0.5, 1.5, ...) por lo que -180/180 nunca son puntos de grilla exactos;
    el borde se resuelve en regrid_edge_aligned() al regrillar."""
    da = da.assign_coords(longitude=((da["longitude"] + 180) % 360 - 180))
    return da.sortby("longitude")


def regrid_edge_aligned(da, resolution, bbox=None):
    """Regrilla a una malla alineada a los bordes/polos (90 a -90, -180 a 180 por
    defecto), en vez de anclar la malla a los extremos de celda de la grilla nativa
    de SEAS5 (89.5, -89.5, ... — la que produce era5_to_cpt.regrid()). La experta
    descarga con la convención de bordes exactos y la usa como referencia.

    Como el dato nativo no llega exactamente a los polos, se extrapola linealmente
    en latitud (single-dim interp, soporta fill_value='extrapolate'). En longitud
    el globo es periódico, así que en vez de extrapolar se duplica el punto nativo
    del borde opuesto para poder interpolar -180/180 "envolviendo" el dateline. Si
    la malla cubre el globo completo, -180 y 180 son el mismo meridiano: se incluye
    solo -180 (el original de la experta usa 360 columnas, no 361, por lo mismo)."""
    bbox = bbox or {}
    lat_max = bbox.get("lat_max") or 90.0
    lat_min = bbox.get("lat_min") or -90.0
    lon_min = bbox.get("lon_min") or -180.0
    lon_max = bbox.get("lon_max") or 180.0
    full_globe = lon_min <= -180.0 and lon_max >= 180.0

    lat_out = np.arange(lat_max, lat_min - resolution / 2, -resolution)
    da = da.interp(latitude=lat_out, method="linear", kwargs={"fill_value": "extrapolate"})

    if full_globe:
        edge_lo = da.sel(longitude=da["longitude"].max()).assign_coords(
            longitude=da["longitude"].min().item() - 1.0)
        edge_hi = da.sel(longitude=da["longitude"].min()).assign_coords(
            longitude=da["longitude"].max().item() + 1.0)
        da = xr.concat([edge_lo, da, edge_hi], dim="longitude").sortby("longitude")
        lon_out = np.arange(lon_min, lon_max, resolution)  # excluye el duplicado en lon_max
    else:
        lon_out = np.arange(lon_min, lon_max + resolution / 2, resolution)
    return da.interp(longitude=lon_out, method="linear")


def seasonal_time_metadata(da):
    """Calcula, para cada forecast_reference_time, la temporada objetivo (promedio de
    los forecastMonth presentes), el plazo a la mitad de esa temporada (cpt:L) y la
    fecha de inicialización (cpt:S). Debe llamarse antes de promediar forecastMonth.

    forecastMonth=k es el k-ésimo mes calendario DESPUÉS de la inicialización S
    (lead 0 sería el propio mes de inicialización, que CDS no ofrece como
    leadtime_month): para S=junio, forecastMonth 1/2/3 son julio/agosto/septiembre
    (confirmado por la experta)."""
    fm = da["forecastMonth"].values
    fm_min, fm_max = int(fm.min()), int(fm.max())
    lead = (fm_min + fm_max + 1) / 2.0

    target_labels, lead_months, start_dates = [], [], []
    for t in da["forecast_reference_time"].values:
        init_year, init_month = (int(x) for x in np.datetime_as_string(t, unit="M").split("-"))
        start_num = init_month + fm_min
        end_num   = init_month + fm_max
        start_year, start_month = init_year + (start_num - 1) // 12, (start_num - 1) % 12 + 1
        end_month = (end_num - 1) % 12 + 1
        label = (f"{start_year}-{start_month:02d}" if start_month == end_month
                 else f"{start_year}-{start_month:02d}/{end_month:02d}")
        target_labels.append(label)
        lead_months.append(lead)
        start_dates.append(f"{init_year:04d}-{init_month:02d}-01T00:00")
    return target_labels, lead_months, start_dates


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

    print("Calculando temporada objetivo / lead / fecha de inicialización ...")
    target_labels, lead_months, start_dates = seasonal_time_metadata(da)

    print("Promediando leadtime months ...")
    da = da.mean(dim="forecastMonth", skipna=True)
    da = da.rename({"forecast_reference_time": "time"}).astype("float32")

    print("Rotando longitudes a -180/180 ...")
    da = lon_0360_to_180(da)

    print("Aplicando bounding box ...")
    da = apply_bbox(da, cfg["grid"].get("bbox") or {})

    res = cfg["grid"]["resolution"]
    print(f"Regrillando a {res}° ...")
    da = regrid_edge_aligned(da, res, cfg["grid"].get("bbox")).fillna(MISSING)

    output_path = build_output_path(cfg, da)
    print(f"Escribiendo {output_path} ...")
    write_cpt_seasonal(da, output_path, cfg, cpt_units, lead_months, start_dates, target_labels)
    print("Listo.")


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config_convert_ecmwf.yaml"
    main(config_path)
