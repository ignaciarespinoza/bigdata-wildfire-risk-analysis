CREATE OR REPLACE TABLE `incendios-500902.Ev3.fact_clima` AS
SELECT
  comuna AS estacion,
  fecha_hora_api,
  latitud,
  longitud,
  ST_GEOGPOINT(longitud, latitud) AS geom,
  temperatura_c,
  precipitacion_mm,
  viento_kmh,
  humedad_pct,
  codigo_clima
FROM `incendios-500902.Ev3.clima`;
