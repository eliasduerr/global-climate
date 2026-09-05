from __future__ import annotations

import datetime as dt
import os

import altair as alt
import polars as pl
import streamlit as st

BUCKET = os.environ.get("DATA_BUCKET", "global-climate-data")
PROCESSED_URI = f"s3://{BUCKET}/processed/temperature-features.parquet"


@st.cache_data(ttl=3600, show_spinner="Loading features from S3 ...")
def load_features() -> pl.DataFrame:
    return pl.scan_parquet(PROCESSED_URI).collect()


def main() -> None:
    st.set_page_config(page_title="Global climate", layout="wide")
    st.title("Global climate features")
    st.caption(
        "Rolling baselines and anomalies from the Berkeley Earth "
        "surface temperature dataset."
    )

    df = load_features()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rows", f"{df.height:,}")
    col2.metric("Cities", df["city"].n_unique())
    col3.metric("Countries", df["country"].n_unique())
    col4.metric("Date range", f"{df['dt'].min()} → {df['dt'].max()}")

    st.divider()

    st.subheader("City drill-down")
    cities = sorted(df["city"].unique().to_list())
    default = [c for c in ("Berlin", "Tokyo", "Lima") if c in cities] or cities[:3]
    selected = st.multiselect("Cities", cities, default=default)

    if selected:
        subset = (
            df.filter(pl.col("city").is_in(selected))
            .select("dt", "city", "temperature_anomaly", "baseline_temperature_30y")
            .to_pandas()
        )
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
    latest: dt.date = df["dt"].max()
    cutoff = dt.date(latest.year - window_years, latest.month, 1)

    top = (
        df.filter(pl.col("dt") >= cutoff)
        .group_by(["country", "city"])
        .agg(
            pl.col("temperature_anomaly").mean().round(3).alias("avg_anomaly"),
            pl.col("temperature_anomaly").max().round(3).alias("max_anomaly"),
        )
        .sort("avg_anomaly", descending=True)
        .head(20)
        .to_pandas()
    )
    st.dataframe(top, use_container_width=True, hide_index=True)

    st.caption("Data: Berkeley Earth via Kaggle. Baseline = 360-month rolling mean.")


if __name__ == "__main__":
    main()
