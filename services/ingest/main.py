from __future__ import annotations

import os

from kagglehub import dataset_load, KaggleDatasetAdapter


def main() -> None:
    dataset = os.environ.get(
        "KAGGLE_DATASET",
        default="berkeleyearth/climate-change-earth-surface-temperature-data",
    )
    source_file = os.environ.get(
        "KAGGLE_DATASET_FILE", default="GlobalLandTemperaturesByCity.csv"
    )

    output_path = os.environ.get(
        "RAW_OUTPUT_PATH", default="s3://raw/temperatures.parquet"
    )

    dataset_load(
        adapter=KaggleDatasetAdapter.POLARS,
        handle=dataset,
        path=source_file,
    ).sink_parquet(output_path)


if __name__ == "__main__":
    main()
