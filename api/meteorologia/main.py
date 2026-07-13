import requests
import pandas as pd
from google.cloud import bigquery
from google.cloud import storage
import datetime
from zoneinfo import ZoneInfo
import functions_framework
import json

# --- CONFIGURACIÓN ---
PROJECT_ID = "PROJECT_ID" 
DATASET = "datos_emergencia"
TABLE = "clima"

BUCKET = "clima_historico"  

@functions_framework.http
def ejecutar_ruta_meteorologica(request):
    try:
        bq_client = bigquery.Client(project=PROJECT_ID)
        storage_client = storage.Client(project=PROJECT_ID)

        table_ref = bq_client.dataset(DATASET_ID).table(TABLE_NAME)

        bucket = storage_client.bucket(BUCKET_NAME)

        ciudades = [
            {"comuna": "Arica", "lat": -18.4746, "lon": -70.2979},
            {"comuna": "Iquique", "lat": -20.2133, "lon": -70.1503},
            {"comuna": "Antofagasta", "lat": -23.6524, "lon": -70.3954},
            {"comuna": "Copiapo", "lat": -27.3665, "lon": -70.3323},
            {"comuna": "La Serena", "lat": -29.9045, "lon": -71.2489},
            {"comuna": "Valparaiso", "lat": -33.0458, "lon": -71.6197},
            {"comuna": "Santiago", "lat": -33.4569, "lon": -70.6483},
            {"comuna": "Rancagua", "lat": -34.1708, "lon": -70.7445},
            {"comuna": "Talca", "lat": -35.4264, "lon": -71.6554},
            {"comuna": "Chillan", "lat": -36.6066, "lon": -72.1034},
            {"comuna": "Concepcion", "lat": -36.8270, "lon": -73.0503},
            {"comuna": "Temuco", "lat": -38.7397, "lon": -72.5901},
            {"comuna": "Valdivia", "lat": -39.8142, "lon": -73.2459},
            {"comuna": "Puerto Montt", "lat": -41.4693, "lon": -72.9424},
            {"comuna": "Coyhaique", "lat": -45.5712, "lon": -72.0683},
            {"comuna": "Punta Arenas", "lat": -53.1548, "lon": -70.9113}
        ]

        filas_streaming = []

        zona_chile = ZoneInfo("America/Santiago")
        tiempo_ingesta_dt = datetime.datetime.now(zona_chile)
        tiempo_ingesta = tiempo_ingesta_dt.strftime("%Y-%m-%d %H:%M:%S")

        for ciudad in ciudades:
            url_api = f"https://api.open-meteo.com/v1/forecast?latitude={ciudad['lat']}&longitude={ciudad['lon']}&current=temperature_2m,precipitation,wind_speed_10m,relative_humidity_2m,weather_code&timezone=America/Santiago"
            
            response = requests.get(url_api)
            response.raise_for_status()
            actual = response.json().get('current', {})

            if actual:
                tiempo_api = pd.to_datetime(actual['time']).strftime("%Y-%m-%d %H:%M:%S")

                fila = {
                    "fecha_hora_api": tiempo_api,
                    "fecha_hora_ingesta": tiempo_ingesta,
                    "comuna": ciudad['comuna'],
                    "latitud": ciudad['lat'],
                    "longitud": ciudad['lon'],
                    "temperatura_c": float(actual['temperature_2m']),
                    "precipitacion_mm": float(actual['precipitation']),
                    "viento_kmh": float(actual['wind_speed_10m']),
                    "humedad_pct": int(actual['relative_humidity_2m']),
                    "codigo_clima": int(actual['weather_code'])
                }

                filas_streaming.append(fila)

        if not filas_streaming:
            return "Error: No se generaron registros.", 500

        # -------------------------
        # 1. GUARDAR EN BIGQUERY
        # -------------------------
        errores = bq_client.insert_rows_json(table_ref, filas_streaming)

        # -------------------------
        # 2. GUARDAR EN STORAGE
        # -------------------------
        nombre_archivo = f"clima_historico/{tiempo_ingesta_dt.strftime('%Y/%m/%d/%H%M%S')}_clima.json"
        blob = bucket.blob(nombre_archivo)
        blob.upload_from_string(
            data=json.dumps(filas_streaming, ensure_ascii=False),
            content_type="application/json"
        )

        if errores == []:
            return f"OK: Datos guardados en BigQuery y Storage ({nombre_archivo})", 200
        else:
            return f"Error BigQuery: {str(errores)} (pero Storage OK)", 500

    except Exception as e:
        return f"Error crítico: {str(e)}", 500
