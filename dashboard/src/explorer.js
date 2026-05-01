const API_BASE = (window.NFL_API_BASE || "https://nflanalysis.onrender.com").replace(/\/$/, "");

const TEAM_IDS = [
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
  "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
];

const POSITION_GROUPS = [
  "offense_skill",
  "offense_line",
  "defense_front",
  "defense_second_level",
  "defense_secondary",
  "special_teams",
  "other",
];

const SEASON_OPTIONS = [2022, 2023, 2024, 2025, 2026];

const state = {
  season: 2026,
  teamFilter: "",
  positionFilter: "",
  moveTypeFilter: "",
  directionFilter: "",
  misBandFilter: "",
  sortOrder: "abs_desc",
};

let allEvents = [];
let failedTeamCount = 0;

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
    state.teamFilter = teamId;
  }
  return { hasSeason, hasTeamId };
}

function writeQueryState() {
  const params = new URLSearchParams({
    season: String(state.season),
    team_id: state.teamFilter,
  });
  window.history.replaceState({}, "", `?${params.toString()}`);
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
  ensureControlOptions();
  document.getElementById("seasonInput").value = String(state.season);
  document.getElementById("teamFilter").value = state.teamFilter;
  document.getElementById("positionFilter").value = state.positionFilter;
  document.getElementById("moveTypeFilter").value = state.moveTypeFilter;
  document.getElementById("directionFilter").value = state.directionFilter;
  document.getElementById("misBandFilter").value = state.misBandFilter;
  document.getElementById("sortInput").value = state.sortOrder;

  const params = new URLSearchParams({
    season: String(state.season),
    team_id: state.teamFilter,
  });
  document.getElementById("overviewLink").href = `./index.html?${params.toString()}`;
  document.getElementById("teamLink").href = `./team.html?${params.toString()}`;
  document.getElementById("scenarioLink").href = `./scenario.html?${params.toString()}`;
  document.getElementById("explorerLink").href = `./explorer.html?${params.toString()}`;
}

function updateResultsCount(filtered, total) {
  document.getElementById("resultsCount").textContent = `Showing ${filtered} of ${total} movement events`;
}

function applyFilters(events) {
  const filtered = (events || []).filter((event) => {
    const fromTeam = String(event.from_team_id || "").trim().toUpperCase();
    const toTeam = String(event.to_team_id || "").trim().toUpperCase();

    if (state.teamFilter && fromTeam !== state.teamFilter && toTeam !== state.teamFilter) {
      return false;
    }

    const rawPosition = String(event.position || event.position_group || "other").trim().toLowerCase() || "other";
    const normalizedPosition = POSITION_GROUPS.includes(rawPosition) ? rawPosition : "other";
    if (state.positionFilter && normalizedPosition !== state.positionFilter) {
      return false;
    }

    const moveType = String(event.move_type || "").trim().toLowerCase();
    if (state.moveTypeFilter && moveType !== state.moveTypeFilter) {
      return false;
    }

    if (state.directionFilter) {
      if (state.teamFilter) {
        const isInbound = toTeam === state.teamFilter;
        const isOutbound = fromTeam === state.teamFilter;
        if (state.directionFilter === "inbound" && !isInbound) {
          return false;
        }
        if (state.directionFilter === "outbound" && !isOutbound) {
          return false;
        }
      } else {
        const isInbound = toTeam !== "";
        const isOutbound = fromTeam !== "";
        if (state.directionFilter === "inbound" && !isInbound) {
          return false;
        }
        if (state.directionFilter === "outbound" && !isOutbound) {
          return false;
        }
      }
    }

    if (state.misBandFilter) {
      const metric = Number(event.mis_z ?? event.impact_estimate ?? 0);
      const value = Number.isFinite(metric) ? metric : 0;

      if (state.misBandFilter === "high_pos" && !(value >= 1.0)) {
        return false;
      }
      if (state.misBandFilter === "mod_pos" && !(value >= 0.3 && value < 1.0)) {
        return false;
      }
      if (state.misBandFilter === "neutral" && !(value >= -0.3 && value <= 0.3)) {
        return false;
      }
      if (state.misBandFilter === "mod_neg" && !(value > -1.0 && value < -0.3)) {
        return false;
      }
      if (state.misBandFilter === "high_neg" && !(value <= -1.0)) {
        return false;
      }
    }

    return true;
  });

  const sorted = [...filtered].sort((a, b) => {
    if (state.sortOrder === "abs_desc") {
      return Math.abs(Number(b.impact_estimate) || 0) - Math.abs(Number(a.impact_estimate) || 0);
    }
    if (state.sortOrder === "abs_asc") {
      return Math.abs(Number(a.impact_estimate) || 0) - Math.abs(Number(b.impact_estimate) || 0);
    }
    const aDate = Date.parse(String(a.event_date || ""));
    const bDate = Date.parse(String(b.event_date || ""));
    const safeA = Number.isFinite(aDate) ? aDate : 0;
    const safeB = Number.isFinite(bDate) ? bDate : 0;
    if (state.sortOrder === "date_desc") {
      return safeB - safeA;
    }
    return safeA - safeB;
  });

  return sorted;
}

