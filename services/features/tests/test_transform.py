from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import polars as pl
import pytest
from hypothesis import given
from hypothesis import strategies as st
from polars.testing import assert_frame_equal
from polars.testing.parametric import column, dataframes

from main import CLEANED_SCHEMA, FEATURES_SCHEMA, transform

if TYPE_CHECKING:
    from typing import Any


_MIN_GROUP_SIZE = 360


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
        "AverageTemperature": avg,
        "AverageTemperatureUncertainty": unc,
        "City": city,
        "Country": country,
        "Latitude": lat,
        "Longitude": lon,
    }


def _cleaned_lf(rows: list[dict[str, Any]]) -> pl.LazyFrame:
    return pl.LazyFrame(rows, schema=CLEANED_SCHEMA)


def _features_row(
    dt_val: dt.date,
    baseline: float,
    stddev: float,
    yoy: float,
    anomaly: float,
    city: str = "Berlin",
    country: str = "Germany",
) -> dict[str, Any]:
    return {
        "dt": dt_val,
        "Country": country,
        "City": city,
        "30YearBaselineTemperature": baseline,
        "10YearTemperatureStdDev": stddev,
        "YearOverYearChange": yoy,
        "TemperatureAnomaly": anomaly,
    }


def _features_lf(rows: list[dict[str, Any]]) -> pl.LazyFrame:
    return pl.LazyFrame(rows, schema=FEATURES_SCHEMA)


def _monthly_dates(n: int, start: dt.date = dt.date(1900, 1, 1)) -> list[dt.date]:
    return [start + dt.timedelta(days=30 * i) for i in range(n)]


# ---------------------------------------------------------------------------
# Example tests
# ---------------------------------------------------------------------------


def test_constant_temperature_yields_zero_anomaly_and_change():
    dates = _monthly_dates(_MIN_GROUP_SIZE + 40)
    INPUT_LF = _cleaned_lf([_cleaned_row(d, 10.0) for d in dates])

    output_df = transform(INPUT_LF).collect()

    EXPECTED_DF = _features_lf(
        [_features_row(d, 10.0, 0.0, 0.0, 0.0) for d in dates[_MIN_GROUP_SIZE - 1 :]]
    ).collect()
    assert_frame_equal(output_df, EXPECTED_DF)


def test_insufficient_history_produces_empty_output():
    dates = _monthly_dates(_MIN_GROUP_SIZE - 1)
    output_df = transform(_cleaned_lf([_cleaned_row(d, 10.0) for d in dates])).collect()

    assert output_df.is_empty()
    assert output_df.schema == FEATURES_SCHEMA


def test_groups_are_computed_independently():
    dates = _monthly_dates(_MIN_GROUP_SIZE)
    rows: list[dict[str, Any]] = []
    for d in dates:
        rows.append(_cleaned_row(d, 5.0, city="Berlin", country="Germany"))
        rows.append(_cleaned_row(d, 20.0, city="Lima", country="Peru"))

    output_df = transform(_cleaned_lf(rows)).collect().sort(["Country", "City"])

    last_date = dates[-1]
    EXPECTED_DF = (
        _features_lf(
            [
                _features_row(last_date, 5.0, 0.0, 0.0, 0.0, "Berlin", "Germany"),
                _features_row(last_date, 20.0, 0.0, 0.0, 0.0, "Lima", "Peru"),
            ]
        )
        .collect()
        .sort(["Country", "City"])
    )
    assert_frame_equal(output_df, EXPECTED_DF)


def test_year_over_year_change_matches_twelve_month_lag():
    dates = _monthly_dates(_MIN_GROUP_SIZE + 24)
    INPUT_LF = _cleaned_lf([_cleaned_row(d, float(i)) for i, d in enumerate(dates)])
    output_df = transform(INPUT_LF).collect().sort("dt")

    yoy_values = output_df["YearOverYearChange"].to_list()
    assert yoy_values, "expected at least one surviving row"
    assert all(v == pytest.approx(12.0) for v in yoy_values)


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
            "AverageTemperature",
            dtype=pl.Float64,
            strategy=_temperature,
            allow_null=False,
        ),
        column(
            "AverageTemperatureUncertainty",
            dtype=pl.Float64,
            strategy=_uncertainty,
            allow_null=False,
        ),
        column("City", dtype=pl.Categorical(), strategy=_city, allow_null=False),
        column("Country", dtype=pl.Categorical(), strategy=_country, allow_null=False),
        column("Latitude", dtype=pl.Float64, strategy=_latitude, allow_null=False),
        column("Longitude", dtype=pl.Float64, strategy=_longitude, allow_null=False),
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
def test_output_dates_are_subset_of_input_dates(input_lf: pl.LazyFrame) -> None:
    input_df = input_lf.collect()
    output_df = transform(input_lf).collect()
    if output_df.is_empty():
        return
    input_dates = set(input_df["dt"].to_list())
    output_dates = set(output_df["dt"].to_list())
    assert output_dates.issubset(input_dates)
