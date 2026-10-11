
from __future__ import annotations

import mysql.connector
import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Tennis Rankings Explorer",
    page_icon="🎾",
    layout="wide",
)


def fetch_frame(connection, query: str, params: tuple = ()) -> pd.DataFrame:
    """Run a read-only query and return the results as a dataframe."""
    cursor = connection.cursor()
    try:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return pd.DataFrame(rows, columns=columns)
    finally:
        cursor.close()


st.title("🎾 Tennis Rankings Explorer")
st.caption(
    "Explore Sportradar ATP/WTA doubles rankings, venues, and competitions "
    "from your MySQL database."
)

with st.sidebar:
    st.header("MySQL connection")

    # Use Streamlit Cloud Secrets when configured.
    # When running locally without secrets.toml, show the connection form.
    try:
        has_mysql_secrets = "mysql" in st.secrets
    except FileNotFoundError:
        has_mysql_secrets = False

    if has_mysql_secrets:
        secret_config = st.secrets["mysql"]
        db_config = {
            "host": secret_config["host"],
            "port": int(secret_config.get("port", 3306)),
            "user": secret_config["user"],
            "password": secret_config["password"],
            "database": secret_config.get("database", "tennis_analytics"),
        }
        connected = True
        st.caption("Using the private database settings configured for this app.")
    else:
        with st.form("mysql_connection"):
            host = st.text_input("Host", value="localhost")
            port = st.number_input(
                "Port",
                min_value=1,
                max_value=65535,
                value=3306,
            )
            username = st.text_input("Username", value="root")
            password = st.text_input("Password", type="password")
            database = st.text_input("Database", value="tennis_analytics")
            connect_clicked = st.form_submit_button("Connect", type="primary")

        if connect_clicked:
            try:
                test_connection = mysql.connector.connect(
                    host=host,
                    port=int(port),
                    user=username,
                    password=password,
                    database=database,
                    connection_timeout=8,
                )
                test_connection.close()
                st.session_state["mysql_connected"] = True
                st.success("Connected to MySQL.")
            except mysql.connector.Error as exc:
                st.session_state["mysql_connected"] = False
                st.error(f"Could not connect: {exc}")

        db_config = {
            "host": host,
            "port": int(port),
            "user": username,
            "password": password,
            "database": database,
        }
        connected = st.session_state.get("mysql_connected", False)
        st.caption(
            "For a deployed app, configure the database under Streamlit Secrets."
        )

if not connected:
    st.info(
        "Enter your MySQL connection details in the sidebar "
        "and select **Connect**."
    )
    st.stop()


try:
    connection = mysql.connector.connect(
        **db_config,
        connection_timeout=8,
    )

    try:
        counts = fetch_frame(
            connection,
            """
            SELECT
                (SELECT COUNT(*) FROM competitions) AS competition_count,
                (SELECT COUNT(*) FROM venues) AS venue_count,
                (SELECT COUNT(*) FROM competitors) AS competitor_count
            """,
        )

        snapshots = fetch_frame(
            connection,
            """
            SELECT snapshot_id, league, year, week, generated_at
            FROM ranking_snapshots
            ORDER BY year DESC, week DESC, league
            """,
        )

        rankings = fetch_frame(
            connection,
            """
            SELECT
                cr.rank AS competitor_rank,
                cr.movement,
                cr.points,
                cr.competitions_played,
                c.competitor_id,
                c.name AS competitor_name,
                COALESCE(c.country, 'Unknown') AS country,
                c.country_code,
                c.abbreviation,
                rs.snapshot_id,
                rs.league,
                rs.gender,
                rs.year,
                rs.week,
                rs.generated_at
            FROM competitor_rankings AS cr
            JOIN competitors AS c
                ON c.competitor_id = cr.competitor_id
            JOIN ranking_snapshots AS rs
                ON rs.snapshot_id = cr.snapshot_id
            """,
        )

        competitions = fetch_frame(
            connection,
            """
            SELECT
                comp.competition_id,
                comp.competition_name,
                comp.type,
                comp.gender,
                comp.level,
                comp.parent_id,
                COALESCE(cat.category_name, 'Uncategorized') AS category_name
            FROM competitions AS comp
            LEFT JOIN categories AS cat
                ON cat.category_id = comp.category_id
            """,
        )

        venues = fetch_frame(
            connection,
            """
            SELECT
                v.venue_id,
                v.venue_name,
                v.city_name,
                v.country_name,
                v.country_code,
                v.timezone,
                v.capacity,
                v.complex_id,
                COALESCE(cx.complex_name, 'Unknown') AS complex_name
            FROM venues AS v
            LEFT JOIN complexes AS cx
                ON cx.complex_id = v.complex_id
            """,
        )
    finally:
        connection.close()