function renderExplorer() {
  const container = document.getElementById("explorerResults");
  const filtered = applyFilters(allEvents);
  updateResultsCount(filtered.length, allEvents.length);

  container.innerHTML = "";
  if (filtered.length === 0) {
    renderEmptyState(container, teamSeasonEmptyMessage());
  } else {
    const cardsRoot = document.createElement("div");
    cardsRoot.className = "movement-cards";

    filtered.forEach((event) => {
      const perspectiveTeam = state.teamFilter
        || String(pickField(event, ["team_id", "to_team_id", "from_team_id"], "")).trim().toUpperCase()
        || "BUF";
      const temp = document.createElement("div");
      renderMovementCards([event], perspectiveTeam, state.season, temp);
      const card = temp.querySelector(".movement-card");
      if (card) {
        cardsRoot.appendChild(card);
      }
    });

    if (cardsRoot.children.length > 0) {
      container.appendChild(cardsRoot);
    } else {
      renderEmptyState(container, teamSeasonEmptyMessage());
    }
  }

  const partial = document.getElementById("partialLoadNotice");
  if (failedTeamCount > 0) {
    partial.textContent = `${failedTeamCount} team(s) failed to load and are excluded from results.`;
  } else {
    partial.textContent = "";
  }
}

function renderMovementCards(events, teamId, season, containerEl = null) {
  const container = containerEl || document.getElementById("timeline");
  container.innerHTML = "";

  const normalizedEvents = (events || []).map((event) => {
    const toTeam = String(pickField(event, ["to_team_id", "to_team"], "")).trim().toUpperCase();
    const fromTeam = String(pickField(event, ["from_team_id", "from_team"], "")).trim().toUpperCase();
    const direction = toTeam === teamId ? "inbound" : "outbound";
    const pointEstimate = toFiniteNumber(pickField(event, ["impact_estimate", "mis_value"], 0)) || 0;
    const misZ = toFiniteNumber(pickField(event, ["mis_z"], pointEstimate));
    const interval = intervalForEvent(event);
    const outcomeName = String(pickField(event, ["outcome_name"], "win_pct")).trim() || "win_pct";

    return {
      original: event,
      direction,
      pointEstimate,
      misZ: misZ === null ? pointEstimate : misZ,
      interval,
      outcomeName,
      playerId: String(pickField(event, ["player_id"], "")).trim(),
      playerName: String(pickField(event, ["player_name", "player_display_name", "player_id"], "Unknown Player")).trim(),
      position: String(pickField(event, ["position", "position_group"], "")).trim().toUpperCase(),
      fromTeam,
      toTeam,
      moveType: String(pickField(event, ["move_type"], "")).trim(),
      week: toFiniteNumber(pickField(event, ["nfl_week", "week"], "")),
      eventDate: String(pickField(event, ["event_date", "effective_date", "date"], "")).trim(),
      lowConfidence: String(pickField(event, ["low_confidence_flag", "low_confidence"], "false")).toLowerCase() === "true",
    };
  });

  if (normalizedEvents.length === 0) {
    renderEmptyState(container, teamSeasonEmptyMessage());
    return;
  }

  normalizedEvents.sort((a, b) => {
    const impactDiff = Math.abs(b.pointEstimate) - Math.abs(a.pointEstimate);
    if (impactDiff !== 0) {
      return impactDiff;
    }
    if (a.direction !== b.direction) {
      return a.direction === "inbound" ? -1 : 1;
    }
    return 0;
  });

  const scalesByOutcome = {};
  normalizedEvents.forEach((item) => {
    if (!item.interval) {
      return;
    }
    const key = item.outcomeName;
    if (!scalesByOutcome[key]) {
      scalesByOutcome[key] = {
        min: Math.min(item.interval.low, item.pointEstimate),
        max: Math.max(item.interval.high, item.pointEstimate),
      };
      return;
    }
    scalesByOutcome[key].min = Math.min(scalesByOutcome[key].min, item.interval.low, item.pointEstimate);
    scalesByOutcome[key].max = Math.max(scalesByOutcome[key].max, item.interval.high, item.pointEstimate);
  });

  const cardsRoot = document.createElement("div");
  cardsRoot.className = "movement-cards";

  normalizedEvents.forEach((item) => {
    const directionLabel = item.direction === "inbound" ? "▼ INBOUND" : "▲ OUTBOUND";
    const directionClass = item.direction;
    const moveTypeLabel = item.moveType === "free_agency"
      ? "FREE AGENCY"
      : item.moveType === "trade"
        ? "TRADE"
        : item.moveType.replace(/_/g, " ").toUpperCase();
    const teamBoldFrom = item.fromTeam === teamId ? `<strong>${item.fromTeam}</strong>` : item.fromTeam;
    const teamBoldTo = item.toTeam === teamId ? `<strong>${item.toTeam}</strong>` : item.toTeam;
    const whenText = item.week && item.week > 0
      ? `Wk ${Math.trunc(item.week)}`
      : item.eventDate || "Date unavailable";

    const params = new URLSearchParams({
      team_id: teamId,
      season: String(season),
      player_id: item.playerId,
      from_team: item.fromTeam,
      to_team: item.toTeam,
    });
    const whatIfHref = `./scenario.html?${params.toString()}`;

    let intervalHtml = "";
    if (item.interval) {
      const scale = scalesByOutcome[item.outcomeName] || {
        min: Math.min(item.interval.low, item.pointEstimate),
        max: Math.max(item.interval.high, item.pointEstimate),
      };
      intervalHtml = `
        <div class="movement-interval">
          <div class="movement-row">
            <span class="movement-interval-label">${item.interval.label}</span>
          </div>
          ${renderIntervalSvg(item.pointEstimate, item.interval, scale.min, scale.max)}
          <div class="movement-interval-text">[${fmt(item.interval.low)}, ${fmt(item.interval.high)}]</div>
        </div>
      `;
    }

    const lowConfidenceHtml = item.lowConfidence
      ? '<div class="movement-low-confidence">LOW CONFIDENCE</div>'
      : "";

    const positionHtml = item.position ? `<span class="movement-position">${item.position}</span>` : "";

    const card = document.createElement("article");
    card.className = `movement-card ${directionClass}`;
    card.innerHTML = `
      <div class="movement-row">
        <span class="movement-direction ${directionClass}">${directionLabel}</span>
        <span class="movement-badge">${moveTypeLabel || "MOVE"}</span>
      </div>
      <div class="movement-player">
        <span class="movement-player-name">${item.playerName}</span>${positionHtml}
      </div>
      <div class="movement-route">${teamBoldFrom} &rarr; ${teamBoldTo}</div>
      <div class="movement-when">${whenText}</div>
      <div class="movement-mis-row">
        <span class="movement-mis-label">MIS (win%)</span>
        <span class="movement-mis-value ${misBandClass(item.misZ)}">${fmtSigned(item.pointEstimate)}</span>
      </div>
      ${intervalHtml}
      ${lowConfidenceHtml}
      <div class="movement-footer"><a href="${whatIfHref}">Run What-If &rarr;</a></div>
    `;
    cardsRoot.appendChild(card);
  });

  container.appendChild(cardsRoot);
}

