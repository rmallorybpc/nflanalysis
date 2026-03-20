const API_URL = "http://localhost:8080/v1/dashboard/scenario-sandbox";
const FALLBACK_URL = "../public/scenario-sandbox.sample.json";

function fmt(num) {
  return Number(num).toFixed(3);
}

function payloadFromInputs() {
  return {
    team_id: document.getElementById("teamId").value.trim(),
    season: Number(document.getElementById("season").value),
    week: Number(document.getElementById("week").value),
    scenario_id: document.getElementById("scenarioId").value.trim(),
    applied_moves: [
      {
        move_id: "ui_custom_001",
        player_id: document.getElementById("playerId").value.trim(),
        from_team_id: document.getElementById("fromTeam").value.trim(),
        to_team_id: document.getElementById("toTeam").value.trim(),
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
    if (resp.ok) {
      return resp.json();
    }
  } catch (_err) {
    // static fallback path below
  }

  const fallback = await fetch(FALLBACK_URL);
  if (!fallback.ok) {
    throw new Error("Unable to fetch scenario payload");
  }
  return fallback.json();
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
  const payload = payloadFromInputs();
  const data = await fetchScenario(payload);
  renderDeltas(data.delta_summary);
  renderEstimates("baseline", data.baseline_estimates);
  renderEstimates("scenario", data.scenario_estimates);
}

document.getElementById("runBtn").addEventListener("click", () => {
  runScenario().catch((err) => console.error(err));
});

runScenario().catch((err) => console.error(err));
