from __future__ import annotations

import os

import polars as pl


def main():
    input_path: str = os.environ.get(
        "CLEANED_INPUT_PATH", "s3://interim/temperatures.parquet"
    )
    output_path: str = os.environ.get(
        "FEATURES_OUTPUT_PATH", "s3://processed/temperatures.parquet"
    )

    (
        # Read cleaned data from S3
        pl.scan_parquet(input_path)
        .select(
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
            (pl.col("AverageTemperature").sort_by("dt") - pl.col("AverageTemperature").sort_by("dt").shift(12))
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
        # Write features data back to S3
        .sink_parquet(output_path)
    )


if __name__ == "__main__":
    main()
