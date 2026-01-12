// app/static/js/main.js
(function () {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function debounce(fn, ms = 250) {
    let t = null;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  }

  function formatNumber(n, digits = 2) {
    const v = Number(n);
    if (!Number.isFinite(v)) return "";
    return v.toLocaleString(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: digits,
    });
  }

  function parseNumber(s) {
    if (s === null || s === undefined) return NaN;
    const v = String(s).replace(",", ".").trim();
    return Number(v);
  }

  function escapeHtml(str) {
    return String(str)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function initFlash() {
    const container = $(".flash");
    if (!container) return;

    $$(".flash__close", container).forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = btn.closest(".flash__item");
        if (item) item.remove();
      });
    });

    const autoHide = container.getAttribute("data-autohide") === "1";
    if (!autoHide) return;

    setTimeout(() => {
      $$(".flash__item", container).forEach((item) => {
        item.style.opacity = "0";
        item.style.transition = "opacity .25s ease";
        setTimeout(() => item.remove(), 250);
      });
    }, 5000);
  }

  function initConfirms() {
    document.addEventListener("click", (e) => {
      const el = e.target.closest("[data-confirm]");
      if (!el) return;

      const msg = el.getAttribute("data-confirm") || "Подтвердить действие?";
      if (!window.confirm(msg)) {
        e.preventDefault();
        e.stopPropagation();
      }
    });

    document.addEventListener(
      "submit",
      (e) => {
        const form = e.target.closest("form[data-confirm]");
        if (!form) return;

        const msg = form.getAttribute("data-confirm") || "Подтвердить действие?";
        if (!window.confirm(msg)) {
          e.preventDefault();
          e.stopPropagation();
        }
      },
      true
    );
  }

  function initAutoSubmitFilters() {
    $$("form[data-autosubmit='1']").forEach((form) => {
      const submitDebounced = debounce(() => form.submit(), 300);

      const textEnabled = form.getAttribute("data-autosubmit-text") === "1";

      $$("select, input[type='checkbox'], input[type='radio'], input[type='date'], input[type='datetime-local'], input[type='time']", form).forEach(
        (el) => el.addEventListener("change", () => form.submit())
      );

      $$("input[type='text'], input[type='search'], input[type='number']", form).forEach((el) => {
        const perEl = el.getAttribute("data-autosubmit-text") === "1";
        if (!textEnabled && !perEl) return;
        el.addEventListener("input", submitDebounced);
      });
    });
  }

  function initNumericInputs() {
    $$("input[data-numeric='1']").forEach((inp) => {
      inp.addEventListener("blur", () => {
        if (!inp.value) return;

        inp.value = String(inp.value).replace(",", ".").trim();
        const n = parseNumber(inp.value);

        const min = parseNumber(inp.getAttribute("data-min"));
        const max = parseNumber(inp.getAttribute("data-max"));

        if ((Number.isFinite(min) && n < min) || (Number.isFinite(max) && n > max)) {
          inp.classList.add("is-invalid");
        } else {
          inp.classList.remove("is-invalid");
        }
      });
    });
  }

  function initTooltips() {
    const tip = document.createElement("div");
    tip.style.position = "fixed";
    tip.style.zIndex = "9999";
    tip.style.pointerEvents = "none";
    tip.style.padding = "8px 10px";
    tip.style.border = "1px solid rgba(0,0,0,0.08)";
    tip.style.borderRadius = "10px";
    tip.style.background = "rgba(255,255,255,0.95)";
    tip.style.boxShadow = "0 10px 30px rgba(0,0,0,0.10)";
    tip.style.color = "#101114";
    tip.style.fontSize = "12px";
    tip.style.maxWidth = "320px";
    tip.style.display = "none";
    document.body.appendChild(tip);

    let active = null;

    document.addEventListener("mouseover", (e) => {
      const el = e.target.closest("[data-tip]");
      if (!el) return;
      const text = el.getAttribute("data-tip") || "";
      if (!text) return;

      active = el;
      tip.textContent = text;
      tip.style.display = "block";
    });

    document.addEventListener("mousemove", (e) => {
      if (!active) return;
      tip.style.left = e.clientX + 12 + "px";
      tip.style.top = e.clientY + 14 + "px";
    });

    document.addEventListener("mouseout", (e) => {
      const el = e.target.closest("[data-tip]");
      if (!el) return;
      active = null;
      tip.style.display = "none";
    });

    document.addEventListener("scroll", () => {
      if (!active) return;
      active = null;
      tip.style.display = "none";
    });
  }

  function initModals() {
    const openModal = (modal) => {
      if (!modal) return;
      modal.classList.add("is-open");
      modal.setAttribute("aria-hidden", "false");
      document.documentElement.classList.add("is-modal-open");
    };

    const closeModal = (modal) => {
      if (!modal) return;
      modal.classList.remove("is-open");
      modal.setAttribute("aria-hidden", "true");
      document.documentElement.classList.remove("is-modal-open");
    };

    document.addEventListener("click", (e) => {
      const opener = e.target.closest("[data-modal-open]");
      if (opener) {
        e.preventDefault();
        const sel = opener.getAttribute("data-modal-open");
        const modal = sel ? $(sel) : null;
        openModal(modal);
        return;
      }

      const closer = e.target.closest("[data-modal-close]");
      if (closer) {
        e.preventDefault();
        const modal = closer.closest("[data-modal]");
        closeModal(modal);
        return;
      }

      const modal = e.target.closest("[data-modal]");
      if (modal && e.target === modal && modal.getAttribute("data-modal-overlay-close") === "1") {
        closeModal(modal);
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      const modal = $("[data-modal].is-open");
      if (modal) closeModal(modal);
    });

    window.AppModal = { openModal, closeModal };
  }

  function initCharts() {
    const canvases = $$(".js-chart");
    if (!canvases.length) return;
    if (typeof window.Chart === "undefined") return;

    canvases.forEach((canvas) => {
      try {
        const type = canvas.getAttribute("data-chart-type") || "line";
        const label = canvas.getAttribute("data-label") || "Series";
        const labels = JSON.parse(canvas.getAttribute("data-labels") || "[]");
        const values = JSON.parse(canvas.getAttribute("data-values") || "[]");

        const nmin = parseNumber(canvas.getAttribute("data-min"));
        const nmax = parseNumber(canvas.getAttribute("data-max"));

        const datasets = [
          {
            label,
            data: values,
            borderWidth: 2,
            tension: 0.25,
            pointRadius: 2,
          },
        ];

        if (Number.isFinite(nmin)) {
          datasets.push({
            label: "Норма min",
            data: labels.map(() => nmin),
            borderWidth: 1,
            borderDash: [6, 6],
            pointRadius: 0,
          });
        }

        if (Number.isFinite(nmax)) {
          datasets.push({
            label: "Норма max",
            data: labels.map(() => nmax),
            borderWidth: 1,
            borderDash: [6, 6],
            pointRadius: 0,
          });
        }

        new window.Chart(canvas.getContext("2d"), {
          type,
          data: { labels, datasets },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
              legend: { display: true },
              tooltip: {
                callbacks: {
                  label: (ctx) => `${ctx.dataset.label}: ${formatNumber(ctx.parsed.y, 2)}`,
                },
              },
            },
            scales: {
              x: { ticks: { maxRotation: 0 } },
              y: { beginAtZero: false },
            },
          },
        });
      } catch (err) {
        console.warn("Chart init error:", err);
      }
    });
  }

  function initCopyButtons() {
    document.addEventListener("click", async (e) => {
      const el = e.target.closest("[data-copy], [data-copy-target]");
      if (!el) return;

      let text = el.getAttribute("data-copy");
      if (!text) {
        const targetSel = el.getAttribute("data-copy-target");
        const t = targetSel ? $(targetSel) : null;
        text = t ? (t.value || t.textContent || "") : "";
      }

      text = String(text || "");
      if (!text) return;

      try {
        await navigator.clipboard.writeText(text);
      } catch {
        const tmp = document.createElement("textarea");
        tmp.value = text;
        document.body.appendChild(tmp);
        tmp.select();
        document.execCommand("copy");
        tmp.remove();
      }

      const prev = el.getAttribute("data-tip") || "";
      el.setAttribute("data-tip", "Скопировано!");
      setTimeout(() => el.setAttribute("data-tip", prev), 1200);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initFlash();
    initConfirms();
    initAutoSubmitFilters();
    initNumericInputs();
    initTooltips();
    initModals();
    initCharts();
    initCopyButtons();
  });

  window.AppUI = {
    debounce,
    formatNumber,
    parseNumber,
    escapeHtml,
  };
})();
