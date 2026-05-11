const API_BASE = (window.NFL_API_BASE || "https://nflanalysis.onrender.com").replace(/\/$/, "");

const TEAM_IDS = [
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
  "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
];

const state = {
  season: 2026,
  teamId: "BUF",
};

const spendingCache = {};
const spendingRequestCache = {};
const overviewPayloadCache = {};
let teamOutcomesCache = null;
let spendingResizeBound = false;
let activeSpendingSeason = null;

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

function getNumberInputValue(id, fallback) {
  const value = Number(document.getElementById(id).value);
  return Number.isFinite(value) && value > 0 ? Math.trunc(value) : fallback;
}

function syncControls() {
  ensureTeamOptions();
  document.getElementById("seasonInput").value = String(state.season);
  document.getElementById("teamInput").value = state.teamId;
  updateTeamLinks();
}

function ensureTeamOptions() {
  const select = document.getElementById("teamInput");
  if (select.options.length > 0) {
    return;
  }
  TEAM_IDS.forEach((teamId) => {
    const option = document.createElement("option");
    option.value = teamId;
    option.textContent = teamId;
    select.appendChild(option);
  });
}

function updateTeamLinks() {
  const params = new URLSearchParams({
    team_id: state.teamId,
    season: String(state.season),
  });
  document.getElementById("welcomeLink").href = `./welcome.html?${params.toString()}`;
  const href = `./team.html?${params.toString()}`;
  document.getElementById("openTeamBtn").href = href;
  document.getElementById("teamPageLink").href = href;
  document.getElementById("scenarioPageLink").href = `./scenario.html?${params.toString()}`;
  document.getElementById("explorerLink").href = `./explorer.html?${params.toString()}`;
}

function rewriteNavLinksFromParams() {
  const params = new URLSearchParams(window.location.search);
  const season = params.get("season") || "";
  const teamId = params.get("team_id") || "";
  const suffix = (season || teamId)
    ? `?season=${encodeURIComponent(season)}&team_id=${encodeURIComponent(teamId)}`
    : "";

  document.querySelectorAll("nav a").forEach((a) => {
    const base = a.href.split("?")[0];
    if (suffix) {
      a.href = base + suffix;
    }
  });
}

function navigateToTeam(teamId) {
  const safeTeam = toTeamId(teamId) || state.teamId;
  const params = new URLSearchParams({
    team_id: safeTeam,
    season: String(state.season),
  });
  window.location.href = `./team.html?${params.toString()}`;
}

function fmt(num) {
  return Number(num).toFixed(3);
}

function setStatus(message, isError = false) {
  const el = document.getElementById("statusMessage");
  el.textContent = message || "";
  el.classList.toggle("error", Boolean(isError));
}

function renderEmptyState(container, message) {
  container.innerHTML = `<div class="empty-state">${message}</div>`;
}

function renderErrorState(container) {
  container.innerHTML = '<div class="empty-state error-state">Failed to load data. Refresh the page or try again.</div>';
}

function teamSeasonEmptyMessage() {
  return `No data available for ${state.teamId} ${state.season}.`;
}

function skeletonRows(count, widths, height = 20, rowClass = "") {
  return Array.from({ length: count }, (_, index) => {
    const width = widths[index] || widths[widths.length - 1] || "100%";
    const className = rowClass ? `skeleton-row ${rowClass}` : "skeleton-row";
    return `<div class="${className} skeleton" style="height:${height}px;width:${width};"></div>`;
  }).join("");
}

