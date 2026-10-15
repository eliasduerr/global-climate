# global-climate

A small AWS data pipeline that pulls the Berkeley Earth surface temperature dataset from Kaggle, cleans it, computes useful features, and stores each stage as Parquet in S3.

## What it does

The pipeline has three stages:

1. **ingest** — downloads `GlobalLandTemperaturesByCity.csv` from Kaggle via `kagglehub`, validates it against a fixed schema, and writes it as Parquet to `s3://<bucket>/raw/`.
2. **clean** — casts types (dates, categoricals, signed floats for lat/lon), drops pre-1850 rows, nulls out obvious outliers (`AverageTemperatureUncertainty > 2.0`), interpolates missing temperatures per `(City, Country)`, then writes to `s3://<bucket>/interim/`.
3. **features** — aggregates each city to yearly means (complete years only, which cancels the seasonal cycle) and computes the anomaly against the city's 1951–1980 average — the reference period used by Berkeley Earth and NASA GISS. Writes one small table to `s3://<bucket>/processed/`.
4. **dashboard** — a Streamlit page showing the global mean anomaly, a map of per-city warming trends since 1950 and a city drill-down.

The batch stages use Polars in streaming mode (`scan_parquet` / `sink_parquet`), so the containers only need enough memory to hold a small buffer, not the full dataset.
