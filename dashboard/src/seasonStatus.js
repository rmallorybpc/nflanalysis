const TEAM_IDS = [
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
  "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
];

const OUTCOME_PATH_CANDIDATES = [
  "../../data/processed/team_week_outcomes.csv",
  "/data/processed/team_week_outcomes.csv",
  "/nflanalysis/data/processed/team_week_outcomes.csv",
];

const MIN_COMPLETED_GAMES = 16;
const MIN_COMPLETION_RATE = 0.9;

let outcomesIndexCache = null;
let latestCompletedSeasonCache = null;

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

function splitCsvLine(line) {
  const values = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    const next = line[i + 1];
    if (ch === '"') {
      if (inQuotes && next === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (ch === "," && !inQuotes) {
      values.push(current);
      current = "";
      continue;
    }

    current += ch;
  }

  values.push(current);
  return values.map(parseCsvCell);
}

function parseCsvRows(csvText) {
  const lines = String(csvText || "").trim().split(/\r?\n/);
  if (lines.length <= 1) {
    return [];
  }

  const headers = splitCsvLine(lines[0]);
  return lines.slice(1).map((line) => {
    const values = splitCsvLine(line);
    const row = {};
    headers.forEach((header, index) => {
      row[header] = (values[index] || "").trim();
    });
    return row;
  });
}

function toTeamId(value) {
  const normalized = String(value || "")
    .trim()
    .toUpperCase()
    .slice(0, 3);
  return TEAM_IDS.includes(normalized) ? normalized : "";
}

function summarizeSeason(outcomesIndex, season) {
  const teams = TEAM_IDS.map((teamId) => outcomesIndex[`${season}:${teamId}`]).filter(Boolean);
  const teamCount = TEAM_IDS.length;
  const teamsWithRows = teams.length;
  const teamsWithGames = teams.filter((row) => toFiniteNumber(row.games_played, 0) > 0).length;
  const teamsCompleted = teams.filter((row) => toFiniteNumber(row.games_played, 0) >= MIN_COMPLETED_GAMES).length;

  return {
    season,
    teamCount,
    teamsWithRows,
    teamsWithGames,
    teamsCompleted,
    completionRate: teamCount > 0 ? teamsCompleted / teamCount : 0,
  };
}

export function classifySeasonStatus(outcomesIndex, season) {
  const summary = summarizeSeason(outcomesIndex, season);

  if (summary.teamsWithGames === 0) {
    return "upcoming";
  }

  if (summary.completionRate >= MIN_COMPLETION_RATE) {
    return "completed";
  }

  return "in_progress";
}

export function getSeasonSummary(outcomesIndex, season) {
  const summary = summarizeSeason(outcomesIndex, season);
  return {
    ...summary,
    status: classifySeasonStatus(outcomesIndex, season),
  };
}

export async function loadTeamOutcomesIndex() {
  if (outcomesIndexCache) {
    return outcomesIndexCache;
  }

  let csvText = "";
  for (const path of OUTCOME_PATH_CANDIDATES) {
    try {
      const resp = await fetch(path);
      if (resp.ok) {
        csvText = await resp.text();
        break;
      }
    } catch (_err) {
      // Try next path.
    }
  }

  if (!csvText) {
    throw new Error("Unable to load team outcomes for season status checks.");
  }

  const rows = parseCsvRows(csvText);
  const indexed = {};

  rows.forEach((row) => {
    const teamId = toTeamId(row.team_id);
    const season = Number(row.nfl_season);
    if (!teamId || !Number.isFinite(season)) {
      return;
    }

    const snapshot = {
      team_id: teamId,
      season,
      nfl_week: toFiniteNumber(row.nfl_week, -1),
      wins: toFiniteNumber(row.wins),
      losses: toFiniteNumber(row.losses),
      ties: toFiniteNumber(row.ties),
      win_pct: toFiniteNumber(row.win_pct),
      games_played: toFiniteNumber(row.games_played),
    };

    const key = `${season}:${teamId}`;
    const current = indexed[key];
    if (!current) {
      indexed[key] = snapshot;
      return;
    }

    const hasMoreGames = snapshot.games_played > current.games_played;
    const sameGamesLaterWeek = snapshot.games_played === current.games_played
      && snapshot.nfl_week > current.nfl_week;
    if (hasMoreGames || sameGamesLaterWeek) {
      indexed[key] = snapshot;
    }
  });

  outcomesIndexCache = indexed;
  return indexed;
}

export async function getLatestCompletedSeason(fallbackSeason = 2025) {
  if (Number.isInteger(latestCompletedSeasonCache)) {
    return latestCompletedSeasonCache;
  }

  try {
    const outcomes = await loadTeamOutcomesIndex();
    const seasons = [...new Set(Object.keys(outcomes)
      .map((key) => Number(key.split(":")[0]))
      .filter((season) => Number.isFinite(season)))]
      .sort((a, b) => b - a);

    for (const season of seasons) {
      if (classifySeasonStatus(outcomes, season) === "completed") {
        latestCompletedSeasonCache = season;
        return season;
      }
    }
  } catch (_err) {
    // Fall through to fallback.
  }

  latestCompletedSeasonCache = fallbackSeason;
  return fallbackSeason;
}
