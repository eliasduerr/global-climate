from __future__ import annotations

import logging
import os

import polars as pl


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger: logging.Logger = logging.getLogger(__name__)

REFERENCE_START = 1951
"""Start of the reference period according to Berkeley Earth and NASA GISS."""
REFERENCE_END = 1980
"""End of the reference period according to Berkeley Earth and NASA GISS."""

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
        "year": pl.Int32,
        "country": pl.Categorical(),
        "city": pl.Categorical(),
        "latitude": pl.Float64,
        "longitude": pl.Float64,
        "annual_temperature": pl.Float64,
        "temperature_anomaly": pl.Float64,
    }
)


def _get_input_path() -> str:
    bucket: str | None = os.environ.get("DATA_BUCKET")
    default_input_path: str = (
        f"s3://{bucket}/interim/temperatures.parquet"
        if bucket
        else "s3://interim/temperatures.parquet"
    )
    return os.environ.get("CLEANED_INPUT_PATH", default_input_path)


def _get_output_path() -> str:
    bucket: str | None = os.environ.get("DATA_BUCKET")
    default_output_path: str = (
        f"s3://{bucket}/processed/city-annual.parquet"
        if bucket
        else "s3://processed/city-annual.parquet"
    )
    return os.environ.get("FEATURES_OUTPUT_PATH", default_output_path)


def transform(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Calculates the features from the cleaned data.

    Groups per year and city, then computes the `annual_temperature` by averaging over the monthly temperature averages.
    Incomplete years are dropped, as these would be biased towards the present months (e.g. too cold if only winter month are present).
    The anomaly is calculated by subtracting the average of the 1951-1980 period from each year's average.
    Cities without a baseline are dropped.

    Args:
        lf: Cleaned monthly temperatures.

    Returns:
        One row per city and year with the average temperature and the temperature anomaly.
    """
    logger.info("Calculating features ...")
    in_reference = pl.col("year").is_between(REFERENCE_START, REFERENCE_END)
    return (
        lf.group_by(pl.col("dt").dt.year().alias("year"), "country", "city")
        .agg(
            pl.col("latitude").first(),
            pl.col("longitude").first(),
            pl.col("avg_temperature").mean().alias("annual_temperature"),
            pl.len().alias("n_months"),
        )
        .filter(pl.col("n_months") == 12)
        .drop("n_months")
        .with_columns(
            (
                pl.col("annual_temperature")
                - pl.col("annual_temperature")
                .filter(in_reference)
                .mean()
                .over(["country", "city"])
            ).alias("temperature_anomaly")
        )
        .drop_nulls("temperature_anomaly")
        .sort("country", "city", "year")
    )


def main():
    input_path: str = _get_input_path()
    output_path: str = _get_output_path()

    logger.info("Reading cleaned data from %r ...", input_path)
    lf: pl.LazyFrame = pl.scan_parquet(input_path, schema=CLEANED_SCHEMA)

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
