from __future__ import annotations

import os
import logging

import polars as pl

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger: logging.Logger = logging.getLogger(__name__)

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

CLEANED_SCHEMA = pl.Schema(
    {
        "dt": pl.Date,
        "avg_temperature": pl.Float64,
        "avg_temperature_uncertainty": pl.Float64,
        "city": pl.Categorical(),
        "country": pl.Categorical(),
        "latitude": pl.Float64,
        "longitude": pl.Float64,
    }
)


def _get_input_path() -> str:
    bucket: str | None = os.environ.get("DATA_BUCKET")
    default_input_path: str = (
        f"s3://{bucket}/raw/temperatures.parquet"
        if bucket
        else "s3://raw/temperatures.parquet"
    )
    return os.environ.get("RAW_INPUT_PATH", default_input_path)


def _get_output_path() -> str:
    bucket: str | None = os.environ.get("DATA_BUCKET")
    default_output_path: str = (
        f"s3://{bucket}/interim/temperatures.parquet"
        if bucket
        else "s3://interim/temperatures.parquet"
    )
    return os.environ.get("CLEAN_OUTPUT_PATH", default_output_path)


def transform(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Clean the raw data.

    Column names are standardized to snake case.
    Date column is parsed, city and country are cast to categoricals.
    Unreliable early dates before 1850 are dropped.
    Temperature values with an uncertainty above 2 °C are nulled.
    Missing values (including the nulled ones) are linearly interpolated over time.
    String coordinates are parsed to signed floats.
    Remaining nulls are dropped.

    Args:
        lf: Raw monthly temperatures per city.

    Returns:
        Cleaned monthly temperatures per city.
    """
    logger.info("Applying transformations ...")
    return (
        lf.rename(
            {
                "AverageTemperature": "avg_temperature",
                "AverageTemperatureUncertainty": "avg_temperature_uncertainty",
                "City": "city",
                "Country": "country",
                "Latitude": "latitude",
                "Longitude": "longitude",
            }
        )
        # Cast data types for better performance
        .with_columns(
            pl.col("dt").str.to_date("%Y-%m-%d"),
            pl.col("city").cast(pl.Categorical),
            pl.col("country").cast(pl.Categorical),
        )
        # Remove unreliable years
        .filter(pl.col("dt").dt.year() >= 1850)
        # Remove outliers
        .with_columns(
            pl.when(pl.col("avg_temperature_uncertainty") > 2.0)
            .then(None)
            .otherwise(pl.col("avg_temperature"))
            .alias("avg_temperature")
        )
        # Interpolate missing values
        .with_columns(
            pl.col("avg_temperature").interpolate_by("dt").over(["city", "country"])
        )
        # Cast coordinates to signed floats
        .with_columns(
            (
                pl.col("latitude").str.strip_chars_end("NS").cast(pl.Float64)
                * pl.when(pl.col("latitude").str.ends_with("S")).then(-1).otherwise(1)
            ).alias("latitude"),
            (
                pl.col("longitude").str.strip_chars_end("EW").cast(pl.Float64)
                * pl.when(pl.col("longitude").str.ends_with("W")).then(-1).otherwise(1)
            ).alias("longitude"),
        )
        # Remove missing values (after interpolation)
        .drop_nulls()
    )


def main() -> None:
    input_path: str = _get_input_path()
    output_path: str = _get_output_path()

    logger.info("Reading raw data from %r ...", input_path)
    lf: pl.LazyFrame = pl.scan_parquet(input_path, schema=RAW_SCHEMA)

    # Apply transformations
    lf: pl.LazyFrame = lf.pipe(transform)

    logger.info("Validating schema and writing cleaned data to %r ...", output_path)
    try:
        lf.match_to_schema(CLEANED_SCHEMA).sink_parquet(output_path)
    except pl.exceptions.SchemaError as e:
        logger.exception("Schema validation failed: %s", e)
        raise

    logger.info("Data cleaning completed successfully!")


if __name__ == "__main__":
    main()
