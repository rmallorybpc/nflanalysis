# Dashboard

## Issue #17: Overview Dashboard Page

The overview page is implemented as static assets under `dashboard/src`:

- `index.html`
- `styles.css`
- `overview.js`

Data source priority:

1. Live API endpoint: `GET /v1/dashboard/overview?season=2024`
2. Fallback fixture: `dashboard/public/overview.sample.json`

Quick local preview using Python static server:

```bash
cd dashboard/src
/usr/bin/python3 -m http.server 4173
```

Open in browser:

```bash
"$BROWSER" https://rmallorybpc.github.io/nflanalysis/dashboard/src/
```

## Issue #18: Team Detail Page With Movement Timeline

Team detail assets are implemented under `dashboard/src`:

- `team.html`
- `team.css`
- `team.js`

Data source priority:

1. Live API endpoint: `GET /v1/dashboard/team-detail?team_id=BUF&season=2024`
2. Fallback fixture: `dashboard/public/team-detail.sample.json`

Quick local preview:

```bash
cd dashboard/src
/usr/bin/python3 -m http.server 4173
```

Open in browser:

```bash
"$BROWSER" https://rmallorybpc.github.io/nflanalysis/dashboard/src/team.html
```

## Issue #19: Scenario Sandbox With Uncertainty Output

Scenario sandbox assets are implemented under `dashboard/src`:

- `scenario.html`
- `scenario.css`
- `scenario.js`

Data source priority:

1. Live API endpoint: `POST /v1/dashboard/scenario-sandbox`
2. Fallback fixture: `dashboard/public/scenario-sandbox.sample.json`

Quick local preview:

```bash
cd dashboard/src
/usr/bin/python3 -m http.server 4173
```

Open in browser:

```bash
"$BROWSER" https://rmallorybpc.github.io/nflanalysis/dashboard/src/scenario.html
```
