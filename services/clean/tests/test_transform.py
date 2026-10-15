from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import polars as pl
import pytest
from hypothesis import given, strategies as st
from polars.testing import assert_frame_equal
from polars.testing.parametric import column, dataframes

from main import CLEANED_SCHEMA, RAW_SCHEMA, transform

if TYPE_CHECKING:
    from typing import Any


def _raw_row(
    dt_str: str,
    avg: float | None,
    unc: float | None,
    city: str = "Berlin",
    country: str = "Germany",
    lat: str = "52.24N",
    lon: str = "13.04E",
) -> dict[str, Any]:
    return {
        "dt": dt_str,
        "AverageTemperature": avg,
        "AverageTemperatureUncertainty": unc,
        "City": city,
        "Country": country,
        "Latitude": lat,
        "Longitude": lon,
    }


def _raw_lf(rows: list[dict[str, Any]]) -> pl.LazyFrame:
    return pl.LazyFrame(rows, schema=RAW_SCHEMA)


def _cleaned_row(
    dt_str: dt.date,
    avg: float | None,
    unc: float | None,
    city: str = "Berlin",
    country: str = "Germany",
    lat: float = 52.24,
    lon: float = 13.04,
) -> dict[str, Any]:
    return {
        "dt": dt_str,
        "avg_temperature": avg,
        "avg_temperature_uncertainty": unc,
        "city": city,
        "country": country,
        "latitude": lat,
        "longitude": lon,
    }


def _cleaned_lf(rows: list[dict[str, Any]]) -> pl.LazyFrame:
    return pl.LazyFrame(rows, schema=CLEANED_SCHEMA)


def test_filters_pre_1850_rows():
    INPUT_LF: pl.LazyFrame = _raw_lf(
        [
            _raw_row("1700-01-01", 5.0, 0.5),
            _raw_row("1849-12-01", 5.0, 0.5),
            _raw_row("1850-01-01", 5.0, 0.5),
            _raw_row("2000-06-01", 18.0, 0.3),
        ]
    )
    output_df = transform(INPUT_LF).collect()

    EXPECTED_DF: pl.LazyFrame = _cleaned_lf(
        [
            _cleaned_row(dt.date(1850, 1, 1), 5.0, 0.5),
            _cleaned_row(dt.date(2000, 6, 1), 18.0, 0.3),
        ]
    ).collect()

    assert_frame_equal(output_df, EXPECTED_DF)


def test_coordinate_signs_for_all_hemispheres():
    INPUT_LF: pl.LazyFrame = _raw_lf(
        [
            _raw_row("1900-01-01", 1.0, 0.1, city="N", lat="10.0N", lon="20.0E"),
            _raw_row("1900-01-01", 1.0, 0.1, city="S", lat="10.0S", lon="20.0W"),
        ]
    )
    output_df = transform(INPUT_LF).collect().sort("city")

    EXPECTED_DF: pl.LazyFrame = _cleaned_lf(
        [
            _cleaned_row(dt.date(1900, 1, 1), 1.0, 0.1, city="N", lat=10.0, lon=20.0),
            _cleaned_row(dt.date(1900, 1, 1), 1.0, 0.1, city="S", lat=-10.0, lon=-20.0),
        ]
    ).collect()

    assert_frame_equal(output_df, EXPECTED_DF)


def test_high_uncertainty_values_are_dropped():
    INPUT_LF: pl.LazyFrame = _raw_lf(
        [
            _raw_row("1900-01-01", 10.0, 0.1),
            _raw_row("1900-02-01", 999.0, 5.0),
            _raw_row("1900-03-01", 30.0, 2.0),
        ]
    )
    output_df = transform(INPUT_LF).collect().sort("dt")

    EXPECTED_DF: pl.LazyFrame = _cleaned_lf(
        [
            _cleaned_row(dt.date(1900, 1, 1), 10.0, 0.1),
            _cleaned_row(dt.date(1900, 3, 1), 30.0, 2.0),
        ]
    ).collect()

    assert_frame_equal(output_df, EXPECTED_DF)


def test_missing_values_are_dropped_not_interpolated():
    INPUT_LF: pl.LazyFrame = _raw_lf(
        [
            _raw_row("1900-01-01", 10.0, 0.1),
            _raw_row("1900-02-01", None, None),
            _raw_row("1900-03-01", 30.0, 0.1),
        ]
    )
    output_df = transform(INPUT_LF).collect().sort("dt")

    EXPECTED_DF: pl.LazyFrame = _cleaned_lf(
        [
            _cleaned_row(dt.date(1900, 1, 1), 10.0, 0.1),
            _cleaned_row(dt.date(1900, 3, 1), 30.0, 0.1),
        ]
    ).collect()

    assert_frame_equal(output_df, EXPECTED_DF)


