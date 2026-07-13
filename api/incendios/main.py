from flask import Flask
from google.cloud import storage, bigquery
import pandas as pd
from io import BytesIO
import re

app = Flask(__name__)

# =========================
# CONFIG
# =========================
PROJECT_ID = "qwiklabs-gcp-02-99671df7afc7"
BUCKET = "incendio"
FILE = "incendios_chile_2024_2025.csv"

DATASET = "datos_emergencia"
TABLE = "incendios"


# =========================
# POLYGON FIX (WKT)
# =========================
def parse_polygon(raw):
    """
    El CSV trae 2 puntos por fila: esquina suroeste y esquina noreste
    de un bounding box, ej: [(-36.6607, -70.7906), (-36.6507, -70.7706)]
    A partir de esas 2 esquinas construimos las 4 esquinas del rectángulo
    y cerramos el polígono.
    """
    if raw is None:
        return None

    raw = str(raw).strip()

    if raw == "" or raw.lower() == "nan":
        return None

    matches = re.findall(
        r"\((-?\d+\.\d+),\s*(-?\d+\.\d+)\)",
        raw
    )

    if len(matches) < 2:
        return None

    # Tomamos las primeras 2 coordenadas como esquinas opuestas del bbox
    lat1, lon1 = float(matches[0][0]), float(matches[0][1])
    lat2, lon2 = float(matches[1][0]), float(matches[1][1])

    min_lat, max_lat = min(lat1, lat2), max(lat1, lat2)
    min_lon, max_lon = min(lon1, lon2), max(lon1, lon2)

    # WKT usa orden (lon lat)
    coords = [
        f"{min_lon} {min_lat}",
        f"{max_lon} {min_lat}",
        f"{max_lon} {max_lat}",
        f"{min_lon} {max_lat}",
        f"{min_lon} {min_lat}",  # cerrar polígono
    ]

    return f"POLYGON(({', '.join(coords)}))"


# =========================
# CLOUD RUN ENTRYPOINT
# =========================
@app.route("/", methods=["GET"])
def run(request):

    storage_client = storage.Client()
    bq_client = bigquery.Client()

    # =========================
    # 1. LOAD CSV
    # =========================
    blob = storage_client.bucket(BUCKET).blob(FILE)
    data = blob.download_as_bytes()

    df = pd.read_csv(
        BytesIO(data),
        sep=";",
        dtype=str,
        encoding="latin-1",
        on_bad_lines="skip"
    )

    df = df.fillna("")

    # =========================
    # 2. CLEAN COLUMNS
    # =========================
    df.columns = df.columns.str.strip()

    df.columns = (
        df.columns
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("/", "_")
        .str.replace("(", "")
        .str.replace(")", "")
        .str.replace("ó", "o")
        .str.replace("ñ", "n")
        .str.replace("á", "a")
        .str.replace("é", "e")
        .str.replace("í", "i")
        .str.replace("ú", "u")
    )

    df.columns = df.columns.str.replace(r"[^a-z0-9_]", "_", regex=True)

    # =========================
    # 3. NUMERIC CLEAN
    # =========================
    for col in ["temp_max", "viento_kmh", "humedad_porc", "superficie_ha"]:
        if col in df.columns:
            df[col] = df[col].str.replace(",", ".", regex=False)

    # =========================
    # 4. DATES
    # =========================
    if "inicio_incendio" in df.columns:
        df["inicio_incendio"] = pd.to_datetime(df["inicio_incendio"], errors="coerce")

    if "termino_incendio" in df.columns:
        df["termino_incendio"] = pd.to_datetime(df["termino_incendio"], errors="coerce")

    # =========================
    # 5. GEOMETRY FIX
    # =========================
    if "poligono_afectado" in df.columns:
        df["geom_wkt"] = df["poligono_afectado"].apply(parse_polygon)
    else:
        df["geom_wkt"] = None

    # =========================
    # 6. LOAD TO BIGQUERY
    # =========================
    destination = f"{PROJECT_ID}.{DATASET}.{TABLE}"

    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        autodetect=True
    )

    bq_client.load_table_from_dataframe(
        df,
        destination,
        job_config=job_config
    ).result()

    # =========================
    # 7. SAFE RESPONSE (NO int64 ERROR)
    # =========================
    return {
        "status": "ok",
        "rows": int(len(df)),
        "geom_ok": int(df["geom_wkt"].notna().sum())
    }
