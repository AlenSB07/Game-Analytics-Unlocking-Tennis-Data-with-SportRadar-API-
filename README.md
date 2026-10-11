# Tennis Data Analytics

A small end-to-end project for collecting tennis competition, venue, and doubles-ranking data from the Sportradar Tennis API, storing it in a relational database, and exploring it in Jupyter.

## Project scope

- Competitions and their categories, types, levels, gender, and parent links.
- Complexes and their venues, locations, capacities, and timezones.
- Doubles ranking snapshots, league metadata, and competitor details.
- SQL analyses and interactive notebook charts. An optional Streamlit dashboard is also included.

The project brief suggests MySQL or PostgreSQL. This implementation defaults to SQLite for a simple local start; it also supports PostgreSQL through `DATABASE_URL`.

## Setup (Jupyter workflow)

1. Get a Sportradar Tennis API key from your account. You can start a Tennis trial through the [Sportradar developer portal](https://developer.sportradar.com/getting-started/docs/make-your-first-call).
2. Open `notebooks/tennis_data_analytics.ipynb` in Jupyter.
3. Run the cells from top to bottom. The setup cell installs the project libraries into the notebook's active Python environment. The notebook prompts privately for your API key, then fetches, stores, queries, and charts the data.
4. The final optional cell launches the Streamlit dashboard and prints its local URL.

You do not need to use a terminal for the project steps when using this notebook. The account/key setup happens on Sportradar's website; enter the key only in the notebook's hidden prompt. `notebooks/01_collect_competitions.ipynb` is a smaller notebook if you want to run just the first API feed.

To use PostgreSQL, install the listed dependencies and set, for example, `DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/tennis_analytics`.

## Refresh behavior

The notebook and `python scripts/ingest.py` upsert competitions, categories, complexes, venues, competitors, and ranking snapshots. Ranking rows are keyed by ranking year, week, and league, so historical weekly snapshots are retained. Sportradar documents these feeds as cached for roughly five minutes; ranking lists are updated weekly. API access, quotas, and coverage depend on your key and subscription tier.

## Streamlit dashboard and GitHub deployment

`app_mysql.py` connects directly to the MySQL tables created in the project workflow. It includes an overview, doubles ranking search and filters, competitor details, country analysis, leaderboards, competition filters, and venue search. Locally, run `streamlit run app_mysql.py` and enter MySQL connection details in the sidebar.

To share the app on the internet, push this project folder to a GitHub repository, then create an app at [Streamlit Community Cloud](https://share.streamlit.io/) using `app_mysql.py` as the entrypoint. The app needs a MySQL server reachable from the internet: `localhost` on your computer will not work from Community Cloud. Use a hosted MySQL database, create a limited database user for the app, and allow the app host to reach that server. Add the hosted connection values to the app's private Secrets settings using the format in `.streamlit/secrets.toml.example`. Never commit real passwords or API keys to GitHub.

Community Cloud uses `requirements.txt` beside the app entrypoint to install Python packages. The app connects using private Community Cloud Secrets when configured, and otherwise shows the local sidebar connection form. It reads the existing tables and does not fetch or modify API data.

Use `python scripts/ingest.py --help` to refresh only selected feeds. Failed feeds are reported separately; successful feeds are committed without discarding existing data.

## Database design

See `docs/project_report.md` for the schema rationale and `sql/queries.sql` for the required analysis queries. The database is initialized automatically when the app or ingestion script starts.

## Troubleshooting

- **403**: check that the key is valid and the access level matches it.
- **429**: the quota or request rate has been exceeded; wait before retrying.
- **No rows in the dashboard**: configure the key and run ingestion first.
- **Different feed shape**: inspect the raw JSON response for your API version; the ingestion code handles common v3 shapes and raises a useful error when a required collection is missing.

## Sources

- Sportradar [Competitions](https://developer.sportradar.com/tennis/reference/competitions)
- Sportradar [Complexes](https://developer.sportradar.com/tennis/reference/complexes)
- Sportradar [Doubles Competitor Rankings](https://developer.sportradar.com/tennis/reference/doubles-competitor-rankings)
- Sportradar [Tennis API basics](https://developer.sportradar.com/tennis/docs/tennis-ig-api-basics)
- Sportradar [Make your first API call](https://developer.sportradar.com/getting-started/docs/make-your-first-call)
