from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(page_title="Tennis Rankings Explorer", page_icon="🎾", layout="wide")
DB_PATH = Path(__file__).resolve().with_name("tennis_data.sqlite")


@st.cache_data(ttl=300)
def load_data(database_path: str) -> dict[str, pd.DataFrame]:
    with sqlite3.connect(database_path) as conn:
        rankings = pd.read_sql_query(
            """
            SELECT cr.rank, cr.movement, cr.points, cr.competitions_played,
                   c.id AS competitor_id, c.name AS competitor, c.country,
                   c.country_code, c.abbreviation, rs.league, rs.gender,
                   rs.year, rs.week, rs.id AS snapshot_id,
                   rs.generated_at, rs.type_id
            FROM competitor_rankings AS cr
            JOIN competitors AS c ON c.id = cr.competitor_id
            JOIN ranking_snapshots AS rs ON rs.id = cr.snapshot_id
            ORDER BY rs.year DESC, rs.week DESC, cr.rank, c.name
            """, conn
        )
        competitions = pd.read_sql_query(
            """
            SELECT co.id, co.name AS competition, co.type, co.gender, co.level,
                   co.parent_id, COALESCE(cat.name, 'Uncategorized') AS category
            FROM competitions AS co
            LEFT JOIN categories AS cat ON cat.id = co.category_id
            ORDER BY category, competition
            """, conn
        )
        venues = pd.read_sql_query(
            """
            SELECT v.id, v.name AS venue, v.city_name AS city,
                   COALESCE(v.country_name, 'Unknown') AS country,
                   v.country_code, v.timezone, v.capacity,
                   COALESCE(cx.name, 'Unknown') AS complex
            FROM venues AS v
            LEFT JOIN complexes AS cx ON cx.id = v.complex_id
            ORDER BY country, city, venue
            """, conn
        )
        snapshots = pd.read_sql_query(
            """
            SELECT id, league, gender, year, week, generated_at
            FROM ranking_snapshots
            ORDER BY year DESC, week DESC, league
            """, conn
        )
    return {"rankings": rankings, "competitions": competitions,
            "venues": venues, "snapshots": snapshots}


st.title("🎾 Tennis Rankings Explorer")
st.caption("Explore Sportradar doubles rankings, competitions, venues, and tennis complexes.")

if not DB_PATH.exists():
    st.error("The project database file is missing. Make sure tennis_data.sqlite is in the same GitHub folder as app.py.")
    st.stop()

try:
    data = load_data(str(DB_PATH))
except Exception as exc:
    st.error(f"Could not read the project database: {exc}")
    st.stop()

rankings_all = data["rankings"]
competitions = data["competitions"]
venues = data["venues"]
snapshots = data["snapshots"]

if snapshots.empty:
    st.warning("No ranking snapshots were found in the database.")
    selected_snapshot = None
else:
    snapshots = snapshots.copy()
    snapshots["label"] = snapshots.apply(
        lambda r: f"{r['league']} · {r['gender'] or 'unknown'} · {r['year'] or '?'} week {r['week'] or '?'}",
        axis=1,
    )
    labels = dict(zip(snapshots["id"], snapshots["label"]))
    selected_snapshot = st.sidebar.selectbox(
        "Ranking snapshot", list(labels), format_func=lambda value: labels[value]
    )

rankings = rankings_all[rankings_all["snapshot_id"] == selected_snapshot].copy() if selected_snapshot is not None else rankings_all.copy()

st.sidebar.header("Ranking filters")
if not rankings.empty:
    countries = sorted(rankings["country"].fillna("Unknown").unique().tolist())
    chosen_countries = st.sidebar.multiselect("Country", countries, placeholder="All countries")
    max_rank = max(1, int(rankings["rank"].max()))
    rank_range = st.sidebar.slider("Rank range", 1, max_rank, (1, min(100, max_rank)))
    min_points = st.sidebar.number_input("Minimum points", min_value=0, value=0, step=100)
    search_name = st.sidebar.text_input("Search competitor")
else:
    chosen_countries, rank_range, min_points, search_name = [], (1, 1), 0, ""

filtered_rankings = rankings.copy()
if not filtered_rankings.empty:
    filtered_rankings = filtered_rankings[filtered_rankings["rank"].between(*rank_range)]
    filtered_rankings = filtered_rankings[filtered_rankings["points"].fillna(0) >= min_points]
    if chosen_countries:
        filtered_rankings = filtered_rankings[filtered_rankings["country"].fillna("Unknown").isin(chosen_countries)]
    if search_name:
        filtered_rankings = filtered_rankings[filtered_rankings["competitor"].str.contains(search_name, case=False, na=False)]

summary_competitors = filtered_rankings["competitor_id"].nunique() if not filtered_rankings.empty else 0
summary_countries = filtered_rankings["country"].nunique() if not filtered_rankings.empty else 0
highest_points = int(filtered_rankings["points"].max()) if not filtered_rankings.empty and filtered_rankings["points"].notna().any() else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Matching competitors", f"{summary_competitors:,}", help="Updates with the ranking filters in the sidebar.")
m2.metric("Countries represented", f"{summary_countries:,}")
m3.metric("Highest points · selected snapshot", f"{highest_points:,}")
m4.metric("Competitions", f"{len(competitions):,}")

summary_tabs = st.tabs(["Overview", "Competitors", "Competitions", "Venues & complexes"])

