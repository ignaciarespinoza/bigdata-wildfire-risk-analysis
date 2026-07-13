from flask import Flask
from google.cloud import storage, bigquery
import pandas as pd
from io import BytesIO

app = Flask(__name__)

PROJECT_ID = "qwiklabs-gcp-02-99671df7afc7"
BUCKET_NAME = "postas"
FILE_NAME = "establecimientos_20260526.csv"

DATASET = "datos_emergencia"
TABLE = "postas_rurales"


@app.route("/", methods=["GET"])
def run(request):

    try:
        storage_client = storage.Client()
        bq_client = bigquery.Client()

        blob = storage_client.bucket(BUCKET_NAME).blob(FILE_NAME)
        csv_bytes = blob.download_as_bytes()

        # lectura más robusta
        df = pd.read_csv(
            BytesIO(csv_bytes),
            sep=None,          
            engine="python",
            dtype=str,
            encoding="utf-8",
            on_bad_lines="skip"
        )

        # limpiar headers
        df.columns = df.columns.str.strip()

        # validar columna existe
        if "TipoEstablecimientoGlosa" not in df.columns:
            return {
                "error": "No existe columna TipoEstablecimientoGlosa",
                "columns": list(df.columns)
            }, 500

        df = df.fillna("")

        # filtro robusto
        postas = df[
            df["TipoEstablecimientoGlosa"]
            .str.upper()
            .str.contains("POSTA", na=False)
        ].copy()

        # BigQuery destino
        destination = f"{PROJECT_ID}.{DATASET}.{TABLE}"

        job_config = bigquery.LoadJobConfig(
            write_disposition="WRITE_TRUNCATE",
            autodetect=True
        )

        bq_client.load_table_from_dataframe(
            postas,
            destination,
            job_config=job_config
        ).result()

        return {
            "status": "ok",
            "total_csv": len(df),
            "total_postas": len(postas)
        }

    except Exception as e:
        return {"error": str(e)}, 500
