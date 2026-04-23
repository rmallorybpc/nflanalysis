const API_BASE = (window.NFL_API_BASE || "https://nflanalysis.onrender.com").replace(/\/$/, "");

const TEAM_IDS = [
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
  "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
];

const state = {
  teamId: "BUF",
  season: 2026,
};

const SHARE_DEFAULT_LABEL = "🔗 Share This View";
const SHARE_SUCCESS_LABEL = "✓ Link Copied";

function toTeamId(value) {
  const normalized = String(value || "")
    .trim()
    .toUpperCase()
    .slice(0, 3);
  return TEAM_IDS.includes(normalized) ? normalized : "";
}

function buildTeamDetailUrl(teamId, season) {
  const params = new URLSearchParams({
    team_id: teamId,
    season: String(season),
  });
  return `${API_BASE}/v1/dashboard/team-detail?${params.toString()}`;
}

function syncControls() {
  ensureTeamOptions();
  document.getElementById("teamInput").value = state.teamId;
  document.getElementById("seasonInput").value = String(state.season);
  const overviewLink = document.getElementById("overviewLink");
  overviewLink.href = `./index.html?season=${state.season}&team_id=${state.teamId}`;
  const scenarioLink = document.getElementById("scenarioLink");
  scenarioLink.href = `./scenario.html?season=${state.season}&team_id=${state.teamId}`;
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

function parseQueryState() {
  const params = new URLSearchParams(window.location.search);
  const hasTeam = params.has("team_id");
  const hasSeason = params.has("season");
  const queryTeam = toTeamId(params.get("team_id"));
  if (queryTeam) {
    state.teamId = queryTeam;
  }
  const querySeason = Number(params.get("season"));
  if (Number.isFinite(querySeason) && querySeason > 0) {
    state.season = Math.trunc(querySeason);
  }
  return { hasTeam, hasSeason };
}

function writeQueryState() {
  const params = new URLSearchParams({
    team_id: state.teamId,
    season: String(state.season),
  });
  window.history.replaceState({}, "", `?${params.toString()}`);
}

async function copyToClipboard(text) {
  if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_err) {
      // Fall back to legacy copy path below.
    }
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);

  const selection = document.getSelection();
  const selectedRange = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;

  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);

  let didCopy = false;
  try {
    didCopy = Boolean(document.execCommand && document.execCommand("copy"));
  } catch (_err) {
    didCopy = false;
  }

  document.body.removeChild(textarea);
  if (selection) {
    selection.removeAllRanges();
    if (selectedRange) {
      selection.addRange(selectedRange);
    }
  }

  return didCopy;
}

function bindShareButton() {
  const shareButton = document.getElementById("shareViewBtn");
  const shareFeedback = document.getElementById("shareFeedback");
  if (!shareButton || !shareFeedback) {
    return;
  }

  let successTimer = null;
  let failureTimer = null;

  shareButton.textContent = SHARE_DEFAULT_LABEL;

  shareButton.addEventListener("click", async () => {
    const url = window.location.href;

    if (successTimer) {
      window.clearTimeout(successTimer);
      successTimer = null;
    }
    if (failureTimer) {
      window.clearTimeout(failureTimer);
      failureTimer = null;
    }

    shareFeedback.textContent = "";

    const didCopy = await copyToClipboard(url);
    if (didCopy) {
      shareButton.classList.add("copied");
      shareButton.textContent = SHARE_SUCCESS_LABEL;
      successTimer = window.setTimeout(() => {
        shareButton.classList.remove("copied");
        shareButton.textContent = SHARE_DEFAULT_LABEL;
        successTimer = null;
      }, 2000);
      return;
    }

    shareButton.classList.remove("copied");
    shareButton.textContent = SHARE_DEFAULT_LABEL;
    shareFeedback.textContent = `Copy failed — try manually: ${url}`;
    failureTimer = window.setTimeout(() => {
      shareFeedback.textContent = "";
      failureTimer = null;
    }, 4000);
  });
}