function renderEmptyState(container, message) {
  container.innerHTML = `<div class="empty-state">${message}</div>`;
}

function renderErrorState(container) {
  container.innerHTML = '<div class="empty-state error-state">Failed to load data. Refresh the page or try again.</div>';
}

function skeletonRows(count, widths, height = 20, rowClass = "") {
  return Array.from({ length: count }, (_, index) => {
    const width = widths[index] || widths[widths.length - 1] || "100%";
    const className = rowClass ? `skeleton-row ${rowClass}` : "skeleton-row";
    return `<div class="${className} skeleton" style="height:${height}px;width:${width};"></div>`;
  }).join("");
}

function misBandClass(misZOrProxy) {
  if (misZOrProxy >= 1.0) {
    return "band-positive-strong";
  }
  if (misZOrProxy >= 0.3) {
    return "band-positive-light";
  }
  if (misZOrProxy > -0.3) {
    return "band-neutral";
  }
  if (misZOrProxy > -1.0) {
    return "band-negative-light";
  }
  return "band-negative-strong";
}

function fmtSigned(num) {
  const value = Number(num);
  if (!Number.isFinite(value)) {
    return "+0.000";
  }
  const decimals = Math.abs(value) > 0 && Math.abs(value) < 0.001 ? 6 : 3;
  const fixed = value.toFixed(decimals);
  return value >= 0 ? `+${fixed}` : fixed;
}

