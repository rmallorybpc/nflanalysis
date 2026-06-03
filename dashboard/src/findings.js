import {
  classifySeasonStatus,
  getLatestCompletedSeason,
  getSeasonSummary,
  loadTeamOutcomesIndex,
} from "./seasonStatus.js";
const DATA_ROOT = "./data";

const TEAM_IDS = [
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
  "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
];

const overviewPayloadCache = {};
const seasonSpendIndexCache = {};
let teamOutcomesCache = null;
let findingsLoadInFlight = false;
let dataManifestPromise = null;

const DEFAULT_FINDINGS_SEASONS = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026];
const FETCH_TIMEOUT_MS = 18000;
const FETCH_RETRIES = 2;

function seasonLabel(year) {
  return `${year} Season (Super Bowl Feb ${Number(year) + 1})`;
}

async function loadDataManifest() {
  if (dataManifestPromise) {
    return dataManifestPromise;
  }
  dataManifestPromise = fetch(`${DATA_ROOT}/manifest.json?t=${Date.now()}`, { cache: "no-store" })
    .then(async (resp) => {
      if (!resp.ok) {
        throw new Error(`status ${resp.status}`);
      }
      return resp.json();
    })
    .catch((err) => {
      dataManifestPromise = null;
      throw err;
    });
  return dataManifestPromise;
}

async function buildDataUrl(relativePath) {
  const manifest = await loadDataManifest();
  const builtAt = String(manifest?.built_at || "").trim();
  if (!builtAt) {
    return `${DATA_ROOT}/${relativePath}`;
  }
  return `${DATA_ROOT}/${relativePath}?v=${encodeURIComponent(builtAt)}`;
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

function dollarsToMillions(value) {
  return toFiniteNumber(value, 0) / 1_000_000;
}

function getContractTotalSpendRaw(row) {
  const total = toFiniteNumber(row?.contract_total, 0);
  if (total > 0) {
    return total;
  }

  const aav = toFiniteNumber(row?.contract_aav, 0);
  const years = toFiniteNumber(row?.contract_years, 0);
  if (aav > 0 && years > 0) {
    return aav * years;
  }

  return aav;
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
    const isExpectedPlaceholderWarning = String(message || "").startsWith("Data loaded with partial coverage")
      && String(message || "").includes("Some win-change placeholders are expected for upcoming seasons.");
    const allowRetry = showRetry && !isExpectedPlaceholderWarning;
    retryBtn.hidden = !allowRetry;
    retryBtn.disabled = loading;
  }
}

function resetFindingsCaches() {
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
  const expectedText = "Note: Validation shows no consistent geography winner across seasons; confidence is set to Low and reported scope counts are shown for transparency.";

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
  teamOutcomesCache = await loadTeamOutcomesIndex();
  return teamOutcomesCache;
}

async function loadOverviewData(season) {
  const overviewUrl = await buildDataUrl(`overview/${season}.json`);
  const resp = await fetchWithRetry(overviewUrl);
  if (!resp.ok) {
    throw new Error(`Static data request failed: status ${resp.status}`);
  }

  return resp.json();
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

  const manifest = await loadDataManifest();
  const seasonList = Array.isArray(manifest?.seasons) && manifest.seasons.length > 0
    ? manifest.seasons
    : DEFAULT_FINDINGS_SEASONS;

  const indexed = {};

  for (const season of seasonList) {
    try {
      const seasonUrl = await buildDataUrl(`season/${season}.json`);
      const resp = await fetchWithRetry(seasonUrl);
      if (!resp.ok) {
        continue;
      }
      const seasonPayload = await resp.json();
      TEAM_IDS.forEach((teamId) => {
        const timeline = Array.isArray(seasonPayload?.[teamId]?.timeline)
          ? seasonPayload[teamId].timeline
          : [];
        const inbound = timeline.filter((event) => (
          String(event.move_type || "").toLowerCase() === "free_agency"
            && toTeamId(event.to_team_id) === teamId
        ));

        const key = `${season}:${teamId}`;
        const current = indexed[key] || {
          teamId,
          season,
          totalSpendRaw: 0,
          moveCount: 0,
        };

        current.totalSpendRaw += inbound.reduce(
          (sum, event) => sum + getContractTotalSpendRaw(event),
          0
        );
        current.moveCount += inbound.length;
        indexed[key] = current;
      });
    } catch (_err) {
      // Leave this season out and allow downstream rows to surface partial coverage.
    }
  }

  seasonSpendIndexCache.index = indexed;
  return indexed;
}

