from __future__ import annotations

import os

import polars as pl

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
FEATURES_SCHEMA = pl.Schema(
    {
        "dt": pl.Date,
        "Country": pl.Categorical(),
        "City": pl.Categorical(),
        "30YearBaselineTemperature": pl.Float64,
        "10YearTemperatureStdDev": pl.Float64,
        "YearOverYearChange": pl.Float64,
        "TemperatureAnomaly": pl.Float64,
    }
)


def transform(lf: pl.LazyFrame) -> pl.LazyFrame:
    return (
        lf.select(
            pl.col("dt"),
            pl.col("Country"),
            pl.col("City"),
            pl.col("AverageTemperature")
            .sort_by("dt")
            .rolling_mean(window_size=360)
            .over(["Country", "City"])
            .alias("30YearBaselineTemperature"),
            pl.col("AverageTemperature")
            .sort_by("dt")
            .rolling_std(window_size=120)
            .over(["Country", "City"])
            .alias("10YearTemperatureStdDev"),
            (
                pl.col("AverageTemperature").sort_by("dt")
                - pl.col("AverageTemperature").sort_by("dt").shift(12)
            )
            .over(["Country", "City"])
            .alias("YearOverYearChange"),
            (
                pl.col("AverageTemperature")
                - pl.col("AverageTemperature")
                .sort_by("dt")
                .rolling_mean(window_size=360)
                .over(["Country", "City"])
            ).alias("TemperatureAnomaly"),
        )
        # Drop nulls from rolling calculations
        .drop_nulls()
    )


def main():
    input_path: str = os.environ.get(
        "CLEANED_INPUT_PATH", "s3://interim/temperatures.parquet"
    )
    output_path: str = os.environ.get(
        "FEATURES_OUTPUT_PATH", "s3://processed/temperatures.parquet"
    )

    # Read raw data from S3
    lf: pl.LazyFrame = pl.scan_parquet(input_path, schema=CLEANED_SCHEMA)

    # Apply transformations
    lf: pl.LazyFrame = lf.pipe(transform)

    # Validate the schema
    lf: pl.LazyFrame = lf.match_to_schema(FEATURES_SCHEMA)

    # Write cleaned data back to S3
    lf.sink_parquet(output_path)


if __name__ == "__main__":
    main()
