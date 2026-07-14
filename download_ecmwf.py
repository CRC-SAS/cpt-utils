"""
Descarga datos de pronóstico estacional ECMWF (SEAS5) desde Copernicus CDS en formato NetCDF.

Requiere autenticación previa: ver config_download_ecmwf.yaml.example.

Uso:
  python download_ecmwf.py [config_download.yaml]
"""

import sys
import yaml
from pathlib import Path

import cdsapi


def load_config(path):
    with open(path) as f:
        return yaml.safe_load(f)


def download(client, cfg):
    ds = cfg["dataset"]
    s = cfg["seasonal"]
    years = [str(y) for y in s["years"]]
    output = s["output"]

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    print(f"Descargando {ds['variable']} ({years[0]}-{years[-1]}) → {output} ...")

    client.retrieve(
        "seasonal-monthly-single-levels",
        {
            "originating_centre": ds["originating_centre"],
            "system": ds["system"],
            "variable": [ds["variable"]],
            "product_type": [ds["product_type"]],
            "year": years,
            "month": [s["month"]],
            "leadtime_month": [str(l) for l in s["leadtime_months"]],
            "data_format": "netcdf",
        },
    ).download(output)
    print("Listo.")


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config_download_ecmwf.yaml"
    cfg = load_config(config_path)
    creds = cfg.get("credentials", {})
    client = cdsapi.Client(url=creds.get("url"), key=creds.get("key"))
    download(client, cfg)


if __name__ == "__main__":
    main()
