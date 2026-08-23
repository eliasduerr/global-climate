from __future__ import annotations

import polars as pl
import pytest

from main import RAW_SCHEMA


def _valid_row() -> dict[str, object]:
    return {
        "dt": "2020-01-01",
        "AverageTemperature": 10.0,
        "AverageTemperatureUncertainty": 0.5,
        "City": "Berlin",
        "Country": "Germany",
        "Latitude": "52.52N",
        "Longitude": "13.40E",
    }


def test_raw_schema_accepts_valid_frame() -> None:
    lf = pl.LazyFrame([_valid_row()], schema=RAW_SCHEMA)
    lf.match_to_schema(RAW_SCHEMA).collect()


def test_raw_schema_rejects_missing_column() -> None:
    row = _valid_row()
    del row["Latitude"]
    lf = pl.LazyFrame([row])
    with pytest.raises(pl.exceptions.SchemaError):
        lf.match_to_schema(RAW_SCHEMA).collect()


def test_raw_schema_rejects_wrong_dtype() -> None:
    row = _valid_row()
    row["AverageTemperature"] = "not a float"
    lf = pl.LazyFrame([row])
    with pytest.raises(pl.exceptions.SchemaError):
        lf.match_to_schema(RAW_SCHEMA).collect()
