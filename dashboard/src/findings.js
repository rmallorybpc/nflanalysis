const API_BASE = (window.NFL_API_BASE || "https://nflanalysis.onrender.com").replace(/\/$/, "");

const TEAM_IDS = [
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
  "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
];

const spendingRequestCache = {};
const overviewPayloadCache = {};
const seasonSpendIndexCache = {};
const teamDetailSpendCache = {};
let teamOutcomesCache = null;
let findingsLoadInFlight = false;

const DEFAULT_FINDINGS_SEASONS = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026];
const FETCH_TIMEOUT_MS = 18000;
const FETCH_RETRIES = 2;
const MAX_TEAM_DETAIL_CONCURRENCY = 6;

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

function aavDollarsToMillions(value) {
  return toFiniteNumber(value, 0) / 1_000_000;
}

async function fetchWithTimeout(url, options = {}, timeoutMs = FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeoutId);
  }
}

async function fetchWithRetry(url, options = {}, retries = FETCH_RETRIES) {
  let lastError = null;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      return await fetchWithTimeout(url, options);
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError || new Error("Network request failed");
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

function setFindingsStatus(message, type = "info", options = {}) {
  const { showRetry = false, loading = false } = options;
  const el = document.getElementById("findingsStatus");
  const textEl = document.getElementById("findingsStatusText");
  const retryBtn = document.getElementById("findingsRetryBtn");
  if (!el || !textEl) return;
  textEl.textContent = message;
  el.className = `findings-status findings-status--${type}`;
  el.setAttribute("data-status", type);
  if (retryBtn) {
    retryBtn.hidden = !showRetry;
    retryBtn.disabled = loading;
  }
}

function resetFindingsCaches() {
  Object.keys(spendingRequestCache).forEach((key) => {
    delete spendingRequestCache[key];
  });
  Object.keys(overviewPayloadCache).forEach((key) => {
    delete overviewPayloadCache[key];
  });
  teamOutcomesCache = null;
}

function toSeasonNumber(value) {
  const num = Number(value);
  return Number.isInteger(num) ? num : null;
}

function buildSeasonRange(start, end) {
  const startSeason = toSeasonNumber(start);
  const endSeason = toSeasonNumber(end);
  if (startSeason == null || endSeason == null || endSeason < startSeason) {
    return [];
  }
  // Guard against malformed payloads to avoid runaway ranges.
  if ((endSeason - startSeason) > 30) {
    return [];
  }
  const seasons = [];
  for (let season = startSeason; season <= endSeason; season += 1) {
    seasons.push(season);
  }
  return seasons;
}

function classifyLoadError(err) {
  const message = String(err?.message || err || "");
  if (err?.name === "AbortError" || /aborted|timeout/i.test(message)) {
    return "timeout";
  }
  if (/data not available for season=/i.test(message)) {
    return "unsupported season";
  }
  if (/status\s+\d+/i.test(message)) {
    const match = message.match(/status\s+(\d+)/i);
    return match ? `http ${match[1]}` : "http error";
  }
  if (/failed to fetch|network|cors/i.test(message)) {
    return "network/cors";
  }
  return "request failed";
}

function incrementReasonCount(reasonCounts, reason) {
  const key = String(reason || "request failed");
  reasonCounts[key] = (reasonCounts[key] || 0) + 1;
}

function formatReasonSummary(reasonCounts) {
  const entries = Object.entries(reasonCounts || {})
    .filter(([, count]) => Number(count) > 0)
    .sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) {
    return "";
  }
  return entries
    .map(([reason, count]) => `${reason}: ${count}`)
    .join(", ");
}