function showOverviewSkeletons() {
  document.getElementById("rankingChart").innerHTML = `<div class="skeleton-list">${skeletonRows(5, ["100%", "100%", "100%", "100%", "100%"], 20)}</div>`;
  document.getElementById("distributionChart").innerHTML = `<div class="skeleton-list">${skeletonRows(3, ["100%", "70%", "45%"], 20)}</div>`;
  document.getElementById("scopeList").innerHTML = `<div class="skeleton-list">${skeletonRows(2, ["100%", "100%"], 16)}</div>`;
  document.getElementById("seasonCoverageChart").innerHTML = "";
  document.getElementById("geographyChart").innerHTML = `<div class="skeleton-list">${skeletonRows(3, ["100%", "70%", "45%"], 20)}</div>`;
  document.getElementById("spendingChart").innerHTML = `<div class="skeleton" style="height:320px;width:100%;border-radius:8px;"></div>`;
}

function showOverviewErrorStates() {
  renderErrorState(document.getElementById("rankingChart"));
  renderErrorState(document.getElementById("distributionChart"));
  renderErrorState(document.getElementById("scopeList"));
  renderErrorState(document.getElementById("seasonCoverageChart"));
  renderErrorState(document.getElementById("geographyChart"));
  renderErrorState(document.getElementById("spendingChart"));
}

function isOverviewPayload(payload) {
  return Boolean(
    payload &&
      payload.cards &&
      payload.cards.top_positive_team &&
      payload.cards.top_negative_team &&
      payload.charts
  );
}

function resetRenderedData() {
  document.getElementById("topPositiveCard").innerHTML = "";
  document.getElementById("topNegativeCard").innerHTML = "";
  document.getElementById("leagueCard").innerHTML = "";
  document.getElementById("rankingChart").innerHTML = "";
  document.getElementById("distributionChart").innerHTML = "";
  document.getElementById("scopeList").innerHTML = "";
  document.getElementById("seasonCoverageChart").innerHTML = "";
  document.getElementById("geographyChart").innerHTML = "";
  document.getElementById("spendingChart").innerHTML = "";
}

