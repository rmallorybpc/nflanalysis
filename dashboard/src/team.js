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

const state = {
  teamId: "BUF",
  season: 2026,
  payload: null,
};

let geoProfileCache = null;
let cardsExpanded = false;
const seasonSummaryCache = {};
let dataManifestPromise = null;

function seasonLabel(year) {
  return `${year} Season (Super Bowl Feb ${Number(year) + 1})`;
}

const SHARE_DEFAULT_LABEL = "🔗 Share This View";
const SHARE_SUCCESS_LABEL = "✓ Link Copied";

function toTeamId(value) {
  const normalized = String(value || "")
    .trim()
    .toUpperCase()
    .slice(0, 3);
  return TEAM_IDS.includes(normalized) ? normalized : "";
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

function syncControls() {
  ensureTeamOptions();
  document.getElementById("teamInput").value = state.teamId;
  document.getElementById("seasonInput").value = String(state.season);
  const welcomeLink = document.getElementById("welcomeLink");
  welcomeLink.href = `./welcome.html?season=${state.season}&team_id=${state.teamId}`;
  const findingsLink = document.getElementById("findingsLink");
  findingsLink.href = `./findings.html?season=${state.season}&team_id=${state.teamId}`;
  const overviewLink = document.getElementById("overviewLink");
  overviewLink.href = `./index.html?season=${state.season}&team_id=${state.teamId}`;
  const explorerLink = document.getElementById("explorerLink");
  explorerLink.href = `./explorer.html?season=${state.season}&team_id=${state.teamId}`;
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
  const value = Number(num);
  if (!Number.isFinite(value)) {
    return "0.000";
  }
  const decimals = Math.abs(value) > 0 && Math.abs(value) < 0.001 ? 6 : 3;
  return value.toFixed(decimals);
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

  let noticeEl = document.getElementById("teamSeasonNotice");
  if (!noticeEl) {
    noticeEl = document.createElement("p");
    noticeEl.id = "teamSeasonNotice";
    noticeEl.className = "status-message";
    hero.appendChild(noticeEl);
  }

  if (!seasonSummary || seasonSummary.status !== "upcoming") {
    noticeEl.textContent = "";
    noticeEl.classList.remove("error");
    return;
  }

  noticeEl.textContent = `${seasonLabel(seasonSummary.season)} is upcoming. Team outputs on this page are model estimates from player movement, not observed results.`;
  noticeEl.classList.add("error");
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
  cardsExpanded = false;
  document.getElementById("cardCurrent").innerHTML = "";
  document.getElementById("cardMoves").innerHTML = "";
  document.getElementById("cardPosition").innerHTML = "";
  document.getElementById("timeline").innerHTML = "";
  document.getElementById("trend").innerHTML = "";
  document.getElementById("position").innerHTML = "";
  const cardsBtn = document.getElementById("cardsExpandBtn");
  if (cardsBtn) {
    cardsBtn.style.display = "none";
  }
  const cardsNote = document.getElementById("cardsCollapseNote");
  if (cardsNote) {
    cardsNote.style.display = "";
  }
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
  const value = Number(num);
  if (!Number.isFinite(value)) {
    return "+0.000";
  }
  const decimals = Math.abs(value) > 0 && Math.abs(value) < 0.001 ? 6 : 3;
  const fixed = value.toFixed(decimals);
  return value >= 0 ? `+${fixed}` : fixed;
}

function computeMISDecomposition(payload, teamId) {
  const timeline = Array.isArray(payload?.timeline) ? payload.timeline : [];
  const currentMIS = parseFloat(payload?.cards?.current_mis?.mis_value) || 0;
  const tid = String(teamId || "").trim().toUpperCase();

  const inboundEvents = timeline.filter(
    (e) => String(e?.to_team_id || "").trim().toUpperCase() === tid
  );
  const outboundEvents = timeline.filter(
    (e) => String(e?.from_team_id || "").trim().toUpperCase() === tid
  );

  const inboundImpact = inboundEvents.reduce(
    (sum, e) => sum + (parseFloat(e?.impact_estimate) || 0),
    0
  );
  const outboundImpact = outboundEvents.reduce(
    (sum, e) => sum + (parseFloat(e?.impact_estimate) || 0),
    0
  );
  const interactionTerm = currentMIS - inboundImpact - outboundImpact;

  return {
    total: currentMIS,
    inbound: inboundImpact,
    outbound: outboundImpact,
    interaction: interactionTerm,
    inboundCount: inboundEvents.length,
    outboundCount: outboundEvents.length,
  };
}

function decompInterpretation(decomp) {
  const driver = Math.abs(decomp.inbound) > Math.abs(decomp.outbound)
    ? "additions"
    : "departures";
  const direction = decomp.total > 0.001
    ? "positive"
    : decomp.total < -0.001
      ? "negative"
      : "neutral";

  if (direction === "positive" && driver === "additions") {
    return "Win impact driven primarily by incoming players.";
  }
  if (direction === "positive" && driver === "departures") {
    return "Win impact driven primarily by who left.";
  }
  if (direction === "negative" && driver === "additions") {
    return "Negative impact despite additions - departures offset gains.";
  }
  if (direction === "negative" && driver === "departures") {
    return "Negative impact driven primarily by player losses.";
  }
  return "Mixed impact - additions and departures roughly balanced.";
}

function renderDecomp(decomp) {
  const card = document.getElementById("cardDecomp");
  if (!card) {
    return;
  }

  const fmtValue = (value) => {
    const num = Number(value);
    if (!Number.isFinite(num)) {
      return "--";
    }
    return `${num >= 0 ? "+" : ""}${num.toFixed(4)}`;
  };
  const colorClass = (value) => (
    value > 0.001 ? "positive" : value < -0.001 ? "negative" : "neutral"
  );

  const inboundRow = document.getElementById("decompInbound");
  const outboundRow = document.getElementById("decompOutbound");
  const interactionRow = document.getElementById("decompInteraction");
  const note = document.getElementById("decompNote");

  if (!inboundRow || !outboundRow || !interactionRow) {
    return;
  }

  const inboundValue = inboundRow.querySelector(".decomp-value");
  const outboundValue = outboundRow.querySelector(".decomp-value");
  const interactionValue = interactionRow.querySelector(".decomp-value");
  const inboundCount = inboundRow.querySelector(".decomp-count");
  const outboundCount = outboundRow.querySelector(".decomp-count");

  if (inboundValue) {
    inboundValue.textContent = fmtValue(decomp.inbound);
    inboundValue.className = `decomp-value ${colorClass(decomp.inbound)}`;
  }
  if (inboundCount) {
    inboundCount.textContent = `(${decomp.inboundCount} moves)`;
  }

  if (outboundValue) {
    outboundValue.textContent = fmtValue(decomp.outbound);
    outboundValue.className = `decomp-value ${colorClass(decomp.outbound)}`;
  }
  if (outboundCount) {
    outboundCount.textContent = `(${decomp.outboundCount} moves)`;
  }

  if (interactionValue) {
    interactionValue.textContent = fmtValue(decomp.interaction);
    interactionValue.className = `decomp-value ${colorClass(decomp.interaction)}`;
  }

  if (note) {
    note.textContent = decompInterpretation(decomp);
  }
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

function geoLabel(scope) {
  const labels = {
    same_division: { text: "📍 Within Division", color: "var(--color-muted, #94a3b8)" },
    cross_division: { text: "🔀 Diff. Division", color: "#f59e0b" },
    cross_conference: { text: "🌐 Diff. Conference", color: "#8b5cf6" },
  };
  return labels[scope] || null;
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

function renderMovementCards(events, teamId, season, containerEl = null) {
  const timelineContainer = containerEl || document.getElementById("timeline");
  timelineContainer.innerHTML = '<div id="movementCards" class="movement-cards"></div>';
  const container = document.getElementById("movementCards");

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
    const cardsBtn = document.getElementById("cardsExpandBtn");
    if (cardsBtn) {
      cardsBtn.style.display = "none";
    }
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
        <span class="movement-mis-value ${misBandClass(item.misZ)}">${fmtSigned(item.pointEstimate)}</span>
      </div>
      ${intervalHtml}
      ${contractHtml}
      ${lowConfidenceHtml}
    `;
    container.appendChild(card);
  });

  applyCardsCollapse(events, teamId);

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

function selectDefaultCards(events, teamId) {
  const normalizedTeamId = String(teamId || "").trim().toUpperCase();
  const inbound = (events || []).filter((event) => {
    const toTeam = String(event?.to_team_id || "").trim().toUpperCase();
    const aav = parseFloat(event?.contract_aav) || 0;
    const moveId = String(event?.move_id || "").trim();
    return Boolean(moveId) && toTeam === normalizedTeamId && aav > 0;
  });

  if (inbound.length === 0) return null;

  const sorted = [...inbound].sort(
    (a, b) => (parseFloat(b.contract_aav) || 0)
      - (parseFloat(a.contract_aav) || 0)
  );

  const top3 = sorted.slice(0, 3).map((event) => String(event.move_id));
  const bottom3 = sorted.slice(-3).map((event) => String(event.move_id));

  return {
    selected: new Set([...top3, ...bottom3]),
    topMoveIds: top3,
    bottomMoveIds: bottom3,
  };
}

function applyCardsCollapse(events, teamId) {
  const container = document.getElementById("movementCards");
  if (!container) return;

  const cards = [...container.querySelectorAll(".movement-card")];
  if (cards.length === 0) return;

  const defaultSelection = selectDefaultCards(events, teamId);
  const defaultSet = defaultSelection?.selected;

  container.querySelectorAll(".cards-separator").forEach((separator) => separator.remove());

  if (cardsExpanded || !defaultSet || defaultSet.size === 0) {
    cards.forEach((card) => {
      card.style.display = "";
    });
  } else {
    cards.forEach((card) => {
      const moveId = card.dataset.moveId;
      card.style.display = defaultSet.has(moveId) ? "" : "none";
    });

    const topMoveIds = defaultSelection.topMoveIds.filter((moveId) => defaultSet.has(moveId));
    const bottomMoveIds = defaultSelection.bottomMoveIds.filter((moveId) => defaultSet.has(moveId));
    const hasDistinctGroups = topMoveIds.length > 0
      && bottomMoveIds.length > 0
      && topMoveIds.some((moveId) => !bottomMoveIds.includes(moveId));

    if (hasDistinctGroups) {
      const bottomFirstCard = bottomMoveIds
        .map((moveId) => container.querySelector(`[data-move-id="${CSS.escape(moveId)}"]`))
        .find(Boolean);
      if (bottomFirstCard) {
        const separator = document.createElement("div");
        separator.className = "cards-separator";
        separator.innerHTML = "<span>· · ·</span>";
        bottomFirstCard.before(separator);
      }
    }
  }

  const note = document.getElementById("cardsCollapseNote");
  if (note) {
    note.style.display = cardsExpanded ? "none" : "";
  }

  const btn = document.getElementById("cardsExpandBtn");
  if (!btn) return;

  const totalCount = cards.length;
  if (cardsExpanded) {
    btn.textContent = "Show top and bottom signings only ↑";
    btn.setAttribute("aria-expanded", "true");
  } else {
    btn.textContent = `Show all ${totalCount} players ↓`;
    btn.setAttribute("aria-expanded", "false");
  }
  btn.style.display = totalCount > 6 ? "" : "none";
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
          ? "linear-gradient(90deg, #2e8540, #84a98c)"
          : "linear-gradient(90deg, #b00020, #d56b7f)";
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
  const seasonUrl = await buildDataUrl(`season/${season}.json`);
  try {
    const resp = await fetch(seasonUrl);
    if (!resp.ok) {
      throw new Error(`Static data request failed: status ${resp.status}`);
    }

    const seasonPayload = await resp.json();
    const payload = seasonPayload?.[teamId] || null;
    if (isTeamDetailPayload(payload)) {
      return payload;
    }
    throw new Error("Static data returned an invalid team detail payload format.");
  } catch (err) {
    const detail = err instanceof Error ? err.message : "request failed";
    throw new Error(`Data collection failed. Please check source data coverage and pipeline outputs. ${detail}`);
  }
}

async function refreshTeamDetail() {
  const previousTeamId = state.teamId;
  const previousSeason = state.season;
  readControlState();
  if (state.teamId !== previousTeamId || state.season !== previousSeason) {
    cardsExpanded = false;
  }
  try {
    const seasonSummary = await getSeasonSummaryFor(state.season);
    renderSeasonContextNotice(seasonSummary);
  } catch (_err) {
    renderSeasonContextNotice(null);
  }
  syncControls();
  writeQueryState();
  showTeamSkeletons();

  setStatus(`Loading ${state.teamId} ${state.season}...`);
  try {
    const payload = await loadData(state.teamId, state.season);
    state.payload = payload;
    const decomp = computeMISDecomposition(state.payload, state.teamId);
    applyMeta(payload);
    renderDecomp(decomp);
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
      cardsExpanded = false;
      syncControls();
    }
  });

  document.getElementById("seasonInput").addEventListener("change", () => {
    cardsExpanded = false;
  });

  const cardsBtn = document.getElementById("cardsExpandBtn");
  if (cardsBtn) {
    cardsBtn.addEventListener("click", () => {
      cardsExpanded = !cardsExpanded;
      applyCardsCollapse(state.payload?.timeline || [], state.teamId);
    });
  }

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

async function main() {
  rewriteNavLinksFromParams();
  const { hasTeam, hasSeason } = parseQueryState();
  if (!hasSeason) {
    state.season = await getLatestCompletedSeason(state.season);
  }
  try {
    const seasonSummary = await getSeasonSummaryFor(state.season);
    renderSeasonContextNotice(seasonSummary);
  } catch (_err) {
    renderSeasonContextNotice(null);
  }
  syncControls();
  bindShareButton();
  const { reloadAction } = bindControls();
  if (hasTeam && hasSeason) {
    reloadAction();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  main().catch((err) => console.error(err));
});
