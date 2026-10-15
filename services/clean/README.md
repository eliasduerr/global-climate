# clean

Turns the raw city temperatures into a typed, validated monthly table: parses dates and coordinates, makes city names unique and drops unreliable rows.

## Input / output

| | Location |
| --- | --- |
| Input | `s3://<DATA_BUCKET>/raw/temperatures.parquet` (written by [ingest](../ingest/README.md)) |
| Output | `s3://<DATA_BUCKET>/interim/temperatures.parquet` |

## Transformation

The steps in [`transform`](main.py), in order:

1. **Rename** columns to snake case.
2. **Disambiguate city names.** Some names occur at several coordinates within the same country. Those cities get their coordinates appended, e.g. `Springfield (39.38N, 89.48W)`, so that `(country, city)` uniquely identifies a location downstream. Unique names are left unchanged.
3. **Cast types.** `dt` becomes a `Date`; `city` and `country` become categoricals.
4. **Drop rows before 1850.** Early measurements are sparse and very uncertain.
5. **Drop months with an uncertainty above 2 °C.** These are treated as unreliable outliers.
6. **Parse coordinates** to signed floats (`52.24N` → `52.24`, `89.48W` → `-89.48`).
7. **Drop rows with missing values.** Gaps are deliberately not interpolated, because linear interpolation between months ignores the seasonal cycle. Years with gaps are later dropped by [features](../features/README.md).

## Output schema

Enforced with `match_to_schema`, so the job fails if the output doesn't match.

| Column | Type |
| --- | --- |
| `dt` | `Date` |
| `avg_temperature` | `Float64` |
| `avg_temperature_uncertainty` | `Float64` |
| `city` | `Categorical` |
| `country` | `Categorical` |
| `latitude` | `Float64` |
| `longitude` | `Float64` |

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `DATA_BUCKET` | – | Bucket used to build the default paths. |
| `RAW_INPUT_PATH` | `s3://<DATA_BUCKET>/raw/temperatures.parquet` | Input path. Can also be a local file path. |
| `CLEAN_OUTPUT_PATH` | `s3://<DATA_BUCKET>/interim/temperatures.parquet` | Output path. Can also be a local file path. |

Without `DATA_BUCKET`, the defaults are `s3://raw/temperatures.parquet` and `s3://interim/temperatures.parquet`.

## Run locally

```sh
uv sync
RAW_INPUT_PATH=../../data/raw.parquet CLEAN_OUTPUT_PATH=../../data/interim.parquet uv run main.py
```

## Tests

```sh
uv run pytest                # all tests
uv run pytest -m "not slow"  # skip the property-based tests
```

[tests/test_transform.py](tests/test_transform.py) has example-based tests for each step above. It also has property-based tests (Hypothesis, marked `slow`) that check invariants on random input: the output matches the schema, has no nulls, only contains dates from 1850 onwards, keeps coordinates within geographic bounds and never has more rows than the input.

## Deployment notes

Runs as an AWS Batch job on Fargate Spot with 2 vCPU and 4 GB memory. The task role may only read `raw/*` and write `interim/*`.
