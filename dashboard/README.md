# Dashboard

## Issue #17: Overview Dashboard Page

The overview page is implemented as static assets under `dashboard/src`:

- `index.html`
- `styles.css`
- `overview.js`

Data source priority:

1. Static payload: `./data/overview/<season>.json`
2. Cache-busting key source: `./data/manifest.json` (`built_at` appended as `?v=`)

If the payload is missing/unavailable, the page shows a data collection failure status and does not load sample fallback data.

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

1. Static season bundle: `./data/season/<season>.json`
2. Team lookup key: `payload[team_id]`
3. Cache-busting key source: `./data/manifest.json`

If the payload is missing/unavailable, the page shows a data collection failure status and does not load sample fallback data.

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

Data source priority:

1. Placeholder page only (Scenario Sandbox is currently being rebuilt)

No live compute requests are issued from the current placeholder page.

## Static Payload Build

Generate payloads with:

```bash
python3 scripts/build_static_payloads.py
```

Generated outputs live in `dashboard/src/data/` and are served directly by GitHub Pages.

Quick local preview:

```bash
cd dashboard/src
/usr/bin/python3 -m http.server 4173
```

Open in browser:

```bash
"$BROWSER" https://rmallorybpc.github.io/nflanalysis/dashboard/src/scenario.html
```