with summary_tabs[0]:
    st.subheader("Selected ranking snapshot")
    st.caption(f"Showing {len(filtered_rankings):,} of {len(rankings):,} competitors matching the sidebar filters.")
    if filtered_rankings.empty:
        st.info("No competitors match the selected ranking filters.")
    else:
        top = filtered_rankings.sort_values(["rank", "points"], ascending=[True, False]).head(10)
        left, right = st.columns(2)
        country_counts = filtered_rankings.groupby("country", dropna=False).size().reset_index(name="competitors")
        country_counts["country"] = country_counts["country"].fillna("Unknown")
        left.plotly_chart(
            px.bar(country_counts.sort_values("competitors", ascending=False).head(15),
                   x="country", y="competitors", title="Ranked competitors by country"),
            use_container_width=True,
        )
        right.plotly_chart(
            px.scatter(filtered_rankings, x="rank", y="points", color="league", hover_name="competitor",
                       hover_data=["country", "movement"], title="Rank compared with points"),
            use_container_width=True,
        )
        st.markdown("**Top 10 competitors**")
        st.dataframe(top[["rank", "movement", "points", "competitions_played", "competitor", "country"]],
                     use_container_width=True, hide_index=True)
    if not competitions.empty:
        type_counts = competitions.groupby("type", dropna=False).size().reset_index(name="competitions")
        type_counts["type"] = type_counts["type"].fillna("Unknown")
        st.plotly_chart(px.bar(type_counts.sort_values("competitions", ascending=False),
                               x="type", y="competitions", title="Competitions by event type"),
                        use_container_width=True)

with summary_tabs[1]:
    st.subheader("Search and filter competitors")
    st.caption(f"Showing {len(filtered_rankings):,} of {len(rankings):,} competitors in the selected snapshot.")
    if filtered_rankings.empty:
        st.info("No competitors match the selected filters.")
    else:
        st.dataframe(
            filtered_rankings[["rank", "movement", "points", "competitions_played", "competitor", "country", "league"]]
            .sort_values(["rank", "competitor"]),
            use_container_width=True, hide_index=True,
        )
        country_analysis = filtered_rankings.groupby("country", dropna=False).agg(
            competitors=("competitor_id", "nunique"), average_points=("points", "mean"), total_points=("points", "sum")
        ).reset_index().rename(columns={"country": "Country"})
        country_analysis["Country"] = country_analysis["Country"].fillna("Unknown")
        country_analysis["average_points"] = country_analysis["average_points"].round(1)
        st.subheader("Country-wise ranking analysis")
        st.dataframe(country_analysis.sort_values("competitors", ascending=False), use_container_width=True, hide_index=True)
        st.download_button("Download filtered rankings", filtered_rankings.to_csv(index=False),
                           "tennis_rankings.csv", "text/csv")

with summary_tabs[2]:
    st.subheader("Competition catalog")
    if competitions.empty:
        st.info("No competition data is available.")
    else:
        f1, f2, f3 = st.columns(3)
        type_options = sorted(competitions["type"].dropna().unique().tolist())
        level_options = sorted(competitions["level"].dropna().unique().tolist())
        category_options = sorted(competitions["category"].dropna().unique().tolist())
        selected_types = f1.multiselect("Event type", type_options)
        selected_levels = f2.multiselect("Competition level", level_options)
        selected_categories = f3.multiselect("Category", category_options)
        comp_view = competitions.copy()
        if selected_types:
            comp_view = comp_view[comp_view["type"].isin(selected_types)]
        if selected_levels:
            comp_view = comp_view[comp_view["level"].isin(selected_levels)]
        if selected_categories:
            comp_view = comp_view[comp_view["category"].isin(selected_categories)]
        st.caption(f"Showing {len(comp_view):,} of {len(competitions):,} competitions. Use the filters above this table.")
        st.dataframe(comp_view, use_container_width=True, hide_index=True)
        type_category = comp_view.assign(type=comp_view["type"].fillna("Unknown")).groupby(
            ["category", "type"], dropna=False
        ).size().reset_index(name="count")
        st.plotly_chart(px.bar(type_category, x="category", y="count", color="type",
                               title="Event type distribution by category", barmode="stack"),
                        use_container_width=True)

with summary_tabs[3]:
    st.subheader("Venues and complexes")
    if venues.empty:
        st.info("No venue data is available.")
    else:
        v1, v2 = st.columns(2)
        venue_countries = sorted(venues["country"].dropna().unique().tolist())
        selected_venue_countries = v1.multiselect("Country", venue_countries)
        venue_query = v2.text_input("Search venue, city, or complex")
        venue_view = venues.copy()
        if selected_venue_countries:
            venue_view = venue_view[venue_view["country"].isin(selected_venue_countries)]
        if venue_query:
            mask = venue_view[["venue", "city", "complex"]].astype(str).apply(
                lambda col: col.str.contains(venue_query, case=False, na=False)
            ).any(axis=1)
            venue_view = venue_view[mask]
        st.caption(f"Showing {len(venue_view):,} of {len(venues):,} venues. Use the venue filters above this table.")
        st.dataframe(venue_view, use_container_width=True, hide_index=True)
        complex_counts = venues.groupby("complex", dropna=False).size().reset_index(name="venues")
        st.markdown("**Complexes with the most venues**")
        st.dataframe(complex_counts.sort_values("venues", ascending=False).head(20),
                     use_container_width=True, hide_index=True)

st.caption("Data snapshot from Sportradar feeds. Queries run against the bundled SQLite database.")
st.markdown("<div style='text-align:center; padding:1rem 0; color:#7b8190;'>Developed by <strong>Alen S B</strong></div>", unsafe_allow_html=True)
