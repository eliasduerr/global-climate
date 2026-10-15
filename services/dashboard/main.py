from __future__ import annotations

import os

import altair as alt
import polars as pl
import streamlit as st

BUCKET = os.environ.get("DATA_BUCKET", "global-climate-data")
PROCESSED_URI = os.environ.get(
    "PROCESSED_URI", f"s3://{BUCKET}/processed/city-annual.parquet"
)
TREND_START = 1950
WORLD_TOPOJSON = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json"

alt.data_transformers.disable_max_rows()

DIVERGING = alt.Scale(scheme="redblue", reverse=True, domainMid=0)


@st.cache_data(ttl=3600, show_spinner="Loading data ...")
def load_data() -> pl.DataFrame:
    return pl.read_parquet(PROCESSED_URI).with_columns(
        pl.col("country", "city").cast(pl.String)
    )


@st.cache_data(ttl=3600)
def city_trends(df: pl.DataFrame) -> pl.DataFrame:
    """Computes the linear regression slope (°C per decade) for each city since 1950."""
    year = pl.col("year").cast(pl.Float64)
    return (
        df.filter(pl.col("year") >= TREND_START)
        .group_by("country", "city")
        .agg(
            pl.col("latitude").first(),
            pl.col("longitude").first(),
            (pl.cov(year, pl.col("temperature_anomaly")) / year.var() * 10).alias(
                "trend_per_decade"
            ),
        )
        .drop_nulls()
    )


def anomaly_bars(df: pl.DataFrame) -> alt.Chart:
    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X(
                "year:Q",
                title="Year",
                axis=alt.Axis(format="d"),
                scale=alt.Scale(zero=False),
            ),
            y=alt.Y("temperature_anomaly:Q", title="Anomaly vs 1951-1980 (°C)"),
            color=alt.Color("temperature_anomaly:Q", scale=DIVERGING, legend=None),
            tooltip=[
                alt.Tooltip("year:Q", format="d"),
                alt.Tooltip("temperature_anomaly:Q", format="+.2f", title="Anomaly"),
            ],
        )
        .properties(height=300)
    )


def main() -> None:
    st.set_page_config(page_title="Global climate", layout="wide")
    st.title("How much have cities warmed?")
    st.caption(
        "Berkeley Earth city temperatures. Each year is compared with the city's "
        "own 1951-1980 average."
    )

    df = load_data()
    trends = city_trends(df)

    global_mean = (
        df.group_by("year").agg(pl.col("temperature_anomaly").mean()).sort("year")
    )
    last_decade = global_mean.filter(pl.col("year") > global_mean["year"].max() - 10)

    c1, c2, c3 = st.columns(3)
    c1.metric("Cities", f"{trends.height:,}")
    c2.metric(
        f"Mean anomaly {last_decade['year'].min()}-{last_decade['year'].max()}",
        f"{last_decade['temperature_anomaly'].mean():+.2f} °C",
    )
    c3.metric(
        f"Median city trend since {TREND_START}",
        f"{trends['trend_per_decade'].median():+.2f} °C / decade",
    )

    st.subheader("Global mean anomaly")
    st.caption("Average of all cities with a complete year of data.")
    st.altair_chart(anomaly_bars(global_mean), width="stretch")

    st.subheader(f"Warming trend since {TREND_START}")
    world = alt.Chart(alt.topo_feature(WORLD_TOPOJSON, "countries")).mark_geoshape(
        fill="#eeeeee", stroke="white"
    )
    points = (
        alt.Chart(trends)
        .mark_circle(size=25)
        .encode(
            longitude="longitude:Q",
            latitude="latitude:Q",
            color=alt.Color("trend_per_decade:Q", scale=DIVERGING, title="°C / decade"),
            tooltip=[
                "city",
                "country",
                alt.Tooltip("trend_per_decade:Q", format="+.2f"),
            ],
        )
    )
    st.altair_chart(
        (world + points).project("equalEarth").properties(height=450), width="stretch"
    )

    st.subheader("City drill-down")
    col1, col2 = st.columns(2)
    countries = sorted(df["country"].unique())
    country = col1.selectbox("Country", countries, index=countries.index("Germany"))
    cities = sorted(df.filter(pl.col("country") == country)["city"].unique())
    city = col2.selectbox(
        "City", cities, index=cities.index("Berlin") if "Berlin" in cities else 0
    )
    st.altair_chart(
        anomaly_bars(df.filter(pl.col("country") == country, pl.col("city") == city)),
        width="stretch",
    )

    st.caption("Data: Berkeley Earth via Kaggle.")


if __name__ == "__main__":
    main()
