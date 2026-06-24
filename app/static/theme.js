"use strict";

// Session guard: if any API call comes back 401 (session expired or the account
// was logged out), bounce to the login page instead of letting pages render an
// empty/broken state. Wraps fetch once, before app.js/library.js run.
(function () {
  const realFetch = window.fetch.bind(window);
  let redirecting = false;
  window.fetch = async (...args) => {
    const res = await realFetch(...args);
    if (res.status === 401 && !redirecting) {
      redirecting = true;
      window.location.href = "/login";
    }
    return res;
  };
})();

// Light/dark theme toggle. The current theme is stored on <html data-theme="…">
// and persisted in localStorage. A tiny inline script in each page's <head>
// applies the saved theme before paint (avoiding a flash); this file wires the
// toggle button and keeps its icon in sync.
(function () {
  const root = document.documentElement;

  function current() {
    return root.getAttribute("data-theme") || "dark";
  }

  function apply(theme) {
    root.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* ignore */
    }
    // The button holds both a Moon and a Sun lucide SVG; CSS shows the one that
    // matches the active theme (see .theme-toggle .icon-sun/.icon-moon rules).
    // We only keep the tooltip in sync here — no glyph swap.
    const btn = document.getElementById("themeToggle");
    if (btn) {
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
