import {
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

const POSITION_GROUPS = [
  "offense_skill",
  "offense_line",
  "defense_front",
  "defense_second_level",
  "defense_secondary",
  "special_teams",
  "other",
];

const SEASON_OPTIONS = [
  2017, 2018, 2019, 2020, 2021,
  2022, 2023, 2024, 2025, 2026,
];

const state = {
  season: 2026,
  teamFilter: "",
  positionFilter: "",
  moveTypeFilter: "",
  directionFilter: "",
  misBandFilter: "",
  sortOrder: "abs_desc",
};

let geoProfileCache = null;

function seasonLabel(year) {
  return `${year} Season (Super Bowl Feb ${Number(year) + 1})`;
}

let allEvents = [];
let failedTeamCount = 0;
const seasonSummaryCache = {};
let dataManifestPromise = null;

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

async function loadGeoProfile(season) {
  if (geoProfileCache && geoProfileCache.season === season) {
    return geoProfileCache.data;
  }
  try {
    const url = await buildDataUrl(`overview/${season}.json`);
    const resp = await fetch(url);
    if (!resp.ok) {
      return null;
    }
    const json = await resp.json();
    const profile = (json.charts?.geography_impact_profile || [])
      .filter((g) => g.outcome_name === "win_pct");
    geoProfileCache = { season, data: profile };
    return profile;
  } catch {
    return null;
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
  document.getElementById("welcomeLink").href = `./welcome.html?${params.toString()}`;
  document.getElementById("findingsLink").href = `./findings.html?${params.toString()}`;
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
      const rawMetric = Number(event.mis_z ?? event.impact_estimate ?? 0);
      const metric = event.mis_z != null
        ? rawMetric
        : rawMetric * 100;
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
    if (state.sortOrder === "efficiency_desc") {
      // Impact per dollar: abs(impact_estimate) / contract_aav
      // Events with no contract data sort to the bottom
      const aAav = Number(a.contract_aav) || 0;
      const bAav = Number(b.contract_aav) || 0;
      const aEff = aAav > 0 ? Math.abs(Number(a.impact_estimate) || 0) / aAav : -1;
      const bEff = bAav > 0 ? Math.abs(Number(b.impact_estimate) || 0) / bAav : -1;
      return bEff - aEff;
    }
    if (state.sortOrder === "efficiency_asc") {
      const aAav = Number(a.contract_aav) || 0;
      const bAav = Number(b.contract_aav) || 0;
      const aEff = aAav > 0 ? Math.abs(Number(a.impact_estimate) || 0) / aAav : Infinity;
      const bEff = bAav > 0 ? Math.abs(Number(b.impact_estimate) || 0) / bAav : Infinity;
      return aEff - bEff;
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
    const misZ = toFiniteNumber(pickField(event, ["mis_z"], null));
    const scaledImpact = (toFiniteNumber(pickField(event, ["impact_estimate"], 0)) || 0) * 100;
    // Use mis_z if available, otherwise use scaled impact as proxy.
    const bandProxy = misZ !== null ? misZ : scaledImpact;
    const interval = intervalForEvent(event);
    const outcomeName = String(pickField(event, ["outcome_name"], "win_pct")).trim() || "win_pct";

    return {
      original: event,
      direction,
      pointEstimate,
      bandProxy,
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
            <span class="movement-interval-label" data-tooltip="Uncertainty range — there is a 90% probability the true impact falls within these bounds. A wide range means the model has less certainty about this estimate.">${item.interval.label}</span>
          </div>
          ${renderIntervalSvg(item.pointEstimate, item.interval, scale.min, scale.max)}
          <div class="movement-interval-text">[${fmt(item.interval.low)}, ${fmt(item.interval.high)}]</div>
        </div>
      `;
    }

    const lowConfidenceHtml = item.lowConfidence
      ? '<div class="movement-low-confidence" data-tooltip="The model has limited data to estimate this move\'s impact reliably. Treat this value as directional, not precise.">LOW CONFIDENCE</div>'
      : "";

    const contractAav = toFiniteNumber(pickField(item.original, ["contract_aav"], null));
    const contractYears = pickField(item.original, ["contract_years"], "");
    const contractHtml = contractAav && contractAav > 0
      ? `<div class="movement-contract">
           <span class="movement-contract-label" data-tooltip="Average Annual Value — the average yearly salary for this contract.">AAV</span>
           <span class="movement-contract-value">$${(contractAav / 1_000_000).toFixed(1)}M</span>${contractYears ? ` <span class="movement-contract-years">/ ${contractYears} yr${contractYears === "1" ? "" : "s"}</span>` : ""}
         </div>`
      : "";

    const positionHtml = item.position ? `<span class="movement-position">${item.position}</span>` : "";
    const moveScope = String(pickField(item.original, ["move_scope"], "")).trim().toLowerCase();
    const geo = geoLabel(moveScope);
    const geoBadgeHtml = geo
      ? `<span
           class="movement-geo-badge"
           style="color:${geo.color}"
           aria-label="Move geography: ${geo.text}"
           data-tooltip="Whether this player moved within their division, to a different division, or across conferences. The geography of a move can affect whether the reset effect applies."
         >${geo.text}</span>`
      : "";
    const moveId = String(pickField(item.original, ["move_id"], "")).trim();
    const geoPanelId = moveId ? `geo-panel-${moveId}` : "";
    const geoPanelHtml = geo && geoPanelId
      ? `<div class="movement-geo-panel" id="${geoPanelId}" style="display:none"></div>`
      : "";

    const card = document.createElement("article");
    card.className = `movement-card ${directionClass}`;
    card.dataset.moveId = moveId;
    card.innerHTML = `
      <div class="movement-row">
        <span class="movement-direction ${directionClass}">${directionLabel}</span>
        <span class="movement-badge">${moveTypeLabel || "MOVE"}</span>
        ${geoBadgeHtml}
      </div>
      ${geoPanelHtml}
      <div class="movement-player">
        <span class="movement-player-name">${item.playerName}</span>${positionHtml}
      </div>
      <div class="movement-route">${teamBoldFrom} &rarr; ${teamBoldTo}</div>
      <div class="movement-when">${whenText}</div>
      <div class="movement-mis-row">
        <span class="movement-mis-label" data-tooltip="Movement Impact Score — the estimated change in win probability from this player move. Positive means the team improved, negative means they lost ground.">MIS (win%)</span>
        <span class="movement-mis-value ${misBandClass(item.bandProxy)}">${fmtSigned(item.pointEstimate)}</span>
      </div>
      ${intervalHtml}
      ${contractHtml}
      ${lowConfidenceHtml}
      <div class="movement-footer"><a href="${whatIfHref}">Run What-If &rarr;</a></div>
    `;
    cardsRoot.appendChild(card);
  });

  container.appendChild(cardsRoot);

  container.querySelectorAll(".movement-geo-badge").forEach((badge) => {
    badge.style.cursor = "pointer";
    badge.addEventListener("click", async (e) => {
      e.stopPropagation();
      const card = badge.closest(".movement-card");
      const moveId = card?.dataset.moveId;
      if (!moveId) {
        return;
      }

      const panel = document.getElementById(`geo-panel-${moveId}`);
      if (!panel) {
        return;
      }

      if (panel.style.display !== "none") {
        panel.style.display = "none";
        return;
      }

      const profile = await loadGeoProfile(state.season);
      if (!profile || profile.length === 0) {
        panel.innerHTML = '<p class="movement-geo-panel-note">Geography data unavailable.</p>';
        panel.style.display = "block";
        return;
      }

      const scopeNames = {
        same_division: "Within Division",
        cross_division: "Diff. Division",
        cross_conference: "Diff. Conference",
      };

      const rows = ["same_division", "cross_division", "cross_conference"]
        .map((scope) => {
          const entry = profile.find((p) => p.move_scope === scope);
          const count = entry?.move_count ?? 0;
          const impact = entry?.avg_abs_impact ?? 0;
          return `<div class="movement-geo-panel-row">
          <span>${scopeNames[scope]}</span>
          <span>${count} moves</span>
          <span>avg ${fmtSigned(impact)} win%</span>
        </div>`;
        }).join("");

      const total = profile.reduce((s, p) => s + (p.move_count || 0), 0);

      panel.innerHTML = `
      <div class="movement-geo-panel-header">
        <span>League Geography — ${state.season} Season</span>
        <span class="movement-geo-panel-close"
          onclick="this.closest('.movement-geo-panel').style.display='none'">×</span>
      </div>
      ${rows}
      <div class="movement-geo-panel-note">
        Based on ${total} moves this season.
        Higher avg impact = stronger win probability signal.
      </div>`;
      panel.style.display = "block";
    });
  });
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

function geoLabel(scope) {
  const labels = {
    same_division: { text: "📍 Within Division", color: "var(--color-muted, #94a3b8)" },
    cross_division: { text: "🔀 Diff. Division", color: "#f59e0b" },
    cross_conference: { text: "🌐 Diff. Conference", color: "#8b5cf6" },
  };
  return labels[scope] || null;
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
      <line x1="0" y1="8" x2="160" y2="8" stroke="#2d3436" stroke-opacity="0.35" stroke-width="2" />
      <line x1="${leftX}" y1="8" x2="${rightX}" y2="8" stroke="#84a98c" stroke-width="3" />
      <line x1="${leftX}" y1="4" x2="${leftX}" y2="12" stroke="#6b8f74" stroke-width="2" />
      <line x1="${rightX}" y1="4" x2="${rightX}" y2="12" stroke="#6b8f74" stroke-width="2" />
      <circle cx="${pointX}" cy="8" r="3" fill="#2d3436" />
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
  progressEl.textContent = `Loading... (${settledCount} of 1 season file)`;

  const seasonUrl = await buildDataUrl(`season/${season}.json`);
  const seasonPayload = await fetch(seasonUrl)
    .then(async (resp) => {
      if (!resp.ok) {
        throw new Error(`status ${resp.status}`);
      }
      return resp.json();
    })
    .finally(() => {
      settledCount += 1;
      progressEl.textContent = `Loading... (${settledCount} of 1 season file)`;
    });

  const merged = [];
  TEAM_IDS.forEach((teamId) => {
    const payload = seasonPayload?.[teamId];
    const timeline = Array.isArray(payload?.timeline) ? payload.timeline : null;
    if (!timeline) {
      failedTeamCount += 1;
      return;
    }
    merged.push(...timeline.map((event) => ({
      ...event,
      team_id: teamId,
    })));
  });

  if (merged.length === 0) {
    throw new Error("Failed to load movement events for all teams.");
  }

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
    refreshSeasonNotice().catch((err) => console.error(err));
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

async function main() {
  rewriteNavLinksFromParams();
  const { hasSeason } = parseQueryState();
  if (!hasSeason) {
    state.season = await getLatestCompletedSeason(state.season);
  }
  syncControls();
  await refreshSeasonNotice();
  bindControls();
  refreshExplorer().catch((err) => console.error(err));
}

document.addEventListener("DOMContentLoaded", () => {
  main().catch((err) => console.error(err));
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
      option.textContent = seasonLabel(season);
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

async function getSeasonSummaryFor(season) {
  if (seasonSummaryCache[season]) {
    return seasonSummaryCache[season];
  }
  const outcomes = await loadTeamOutcomesIndex();
  const summary = getSeasonSummary(outcomes, season);
  seasonSummaryCache[season] = summary;
  return summary;
}

function renderSeasonContextNotice(seasonSummary) {
  const hero = document.querySelector("main .hero");
  if (!hero) {
    return;
  }

  let noticeEl = document.getElementById("explorerSeasonNotice");
  if (!noticeEl) {
    noticeEl = document.createElement("p");
    noticeEl.id = "explorerSeasonNotice";
    noticeEl.className = "status-message";
    hero.appendChild(noticeEl);
  }

  if (!seasonSummary || seasonSummary.status !== "upcoming") {
    noticeEl.textContent = "";
    noticeEl.classList.remove("error");
    return;
  }

  noticeEl.textContent = `${seasonLabel(seasonSummary.season)} is upcoming. Explorer cards show movement and model impact estimates, not observed game outcomes.`;
  noticeEl.classList.add("error");
}

async function refreshSeasonNotice() {
  const seasonValue = Number(document.getElementById("seasonInput")?.value);
  const season = Number.isFinite(seasonValue) && seasonValue > 0 ? Math.trunc(seasonValue) : state.season;
  try {
    const summary = await getSeasonSummaryFor(season);
    renderSeasonContextNotice(summary);
  } catch (_err) {
    renderSeasonContextNotice(null);
  }
}

function teamSeasonEmptyMessage() {
  if (state.teamFilter) {
    return `No movement events match current filters for ${state.teamFilter} ${state.season}.`;
  }
  return `No movement events match current filters for ${state.season}.`;
}
