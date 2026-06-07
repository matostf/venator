"use strict";

// Light/dark theme toggle. The current theme is stored on <html data-theme="…">
// and persisted in localStorage. A tiny inline script in each page's <head>
// applies the saved theme before paint (avoiding a flash); this file wires the
// toggle button and keeps its icon in sync.
(function () {
  const root = document.documentElement;

  function current() {
    return root.getAttribute("data-theme") || "light";
  }

  function apply(theme) {
    root.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* ignore */
    }
    const btn = document.getElementById("themeToggle");
    if (btn) {
      btn.textContent = theme === "dark" ? "🌙" : "☀️";
      btn.title = theme === "dark" ? "Mudar para tema claro" : "Mudar para tema escuro";
    }
  }

  function init() {
    apply(current());
    const btn = document.getElementById("themeToggle");
    if (btn) {
      btn.addEventListener("click", () =>
        apply(current() === "dark" ? "light" : "dark")
      );
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