async function loadGeoTable(seasons) {
  const tbody = document.getElementById("geoTableBody");
  if (!tbody) return;
  const teamOutcomes = await loadTeamOutcomes();

  const rows = [];
  let failedSeasons = 0;
  const reasonCounts = {};

  const seasonList = Array.isArray(seasons) && seasons.length > 0
    ? seasons
    : DEFAULT_FINDINGS_SEASONS;

  for (const season of seasonList) {
    try {
      const seasonStatus = classifySeasonStatus(teamOutcomes, season);
      if (seasonStatus === "upcoming") {
        rows.push(`
          <tr>
            <td>${seasonLabel(season)}</td>
            <td>Upcoming season - pending games</td>
            <td>Upcoming season - pending games</td>
            <td>Upcoming season - pending games</td>
            <td>Upcoming season - pending games</td>
          </tr>
        `);
        continue;
      }

      const payload = await loadOverviewBySeason(season);
      const geographyQuality = payload?.scope?.geography_data_quality || {};
      const totalEvents = toFiniteNumber(geographyQuality.total_events, 0);
      const unknownScopeEvents = toFiniteNumber(geographyQuality.unknown_scope_events, 0);
      const movesAnalyzed = Math.max(0, totalEvents - unknownScopeEvents);
      const evidenceRows = (payload?.charts?.geography_impact_profile || [])
        .filter((row) => row.outcome_name === "win_pct" && Number(row.move_count) > 0);

      const scopeCounts = {
        same_division: 0,
        cross_division: 0,
        cross_conference: 0,
      };
      evidenceRows.forEach((row) => {
        const scope = String(row.move_scope || "").trim();
        if (!(scope in scopeCounts)) {
          return;
        }
        scopeCounts[scope] = Math.max(scopeCounts[scope], Math.trunc(toFiniteNumber(row.move_count, 0)));
      });

      const shortAnswer = `Same Div: ${scopeCounts.same_division} | Cross Div: ${scopeCounts.cross_division} | Cross Conf: ${scopeCounts.cross_conference}`;

      const confidence = "Low — no consistent signal found";
      const confidenceTone = "low";

      const evidenceText = "No reliable difference between geography types across seasons. Standard deviation within each group exceeds the difference between groups.";

      const analyzedText = movesAnalyzed > 0
        ? `${movesAnalyzed} moves`
        : "n/a";
      const seasonalContext = seasonStatus === "upcoming"
        ? "Model signal only (season not yet played)."
        : "";

      rows.push(`
        <tr>
          <td>${seasonLabel(season)}</td>
          <td>${shortAnswer}</td>
          <td><span class="findings-confidence findings-confidence--${confidenceTone}">${confidence}</span></td>
          <td class="findings-cell-evidence">${evidenceText}${seasonalContext ? `<span class="findings-evidence-note"> | ${seasonalContext}</span>` : ""}</td>
          <td>${analyzedText}</td>
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

  const [seasonSpendIndex, teamOutcomes] = await Promise.all([
    loadSeasonSpendIndex(),
    loadTeamOutcomes(),
  ]);
  const rows = [];
  let failedSeasons = 0;
  let partialSeasonCount = 0;
  let upcomingSeasonCount = 0;
  const upcomingSeasons = [];
  let outcomeGapSeasonCount = 0;
  let seasonsWithWinOutcomes = 0;
  const reasonCounts = {};

  const seasonList = Array.isArray(seasons) && seasons.length > 0
    ? seasons
    : DEFAULT_FINDINGS_SEASONS;

  for (const season of seasonList) {
    try {
      const seasonSummary = getSeasonSummary(teamOutcomes, season);
      const seasonStatus = seasonSummary.status;
      const seasonSpendingRows = TEAM_IDS.map((teamId) => {
        const indexed = seasonSpendIndex[`${season}:${teamId}`] || {
          teamId,
          totalSpendRaw: 0,
          moveCount: 0,
        };
        return {
          teamId,
          totalSpendRaw: toFiniteNumber(indexed.totalSpendRaw, 0),
          totalSpendM: dollarsToMillions(toFiniteNumber(indexed.totalSpendRaw, 0)),
          moveCount: toFiniteNumber(indexed.moveCount, 0),
        };
      });

      const topSpenderSeed = [...seasonSpendingRows]
        .sort((a, b) => b.totalSpendRaw - a.totalSpendRaw)[0];
      const topSpenderTeamId = toTeamId(topSpenderSeed?.teamId);

      if (!topSpenderTeamId) {
        throw new Error("insufficient data");
      }

      const seasonSpendingByTeam = {};
      seasonSpendingRows.forEach((row) => {
        seasonSpendingByTeam[row.teamId] = row;
      });

      const spends = seasonSpendingRows
        .map((t) => t.totalSpendM)
        .filter((v) => v > 0);
      const leagueAvg = spends.length > 0
        ? spends.reduce((s, v) => s + v, 0) / spends.length
        : 0;

      const topSpender = seasonSpendingByTeam[topSpenderTeamId] || {
        teamId: topSpenderTeamId,
        totalSpendM: topSpenderSeed.totalSpendM,
      };

      const isUpcomingSeason = seasonSummary.teamsWithRows === 0 || seasonSummary.teamsWithGames === 0;
      if (isUpcomingSeason) {
        partialSeasonCount += 1;
        upcomingSeasonCount += 1;
        upcomingSeasons.push(season);
        rows.push(`
          <tr>
            <td>${seasonLabel(season)}</td>
            <td>$${leagueAvg.toFixed(0)}M</td>
            <td>${topSpender?.teamId || "—"}
              ($${(topSpender?.totalSpendM || 0).toFixed(0)}M)</td>
            <td>Upcoming season - pending games</td>
            <td>Upcoming season - pending games</td>
            <td>Upcoming season - pending games</td>
          </tr>
        `);
        continue;
      }

      const winDeltaByTeam = {};
      TEAM_IDS.forEach((teamId) => {
        const current = teamOutcomes[`${season}:${teamId}`];
        const prior = teamOutcomes[`${season - 1}:${teamId}`];
        if (!current || !prior) {
          return;
        }
        winDeltaByTeam[teamId] = toFiniteNumber(current.wins, 0) - toFiniteNumber(prior.wins, 0);
      });

      const winDeltaRows = Object.entries(winDeltaByTeam)
        .map(([teamId, winDelta]) => ({ teamId, winDelta }))
        .sort((a, b) => {
          if (b.winDelta !== a.winDelta) {
            return b.winDelta - a.winDelta;
          }
          return a.teamId.localeCompare(b.teamId);
        });

      const biggestGainTeamId = winDeltaRows[0]?.teamId || "";
      const topSpenderOutcome = Object.prototype.hasOwnProperty.call(winDeltaByTeam, topSpenderTeamId)
        ? winDeltaByTeam[topSpenderTeamId]
        : null;
      const biggestGainOutcome = Object.prototype.hasOwnProperty.call(winDeltaByTeam, biggestGainTeamId)
        ? winDeltaByTeam[biggestGainTeamId]
        : null;
      const biggestGainSpend = seasonSpendingByTeam[biggestGainTeamId]?.totalSpendM || 0;
      const biggestGainLabel = biggestGainTeamId
        ? `${biggestGainTeamId} ($${biggestGainSpend.toFixed(0)}M)`
        : "—";

      if (winDeltaRows.length > 0) {
        seasonsWithWinOutcomes += 1;
      }
      if (topSpenderOutcome == null || biggestGainOutcome == null) {
        partialSeasonCount += 1;
        outcomeGapSeasonCount += 1;
      }

      const fmtOutcome = (v) => (v == null ? "—"
        : `${v >= 0 ? "+" : ""}${v.toFixed(0)} wins`);

      const outcomeClass = (v) => (v == null ? ""
        : v > 0 ? ' class="findings-gain"'
        : v < 0 ? ' class="findings-loss"' : "");

      rows.push(`
        <tr>
          <td>${seasonLabel(season)}</td>
          <td>$${leagueAvg.toFixed(0)}M</td>
          <td>${topSpender?.teamId || "—"}
            ($${(topSpender?.totalSpendM || 0).toFixed(0)}M)</td>
          <td${outcomeClass(topSpenderOutcome)}>
            ${fmtOutcome(topSpenderOutcome)}
          </td>
          <td>${biggestGainLabel}</td>
          <td${outcomeClass(biggestGainOutcome)}>
            ${fmtOutcome(biggestGainOutcome)}
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
          <td colspan="5" class="findings-error">
            Data unavailable (${reason})
          </td>
        </tr>
      `);
    }
  }

  tbody.innerHTML = rows.join("")
    || "<tr><td colspan=\"6\">No data available.</td></tr>";

  return {
    totalSeasons: seasonList.length,
    failedSeasons,
    partialSeasonCount,
    upcomingSeasonCount,
    upcomingSeasons,
    outcomeGapSeasonCount,
    outcomesAvailable: seasonsWithWinOutcomes > 0,
    reasonCounts,
  };
}

async function initFindings() {
  if (findingsLoadInFlight) {
    return;
  }
  findingsLoadInFlight = true;

  const params = new URLSearchParams(window.location.search);
  const season = params.get("season") || String(await getLatestCompletedSeason());
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
    const upcomingSeasonCount = spendSummary?.upcomingSeasonCount || 0;
    const outcomeGapSeasonCount = spendSummary?.outcomeGapSeasonCount || 0;
    // Show Retry only for actionable issues (hard failures or real missing-row gaps).
    const hasRealPartialProblems = outcomeGapSeasonCount > 0;
    const hasExpectedPlaceholderOnly = hasPartial && !hasRealPartialProblems;

    // Keep failure warnings first. Expected placeholders for non-completed
    // seasons should not raise warnings.
    if (hasFailures) {
      setFindingsStatus(
        `Some seasons could not be loaded (${reasonSummary || "see table rows for details"}). Tables show available rows only. Last updated at ${loadedAt}.`,
        "warning",
        { showRetry: true }
      );
    } else if (hasRealPartialProblems) {
      setFindingsStatus(
        `Data loaded with missing complete win-change rows (${outcomeGapSeasonCount} season${outcomeGapSeasonCount === 1 ? "" : "s"}). Retry may resolve transient data gaps. Last updated at ${loadedAt}.`,
        "warning",
        { showRetry: true }
      );
    } else {
      const upcomingSeasons = Array.isArray(spendSummary?.upcomingSeasons)
        ? spendSummary.upcomingSeasons
        : [];
      const upcomingSuffix = hasExpectedPlaceholderOnly && upcomingSeasonCount > 0
        ? ` ${upcomingSeasonCount} upcoming season${upcomingSeasonCount === 1 ? "" : "s"}${upcomingSeasons.length > 0 ? ` (${upcomingSeasons.join(", ")})` : ""} ${upcomingSeasonCount === 1 ? "is" : "are"} pending games.`
        : "";
      setFindingsStatus(
        `All findings data loaded successfully.${upcomingSuffix} Last updated at ${loadedAt}.`,
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
