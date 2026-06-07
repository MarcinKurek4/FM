"""Ranking SQL queries for the FM analytics dashboard.

All queries read exclusively from the ``dwh`` PostgreSQL schema. Each
function accepts an open ``psycopg2`` connection, executes a parameterised
query, and returns a plain ``list[dict]`` so that the caller (Streamlit)
can construct a ``pandas.DataFrame`` without coupling to any ORM.

No business logic lives here — only data-retrieval. Column names in the
returned dicts match the display-friendly aliases defined in each SQL
statement.

Usage::

    import psycopg2
    from analytics.queries import top_10_movies_by_revenue

    conn = psycopg2.connect(dsn)
    rows = top_10_movies_by_revenue(conn)
"""

from __future__ import annotations

from typing import Any

import psycopg2.extensions


def _fetchall_as_dicts(
    conn: psycopg2.extensions.connection,
    sql: str,
    params: tuple[Any, ...] | None = None,
) -> list[dict[str, Any]]:
    """Execute *sql* and return all rows as a list of column-name-keyed dicts.

    Args:
        conn: Open psycopg2 connection. Caller is responsible for lifecycle.
        sql: Parameterised SQL statement.
        params: Optional positional parameters bound to *sql*.

    Returns:
        List of dicts, one per result row. Empty list when no rows match.
    """
    with conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def top_10_movies_by_total_revenue(
    conn: psycopg2.extensions.connection,
) -> list[dict[str, Any]]:
    """Return the top 10 movies ranked by cumulative box-office revenue.

    Joins ``fact_revenue`` with ``dim_movie`` to resolve the title.

    Args:
        conn: Open psycopg2 connection.

    Returns:
        List of dicts with keys: ``rank``, ``title``, ``release_year``,
        ``total_revenue``.

    Example:
        rows = top_10_movies_by_total_revenue(conn)
    """
    sql = """
        SELECT
            ROW_NUMBER() OVER (ORDER BY SUM(fr.revenue) DESC)::int AS rank,
            dm.title,
            dm.release_year,
            SUM(fr.revenue) AS total_revenue
        FROM dwh.fact_revenue fr
        JOIN dwh.dim_movie dm ON dm.movie_id = fr.movie_id
        GROUP BY dm.movie_id, dm.title, dm.release_year
        ORDER BY total_revenue DESC
        LIMIT 10;
    """
    return _fetchall_as_dicts(conn, sql)


def top_3_movies_per_release_year(
    conn: psycopg2.extensions.connection,
) -> list[dict[str, Any]]:
    """Return the top 3 movies by total revenue for each release year.

    Uses a window function (RANK) partitioned by ``release_year`` so that
    ties within a year share the same rank position.

    Args:
        conn: Open psycopg2 connection.

    Returns:
        List of dicts with keys: ``release_year``, ``rank``, ``title``,
        ``total_revenue``.

    Example:
        rows = top_3_movies_per_release_year(conn)
    """
    sql = """
        WITH revenue_by_movie AS (
            SELECT
                dm.movie_id,
                dm.title,
                dm.release_year,
                SUM(fr.revenue) AS total_revenue
            FROM dwh.fact_revenue fr
            JOIN dwh.dim_movie dm ON dm.movie_id = fr.movie_id
            WHERE dm.release_year IS NOT NULL
            GROUP BY dm.movie_id, dm.title, dm.release_year
        ),
        ranked AS (
            SELECT
                release_year,
                title,
                total_revenue,
                RANK() OVER (
                    PARTITION BY release_year
                    ORDER BY total_revenue DESC
                )::int AS rank
            FROM revenue_by_movie
        )
        SELECT release_year, rank, title, total_revenue
        FROM ranked
        WHERE rank <= 3
        ORDER BY release_year DESC, rank ASC;
    """
    return _fetchall_as_dicts(conn, sql)


def top_3_movies_per_genre(
    conn: psycopg2.extensions.connection,
) -> list[dict[str, Any]]:
    """Return the top 3 movies by total revenue for each genre.

    Resolves the many-to-many movie–genre relationship via
    ``bridge_movie_genre`` and ``dim_genre``. A movie that belongs to
    multiple genres appears once in each genre's ranking.

    Args:
        conn: Open psycopg2 connection.

    Returns:
        List of dicts with keys: ``genre``, ``rank``, ``title``,
        ``release_year``, ``total_revenue``.

    Example:
        rows = top_3_movies_per_genre(conn)
    """
    sql = """
        WITH revenue_by_movie AS (
            SELECT
                dm.movie_id,
                dm.title,
                dm.release_year,
                SUM(fr.revenue) AS total_revenue
            FROM dwh.fact_revenue fr
            JOIN dwh.dim_movie dm ON dm.movie_id = fr.movie_id
            GROUP BY dm.movie_id, dm.title, dm.release_year
        ),
        movie_genre AS (
            SELECT
                rbm.movie_id,
                rbm.title,
                rbm.release_year,
                rbm.total_revenue,
                dg.genre_name AS genre
            FROM revenue_by_movie rbm
            JOIN dwh.bridge_movie_genre bmg ON bmg.movie_id = rbm.movie_id
            JOIN dwh.dim_genre dg ON dg.genre_id = bmg.genre_id
        ),
        ranked AS (
            SELECT
                genre,
                title,
                release_year,
                total_revenue,
                RANK() OVER (
                    PARTITION BY genre
                    ORDER BY total_revenue DESC
                )::int AS rank
            FROM movie_genre
        )
        SELECT genre, rank, title, release_year, total_revenue
        FROM ranked
        WHERE rank <= 3
        ORDER BY genre ASC, rank ASC;
    """
    return _fetchall_as_dicts(conn, sql)


