/* ==========================================================================
   Nebula — streaming chat client
   WebSocket protocol: ready | turn_start | token | done | error | pong
   Falls back to the regular HTTP form when the socket is unavailable.
   ========================================================================== */
(() => {
  "use strict";

  const root = document.querySelector("[data-conversation-id]");
  if (!root) return;

  const conversationId = root.dataset.conversationId;
  const initials = root.dataset.userInitials || "You";
  const body = document.getElementById("chat-body");
  const list = document.getElementById("message-list");
  const form = document.getElementById("composer-form");
  const input = document.getElementById("composer-input");
  const status = document.getElementById("ws-status");
  const statusText = document.getElementById("ws-status-text");
  const stopBtn = document.querySelector("[data-stop]");
  const attachBtn = document.querySelector("[data-attach]");
  const titleEl = document.querySelector("[data-chat-title]");

  if (!body || !list || !form || !input) return;

  const toast = (message, kind) => {
    if (window.nebula && typeof window.nebula.toast === "function") {
      window.nebula.toast(message, kind);
    }
  };

  let socket = null;
  let ready = false;
  let busy = false;
  let userStopped = false;
  let stream = null;
  let streamText = null;
  let attempts = 0;
  let heartbeat = null;
  let reconnectTimer = null;
  let closedByUs = false;

  /* --------------------------------------------------------------- status */
  function setStatus(state, label) {
    if (!status) return;
    status.classList.remove("is-online", "is-offline");
    if (state) status.classList.add(state);
    if (statusText) statusText.textContent = label;
  }

  function setStreaming(on) {
    form.classList.toggle("is-streaming", on);
    if (stopBtn) stopBtn.disabled = false;
    if (on) setStatus("", "Streaming…");
  }

  /* ----------------------------------------------------------------- socket */
  function socketUrl() {
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    return `${scheme}://${window.location.host}/ws/chat/${conversationId}/`;
  }

  function connect() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    closedByUs = false;
    setStatus("", "Connecting…");

    try {
      socket = new WebSocket(socketUrl());
    } catch (error) {
      setStatus("is-offline", "Offline — HTTP fallback");
      return;
    }

    socket.addEventListener("open", () => {
      attempts = 0;
      setStatus("", "Connecting…");
    });

    socket.addEventListener("message", (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (error) {
        return;
      }
      handleEvent(data);
    });

    socket.addEventListener("close", () => {
      ready = false;
      window.clearInterval(heartbeat);
      heartbeat = null;
      setStatus("is-offline", "Offline — retrying…");
      if (busy) {
        abortStream("The connection dropped. Your partial reply was kept — try sending again.");
        busy = false;
        setStreaming(false);
      }
      if (!closedByUs) scheduleReconnect();
    });

    socket.addEventListener("error", () => {
      // The close handler performs the retry bookkeeping.
    });
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    const delay = Math.min(1000 * Math.pow(1.7, attempts), 15000);
    attempts += 1;
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, delay);
  }

  function startHeartbeat() {
    window.clearInterval(heartbeat);
    heartbeat = window.setInterval(() => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ action: "ping" }));
      }
    }, 25000);
  }

  function sendRaw(payload) {
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify(payload));
    return true;
  }

  /* -------------------------------------------------------------- rendering */
  function scrollToBottom(force = true) {
    if (!force) {
      const nearBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 160;
      if (!nearBottom) return;
    }
    window.requestAnimationFrame(() => {
      body.scrollTop = body.scrollHeight;
    });
  }

  function removeEmptyState() {
    const empty = list.querySelector("[data-chat-empty]");
    if (empty) empty.remove();
  }

  function addOptimisticUser(text) {
    removeEmptyState();
    const el = document.createElement("article");
    el.className = "message message-user";
    el.dataset.optimistic = "true";
    el.innerHTML = `
      <div class="message-avatar" aria-hidden="true"></div>
      <div class="message-body">
        <div class="message-head">
          <span class="message-author">You</span>
          <span class="message-time">Now</span>
        </div>
        <div class="prose-chat"></div>
      </div>`;
    el.querySelector(".message-avatar").textContent = initials;
    el.querySelector(".prose-chat").textContent = text;
    list.appendChild(el);
    scrollToBottom();
  }

  function removeOptimistic() {
    list.querySelectorAll("[data-optimistic]").forEach((el) => el.remove());
  }

  function ensureStream() {
    if (stream && document.body.contains(stream)) return stream;
    removeEmptyState();
    const el = document.createElement("article");
    el.className = "message message-assistant is-streaming";
    el.dataset.streaming = "true";
    el.innerHTML = `
      <div class="message-avatar" aria-hidden="true">
        <svg class="icon"><use href="#i-spark"></use></svg>
      </div>
      <div class="message-body">
        <div class="message-head">
          <span class="message-author">Nebula</span>
          <span class="message-time">Now</span>
        </div>
        <div class="prose-chat">
          <span class="typing-dots" data-typing><span></span><span></span><span></span></span>
          <span data-stream-text></span><span class="streaming-caret" data-caret></span>
        </div>
      </div>`;
    list.appendChild(el);
    stream = el;
    streamText = el.querySelector("[data-stream-text]");
    scrollToBottom();
    return el;
  }

  function appendToken(text) {
    ensureStream();
    const typing = stream.querySelector("[data-typing]");
    if (typing) typing.remove();
    if (streamText) streamText.appendChild(document.createTextNode(text));
    scrollToBottom(false);
  }

  function settleStream(html) {
    if (!stream) return;
    const current = stream;
    stream = null;
    streamText = null;
    if (html) {
      const holder = document.createElement("div");
      holder.innerHTML = html.trim();
      const replacement = holder.firstElementChild;
      if (replacement) {
        current.replaceWith(replacement);
        scrollToBottom(false);
        return;
      }
    }
    current.classList.remove("is-streaming");
    const caret = current.querySelector("[data-caret]");
    if (caret) caret.remove();
  }

  function abortStream(message) {
    if (!stream) return;
    const current = stream;
    stream = null;
    streamText = null;
    current.classList.remove("is-streaming");
    const caret = current.querySelector("[data-caret]");
    if (caret) caret.remove();
    const typing = current.querySelector("[data-typing]");
    if (typing) typing.remove();
    if (message) {
      const note = document.createElement("div");
      note.className = "message-error-note";
      note.innerHTML = `<svg class="icon"><use href="#i-alert"></use></svg><span></span>`;
      note.querySelector("span").textContent = message;
      const messageBody = current.querySelector(".message-body") || current;
      messageBody.appendChild(note);
    }
  }

  /* ------------------------------------------------------------------ quota */
  function formatter(value) {
    return Number(value || 0).toLocaleString();
  }

  function updateQuota(quota) {
    if (!quota) return;
    const percent = quota.unlimited ? 100 : quota.percent || 0;
    document.querySelectorAll(".quota-fill").forEach((el) => {
      el.style.width = `${percent}%`;
    });

    const sidebarValue = document.querySelector(".sidebar-foot .quota-value");
    if (sidebarValue) {
      sidebarValue.innerHTML = quota.unlimited
        ? "Unlimited"
        : `${formatter(quota.used)}<span class="muted"> / ${formatter(quota.quota)}</span>`;
    }

    const sidebarNote = document.querySelector(".sidebar-foot .quota-note");
    if (sidebarNote) {
      if (quota.unlimited) sidebarNote.textContent = "No token limit on this account.";
      else if (quota.exceeded) sidebarNote.textContent = "Limit reached — wait for the monthly reset.";
      else sidebarNote.textContent = `${formatter(quota.remaining)} tokens left this month.`;
    }

    const hint = document.querySelector(".composer-hint .hint-right");
    if (hint) {
      hint.innerHTML = quota.unlimited
        ? '<svg class="icon"><use href="#i-shield"></use></svg> Unlimited tokens'
        : `<svg class="icon"><use href="#i-shield"></use></svg> ${formatter(quota.remaining)} tokens left`;
    }
  }

  function setTitle(title) {
    if (!title) return;
    if (titleEl) titleEl.textContent = title;
    document.title = `${title} — Nebula`;
    const active = document.querySelector(".conversation-item.is-active .conversation-title");
    if (active) active.textContent = title;
  }

  /* ------------------------------------------------------------- ws events */
  function handleEvent(data) {
    switch (data.type) {
      case "ready":
        ready = true;
        setStatus("is-online", "Online");
        startHeartbeat();
        updateQuota(data.quota);
        break;

      case "turn_start":
        removeOptimistic();
        if (data.user_html) list.insertAdjacentHTML("beforeend", data.user_html);
        setTitle(data.title);
        ensureStream();
        scrollToBottom();
        break;

      case "token":
        appendToken(data.content || "");
        break;

      case "done":
        busy = false;
        userStopped = false;
        settleStream(data.html || "");
        setStreaming(false);
        setStatus("is-online", "Online");
        updateQuota(data.quota);
        if (data.error) toast(data.error, "error");
        input.focus();
        scrollToBottom();
        break;

      case "error":
        busy = false;
        removeOptimistic();
        if (stream && !(streamText && streamText.textContent)) {
          stream.remove();
          stream = null;
          streamText = null;
        } else if (stream) {
          abortStream(data.message || "The reply was interrupted.");
        }
        setStreaming(false);
        if (data.code === "quota") rejectTitle();
        toast(data.message || "The assistant could not answer.", "error");
        break;

      case "pong":
        break;

      default:
        break;
    }
  }

  function rejectTitle() {
    setStatus("is-offline", "Quota reached");
  }

  /* ------------------------------------------------------------------- send */
  function resetComposer() {
    input.value = "";
    input.style.height = "auto";
    input.focus();
  }

  function submitTurn(text) {
    const clean = (text || "").trim();
    if (!clean || busy) return;

    if (!socket || socket.readyState !== WebSocket.OPEN) {
      // Graceful fallback to the no-JavaScript endpoint.
      input.value = clean;
      HTMLFormElement.prototype.submit.call(form);
      return;
    }

    busy = true;
    userStopped = false;
    setStreaming(true);
    addOptimisticUser(clean);
    resetComposer();
    if (!sendRaw({ action: "send", message: clean })) {
      busy = false;
      setStreaming(false);
      HTMLFormElement.prototype.submit.call(form);
    }
  }

  form.addEventListener("submit", (event) => {
    const text = input.value.trim();
    if (!text) {
      event.preventDefault();
      return;
    }
    if (socket && socket.readyState === WebSocket.OPEN) {
      event.preventDefault();
      submitTurn(text);
    }
    // Otherwise the browser performs a normal POST to the HTTP fallback view.
  });

  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    if (typeof form.requestSubmit === "function") form.requestSubmit();
    else form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
  });

  if (stopBtn) {
    stopBtn.addEventListener("click", () => {
      if (!busy) return;
      userStopped = true;
      stopBtn.disabled = true;
      sendRaw({ action: "stop" });
    });
  }

  /* --------------------------------------------------------------- suggestions */
  document.addEventListener("click", (event) => {
    const suggestion = event.target.closest("[data-suggestion]");
    if (!suggestion) return;
    event.preventDefault();
    input.value = suggestion.dataset.suggestion || "";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.focus();
  });

  /* ------------------------------------------------------------------- attach */
  if (attachBtn) {
    attachBtn.addEventListener("click", (event) => {
      event.preventDefault();
      const fileInput = document.getElementById("doc-file-input");
      const asideVisible = window.innerWidth > 1280;
      if (fileInput && asideVisible) {
        fileInput.click();
      } else if (attachBtn.dataset.libraryUrl) {
        window.location.href = attachBtn.dataset.libraryUrl;
      }
    });
  }

  /* ------------------------------------------------------------------- boot */
  window.addEventListener("beforeunload", () => {
    closedByUs = true;
    if (socket) socket.close();
  });

  connect();
})();
