# features

Aggregates the cleaned monthly temperatures to one row per city and year, and computes each year's temperature anomaly against the city's 1951–1980 average.

## Input / output

| | Location |
| --- | --- |
| Input | `s3://<DATA_BUCKET>/interim/temperatures.parquet` (written by [clean](../clean/README.md)) |
| Output | `s3://<DATA_BUCKET>/processed/city-annual.parquet` |

The output is read by the [dashboard](../dashboard/README.md) and registered in the Glue Data Catalog as the table `global_climate.city_annual`, so Athena can query it.

## Method

The steps in [`transform`](main.py):

1. **Annual mean.** Group by `(year, country, city)` and average the monthly temperatures.
2. **Complete years only.** Keep only years with all 12 months. A year with only winter months would be biased too cold, so only complete years cancel out the seasonal cycle.
3. **Anomaly.** Subtract the city's mean annual temperature over the reference period 1951–1980, the reference period used by Berkeley Earth and NASA GISS:

   $$\text{anomaly}_{c,y} = T_{c,y} - \frac{1}{|R_c|} \sum_{y' \in R_c} T_{c,y'}$$

   where $T_{c,y}$ is the annual mean of city $c$ in year $y$ and $R_c$ are the complete years of city $c$ within 1951–1980.
4. **Drop cities without a baseline.** Cities with no complete year in 1951–1980 have no anomaly and are removed.
5. Sort by `country`, `city` and `year`.

Anomalies make cities comparable: a city's climate (e.g. Oslo vs. Cairo) cancels out, leaving only its change over time.

## Output schema

Enforced with `match_to_schema`. It must match the Glue table in [infra/catalog.tf](../../infra/catalog.tf).

| Column | Type | Description |
| --- | --- | --- |
| `year` | `Int32` | Calendar year |
| `country` | `Categorical` | Country name |
| `city` | `Categorical` | City name, unique within a country |
| `latitude` | `Float64` | Signed latitude |
| `longitude` | `Float64` | Signed longitude |
| `annual_temperature` | `Float64` | Mean of the 12 monthly averages (°C) |
| `temperature_anomaly` | `Float64` | Difference from the city's 1951–1980 mean (°C) |

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `DATA_BUCKET` | – | Bucket used to build the default paths. |
| `CLEANED_INPUT_PATH` | `s3://<DATA_BUCKET>/interim/temperatures.parquet` | Input path. Can also be a local file path. |
| `FEATURES_OUTPUT_PATH` | `s3://<DATA_BUCKET>/processed/city-annual.parquet` | Output path. Can also be a local file path. |

Without `DATA_BUCKET`, the defaults are `s3://interim/temperatures.parquet` and `s3://processed/city-annual.parquet`.

## Run locally

```sh
uv sync
CLEANED_INPUT_PATH=../../data/interim.parquet FEATURES_OUTPUT_PATH=../../data/city-annual.parquet uv run main.py
```

## Tests

```sh
uv run pytest                # all tests
uv run pytest -m "not slow"  # skip the property-based tests
```

[tests/test_transform.py](tests/test_transform.py) has example-based tests for these cases:

- A constant temperature gives a zero anomaly.
- The seasonal cycle doesn't leak into the anomaly.
- The anomaly is relative to the reference-period mean.
- Incomplete years are dropped.
- Cities without reference data are dropped.
- Cities are computed independently of each other.

The property-based tests (Hypothesis, marked `slow`) check that the output matches the schema, has no nulls, never has more rows than the input and contains only years present in the input.

## Deployment notes

Runs as an AWS Batch job on Fargate Spot with 2 vCPU and 8 GB memory. It gets more memory than the other stages because of the group-by aggregation. The task role may only read `interim/*` and write `processed/*`.
