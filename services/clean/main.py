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
        "AverageTemperature": pl.Float64,
        "AverageTemperatureUncertainty": pl.Float64,
        "City": pl.Categorical(),
        "Country": pl.Categorical(),
        "Latitude": pl.Float64,
        "Longitude": pl.Float64,
    }
)


def transform(lf: pl.LazyFrame) -> pl.LazyFrame:
    logger.info("Applying transformations ...")
    return (
        lf
        # Cast data types for better performance
        .with_columns(
            pl.col("dt").str.to_date("%Y-%m-%d"),
            pl.col("City").cast(pl.Categorical),
            pl.col("Country").cast(pl.Categorical),
        )
        # Remove unreliable years
        .filter(pl.col("dt").dt.year() >= 1850)
        # Remove outliers
        .with_columns(
            pl.when(pl.col("AverageTemperatureUncertainty") > 2.0)
            .then(None)
            .otherwise(pl.col("AverageTemperature"))
            .alias("AverageTemperature")
        )
        # Interpolate missing values
        .with_columns(
            pl.col("AverageTemperature").interpolate_by("dt").over(["City", "Country"])
        )
        # Cast coordinates to signed floats
        .with_columns(
            (
                pl.col("Latitude").str.strip_chars_end("NS").cast(pl.Float64)
                * pl.when(pl.col("Latitude").str.ends_with("S")).then(-1).otherwise(1)
            ).alias("Latitude"),
            (
                pl.col("Longitude").str.strip_chars_end("EW").cast(pl.Float64)
                * pl.when(pl.col("Longitude").str.ends_with("W")).then(-1).otherwise(1)
            ).alias("Longitude"),
        )
        # Remove missing values (after interpolation)
        .drop_nulls()
    )


def main() -> None:
    input_path: str = os.environ.get(
        "RAW_INPUT_PATH", default="s3://raw/temperatures.parquet"
    )
    output_path: str = os.environ.get(
        "CLEAN_OUTPUT_PATH", default="s3://interim/temperatures.parquet"
    )

    logger.info("Reading raw data from %r ...", input_path)
    lf: pl.LazyFrame = pl.scan_parquet(input_path, schema=RAW_SCHEMA)

    # Apply transformations
    lf: pl.LazyFrame = lf.pipe(transform)

    logger.info("Validating schema and writing cleaned data to %r ...", output_path)
    try:
        lf.match_to_schema(CLEANED_SCHEMA).sink_parquet(output_path)
    except pl.exceptions.SchemaError as e:
        logger.exception("Schema validation failed: %s", e)

    logger.info("Data cleaning completed successfully!")


if __name__ == "__main__":
    main()
