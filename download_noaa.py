"""
Descarga datos de SST (NOAA ERSST v5 + OISST v2.1) en formato NetCDF.

Fuentes públicas (sin autenticación):
  - ERSST v5, 1961-ersst_last_year: un archivo por año-mes
  - OISST v2.1 mensual: serie completa (1981-09 en adelante), un único archivo
  - OISST v2.1 diario: año en curso, para promediar el mes objetivo si aún no cerró

Uso:
  python download_noaa.py [config_download_noaa.yaml] [--ersst] [--oisst-monthly] [--oisst-daily]

  Sin flags descarga las tres partes. Con uno o más flags, descarga solo esas partes.
"""

import argparse
import urllib.request
from pathlib import Path

import yaml

ERSST_URL = ("https://www.ncei.noaa.gov/data/sea-surface-temperature-extended-"
             "reconstructed/v5/netcdf/ersst.v5.{year}{month}.nc")
OISST_MONTHLY_URL = "https://downloads.psl.noaa.gov/Datasets/noaa.oisst.v2.highres/sst.mon.mean.nc"
OISST_DAILY_URL = "https://downloads.psl.noaa.gov/Datasets/noaa.oisst.v2.highres/sst.day.mean.{year}.nc"


def load_config(path):
    with open(path) as f:
        return yaml.safe_load(f)


def download_file(url, output):
    output = Path(output)
    if output.exists():
        print(f"  {output} ya existe, se omite.")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"  {url} -> {output}")
    urllib.request.urlretrieve(url, output)


def download_ersst(cfg):
    month = cfg["dataset"]["month"]
    e = cfg["ersst"]
    out_dir = Path(e["output_dir"])
    print(f"Descargando ERSST {e['year_start']}-{e['year_end']} (mes {month}) ...")
    for year in range(e["year_start"], e["year_end"] + 1):
        url = ERSST_URL.format(year=year, month=month)
        download_file(url, out_dir / f"ersst.v5.{year}{month}.nc")
    print("Listo.")


def download_oisst_monthly(cfg):
    print("Descargando OISST mensual (serie completa) ...")
    download_file(OISST_MONTHLY_URL, cfg["oisst_monthly"]["output"])
    print("Listo.")


def download_oisst_daily(cfg):
    o = cfg["oisst_daily"]
    print(f"Descargando OISST diario {o['year']} ...")
    download_file(OISST_DAILY_URL.format(year=o["year"]), o["output"])
    print("Listo.")


def main():
    parser = argparse.ArgumentParser(description="Descarga datos SST (ERSST + OISST) de NOAA.")
    parser.add_argument("config", nargs="?", default="config_download_noaa.yaml")
    parser.add_argument("--ersst", action="store_true", help="Descargar solo ERSST")
    parser.add_argument("--oisst-monthly", action="store_true", help="Descargar solo OISST mensual")
    parser.add_argument("--oisst-daily", action="store_true", help="Descargar solo OISST diario")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_all = not (args.ersst or args.oisst_monthly or args.oisst_daily)

    if args.ersst or run_all:
        download_ersst(cfg)
    if args.oisst_monthly or run_all:
        download_oisst_monthly(cfg)
    if args.oisst_daily or run_all:
        download_oisst_daily(cfg)


if __name__ == "__main__":
    main()
