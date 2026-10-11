from __future__ import annotations

import mysql.connector
import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(
    page_title="Tennis Data Analytics",
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


def latest_snapshot_ids(snapshots: pd.DataFrame) -> list[int]:
    if snapshots.empty:
        return []
    latest = snapshots.sort_values(
        ["league", "year", "week", "snapshot_id"],
        ascending=[True, False, False, False],
    ).drop_duplicates("league", keep="first")
    return latest["snapshot_id"].astype(int).tolist()


st.title("🎾 Tennis Data Analytics")
st.caption(
    "Explore Sportradar competitions, venues, and ATP/WTA doubles rankings "
    "from your MySQL database."
)

with st.sidebar:
    st.header("MySQL connection")
    if "mysql" in st.secrets:
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
            port = st.number_input("Port", min_value=1, max_value=65535, value=3306)
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
        st.caption("For a deployed app, configure the database under Streamlit Secrets instead.")

if not connected:
    st.info("Enter your MySQL connection details in the sidebar and select **Connect**.")
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
            JOIN competitors AS c ON c.competitor_id = cr.competitor_id
            JOIN ranking_snapshots AS rs ON rs.snapshot_id = cr.snapshot_id
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
            LEFT JOIN categories AS cat ON cat.category_id = comp.category_id
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
            LEFT JOIN complexes AS cx ON cx.complex_id = v.complex_id
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

for column in ("competitor_rank", "movement", "points", "competitions_played", "year", "week"):
    if column in rankings.columns:
        rankings[column] = pd.to_numeric(rankings[column], errors="coerce")

if not snapshots.empty:
    latest_ids = latest_snapshot_ids(snapshots)
    options: dict[str, list[int]] = {"Latest snapshot for each league": latest_ids}
    for row in snapshots.to_dict("records"):
        label = f"{row['league']} — {row['year']} week {row['week']}"
        options[label] = [int(row["snapshot_id"])]
    selected_label = st.sidebar.selectbox("Ranking snapshot", list(options))
    selected_ids = options[selected_label]
    ranking_view = rankings[rankings["snapshot_id"].isin(selected_ids)].copy()
else:
    ranking_view = rankings.copy()
    st.sidebar.caption("No ranking snapshots are available yet.")

tabs = st.tabs(["Overview", "Competitors", "Competitions", "Venues"])

with tabs[0]:
    st.subheader("Project overview")
    total_competitions = int(counts.iloc[0]["competition_count"])
    total_venues = int(counts.iloc[0]["venue_count"])
    total_competitors = int(counts.iloc[0]["competitor_count"])
    country_count = ranking_view["country"].nunique() if not ranking_view.empty else 0
    metric_cols = st.columns(4)
    metric_cols[0].metric("Competitions", f"{total_competitions:,}")
    metric_cols[1].metric("Venues", f"{total_venues:,}")
    metric_cols[2].metric("Competitors", f"{total_competitors:,}")
    metric_cols[3].metric("Countries represented", f"{country_count:,}")

    if not ranking_view.empty:
        top_points = ranking_view.sort_values(
            ["points", "competitor_rank"], ascending=[False, True]
        ).iloc[0]
        st.metric(
            "Highest points in selected snapshot(s)",
            f"{int(top_points['points']):,}",
            str(top_points["competitor_name"]),
        )
        left, right = st.columns(2)
        country_counts = (
            ranking_view.groupby("country", as_index=False)
            .agg(competitor_count=("competitor_id", "nunique"))
            .sort_values("competitor_count", ascending=False)
            .head(15)
        )
        left.plotly_chart(
            px.bar(country_counts, x="country", y="competitor_count", title="Competitors by country"),
            use_container_width=True,
        )
        right.plotly_chart(
            px.scatter(
                ranking_view,
                x="competitor_rank",
                y="points",
                color="league",
                hover_name="competitor_name",
                hover_data=["country", "movement", "competitions_played"],
                title="Rank versus points",
            ),
            use_container_width=True,
        )
    else:
        st.info("Ranking summaries appear here after ranking data is loaded.")

    if not competitions.empty:
        type_summary = (
            competitions.groupby("type", dropna=False)
            .size()
            .reset_index(name="competition_count")
            .sort_values("competition_count", ascending=False)
        )
        st.plotly_chart(
            px.bar(type_summary, x="type", y="competition_count", title="Competitions by type"),
            use_container_width=True,
        )

with tabs[1]:
    st.subheader("Search and filter competitors")
    if ranking_view.empty:
        st.info("No ranking rows are available for this selection.")
    else:
        countries = sorted(ranking_view["country"].dropna().unique().tolist())
        selected_countries = st.multiselect("Country", countries, key="competitor_country_filter")
        search = st.text_input("Search competitor name", key="competitor_search")
        max_rank = max(1, int(ranking_view["competitor_rank"].max()))
        filter_a, filter_b = st.columns(2)
        rank_range = filter_a.slider(
            "Rank range", min_value=1, max_value=max_rank,
            value=(1, min(max_rank, 100)),
        )
        minimum_points = filter_b.number_input("Minimum points", min_value=0, value=0, step=100)
        filtered_rankings = ranking_view[
            ranking_view["competitor_rank"].between(*rank_range)
            & (ranking_view["points"].fillna(0) >= minimum_points)
        ].copy()
        if selected_countries:
            filtered_rankings = filtered_rankings[filtered_rankings["country"].isin(selected_countries)]
        if search:
            filtered_rankings = filtered_rankings[
                filtered_rankings["competitor_name"].str.contains(search, case=False, na=False)
            ]
        filtered_rankings = filtered_rankings.sort_values(["league", "competitor_rank", "competitor_name"])
        shown_columns = [
            "competitor_rank", "competitor_name", "country", "points", "movement",
            "competitions_played", "league", "year", "week",
        ]
        st.dataframe(filtered_rankings[shown_columns], use_container_width=True, hide_index=True)
        st.download_button(
            "Download filtered competitors as CSV",
            filtered_rankings.to_csv(index=False).encode("utf-8"),
            file_name="tennis_competitor_rankings.csv",
            mime="text/csv",
        )

        if not filtered_rankings.empty:
            selected_competitor = st.selectbox(
                "Competitor details",
                filtered_rankings["competitor_id"].tolist(),
                format_func=lambda competitor_id: filtered_rankings.loc[
                    filtered_rankings["competitor_id"] == competitor_id, "competitor_name"
                ].iloc[0],
            )
            detail_rows = filtered_rankings[filtered_rankings["competitor_id"] == selected_competitor]
            st.dataframe(detail_rows[shown_columns], use_container_width=True, hide_index=True)

        country_analysis = (
            ranking_view.groupby("country", as_index=False)
            .agg(
                competitor_count=("competitor_id", "nunique"),
                average_points=("points", "mean"),
            )
            .sort_values(["competitor_count", "average_points"], ascending=False)
        )
        st.subheader("Country-wise analysis")
        country_analysis["average_points"] = country_analysis["average_points"].round(1)
        st.dataframe(country_analysis, use_container_width=True, hide_index=True)

        leaders_tab, points_tab = st.tabs(["Top ranks", "Highest points"])
        with leaders_tab:
            st.dataframe(
                ranking_view.sort_values(["competitor_rank", "league", "competitor_name"]).head(100)[shown_columns],
                use_container_width=True,
                hide_index=True,
            )
        with points_tab:
            st.dataframe(
                ranking_view.sort_values(["points", "competitor_rank"], ascending=[False, True]).head(100)[shown_columns],
                use_container_width=True,
                hide_index=True,
            )

with tabs[2]:
    st.subheader("Competition catalog")
    if competitions.empty:
        st.info("No competition rows found.")
    else:
        filter_cols = st.columns(3)
        type_options = sorted(competitions["type"].fillna("Unknown").unique().tolist())
        level_options = sorted(competitions["level"].fillna("Unknown").unique().tolist())
        category_options = sorted(competitions["category_name"].fillna("Uncategorized").unique().tolist())
        selected_types = filter_cols[0].multiselect("Competition type", type_options)
        selected_levels = filter_cols[1].multiselect("Competition level", level_options)
        selected_categories = filter_cols[2].multiselect("Category", category_options)
        filtered_competitions = competitions.copy()
        if selected_types:
            filtered_competitions = filtered_competitions[filtered_competitions["type"].isin(selected_types)]
        if selected_levels:
            filtered_competitions = filtered_competitions[filtered_competitions["level"].isin(selected_levels)]
        if selected_categories:
            filtered_competitions = filtered_competitions[filtered_competitions["category_name"].isin(selected_categories)]
        st.caption(f"Showing {len(filtered_competitions):,} of {len(competitions):,} competitions")
        st.dataframe(
            filtered_competitions.sort_values(["category_name", "competition_name"]),
            use_container_width=True,
            hide_index=True,
        )

with tabs[3]:
    st.subheader("Venue and complex directory")
    if venues.empty:
        st.info("No venue rows found.")
    else:
        countries = sorted(venues["country_name"].dropna().unique().tolist())
        picked_countries = st.multiselect("Venue country", countries)
        venue_search = st.text_input("Search venue, city, or complex", key="venue_search")
        filtered_venues = venues.copy()
        if picked_countries:
            filtered_venues = filtered_venues[filtered_venues["country_name"].isin(picked_countries)]
        if venue_search:
            search_columns = ["venue_name", "city_name", "complex_name"]
            mask = filtered_venues[search_columns].fillna("").astype(str).apply(
                lambda column: column.str.contains(venue_search, case=False, na=False)
            ).any(axis=1)
            filtered_venues = filtered_venues[mask]
        st.dataframe(
            filtered_venues.sort_values(["country_name", "city_name", "venue_name"]),
            use_container_width=True,
            hide_index=True,
        )
        venue_counts = (
            venues.groupby("country_name", dropna=False)
            .size()
            .reset_index(name="venue_count")
            .sort_values("venue_count", ascending=False)
            .head(20)
        )
        st.plotly_chart(
            px.bar(venue_counts, x="country_name", y="venue_count", title="Venues by country"),
            use_container_width=True,
        )
