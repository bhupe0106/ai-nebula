/* ==========================================================================
   Nebula — global UI behaviour
   Sidebar, toasts, dialogs, confirms, copy buttons, uploads, small shortcuts.
   ========================================================================== */
(() => {
  "use strict";

  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));

  /* ------------------------------------------------------------------ utils */
  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[2]) : "";
  }

  function isTypingTarget(target) {
    if (!target) return false;
    const tag = target.tagName;
    return (
      tag === "INPUT" ||
      tag === "TEXTAREA" ||
      tag === "SELECT" ||
      target.isContentEditable
    );
  }

  /* ----------------------------------------------------------------- toasts */
  const ICONS = { success: "i-check", error: "i-alert", warning: "i-alert", info: "i-spark" };

  function buildToast(message, kind = "info") {
    const el = document.createElement("div");
    el.className = `toast toast-${kind}`;
    el.setAttribute("role", "status");
    el.dataset.toast = "";
    el.innerHTML = `
      <span class="toast-icon"><svg class="icon"><use href="#${ICONS[kind] || ICONS.info}"></use></svg></span>
      <p></p>
      <button type="button" class="toast-close" data-toast-close aria-label="Dismiss">
        <svg class="icon"><use href="#i-close"></use></svg>
      </button>`;
    el.querySelector("p").textContent = message;
    return el;
  }

  function dismissToast(el) {
    if (!el || el.classList.contains("is-leaving")) return;
    el.classList.add("is-leaving");
    window.setTimeout(() => el.remove(), 320);
  }

  function toast(message, kind = "info") {
    if (!message) return;
    const stack = $("#js-toast-stack") || $(".toast-stack");
    if (!stack) return;
    const el = buildToast(message, kind);
    stack.appendChild(el);
    window.setTimeout(() => dismissToast(el), kind === "error" ? 7000 : 5200);
  }

  window.nebula = Object.assign(window.nebula || {}, { toast });

  document.addEventListener("click", (event) => {
    const close = event.target.closest("[data-toast-close]");
    if (close) {
      event.preventDefault();
      dismissToast(close.closest("[data-toast]"));
    }
  });

  $$("[data-toast]").forEach((el) => {
    window.setTimeout(() => dismissToast(el), 5200);
  });

  /* --------------------------------------------------------------- sidebar */
  function setSidebar(open) {
    document.body.classList.toggle("sidebar-open", open);
    const overlay = $("#sidebar-overlay");
    if (overlay) overlay.setAttribute("aria-hidden", open ? "false" : "true");
  }

  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-sidebar-toggle]")) {
      event.preventDefault();
      setSidebar(true);
    }
    if (event.target.closest("[data-sidebar-close]") || event.target.id === "sidebar-overlay") {
      setSidebar(false);
    }
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 1023) setSidebar(false);
  });

  /* ---------------------------------------------------------------- dialogs */
  function openDialog(id) {
    const dialog = document.getElementById(id);
    if (!dialog) return;
    if (typeof dialog.showModal === "function") {
      if (!dialog.open) dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
  }

  function closeDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  document.addEventListener("click", (event) => {
    const opener = event.target.closest("[data-open-dialog]");
    if (opener) {
      event.preventDefault();
      openDialog(opener.dataset.openDialog);
      return;
    }
    const closer = event.target.closest("[data-close-dialog]");
    if (closer) {
      event.preventDefault();
      closeDialog(closer.closest("dialog"));
      return;
    }
    if (event.target.matches("dialog.modal")) {
      closeDialog(event.target);
    }
  });

  /* ---------------------------------------------------------------- confirm */
  let confirmResolver = null;

  function finishConfirm(value) {
    const dialog = document.getElementById("confirm-dialog");
    if (dialog && dialog.open) dialog.close();
    if (confirmResolver) {
      const resolve = confirmResolver;
      confirmResolver = null;
      resolve(value);
    }
  }

  function askConfirm(message) {
    const dialog = document.getElementById("confirm-dialog");
    if (!dialog) return Promise.resolve(window.confirm(message));
    const text = dialog.querySelector("#confirm-message");
    if (text) text.textContent = message || "Are you sure?";
    if (!dialog.open) dialog.showModal();
    return new Promise((resolve) => {
      confirmResolver = resolve;
    });
  }

  (() => {
    const dialog = document.getElementById("confirm-dialog");
    if (!dialog) return;
    const ok = dialog.querySelector("[data-confirm-ok]");
    const cancel = dialog.querySelector("[data-confirm-cancel]");
    if (ok) ok.addEventListener("click", () => finishConfirm(true));
    if (cancel) cancel.addEventListener("click", () => finishConfirm(false));
    dialog.addEventListener("close", () => {
      if (confirmResolver) {
        const resolve = confirmResolver;
        confirmResolver = null;
        resolve(false);
      }
    });
  })();

  // Forms that need a confirmation before a normal (or htmx) submit.
  document.addEventListener(
    "submit",
    (event) => {
      const form = event.target.closest("form[data-confirm-form]");
      if (!form || form.dataset.confirmed === "true") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      askConfirm(form.dataset.confirmForm).then((ok) => {
        if (!ok) return;
        form.dataset.confirmed = "true";
        if (typeof form.requestSubmit === "function") form.requestSubmit();
        else form.submit();
        window.setTimeout(() => delete form.dataset.confirmed, 0);
      });
    },
    true
  );

  // Click-driven confirmations (htmx buttons).
  document.addEventListener(
    "click",
    (event) => {
      const el = event.target.closest("[data-confirm]");
      if (!el || el.dataset.confirmed === "true") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      askConfirm(el.dataset.confirm).then((ok) => {
        if (!ok) return;
        el.dataset.confirmed = "true";
        el.click();
        window.setTimeout(() => delete el.dataset.confirmed, 0);
      });
    },
    true
  );

  /* ------------------------------------------------------------ copy button */
  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand("copy");
    } finally {
      area.remove();
    }
  }

  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-copy-selector]");
    if (!button) return;
    event.preventDefault();
    const target = document.querySelector(button.dataset.copySelector);
    const text = target ? target.innerText.trim() : "";
    if (!text) return;
    try {
      await copyText(text);
      button.classList.add("is-copied");
      const use = button.querySelector("use");
      const previous = use ? use.getAttribute("href") : null;
      if (use) use.setAttribute("href", "#i-check");
      toast("Copied to clipboard.", "success");
      window.setTimeout(() => {
        button.classList.remove("is-copied");
        if (use && previous) use.setAttribute("href", previous);
      }, 1600);
    } catch (error) {
      toast("Could not copy. Select the text manually.", "error");
    }
  });

  /* -------------------------------------------------------------- textareas */
  function autoGrow(el) {
    if (!el) return;
    el.style.height = "auto";
    const max = 176;
    el.style.height = Math.min(el.scrollHeight, max) + "px";
    el.style.overflowY = el.scrollHeight > max ? "auto" : "hidden";
  }

  document.addEventListener("input", (event) => {
    if (event.target.matches("[data-composer-input]")) autoGrow(event.target);
  });
  $$("[data-composer-input]").forEach(autoGrow);

  /* --------------------------------------------------------------- dropzone */
  $$(".dropzone").forEach((zone) => {
    const form = zone.closest("form");
    const input = zone.querySelector('input[type="file"]') || (form && form.querySelector('input[type="file"]'));
    if (!input) return;

    ["dragenter", "dragover"].forEach((type) =>
      zone.addEventListener(type, (event) => {
        event.preventDefault();
        zone.classList.add("is-dragover");
      })
    );
    ["dragleave", "dragend"].forEach((type) =>
      zone.addEventListener(type, () => zone.classList.remove("is-dragover"))
    );
    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      zone.classList.remove("is-dragover");
      const files = event.dataTransfer && event.dataTransfer.files;
      if (!files || !files.length) return;
      input.files = files;
      if (form) {
        if (typeof form.requestSubmit === "function") form.requestSubmit();
        else form.submit();
      }
    });
  });

  document.addEventListener("change", (event) => {
    const input = event.target.closest("[data-auto-upload]");
    if (!input) return;
    const form = input.form;
    if (!form) return;
    const feedback = document.querySelector("[data-upload-feedback]");
    if (feedback) feedback.innerHTML = "";
    if (typeof form.requestSubmit === "function") form.requestSubmit();
    else form.submit();
  });

  /* ------------------------------------------------------------- htmx glue */
  document.body.addEventListener("htmx:configRequest", (event) => {
    event.detail.headers["X-CSRFToken"] = getCookie("csrftoken");
  });

  document.body.addEventListener("htmx:responseError", (event) => {
    const html = event.detail.xhr && event.detail.xhr.responseText;
    const feedback = document.querySelector("[data-upload-feedback]");
    if (feedback && html && html.indexOf("upload-error") !== -1) {
      feedback.innerHTML = html;
      window.setTimeout(() => {
        feedback.innerHTML = "";
      }, 7000);
      return;
    }
    toast("The request failed. Please try again.", "error");
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    const list = document.getElementById("doc-list");
    if (list && list.querySelector(".doc-row")) {
      const empty = list.querySelector("[data-doc-empty]");
      if (empty) empty.remove();
    }
    if (event.detail && event.detail.target) {
      $$("[data-composer-input]", event.detail.target).forEach(autoGrow);
    }
  });

  /* ------------------------------------------------------- pointer spotlight */
  document.addEventListener("mousemove", (event) => {
    const card = event.target.closest(".conversation-card");
    if (!card) return;
    const rect = card.getBoundingClientRect();
    card.style.setProperty("--mx", `${event.clientX - rect.left}px`);
    card.style.setProperty("--my", `${event.clientY - rect.top}px`);
  });

  /* --------------------------------------------------------------- shortcuts */
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setSidebar(false);
      return;
    }
    if (isTypingTarget(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;

    if (event.key === "/") {
      const search = document.getElementById("conversation-search");
      if (search) {
        event.preventDefault();
        search.focus();
        search.select();
      }
      return;
    }

    if (event.key.toLowerCase() === "n") {
      const form = document.querySelector(".sidebar-new form");
      if (form) {
        event.preventDefault();
        if (typeof form.requestSubmit === "function") form.requestSubmit();
        else form.submit();
      }
    }
  });

  /* ------------------------------------------------------------- range sync */
  document.addEventListener("input", (event) => {
    if (!event.target.matches("[data-temp-range]")) return;
    const output = event.target.closest(".range-row")?.querySelector("[data-temp-value]");
    if (output) output.textContent = Number(event.target.value).toFixed(1);
  });
})();
