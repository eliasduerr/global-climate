from __future__ import annotations

import logging
import os

import boto3
import polars as pl
from kagglehub import KaggleDatasetAdapter, dataset_load

RAW_SCHEMA = pl.Schema(
    {
        "dt": pl.Utf8,
        "AverageTemperature": pl.Float64,
        "AverageTemperatureUncertainty": pl.Float64,
        "City": pl.Utf8,
        "Country": pl.Utf8,
        "Latitude": pl.Utf8,
        "Longitude": pl.Utf8,
    }
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger: logging.Logger = logging.getLogger(__name__)

ssm = boto3.client("ssm")


def _get_kaggle_token_from_ssm() -> None:
    if os.environ.get("KAGGLE_API_TOKEN"):
        msg = "KAGGLE_API_TOKEN environment variable is already set. Skipping retrieval from SSM."
        logger.warning(msg)
        return None

    param_name: str | None = os.environ.get("KAGGLE_TOKEN_PARAM")
    if not param_name:
        msg = "KAGGLE_TOKEN_PARAM environment variable is not set. Skipping retrieval from SSM."
        logger.warning(msg)
        return None

    response: dict[str, dict[str, str]] = ssm.get_parameter(
        Name=param_name, WithDecryption=True
    )
    os.environ["KAGGLE_API_TOKEN"] = response["Parameter"]["Value"]


def main() -> None:
    _get_kaggle_token_from_ssm()

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

    logger.info("Loading %r from Kaggle dataset %r ...", source_file, dataset)
    lf: pl.LazyFrame = dataset_load(
        adapter=KaggleDatasetAdapter.POLARS,
        handle=dataset,
        path=source_file,
    )

    logger.info("Validating schema and writing raw data to %r ...", output_path)
    try:
        lf.match_to_schema(RAW_SCHEMA).sink_parquet(output_path)
    except pl.exceptions.SchemaError as e:
        logger.exception("Schema validation failed: %s", e)
        raise

    logger.info("Ingest completed successfully!")


if __name__ == "__main__":
    main()
