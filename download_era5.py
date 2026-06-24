"""
Descarga datos ERA5 desde Copernicus CDS en formato NetCDF.

Requiere autenticación previa: crear ~/.cdsapirc con el contenido:
  url: https://cds.climate.copernicus.eu/api
  key: <tu-api-key>

Uso:
  python download_era5.py [config_download.yaml] [--monthly] [--hourly]

  Sin flags descarga ambos. Con --monthly o --hourly descarga solo ese tipo.
"""

import sys
import yaml
import argparse
from pathlib import Path

import cdsapi


def load_config(path):
    with open(path) as f:
        return yaml.safe_load(f)


def download_monthly(client, cfg):
    ds = cfg["dataset"]
    m = cfg["monthly"]
    years = [str(y) for y in range(m["year_start"], m["year_end"] + 1)]
    output = m["output"]

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    print(f"Descargando mensual {m['year_start']}–{m['year_end']} → {output} ...")

    client.retrieve(
        "reanalysis-era5-pressure-levels-monthly-means",
        {
            "product_type": ["monthly_averaged_reanalysis"],
            "variable": [ds["variable"]],
            "pressure_level": [ds["pressure_level"]],
            "year": years,
            "month": [m["month"]],
            "time": ["00:00"],
            "data_format": "netcdf",
            "download_format": "unarchived",
        },
    ).download(output)
    print("Listo.")


def download_hourly(client, cfg):
    ds = cfg["dataset"]
    h = cfg["hourly"]
    output = h["output"]

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    print(f"Descargando horario {h['year']}-{h['month']} → {output} ...")

    days = [f"{d:02d}" for d in range(h["day_start"], h["day_end"] + 1)]

    client.retrieve(
        "reanalysis-era5-pressure-levels",
        {
            "product_type": ["reanalysis"],
            "variable": [ds["variable"]],
            "pressure_level": [ds["pressure_level"]],
            "year": [h["year"]],
            "month": [h["month"]],
            "day": days,
            "time": h["times"],
            "data_format": "netcdf",
            "download_format": "unarchived",
        },
    ).download(output)
    print("Listo.")


def main():
    parser = argparse.ArgumentParser(description="Descarga datos ERA5 desde CDS.")
    parser.add_argument("config", nargs="?", default="config_download.yaml")
    parser.add_argument("--monthly", action="store_true", help="Descargar solo datos mensuales")
    parser.add_argument("--hourly",  action="store_true", help="Descargar solo datos horarios")
    args = parser.parse_args()

    cfg = load_config(args.config)
    creds = cfg.get("credentials", {})
    client = cdsapi.Client(
        url=creds.get("url"),
        key=creds.get("key"),
    )

    run_monthly = args.monthly or not (args.monthly or args.hourly)
    run_hourly  = args.hourly  or not (args.monthly or args.hourly)

    if run_monthly:
        download_monthly(client, cfg)
    if run_hourly:
        download_hourly(client, cfg)


if __name__ == "__main__":
    main()
