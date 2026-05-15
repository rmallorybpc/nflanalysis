import { getLatestCompletedSeason } from "./seasonStatus.js";

let defaultSeason = 2025;

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

  const findingsLink = document.getElementById("findingsLink");
  if (findingsLink) {
    findingsLink.setAttribute("href", `./findings.html${suffix}`);
  }
}

function buildExampleUrl(exampleKey) {
  const map = {
    overview: `/src/index.html?season=${defaultSeason}&team_id=BUF#highlight=overview-metric`,
    team: "/src/team.html?season=2022&team_id=JAX#highlight=timeline",
    scenario: `/src/scenario.html?season=${defaultSeason}#highlight=scenario-compare`,
    explorer: `/src/explorer.html?season=${defaultSeason}#highlight=spend-vs-mis`,
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

function applyDefaultSeasonLinks(season) {
  const safeSeason = Number.isFinite(Number(season)) ? String(Math.trunc(Number(season))) : String(defaultSeason);
  const cta = document.querySelector(".welcome-cta");
  if (cta) {
    cta.setAttribute("href", `./index.html?season=${safeSeason}`);
    cta.textContent = `Explore the ${safeSeason} Season ->`;
  }

  const overviewLink = document.getElementById("overviewLink");
  const teamLink = document.getElementById("teamPageLink");
  const scenarioLink = document.getElementById("scenarioPageLink");
  if (overviewLink) overviewLink.setAttribute("href", `./index.html?season=${safeSeason}&team_id=BUF`);
  if (teamLink) teamLink.setAttribute("href", `./team.html?team_id=BUF&season=${safeSeason}`);
  if (scenarioLink) scenarioLink.setAttribute("href", `./scenario.html?team_id=BUF&season=${safeSeason}`);
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

async function main() {
  defaultSeason = await getLatestCompletedSeason(defaultSeason);
  applyDefaultSeasonLinks(defaultSeason);
  rewriteNavLinksFromParams();
  bindExampleButtons();
}

document.addEventListener("DOMContentLoaded", () => {
  main().catch((err) => console.error(err));
});