function readControlState() {
  const rawSeason = Number(document.getElementById("seasonInput").value);
  const nextSeason = Number.isFinite(rawSeason) && rawSeason > 0 ? Math.trunc(rawSeason) : state.season;
  const nextTeam = toTeamId(document.getElementById("teamInput").value) || state.teamId;
  state.season = nextSeason;
  state.teamId = nextTeam;
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

function showTeamSkeletons() {
  document.getElementById("timeline").innerHTML = `
    <div class="skeleton-list timeline-skeleton-list">
      ${skeletonRows(3, ["100%", "100%", "100%"], 80, "timeline-skeleton-card")}
    </div>
  `;
  document.getElementById("trend").innerHTML = `<div class="skeleton skeleton-chart" style="height:120px;width:100%;"></div>`;
  document.getElementById("position").innerHTML = `<div class="skeleton-list">${skeletonRows(4, ["100%", "100%", "100%", "100%"], 20)}</div>`;
}

function showTeamErrorStates() {
  renderErrorState(document.getElementById("timeline"));
  renderErrorState(document.getElementById("trend"));
  renderErrorState(document.getElementById("position"));
}

function isTeamDetailPayload(payload) {
  return Boolean(
    payload &&
      payload.cards &&
      payload.cards.current_mis &&
      payload.timeline &&
      payload.charts &&
      payload.charts.mis_trend &&
      payload.charts.position_group_delta
  );
}

function resetRenderedData() {
  document.getElementById("cardCurrent").innerHTML = "";
  document.getElementById("cardMoves").innerHTML = "";
  document.getElementById("cardPosition").innerHTML = "";
  document.getElementById("timeline").innerHTML = "";
  document.getElementById("trend").innerHTML = "";
  document.getElementById("position").innerHTML = "";
}

function setCard(el, title, value, sub) {
  el.innerHTML = `<h3>${title}</h3><div class="big">${value}</div><div class="sub">${sub}</div>`;
}

function renderCards(payload) {
  const cards = payload.cards;
  setCard(
    document.getElementById("cardCurrent"),
    "Current MIS",
    fmt(cards.current_mis.mis_value),
    `${cards.current_mis.outcome_name} | z ${fmt(cards.current_mis.mis_z)} | 50% [${fmt(cards.current_mis.interval_50.low)}, ${fmt(cards.current_mis.interval_50.high)}] | 90% [${fmt(cards.current_mis.interval_90.low)}, ${fmt(cards.current_mis.interval_90.high)}] | ${cards.current_mis.low_confidence_flag ? "Low confidence" : "High confidence"}`
  );
  setCard(
    document.getElementById("cardMoves"),
    "Movement Counts",
    `${cards.inbound_move_count} in / ${cards.outbound_move_count} out`,
    "Regular-season movement events"
  );
  setCard(
    document.getElementById("cardPosition"),
    "Net Position Delta",
    fmt(cards.net_position_value_delta),
    "Aggregated weighted roster shift"
  );
}

function renderTimeline(payload) {
  const container = document.getElementById("timeline");
  container.innerHTML = "";

  renderMovementCards(payload.timeline, state.teamId, state.season, container);
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

function fmtSigned(num) {
  const fixed = Number(num).toFixed(3);
  return Number(num) >= 0 ? `+${fixed}` : fixed;
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

function renderTrend(payload) {
  const latestByOutcome = {};
  const sourceRows = Array.isArray(payload?.charts?.mis_trend) ? payload.charts.mis_trend : [];
  sourceRows.forEach((point) => {
    const key = point.outcome_name;
    if (!latestByOutcome[key] || point.nfl_week > latestByOutcome[key].nfl_week) {
      latestByOutcome[key] = point;
    }
  });

  const rows = Object.values(latestByOutcome);
  const container = document.getElementById("trend");
  const template = document.getElementById("trendTemplate");
  container.innerHTML = "";

  if (rows.length === 0) {
    renderEmptyState(container, teamSeasonEmptyMessage());
    return;
  }

  const maxAbs = Math.max(...rows.map((row) => Math.abs(row.mis_value)), 1);

  rows.forEach((row) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector(".trend-label").textContent = row.outcome_name;
    node.querySelector(".trend-fill").style.width = `${Math.max((Math.abs(row.mis_value) / maxAbs) * 100, 4)}%`;
    node.querySelector(".trend-fill").style.background =
      row.mis_value >= 0
        ? "linear-gradient(90deg, #0f7f7c, #57b7a9)"
        : "linear-gradient(90deg, #cf6330, #ef9a66)";
    node.querySelector(".trend-value").textContent = `${fmt(row.mis_value)} | 90% [${fmt(row.interval_90.low)}, ${fmt(row.interval_90.high)}]`;
    container.appendChild(node);
  });
}

function renderPosition(payload) {
  const rows = Array.isArray(payload?.charts?.position_group_delta) ? payload.charts.position_group_delta : [];
  const container = document.getElementById("position");
  const template = document.getElementById("positionTemplate");
  container.innerHTML = "";

  if (rows.length === 0) {
    renderEmptyState(container, teamSeasonEmptyMessage());
    return;
  }

  rows.forEach((point) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector(".position-label").textContent = point.position_group;
    const valueEl = node.querySelector(".position-value");
    valueEl.textContent = fmt(point.value_delta);
    valueEl.classList.add(point.value_delta >= 0 ? "positive" : "negative");
    container.appendChild(node);
  });
}

function applyMeta(payload) {
  document.getElementById("title").textContent = `Team ${payload.team_id}`;
  document.getElementById("meta").textContent = `Season ${payload.season} | Generated ${payload.generated_at}`;
}

async function loadData(teamId, season) {
  const apiUrl = buildTeamDetailUrl(teamId, season);
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
    if (isTeamDetailPayload(livePayload)) {
      return livePayload;
    }
    if (livePayload && livePayload.error) {
      throw new Error(`Live API error: ${livePayload.error}`);
    }
    throw new Error("Live API returned an invalid team detail payload format.");
  } catch (err) {
    const detail = err instanceof Error ? err.message : "request failed";
    throw new Error(`Data collection failed. Please check source data coverage and pipeline outputs. ${detail}`);
  }
}

