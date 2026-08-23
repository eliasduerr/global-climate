# global-climate

A small AWS data pipeline that pulls the Berkeley Earth surface temperature dataset from Kaggle, cleans it, computes useful features, and stores each stage as Parquet in S3.

## What it does

The pipeline has three stages:

1. **ingest** — downloads `GlobalLandTemperaturesByCity.csv` from Kaggle via `kagglehub`, validates it against a fixed schema, and writes it as Parquet to `s3://<bucket>/raw/`.
2. **clean** — casts types (dates, categoricals, signed floats for lat/lon), drops pre-1850 rows, nulls out obvious outliers (`AverageTemperatureUncertainty > 2.0`), interpolates missing temperatures per `(City, Country)`, then writes to `s3://<bucket>/interim/`.
3. **features** — computes rolling 30-year baseline, 10-year std-dev, year-over-year change, and a temperature anomaly per city, then writes to `s3://<bucket>/processed/`.

All three stages use Polars in streaming mode (`scan_parquet` / `sink_parquet`), so the containers only need enough memory to hold a small buffer, not the full dataset.
