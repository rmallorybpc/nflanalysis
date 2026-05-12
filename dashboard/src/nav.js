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

function ensureGlobalTooltipModal() {
  let modal = document.getElementById("globalTooltipModal");
  if (modal) {
    return modal;
  }

  modal = document.createElement("div");
  modal.id = "globalTooltipModal";
  modal.className = "tooltip-modal";
  modal.innerHTML = `
    <div class="tooltip-modal-card" role="dialog" aria-modal="true" aria-labelledby="globalTooltipModalTitle">
      <h2 id="globalTooltipModalTitle" class="sr-only">Term definition</h2>
      <p id="globalTooltipModalText"></p>
      <button type="button" class="tooltip-modal-close" id="globalTooltipModalClose" aria-label="Close tooltip modal">Close</button>
    </div>
  `;
  document.body.appendChild(modal);
  return modal;
}

function bindMobileTooltipModal() {
  if (window.innerWidth >= 600) {
    return;
  }

  const modal = ensureGlobalTooltipModal();
  const modalText = modal.querySelector("#globalTooltipModalText");
  const closeButton = modal.querySelector("#globalTooltipModalClose");
  const dialog = modal.querySelector(".tooltip-modal-card");
  let previousFocus = null;

  const closeModal = () => {
    modal.classList.remove("open");
    if (previousFocus && typeof previousFocus.focus === "function") {
      previousFocus.focus();
    }
    previousFocus = null;
  };

  const trapFocus = (event) => {
    if (event.key !== "Tab") {
      return;
    }
    const focusable = dialog.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    if (focusable.length === 0) {
      event.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  if (!modal.dataset.bound) {
    modal.dataset.bound = "true";
    closeButton.addEventListener("click", closeModal);
    modal.addEventListener("click", (event) => {
      if (event.target === modal) {
        closeModal();
      }
    });
    document.addEventListener("keydown", (event) => {
      if (!modal.classList.contains("open")) {
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        closeModal();
      } else {
        trapFocus(event);
      }
    });
  }

  document.querySelectorAll("[data-tooltip]").forEach((target) => {
    if (!target.hasAttribute("tabindex")) {
      target.setAttribute("tabindex", "0");
    }
    if (!target.hasAttribute("aria-label")) {
      target.setAttribute("aria-label", "Open tooltip details");
    }
    const openModal = (event) => {
      event.preventDefault();
      const text = target.getAttribute("data-tooltip") || "";
      modalText.textContent = text;
      previousFocus = target;
      modal.classList.add("open");
      closeButton.focus();
    };

    target.addEventListener("click", openModal);
    target.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        openModal(event);
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  applyWelcomeExampleHighlight();
  bindMobileTooltipModal();
});
