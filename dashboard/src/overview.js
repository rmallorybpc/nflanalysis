const API_BASE = (window.NFL_API_BASE || "https://nflanalysis.onrender.com").replace(/\/$/, "");
const FALLBACK_URLS = [
  "../public/overview.sample.json",
  "./public/overview.sample.json",
  "/dashboard/public/overview.sample.json",
  "/public/overview.sample.json",
  "https://rmallorybpc.github.io/nflanalysis/dashboard/public/overview.sample.json",
  "https://raw.githubusercontent.com/rmallorybpc/nflanalysis/main/dashboard/public/overview.sample.json",
];

function buildSeasonFallbackUrls(season) {
  const safeSeason = Number.isFinite(Number(season)) ? Math.trunc(Number(season)) : null;
  if (!safeSeason || safeSeason <= 0) {
    return [];
  }

  const fileName = `overview.${safeSeason}.json`;
  return [
    `../public/${fileName}`,
    `./public/${fileName}`,
    `/dashboard/public/${fileName}`,
    `/public/${fileName}`,
    `https://rmallorybpc.github.io/nflanalysis/dashboard/public/${fileName}`,
    `https://raw.githubusercontent.com/rmallorybpc/nflanalysis/main/dashboard/public/${fileName}`,
  ];
}

const TEAM_IDS = [
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
  "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
];

const state = {
  season: 2024,
  teamId: "BUF",
};

function buildOverviewUrl(season) {
  const params = new URLSearchParams({ season: String(season) });
  return `${API_BASE}/v1/dashboard/overview?${params.toString()}`;
}

function toTeamId(value) {
  const normalized = String(value || "")
    .trim()
    .toUpperCase()
    .slice(0, 3);
  return TEAM_IDS.includes(normalized) ? normalized : "";
}

function getNumberInputValue(id, fallback) {
  const value = Number(document.getElementById(id).value);
  return Number.isFinite(value) && value > 0 ? Math.trunc(value) : fallback;
}

function syncControls() {
  ensureTeamOptions();
  document.getElementById("seasonInput").value = String(state.season);
  document.getElementById("teamInput").value = state.teamId;
  updateTeamLinks();
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

function updateTeamLinks() {
  const params = new URLSearchParams({
    team_id: state.teamId,
    season: String(state.season),
  });
  const href = `./team.html?${params.toString()}`;
  document.getElementById("openTeamBtn").href = href;
  document.getElementById("teamPageLink").href = href;
  document.getElementById("scenarioPageLink").href = `./scenario.html?${params.toString()}`;
}

function navigateToTeam(teamId) {
  const safeTeam = toTeamId(teamId) || state.teamId;
  const params = new URLSearchParams({
    team_id: safeTeam,
    season: String(state.season),
  });
  window.location.href = `./team.html?${params.toString()}`;
}

function fmt(num) {
  return Number(num).toFixed(3);
}

function setStatus(message, isError = false) {
  const el = document.getElementById("statusMessage");
  el.textContent = message || "";
  el.classList.toggle("error", Boolean(isError));
}

function isOverviewPayload(payload) {
  return Boolean(
    payload &&
      payload.cards &&
      payload.cards.top_positive_team &&
      payload.cards.top_negative_team &&
      payload.charts
  );
}

function resetRenderedData() {
  document.getElementById("topPositiveCard").innerHTML = "";
  document.getElementById("topNegativeCard").innerHTML = "";
  document.getElementById("leagueCard").innerHTML = "";
  document.getElementById("rankingChart").innerHTML = "";
  document.getElementById("distributionChart").innerHTML = "";
  document.getElementById("scopeList").innerHTML = "";
  document.getElementById("seasonCoverageChart").innerHTML = "";
  document.getElementById("geographyChart").innerHTML = "";
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
  const confidenceLabel = (flag) => (flag ? "Low confidence" : "High confidence");

  setCard(
    document.getElementById("topPositiveCard"),
    `Top Positive (${cards.top_positive_team.team_id})`,
    fmt(cards.top_positive_team.mis_value),
    `MISz ${fmt(cards.top_positive_team.mis_z)} | 90% [${fmt(cards.top_positive_team.interval_90.low)}, ${fmt(cards.top_positive_team.interval_90.high)}] | ${confidenceLabel(cards.top_positive_team.low_confidence_flag)}`
  );

  setCard(
    document.getElementById("topNegativeCard"),
    `Top Negative (${cards.top_negative_team.team_id})`,
    fmt(cards.top_negative_team.mis_value),
    `MISz ${fmt(cards.top_negative_team.mis_z)} | 90% [${fmt(cards.top_negative_team.interval_90.low)}, ${fmt(cards.top_negative_team.interval_90.high)}] | ${confidenceLabel(cards.top_negative_team.low_confidence_flag)}`
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
    node.classList.add("clickable");
    node.setAttribute("role", "button");
    node.tabIndex = 0;
    node.setAttribute("aria-label", `Open ${row.team_id} team detail`);
    node.querySelector(".bar-label").textContent = `${row.rank}. ${row.team_id}`;
    node.querySelector(".bar-fill").style.width = `${Math.max((Math.abs(row.mis_value) / maxAbs) * 100, 4)}%`;
    node.querySelector(".bar-fill").style.background =
      row.mis_value >= 0
        ? "linear-gradient(90deg, #0f8a5f, #65c9a8)"
        : "linear-gradient(90deg, #c13f2d, #e68d7d)";
    node.querySelector(".bar-value").textContent = fmt(row.mis_value);
    node.addEventListener("click", () => navigateToTeam(row.team_id));
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        navigateToTeam(row.team_id);
      }
    });
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