def test_only_ambiguous_city_names_get_coordinates():
    INPUT_LF: pl.LazyFrame = _raw_lf(
        [
            _raw_row("1900-01-01", 1.0, 0.1, city="Berlin"),
            _raw_row("1900-01-01", 1.0, 0.1, city="Springfield", lat="39.38N"),
            _raw_row("1900-01-01", 1.0, 0.1, city="Springfield", lat="42.59N"),
        ]
    )
    output_df = transform(INPUT_LF).collect()

    assert sorted(output_df["city"].cast(pl.String).to_list()) == [
        "Berlin",
        "Springfield (39.38N, 13.04E)",
        "Springfield (42.59N, 13.04E)",
    ]


_dt_str = st.dates(min_value=dt.date(1700, 1, 1), max_value=dt.date(2020, 12, 31)).map(
    lambda d: d.isoformat()
)
_temperature = st.floats(
    min_value=-80.0, max_value=60.0, allow_nan=False, allow_infinity=False
)
_uncertainty = st.floats(
    min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False
)
_city = st.sampled_from(["Berlin", "Paris", "Tokyo", "Lima", "Oslo"])
_country = st.sampled_from(["Germany", "France", "Japan", "Peru", "Norway"])
_latitude_str = st.builds(
    lambda v, h: f"{v:.4f}{h}",
    st.floats(min_value=0.0, max_value=90.0, allow_nan=False, allow_infinity=False),
    st.sampled_from(["N", "S"]),
)
_longitude_str = st.builds(
    lambda v, h: f"{v:.4f}{h}",
    st.floats(min_value=0.0, max_value=180.0, allow_nan=False, allow_infinity=False),
    st.sampled_from(["E", "W"]),
)

_raw_lazyframes = dataframes(
    cols=[
        column("dt", dtype=pl.Utf8, strategy=_dt_str, allow_null=False),
        column(
            "AverageTemperature",
            dtype=pl.Float64,
            strategy=_temperature,
            allow_null=True,
        ),
        column(
            "AverageTemperatureUncertainty",
            dtype=pl.Float64,
            strategy=_uncertainty,
            allow_null=False,
        ),
        column("City", dtype=pl.Utf8, strategy=_city, allow_null=False),
        column("Country", dtype=pl.Utf8, strategy=_country, allow_null=False),
        column("Latitude", dtype=pl.Utf8, strategy=_latitude_str, allow_null=False),
        column("Longitude", dtype=pl.Utf8, strategy=_longitude_str, allow_null=False),
    ],
    min_size=0,
    max_size=50,
    allow_chunks=False,
    lazy=True,
)


@pytest.mark.slow
@given(input_lf=_raw_lazyframes)
def test_output_schema_matches_contract(input_lf: pl.LazyFrame) -> None:
    output_df = transform(input_lf).collect()
    assert output_df.schema == CLEANED_SCHEMA


@pytest.mark.slow
@given(input_lf=_raw_lazyframes)
def test_output_has_no_nulls(input_lf: pl.LazyFrame) -> None:
    output_df = transform(input_lf).collect()
    assert output_df.null_count().sum_horizontal().item() == 0


@pytest.mark.slow
@given(input_lf=_raw_lazyframes)
def test_all_output_dates_are_post_1850(input_lf: pl.LazyFrame) -> None:
    output_df = transform(input_lf).collect()
    if output_df.height > 0:
        assert output_df["dt"].dt.year().min() >= 1850


@pytest.mark.slow
@given(input_lf=_raw_lazyframes)
def test_coordinates_stay_within_geographic_bounds(input_lf: pl.LazyFrame) -> None:
    output_df = transform(input_lf).collect()
    if output_df.height > 0:
        assert output_df["latitude"].min() >= -90.0
        assert output_df["latitude"].max() <= 90.0
        assert output_df["longitude"].min() >= -180.0
        assert output_df["longitude"].max() <= 180.0


@pytest.mark.slow
@given(input_lf=_raw_lazyframes)
def test_transform_is_non_amplifying(input_lf: pl.LazyFrame) -> None:
    output_df = transform(input_lf).collect()
    assert output_df.height <= input_lf.collect().height