def top_10_directors_by_total_revenue(
    conn: psycopg2.extensions.connection,
) -> list[dict[str, Any]]:
    """Return the top 10 directors ranked by cumulative revenue across all movies.

    Resolves the many-to-many movie–director relationship via
    ``bridge_movie_director`` and ``dim_director``. ``distinct_movies``
    counts unique titles credited to each director.

    Args:
        conn: Open psycopg2 connection.

    Returns:
        List of dicts with keys: ``rank``, ``director``, ``total_revenue``,
        ``distinct_movies``.

    Example:
        rows = top_10_directors_by_total_revenue(conn)
    """
    sql = """
        SELECT
            ROW_NUMBER() OVER (ORDER BY SUM(fr.revenue) DESC)::int AS rank,
            dd.director_name AS director,
            SUM(fr.revenue) AS total_revenue,
            COUNT(DISTINCT fr.movie_id)::int AS distinct_movies
        FROM dwh.fact_revenue fr
        JOIN dwh.bridge_movie_director bmd ON bmd.movie_id = fr.movie_id
        JOIN dwh.dim_director dd ON dd.director_id = bmd.director_id
        GROUP BY dd.director_id, dd.director_name
        ORDER BY total_revenue DESC
        LIMIT 10;
    """
    return _fetchall_as_dicts(conn, sql)


def top_10_movies_by_box_office_omdb(
    conn: psycopg2.extensions.connection,
) -> list[dict[str, Any]]:
    """Return the top 10 movies ranked by the OMDb-reported box office figure.

    Only movies where ``box_office_omdb`` is not NULL and greater than zero
    are included. No join to ``fact_revenue`` is performed — the ranking is
    based entirely on the OMDb metadata stored in ``dim_movie``.

    Args:
        conn: Open psycopg2 connection.

    Returns:
        List of dicts with keys: ``rank``, ``title``, ``release_year``,
        ``box_office_omdb``.

    Example:
        rows = top_10_movies_by_box_office_omdb(conn)
    """
    sql = """
        SELECT
            ROW_NUMBER() OVER (ORDER BY box_office_omdb DESC)::int AS rank,
            title,
            release_year,
            box_office_omdb
        FROM dwh.dim_movie
        WHERE box_office_omdb IS NOT NULL
          AND box_office_omdb > 0
        ORDER BY box_office_omdb DESC
        LIMIT 10;
    """
    return _fetchall_as_dicts(conn, sql)


def top_10_movies_revenue_vs_box_office(
    conn: psycopg2.extensions.connection,
) -> list[dict[str, Any]]:
    """Return the top 10 movies by the ratio of tracked revenue to OMDb box office.

    The ratio ``revenue_ratio`` is defined as::

        SUM(fact_revenue.revenue) / dim_movie.box_office_omdb

    Only movies where ``box_office_omdb`` is not NULL and greater than zero
    are included. A ratio above 1.0 means tracked revenue exceeds the OMDb
    reported box office figure (e.g. due to international receipts or data
    discrepancies). The ranking is ordered by ``revenue_ratio`` descending.

    Args:
        conn: Open psycopg2 connection.

    Returns:
        List of dicts with keys: ``rank``, ``title``, ``release_year``,
        ``tracked_revenue``, ``box_office_omdb``, ``revenue_ratio``.

    Example:
        rows = top_10_movies_revenue_vs_box_office(conn)
    """
    sql = """
        SELECT
            ROW_NUMBER() OVER (
                ORDER BY SUM(fr.revenue) / dm.box_office_omdb DESC
            )::int AS rank,
            dm.title,
            dm.release_year,
            SUM(fr.revenue)         AS tracked_revenue,
            dm.box_office_omdb      AS box_office_omdb,
            ROUND(
                SUM(fr.revenue) / dm.box_office_omdb,
                4
            )                       AS revenue_ratio
        FROM dwh.fact_revenue fr
        JOIN dwh.dim_movie dm ON dm.movie_id = fr.movie_id
        WHERE dm.box_office_omdb IS NOT NULL
          AND dm.box_office_omdb > 0
        GROUP BY dm.movie_id, dm.title, dm.release_year, dm.box_office_omdb
        ORDER BY revenue_ratio DESC
        LIMIT 10;
    """
    return _fetchall_as_dicts(conn, sql)


def top_10_distributors_by_total_revenue(
    conn: psycopg2.extensions.connection,
) -> list[dict[str, Any]]:
    """Return the top 10 distributors ranked by cumulative box-office revenue.

    Joins ``fact_revenue`` with ``dim_distributor``. Rows where
    ``distributor_id`` is NULL are excluded (revenue without a known
    distributor).

    Args:
        conn: Open psycopg2 connection.

    Returns:
        List of dicts with keys: ``rank``, ``distributor``, ``total_revenue``,
        ``distinct_movies``.

    Example:
        rows = top_10_distributors_by_total_revenue(conn)
    """
    sql = """
        SELECT
            ROW_NUMBER() OVER (ORDER BY SUM(fr.revenue) DESC)::int AS rank,
            dd.distributor_name AS distributor,
            SUM(fr.revenue) AS total_revenue,
            COUNT(DISTINCT fr.movie_id)::int AS distinct_movies
        FROM dwh.fact_revenue fr
        JOIN dwh.dim_distributor dd ON dd.distributor_id = fr.distributor_id
        GROUP BY dd.distributor_id, dd.distributor_name
        ORDER BY total_revenue DESC
        LIMIT 10;
    """
    return _fetchall_as_dicts(conn, sql)