except mysql.connector.Error as exc:
    st.error(f"Could not read the project tables from MySQL: {exc}")
    st.info(
        "Confirm that the categories, competitions, complexes, venues, "
        "ranking_snapshots, competitors, and competitor_rankings tables exist."
    )
    st.stop()


numeric_columns = [
    "competitor_rank",
    "movement",
    "points",
    "competitions_played",
    "year",
    "week",
]
for column in numeric_columns:
    if column in rankings.columns:
        rankings[column] = pd.to_numeric(rankings[column], errors="coerce")


st.sidebar.subheader("Filters")

if not snapshots.empty:
    years = sorted(
        snapshots["year"].dropna().astype(int).unique().tolist(),
        reverse=True,
    )
    selected_year = st.sidebar.selectbox("Year", years)

    year_snapshots = snapshots[snapshots["year"] == selected_year]
    weeks = sorted(
        year_snapshots["week"].dropna().astype(int).unique().tolist(),
        reverse=True,
    )
    selected_week = st.sidebar.selectbox("Week", ["All"] + weeks)

    period_snapshots = year_snapshots.copy()
    if selected_week != "All":
        period_snapshots = period_snapshots[
            period_snapshots["week"] == selected_week
        ]

    genders = sorted(period_snapshots["gender"].dropna().unique().tolist())
    selected_gender = st.sidebar.selectbox("Gender", ["All"] + genders)

    selected_ids = period_snapshots["snapshot_id"].astype(int).tolist()
    filtered_rankings = rankings[
        rankings["snapshot_id"].isin(selected_ids)
    ].copy()

    if selected_gender != "All":
        filtered_rankings = filtered_rankings[
            filtered_rankings["gender"] == selected_gender
        ]

    if not filtered_rankings.empty:
        max_rank = max(1, int(filtered_rankings["competitor_rank"].max()))

        rank_range = st.sidebar.slider(
            "Rank Range",
            min_value=1,
            max_value=max_rank,
            value=(1, min(100, max_rank)),
        )

        filtered_rankings = filtered_rankings[
            filtered_rankings["competitor_rank"].between(*rank_range)
        ].copy()
    else:
        st.sidebar.caption(
            "No ranking rows match this year/week/gender selection."
        )

    st.sidebar.subheader("Search Competitors")
    competitor_search = st.sidebar.text_input("Competitor name")

    if competitor_search:
        filtered_rankings = filtered_rankings[
            filtered_rankings["competitor_name"].str.contains(
                competitor_search,
                case=False,
                na=False,
            )
        ]
else:
    filtered_rankings = rankings.copy()
    st.sidebar.info(
        "No ranking snapshots found. Load rankings into MySQL first."
    )


st.subheader("Rankings")
st.markdown("#### Filtered Rankings")

if filtered_rankings.empty:
    st.info("No rankings match the selected filters.")
