from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import polars as pl
import pytest
from hypothesis import given
from hypothesis import strategies as st
from polars.testing import assert_frame_equal
from polars.testing.parametric import column, dataframes

from main import (
    CLEANED_SCHEMA,
    FEATURES_SCHEMA,
    REFERENCE_END,
    REFERENCE_START,
    transform,
)

if TYPE_CHECKING:
    from typing import Any


def _cleaned_row(
    dt_val: dt.date,
    avg: float,
    unc: float = 0.1,
    city: str = "Berlin",
    country: str = "Germany",
    lat: float = 52.24,
    lon: float = 13.04,
) -> dict[str, Any]:
    return {
        "dt": dt_val,
        "avg_temperature": avg,
        "avg_temperature_uncertainty": unc,
        "city": city,
        "country": country,
        "latitude": lat,
        "longitude": lon,
    }


def _cleaned_lf(rows: list[dict[str, Any]]) -> pl.LazyFrame:
    return pl.LazyFrame(rows, schema=CLEANED_SCHEMA)


def _features_row(
    year: int,
    temperature: float,
    anomaly: float,
    city: str = "Berlin",
    country: str = "Germany",
    lat: float = 52.24,
    lon: float = 13.04,
) -> dict[str, Any]:
    return {
        "year": year,
        "country": country,
        "city": city,
        "latitude": lat,
        "longitude": lon,
        "annual_temperature": temperature,
        "temperature_anomaly": anomaly,
    }


def _features_lf(rows: list[dict[str, Any]]) -> pl.LazyFrame:
    return pl.LazyFrame(rows, schema=FEATURES_SCHEMA)


def _monthly_dates(start_year: int, end_year: int) -> list[dt.date]:
    return [
        dt.date(y, m, 1) for y in range(start_year, end_year + 1) for m in range(1, 13)
    ]


def test_constant_temperature_yields_zero_anomaly():
    dates = _monthly_dates(1950, 1985)
    output_df = transform(_cleaned_lf([_cleaned_row(d, 10.0) for d in dates])).collect()

    EXPECTED_DF = _features_lf(
        [_features_row(y, 10.0, 0.0) for y in range(1950, 1986)]
    ).collect()
    assert_frame_equal(output_df, EXPECTED_DF)


def test_seasonal_cycle_does_not_leak_into_anomaly():
    dates = _monthly_dates(1950, 1985)
    rows = [
        _cleaned_row(d, 10.0 + (10.0 if d.month in (6, 7, 8) else -10.0 / 3))
        for d in dates
    ]
    output_df = transform(_cleaned_lf(rows)).collect()

    assert output_df["temperature_anomaly"].abs().max() == pytest.approx(0.0, abs=1e-9)


def test_anomaly_is_relative_to_reference_period_mean():
    dates = _monthly_dates(1950, 1985)
    rows = [_cleaned_row(d, float(d.year)) for d in dates]
    output_df = transform(_cleaned_lf(rows)).collect()

    expected = {y: y - (REFERENCE_START + REFERENCE_END) / 2 for y in range(1950, 1986)}
    for year, anomaly in output_df.select("year", "temperature_anomaly").iter_rows():
        assert anomaly == pytest.approx(expected[year])


def test_incomplete_years_are_dropped():
    dates = [d for d in _monthly_dates(1950, 1985) if d != dt.date(1960, 6, 1)]
    output_df = transform(_cleaned_lf([_cleaned_row(d, 10.0) for d in dates])).collect()

    assert 1960 not in output_df["year"].to_list()
    assert output_df.height == 35


def test_no_reference_data_produces_empty_output():
    dates = _monthly_dates(1981, 2000)
    output_df = transform(_cleaned_lf([_cleaned_row(d, 10.0) for d in dates])).collect()

    assert output_df.is_empty()
    assert output_df.schema == FEATURES_SCHEMA


def test_groups_are_computed_independently():
    rows: list[dict[str, Any]] = []
    for d in _monthly_dates(1951, 1980):
        rows.append(_cleaned_row(d, 5.0, city="Berlin", country="Germany"))
        rows.append(
            _cleaned_row(d, 20.0, city="Lima", country="Peru", lat=-12.0, lon=-77.0)
        )

    output_df = transform(_cleaned_lf(rows)).collect()

    assert output_df["temperature_anomaly"].abs().max() == pytest.approx(0.0)
    per_city = output_df.group_by("city").agg(pl.col("annual_temperature").mean())
    assert dict(per_city.iter_rows()) == {"Berlin": 5.0, "Lima": 20.0}


_dt_value = st.dates(min_value=dt.date(1850, 1, 1), max_value=dt.date(2020, 12, 31))
_temperature = st.floats(
    min_value=-80.0, max_value=60.0, allow_nan=False, allow_infinity=False
)
_uncertainty = st.floats(
    min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False
)
_city = st.sampled_from(["Berlin", "Paris", "Tokyo", "Lima", "Oslo"])
_country = st.sampled_from(["Germany", "France", "Japan", "Peru", "Norway"])
_latitude = st.floats(
    min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False
)
_longitude = st.floats(
    min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False
)

_cleaned_lazyframes = dataframes(
    cols=[
        column("dt", dtype=pl.Date, strategy=_dt_value, allow_null=False),
        column(
            "avg_temperature",
            dtype=pl.Float64,
            strategy=_temperature,
            allow_null=False,
        ),
        column(
            "avg_temperature_uncertainty",
            dtype=pl.Float64,
            strategy=_uncertainty,
            allow_null=False,
        ),
        column("city", dtype=pl.Categorical(), strategy=_city, allow_null=False),
        column("country", dtype=pl.Categorical(), strategy=_country, allow_null=False),
        column("latitude", dtype=pl.Float64, strategy=_latitude, allow_null=False),
        column("longitude", dtype=pl.Float64, strategy=_longitude, allow_null=False),
    ],
    min_size=0,
    max_size=50,
    allow_chunks=False,
    lazy=True,
)


@pytest.mark.slow
@given(input_lf=_cleaned_lazyframes)
def test_output_schema_matches_contract(input_lf: pl.LazyFrame) -> None:
    output_df = transform(input_lf).collect()
    assert output_df.schema == FEATURES_SCHEMA


@pytest.mark.slow
@given(input_lf=_cleaned_lazyframes)
def test_output_has_no_nulls(input_lf: pl.LazyFrame) -> None:
    output_df = transform(input_lf).collect()
    assert output_df.null_count().sum_horizontal().item() == 0


@pytest.mark.slow
@given(input_lf=_cleaned_lazyframes)
def test_transform_is_non_amplifying(input_lf: pl.LazyFrame) -> None:
    output_df = transform(input_lf).collect()
    assert output_df.height <= input_lf.collect().height


@pytest.mark.slow
@given(input_lf=_cleaned_lazyframes)
def test_output_years_are_subset_of_input_years(input_lf: pl.LazyFrame) -> None:
    input_df = input_lf.collect()
    output_df = transform(input_lf).collect()
    if output_df.is_empty():
        return
    input_years = set(input_df["dt"].dt.year().to_list())
    output_years = set(output_df["year"].to_list())
    assert output_years.issubset(input_years)
