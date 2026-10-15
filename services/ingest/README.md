# ingest

Downloads the Berkeley Earth city temperature CSV from Kaggle, validates it against a fixed schema and writes it unchanged as Parquet to the raw layer.

## Input / output

| | Location |
| --- | --- |
| Input | `GlobalLandTemperaturesByCity.csv` from the Kaggle dataset [`berkeleyearth/climate-change-earth-surface-temperature-data`](https://www.kaggle.com/datasets/berkeleyearth/climate-change-earth-surface-temperature-data) |
| Output | `s3://<DATA_BUCKET>/raw/temperatures.parquet` |

## Schema

The data is not transformed. The schema is enforced with `match_to_schema`, so a missing, extra or mistyped column raises a `SchemaError` and fails the job.

| Column | Type | Example |
| --- | --- | --- |
| `dt` | `String` | `1850-01-01` |
| `AverageTemperature` | `Float64` | `-1.94` |
| `AverageTemperatureUncertainty` | `Float64` | `1.28` |
| `City` | `String` | `Berlin` |
| `Country` | `String` | `Germany` |
| `Latitude` | `String` | `52.24N` |
| `Longitude` | `String` | `13.14E` |

Dates and coordinates stay strings here and are parsed in [clean](../clean/README.md).

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `KAGGLE_API_TOKEN` | – | Kaggle API token. If set, SSM is not queried. |
| `KAGGLE_TOKEN_PARAM` | – | Name of an SSM SecureString holding the token. Used if `KAGGLE_API_TOKEN` is unset. In AWS this is `/global-climate/kaggle/token`. |
| `KAGGLE_DATASET` | `berkeleyearth/climate-change-earth-surface-temperature-data` | Kaggle dataset handle. |
| `KAGGLE_DATASET_FILE` | `GlobalLandTemperaturesByCity.csv` | File within the dataset. |
| `DATA_BUCKET` | – | Bucket used to build the default output path. |
| `RAW_OUTPUT_PATH` | `s3://<DATA_BUCKET>/raw/temperatures.parquet` | Output path. Can also be a local file path. |

One of `KAGGLE_API_TOKEN` or `KAGGLE_TOKEN_PARAM` is required. If neither `DATA_BUCKET` nor `RAW_OUTPUT_PATH` is set, the output goes to `s3://raw/temperatures.parquet` (a bucket called `raw`, as used with a local MinIO).

## Run locally

```sh
uv sync
mkdir -p ../../data
KAGGLE_API_TOKEN=<token> RAW_OUTPUT_PATH=../../data/raw.parquet uv run main.py
```

`kagglehub` caches the download in `~/.cache/kagglehub`, so repeated runs don't download the dataset again.

## Tests

```sh
uv run pytest
```

[tests/test_schema.py](tests/test_schema.py) checks that the schema accepts a valid frame and rejects frames with a missing column or a wrong data type.

## Deployment notes

- Runs as an AWS Batch job on Fargate Spot with 2 vCPU, 4 GB memory and 30 GiB ephemeral storage (the CSV download needs the extra disk).
- `HOME` is set to `/tmp`, because `kagglehub` writes to `$HOME/.cache` and `/app` is read-only for the container user.
- The task role may only write to `raw/*` and read parameters under `/global-climate/kaggle/*`.
