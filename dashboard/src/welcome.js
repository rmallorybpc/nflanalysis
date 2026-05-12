function rewriteNavLinksFromParams() {
  const params = new URLSearchParams(window.location.search);
  const season = params.get("season") || "";
  const teamId = params.get("team_id") || "";
  if (!season && !teamId) {
    return;
  }

  const suffix = `?season=${encodeURIComponent(season)}&team_id=${encodeURIComponent(teamId)}`;
  document.querySelectorAll("nav a").forEach((anchor) => {
    const base = anchor.getAttribute("href").split("?")[0];
    anchor.setAttribute("href", `${base}${suffix}`);
  });
}

function buildExampleUrl(exampleKey) {
  const map = {
    overview: "/src/index.html?season=2026&team_id=BUF#highlight=overview-metric",
    team: "/src/team.html?season=2022&team_id=JAX#highlight=timeline",
    scenario: "/src/scenario.html?season=2026#highlight=scenario-compare",
    explorer: "/src/explorer.html?season=2026#highlight=spend-vs-mis",
  };
  const raw = map[exampleKey];
  if (!raw) {
    return "";
  }

  // Deep-link helper: append from=welcome while preserving existing hash highlight target.
  const [pathAndQuery, hash] = raw.split("#");
  const joiner = pathAndQuery.includes("?") ? "&" : "?";
  const withSource = `${pathAndQuery}${joiner}from=welcome`;
  return hash ? `${withSource}#${hash}` : withSource;
}

function bindExampleButtons() {
  document.querySelectorAll("button[data-example]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.getAttribute("data-example");
      const targetUrl = buildExampleUrl(key);
      if (targetUrl) {
        window.location.href = targetUrl;
      }
    });
  });
}

function main() {
  rewriteNavLinksFromParams();
  bindExampleButtons();
}

document.addEventListener("DOMContentLoaded", main);
