const API_BASE = (window.NFL_API_BASE || "https://nflanalysis.onrender.com").replace(/\/$/, "");

const TEAM_IDS = [
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
  "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
];

const spendingRequestCache = {};
const overviewPayloadCache = {};
let teamOutcomesCache = null;

const FINDINGS_SEASONS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025];

function seasonLabel(year) {
  return `${year} Season (Super Bowl Feb ${Number(year) + 1})`;
}

function buildOverviewUrl(season) {
  const params = new URLSearchParams({ season: String(season) });
  return `${API_BASE}/v1/dashboard/overview?${params.toString()}`;
}

function toTeamId(value) {
  const normalized = String(value || "")
    .trim()
    .toUpperCase()
    .slice(0, 3);
  return TEAM_IDS.includes(normalized) ? normalized : "";
}

function toFiniteNumber(value, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function parseCsvCell(value) {
  const raw = String(value || "").trim();
  if (raw.length >= 2 && raw.startsWith('"') && raw.endsWith('"')) {
    return raw.slice(1, -1).replace(/""/g, '"').trim();
  }
  return raw;
}

function parseCsvRows(csvText) {
  const lines = String(csvText || "").trim().split(/\r?\n/);
  if (lines.length <= 1) {
    return [];
  }

  const headers = lines[0].split(",").map(parseCsvCell);
  return lines.slice(1).map((line) => {
    const values = line.split(",").map(parseCsvCell);
    const row = {};
    headers.forEach((header, index) => {
      row[header] = (values[index] || "").trim();
    });
    return row;
  });
}

async function loadTeamOutcomes() {
  if (teamOutcomesCache) {
    return teamOutcomesCache;
  }

  const candidates = [
    "../../data/processed/team_week_outcomes.csv",
    "/data/processed/team_week_outcomes.csv",
    "/nflanalysis/data/processed/team_week_outcomes.csv",
  ];

  let csvText = "";
  for (const path of candidates) {
    try {
      const resp = await fetch(path);
      if (resp.ok) {
        csvText = await resp.text();
        break;
      }
    } catch (_err) {
      // Try the next candidate.
    }
  }

  if (!csvText) {
    throw new Error("Unable to load team outcomes for spending table.");
  }

  const rows = parseCsvRows(csvText);
  const indexed = {};
  rows.forEach((row) => {
    const teamId = toTeamId(row.team_id);
    const season = Number(row.nfl_season);
    if (!teamId || !Number.isFinite(season)) {
      return;
    }
    indexed[`${season}:${teamId}`] = {
      team_id: teamId,
      season,
      wins: toFiniteNumber(row.wins),
      losses: toFiniteNumber(row.losses),
      ties: toFiniteNumber(row.ties),
      win_pct: toFiniteNumber(row.win_pct),
      games_played: toFiniteNumber(row.games_played),
    };
  });

  if (Object.keys(indexed).length === 0) {
    throw new Error("Team outcomes CSV parsed, but no valid rows were indexed.");
  }

  teamOutcomesCache = indexed;
  return indexed;
}

async function loadOverviewData(season) {
  const apiUrl = buildOverviewUrl(season);
  const live = await fetch(apiUrl);
  if (!live.ok) {
    let detail = `status ${live.status}`;
    try {
      const errorPayload = await live.json();
      if (errorPayload && errorPayload.error) {
        detail = String(errorPayload.error);
      }
    } catch (_err) {
      // Ignore JSON parse errors and keep HTTP status detail.
    }
    throw new Error(`Live API request failed: ${detail}`);
  }

  return live.json();
}

async function loadOverviewBySeason(season) {
  if (overviewPayloadCache[season]) {
    return overviewPayloadCache[season];
  }
  const payload = await loadOverviewData(season);
  overviewPayloadCache[season] = payload;
  return payload;
}

async function loadSeasonSpendingByTeam(season, onProgress) {
  if (spendingRequestCache[season]) {
    return spendingRequestCache[season];
  }

  const promise = (async () => {
    let settledCount = 0;
    const total = TEAM_IDS.length;
    onProgress?.(settledCount, total);

    const requests = TEAM_IDS.map((teamId) => {
      const params = new URLSearchParams({
        team_id: teamId,
        season: String(season),
      });

      return fetch(`${API_BASE}/v1/dashboard/team-detail?${params.toString()}`)
        .then(async (resp) => {
          if (!resp.ok) {
            throw new Error(`status ${resp.status}`);
          }

          const payload = await resp.json();
          const timeline = Array.isArray(payload?.timeline) ? payload.timeline : [];
          const inboundFreeAgency = timeline.filter(
            (event) => String(event.move_type || "").toLowerCase() === "free_agency"
              && toTeamId(event.to_team_id) === teamId
          );

          const totalAavDollars = inboundFreeAgency.reduce(
            (sum, event) => sum + toFiniteNumber(event.contract_aav),
            0
          );

          return {
            teamId,
            totalAavM: totalAavDollars / 1_000_000,
            moveCount: inboundFreeAgency.length,
          };
        })
        .finally(() => {
          settledCount += 1;
          onProgress?.(settledCount, total);
        });
    });

    const results = await Promise.allSettled(requests);
    const spendByTeam = {};
    let fulfilledCount = 0;

    results.forEach((result) => {
      if (result.status === "fulfilled") {
        spendByTeam[result.value.teamId] = result.value;
        fulfilledCount += 1;
      }
    });

    if (fulfilledCount === 0) {
      throw new Error("Unable to load team spending data.");
    }

    return spendByTeam;
  })();

  spendingRequestCache[season] = promise;
  return promise;
}

async function loadGeoTable() {
  const tbody = document.getElementById("geoTableBody");
  if (!tbody) return;

  const scopeLabel = {
    same_division: "Same Div",
    cross_division: "Cross Div",
    cross_conference: "Cross Conf",
  };

  const scopeIcon = {
    same_division: "📍",
    cross_division: "🔀",
    cross_conference: "🌐",
  };

  const rows = [];

  for (const season of FINDINGS_SEASONS) {
    try {
      const payload = await loadOverviewBySeason(season);
      const geoRows = (payload?.charts?.geography_impact_profile || [])
        .filter((r) => r.outcome_name === "win_pct" && r.move_count > 0);

      if (geoRows.length < 2) {
        rows.push(`
          <tr>
            <td>${seasonLabel(season)}</td>
            <td colspan="4" class="findings-error">Data unavailable</td>
          </tr>
        `);
        continue;
      }

      const byScope = {};
      geoRows.forEach((r) => { byScope[r.move_scope] = r; });

      const sorted = [...geoRows].sort(
        (a, b) => b.avg_abs_impact - a.avg_abs_impact
      );
      const strongest = sorted[0];

      const fmtImpact = (v) => (v != null ? Number(v).toFixed(4) : "—");

      const isBest = (scope) => (
        scope === strongest.move_scope
          ? " class=\"findings-best\"" : ""
      );

      rows.push(`
        <tr>
          <td>${seasonLabel(season)}</td>
          <td${isBest("same_division")}>
            ${fmtImpact(byScope.same_division?.avg_abs_impact)}
          </td>
          <td${isBest("cross_division")}>
            ${fmtImpact(byScope.cross_division?.avg_abs_impact)}
          </td>
          <td${isBest("cross_conference")}>
            ${fmtImpact(byScope.cross_conference?.avg_abs_impact)}
          </td>
          <td>
            ${scopeIcon[strongest.move_scope] || ""}
            ${scopeLabel[strongest.move_scope] || strongest.move_scope}
          </td>
        </tr>
      `);
    } catch (_err) {
      rows.push(`
        <tr>
          <td>${seasonLabel(season)}</td>
          <td colspan="4" class="findings-error">
            Data unavailable
          </td>
        </tr>
      `);
    }
  }

  tbody.innerHTML = rows.join("")
    || "<tr><td colspan=\"5\">No data available.</td></tr>";
}

async function loadSpendTable() {
  const tbody = document.getElementById("spendTableBody");
  if (!tbody) return;

  let outcomes = {};
  let outcomesAvailable = true;
  try {
    outcomes = await loadTeamOutcomes();
  } catch (err) {
    outcomesAvailable = false;
    console.warn("Spending table loaded without win-change outcomes:", err);
  }
  const rows = [];

  for (const season of FINDINGS_SEASONS) {
    try {
      const spendingByTeam = await loadSeasonSpendingByTeam(
        season, () => {}
      );

      const spends = Object.values(spendingByTeam)
        .map((t) => t.totalAavM)
        .filter((v) => v > 0);
      const leagueAvg = spends.length > 0
        ? spends.reduce((s, v) => s + v, 0) / spends.length
        : 0;

      const topSpender = Object.values(spendingByTeam)
        .sort((a, b) => b.totalAavM - a.totalAavM)[0];

      const topSpenderWins = outcomesAvailable ? outcomes[
        `${season}:${topSpender?.teamId}`
      ] : null;
      const topSpenderPriorWins = outcomesAvailable ? outcomes[
        `${season - 1}:${topSpender?.teamId}`
      ] : null;
      const topSpenderDelta = topSpenderWins && topSpenderPriorWins
        ? topSpenderWins.wins - topSpenderPriorWins.wins
        : null;

      const winGains = outcomesAvailable ? TEAM_IDS.map((teamId) => {
        const cur = outcomes[`${season}:${teamId}`];
        const prev = outcomes[`${season - 1}:${teamId}`];
        if (!cur || !prev) return null;
        return {
          teamId,
          delta: cur.wins - prev.wins,
          spend: spendingByTeam[teamId]?.totalAavM || 0,
        };
      }).filter(Boolean) : [];

      const biggestGain = winGains.sort(
        (a, b) => b.delta - a.delta
      )[0];

      const fmtDelta = (v) => (v == null ? "—"
        : v > 0 ? `▲ +${v} wins`
        : v < 0 ? `▼ ${v} wins`
        : "— no change");

      const deltaClass = (v) => (v == null ? ""
        : v > 0 ? ' class="findings-gain"'
        : v < 0 ? ' class="findings-loss"' : "");

      rows.push(`
        <tr>
          <td>${seasonLabel(season)}</td>
          <td>$${leagueAvg.toFixed(0)}M</td>
          <td>${topSpender?.teamId || "—"}
            ($${(topSpender?.totalAavM || 0).toFixed(0)}M)</td>
          <td${deltaClass(topSpenderDelta)}>
            ${fmtDelta(topSpenderDelta)}
          </td>
          <td>${biggestGain?.teamId || "—"}</td>
          <td${deltaClass(biggestGain?.delta)}>
            ${fmtDelta(biggestGain?.delta)}
          </td>
          <td>$${(biggestGain?.spend || 0).toFixed(0)}M</td>
        </tr>
      `);
    } catch (_err) {
      rows.push(`
        <tr>
          <td>${seasonLabel(season)}</td>
          <td colspan="6" class="findings-error">
            Data unavailable
          </td>
        </tr>
      `);
    }
  }

  tbody.innerHTML = rows.join("")
    || "<tr><td colspan=\"7\">No data available.</td></tr>";
}

async function initFindings() {
  const params = new URLSearchParams(window.location.search);
  const season = params.get("season") || "2026";
  const teamId = toTeamId(params.get("team_id")) || "BUF";

  document.querySelectorAll("nav a").forEach((a) => {
    const base = a.href.split("?")[0];
    a.href = `${base}?season=${season}&team_id=${teamId}`;
  });

  const overviewParams = new URLSearchParams(
    { season, team_id: teamId }
  );
  const linkSuffix = `?${overviewParams.toString()}`;
  const overviewEl = document.getElementById("findingsOverviewLink");
  const spendEl = document.getElementById("findingsSpendLink");
  if (overviewEl) overviewEl.href = `./index.html${linkSuffix}`;
  if (spendEl) spendEl.href = `./index.html${linkSuffix}`;

  await Promise.all([
    loadGeoTable(),
    loadSpendTable(),
  ]);
}

document.addEventListener("DOMContentLoaded", () => {
  initFindings().catch((err) => console.error(err));
});