async function refreshTeamDetail() {
  readControlState();
  syncControls();
  writeQueryState();
  showTeamSkeletons();

  setStatus(`Loading ${state.teamId} ${state.season}...`);
  try {
    const payload = await loadData(state.teamId, state.season);
    applyMeta(payload);
    renderCards(payload);
    renderTrend(payload);
    renderPosition(payload);
    renderMovementCards(payload.timeline, state.teamId, state.season);
    setStatus("");
  } catch (err) {
    resetRenderedData();
    showTeamErrorStates();
    document.getElementById("title").textContent = `Team ${state.teamId}`;
    document.getElementById("meta").textContent = `Season ${state.season} | Generated --`;
    const message = err instanceof Error
      ? err.message
      : "Data collection failed. Please check source data coverage and pipeline outputs.";
    setStatus(message, true);
  }
}

function bindControls() {
  const reloadAction = () => {
    refreshTeamDetail().catch((err) => console.error(err));
  };

  document.getElementById("reloadBtn").addEventListener("click", () => {
    reloadAction();
  });

  document.getElementById("teamInput").addEventListener("change", (event) => {
    const normalized = toTeamId(event.target.value);
    if (normalized) {
      state.teamId = normalized;
      syncControls();
    }
  });

  ["seasonInput", "teamInput"].forEach((id) => {
    document.getElementById(id).addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        reloadAction();
      }
    });
  });

  return { reloadAction };
}

function main() {
  rewriteNavLinksFromParams();
  const { hasTeam, hasSeason } = parseQueryState();
  syncControls();
  bindShareButton();
  const { reloadAction } = bindControls();
  if (hasTeam && hasSeason) {
    reloadAction();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  main();
});
