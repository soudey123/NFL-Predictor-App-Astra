# Gridiron

A complete local NFL prediction application for the **2026 regular season**. Browse all 18 weeks and 32 teams, explore quarterback/rest scenarios, save your picks, and compare your accuracy with the model as final results arrive.

## Run

Requires Python **3.10+** and a modern browser. No pip, npm, API key, or account needed.

```sh
cd outputs/gridiron
python3 server.py
```

If your terminal is already in this folder, just run `python3 server.py`. Open **http://127.0.0.1:8000**. Stop with Ctrl+C. To use another port: `PORT=8001 python3 server.py` (PowerShell: `$env:PORT=8001; python server.py`).

```sh
python3 -m unittest discover -s tests -v
```

## Using it

- Select a week or use the arrows, then optionally filter by team. The initial week follows a Tuesday rollover during the 2026 season, clamped to weeks 1–18.
- Each card shows the model's projected score, winner, and a probability bar.
- Click a team to save your pick. Click it again to clear it, or select the other team to change it. Changes lock at the stored kickoff time, or when the feed marks a game underway/final.
- Open **Explore a what-if** and adjust either team's quarterback penalty or extra rest. The backend immediately recomputes the score, probability, and factor contributions. Close the dialog to return; scenarios are intentionally transient.
- Click **Refresh ESPN** for the selected week to retrieve updated schedule/status/results. It also updates the season-wide scoreboard. Refresh past weeks after games finish to grade them. There is no background polling.
- Accuracy is correct picks / decided, completed games, with ties excluded. The model and user each have their own sample size, shown beside their percentage; these samples need not match. Pending counts include saved forecasts or picks for unfinished games.

## Stack and architecture

Python's standard-library HTTP server + SQLite + plain HTML/CSS/JavaScript keeps installation at one command and avoids a frontend build toolchain. It is a loopback-only, single-user app, not a public multi-user deployment.

- `server.py`: HTTP endpoints, input limits, same-origin JSON mutation checks, kickoff locks, forecast ledger, SQLite transactions, grading.
- `data.py`: isolated ESPN fetching and validation, atomic schedule caching, normalized game/team data.
- `model.py`: deterministic pure prediction function, separate from storage and HTTP.
- `static/`: responsive frontend with keyboard-accessible native controls and scenario dialog.
- `cache/1.json` through `18.json`: real ESPN 2026 regular-season schedule snapshots, 272 games.
- `standings.json`: real ESPN 2025 regular-season team-statistics snapshot.
- `tests/test_app.py`: model and integration tests, isolated temporary SQLite databases.

`gridiron.sqlite3` is created beside the server. It stores normalized game payloads (including results), baseline forecasts, picks, and pick timestamps. Restarting the server or browser preserves these. Back up the file with the app stopped. Set `GRIDIRON_DB` to use a different database file. Cache files hold the latest successfully fetched schedule.

A model forecast is saved on the **first pregame visit** and is never rewritten by scenario experiments or subsequent refreshes. Games first loaded after kickoff get a clearly marked retrospective forecast and are excluded from model accuracy. Visit a week before kickoff to register its model forecasts. No historical accuracy is fabricated.

## Data source and refresh behavior

Real, public ESPN JSON endpoints, verified September 7, 2026:

- Schedule/results: [2026 week 1 scoreboard](https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=2026&seasontype=2&week=1). Change `week` to 1–18.
- Team statistics: [2025 standings](https://site.web.api.espn.com/apis/v2/sports/football/nfl/standings?season=2025).

All shipped schedule and statistics data are real source snapshots, **not mock fixtures**. The app can browse and predict offline immediately. The refresh button requests the real scoreboard from the backend, validates the season/week and game fields, then atomically replaces that week's cache. Network or invalid-feed failures retain the last valid snapshot and display a warning. First-time missing caches produce an actionable error if ESPN cannot be reached. The displayed snapshot time is the cache file's modification time; copying files may change it. The bundled snapshots were obtained September 7, 2026.

These are publicly reachable endpoints without a contractual availability guarantee or stable official API specification. Refresh depends on ESPN availability. Team statistics remain pinned to 2025; refresh does not silently change the model inputs. Font styling optionally uses Google Fonts, with system fallbacks offline. There are no tracking services, remote user-pick storage, or external scripts.

To swap providers, replace `data.schedule()` and `data.teams()` while preserving their normalized dictionaries. Keep provider game IDs stable across refreshes; they are the ledger keys. Supply UTC ISO timestamps, `Scheduled` for pregame status, a final flag, integer scores, and neutral-site flags. Team inputs are per-game points for/against/differential and a 0–1 win rate. Update source attribution in the UI and this README. For another season, update the season, URL, snapshots, prior-year stats, and frontend season labels/week rollover together; use a fresh database to keep season ledgers separate.

## Explainable model v1.0

For each team, `n = wins + losses + ties`, point differential is `(pointsFor − pointsAgainst) / n`, and win rate is `(wins + 0.5 × ties) / n`.

The predicted home margin in points is:

```text
m = 0.65 × (home point differential − away point differential)
  + 6.0 × (home win rate − away win rate)
  + 1.5 home advantage (0 at neutral sites)
  + 0.25 × (home extra rest days − away extra rest days)
  − home QB penalty + away QB penalty
```

Coefficients are explicit heuristic choices, not fitted coefficients. The point-differential weight regresses prior-season strength; record adds a smaller signal. Baseline extra rest and QB penalties are zero because neither is fetched automatically. Users may choose 0–4 extra rest days and 0–7 QB penalty points in 0.5-point increments.

`P(home) = 1 / (1 + exp(−m / 7))`, capped to 5–95%. The model picks home when `m >= 0`; an exact neutral tie is a documented deterministic home-side tiebreak at 50%.

Expected total = `(home PF/game + away PA/game + away PF/game + home PA/game) / 2`, capped to 28–65. Predicted scores are `round((total + m) / 2)` and `round((total − m) / 2)`, bounded below at zero. Python rounds half-to-even. If rounding creates a tie, add one point to the model winner. This is a point forecast, not a simulated possession model; scores are not restricted to common football scoring combinations.

## Limitations

- Probabilities are uncalibrated; no out-of-sample performance is claimed.
- Uses last season's aggregate strength; no schedule-strength correction, recency weighting, current-year form, weather, roster updates, automatic injuries, or playoff modeling.
- Cached kickoff times may be stale after rescheduling; refresh before making picks. Times depend on your computer clock and browser timezone.
- No result polling: refresh each completed week to settle it. A postponed/canceled game may remain pending until the feed resolves it.
- Forecasts are frozen when first viewed, not at one standardized league-wide cutoff. Both scoreboard denominators are disclosed for fair interpretation.
- Standard-library HTTP serving is appropriate here only for local use. No authentication, concurrent multi-user separation, TLS, or production deployment configuration is included. Do not expose it publicly.

## If I had more time

Fit and calibrate the model on chronological holdout seasons; add opponent-adjusted rolling stats, QB availability and actual rest, confidence intervals, probability calibration and Brier scoring, automatic result ingestion with audit history, season win-total/playoff simulations, and forecast export. Package a production server and identity layer if this becomes a shared service.
