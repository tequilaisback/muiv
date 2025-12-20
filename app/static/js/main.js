// app/static/js/main.js

(function () {
  "use strict";

  // ---------------------------
  // Утилита: безопасный querySelector
  // ---------------------------
  function $(sel, root) {
    return (root || document).querySelector(sel);
  }
  function $all(sel, root) {
    return Array.from((root || document).querySelectorAll(sel));
  }

  // ---------------------------
  // Автоскрытие flash-сообщений
  // ---------------------------
  const flashes = $all(".flash");
  if (flashes.length) {
    setTimeout(() => {
      flashes.forEach((el) => {
        el.style.transition = "opacity .35s ease, transform .35s ease";
        el.style.opacity = "0";
        el.style.transform = "translateY(-6px)";
        setTimeout(() => el.remove(), 400);
      });
    }, 4500);
  }

  // ---------------------------
  // Подтверждение опасных действий
  // (кнопки/формы с data-confirm)
  // ---------------------------
  $all("[data-confirm]").forEach((el) => {
    el.addEventListener("click", (e) => {
      const msg = el.getAttribute("data-confirm") || "Подтвердить действие?";
      if (!window.confirm(msg)) {
        e.preventDefault();
        e.stopPropagation();
      }
    });
  });

  // ---------------------------
  // Мелкая UX штука:
  // в поисковой строке /search -> Enter отправляет форму
  // ---------------------------
  const searchForm = $("#searchForm");
  if (searchForm) {
    const input = $("#searchInput", searchForm);
    if (input) {
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          // на всякий случай: предотвращаем лишние переносы в мобильных
          e.preventDefault();
          searchForm.submit();
        }
      });
    }
  }

  // ---------------------------
  // Быстрый фильтр по категории в каталоге (если есть select)
  // ---------------------------
  const categorySelect = $("#categorySelect");
  if (categorySelect) {
    categorySelect.addEventListener("change", () => {
      const val = categorySelect.value || "";
      const url = new URL(window.location.href);
      if (val) url.searchParams.set("category_id", val);
      else url.searchParams.delete("category_id");
      window.location.href = url.toString();
    });
  }
})();
