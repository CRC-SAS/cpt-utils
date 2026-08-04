# input/seasonal

Archivos NetCDF con pronóstico estacional ECMWF (SEAS5) descargados con `download_ecmwf.py`.

Cada archivo cubre una variable en un rango de años, con dimensiones `number` (miembro de
ensamble), `forecast_reference_time` (año/mes de inicialización), `forecastMonth` (leadtime
1, 2, 3), `latitude` y `longitude`. Los años hindcast (hasta 2016) tienen 25 miembros reales
y el resto NaN hasta completar 51; los años operativos tienen 51 miembros reales. Ejemplo:
`T2M_jun_1981_2026.nc` contiene temperatura a 2m para pronósticos inicializados en junio,
1981 a 2026, con leadtime 1-3 (jul-ago-sep).
