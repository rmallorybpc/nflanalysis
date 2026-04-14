const API_BASE = (window.NFL_API_BASE || "https://nflanalysis.onrender.com").replace(/\/$/, "");

const TEAM_IDS = [
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
  "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
];

const state = {
  teamId: "BUF",
  season: 2024,
};

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
  const template = document.getElementById("timelineTemplate");
  container.innerHTML = "";

  payload.timeline.forEach((event) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector(".timeline-week").textContent = `W${event.nfl_week}`;
    node.querySelector(".timeline-content").textContent = `${event.move_type}: ${event.player_id} ${event.from_team_id} -> ${event.to_team_id} (impact ${fmt(event.impact_estimate)})`;
    container.appendChild(node);
  });
}

function renderTrend(payload) {
  const latestByOutcome = {};
  payload.charts.mis_trend.forEach((point) => {
    const key = point.outcome_name;
    if (!latestByOutcome[key] || point.nfl_week > latestByOutcome[key].nfl_week) {
      latestByOutcome[key] = point;
    }
  });

  const rows = Object.values(latestByOutcome);
  const maxAbs = Math.max(...rows.map((row) => Math.abs(row.mis_value)), 1);

  const container = document.getElementById("trend");
  const template = document.getElementById("trendTemplate");
  container.innerHTML = "";

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
  const container = document.getElementById("position");
  const template = document.getElementById("positionTemplate");
  container.innerHTML = "";

  payload.charts.position_group_delta.forEach((point) => {
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

  setStatus(`Loading ${state.teamId} ${state.season}...`);
  try {
    const payload = await loadData(state.teamId, state.season);
    applyMeta(payload);
    renderCards(payload);
    renderTimeline(payload);
    renderTrend(payload);
    renderPosition(payload);
    setStatus("");
  } catch (err) {
    resetRenderedData();
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
  const { reloadAction } = bindControls();
  if (hasTeam && hasSeason) {
    reloadAction();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  main();
});