function fmt(num) {
  const value = Number(num);
  if (!Number.isFinite(value)) {
    return "0.000";
  }
  const decimals = Math.abs(value) > 0 && Math.abs(value) < 0.001 ? 6 : 3;
  return value.toFixed(decimals);
}

function pickField(row, keys, fallback = "") {
  for (const key of keys) {
    if (!(key in row)) {
      continue;
    }
    const value = row[key];
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      return value;
    }
  }
  return fallback;
}

function toFiniteNumber(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function intervalForEvent(event) {
  const i90Low = toFiniteNumber(pickField(event, ["interval_90_low"]));
  const i90High = toFiniteNumber(pickField(event, ["interval_90_high"]));
  if (i90Low !== null && i90High !== null) {
    return {
      label: "90% interval",
      low: i90Low,
      high: i90High,
    };
  }

  const nested90 = event.interval_90;
  if (nested90 && typeof nested90 === "object") {
    const nestedLow = toFiniteNumber(nested90.low);
    const nestedHigh = toFiniteNumber(nested90.high);
    if (nestedLow !== null && nestedHigh !== null) {
      return {
        label: "90% interval",
        low: nestedLow,
        high: nestedHigh,
      };
    }
  }

  const i50Low = toFiniteNumber(pickField(event, ["interval_50_low"]));
  const i50High = toFiniteNumber(pickField(event, ["interval_50_high"]));
  if (i50Low !== null && i50High !== null) {
    return {
      label: "50% interval",
      low: i50Low,
      high: i50High,
    };
  }

  const nested50 = event.interval_50;
  if (nested50 && typeof nested50 === "object") {
    const nestedLow = toFiniteNumber(nested50.low);
    const nestedHigh = toFiniteNumber(nested50.high);
    if (nestedLow !== null && nestedHigh !== null) {
      return {
        label: "50% interval",
        low: nestedLow,
        high: nestedHigh,
      };
    }
  }

  return null;
}

function renderIntervalSvg(point, interval, min, max) {
  const width = 160;
  const toX = (value) => {
    if (max <= min) {
      return width / 2;
    }
    const ratio = (value - min) / (max - min);
    return Math.max(0, Math.min(width, ratio * width));
  };

  const leftX = toX(interval.low);
  const rightX = toX(interval.high);
  const pointX = toX(point);

  return `
    <svg class="movement-interval-svg" viewBox="0 0 160 16" aria-hidden="true" focusable="false">
      <line x1="0" y1="8" x2="160" y2="8" stroke="#334155" stroke-width="2" />
      <line x1="${leftX}" y1="8" x2="${rightX}" y2="8" stroke="#38bdf8" stroke-width="3" />
      <line x1="${leftX}" y1="4" x2="${leftX}" y2="12" stroke="#7dd3fc" stroke-width="2" />
      <line x1="${rightX}" y1="4" x2="${rightX}" y2="12" stroke="#7dd3fc" stroke-width="2" />
      <circle cx="${pointX}" cy="8" r="3" fill="#f8fafc" />
    </svg>
  `;
}

function showExplorerSkeleton() {
  document.getElementById("explorerResults").innerHTML = `
    <div class="skeleton-list timeline-skeleton-list">
      ${skeletonRows(3, ["100%", "100%", "100%"], 80, "timeline-skeleton-card")}
    </div>
  `;
}

async function loadAllTeams(season) {
  failedTeamCount = 0;
  const progressEl = document.getElementById("loadProgress");
  let settledCount = 0;
  progressEl.textContent = `Loading... (${settledCount} of ${TEAM_IDS.length} teams)`;

  const requests = TEAM_IDS.map((teamId) => {
    const params = new URLSearchParams({
      team_id: teamId,
      season: String(season),
    });
    const url = `${API_BASE}/v1/dashboard/team-detail?${params.toString()}`;

    return fetch(url)
      .then(async (resp) => {
        if (!resp.ok) {
          throw new Error(`status ${resp.status}`);
        }
        const payload = await resp.json();
        const timeline = Array.isArray(payload?.timeline) ? payload.timeline : null;
        if (!timeline) {
          throw new Error("invalid payload");
        }
        return timeline.map((event) => ({
          ...event,
          team_id: teamId,
        }));
      })
      .finally(() => {
        settledCount += 1;
        progressEl.textContent = `Loading... (${settledCount} of ${TEAM_IDS.length} teams)`;
      });
  });

  const results = await Promise.allSettled(requests);
  const rejected = results.filter((result) => result.status === "rejected");
  failedTeamCount = rejected.length;

  if (rejected.length === TEAM_IDS.length) {
    throw new Error("Failed to load movement events for all teams.");
  }

  const merged = [];
  results.forEach((result) => {
    if (result.status === "fulfilled") {
      merged.push(...result.value);
    }
  });

  const deduped = [];
  const seenMoveIds = new Set();
  merged.forEach((event, index) => {
    const moveId = String(event.move_id || "").trim();
    if (!moveId) {
      deduped.push({ ...event, __explorer_index: index });
      return;
    }
    if (seenMoveIds.has(moveId)) {
      return;
    }
    seenMoveIds.add(moveId);
    deduped.push(event);
  });

  return deduped;
}

async function refreshExplorer() {
  const seasonValue = Number(document.getElementById("seasonInput").value);
  if (Number.isFinite(seasonValue) && seasonValue > 0) {
    state.season = Math.trunc(seasonValue);
  }
  syncControls();
  writeQueryState();
  showExplorerSkeleton();
  setStatus(`Loading movement events for ${state.season}...`);

  try {
    allEvents = await loadAllTeams(state.season);
    renderExplorer();
    setStatus("");
  } catch (err) {
    allEvents = [];
    updateResultsCount(0, 0);
    const container = document.getElementById("explorerResults");
    renderErrorState(container);
    document.getElementById("partialLoadNotice").textContent = "";
    const message = err instanceof Error
      ? err.message
      : "Data collection failed. Please check source data coverage and pipeline outputs.";
    setStatus(message, true);
  } finally {
    document.getElementById("loadProgress").textContent = "";
  }
}

function bindControls() {
  document.getElementById("seasonInput").addEventListener("change", () => {
    refreshExplorer().catch((err) => console.error(err));
  });

  document.getElementById("teamFilter").addEventListener("change", (event) => {
    state.teamFilter = toTeamId(event.target.value);
    syncControls();
    writeQueryState();
    renderExplorer();
  });

  document.getElementById("positionFilter").addEventListener("change", (event) => {
    state.positionFilter = String(event.target.value || "");
    renderExplorer();
  });

  document.getElementById("moveTypeFilter").addEventListener("change", (event) => {
    state.moveTypeFilter = String(event.target.value || "");
    renderExplorer();
  });

  document.getElementById("directionFilter").addEventListener("change", (event) => {
    state.directionFilter = String(event.target.value || "");
    renderExplorer();
  });

  document.getElementById("misBandFilter").addEventListener("change", (event) => {
    state.misBandFilter = String(event.target.value || "");
    renderExplorer();
  });

  document.getElementById("sortInput").addEventListener("change", (event) => {
    state.sortOrder = String(event.target.value || "abs_desc");
    renderExplorer();
  });
}

function main() {
  rewriteNavLinksFromParams();
  parseQueryState();
  syncControls();
  bindControls();
  refreshExplorer().catch((err) => console.error(err));
}

document.addEventListener("DOMContentLoaded", () => {
  main();
});

function toTeamId(value) {
  const normalized = String(value || "")
    .trim()
    .toUpperCase()
    .slice(0, 3);
  return TEAM_IDS.includes(normalized) ? normalized : "";
}

function ensureControlOptions() {
  const seasonSelect = document.getElementById("seasonInput");
  if (seasonSelect.options.length === 0) {
    SEASON_OPTIONS.forEach((season) => {
      const option = document.createElement("option");
      option.value = String(season);
      option.textContent = String(season);
      seasonSelect.appendChild(option);
    });
  }

  const teamSelect = document.getElementById("teamFilter");
  if (teamSelect.options.length === 0) {
    const allOption = document.createElement("option");
    allOption.value = "";
    allOption.textContent = "All Teams";
    teamSelect.appendChild(allOption);

    TEAM_IDS.forEach((teamId) => {
      const option = document.createElement("option");
      option.value = teamId;
      option.textContent = teamId;
      teamSelect.appendChild(option);
    });
  }

  const positionSelect = document.getElementById("positionFilter");
  if (positionSelect.options.length === 0) {
    const allOption = document.createElement("option");
    allOption.value = "";
    allOption.textContent = "All Positions";
    positionSelect.appendChild(allOption);

    POSITION_GROUPS.forEach((group) => {
      const option = document.createElement("option");
      option.value = group;
      option.textContent = group;
      positionSelect.appendChild(option);
    });
  }
}

function setStatus(message, isError = false) {
  const el = document.getElementById("statusMessage");
  el.textContent = message || "";
  el.classList.toggle("error", Boolean(isError));
}

function teamSeasonEmptyMessage() {
  if (state.teamFilter) {
    return `No movement events match current filters for ${state.teamFilter} ${state.season}.`;
  }
  return `No movement events match current filters for ${state.season}.`;
}
