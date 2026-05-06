function rewriteNavLinksFromParams() {
  const params = new URLSearchParams(window.location.search);
  const season = params.get("season") || "";
  const teamId = params.get("team_id") || "";
  if (!season && !teamId) {
    return;
  }

  const suffix = `?season=${encodeURIComponent(season)}&team_id=${encodeURIComponent(teamId)}`;
  document.querySelectorAll(".top-nav a").forEach((anchor) => {
    const base = anchor.getAttribute("href").split("?")[0];
    anchor.setAttribute("href", `${base}${suffix}`);
  });
}

function buildExampleUrl(exampleKey) {
  const map = {
    overview: "/src/index.html?season=2026&team_id=BUF#highlight=overview-metric",
    team: "/src/index.html?season=2022&team_id=JAX#highlight=movement-card-1",
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

function ensureTooltipModal() {
  let modal = document.getElementById("tooltipModal");
  if (modal) {
    return modal;
  }

  modal = document.createElement("div");
  modal.id = "tooltipModal";
  modal.className = "tooltip-modal";
  modal.innerHTML = `
    <div class="tooltip-modal-card" role="dialog" aria-modal="true" aria-label="Term definition">
      <p id="tooltipModalText"></p>
      <button type="button" class="tooltip-modal-close" id="tooltipModalClose" aria-label="Close definition modal">Close</button>
    </div>
  `;
  document.body.appendChild(modal);

  const closeModal = () => {
    modal.classList.remove("open");
  };

  modal.addEventListener("click", (event) => {
    if (event.target === modal) {
      closeModal();
    }
  });

  document.getElementById("tooltipModalClose").addEventListener("click", closeModal);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeModal();
    }
  });

  return modal;
}

function bindMobileTooltipModal() {
  // Progressive enhancement: turn tooltip taps into modal dialogs on narrow screens.
  if (window.innerWidth >= 600) {
    return;
  }

  const modal = ensureTooltipModal();
  const modalText = document.getElementById("tooltipModalText");

  document.querySelectorAll("[data-tooltip]").forEach((target) => {
    target.addEventListener("click", (event) => {
      event.preventDefault();
      const text = target.getAttribute("data-tooltip") || "";
      modalText.textContent = text;
      modal.classList.add("open");
    });
  });
}

function main() {
  rewriteNavLinksFromParams();
  bindExampleButtons();
  bindMobileTooltipModal();
}

document.addEventListener("DOMContentLoaded", main);
