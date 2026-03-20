const API_URL = "http://localhost:8080/v1/dashboard/team-detail?team_id=BUF&season=2024";
const FALLBACK_URL = "../public/team-detail.sample.json";

function fmt(num) {
  return Number(num).toFixed(3);
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
    `${cards.current_mis.outcome_name} | z ${fmt(cards.current_mis.mis_z)}`
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
    node.querySelector(".trend-value").textContent = fmt(row.mis_value);
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

async function loadData() {
  try {
    const live = await fetch(API_URL);
    if (live.ok) {
      return live.json();
    }
  } catch (_err) {
    // fallback for static preview
  }

  const fallback = await fetch(FALLBACK_URL);
  if (!fallback.ok) {
    throw new Error("Unable to load team detail payload");
  }
  return fallback.json();
}

async function main() {
  const payload = await loadData();
  applyMeta(payload);
  renderCards(payload);
  renderTimeline(payload);
  renderTrend(payload);
  renderPosition(payload);
}

main().catch((err) => console.error(err));
