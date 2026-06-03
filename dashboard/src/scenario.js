import { getLatestCompletedSeason } from "./seasonStatus.js";

function rewriteNavLinksFromParams() {
  const params = new URLSearchParams(window.location.search);
  const season = params.get("season") || "";
  const teamId = params.get("team_id") || "";
  const suffix = (season || teamId)
    ? `?season=${encodeURIComponent(season)}&team_id=${encodeURIComponent(teamId)}`
    : "";

  document.querySelectorAll("nav a").forEach((anchor) => {
    const base = anchor.href.split("?")[0];
    if (suffix && !anchor.hasAttribute("aria-current")) {
      anchor.href = `${base}${suffix}`;
    }
  });
}

async function initScenarioPlaceholder() {
  const defaultSeason = await getLatestCompletedSeason();
  const params = new URLSearchParams(window.location.search);
  const safeTeam = (params.get("team_id") || "BUF").toUpperCase().slice(0, 3);
  const safeSeason = Number.isFinite(Number(params.get("season")))
    ? String(Math.trunc(Number(params.get("season"))))
    : String(defaultSeason);

  const navUpdates = {
    welcomeLink: `./welcome.html?season=${safeSeason}&team_id=${safeTeam}`,
    findingsLink: `./findings.html?season=${safeSeason}&team_id=${safeTeam}`,
    overviewLink: `./index.html?season=${safeSeason}&team_id=${safeTeam}`,
    teamLink: `./team.html?season=${safeSeason}&team_id=${safeTeam}`,
    explorerLink: `./explorer.html?season=${safeSeason}&team_id=${safeTeam}`,
  };

  Object.entries(navUpdates).forEach(([id, href]) => {
    const el = document.getElementById(id);
    if (el) {
      el.setAttribute("href", href);
    }
  });

  rewriteNavLinksFromParams();
}

document.addEventListener("DOMContentLoaded", () => {
  initScenarioPlaceholder().catch((err) => console.error(err));
});
