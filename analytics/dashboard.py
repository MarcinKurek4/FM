"""FM Analytics — Box Office Ranking Dashboard.

Streamlit application that connects to the DWH PostgreSQL database and
presents six box-office rankings with interactive charts and tables:

    1. TOP 10 movies by OMDb box office (bar chart + table)
    2. TOP 10 movies by tracked revenue / OMDb box office ratio (bar chart + table)
    3. TOP 10 movies by total tracked revenue (bar chart + table)
    4. TOP 3 movies per release year (table)
    5. TOP 3 movies per genre (table)
    6. TOP 10 directors by total revenue and distinct movie count
    7. TOP 10 distributors by total revenue

Database credentials are read from the ``.env`` file at the project root
using ``python-dotenv``. The same variables used by the main application
are reused (``POSTGRES_HOST``, ``POSTGRES_PORT``, ``POSTGRES_DB``,
``POSTGRES_USER``, ``POSTGRES_PASSWORD``).

Run::

    streamlit run analytics/dashboard.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import psycopg2
import psycopg2.extensions
import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from queries import (
    top_10_directors_by_total_revenue,
    top_10_distributors_by_total_revenue,
    top_10_movies_by_box_office_omdb,
    top_10_movies_by_total_revenue,
    top_10_movies_revenue_vs_box_office,
    top_3_movies_per_genre,
    top_3_movies_per_release_year,
)

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE)

_PALETTE = px.colors.qualitative.Plotly
_CURRENCY_FMT = "${:,.0f}"
_CHART_HEIGHT = 480

st.set_page_config(
    page_title="FM Box Office Rankings",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)


@st.cache_resource(show_spinner="Connecting to DWH …")
def _get_connection() -> psycopg2.extensions.connection:
    """Return a cached psycopg2 connection to the DWH database.

    Credentials are sourced exclusively from environment variables populated
    by ``load_dotenv``. The connection is cached for the Streamlit session
    lifetime via ``st.cache_resource``.

    Returns:
        Open ``psycopg2`` connection.

    Raises:
        SystemExit: When a mandatory environment variable is absent.
        psycopg2.OperationalError: When the database is unreachable.
    """
    required = ["POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        st.error(f"Missing environment variables: {', '.join(missing)}")
        st.stop()

    return psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


@st.cache_data(ttl=300, show_spinner="Loading data …")
def _load(query_name: str) -> list[dict[str, Any]]:
    """Dispatch a named query and return cached results.

    Results are cached for 300 seconds (5 minutes). Cache is keyed by
    ``query_name`` so each ranking has an independent TTL.

    Args:
        query_name: One of the registered query identifiers.

    Returns:
        List of row dicts as returned by the underlying query function.
    """
    conn = _get_connection()
    dispatch: dict[str, Any] = {
        "top10_movies": top_10_movies_by_total_revenue,
        "top10_movies_box_office": top_10_movies_by_box_office_omdb,
        "top10_movies_ratio": top_10_movies_revenue_vs_box_office,
        "top3_per_year": top_3_movies_per_release_year,
        "top3_per_genre": top_3_movies_per_genre,
        "top10_directors": top_10_directors_by_total_revenue,
        "top10_distributors": top_10_distributors_by_total_revenue,
    }
    return dispatch[query_name](conn)


def _fmt_revenue(df: pd.DataFrame, col: str = "total_revenue") -> pd.DataFrame:
    """Add a human-readable ``revenue_display`` column to *df*.

    Args:
        df: Input DataFrame containing a numeric *col* column.
        col: Column name holding raw revenue values.

    Returns:
        Copy of *df* with an additional ``revenue_display`` string column.
    """
    df = df.copy()
    df["revenue_display"] = df[col].apply(lambda v: _CURRENCY_FMT.format(v))
    return df


def _section_header(title: str, description: str) -> None:
    """Render a styled section heading with a subtitle.

    Args:
        title: Primary heading text.
        description: Short description rendered below the heading.
    """
    st.markdown(f"### {title}")
    st.caption(description)


def _render_top10_movies(conn: psycopg2.extensions.connection) -> None:
    """Render the TOP 10 Movies by Total Revenue section.

    Args:
        conn: Open psycopg2 connection (passed for type-checking; actual
            data is retrieved via the cached ``_load`` helper).
    """
    rows = _load("top10_movies")
    if not rows:
        st.info("No revenue data found.")
        return

    df = pd.DataFrame(rows)
    df = _fmt_revenue(df)

    _section_header(
        "TOP 10 Movies — Total Tracked Revenue",
        "Cumulative tracked revenue across all recorded days per title.",
    )

    col_chart, col_table = st.columns([3, 2], gap="large")

    with col_chart:
        fig = px.bar(
            df,
            x="total_revenue",
            y="title",
            orientation="h",
            color="total_revenue",
            color_continuous_scale="Blues",
            text="revenue_display",
            height=_CHART_HEIGHT,
            labels={"total_revenue": "Total Revenue (USD)", "title": "Movie"},
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(
            yaxis={"autorange": "reversed", "tickfont": {"size": 11}},
            coloraxis_showscale=False,
            margin={"l": 10, "r": 30, "t": 30, "b": 10},
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        display = df[["rank", "title", "release_year", "revenue_display"]].rename(
            columns={
                "rank": "Rank",
                "title": "Movie",
                "release_year": "Year",
                "revenue_display": "Total Revenue",
            }
        )
        st.dataframe(display, use_container_width=True, hide_index=True)


def _render_top10_movies_box_office(conn: psycopg2.extensions.connection) -> None:
    """Render the TOP 10 Movies by OMDb Box Office section.

    Args:
        conn: Open psycopg2 connection.
    """
    rows = _load("top10_movies_box_office")
    if not rows:
        st.info("No data found — requires movies with a non-null OMDb box office value.")
        return

    df = pd.DataFrame(rows)
    df["box_office_display"] = df["box_office_omdb"].apply(
        lambda v: _CURRENCY_FMT.format(v)
    )

    _section_header(
        "TOP 10 Movies — OMDb Box Office",
        "Top 10 titles ranked by the box office figure reported by OMDb.",
    )

    col_chart, col_table = st.columns([3, 2], gap="large")

    with col_chart:
        fig = px.bar(
            df,
            x="box_office_omdb",
            y="title",
            orientation="h",
            color="box_office_omdb",
            color_continuous_scale="Teal",
            text="box_office_display",
            height=_CHART_HEIGHT,
            labels={"box_office_omdb": "OMDb Box Office (USD)", "title": "Movie"},
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(
            yaxis={"autorange": "reversed", "tickfont": {"size": 11}},
            coloraxis_showscale=False,
            margin={"l": 10, "r": 30, "t": 30, "b": 10},
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        display = df[["rank", "title", "release_year", "box_office_display"]].rename(
            columns={
                "rank": "Rank",
                "title": "Movie",
                "release_year": "Year",
                "box_office_display": "OMDb Box Office",
            }
        )
        st.dataframe(display, use_container_width=True, hide_index=True)


def _render_top10_movies_ratio(conn: psycopg2.extensions.connection) -> None:
    """Render the TOP 10 Movies by Revenue / OMDb Box Office Ratio section.

    The ratio compares cumulative tracked revenue (``fact_revenue``) against
    the OMDb-reported box office figure (``dim_movie.box_office_omdb``).
    Only movies with a known, positive OMDb box office value are included.

    Args:
        conn: Open psycopg2 connection.
    """
    rows = _load("top10_movies_ratio")
    if not rows:
        st.info("No data found — requires movies with a non-null OMDb box office value.")
        return

    df = pd.DataFrame(rows)
    df["tracked_revenue_display"] = df["tracked_revenue"].apply(
        lambda v: _CURRENCY_FMT.format(v)
    )
    df["box_office_display"] = df["box_office_omdb"].apply(
        lambda v: _CURRENCY_FMT.format(v)
    )
    df["ratio_display"] = df["revenue_ratio"].apply(lambda v: f"{float(v):.2%}")

    _section_header(
        "TOP 10 Movies — Tracked Revenue / OMDb Box Office Ratio",
        "Ratio of cumulative tracked revenue to the OMDb-reported box office figure. "
        "Values above 100% indicate tracked revenue exceeds the OMDb total.",
    )

    col_chart, col_table = st.columns([3, 2], gap="large")

    with col_chart:
        fig = px.bar(
            df,
            x="revenue_ratio",
            y="title",
            orientation="h",
            color="revenue_ratio",
            color_continuous_scale="Purples",
            text="ratio_display",
            height=_CHART_HEIGHT,
            labels={"revenue_ratio": "Revenue / OMDb Box Office", "title": "Movie"},
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(
            yaxis={"autorange": "reversed", "tickfont": {"size": 11}},
            xaxis_tickformat=".0%",
            coloraxis_showscale=False,
            margin={"l": 10, "r": 30, "t": 30, "b": 10},
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        display = df[
            [
                "rank",
                "title",
                "release_year",
                "tracked_revenue_display",
                "box_office_display",
                "ratio_display",
            ]
        ].rename(
            columns={
                "rank": "Rank",
                "title": "Movie",
                "release_year": "Year",
                "tracked_revenue_display": "Tracked Revenue",
                "box_office_display": "OMDb Box Office",
                "ratio_display": "Ratio",
            }
        )
        st.dataframe(display, use_container_width=True, hide_index=True)


def _render_top3_per_year(conn: psycopg2.extensions.connection) -> None:
    """Render individual TOP 3 charts and tables for each release year.

    One horizontal bar chart and one table are generated per year, ordered
    year descending. Each chart shows the top 3 titles for that year ranked
    by total tracked revenue.

    Args:
        conn: Open psycopg2 connection.
    """
    rows = _load("top3_per_year")
    if not rows:
        st.info("No data found.")
        return

    df = pd.DataFrame(rows)
    df = _fmt_revenue(df)

    _section_header(
        "TOP 3 Movies per Release Year",
        "Top 3 titles by total tracked revenue for each release year, year descending.",
    )

    years = sorted(df["release_year"].dropna().unique().tolist(), reverse=True)
    for year in years:
        year_df = df[df["release_year"] == year].sort_values("rank")
        st.markdown(f"**{int(year)}**")
        col_chart, col_table = st.columns([3, 2], gap="large")
        with col_chart:
            fig = px.bar(
                year_df,
                x="total_revenue",
                y="title",
                orientation="h",
                color="total_revenue",
                color_continuous_scale="Blues",
                text="revenue_display",
                height=220,
                labels={"total_revenue": "Total Revenue (USD)", "title": "Movie"},
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(
                yaxis={"autorange": "reversed", "tickfont": {"size": 11}},
                coloraxis_showscale=False,
                margin={"l": 10, "r": 30, "t": 10, "b": 10},
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True, key=f"year_chart_{int(year)}")
        with col_table:
            display = year_df[["rank", "title", "revenue_display"]].rename(
                columns={
                    "rank": "Rank",
                    "title": "Movie",
                    "revenue_display": "Total Revenue",
                }
            )
            st.dataframe(display, use_container_width=True, hide_index=True)


def _render_top3_per_genre(conn: psycopg2.extensions.connection) -> None:
    """Render individual TOP 3 charts and tables for each genre.

    One horizontal bar chart and one table are generated per genre, ordered
    genre name ascending. Each chart shows the top 3 titles for that genre
    ranked by total tracked revenue.

    Args:
        conn: Open psycopg2 connection.
    """
    rows = _load("top3_per_genre")
    if not rows:
        st.info("No data found.")
        return

    df = pd.DataFrame(rows)
    df = _fmt_revenue(df)

    _section_header(
        "TOP 3 Movies per Genre",
        "Top 3 titles by total tracked revenue for each genre, genre name ascending. "
        "A movie spanning multiple genres appears in each relevant group.",
    )

    genres = sorted(df["genre"].dropna().unique().tolist())
    for genre in genres:
        genre_df = df[df["genre"] == genre].sort_values("rank")
        st.markdown(f"**{genre}**")
        col_chart, col_table = st.columns([3, 2], gap="large")
        with col_chart:
            fig = px.bar(
                genre_df,
                x="total_revenue",
                y="title",
                orientation="h",
                color="total_revenue",
                color_continuous_scale="Greens",
                text="revenue_display",
                height=220,
                labels={"total_revenue": "Total Revenue (USD)", "title": "Movie"},
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(
                yaxis={"autorange": "reversed", "tickfont": {"size": 11}},
                coloraxis_showscale=False,
                margin={"l": 10, "r": 30, "t": 10, "b": 10},
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True, key=f"genre_chart_{genre}")
        with col_table:
            display = genre_df[["rank", "title", "release_year", "revenue_display"]].rename(
                columns={
                    "rank": "Rank",
                    "title": "Movie",
                    "release_year": "Year",
                    "revenue_display": "Total Revenue",
                }
            )
            st.dataframe(display, use_container_width=True, hide_index=True)


def _render_top10_directors(conn: psycopg2.extensions.connection) -> None:
    """Render the TOP 10 Directors by Total Revenue section.

    Args:
        conn: Open psycopg2 connection.
    """
    rows = _load("top10_directors")
    if not rows:
        st.info("No data found.")
        return

    df = pd.DataFrame(rows)
    df = _fmt_revenue(df)

    _section_header(
        "TOP 10 Directors — Total Revenue & Film Count",
        "Cumulative revenue and number of distinct movies credited per director.",
    )

    col_bar, col_bubble, col_table = st.columns([2, 2, 2], gap="large")

    with col_bar:
        fig = px.bar(
            df,
            x="total_revenue",
            y="director",
            orientation="h",
            color="total_revenue",
            color_continuous_scale="Oranges",
            text="revenue_display",
            height=_CHART_HEIGHT,
            labels={"total_revenue": "Total Revenue (USD)", "director": "Director"},
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(
            yaxis={"autorange": "reversed", "tickfont": {"size": 10}},
            coloraxis_showscale=False,
            margin={"l": 10, "r": 10, "t": 30, "b": 10},
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_bubble:
        fig2 = px.scatter(
            df,
            x="distinct_movies",
            y="total_revenue",
            size="distinct_movies",
            color="director",
            text="director",
            height=_CHART_HEIGHT,
            labels={
                "distinct_movies": "Distinct Movies",
                "total_revenue": "Total Revenue (USD)",
                "director": "Director",
            },
        )
        fig2.update_traces(textposition="top center", textfont_size=9)
        fig2.update_layout(
            showlegend=False,
            margin={"l": 10, "r": 10, "t": 30, "b": 10},
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig2, use_container_width=True)

    with col_table:
        display = df[["rank", "director", "revenue_display", "distinct_movies"]].rename(
            columns={
                "rank": "Rank",
                "director": "Director",
                "revenue_display": "Total Revenue",
                "distinct_movies": "Movies",
            }
        )
        st.dataframe(display, use_container_width=True, hide_index=True)


def _render_top10_distributors(conn: psycopg2.extensions.connection) -> None:
    """Render the TOP 10 Distributors by Total Revenue section.

    Args:
        conn: Open psycopg2 connection.
    """
    rows = _load("top10_distributors")
    if not rows:
        st.info("No data found.")
        return

    df = pd.DataFrame(rows)
    df = _fmt_revenue(df)

    _section_header(
        "TOP 10 Distributors — Total Revenue",
        "Cumulative box-office revenue and distinct title count per distribution company.",
    )

    col_pie, col_bar, col_table = st.columns([2, 2, 2], gap="large")

    with col_pie:
        fig_pie = px.pie(
            df,
            names="distributor",
            values="total_revenue",
            hole=0.4,
            height=_CHART_HEIGHT,
            color_discrete_sequence=_PALETTE,
        )
        fig_pie.update_traces(textinfo="label+percent", textfont_size=10)
        fig_pie.update_layout(
            showlegend=False,
            margin={"l": 10, "r": 10, "t": 30, "b": 10},
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_bar:
        fig_bar = px.bar(
            df,
            x="total_revenue",
            y="distributor",
            orientation="h",
            color="total_revenue",
            color_continuous_scale="Greens",
            text="revenue_display",
            height=_CHART_HEIGHT,
            labels={"total_revenue": "Total Revenue (USD)", "distributor": "Distributor"},
        )
        fig_bar.update_traces(textposition="outside")
        fig_bar.update_layout(
            yaxis={"autorange": "reversed", "tickfont": {"size": 10}},
            coloraxis_showscale=False,
            margin={"l": 10, "r": 10, "t": 30, "b": 10},
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_table:
        display = df[["rank", "distributor", "revenue_display", "distinct_movies"]].rename(
            columns={
                "rank": "Rank",
                "distributor": "Distributor",
                "revenue_display": "Total Revenue",
                "distinct_movies": "Movies",
            }
        )
        st.dataframe(display, use_container_width=True, hide_index=True)


def _render_sidebar() -> None:
    """Render the sidebar with database connection status and controls."""
    with st.sidebar:
        st.markdown("## FM Analytics")
        st.markdown("Box Office Ranking Dashboard")
        st.divider()
        if st.button("Refresh data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.divider()
        st.caption(
            f"Host: `{os.environ.get('POSTGRES_HOST', 'n/a')}:{os.environ.get('POSTGRES_PORT', 'n/a')}`"
        )
        st.caption(f"Database: `{os.environ.get('POSTGRES_DB', 'n/a')}`")


def main() -> None:
    """Application entrypoint — renders the full dashboard.

    Establishes the database connection, renders the sidebar, then
    renders each ranking section in sequence separated by a divider.
    """
    conn = _get_connection()
    _render_sidebar()

    st.title("FM — Box Office Rankings Dashboard")
    st.markdown(
        "Interactive rankings derived from the DWH star schema. "
        "Data sourced from ``dwh.fact_revenue``, ``dwh.dim_movie``, "
        "``dwh.dim_genre``, ``dwh.dim_director``, and ``dwh.dim_distributor``."
    )
    st.divider()

    _render_top10_movies_box_office(conn)
    st.divider()

    _render_top10_movies_ratio(conn)
    st.divider()

    _render_top10_movies(conn)
    st.divider()

    _render_top10_directors(conn)
    st.divider()

    _render_top10_distributors(conn)
    st.divider()

    _render_top3_per_year(conn)
    st.divider()

    _render_top3_per_genre(conn)


if __name__ == "__main__":
    main()
