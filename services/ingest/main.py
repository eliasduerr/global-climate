from __future__ import annotations

import os

from kagglehub import dataset_load, KaggleDatasetAdapter

def _require_env(name: str) -> str:
    value: str | None = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name!r} is not set")
    return value

def main() -> None:
    storage_options = {
        "endpoint_url": _require_env("S3_ENDPOINT_URL"),
        "aws_access_key_id": _require_env("AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": _require_env("AWS_SECRET_ACCESS_KEY"),
        "aws_region": "eu-central-1",
    }

    dataset = _require_env("KAGGLE_DATASET")
    source_file = _require_env("KAGGLE_DATASET_FILE")
    output_path = os.environ.get("INGEST_OUTPUT_PATH", "data.parquet")

    lf = dataset_load(
        adapter=KaggleDatasetAdapter.POLARS,
        handle=dataset,
        path=source_file,
    )
    lf.sink_parquet(
        output_path,
        storage_options=storage_options
    )

if __name__ == "__main__":
    main()