async function loadOverviewData(season) {
  const apiUrl = buildOverviewUrl(season);
  const seasonFallbackUrls = buildSeasonFallbackUrls(season);
  let liveError = null;

  try {
    const live = await fetch(apiUrl);
    if (live.ok) {
      const livePayload = await live.json();
      if (isOverviewPayload(livePayload)) {
        return { payload: livePayload, source: "live" };
      }
      if (livePayload && livePayload.error) {
        throw new Error(`Live API error: ${livePayload.error}`);
      }
      throw new Error("Live API returned an invalid overview payload format.");
    }
    liveError = new Error(`Live API request failed with status ${live.status}.`);
  } catch (_err) {
    // Continue to fallback fixture resolution for local/static previews.
    liveError = _err instanceof Error ? _err : new Error("Live API request failed.");
  }

  for (const fallbackUrl of seasonFallbackUrls) {
    try {
      const fallback = await fetch(fallbackUrl);
      if (!fallback.ok) {
        continue;
      }
      const fallbackPayload = await fallback.json();
      if (isOverviewPayload(fallbackPayload)) {
        return { payload: fallbackPayload, source: "preview" };
      }
    } catch (_err) {
      // Try the next fallback URL.
    }
  }

  for (const fallbackUrl of FALLBACK_URLS) {
    try {
      const fallback = await fetch(fallbackUrl);
      if (!fallback.ok) {
        continue;
      }
      const fallbackPayload = await fallback.json();
      if (isOverviewPayload(fallbackPayload)) {
        return { payload: fallbackPayload, source: "fallback" };
      }
    } catch (_err) {
      // Try the next fallback URL.
    }
  }

  const liveErrorSuffix = liveError instanceof Error ? ` Last live error: ${liveError.message}` : "";
  throw new Error(`Unable to load overview data from API or fallback payload.${liveErrorSuffix}`);
}

async function refreshOverview() {
  state.season = getNumberInputValue("seasonInput", state.season);
  state.teamId = toTeamId(document.getElementById("teamInput").value) || state.teamId;
  syncControls();
  writeQueryState();

  setStatus(`Loading season ${state.season}...`);
  try {
    const loaded = await loadOverviewData(state.season);
    const payload = loaded.payload;
    applyMeta(payload);
    renderCards(payload);
    renderRanking(payload);
    renderDistribution(payload);
    renderScope(payload);
    renderSeasonCoverage(payload);
    renderGeography(payload);
    if (loaded.source === "fallback") {
      setStatus("Showing fallback sample data because live API data was unavailable.");
    } else {
      setStatus("");
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unable to load overview data.";
    resetRenderedData();
    document.getElementById("seasonLabel").textContent = `Season: ${state.season}`;
    document.getElementById("generatedLabel").textContent = "Generated: --";
    setStatus(message, true);
  }
}

function parseQueryState() {
  const params = new URLSearchParams(window.location.search);
  const season = Number(params.get("season"));
  if (Number.isFinite(season) && season > 0) {
    state.season = Math.trunc(season);
  }
  const teamId = toTeamId(params.get("team_id"));
  if (teamId) {
    state.teamId = teamId;
  }
}

function writeQueryState() {
  const params = new URLSearchParams({
    season: String(state.season),
    team_id: state.teamId,
  });
  window.history.replaceState({}, "", `?${params.toString()}`);
}

function bindControls() {
  const refreshAction = () => {
    refreshOverview().catch((err) => console.error(err));
  };

  document.getElementById("refreshBtn").addEventListener("click", () => {
    refreshAction();
  });

  document.getElementById("teamInput").addEventListener("change", (event) => {
    const normalized = toTeamId(event.target.value);
    if (normalized) {
      state.teamId = normalized;
      updateTeamLinks();
    }
  });

  ["seasonInput", "teamInput"].forEach((id) => {
    document.getElementById(id).addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        refreshAction();
      }
    });
  });
}

async function main() {
  parseQueryState();
  syncControls();
  bindControls();
  await refreshOverview();
}

main().catch((err) => {
  console.error(err);
});