function toFiniteNumber(value, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function linearRegression(points) {
  const n = points.length;
  const sumX = points.reduce((s, p) => s + p.x, 0);
  const sumY = points.reduce((s, p) => s + p.y, 0);
  const sumXY = points.reduce((s, p) => s + p.x * p.y, 0);
  const sumX2 = points.reduce((s, p) => s + p.x * p.x, 0);
  const denominator = n * sumX2 - sumX * sumX;
  if (!Number.isFinite(denominator) || Math.abs(denominator) < 1e-12) {
    return { slope: 0, intercept: sumY / Math.max(n, 1) };
  }
  const slope = (n * sumXY - sumX * sumY) / denominator;
  const intercept = (sumY - slope * sumX) / n;
  return { slope, intercept };
}

function spendingContextNote(aavM, winDelta, moveCount) {
  const highSpend = aavM > 100;
  const bigGain = winDelta > 0.10;
  const flatResult = Math.abs(winDelta) <= 0.05;
  const declined = winDelta < -0.05;

  if (highSpend && bigGain) {
    return "High spend with strong win improvement — one of the better FA returns in this dataset.";
  }
  if (highSpend && flatResult) {
    return "Large investment with little measurable win impact — wins may have come from other factors.";
  }
  if (highSpend && declined) {
    return "High spend but win total declined — the Fox Sports cautionary tale pattern.";
  }
  if (!highSpend && bigGain) {
    return "Efficient offseason — significant win improvement without top-tier spending.";
  }
  if (!highSpend && declined) {
    return "Limited spending and win decline — roster did not improve through FA.";
  }
  if (moveCount === 0) {
    return "No inbound free agency signings were logged for this season.";
  }
  return "Mixed result — spending and outcome roughly in line with league average.";
}

function pctSigned(value) {
  const pct = toFiniteNumber(value, 0) * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

function winsSigned(value) {
  const rounded = Math.round(toFiniteNumber(value, 0) * 10) / 10;
  return `${rounded >= 0 ? "+" : ""}${rounded}`;
}

function formatRecord(outcomeRow) {
  if (!outcomeRow) {
    return "n/a";
  }
  return `${outcomeRow.wins}-${outcomeRow.losses}`;
}

function escapeTooltipText(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function parseCsvRows(csvText) {
  const lines = String(csvText || "").trim().split(/\r?\n/);
  if (lines.length <= 1) {
    return [];
  }

  const headers = lines[0].split(",").map((header) => header.trim());
  return lines.slice(1).map((line) => {
    const values = line.split(",");
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
    throw new Error("Unable to load team outcomes for spending chart.");
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

  teamOutcomesCache = indexed;
  return indexed;
}

async function loadOverviewBySeason(season) {
  if (overviewPayloadCache[season]) {
    return overviewPayloadCache[season];
  }
  const payload = await loadOverviewData(season);
  overviewPayloadCache[season] = payload;
  return payload;
}

function showSpendingLoadingState(progress, total) {
  const container = document.getElementById("spendingChart");
  if (!container) {
    return;
  }
  container.innerHTML = `
    <div class="skeleton" style="height:320px;width:100%;border-radius:8px;"></div>
    <div class="spending-progress">Loading spending data... (${progress} of ${total} teams)</div>
  `;
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

function buildSpendingTooltip(point, season) {
  const note = spendingContextNote(point.totalAavM, point.winPctDelta, point.moveCount);
  const lines = [
    `${point.teamId} ${seasonLabel(season)}`,
    `FA Spend: $${point.totalAavM.toFixed(1)}M across ${point.moveCount} signings`,
    `Win Change: ${winsSigned(point.winDeltaWins)} wins (${pctSigned(point.winPctDelta)})`,
    `Current: ${formatRecord(point.currentOutcome)} (${(toFiniteNumber(point.currentOutcome?.win_pct) * 100).toFixed(1)}%)`,
    `Prior: ${point.priorOutcome ? `${formatRecord(point.priorOutcome)} (${(toFiniteNumber(point.priorOutcome?.win_pct) * 100).toFixed(1)}%)` : "n/a"}`,
    `MIS (model estimate): ${point.misValue.toFixed(3)}`,
  ];

  if (point.winDeltaWins > 0) {
    lines.push(`Spending efficiency: $${(point.totalAavM / point.winDeltaWins).toFixed(1)}M per win gained`);
  }
  lines.push(`Context: ${note}`);

  return lines.join(" | ");
}

function renderSpendingSvg(season, cached) {
  const container = document.getElementById("spendingChart");
  if (!container) {
    return;
  }

  if (season <= 2017) {
    renderEmptyState(container, "Win change data requires a prior season. Select 2018 or later.");
    return;
  }

  const validPoints = cached.points.filter((point) => point.hasPrior);
  if (validPoints.length < 10) {
    renderEmptyState(container, "Insufficient data to render spending chart for this season.");
    return;
  }

  const width = Math.max(340, Math.min(container.clientWidth || 700, 700));
  const height = 400;
  const margin = { top: 20, right: 20, bottom: 60, left: 60 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const maxSpend = Math.max(...cached.points.map((point) => point.totalAavM), 0);
  const xMax = maxSpend > 0 ? maxSpend * 1.1 : 10;
  const maxAbsDelta = Math.max(...validPoints.map((point) => Math.abs(point.winPctDelta)), 0.05);
  const yMax = maxAbsDelta;

  const xScale = (value) => margin.left + (Math.max(0, value) / xMax) * innerW;
  const yScale = (value) => margin.top + ((yMax - value) / (2 * yMax)) * innerH;

  const xTicks = 6;
  const yTicks = 6;

  const trendPoints = validPoints.map((point) => ({ x: point.totalAavM, y: point.winPctDelta }));
  const trend = trendPoints.length >= 2 ? linearRegression(trendPoints) : null;

  const svgParts = [];
  svgParts.push(`<svg viewBox="0 0 ${width} ${height}" width="100%" height="400" role="img" aria-label="FA spending vs win change scatter plot">`);
  svgParts.push(`<line x1="${margin.left}" y1="${margin.top + innerH}" x2="${margin.left + innerW}" y2="${margin.top + innerH}" stroke="#94a3b8" stroke-width="1" />`);
  svgParts.push(`<line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + innerH}" stroke="#94a3b8" stroke-width="1" />`);

  const yZero = yScale(0);
  svgParts.push(`<line x1="${margin.left}" y1="${yZero}" x2="${margin.left + innerW}" y2="${yZero}" stroke="#94a3b8" stroke-width="1" stroke-dasharray="4 4" />`);

  for (let i = 0; i <= xTicks; i += 1) {
    const tickValue = (xMax / xTicks) * i;
    const x = xScale(tickValue);
    svgParts.push(`<line x1="${x}" y1="${margin.top + innerH}" x2="${x}" y2="${margin.top + innerH + 6}" stroke="#94a3b8" stroke-width="1" />`);
    svgParts.push(`<text x="${x}" y="${margin.top + innerH + 20}" text-anchor="middle" fill="#64748b" font-size="10">$${Math.round(tickValue)}M</text>`);
  }

  for (let i = 0; i <= yTicks; i += 1) {
    const tickValue = yMax - (2 * yMax * i) / yTicks;
    const y = yScale(tickValue);
    svgParts.push(`<line x1="${margin.left - 6}" y1="${y}" x2="${margin.left}" y2="${y}" stroke="#94a3b8" stroke-width="1" />`);
    const pct = Math.round(tickValue * 100);
    const label = `${pct >= 0 ? "+" : ""}${pct}%`;
    svgParts.push(`<text x="${margin.left - 10}" y="${y + 3}" text-anchor="end" fill="#64748b" font-size="10">${label}</text>`);
  }

  svgParts.push(`<text x="${margin.left + innerW / 2}" y="${height - 16}" text-anchor="middle" fill="#64748b" font-size="11">Total FA Spending (AAV, $M)</text>`);
  svgParts.push(`<text x="16" y="${margin.top + innerH / 2}" text-anchor="middle" fill="#64748b" font-size="11" transform="rotate(-90 16 ${margin.top + innerH / 2})">Win% Change vs Prior Season</text>`);

  svgParts.push(`<text class="spending-quadrant-label" x="${margin.left + innerW - 6}" y="${margin.top + 14}" text-anchor="end" fill="#16a34a">High Spend / Big Gain</text>`);
  svgParts.push(`<text class="spending-quadrant-label" x="${margin.left + 6}" y="${margin.top + 14}" text-anchor="start" fill="#16a34a">Low Spend / Big Gain</text>`);
  svgParts.push(`<text class="spending-quadrant-label" x="${margin.left + innerW - 6}" y="${margin.top + innerH - 8}" text-anchor="end" fill="#dc2626">High Spend / Declined</text>`);
  svgParts.push(`<text class="spending-quadrant-label" x="${margin.left + 6}" y="${margin.top + innerH - 8}" text-anchor="start" fill="#dc2626">Low Spend / Declined</text>`);

  if (trend) {
    const x1 = 0;
    const x2 = xMax;
    const y1 = trend.slope * x1 + trend.intercept;
    const y2 = trend.slope * x2 + trend.intercept;
    const sx1 = xScale(x1);
    const sx2 = xScale(x2);
    const sy1 = yScale(Math.max(-yMax, Math.min(yMax, y1)));
    const sy2 = yScale(Math.max(-yMax, Math.min(yMax, y2)));
    svgParts.push(`<line x1="${sx1}" y1="${sy1}" x2="${sx2}" y2="${sy2}" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="5 4" />`);
    svgParts.push(`<text x="${sx2 - 2}" y="${sy2 - 4}" text-anchor="end" fill="#64748b" font-size="10">trend</text>`);
  }

  cached.points.forEach((point) => {
    const x = xScale(point.totalAavM);
    const y = yScale(point.hasPrior ? point.winPctDelta : 0);
    const radius = 8 + Math.min(4, point.moveCount / 6);
    let fill = "#9ca3af";
    if (point.hasPrior) {
      if (point.winPctDelta > 0.05) {
        fill = "#22c55e";
      } else if (point.winPctDelta < -0.05) {
        fill = "#ef4444";
      } else {
        fill = "#f59e0b";
      }
    }
    svgParts.push(`<circle cx="${x}" cy="${y}" r="${radius}" fill="${fill}" stroke="#ffffff" stroke-width="1" />`);
    svgParts.push(`<text x="${x}" y="${y + 3}" text-anchor="middle" fill="#ffffff" font-size="9" font-weight="700">${point.teamId}</text>`);
  });

  svgParts.push(`</svg>`);

  const overlayDots = cached.points.map((point) => {
    const x = xScale(point.totalAavM);
    const y = yScale(point.hasPrior ? point.winPctDelta : 0);
    const tooltip = escapeTooltipText(buildSpendingTooltip(point, season));
    return `<span class="spending-tooltip-dot" data-tooltip="${tooltip}" style="left:${x}px;top:${y}px;min-width:260px;--tooltip-width:260px;" tabindex="0" aria-label="${point.teamId} spending details"></span>`;
  }).join("");

  container.innerHTML = `
    <div class="spending-chart-wrap">
      ${svgParts.join("")}
      <div class="spending-overlay" aria-hidden="false">${overlayDots}</div>
    </div>
    ${cached.hasMissingPrior ? '<div class="spending-note">Prior season data unavailable for some teams.</div>' : ""}
  `;
}

async function renderSpendingChart(season, currentPayload = null) {
  activeSpendingSeason = season;
  if (!spendingResizeBound) {
    spendingResizeBound = true;
    window.addEventListener("resize", () => {
      if (activeSpendingSeason && spendingCache[activeSpendingSeason]) {
        renderSpendingSvg(activeSpendingSeason, spendingCache[activeSpendingSeason]);
      }
    });
  }

  if (spendingCache[season]) {
    renderSpendingSvg(season, spendingCache[season]);
    return;
  }

  if (season <= 2017) {
    renderEmptyState(document.getElementById("spendingChart"), "Win change data requires a prior season. Select 2018 or later.");
    return;
  }

  showSpendingLoadingState(0, TEAM_IDS.length);

  const [spendingByTeam, outcomesIndex, currentOverview] = await Promise.all([
    loadSeasonSpendingByTeam(season, showSpendingLoadingState),
    loadTeamOutcomes(),
    currentPayload ? Promise.resolve(currentPayload) : loadOverviewBySeason(season),
  ]);

  // Keep a prior-season overview fetch in the flow for parity with existing overview sourcing.
  if (season > 2017) {
    loadOverviewBySeason(season - 1).catch(() => null);
  }

  const misByTeam = {};
  const rankingRows = Array.isArray(currentOverview?.charts?.league_ranking)
    ? currentOverview.charts.league_ranking
    : [];
  rankingRows.forEach((row) => {
    const teamId = toTeamId(row.team_id);
    if (!teamId) {
      return;
    }
    misByTeam[teamId] = toFiniteNumber(row.mis_value);
  });

  const points = TEAM_IDS.map((teamId) => {
    const spending = spendingByTeam[teamId] || { totalAavM: 0, moveCount: 0 };
    const currentOutcome = outcomesIndex[`${season}:${teamId}`] || null;
    const priorOutcome = outcomesIndex[`${season - 1}:${teamId}`] || null;
    const hasPrior = Boolean(currentOutcome && priorOutcome);
    const currentWinPct = toFiniteNumber(currentOutcome?.win_pct);
    const priorWinPct = toFiniteNumber(priorOutcome?.win_pct);

    return {
      teamId,
      totalAavM: toFiniteNumber(spending.totalAavM),
      moveCount: toFiniteNumber(spending.moveCount),
      hasPrior,
      currentOutcome,
      priorOutcome,
      winPctDelta: hasPrior ? currentWinPct - priorWinPct : 0,
      winDeltaWins: hasPrior ? toFiniteNumber(currentOutcome?.wins) - toFiniteNumber(priorOutcome?.wins) : 0,
      misValue: toFiniteNumber(misByTeam[teamId]),
    };
  });

  const cached = {
    points,
    hasMissingPrior: points.some((point) => !point.hasPrior),
  };

  spendingCache[season] = cached;
  if (activeSpendingSeason === season) {
    renderSpendingSvg(season, cached);
  }
}

function setCard(el, title, value, meta) {
  el.innerHTML = `
    <h3>${title}</h3>
    <div class="value">${value}</div>
    <div class="meta">${meta}</div>
  `;
}

function renderCards(payload) {
  const cards = payload.cards;
  const confidenceLabel = (flag) => (flag ? "Low confidence" : "High confidence");
  const miszTooltip = "Movement Impact Score (standardized) — a score comparing this move to all other moves. Above 1.0 is a strong positive signal. Below -1.0 is a strong negative signal.";

  setCard(
    document.getElementById("topPositiveCard"),
    `Top Positive (${cards.top_positive_team.team_id})`,
    fmt(cards.top_positive_team.mis_value),
    `<span data-tooltip="${miszTooltip}">MISz</span> ${fmt(cards.top_positive_team.mis_z)} | 90% [${fmt(cards.top_positive_team.interval_90.low)}, ${fmt(cards.top_positive_team.interval_90.high)}] | ${confidenceLabel(cards.top_positive_team.low_confidence_flag)}`
  );

  setCard(
    document.getElementById("topNegativeCard"),
    `Top Negative (${cards.top_negative_team.team_id})`,
    fmt(cards.top_negative_team.mis_value),
    `<span data-tooltip="${miszTooltip}">MISz</span> ${fmt(cards.top_negative_team.mis_z)} | 90% [${fmt(cards.top_negative_team.interval_90.low)}, ${fmt(cards.top_negative_team.interval_90.high)}] | ${confidenceLabel(cards.top_negative_team.low_confidence_flag)}`
  );

  setCard(
    document.getElementById("leagueCard"),
    "League Summary",
    fmt(cards.league_net_mis),
    `High confidence share ${Math.round(cards.high_confidence_share * 100)}%`
  );
}

function renderRanking(payload) {
  const container = document.getElementById("rankingChart");
  const template = document.getElementById("rankingRowTemplate");
  container.innerHTML = "";

  const rows = Array.isArray(payload?.charts?.league_ranking) ? payload.charts.league_ranking : [];
  if (rows.length === 0) {
    renderEmptyState(container, teamSeasonEmptyMessage());
    return;
  }

  const maxAbs = Math.max(...rows.map((row) => Math.abs(row.mis_value)), 1);

  rows.forEach((row, index) => {
    const node = template.content.firstElementChild.cloneNode(true);
    if (index === 0) {
      node.id = "movement-card-1";
    }
    node.classList.add("clickable");
    node.setAttribute("role", "button");
    node.tabIndex = 0;
    node.setAttribute("aria-label", `Open ${row.team_id} team detail`);
    node.querySelector(".bar-label").textContent = `${row.rank}. ${row.team_id}`;
    node.querySelector(".bar-fill").style.width = `${Math.max((Math.abs(row.mis_value) / maxAbs) * 100, 4)}%`;
    node.querySelector(".bar-fill").style.background =
      row.mis_value >= 0
        ? "linear-gradient(90deg, #2e8540, #84a98c)"
        : "linear-gradient(90deg, #b00020, #d56b7f)";
    node.querySelector(".bar-value").textContent = fmt(row.mis_value);
    if (row.team_id === state.teamId) {
      node.classList.add("ranking-row-selected");
      node.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    node.addEventListener("click", () => navigateToTeam(row.team_id));
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        navigateToTeam(row.team_id);
      }
    });
    container.appendChild(node);
  });
}

function renderDistribution(payload) {
  const rows = Array.isArray(payload?.charts?.outcome_distribution) ? payload.charts.outcome_distribution : [];
  const container = document.getElementById("distributionChart");
  const template = document.getElementById("distributionRowTemplate");

  if (rows.length === 0) {
    renderEmptyState(container, teamSeasonEmptyMessage());
    return;
  }

  const grouped = {};
  for (const row of rows) {
    if (!grouped[row.outcome_name]) {
      grouped[row.outcome_name] = [];
    }
    grouped[row.outcome_name].push(row);
  }

  container.innerHTML = "";

  Object.keys(grouped)
    .sort()
    .forEach((outcome) => {
      const node = template.content.firstElementChild.cloneNode(true);
      const labelEl = node.querySelector(".stack-label");
      if (String(outcome).trim().toLowerCase() === "win_pct") {
        labelEl.innerHTML = '<span data-tooltip="Win percentage impact — how much this team\'s player moves are estimated to change their chances of winning games. A value of +0.020 means approximately 2 more wins per 100 games.">win_pct</span>';
      } else {
        labelEl.textContent = outcome;
      }
      const values = node.querySelector(".stack-values");
      grouped[outcome].forEach((point) => {
        const pill = document.createElement("span");
        pill.className = "pill";
        pill.textContent = `${point.bin_label}: ${point.count}`;
        values.appendChild(pill);
      });
      container.appendChild(node);
    });
}

function renderScope(payload) {
  const scope = payload.scope;
  const scopeList = document.getElementById("scopeList");

  if (!scope) {
    renderEmptyState(scopeList, "No data available.");
    return;
  }

  const moveTypes = scope.included_move_types.join(", ");
  const outcomes = scope.outcomes.join(", ");
  const geos = (scope.geography_dimensions || []).join(", ");

  scopeList.innerHTML = `
    <div class="scope-pill">Seasons: ${scope.season_range.start}-${scope.season_range.end} (${scope.season_count})</div>
    <div class="scope-pill">Teams tracked: ${scope.team_count}</div>
    <div class="scope-pill">Move types: ${moveTypes}</div>
    <div class="scope-pill">Move counts: trade ${scope.move_type_counts.trade}, free_agency ${scope.move_type_counts.free_agency}</div>
    <div class="scope-pill">Outcomes: ${outcomes}</div>
    <div class="scope-pill">Geography: ${geos}</div>
  `;
}

function renderSeasonCoverage(payload) {
  const points = Array.isArray(payload?.charts?.season_coverage) ? payload.charts.season_coverage : [];
  const container = document.getElementById("seasonCoverageChart");
  const template = document.getElementById("seasonCoverageRowTemplate");
  container.innerHTML = "";

  if (points.length === 0) {
    renderEmptyState(container, teamSeasonEmptyMessage());
    return;
  }

  const maxTeams = Math.max(...points.map((point) => point.team_count), 1);
  points.forEach((point) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector(".bar-label").textContent = String(point.season);
    node.querySelector(".bar-fill").style.width = `${Math.max((point.team_count / maxTeams) * 100, 4)}%`;
    node.querySelector(".bar-fill").style.background = "linear-gradient(90deg, #6b8f74, #84a98c)";
    node.querySelector(".bar-value").textContent = `${point.team_count} teams | W${point.latest_week}`;
    container.appendChild(node);
  });
}

function renderGeography(payload) {
  const rows = Array.isArray(payload?.charts?.geography_impact_profile) ? payload.charts.geography_impact_profile : [];
  const container = document.getElementById("geographyChart");
  const template = document.getElementById("geoRowTemplate");
  container.innerHTML = "";

  if (rows.length === 0) {
    renderEmptyState(container, "No data available.");
    return;
  }

  rows.forEach((row) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector(".geo-scope").textContent = row.move_scope;
    node.querySelector(".geo-outcome").textContent = row.outcome_name;
    node.querySelector(".geo-count").textContent = `${row.move_count} moves`;
    node.querySelector(".geo-impact").textContent = fmt(row.avg_abs_impact);
    container.appendChild(node);
  });
}

function applyMeta(payload) {
  document.getElementById("seasonLabel").textContent = `Season: ${payload.season}`;
  document.getElementById("generatedLabel").textContent = `Generated: ${payload.generated_at}`;
}

async function loadOverviewData(season) {
  const apiUrl = buildOverviewUrl(season);
  try {
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

    const livePayload = await live.json();
    if (isOverviewPayload(livePayload)) {
      return livePayload;
    }
    if (livePayload && livePayload.error) {
      throw new Error(`Live API error: ${livePayload.error}`);
    }
    throw new Error("Live API returned an invalid overview payload format.");
  } catch (err) {
    const detail = err instanceof Error ? err.message : "request failed";
    throw new Error(`Data collection failed. Please check source data coverage and pipeline outputs. ${detail}`);
  }
}

async function refreshOverview() {
  state.season = getNumberInputValue("seasonInput", state.season);
  state.teamId = toTeamId(document.getElementById("teamInput").value) || state.teamId;
  syncControls();
  writeQueryState();
  showOverviewSkeletons();

  setStatus(`Loading season ${state.season}...`);
  try {
    const payload = await loadOverviewData(state.season);
    applyMeta(payload);
    renderCards(payload);
    renderRanking(payload);
    renderDistribution(payload);
    renderScope(payload);
    renderSeasonCoverage(payload);
    renderGeography(payload);
    renderSpendingChart(state.season, payload).catch((err) => {
      renderEmptyState(document.getElementById("spendingChart"), "Insufficient data to render spending chart for this season.");
      console.error(err);
    });
    setStatus("");
  } catch (err) {
    resetRenderedData();
    showOverviewErrorStates();
    document.getElementById("seasonLabel").textContent = `Season: ${state.season}`;
    document.getElementById("generatedLabel").textContent = "Generated: --";
    const message = err instanceof Error
      ? err.message
      : "Data collection failed. Please check source data coverage and pipeline outputs.";
    setStatus(message, true);
  }
}

function parseQueryState() {
  const params = new URLSearchParams(window.location.search);
  const hasSeason = params.has("season");
  const hasTeamId = params.has("team_id");
  const season = Number(params.get("season"));
  if (Number.isFinite(season) && season > 0) {
    state.season = Math.trunc(season);
  }
  const teamId = toTeamId(params.get("team_id"));
  if (teamId) {
    state.teamId = teamId;
  }
  return { hasSeason, hasTeamId };
}

function writeQueryState() {
  const params = new URLSearchParams({
    season: String(state.season),
    team_id: state.teamId,
  });
  window.history.replaceState({}, "", `?${params.toString()}`);
}

function bindControls() {
  const refreshAction = () => {
    refreshOverview().catch((err) => console.error(err));
  };

  document.getElementById("refreshBtn").addEventListener("click", () => {
    refreshAction();
  });

  document.getElementById("teamInput").addEventListener("change", (event) => {
    const normalized = toTeamId(event.target.value);
    if (normalized) {
      state.teamId = normalized;
      updateTeamLinks();
      document.querySelectorAll("#rankingChart .bar-row").forEach((el) => {
        const label = el.querySelector(".bar-label")?.textContent?.trim();
        const teamInLabel = label?.replace(/^\d+\.\s*/, "").trim();
        el.classList.toggle("ranking-row-selected", teamInLabel === normalized);
        if (teamInLabel === normalized) {
          el.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      });
    }
  });

  ["seasonInput", "teamInput"].forEach((id) => {
    document.getElementById(id).addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        refreshAction();
      }
    });
  });

  return { refreshAction };
}

function main() {
  rewriteNavLinksFromParams();
  const { hasSeason, hasTeamId } = parseQueryState();
  syncControls();
  const { refreshAction } = bindControls();
  if (hasSeason || hasTeamId) {
    refreshAction();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  main();
});
