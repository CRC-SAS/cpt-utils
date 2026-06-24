# cpt-utils

Utilidad para convertir archivos NetCDF de reanálisis ERA5 al formato CPT (IRI Climate Predictability Tool).

## ¿Qué hace?

A partir de uno o dos archivos NetCDF (datos mensuales y/o sub-diarios), genera un archivo CSV en el formato que acepta CPT:

- Convierte geopotencial (m² s⁻²) a altura geopotencial (gpm)
- Rota las longitudes de 0–360° a −180–180°
- Regrilla a la resolución deseada (por defecto 2.5°)
- Si se provee un archivo horario, promedia todos los registros disponibles a un único valor mensual y lo concatena con la serie mensual

## Instalación

Requiere Python 3.10 o superior.

**Linux / macOS**
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Windows**
```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Descarga de datos ERA5

Los datos de entrada se descargan desde Copernicus CDS con `download_era5.py`.

### Autenticación

1. Crear una cuenta gratuita en `https://cds.climate.copernicus.eu`
2. Ir al perfil de usuario y copiar la API key
3. Aceptar los términos del dataset ERA5 desde el portal web (requerido antes de la primera descarga)
4. Copiar `config_download.yaml.example` a `config_download.yaml` y completar las credenciales:

```yaml
credentials:
  url: "https://cds.climate.copernicus.eu/api"
  key: "<tu-api-key>"
```

El archivo `config_download.yaml` está en `.gitignore` para evitar exponer credenciales.

### Configuración

El resto de `config_download.yaml` controla qué datos se descargan:

```yaml
dataset:
  variable: "geopotential"  # variable ERA5
  pressure_level: "500"     # nivel de presión en mb

monthly:
  year_start: 1961          # primer año de la serie
  year_end: 2025            # último año de la serie
  month: "06"               # mes a descargar (formato MM)
  output: "input/monthly/HG500_jun_1961_2025.nc"

hourly:
  year: "2026"
  month: "06"
  day_start: 1              # primer día disponible en CDS
  day_end: 18               # último día disponible en CDS
  times: ["00:00", "06:00", "12:00", "18:00"]
  output: "input/hourly/HG500_jun_2026.nc"
```

### Ejecución

**Linux / macOS**
```bash
.venv/bin/python3 download_era5.py            # descarga mensual y horario
.venv/bin/python3 download_era5.py --monthly  # solo datos mensuales
.venv/bin/python3 download_era5.py --hourly   # solo datos horarios
```

**Windows**
```bat
.venv\Scripts\python download_era5.py
.venv\Scripts\python download_era5.py --monthly
.venv\Scripts\python download_era5.py --hourly
```

Los archivos se guardan en las rutas definidas en `config_download.yaml` (por defecto `input/monthly/` e `input/hourly/`).

## Configuración

Copiar `config_convert.yaml.example` a `config_convert.yaml` y editar según necesidad:

```yaml
input:
  monthly: "input/monthly/HG500_jun_1961_2025.nc"  # requerido
  hourly:  "input/hourly/HG500_jun_2026.nc"         # opcional

variable:
  name: "z"
  pressure_level: 500.0   # null si el NetCDF no tiene esa dimensión

grid:
  resolution: 2.5
  bbox:
    lat_min: null   # null = extremo del input
    lat_max: null
    lon_min: null
    lon_max: null

output:
  dir: "output"
  filename: null  # null = nombre automático (ej. HG500_jun_1961_2026.csv)
```

## Ejecución

**Linux / macOS**
```bash
.venv/bin/python3 netcdf_to_cpt.py
```

**Windows**
```bat
.venv\Scripts\python netcdf_to_cpt.py
```

O especificando un config alternativo:

**Linux / macOS**
```bash
.venv/bin/python3 netcdf_to_cpt.py otro_config_convert.yaml
```

**Windows**
```bat
.venv\Scripts\python netcdf_to_cpt.py otro_config_convert.yaml
```

El archivo de salida se escribe en el directorio `output/`.
