const API_BASE = (window.NFL_API_BASE || "https://nflanalysis.onrender.com").replace(/\/$/, "");
const API_URL = `${API_BASE}/v1/dashboard/scenario-sandbox`;

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

function ensureTeamOptions(selectId) {
  const select = document.getElementById(selectId);
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
  const teamId = toTeamId(params.get("team_id"));
  const season = Number(params.get("season"));
  if (teamId) {
    state.teamId = teamId;
  }
  if (Number.isFinite(season) && season > 0) {
    state.season = Math.trunc(season);
  }
}

function syncControls() {
  ensureTeamOptions("teamId");
  ensureTeamOptions("fromTeam");
  ensureTeamOptions("toTeam");

  document.getElementById("teamId").value = state.teamId;
  document.getElementById("season").value = String(state.season);
  const toTeamSelect = document.getElementById("toTeam");
  const fromTeamSelect = document.getElementById("fromTeam");
  if (!toTeamId(toTeamSelect.value)) {
    toTeamSelect.value = state.teamId;
  }
  if (!toTeamId(fromTeamSelect.value)) {
    fromTeamSelect.value = "NYJ";
  }
  updateNavLinks();
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
}

function payloadFromInputs() {
  return {
    team_id: document.getElementById("teamId").value,
    season: Number(document.getElementById("season").value),
    week: Number(document.getElementById("week").value),
    scenario_id: document.getElementById("scenarioId").value.trim(),
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

async function runScenario() {
  syncStateFromControls();
  syncControls();
  writeQueryState();

  const payload = payloadFromInputs();
  setStatus("Running scenario...");
  try {
    const data = await fetchScenario(payload);
    renderDeltas(data.delta_summary);
    renderEstimates("baseline", data.baseline_estimates);
    renderEstimates("scenario", data.scenario_estimates);
    setStatus("");
  } catch (err) {
    resetRenderedData();
    const message = err instanceof Error
      ? err.message
      : "Data collection failed. Please check source data coverage and pipeline outputs.";
    setStatus(message, true);
  }
}

function bindControls() {
  const runAction = () => {
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

  ["teamId", "season", "week", "scenarioId", "playerId", "fromTeam", "toTeam", "moveType", "action"].forEach((id) => {
    document.getElementById(id).addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        runAction();
      }
    });
  });
}

function main() {
  parseQueryState();
  syncControls();
  bindControls();
  runScenario().catch((err) => console.error(err));
}

main();
