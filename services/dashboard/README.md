# dashboard

A Streamlit app that visualizes the processed city-level temperature anomalies.

## What it shows

- **Headline metrics:** the number of cities, the mean anomaly over the last ten years and the median city trend since 1950.
- **Global mean anomaly:** a bar chart of the yearly anomaly averaged over all cities with a complete year. This is a plain mean over cities, not an area-weighted global average, so regions with many cities (Europe, North America) dominate.
- **Warming trend since 1950:** a world map with one dot per city, coloured by its linear trend in °C per decade. The trend is the least-squares slope of the anomaly against the year, times 10.
- **City drill-down:** the yearly anomaly of a single city, selected by country and city. It defaults to Berlin, Germany.

## Input

`s3://<DATA_BUCKET>/processed/city-annual.parquet`, written by [features](../features/README.md). The data is cached for one hour, so a new pipeline run shows up within an hour at most.

The world map's country outlines are loaded by the browser from the jsDelivr CDN (`world-atlas`), so the map needs internet access on the client side.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `DATA_BUCKET` | `global-climate-data` | Bucket used to build the default `PROCESSED_URI`. |
| `PROCESSED_URI` | `s3://<DATA_BUCKET>/processed/city-annual.parquet` | Path of the processed table. Can also be a local file path. |

Reading from S3 uses the standard AWS credential chain (environment variables, `~/.aws`, or the task role in ECS).

## Run locally

Against a local file produced by the pipeline:

```sh
uv sync
PROCESSED_URI=../../data/city-annual.parquet uv run streamlit run main.py
```

Against the deployed bucket, with AWS credentials in your environment:

```sh
AWS_REGION=eu-central-1 uv run streamlit run main.py
```

Or with Docker, which serves on port 8080 like in AWS:

```sh
docker build -t global-climate-dashboard .
docker run --rm -p 8080:8080 -v "$PWD/../../data:/data:ro" \
  -e PROCESSED_URI=/data/city-annual.parquet global-climate-dashboard
```

## Tests

```sh
uv run pytest
```

[tests/test_app.py](tests/test_app.py) is a smoke test that checks the module imports.

## Deployment notes

- Runs as an ECS Express Gateway service, not through AWS Batch. ECS Express provisions the HTTPS endpoint, which is printed by `terraform output dashboard_endpoints`.
- The service uses 1 vCPU and 2 GB memory, and scales between 1 and 2 tasks at 60 % average CPU.
- The container listens on port 8080. The health check uses Streamlit's `/_stcore/health`.
- The task role can only read `processed/*` from the data bucket.
