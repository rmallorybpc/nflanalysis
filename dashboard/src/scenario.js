const API_BASE = (window.NFL_API_BASE || "https://nflanalysis.onrender.com").replace(/\/$/, "");
const API_URL = `${API_BASE}/v1/dashboard/scenario-sandbox`;
const PLAYERS_API_URL = `${API_BASE}/v1/dashboard/players`;

const TEAM_OPTIONS = [
  { id: "ARI", name: "Arizona Cardinals" },
  { id: "ATL", name: "Atlanta Falcons" },
  { id: "BAL", name: "Baltimore Ravens" },
  { id: "BUF", name: "Buffalo Bills" },
  { id: "CAR", name: "Carolina Panthers" },
  { id: "CHI", name: "Chicago Bears" },
  { id: "CIN", name: "Cincinnati Bengals" },
  { id: "CLE", name: "Cleveland Browns" },
  { id: "DAL", name: "Dallas Cowboys" },
  { id: "DEN", name: "Denver Broncos" },
  { id: "DET", name: "Detroit Lions" },
  { id: "GB", name: "Green Bay Packers" },
  { id: "HOU", name: "Houston Texans" },
  { id: "IND", name: "Indianapolis Colts" },
  { id: "JAX", name: "Jacksonville Jaguars" },
  { id: "KC", name: "Kansas City Chiefs" },
  { id: "LAC", name: "Los Angeles Chargers" },
  { id: "LAR", name: "Los Angeles Rams" },
  { id: "LV", name: "Las Vegas Raiders" },
  { id: "MIA", name: "Miami Dolphins" },
  { id: "MIN", name: "Minnesota Vikings" },
  { id: "NE", name: "New England Patriots" },
  { id: "NO", name: "New Orleans Saints" },
  { id: "NYG", name: "New York Giants" },
  { id: "NYJ", name: "New York Jets" },
  { id: "PHI", name: "Philadelphia Eagles" },
  { id: "PIT", name: "Pittsburgh Steelers" },
  { id: "SEA", name: "Seattle Seahawks" },
  { id: "SF", name: "San Francisco 49ers" },
  { id: "TB", name: "Tampa Bay Buccaneers" },
  { id: "TEN", name: "Tennessee Titans" },
  { id: "WAS", name: "Washington Commanders" },
];

const TEAM_IDS = TEAM_OPTIONS.map((item) => item.id);
const METRIC_CONFIG = [
  {
    key: "win_pct",
    label: "Win %",
    aliases: ["win_pct", "winpct", "win_percentage", "win pct", "win%"],
  },
  {
    key: "point_differential",
    label: "Pt Diff / Game",
    aliases: ["point_differential", "point_diff", "point_diff_per_game", "point diff per game", "point differential"],
  },
  {
    key: "epa_per_play",
    label: "EPA / Play",
    aliases: ["epa_per_play", "offensive_epa_per_play", "epa per play", "offensive epa per play"],
  },
];

let playersCache = null;
let hasTeamParamInQuery = false;
let hasInitializedMoveTeams = false;

const state = {
  teamId: "BUF",
  season: 2026,
};

function toTeamId(value) {
  const normalized = String(value || "")
    .trim()
    .toUpperCase()
    .slice(0, 3);
  return TEAM_IDS.includes(normalized) ? normalized : "";
}

function ensureTeamOptions(selectId) {
  const select = document.getElementById(selectId);
  if (select.options.length > 0) {
    return;
  }

  TEAM_OPTIONS.forEach(({ id, name }) => {
    const option = document.createElement("option");
    option.value = id;
    option.textContent = `${id} — ${name}`;
    select.appendChild(option);
  });
}

