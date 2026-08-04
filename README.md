# cpt-utils

Herramientas para convertir archivos NetCDF de datos climáticos al formato CSV que
acepta CPT (IRI Climate Predictability Tool).

## Descripción general

Los datos climáticos que publican los centros internacionales (Copernicus, NOAA) vienen
en **NetCDF**, un formato binario multidimensional (latitud × longitud × tiempo). CPT, en
cambio, lee un CSV con una estructura muy particular: una cabecera `cpt:` por cada campo
temporal, una fila con las longitudes, y luego una fila por latitud. Pasar de uno a otro a
mano es tedioso y propenso a errores; este repositorio automatiza ese paso, e incluye
además los scripts que descargan los datos de origen.

Cada pipeline (descarga + conversión) es independiente: se usa solo el que corresponda al
dato que se necesite.

| Pipeline | Dato | Scripts | Sección |
|---|---|---|---|
| ERA5 | Reanálisis atmosférico (mensual y/o sub-diario) | `download_era5.py` + `era5_to_cpt.py` | [Reanálisis ERA5](#reanálisis-era5) |
| ECMWF SEAS5 | Pronóstico estacional | `download_ecmwf.py` + `ecmwf_to_cpt.py` | [Pronóstico estacional ECMWF (SEAS5)](#pronóstico-estacional-ecmwf-seas5) |
| NOAA SST | Temperatura de la superficie del mar | `download_noaa.py` + `noaa_to_cpt.py` | [Temperatura de la superficie del mar (NOAA ERSST/OISST)](#temperatura-de-la-superficie-del-mar-noaa-ersstoisst) |

Los tres generan un CSV en el directorio `output/`, listo para abrir con CPT.

## Instalación y configuración

Lo que sigue vale para los tres pipelines; lo específico de cada uno está en su propia
sección.

### Entorno de Python

Requiere **Python 3.10 o superior**.

Conviene instalar las dependencias en un *entorno virtual* (virtualenv): una carpeta
aislada — acá `.venv` — con su propia copia de Python y sus paquetes, para no mezclarlos
con los del sistema ni con los de otros proyectos.

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

No hace falta "activar" nada: en los ejemplos de este README se invoca directamente el
Python del entorno (`.venv/bin/python3` en Linux/macOS). **En Windows, reemplazar
`.venv/bin/python3` por `.venv\Scripts\python` en todos los comandos que siguen.**

### Cómo funcionan los archivos de configuración

Ningún script pide datos de forma interactiva: todo lo que hay que decidir (qué variable,
qué años, qué resolución, dónde guardar) se escribe en un archivo **YAML**, un formato de
texto plano legible donde cada opción se escribe como `clave: valor` y la jerarquía se
marca con sangría.

El repositorio trae plantillas terminadas en `.example`. El flujo siempre es el mismo:
copiar la plantilla a un archivo real y editarla.

```bash
cp config_convert.yaml.example config_convert_HG500.yaml
```

Los archivos `*.yaml` están en `.gitignore` y por lo tanto **no se suben al repositorio**.
Esto es a propósito: algunos contienen credenciales (la API key de Copernicus) y todos
describen una corrida puntual, no algo que deba compartirse. Las plantillas `.example`, en
cambio, sí están versionadas.

Por convención los archivos se nombran según el caso de uso, es decir la variable o el
producto que se está procesando (`HG500`, `U250`, `T2M`, `SST`, ...):

- `config_download_<CASO>.yaml` → qué descargar
- `config_convert_<CASO>.yaml` → cómo convertir lo descargado

Cada script recibe el archivo de configuración como *argumento de línea de comandos*, es
decir, un valor que se escribe a continuación del nombre del script al ejecutarlo:

```bash
.venv/bin/python3 era5_to_cpt.py config_convert_HG500.yaml
```

Si se omite el argumento, cada script usa un nombre por defecto (`config_download.yaml`,
`config_convert_HG500.yaml`, `config_download_ecmwf.yaml`, `config_convert_ecmwf.yaml`,
`config_download_noaa.yaml`, `config_convert_noaa.yaml` según el script). Conviene pasarlo
siempre de forma explícita para no depender de eso.

Algunos scripts aceptan además *flags*, opciones que empiezan con `--` y activan o
desactivan partes del proceso (por ejemplo `--monthly`). Están documentados en la sección
de cada pipeline.

## Reanálisis ERA5

Reanálisis atmosférico global de ERA5 (Copernicus), en niveles de presión: altura
geopotencial, viento, velocidad vertical, etc.

`era5_to_cpt.py` toma uno o dos NetCDF (la serie mensual y, opcionalmente, un archivo
sub-diario del mes en curso) y produce el CSV para CPT. En el camino:

- Convierte geopotencial (m² s⁻²) a altura geopotencial (gpm), dividiendo por la gravedad.
  Otras variables (viento, velocidad vertical) pasan sin conversión, con las unidades
  detectadas del NetCDF.
- Rota las longitudes de 0–360° a −180–180°, que es la convención que espera CPT.
- Regrilla a la resolución deseada (por defecto 2.5°) por interpolación bilineal.
- Si se provee un archivo sub-diario, promedia todos sus registros a un único valor
  mensual y lo concatena al final de la serie mensual. Esto permite incluir el año en
  curso, cuyo dato mensual definitivo todavía no publicó Copernicus.

### Descarga

Los datos se bajan del Climate Data Store (CDS) de Copernicus con `download_era5.py`.

**Autenticación** (una sola vez):

1. Crear una cuenta gratuita en `https://cds.climate.copernicus.eu`.
2. Entrar al perfil de usuario y copiar la API key.
3. Aceptar los términos del dataset ERA5 desde el portal web. Sin este paso la descarga
   falla, aunque las credenciales sean correctas.
4. Copiar la plantilla y pegar la API key:

```bash
cp config_download.yaml.example config_download_HG500.yaml
```

```yaml
credentials:
  url: "https://cds.climate.copernicus.eu/api"
  key: "<tu-api-key>"
```

El resto del archivo define qué se descarga:

```yaml
dataset:
  variable: "geopotential"  # variable ERA5 (ver lista en la plantilla)
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

Ejecución:

```bash
.venv/bin/python3 download_era5.py config_download_HG500.yaml            # mensual + sub-diario
.venv/bin/python3 download_era5.py config_download_HG500.yaml --monthly  # solo mensual
.venv/bin/python3 download_era5.py config_download_HG500.yaml --hourly   # solo sub-diario
```

Los archivos quedan en las rutas indicadas en el YAML (por defecto `input/monthly/` e
`input/hourly/`). La descarga mensual de una serie larga puede tardar varios minutos,
porque CDS encola el pedido antes de servirlo.

### Conversión

```bash
cp config_convert.yaml.example config_convert_HG500.yaml
```

```yaml
input:
  monthly: "input/monthly/HG500_jun_1961_2025.nc"  # requerido
  hourly:  "input/hourly/HG500_jun_2026.nc"        # opcional

variable:
  name: "z"               # nombre de la variable DENTRO del NetCDF, no el pedido a CDS
  pressure_level: 500.0   # null si el NetCDF no tiene esa dimensión

grid:
  resolution: 2.5         # resolución de salida en grados
  bbox:                   # bounding box: rectángulo lat/lon que se recorta
    lat_min: null         # null en cualquier campo = usar el extremo del input
    lat_max: null
    lon_min: null
    lon_max: null

output:
  dir: "output"
  filename: null  # null = nombre automático (ej. HG500_jun_1961_2026.csv)
```

Ejecución:

```bash
.venv/bin/python3 era5_to_cpt.py config_convert_HG500.yaml
```

El CSV se escribe en `output/`. Con `filename: null` el nombre se arma solo, a partir del
prefijo del archivo de entrada y del rango de años efectivamente procesado (por eso
`HG500_jun_1961_2025.nc` + el sub-diario de 2026 da `HG500_jun_1961_2026.csv`).

### Ejemplos de salida

Casos probados con datos de junio 1961–2026 (mensual 1961–2025 + sub-diario 2026
promediado), resolución global de 2.5°.

| Variable ERA5 | Nivel | Var. NetCDF | Unidades | Archivo de salida | Min | Max | Media |
|---|---|---|---|---|---|---|---|
| Geopotential | 500 hPa | `z` | gpm | `HG500_jun_1961_2026.csv` | 4733.23 | 5947.72 | 5548.67 |
| U-component of wind | 250 hPa | `u` | m/s | `U250_jun_1961_2026.csv` | -20.09 | 67.47 | 11.96 |
| V-component of wind | 850 hPa | `v` | m/s | `V850_jun_1961_2026.csv` | -14.64 | 21.45 | 0.33 |
| Vertical velocity | 700 hPa | `w` | Pa/s | `W700_jun_1961_2026.csv` | -1.43 | 2.11 | 0.003 |

Los configs de cada caso son los `config_download_<CASO>.yaml` y
`config_convert_<CASO>.yaml` correspondientes (no versionados, ver
[Instalación y configuración](#instalación-y-configuración)).

## Pronóstico estacional ECMWF (SEAS5)

Pronóstico estacional del ECMWF (sistema SEAS5, dataset `seasonal-monthly-single-levels`
de CDS): para cada año, un pronóstico inicializado en un mes dado, con varios meses de
anticipación (*leadtime*) y muchos miembros de ensamble (corridas del modelo con
condiciones iniciales levemente distintas).

### Descarga

Se baja del Climate Data Store (CDS) de Copernicus con `download_ecmwf.py`.

**Autenticación** (una sola vez):

1. Crear una cuenta gratuita en `https://cds.climate.copernicus.eu`.
2. Copiar la API key del perfil de usuario.
3. Aceptar los términos del dataset `seasonal-monthly-single-levels` desde el portal web.
   Son términos propios de ese dataset: haber aceptado los de ERA5 no alcanza.
4. Copiar la plantilla, pegar la API key y elegir variable y años:

```bash
cp config_download_ecmwf.yaml.example config_download_T2M.yaml
```

```yaml
credentials:
  url: "https://cds.climate.copernicus.eu/api"
  key: "<tu-api-key>"

dataset:
  variable: "2m_temperature"    # o "total_precipitation"
  originating_centre: "ecmwf"
  system: "51"
  product_type: "monthly_mean"  # media del mes por miembro (no promedio de miembros)

seasonal:
  years: [1981, 1982, ..., 2026]  # ver la lista completa en la plantilla
  month: "06"                     # mes de inicialización (MM)
  leadtime_months: [1, 2, 3]
  output: "input/seasonal/T2M_jun_1981_2026.nc"
```

Ejecución:

```bash
.venv/bin/python3 download_ecmwf.py config_download_T2M.yaml
```

Descarga todos los miembros de ensamble y todos los `leadtime_month` pedidos, para todos
los años, en un único NetCDF (ver `input/seasonal/README.md`). Los años de hindcast (hasta
2016) tienen 25 miembros reales y el resto relleno con `NaN` hasta completar 51; los años
operativos tienen 51 miembros reales.

### Conversión

```bash
cp config_convert_ecmwf.yaml.example config_convert_T2M.yaml
```

```yaml
input:
  seasonal: "input/seasonal/T2M_jun_1981_2026.nc"

variable:
  name: "t2m"           # nombre dentro del NetCDF: "t2m", o "tprate" para precipitación
  pressure_level: null  # este dataset no tiene niveles de presión

grid:
  resolution: 2.5
  bbox:                 # bounding box: rectángulo lat/lon que se recorta
    lat_min: null       # null = extremo del input
    lat_max: null
    lon_min: null
    lon_max: null

output:
  dir: "output"
  filename: null
```

Ejecución:

```bash
.venv/bin/python3 ecmwf_to_cpt.py config_convert_T2M.yaml
```

El script:

- Promedia los miembros de ensamble ignorando los `NaN`, para que los años de hindcast
  (con menos miembros reales) no queden sesgados.
- Si la variable es `tprate` (precipitación, que viene como tasa en m/s), la convierte a
  mm/día.
- Promedia los `leadtime_month` con igual peso, obteniendo un valor por temporada. El
  leadtime *k* es el *k*-ésimo mes calendario **posterior** al de inicialización: con
  inicialización en junio, los leadtimes 1-3 corresponden a julio-agosto-septiembre.
- Regrilla a una malla alineada a los polos y bordes (90 a −90, −180 a 180) en lugar de
  anclarla a los centros de celda nativos de SEAS5, que es la convención de la referencia
  del IRI.
- Escribe el CSV con los metadatos que CPT espera para pronósticos: nombre de campo
  (`temp`, `prcp`), plazo (`cpt:L`), fecha de inicialización (`cpt:S`) y temporada objetivo
  (`cpt:T`), con precisión numérica Fortran G13.6.

### Ejemplos de salida

Casos probados con pronóstico inicializado en junio, años 1981–2026, leadtime 1-3,
resolución global de 2.5°.

| Variable ECMWF | Var. NetCDF | Unidades | Archivo de salida | Min | Max | Media |
|---|---|---|---|---|---|---|
| 2m Temperature | `t2m` | K | `T2M_jun_1981_2026.csv` | 211.23 | 313.20 | 281.10 |
| Total precipitation | `tprate` | mm/día | `TP_jun_1981_2026.csv` | 0.00 | 32.20 | 2.55 |

## Temperatura de la superficie del mar (NOAA ERSST/OISST)

Serie interanual de temperatura de la superficie del mar (SST) para un mes fijo,
combinando tres fuentes públicas de NOAA. **No requieren cuenta ni autenticación.**

Se usan tres fuentes porque ninguna cubre sola todo el período: OISST, de mayor
resolución, recién arranca en septiembre de 1981, y su archivo mensual no incluye el mes
en curso hasta que termina.

| Período | Fuente | Resolución nativa |
|---|---|---|
| 1961 – `ersst_last_year` (por defecto 1981) | ERSST v5 | 2° |
| `ersst_last_year`+1 – último mes completo | OISST v2.1 mensual | 0.25° |
| Mes en curso (incompleto) | OISST v2.1 diario, promedio de los días disponibles | 0.25° |

### Descarga

```bash
cp config_download_noaa.yaml.example config_download_SST.yaml
```

```yaml
dataset:
  month: "07"             # mes objetivo (MM), igual para todos los años
  ersst_last_year: 1981   # último año cubierto por ERSST

ersst:
  year_start: 1961
  year_end: 1981
  output_dir: "input/sst/ersst"   # un archivo ersst.v5.<año><mes>.nc por año

oisst_monthly:
  output: "input/sst/sst.mon.mean.nc"

oisst_daily:
  year: 2026                                  # solo hace falta si el mes objetivo
  output: "input/sst/sst.day.mean.2026.nc"    # cae en el año en curso y no cerró
```

Ejecución:

```bash
.venv/bin/python3 download_noaa.py config_download_SST.yaml                  # las tres fuentes
.venv/bin/python3 download_noaa.py config_download_SST.yaml --ersst          # solo ERSST
.venv/bin/python3 download_noaa.py config_download_SST.yaml --oisst-monthly  # solo OISST mensual
.venv/bin/python3 download_noaa.py config_download_SST.yaml --oisst-daily    # solo OISST diario
```

El archivo OISST mensual completo pesa ~2.2 GB (serie 1981-09 en adelante) y el diario
anual ~265 MB. Se descargan una sola vez y se reutilizan entre corridas: el script omite
la descarga si el archivo ya existe. Por eso los flags son útiles, por ejemplo, para
volver a bajar solo el diario del año en curso cuando pasaron más días.

### Conversión

```bash
cp config_convert_noaa.yaml.example config_convert_SST.yaml
```

```yaml
input:
  ersst_dir: "input/sst/ersst"
  oisst_monthly: "input/sst/sst.mon.mean.nc"
  oisst_daily: "input/sst/sst.day.mean.2026.nc"   # opcional

variable:
  name: "sst"

period:
  year_start: 1961
  year_end: 2026
  month: "07"             # mes objetivo (MM), igual para todos los años
  ersst_last_year: 1981   # años <= este usan ERSST; el resto, OISST

grid:
  resolution: 1.0         # resolución de salida en grados
  bbox:                   # bounding box: rectángulo lat/lon que se recorta
    lat_min: null         # null = extremo global (90/-90/-180/180)
    lat_max: null
    lon_min: null
    lon_max: null

output:
  dir: "output"
  filename: null  # null = nombre automático (ej. SST_jul_1961_2026.csv)
```

Ejecución:

```bash
.venv/bin/python3 noaa_to_cpt.py config_convert_SST.yaml
```

El script:

- Elige la fuente año por año según `ersst_last_year`: ERSST hasta ese año, OISST mensual
  después. Si el mes objetivo del año en curso todavía no está completo en el archivo
  mensual, promedia los días disponibles del archivo diario (sin exigir un mínimo de días).
- Rota y regrilla **cada año por separado, antes** de concatenar la serie, porque ERSST
  (2°) y OISST (0.25°) tienen grillas nativas distintas y hay que llevarlas a una malla
  común. En ERA5 y SEAS5, en cambio, se regrilla una sola vez al final.
- Usa la misma malla alineada a polos/bordes que el pipeline SEAS5, porque ninguna fuente
  NOAA tiene puntos de grilla exactos en los bordes.
- Escribe las unidades fijas como `Celsius_scale`: ERSST y OISST ya publican en grados
  Celsius, así que no hay conversión.

### Ejemplo de salida

Serie de julio 1961–2026 (ERSST hasta 1981, OISST desde 1982), resolución global de 1°.

| Variable | Var. NetCDF | Unidades | Archivo de salida | Min | Max | Media |
|---|---|---|---|---|---|---|
| Sea surface temperature | `sst` | °C | `SST_jul_1961_2026.csv` | -1.95 | 34.21 | 13.78 |

### Estado de validación

El tramo cubierto por OISST se comparó contra un archivo de referencia provisto por la
experta (SMN) y el acuerdo es excelente: las diferencias en celdas oceánicas comparables
son despreciables.

El tramo ERSST (1961–1981) no tuvo una referencia número a número (el único archivo
disponible había sido generado con ERSST **v2**, no v5, y v2 ya no se puede descargar),
pero la experta validó visualmente la serie completa 1961–2026 y la confirmó correcta.
La resolución de salida quedó definida en 1° (`grid.resolution: 1.0`).
