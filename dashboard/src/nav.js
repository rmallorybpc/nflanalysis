function getHighlightTargetId() {
  const hash = String(window.location.hash || "").replace(/^#/, "");
  if (!hash) {
    return "";
  }

  if (hash.startsWith("highlight=")) {
    return decodeURIComponent(hash.slice("highlight=".length));
  }

  return "";
}

function applyWelcomeExampleHighlight() {
  const params = new URLSearchParams(window.location.search);
  const fromWelcome = params.get("from") === "welcome";
  const targetId = getHighlightTargetId();

  // Highlight helper for deep-linked examples from the welcome page.
  if (!fromWelcome && !targetId) {
    return;
  }

  if (!targetId) {
    return;
  }

  const target = document.getElementById(targetId);
  if (!target) {
    return;
  }

  target.classList.add("example-highlight");
  window.setTimeout(() => {
    target.classList.remove("example-highlight");
  }, 3000);
}

document.addEventListener("DOMContentLoaded", () => {
  applyWelcomeExampleHighlight();
});
