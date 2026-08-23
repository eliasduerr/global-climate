from __future__ import annotations

import logging
import os

import polars as pl


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger: logging.Logger = logging.getLogger(__name__)

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
FEATURES_SCHEMA = pl.Schema(
    {
        "dt": pl.Date,
        "country": pl.Categorical(),
        "city": pl.Categorical(),
        "baseline_temperature_30y": pl.Float64,
        "temperature_stddev_10y": pl.Float64,
        "year_over_year_change": pl.Float64,
        "temperature_anomaly": pl.Float64,
    }
)


def transform(lf: pl.LazyFrame) -> pl.LazyFrame:
    logger.info("Calculating features ...")
    return (
        lf.select(
            pl.col("dt"),
            pl.col("country"),
            pl.col("city"),
            pl.col("avg_temperature")
            .sort_by("dt")
            .rolling_mean(window_size=360)
            .over(["country", "city"])
            .alias("baseline_temperature_30y"),
            pl.col("avg_temperature")
            .sort_by("dt")
            .rolling_std(window_size=120)
            .over(["country", "city"])
            .alias("temperature_stddev_10y"),
            (
                pl.col("avg_temperature").sort_by("dt")
                - pl.col("avg_temperature").sort_by("dt").shift(12)
            )
            .over(["country", "city"])
            .alias("year_over_year_change"),
            (
                pl.col("avg_temperature")
                - pl.col("avg_temperature")
                .sort_by("dt")
                .rolling_mean(window_size=360)
                .over(["country", "city"])
            ).alias("temperature_anomaly"),
        )
        # Drop nulls from rolling calculations
        .drop_nulls()
    )


def main():
    bucket: str | None = os.environ.get("DATA_BUCKET")
    default_input_path: str = (
        f"s3://{bucket}/interim/temperatures.parquet"
        if bucket
        else "s3://interim/temperatures.parquet"
    )
    default_output_path: str = (
        f"s3://{bucket}/processed/temperature-features.parquet"
        if bucket
        else "s3://processed/temperature-features.parquet"
    )
    input_path: str = os.environ.get("CLEANED_INPUT_PATH", default_input_path)
    output_path: str = os.environ.get("FEATURES_OUTPUT_PATH", default_output_path)

    logger.info("Reading cleaned data from %r ...", input_path)
    lf: pl.LazyFrame = pl.scan_parquet(input_path, schema=CLEANED_SCHEMA)

    # Apply transformations
    lf: pl.LazyFrame = lf.pipe(transform)

    logger.info("Validating schema and writing features to %r ...", output_path)
    try:
        lf.match_to_schema(FEATURES_SCHEMA).sink_parquet(output_path)
    except pl.exceptions.SchemaError as e:
        logger.exception("Schema validation failed: %s", e)
        raise

    logger.info("Feature calculation completed successfully!")


if __name__ == "__main__":
    main()
