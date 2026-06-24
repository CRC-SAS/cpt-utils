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

## Configuración

Editar `config.yaml` antes de ejecutar:

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
.venv/bin/python3 netcdf_to_cpt.py otro_config.yaml
```

**Windows**
```bat
.venv\Scripts\python netcdf_to_cpt.py otro_config.yaml
```

El archivo de salida se escribe en el directorio `output/`.
