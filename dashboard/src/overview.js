const API_URL = "http://localhost:8080/v1/dashboard/overview?season=2024";
const FALLBACK_URL = "../public/overview.sample.json";

function fmt(num) {
  return Number(num).toFixed(3);
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

  setCard(
    document.getElementById("topPositiveCard"),
    `Top Positive (${cards.top_positive_team.team_id})`,
    fmt(cards.top_positive_team.mis_value),
    `MISz ${fmt(cards.top_positive_team.mis_z)} | 90% [${fmt(cards.top_positive_team.interval_90.low)}, ${fmt(cards.top_positive_team.interval_90.high)}]`
  );

  setCard(
    document.getElementById("topNegativeCard"),
    `Top Negative (${cards.top_negative_team.team_id})`,
    fmt(cards.top_negative_team.mis_value),
    `MISz ${fmt(cards.top_negative_team.mis_z)} | 90% [${fmt(cards.top_negative_team.interval_90.low)}, ${fmt(cards.top_negative_team.interval_90.high)}]`
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

  const maxAbs = Math.max(...payload.charts.league_ranking.map((row) => Math.abs(row.mis_value)), 1);

  payload.charts.league_ranking.forEach((row) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector(".bar-label").textContent = `${row.rank}. ${row.team_id}`;
    node.querySelector(".bar-fill").style.width = `${Math.max((Math.abs(row.mis_value) / maxAbs) * 100, 4)}%`;
    node.querySelector(".bar-fill").style.background =
      row.mis_value >= 0
        ? "linear-gradient(90deg, #0f8a5f, #65c9a8)"
        : "linear-gradient(90deg, #c13f2d, #e68d7d)";
    node.querySelector(".bar-value").textContent = fmt(row.mis_value);
    container.appendChild(node);
  });
}

function renderDistribution(payload) {
  const grouped = {};
  for (const row of payload.charts.outcome_distribution) {
    if (!grouped[row.outcome_name]) {
      grouped[row.outcome_name] = [];
    }
    grouped[row.outcome_name].push(row);
  }

  const container = document.getElementById("distributionChart");
  const template = document.getElementById("distributionRowTemplate");
  container.innerHTML = "";

  Object.keys(grouped)
    .sort()
    .forEach((outcome) => {
      const node = template.content.firstElementChild.cloneNode(true);
      node.querySelector(".stack-label").textContent = outcome;
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
  const moveTypes = scope.included_move_types.join(", ");
  const outcomes = scope.outcomes.join(", ");
  const geos = scope.geography_dimensions.join(", ");

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
  const points = payload.charts.season_coverage;
  const container = document.getElementById("seasonCoverageChart");
  const template = document.getElementById("seasonCoverageRowTemplate");
  container.innerHTML = "";

  const maxTeams = Math.max(...points.map((point) => point.team_count), 1);
  points.forEach((point) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector(".bar-label").textContent = String(point.season);
    node.querySelector(".bar-fill").style.width = `${Math.max((point.team_count / maxTeams) * 100, 4)}%`;
    node.querySelector(".bar-fill").style.background = "linear-gradient(90deg, #2458a4, #57b7a9)";
    node.querySelector(".bar-value").textContent = `${point.team_count} teams | W${point.latest_week}`;
    container.appendChild(node);
  });
}

function renderGeography(payload) {
  const rows = payload.charts.geography_impact_profile;
  const container = document.getElementById("geographyChart");
  const template = document.getElementById("geoRowTemplate");
  container.innerHTML = "";

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

async function loadOverviewData() {
  try {
    const live = await fetch(API_URL);
    if (live.ok) {
      return live.json();
    }
  } catch (_err) {
    // Fallback for local static preview.
  }

  const fallback = await fetch(FALLBACK_URL);
  if (!fallback.ok) {
    throw new Error("Unable to load overview data from API or fallback payload");
  }
  return fallback.json();
}

async function main() {
  const payload = await loadOverviewData();
  applyMeta(payload);
  renderCards(payload);
  renderRanking(payload);
  renderDistribution(payload);
  renderScope(payload);
  renderSeasonCoverage(payload);
  renderGeography(payload);
}

main().catch((err) => {
  console.error(err);
});