function parseQueryState() {
  const params = new URLSearchParams(window.location.search);
  const hasTeam = params.has("team_id");
  hasTeamParamInQuery = hasTeam;
  const hasSeason = params.has("season");
  const teamId = toTeamId(params.get("team_id"));
  const season = Number(params.get("season"));
  if (teamId) {
    state.teamId = teamId;
  }
  if (Number.isFinite(season) && season > 0) {
    state.season = Math.trunc(season);
  }
  return { hasTeam, hasSeason };
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

function syncControls() {
  ensureTeamOptions("teamId");
  ensureTeamOptions("fromTeam");
  ensureTeamOptions("toTeam");

  document.getElementById("teamId").value = state.teamId;
  document.getElementById("season").value = String(state.season);
  const toTeamSelect = document.getElementById("toTeam");
  const fromTeamSelect = document.getElementById("fromTeam");
  if (!hasInitializedMoveTeams) {
    toTeamSelect.value = state.teamId;
    fromTeamSelect.value = hasTeamParamInQuery ? state.teamId : "NYJ";
    hasInitializedMoveTeams = true;
  }
  if (!toTeamId(toTeamSelect.value)) {
    toTeamSelect.value = state.teamId;
  }
  if (!toTeamId(fromTeamSelect.value)) {
    fromTeamSelect.value = hasTeamParamInQuery ? state.teamId : "NYJ";
  }
  updateNavLinks();
}

async function loadPlayersMetadata() {
  if (playersCache) {
    return playersCache;
  }

  try {
    const resp = await fetch(PLAYERS_API_URL);
    if (!resp.ok) {
      playersCache = [];
      return playersCache;
    }
    const data = await resp.json();
    window._playerList = (data.players || []).map((p) => ({
      id: p.player_id,
      name: p.full_name,
      position: p.position,
      team_id: p.team_id,
    }));
    playersCache = window._playerList.map((p) => ({
      playerId: p.id,
      playerName: p.name,
      position: p.position,
      team: p.team_id,
    }));
  } catch (_) {
    // typeahead degrades silently if API unavailable
    playersCache = [];
  }

  return playersCache;
}

function clearTypeaheadList() {
  const listEl = document.getElementById("playerSearchList");
  listEl.innerHTML = "";
  listEl.hidden = true;
}

function renderTypeaheadList(matches) {
  const listEl = document.getElementById("playerSearchList");
  listEl.innerHTML = "";

  if (matches.length === 0) {
    listEl.hidden = true;
    return;
  }

  matches.forEach((match) => {
    const option = document.createElement("li");
    option.className = "typeahead-option";
    option.setAttribute("role", "option");
    option.textContent = `${match.playerName} — ${match.position || "N/A"} — ${match.team || "N/A"}`;
    option.addEventListener("click", () => {
      document.getElementById("playerSearch").value = match.playerName;
      document.getElementById("playerId").value = match.playerId;
      clearTypeaheadList();
    });
    listEl.appendChild(option);
  });

  listEl.hidden = false;
}

function getScenarioIdText() {
  const scenarioEl = document.getElementById("scenarioId");
  return scenarioEl ? String(scenarioEl.textContent || "").trim() : "";
}

function generateScenarioId() {
  const teamId = toTeamId(document.getElementById("teamId").value) || state.teamId || "UNK";
  const seasonRaw = Number(document.getElementById("season").value);
  const season = Number.isFinite(seasonRaw) && seasonRaw > 0 ? Math.trunc(seasonRaw) : state.season;
  const generated = `${teamId}-${season}-${Date.now()}`;
  document.getElementById("scenarioId").textContent = generated;
  return generated;
}

function updateNavLinks() {
  const params = new URLSearchParams({
    team_id: state.teamId,
    season: String(state.season),
  });
  const query = params.toString();
  document.getElementById("overviewLink").href = `./index.html?${query}`;
  document.getElementById("teamLink").href = `./team.html?${query}`;
}

function writeQueryState() {
  const params = new URLSearchParams({
    team_id: state.teamId,
    season: String(state.season),
  });
  window.history.replaceState({}, "", `?${params.toString()}`);
}

function syncStateFromControls() {
  const teamId = toTeamId(document.getElementById("teamId").value);
  const season = Number(document.getElementById("season").value);
  if (teamId) {
    state.teamId = teamId;
  }
  if (Number.isFinite(season) && season > 0) {
    state.season = Math.trunc(season);
  }
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

function showScenarioSkeletons() {
  document.getElementById("deltaSummary").innerHTML = `<div class="skeleton-list">${skeletonRows(2, ["100%", "100%"], 20)}</div>`;
  document.getElementById("baseline").innerHTML = `<div class="skeleton-list">${skeletonRows(2, ["100%", "100%"], 20)}</div>`;
  document.getElementById("scenario").innerHTML = `<div class="skeleton-list">${skeletonRows(2, ["100%", "100%"], 20)}</div>`;
  document.getElementById("comparisonChartPanel").style.display = "block";
  document.getElementById("comparisonChart").innerHTML = `<div class="skeleton skeleton-chart" style="height:180px;width:100%;"></div>`;
  document.getElementById("comparisonChartTooltip").hidden = true;
}

function showScenarioErrorStates() {
  renderErrorState(document.getElementById("deltaSummary"));
  renderErrorState(document.getElementById("baseline"));
  renderErrorState(document.getElementById("scenario"));
  document.getElementById("comparisonChartPanel").style.display = "block";
  renderErrorState(document.getElementById("comparisonChart"));
  document.getElementById("comparisonChartTooltip").hidden = true;
}

function isScenarioPayload(payload) {
  return Boolean(
    payload &&
      payload.delta_summary &&
      payload.baseline_estimates &&
      payload.scenario_estimates
  );
}

function resetRenderedData() {
  document.getElementById("deltaSummary").innerHTML = "";
  document.getElementById("baseline").innerHTML = "";
  document.getElementById("scenario").innerHTML = "";
  document.getElementById("comparisonChart").innerHTML = "";
  document.getElementById("comparisonChartPanel").style.display = "none";
  document.getElementById("comparisonChartTooltip").hidden = true;
}

function payloadFromInputs() {
  return {
    team_id: document.getElementById("teamId").value,
    season: Number(document.getElementById("season").value),
    scenario_id: getScenarioIdText(),
    applied_moves: [
      {
        move_id: "ui_custom_001",
        player_id: document.getElementById("playerId").value.trim(),
        from_team_id: document.getElementById("fromTeam").value,
        to_team_id: document.getElementById("toTeam").value,
        move_type: document.getElementById("moveType").value,
        action: document.getElementById("action").value,
      },
    ],
  };
}

async function fetchScenario(payload) {
  try {
    const resp = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      let detail = `status ${resp.status}`;
      try {
        const errorPayload = await resp.json();
        if (errorPayload && errorPayload.error) {
          detail = String(errorPayload.error);
        }
      } catch (_err) {
        // Ignore JSON parse errors and keep HTTP status detail.
      }
      throw new Error(`Live API request failed: ${detail}`);
    }

    const livePayload = await resp.json();
    if (isScenarioPayload(livePayload)) {
      return livePayload;
    }
    if (livePayload && livePayload.error) {
      throw new Error(`Live API error: ${livePayload.error}`);
    }
    throw new Error("Live API returned an invalid scenario payload format.");
  } catch (err) {
    const detail = err instanceof Error ? err.message : "request failed";
    throw new Error(`Data collection failed. Please check source data coverage and pipeline outputs. ${detail}`);
  }
}

function renderEstimates(containerId, rows) {
  const container = document.getElementById(containerId);
  const template = document.getElementById("estimateTemplate");
  container.innerHTML = "";

  if (!Array.isArray(rows) || rows.length === 0) {
    renderEmptyState(container, teamSeasonEmptyMessage());
    return;
  }

  rows.forEach((row) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector(".estimate-outcome").textContent = row.outcome_name;
    node.querySelector(".estimate-mis").textContent = `${fmt(row.mis_value)} (z ${fmt(row.mis_z)})`;
    node.querySelector(".estimate-int").textContent = `Median ${fmt(row.median)} | 50% [${fmt(row.interval_50.low)}, ${fmt(row.interval_50.high)}] | 90% [${fmt(row.interval_90.low)}, ${fmt(row.interval_90.high)}] | ${row.low_confidence_flag ? "Low confidence" : "High confidence"}`;
    container.appendChild(node);
  });
}

