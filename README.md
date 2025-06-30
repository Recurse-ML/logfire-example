# Logfire Example Project

This is an example project that allows us to intentionally trigger Logfire alerts.
We use these alerts as testing input for Alert Investigator in squash.

## Quickstart

1. Replace LOGFIRE_TOKEN in `.env.sample` and move it to `.env`
2. Run `docker compose watch`
3. Now you can access the frontend in `localhost:5173` (see full routes and more info in `development.md`)

## (known) bugs

These are useful for triggering alerts.

1. Logging in (from web UI), will cause an alert due to `crud.py:37`
2. Running `docker compose exec backend pytest app/tests/api/routes/test_login.py` will cause an alert, as the test endpoint raises an Exception.
