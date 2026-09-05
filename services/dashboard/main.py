from __future__ import annotations

import datetime as dt
import os

import altair as alt
import polars as pl
import streamlit as st

BUCKET = os.environ.get("DATA_BUCKET", "global-climate-data")
PROCESSED_URI = f"s3://{BUCKET}/processed/temperature-features.parquet"

# A few thousand points per city is well past Altair's default cap.
alt.data_transformers.disable_max_rows()


# Collecting the whole frame needs a few GB, so every query below stays lazy and
# only materialises the rows it actually renders.
def scan() -> pl.LazyFrame:
    return pl.scan_parquet(PROCESSED_URI)


@st.cache_data(ttl=3600, show_spinner="Reading the dataset summary ...")
def load_summary() -> dict:
    row = (
        scan()
        .select(
            pl.len().alias("rows"),
            pl.col("city").n_unique().alias("cities"),
            pl.col("country").n_unique().alias("countries"),
            pl.col("dt").min().alias("first_dt"),
            pl.col("dt").max().alias("last_dt"),
        )
        .collect(engine="streaming")
    )
    return row.to_dicts()[0]


@st.cache_data(ttl=3600, show_spinner="Loading city list ...")
def load_cities() -> list[str]:
    cities = (
        scan()
        .select(pl.col("city").cast(pl.String))
        .unique()
        .collect(engine="streaming")
    )
    return sorted(cities["city"].to_list())


@st.cache_data(ttl=3600, show_spinner="Loading city series ...")
def load_city_series(cities: tuple[str, ...]) -> pl.DataFrame:
    return (
        scan()
        .filter(pl.col("city").cast(pl.String).is_in(list(cities)))
        .select("dt", pl.col("city").cast(pl.String), "temperature_anomaly")
        .collect(engine="streaming")
    )


@st.cache_data(ttl=3600, show_spinner="Ranking cities ...")
def load_top_warming(cutoff: dt.date, limit: int = 20) -> pl.DataFrame:
    return (
        scan()
        .filter(pl.col("dt") >= cutoff)
        .filter(pl.col("temperature_anomaly").is_not_nan())
        .group_by("country", "city")
        .agg(
            pl.col("temperature_anomaly").mean().round(3).alias("avg_anomaly"),
            pl.col("temperature_anomaly").max().round(3).alias("max_anomaly"),
        )
        .sort("avg_anomaly", descending=True)
        .head(limit)
        .with_columns(
            pl.col("country").cast(pl.String),
            pl.col("city").cast(pl.String),
        )
        .collect(engine="streaming")
    )


def main() -> None:
    st.set_page_config(page_title="Global climate", layout="wide")
    st.title("Global climate features")
    st.caption(
        "Rolling baselines and anomalies from the Berkeley Earth "
        "surface temperature dataset."
    )

    summary = load_summary()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rows", f"{summary['rows']:,}")
    col2.metric("Cities", f"{summary['cities']:,}")
    col3.metric("Countries", f"{summary['countries']:,}")
    col4.metric("Date range", f"{summary['first_dt']} → {summary['last_dt']}")

    st.divider()

    st.subheader("City drill-down")
    cities = load_cities()
    default = [c for c in ("Berlin", "Tokyo", "Lima") if c in cities] or cities[:3]
    selected = st.multiselect("Cities", cities, default=default)

    if selected:
        subset = load_city_series(tuple(sorted(selected)))
        chart = (
            alt.Chart(subset)
            .mark_line()
            .encode(
                x=alt.X("dt:T", title="Date"),
                y=alt.Y("temperature_anomaly:Q", title="Anomaly (°C)"),
                color="city:N",
                tooltip=["dt", "city", "temperature_anomaly"],
            )
            .properties(height=400)
        )
        st.altair_chart(chart, use_container_width=True)

    st.divider()

    st.subheader("Top warming cities")
    window_years = st.slider("Window (years back from most recent)", 5, 100, 30)
    latest: dt.date = summary["last_dt"]
    cutoff = dt.date(latest.year - window_years, latest.month, 1)

    st.dataframe(
        load_top_warming(cutoff),
        use_container_width=True,
        hide_index=True,
    )

    st.caption("Data: Berkeley Earth via Kaggle. Baseline = 360-month rolling mean.")


if __name__ == "__main__":
    main()