function renderDeltas(rows) {
  const container = document.getElementById("deltaSummary");
  const template = document.getElementById("deltaTemplate");
  container.innerHTML = "";

  if (!Array.isArray(rows) || rows.length === 0) {
    renderEmptyState(container, teamSeasonEmptyMessage());
    return;
  }

  rows.forEach((row) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector(".delta-outcome").textContent = row.outcome_name;
    const valueEl = node.querySelector(".delta-value");
    valueEl.textContent = fmt(row.mis_delta);
    valueEl.classList.add(row.direction);
    node.querySelector(".delta-range").textContent = `90% delta [${fmt(row.interval_90_delta.low)}, ${fmt(row.interval_90_delta.high)}]`;
    container.appendChild(node);
  });
}

function normalizeOutcomeName(name) {
  return String(name || "")
    .trim()
    .toLowerCase()
    .replace(/[%/]/g, "")
    .replace(/[_\-]+/g, " ")
    .replace(/\s+/g, " ");
}

function getMetricRow(rows, aliases) {
  const aliasSet = new Set(aliases.map((alias) => normalizeOutcomeName(alias)));
  return rows.find((row) => aliasSet.has(normalizeOutcomeName(row.outcome_name))) || null;
}

function getMetricValue(row) {
  if (!row) {
    return 0;
  }
  const median = Number(row.median);
  if (Number.isFinite(median)) {
    return median;
  }
  const misValue = Number(row.mis_value);
  return Number.isFinite(misValue) ? misValue : 0;
}