else:
    ranking_columns = [
        "league",
        "year",
        "week",
        "gender",
        "competitor_rank",
        "points",
        "competitor_name",
        "country",
    ]

    ranking_display = (
        filtered_rankings.sort_values(
            ["league", "competitor_rank", "competitor_name"]
        )[ranking_columns]
        .rename(
            columns={
                "league": "League",
                "year": "Year",
                "week": "Week",
                "gender": "Gender",
                "competitor_rank": "Rank",
                "points": "Points",
                "competitor_name": "Competitor",
                "country": "Country",
            }
        )
    )

    st.caption(f"{len(ranking_display):,} ranking rows match your filters")
    st.dataframe(
        ranking_display,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download filtered rankings as CSV",
        ranking_display.to_csv(index=False).encode("utf-8"),
        file_name="tennis_rankings.csv",
        mime="text/csv",
    )

    detail_options = filtered_rankings.drop_duplicates("competitor_id")

    selected_competitor_id = st.selectbox(
        "Competitor details",
        detail_options["competitor_id"].tolist(),
        format_func=lambda competitor_id: detail_options.loc[
            detail_options["competitor_id"] == competitor_id,
            "competitor_name",
        ].iloc[0],
    )

    selected_detail = filtered_rankings[
        filtered_rankings["competitor_id"] == selected_competitor_id
    ][
        [
            "competitor_name",
            "country",
            "league",
            "competitor_rank",
            "movement",
            "points",
            "competitions_played",
            "year",
            "week",
        ]
    ].rename(
        columns={
            "competitor_name": "Competitor",
            "country": "Country",
            "league": "League",
            "competitor_rank": "Rank",
            "movement": "Movement",
            "points": "Points",
            "competitions_played": "Competitions Played",
            "year": "Year",
            "week": "Week",
        }
    )

    st.markdown("#### Competitor Details")
    st.dataframe(
        selected_detail,
        use_container_width=True,
        hide_index=True,
    )


st.subheader("Venues and Complexes")

if venues.empty:
    st.info("No venue rows found.")
else:
    venue_countries = sorted(
        venues["country_name"].dropna().unique().tolist()
    )
    venue_country = st.selectbox(
        "Venue country",
        ["All"] + venue_countries,
    )

    venue_search = st.text_input(
        "Search venue, city, or complex",
        key="venue_search",
    )

    filtered_venues = venues.copy()

    if venue_country != "All":
        filtered_venues = filtered_venues[
            filtered_venues["country_name"] == venue_country
        ]

    if venue_search:
        search_columns = ["venue_name", "city_name", "complex_name"]
        search_mask = (
            filtered_venues[search_columns]
            .fillna("")
            .astype(str)
            .apply(
                lambda column: column.str.contains(
                    venue_search,
                    case=False,
                    na=False,
                )
            )
            .any(axis=1)
        )
        filtered_venues = filtered_venues[search_mask]

    st.caption(f"Showing {len(filtered_venues):,} of {len(venues):,} venues")

    venue_columns = [
        "venue_name",
        "city_name",
        "country_name",
        "timezone",
        "complex_name",
    ]

    venue_display = (
        filtered_venues.sort_values(
            ["country_name", "city_name", "venue_name"]
        )[venue_columns]
        .rename(
            columns={
                "venue_name": "Venue",
                "city_name": "City",
                "country_name": "Country",
                "timezone": "Timezone",
                "complex_name": "Complex",
            }
        )
    )

    st.dataframe(
        venue_display,
        use_container_width=True,
        hide_index=True,
    )


st.subheader("Competition Explorer")

if competitions.empty:
    st.info("No competition rows found.")
else:
    filter_cols = st.columns(3)

    type_options = sorted(
        competitions["type"].fillna("Unknown").unique().tolist()
    )
    level_options = sorted(
        competitions["level"].fillna("Unknown").unique().tolist()
    )
    category_options = sorted(
        competitions["category_name"].fillna("Uncategorized").unique().tolist()
    )

    selected_types = filter_cols[0].multiselect(
        "Competition type",
        type_options,
    )
    selected_levels = filter_cols[1].multiselect(
        "Competition level",
        level_options,
    )
    selected_categories = filter_cols[2].multiselect(
        "Category",
        category_options,
    )

    filtered_competitions = competitions.copy()

    if selected_types:
        filtered_competitions = filtered_competitions[
            filtered_competitions["type"].isin(selected_types)
        ]

    if selected_levels:
        filtered_competitions = filtered_competitions[
            filtered_competitions["level"].isin(selected_levels)
        ]

    if selected_categories:
        filtered_competitions = filtered_competitions[
            filtered_competitions["category_name"].isin(selected_categories)
        ]

    st.caption(
        f"Showing {len(filtered_competitions):,} of "
        f"{len(competitions):,} competitions"
    )

    st.dataframe(
        filtered_competitions.sort_values(
            ["category_name", "competition_name"]
        ),
        use_container_width=True,
        hide_index=True,
    )