async function resolveFindingsSeasons(preferredSeason) {
  const seedSeasons = [
    toSeasonNumber(preferredSeason),
    2026,
    2025,
    2024,
  ].filter((v, idx, arr) => v != null && arr.indexOf(v) === idx);

  let lastError = null;
  for (const season of seedSeasons) {
    try {
      const payload = await loadOverviewBySeason(season);
      const range = payload?.scope?.season_range || {};
      const fromRange = buildSeasonRange(range.start, range.end);
      if (fromRange.length > 0) {
        return { seasons: fromRange, source: "api_scope" };
      }

      const fromCoverage = (payload?.charts?.season_coverage || [])
        .map((row) => toSeasonNumber(row?.season))
        .filter((v, idx, arr) => v != null && arr.indexOf(v) === idx)
        .sort((a, b) => a - b);

      if (fromCoverage.length > 0) {
        return { seasons: fromCoverage, source: "api_coverage" };
      }
    } catch (err) {
      lastError = err;
    }
  }

  return {
    seasons: [...DEFAULT_FINDINGS_SEASONS],
    source: "default",
    error: lastError,
  };
}

function statusTimestampLabel() {
  return new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function ensureGeographyCaveatNote() {
  const expectedText = "Note: Geography classifications require a known prior team for each signing. Moves where the player's prior team is unavailable are excluded from this comparison. Sample sizes vary by season - treat these figures as directional, not definitive.";

  const existing = document.querySelector(".findings-caveat");
  if (existing) {
    existing.textContent = expectedText;
    return;
  }

  const geoTableWrap = document.querySelector("#geoTable")?.closest(".findings-table-wrap");
  if (!geoTableWrap || !geoTableWrap.parentElement) {
    return;
  }

  const caveat = document.createElement("p");
  caveat.className = "findings-caveat";
  caveat.textContent = expectedText;
  geoTableWrap.insertAdjacentElement("afterend", caveat);
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
      const resp = await fetchWithRetry(path);
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
  const live = await fetchWithRetry(apiUrl);
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

async function loadSeasonSpendIndex() {
  if (seasonSpendIndexCache.index) {
    return seasonSpendIndexCache.index;
  }

  const candidates = [
    "../../data/processed/movement_events.csv",
    "/data/processed/movement_events.csv",
    "/nflanalysis/data/processed/movement_events.csv",
  ];

  let csvText = "";
  for (const path of candidates) {
    try {
      const resp = await fetchWithRetry(path);
      if (resp.ok) {
        csvText = await resp.text();
        break;
      }
    } catch (_err) {
      // Try the next candidate.
    }
  }

  if (!csvText) {
    throw new Error("Unable to load movement events for spending lookup.");
  }

  const rows = parseCsvRows(csvText);
  const indexed = {};

  rows.forEach((row) => {
    const season = Number(row.nfl_season);
    const teamId = toTeamId(row.to_team_id);
    const moveType = String(row.move_type || "").toLowerCase();
    if (!Number.isFinite(season) || !teamId || moveType !== "free_agency") {
      return;
    }

    const key = `${season}:${teamId}`;
    const current = indexed[key] || {
      teamId,
      season,
      totalAavRaw: 0,
      moveCount: 0,
    };

    current.totalAavRaw += toFiniteNumber(row.contract_aav, 0);
    current.moveCount += 1;
    indexed[key] = current;
  });

  seasonSpendIndexCache.index = indexed;
  return indexed;
}

async function loadTeamDetailSpendByTeam(season, teamId) {
  const normalizedTeamId = toTeamId(teamId);
  if (!normalizedTeamId) {
    return null;
  }

  const cacheKey = `${season}:${normalizedTeamId}`;
  if (teamDetailSpendCache[cacheKey]) {
    return teamDetailSpendCache[cacheKey];
  }

  const promise = (async () => {
    const params = new URLSearchParams({
      team_id: normalizedTeamId,
      season: String(season),
    });
    const resp = await fetchWithRetry(`${API_BASE}/v1/dashboard/team-detail?${params.toString()}`);
    if (!resp.ok) {
      throw new Error(`status ${resp.status}`);
    }

    const payload = await resp.json();
    const timeline = Array.isArray(payload?.timeline) ? payload.timeline : [];
    const inboundFreeAgency = timeline.filter(
      (event) => String(event.move_type || "").toLowerCase() === "free_agency"
        && toTeamId(event.to_team_id) === normalizedTeamId
    );

    const totalAavRaw = inboundFreeAgency.reduce(
      (sum, event) => sum + toFiniteNumber(event.contract_aav, 0),
      0
    );

    // Team-detail contract_aav values are raw dollars; convert to millions once.
    const totalAavM = aavDollarsToMillions(totalAavRaw);

    return {
      teamId: normalizedTeamId,
      totalAavM,
      moveCount: inboundFreeAgency.length,
    };
  })();

  teamDetailSpendCache[cacheKey] = promise.catch((err) => {
    delete teamDetailSpendCache[cacheKey];
    throw err;
  });

  return teamDetailSpendCache[cacheKey];
}

async function loadSeasonSpendingByTeam(season, onProgress) {
  if (spendingRequestCache[season]) {
    return spendingRequestCache[season];
  }

  const promise = (async () => {
    let settledCount = 0;
    const total = TEAM_IDS.length;
    onProgress?.(settledCount, total);

    const spendByTeam = {};
    let fulfilledCount = 0;

    let nextIndex = 0;
    const workerCount = Math.min(MAX_TEAM_DETAIL_CONCURRENCY, total);

    async function runWorker() {
      while (nextIndex < total) {
        const teamId = TEAM_IDS[nextIndex];
        nextIndex += 1;

        try {
          const params = new URLSearchParams({
            team_id: teamId,
            season: String(season),
          });

          const resp = await fetchWithRetry(`${API_BASE}/v1/dashboard/team-detail?${params.toString()}`);
          if (!resp.ok) {
            throw new Error(`status ${resp.status}`);
          }

          const payload = await resp.json();
          const timeline = Array.isArray(payload?.timeline) ? payload.timeline : [];
          const inboundFreeAgency = timeline.filter(
            (event) => String(event.move_type || "").toLowerCase() === "free_agency"
              && toTeamId(event.to_team_id) === teamId
          );

          const totalAavM = inboundFreeAgency.reduce(
            (sum, event) => sum + aavDollarsToMillions(event.contract_aav),
            0
          );

          spendByTeam[teamId] = {
            teamId,
            totalAavM,
            moveCount: inboundFreeAgency.length,
          };
          fulfilledCount += 1;
        } catch (_err) {
          // Keep processing remaining teams to allow partial season output.
        } finally {
          settledCount += 1;
          onProgress?.(settledCount, total);
        }
      }
    }

    await Promise.all(
      Array.from({ length: workerCount }, () => runWorker())
    );

    if (fulfilledCount === 0) {
      throw new Error("Unable to load team spending data.");
    }

    return {
      spendByTeam,
      fulfilledCount,
      totalCount: total,
    };
  })();

  spendingRequestCache[season] = promise
    .catch((err) => {
      delete spendingRequestCache[season];
      throw err;
    });
  return spendingRequestCache[season];
}

async function loadGeoTable(seasons) {
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
  let failedSeasons = 0;
  const reasonCounts = {};

  const seasonList = Array.isArray(seasons) && seasons.length > 0
    ? seasons
    : DEFAULT_FINDINGS_SEASONS;

  for (const season of seasonList) {
    try {
      const payload = await loadOverviewBySeason(season);
      const sensitivityProfiles = payload?.charts?.geography_sensitivity_profiles || [];
      const knownScopeProfile = sensitivityProfiles.find((profile) => profile.mode === "known_scope_only");
      const claimPolicy = payload?.scope?.geography_claim_policy || null;

      const geoRows = (knownScopeProfile?.points || payload?.charts?.geography_impact_profile || [])
        .filter((r) => r.outcome_name === "win_pct" && r.move_count > 0);

      if (geoRows.length < 2) {
        incrementReasonCount(reasonCounts, "insufficient data");
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
      const summary = knownScopeProfile?.win_pct_summary || null;
      const policyReason = Array.isArray(claimPolicy?.reasons)
        ? claimPolicy.reasons.find((reason) => reason !== "ok") || null
        : null;
      const reasonLabel = policyReason
        ? policyReason.replaceAll("_", " ")
        : null;

      const fmtImpact = (v) => (v != null ? Number(v).toFixed(6) : "—");

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
            ${summary && summary.robustness_flag === false ? " (exploratory)" : ""}
            ${claimPolicy && claimPolicy.can_make_strong_claim === false && reasonLabel ? ` [${reasonLabel}]` : ""}
          </td>
        </tr>
      `);
    } catch (err) {
      failedSeasons += 1;
      const reason = classifyLoadError(err);
      incrementReasonCount(reasonCounts, reason);
      rows.push(`
        <tr>
          <td>${seasonLabel(season)}</td>
          <td colspan="4" class="findings-error">
            Data unavailable (${reason})
          </td>
        </tr>
      `);
    }
  }

  tbody.innerHTML = rows.join("")
    || "<tr><td colspan=\"5\">No data available.</td></tr>";

  return {
    totalSeasons: seasonList.length,
    failedSeasons,
    reasonCounts,
  };
}

async function loadSpendTable(seasons) {
  const tbody = document.getElementById("spendTableBody");
  if (!tbody) return;

  const seasonSpendIndex = await loadSeasonSpendIndex();
  const rows = [];
  let failedSeasons = 0;
  let partialSeasonCount = 0;
  const reasonCounts = {};

  const seasonList = Array.isArray(seasons) && seasons.length > 0
    ? seasons
    : DEFAULT_FINDINGS_SEASONS;

  for (const season of seasonList) {
    try {
      const overview = await loadOverviewBySeason(season);
      const rankingRows = Array.isArray(overview?.charts?.league_ranking)
        ? overview.charts.league_ranking
        : [];

      if (rankingRows.length === 0) {
        throw new Error("insufficient data");
      }

      const misByTeam = {};
      rankingRows.forEach((row) => {
        const teamId = toTeamId(row.team_id);
        if (!teamId) {
          return;
        }
        misByTeam[teamId] = toFiniteNumber(row.mis_value, 0);
      });

      const biggestGainTeamId = toTeamId(rankingRows[0]?.team_id);
      if (!biggestGainTeamId) {
        throw new Error("insufficient data");
      }

      const seasonSpendingRows = TEAM_IDS.map((teamId) => {
        const indexed = seasonSpendIndex[`${season}:${teamId}`] || {
          teamId,
          totalAavRaw: 0,
          moveCount: 0,
        };
        return {
          teamId,
          totalAavRaw: toFiniteNumber(indexed.totalAavRaw, 0),
          totalAavM: aavDollarsToMillions(toFiniteNumber(indexed.totalAavRaw, 0)),
          moveCount: toFiniteNumber(indexed.moveCount, 0),
        };
      });

      const topSpenderSeed = [...seasonSpendingRows]
        .sort((a, b) => b.totalAavRaw - a.totalAavRaw)[0];
      const topSpenderTeamId = toTeamId(topSpenderSeed?.teamId);

      if (!topSpenderTeamId) {
        throw new Error("insufficient data");
      }

      const teamsForDetail = [...new Set([topSpenderTeamId, biggestGainTeamId])];
      const detailResults = await Promise.all(
        teamsForDetail.map((teamId) => loadTeamDetailSpendByTeam(season, teamId).catch(() => null))
      );

      const detailByTeam = {};
      detailResults.forEach((detail) => {
        if (detail?.teamId) {
          detailByTeam[detail.teamId] = detail;
        }
      });

      if (!detailByTeam[topSpenderTeamId] || !detailByTeam[biggestGainTeamId]) {
        partialSeasonCount += 1;
      }

      const spends = seasonSpendingRows
        .map((t) => t.totalAavM)
        .filter((v) => v > 0);
      const leagueAvg = spends.length > 0
        ? spends.reduce((s, v) => s + v, 0) / spends.length
        : 0;

      const topSpender = detailByTeam[topSpenderTeamId] || {
        teamId: topSpenderTeamId,
        totalAavM: topSpenderSeed.totalAavM,
      };
      const topSpenderOutcome = Object.prototype.hasOwnProperty.call(misByTeam, topSpenderTeamId)
        ? misByTeam[topSpenderTeamId]
        : null;

      const biggestGainLabel = biggestGainTeamId || "—";
      const biggestGainOutcome = Object.prototype.hasOwnProperty.call(misByTeam, biggestGainTeamId)
        ? misByTeam[biggestGainTeamId]
        : null;
      const biggestGainSpend = detailByTeam[biggestGainTeamId]?.totalAavM || 0;

      const fmtOutcome = (v) => (v == null ? "—"
        : `MIS ${v >= 0 ? "+" : ""}${v.toFixed(6)}`);

      const outcomeClass = (v) => (v == null ? ""
        : v > 0 ? ' class="findings-gain"'
        : v < 0 ? ' class="findings-loss"' : "");

      rows.push(`
        <tr>
          <td>${seasonLabel(season)}</td>
          <td>$${leagueAvg.toFixed(0)}M</td>
          <td>${topSpender?.teamId || "—"}
            ($${(topSpender?.totalAavM || 0).toFixed(0)}M)</td>
          <td${outcomeClass(topSpenderOutcome)}>
            ${fmtOutcome(topSpenderOutcome)}
          </td>
          <td>${biggestGainLabel}</td>
          <td${outcomeClass(biggestGainOutcome)}>
            ${fmtOutcome(biggestGainOutcome)}
          </td>
          <td>$${biggestGainSpend.toFixed(0)}M</td>
        </tr>
      `);
    } catch (err) {
      failedSeasons += 1;
      const reason = classifyLoadError(err);
      incrementReasonCount(reasonCounts, reason);
      rows.push(`
        <tr>
          <td>${seasonLabel(season)}</td>
          <td colspan="6" class="findings-error">
            Data unavailable (${reason})
          </td>
        </tr>
      `);
    }
  }

  tbody.innerHTML = rows.join("")
    || "<tr><td colspan=\"7\">No data available.</td></tr>";

  return {
    totalSeasons: seasonList.length,
    failedSeasons,
    partialSeasonCount,
    outcomesAvailable: true,
    reasonCounts,
  };
}

async function initFindings() {
  if (findingsLoadInFlight) {
    return;
  }
  findingsLoadInFlight = true;

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
  ensureGeographyCaveatNote();

  try {
    setFindingsStatus("Loading findings data...", "info", { loading: true, showRetry: false });

    const seasonResolution = await resolveFindingsSeasons(Number(season));
    const findingsSeasons = seasonResolution.seasons;

    if (seasonResolution.source === "default") {
      console.warn("Findings season resolution fell back to default seasons:", seasonResolution.error);
    }

    const [geoSummary, spendSummary] = await Promise.all([
      loadGeoTable(findingsSeasons),
      loadSpendTable(findingsSeasons),
    ]);

    const hasFailures = (geoSummary?.failedSeasons || 0) > 0
      || (spendSummary?.failedSeasons || 0) > 0;
    const hasPartial = (spendSummary?.partialSeasonCount || 0) > 0
      || !spendSummary?.outcomesAvailable;

    const combinedReasonCounts = {};
    Object.entries(geoSummary?.reasonCounts || {}).forEach(([reason, count]) => {
      combinedReasonCounts[reason] = (combinedReasonCounts[reason] || 0) + count;
    });
    Object.entries(spendSummary?.reasonCounts || {}).forEach(([reason, count]) => {
      combinedReasonCounts[reason] = (combinedReasonCounts[reason] || 0) + count;
    });

    const reasonSummary = formatReasonSummary(combinedReasonCounts);

    const loadedAt = statusTimestampLabel();

    if (hasFailures) {
      setFindingsStatus(
        `Some seasons could not be loaded (${reasonSummary || "see table rows for details"}). Tables show available rows only. Last updated at ${loadedAt}.`,
        "warning",
        { showRetry: true }
      );
    } else if (hasPartial) {
      setFindingsStatus(
        `Data loaded with partial coverage. Some win-change fields may show placeholders. Last updated at ${loadedAt}.`,
        "warning",
        { showRetry: true }
      );
    } else {
      setFindingsStatus(
        `All findings data loaded successfully. Last updated at ${loadedAt}.`,
        "success",
        { showRetry: false }
      );
    }
  } finally {
    findingsLoadInFlight = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const retryBtn = document.getElementById("findingsRetryBtn");
  if (retryBtn) {
    retryBtn.addEventListener("click", () => {
      resetFindingsCaches();
      initFindings().catch((err) => console.error(err));
    });
  }

  initFindings().catch((err) => console.error(err));
});
