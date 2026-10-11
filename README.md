# Tennis Rankings Explorer

A Streamlit dashboard for exploring Sportradar tennis competitions, venues, complexes, and doubles competitor rankings.

## Run locally

Install the packages in `requirements.txt`, then run:

```bash
streamlit run app.py
```

The app reads `tennis_data.sqlite`, a bundled SQLite snapshot, so it does not need a MySQL server or a hosted database connection. The database is a read-only project snapshot; it does not contain database passwords or API keys.

## Deploy on Streamlit Community Cloud

Deploy this repository with `app.py` as the entrypoint. Keep `app.py`, `requirements.txt`, and `tennis_data.sqlite` at the repository root. Streamlit Cloud will install the requirements and serve the dashboard at a public `streamlit.app` URL.

## Project data

The database contains the exported competition categories, competitions, sports complexes, venues, ranking snapshots, competitors, and competitor rankings. The venue export currently contains 2,288 rows; replace the snapshot with a fresh export if you have the complete local venue table.
