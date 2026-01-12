// app/static/js/main.js
// Лёгкий JS для UI: flash-уведомления, confirm, фильтры, тултипы, и мини-хелперы под графики.

(function () {
  "use strict";

  // ----------------------------
  // Helpers
  // ----------------------------
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
    const n = Number(v);
    return n;
  }

  function escapeHtml(str) {
    return String(str)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  // ----------------------------
  // Flash messages: auto-hide + close
  // ----------------------------
  function initFlash() {
    const container = $(".flash");
    if (!container) return;

    $$(".flash__close", container).forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = btn.closest(".flash__item");
        if (item) item.remove();
      });
    });

    // auto hide after 5s (only if data-autohide="1" on container)
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

  // ----------------------------
  // Confirm for destructive actions
  // Add attribute: data-confirm="Точно удалить?"
  // ----------------------------
  function initConfirms() {
    document.addEventListener("click", (e) => {
      const el = e.target.closest("[data-confirm]");
      if (!el) return;

      const msg = el.getAttribute("data-confirm") || "Подтвердить действие?";
      const ok = window.confirm(msg);
      if (!ok) {
        e.preventDefault();
        e.stopPropagation();
      }
    });
  }

  // ----------------------------
  // Filter forms: submit on change (optional)
  // Add attribute: data-autosubmit="1" on form
  // ----------------------------
  function initAutoSubmitFilters() {
    $$("form[data-autosubmit='1']").forEach((form) => {
      const handler = debounce(() => form.submit(), 250);
      $$("select, input[type='checkbox']", form).forEach((el) => {
        el.addEventListener("change", handler);
      });
    });
  }

  // ----------------------------
  // Input numeric improvements
  // - replace comma to dot on blur
  // - optional min/max validation via data-min/data-max
  // ----------------------------
  function initNumericInputs() {
    $$("input[data-numeric='1']").forEach((inp) => {
      inp.addEventListener("blur", () => {
        const v = inp.value;
        if (!v) return;
        inp.value = String(v).replace(",", ".").trim();

        const n = parseNumber(inp.value);
        const min = parseNumber(inp.getAttribute("data-min"));
        const max = parseNumber(inp.getAttribute("data-max"));

        if (Number.isFinite(min) && n < min) inp.classList.add("is-invalid");
        else if (Number.isFinite(max) && n > max) inp.classList.add("is-invalid");
        else inp.classList.remove("is-invalid");
      });
    });
  }

  // ----------------------------
  // Tooltips (very light)
  // Elements: data-tip="..."
  // ----------------------------
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
      active = el;
      tip.textContent = el.getAttribute("data-tip") || "";
      tip.style.display = "block";
    });

    document.addEventListener("mousemove", (e) => {
      if (!active) return;
      const x = e.clientX + 12;
      const y = e.clientY + 14;
      tip.style.left = x + "px";
      tip.style.top = y + "px";
    });

    document.addEventListener("mouseout", (e) => {
      const el = e.target.closest("[data-tip]");
      if (!el) return;
      active = null;
      tip.style.display = "none";
    });
  }

  // ----------------------------
  // Charts support (optional)
  // If Chart.js is included in templates, we can render charts automatically.
  //
  // Use:
  // <canvas class="js-chart"
  //         data-chart-type="line"
  //         data-label="Пульс"
  //         data-labels='["2026-01-01","2026-01-02"]'
  //         data-values='[62,65]'
  //         data-min="50"
  //         data-max="90"></canvas>
  //
  // This module:
  // - checks window.Chart
  // - builds a chart with a safe default
  // - optional min/max reference lines (if plugin not available, just show in tooltip)
  // ----------------------------
  function initCharts() {
    const canvases = $$(".js-chart");
    if (!canvases.length) return;

    if (typeof window.Chart === "undefined") {
      // Chart.js is not loaded — keep UI silent and usable
      return;
    }

    canvases.forEach((canvas) => {
      try {
        const type = canvas.getAttribute("data-chart-type") || "line";
        const label = canvas.getAttribute("data-label") || "Series";
        const labels = JSON.parse(canvas.getAttribute("data-labels") || "[]");
        const values = JSON.parse(canvas.getAttribute("data-values") || "[]");

        const nmin = parseNumber(canvas.getAttribute("data-min"));
        const nmax = parseNumber(canvas.getAttribute("data-max"));

        // dataset
        const datasets = [
          {
            label: label,
            data: values,
            borderWidth: 2,
            tension: 0.25,
            pointRadius: 2,
          },
        ];

        // "reference" datasets for min/max (simple lines)
        // These will appear as additional series if values provided.
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

        // eslint-disable-next-line no-new
        new window.Chart(canvas.getContext("2d"), {
          type,
          data: {
            labels,
            datasets,
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
              legend: { display: true },
              tooltip: {
                callbacks: {
                  label: function (ctx) {
                    const v = ctx.parsed.y;
                    const s = `${ctx.dataset.label}: ${formatNumber(v, 2)}`;
                    return s;
                  },
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
        // silently ignore chart errors
        console.warn("Chart init error:", err);
      }
    });
  }

  // ----------------------------
  // Small UX sugar: copy-to-clipboard
  // Elements with data-copy="text" or data-copy-target="#id"
  // ----------------------------
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

      if (!text) return;

      try {
        await navigator.clipboard.writeText(text);
        el.setAttribute("data-tip", "Скопировано!");
      } catch {
        // fallback
        const tmp = document.createElement("textarea");
        tmp.value = text;
        document.body.appendChild(tmp);
        tmp.select();
        document.execCommand("copy");
        tmp.remove();
        el.setAttribute("data-tip", "Скопировано!");
      }
    });
  }

  // ----------------------------
  // Init
  // ----------------------------
  document.addEventListener("DOMContentLoaded", () => {
    initFlash();
    initConfirms();
    initAutoSubmitFilters();
    initNumericInputs();
    initTooltips();
    initCharts();
    initCopyButtons();
  });

  // expose minimal helpers if needed in templates
  window.AppUI = {
    debounce,
    formatNumber,
    parseNumber,
    escapeHtml,
  };
})();