function getMetricInterval(row) {
  if (!row) {
    return null;
  }
  const preferred = [row.interval_90, row.interval_50];
  for (const interval of preferred) {
    if (!interval) {
      continue;
    }
    const low = Number(interval.low);
    const high = Number(interval.high);
    if (Number.isFinite(low) && Number.isFinite(high)) {
      return { low, high };
    }
  }
  return null;
}

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function makeSvgNode(tag, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => {
    node.setAttribute(key, String(value));
  });
  return node;
}

function renderComparisonChart(baselineRows, scenarioRows) {
  const panel = document.getElementById("comparisonChartPanel");
  const chartRoot = document.getElementById("comparisonChart");
  const tooltip = document.getElementById("comparisonChartTooltip");
  chartRoot.innerHTML = "";
  tooltip.hidden = true;

  if (!Array.isArray(baselineRows) || !Array.isArray(scenarioRows) || baselineRows.length === 0 || scenarioRows.length === 0) {
    panel.style.display = "block";
    renderEmptyState(chartRoot, teamSeasonEmptyMessage());
    return;
  }

  const metrics = METRIC_CONFIG.map((metric) => {
    const baselineRow = getMetricRow(baselineRows, metric.aliases);
    const scenarioRow = getMetricRow(scenarioRows, metric.aliases);
    const baselineValue = getMetricValue(baselineRow);
    const scenarioValue = getMetricValue(scenarioRow);
    const baselineInterval = getMetricInterval(baselineRow);
    const scenarioInterval = getMetricInterval(scenarioRow);
    const hasIntervals = Boolean(baselineInterval && scenarioInterval);

    return {
      ...metric,
      baselineValue,
      scenarioValue,
      baselineInterval: hasIntervals ? baselineInterval : null,
      scenarioInterval: hasIntervals ? scenarioInterval : null,
    };
  });

  const dataValues = [0];
  metrics.forEach((metric) => {
    dataValues.push(metric.baselineValue, metric.scenarioValue);
    if (metric.baselineInterval) {
      dataValues.push(metric.baselineInterval.low, metric.baselineInterval.high);
    }
    if (metric.scenarioInterval) {
      dataValues.push(metric.scenarioInterval.low, metric.scenarioInterval.high);
    }
  });

  let minValue = Math.min(...dataValues);
  let maxValue = Math.max(...dataValues);
  if (minValue === maxValue) {
    const expand = Math.max(Math.abs(minValue) * 0.25, 1);
    minValue -= expand;
    maxValue += expand;
  }
  const padding = (maxValue - minValue) * 0.1;
  minValue -= padding;
  maxValue += padding;

  const width = 900;
  const height = 360;
  const margin = { top: 14, right: 28, bottom: 72, left: 56 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const zeroY = margin.top + ((maxValue - 0) / (maxValue - minValue)) * plotHeight;

  const yFor = (value) => margin.top + ((maxValue - value) / (maxValue - minValue)) * plotHeight;

  const svg = makeSvgNode("svg", {
    viewBox: `0 0 ${width} ${height}`,
    width: "100%",
    height: "auto",
    role: "img",
    "aria-label": "Grouped bar chart comparing baseline and scenario outcomes",
  });

  const baselineColor = cssVar("--neu", "#2a6798");
  const positiveColor = cssVar("--pos", "#0f8f5f");
  const negativeColor = cssVar("--neg", "#c5532f");
  const mutedColor = cssVar("--muted", "#536274");
  const lineColor = cssVar("--line", "rgba(17, 36, 58, 0.15)");
  const inkColor = cssVar("--ink", "#1b2430");

  const yTicks = 4;
  for (let i = 0; i <= yTicks; i += 1) {
    const tickValue = minValue + ((maxValue - minValue) * i) / yTicks;
    const y = yFor(tickValue);
    const gridLine = makeSvgNode("line", {
      x1: margin.left,
      x2: width - margin.right,
      y1: y,
      y2: y,
      stroke: lineColor,
      "stroke-width": 1,
    });
    svg.appendChild(gridLine);

    const tickLabel = makeSvgNode("text", {
      x: margin.left - 8,
      y: y + 4,
      "text-anchor": "end",
      fill: mutedColor,
      "font-size": 11,
      "font-family": "IBM Plex Mono, monospace",
    });
    tickLabel.textContent = fmt(tickValue);
    svg.appendChild(tickLabel);
  }

  const zeroLine = makeSvgNode("line", {
    x1: margin.left,
    x2: width - margin.right,
    y1: zeroY,
    y2: zeroY,
    stroke: inkColor,
    "stroke-width": 1.4,
  });
  svg.appendChild(zeroLine);

  const groupWidth = plotWidth / metrics.length;
  const barWidth = Math.min(34, groupWidth * 0.25);
  const gap = Math.min(14, groupWidth * 0.12);

  const showTooltip = (event, textLines) => {
    const rect = chartRoot.getBoundingClientRect();
    tooltip.innerHTML = textLines.join("<br />");
    tooltip.hidden = false;
    const left = event.clientX - rect.left + 10;
    const top = event.clientY - rect.top + 10;
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  };

  const hideTooltip = () => {
    tooltip.hidden = true;
  };

  metrics.forEach((metric, index) => {
    const groupCenter = margin.left + groupWidth * index + groupWidth / 2;
    const baselineX = groupCenter - barWidth - gap / 2;
    const scenarioX = groupCenter + gap / 2;

    const baselineY = yFor(metric.baselineValue);
    const scenarioY = yFor(metric.scenarioValue);
    const baselineHeight = Math.max(1, Math.abs(zeroY - baselineY));
    const scenarioHeight = Math.max(1, Math.abs(zeroY - scenarioY));

    const baselineBar = makeSvgNode("rect", {
      x: baselineX,
      y: Math.min(baselineY, zeroY),
      width: barWidth,
      height: baselineHeight,
      fill: baselineColor,
      rx: 2,
      ry: 2,
      cursor: "default",
    });

    const scenarioFill = metric.scenarioValue > metric.baselineValue
      ? positiveColor
      : metric.scenarioValue < metric.baselineValue
        ? negativeColor
        : baselineColor;

    const scenarioBar = makeSvgNode("rect", {
      x: scenarioX,
      y: Math.min(scenarioY, zeroY),
      width: barWidth,
      height: scenarioHeight,
      fill: scenarioFill,
      rx: 2,
      ry: 2,
      cursor: "default",
    });

    const baselineTooltipLines = [
      `${metric.label} (Baseline): ${fmt(metric.baselineValue)}`,
    ];
    if (metric.baselineInterval) {
      baselineTooltipLines.push(`Interval: [${fmt(metric.baselineInterval.low)}, ${fmt(metric.baselineInterval.high)}]`);
    }

    const scenarioTooltipLines = [
      `${metric.label} (Scenario): ${fmt(metric.scenarioValue)}`,
    ];
    if (metric.scenarioInterval) {
      scenarioTooltipLines.push(`Interval: [${fmt(metric.scenarioInterval.low)}, ${fmt(metric.scenarioInterval.high)}]`);
    }

    [
      [baselineBar, baselineTooltipLines],
      [scenarioBar, scenarioTooltipLines],
    ].forEach(([bar, lines]) => {
      bar.addEventListener("mouseenter", (event) => showTooltip(event, lines));
      bar.addEventListener("mousemove", (event) => showTooltip(event, lines));
      bar.addEventListener("mouseleave", hideTooltip);
      svg.appendChild(bar);
    });

    if (metric.baselineInterval && metric.scenarioInterval) {
      const drawErrorBar = (xCenter, interval) => {
        const top = yFor(interval.high);
        const bottom = yFor(interval.low);
        const line = makeSvgNode("line", {
          x1: xCenter,
          x2: xCenter,
          y1: top,
          y2: bottom,
          stroke: inkColor,
          "stroke-width": 1,
        });
        const capTop = makeSvgNode("line", {
          x1: xCenter - 4,
          x2: xCenter + 4,
          y1: top,
          y2: top,
          stroke: inkColor,
          "stroke-width": 1,
        });
        const capBottom = makeSvgNode("line", {
          x1: xCenter - 4,
          x2: xCenter + 4,
          y1: bottom,
          y2: bottom,
          stroke: inkColor,
          "stroke-width": 1,
        });
        svg.appendChild(line);
        svg.appendChild(capTop);
        svg.appendChild(capBottom);
      };

      drawErrorBar(baselineX + barWidth / 2, metric.baselineInterval);
      drawErrorBar(scenarioX + barWidth / 2, metric.scenarioInterval);
    }

    const label = makeSvgNode("text", {
      x: groupCenter,
      y: height - margin.bottom + 22,
      "text-anchor": "middle",
      fill: mutedColor,
      "font-size": 11,
      "font-family": "IBM Plex Mono, monospace",
    });
    label.textContent = metric.label;
    svg.appendChild(label);
  });

  chartRoot.appendChild(svg);
  panel.style.display = "block";
}

async function runScenario() {
  syncStateFromControls();
  syncControls();
  writeQueryState();

  const payload = payloadFromInputs();
  showScenarioSkeletons();
  setStatus("Running scenario...");
  try {
    const data = await fetchScenario(payload);
    renderDeltas(data.delta_summary);
    renderEstimates("baseline", data.baseline_estimates);
    renderEstimates("scenario", data.scenario_estimates);
    renderComparisonChart(data.baseline_estimates, data.scenario_estimates);
    setStatus("");
  } catch (err) {
    resetRenderedData();
    showScenarioErrorStates();
    const message = err instanceof Error
      ? err.message
      : "Data collection failed. Please check source data coverage and pipeline outputs.";
    setStatus(message, true);
  }
}

function bindControls() {
  const runAction = () => {
    generateScenarioId();
    runScenario().catch((err) => console.error(err));
  };

  document.getElementById("runBtn").addEventListener("click", () => {
    runAction();
  });

  ["teamId", "season"].forEach((id) => {
    document.getElementById(id).addEventListener("change", () => {
      syncStateFromControls();
      syncControls();
      writeQueryState();
    });
  });

  ["teamId", "season", "playerSearch", "fromTeam", "toTeam", "moveType", "action"].forEach((id) => {
    document.getElementById(id).addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        runAction();
      }
    });
  });

  let typeaheadTimer = null;
  document.getElementById("playerSearch").addEventListener("input", (event) => {
    const query = String(event.target.value || "").trim().toLowerCase();
    document.getElementById("playerId").value = "";

    if (typeaheadTimer) {
      window.clearTimeout(typeaheadTimer);
    }

    typeaheadTimer = window.setTimeout(async () => {
      if (!query) {
        clearTypeaheadList();
        return;
      }
      try {
        const rows = await loadPlayersMetadata();
        const matches = rows
          .filter((row) => row.playerName.toLowerCase().includes(query))
          .slice(0, 10);
        renderTypeaheadList(matches);
      } catch (err) {
        clearTypeaheadList();
        console.error(err);
      }
    }, 200);
  });

  document.addEventListener("click", (event) => {
    const wrap = document.querySelector(".typeahead-wrap");
    if (wrap && !wrap.contains(event.target)) {
      clearTypeaheadList();
    }
  });
}

function main() {
  rewriteNavLinksFromParams();
  parseQueryState();
  syncControls();
  bindControls();
}

document.addEventListener("DOMContentLoaded", () => {
  main();
});
