(() => {
  const form = document.querySelector("[data-chat-form]");
  const input = document.querySelector("[data-chat-input]");
  const list = document.querySelector("[data-message-list]");
  const welcome = document.querySelector("[data-welcome]");
  const sidebar = document.querySelector(".sidebar");
  const menuToggle = document.querySelector("[data-menu-toggle]");
  const historyNav = document.querySelector("[data-chat-history]");
  const historyEmpty = document.querySelector("[data-history-empty]");
  const status = document.querySelector("[data-chat-status]");
  const sendButton = document.querySelector("[data-send-button]");
  const userLabel = document.querySelector("[data-user-label]");
  const userAvatar = document.querySelector("[data-user-avatar]");
  const loginLink = document.querySelector("[data-login-link]");
  const logoutButton = document.querySelector("[data-logout-button]");

  if (!form || !input || !list) return;

  // Same limits as POST /api/chat (strip, 1..1000 chars).
  const MAX_LENGTH = 1000;
  const HISTORY_LIMIT = 30;
  const SIDEBAR_LIMIT = 20;
  const NETWORK_ERROR = "서버에 연결할 수 없습니다. FastAPI 서버에서 페이지를 열었는지 확인해 주세요.";
  const errorMessages = {
    AI_TIMEOUT: "응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요.",
    AI_ERROR: "AI 답변을 받지 못했어요. 잠시 후 다시 시도해 주세요.",
    AI_NOT_CONFIGURED: "AI 연결 설정이 아직 준비되지 않았어요. 관리자에게 알려 주세요.",
    DB_UNAVAILABLE: "서버 저장소에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.",
    VALIDATION_ERROR: `질문은 공백을 제외하고 1자 이상 ${MAX_LENGTH}자 이하로 입력해 주세요.`,
  };

  let history = [];
  let sending = false;

  const setStatus = (text, isError = false) => {
    if (!status) return;
    status.textContent = text;
    status.classList.toggle("is-error", isError);
  };

  const goToLogin = () => window.location.assign("/auth");

  const readResponse = async (response) => {
    if (response.status === 204) return null;
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(body.message || "요청을 처리하지 못했습니다.");
      error.status = response.status;
      error.code = body.error;
      throw error;
    }
    return body;
  };

  const describeError = (error) => {
    if (error instanceof TypeError) return NETWORK_ERROR;
    return errorMessages[error.code] || error.message || "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
  };

  const formatTime = (value) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("ko-KR");
  };

  const scrollToBottom = () => {
    list.lastElementChild?.scrollIntoView({ block: "end" });
  };

  // User and AI text always goes through textContent, never innerHTML.
  const addMessage = (text, role, options = {}) => {
    const item = document.createElement("div");
    item.className = `message message-${role}`;
    item.textContent = text;
    if (options.id != null) item.id = `chat-${options.id}`;
    if (options.time) item.title = formatTime(options.time);
    list.append(item);
    if (welcome) welcome.hidden = true;
    return item;
  };

  const addNote = (text) => {
    const note = document.createElement("p");
    note.className = "message-note";
    note.textContent = text;
    list.append(note);
    return note;
  };

  const renderSidebar = () => {
    if (!historyNav) return;
    historyNav.querySelectorAll(".history-item").forEach((item) => item.remove());
    const recent = history.slice(-SIDEBAR_LIMIT).reverse();
    recent.forEach((chat) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "history-item";
      button.textContent = chat.question;
      button.title = formatTime(chat.created_at);
      button.addEventListener("click", () => showChat(chat.id));
      historyNav.append(button);
    });
    if (historyEmpty) historyEmpty.hidden = recent.length > 0;
  };

  const renderHistory = () => {
    list.replaceChildren();
    history.forEach((chat) => {
      addMessage(chat.question, "user", { id: chat.id, time: chat.created_at });
      addMessage(chat.answer, "assistant", { time: chat.created_at });
    });
    if (welcome) welcome.hidden = history.length > 0;
  };

  const showChat = (id) => {
    if (!document.getElementById(`chat-${id}`)) renderHistory();
    document.getElementById(`chat-${id}`)?.scrollIntoView({ block: "start", behavior: "smooth" });
    closeSidebar();
  };

  const loadHistory = async () => {
    // Sending waits for the history so the two never overlap on screen.
    setSending(true);
    try {
      const response = await fetch(`/api/me/chats?limit=${HISTORY_LIMIT}`, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const body = await readResponse(response);
      history = Array.isArray(body?.items) ? body.items : [];
      renderHistory();
      renderSidebar();
      scrollToBottom();
    } catch (error) {
      if (error.status === 401) {
        goToLogin();
        return;
      }
      setStatus(`이전 대화를 불러오지 못했어요. ${describeError(error)}`, true);
    } finally {
      setSending(false);
    }
  };

  const loadCurrentUser = async () => {
    try {
      const response = await fetch("/api/me", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const user = await readResponse(response);
      const name = user.email.split("@")[0];
      if (userLabel) userLabel.textContent = name;
      if (userAvatar) userAvatar.textContent = name.charAt(0).toUpperCase();
      if (loginLink) loginLink.hidden = true;
      if (logoutButton) logoutButton.hidden = false;
    } catch (error) {
      if (error.status === 401) {
        goToLogin();
        return;
      }
      console.info("Could not load the current session.", error.message);
    }
  };

  logoutButton?.addEventListener("click", async () => {
    logoutButton.disabled = true;
    try {
      const response = await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
      // 401 means the session has already expired, so the user is logged out either way.
      if (response.status !== 401) await readResponse(response);
      goToLogin();
    } catch (error) {
      logoutButton.disabled = false;
      window.alert(describeError(error));
    }
  });

  const setSending = (value) => {
    sending = value;
    if (sendButton) sendButton.disabled = value;
    form.setAttribute("aria-busy", String(value));
    document.querySelectorAll("[data-suggestion]").forEach((button) => { button.disabled = value; });
  };

  // Python counts code points, so count them the same way (emoji are 1 char, not 2).
  const countChars = (value) => [...value].length;

  const resizeInput = () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
  };

  const submitMessage = async (text) => {
    if (sending) return;
    const value = text.trim();
    if (!value) {
      setStatus("질문을 입력해 주세요.", true);
      input.focus();
      return;
    }
    const length = countChars(value);
    if (length > MAX_LENGTH) {
      setStatus(`질문은 ${MAX_LENGTH}자 이하로 입력해 주세요. (지금 ${length}자)`, true);
      input.focus();
      return;
    }

    setStatus("");
    addMessage(value, "user");
    input.value = "";
    resizeInput();
    const pending = addMessage("답변을 준비하고 있어요…", "assistant");
    pending.classList.add("is-pending");
    pending.setAttribute("aria-busy", "true");
    scrollToBottom();
    setSending(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ message: value }),
      });
      const chat = await readResponse(response);
      pending.classList.remove("is-pending");
      pending.removeAttribute("aria-busy");
      pending.textContent = chat.answer;
      pending.title = formatTime(chat.created_at);
      if (chat.saved && chat.id != null) {
        pending.previousElementSibling?.setAttribute("id", `chat-${chat.id}`);
        history.push({ id: chat.id, question: chat.question, answer: chat.answer, created_at: chat.created_at });
        renderSidebar();
      } else {
        addNote("이 대화는 저장되지 않았어요. 새로고침하면 기록에 보이지 않습니다.");
      }
    } catch (error) {
      if (error.status === 401) {
        goToLogin();
        return;
      }
      pending.remove();
      addMessage(describeError(error), "error");
      if (error.code === "VALIDATION_ERROR") setStatus(errorMessages.VALIDATION_ERROR, true);
      // Put the question back so it can be sent again.
      if (!input.value) {
        input.value = value;
        resizeInput();
      }
    } finally {
      setSending(false);
      scrollToBottom();
      input.focus();
    }
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitMessage(input.value);
  });

  input.addEventListener("input", () => {
    resizeInput();
    if (status?.classList.contains("is-error")) setStatus("");
  });

  input.addEventListener("keydown", (event) => {
    // Enter that confirms a Korean IME composition must not send the message.
    if (event.isComposing || event.keyCode === 229) return;
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  document.querySelectorAll("[data-suggestion]").forEach((button) => {
    button.addEventListener("click", () => submitMessage(button.dataset.suggestion || ""));
  });

  // Only clears the screen; saved chats stay in the sidebar.
  document.querySelector("[data-new-chat]")?.addEventListener("click", () => {
    list.replaceChildren();
    if (welcome) welcome.hidden = false;
    input.value = "";
    resizeInput();
    setStatus("");
    closeSidebar();
    input.focus();
  });

  function setSidebarOpen(open) {
    sidebar?.classList.toggle("is-open", open);
    menuToggle?.setAttribute("aria-expanded", String(open));
    menuToggle?.setAttribute("aria-label", open ? "대화 메뉴 닫기" : "대화 메뉴 열기");
  }

  function closeSidebar() {
    if (sidebar?.classList.contains("is-open")) setSidebarOpen(false);
  }

  menuToggle?.addEventListener("click", () => {
    setSidebarOpen(!sidebar?.classList.contains("is-open"));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && sidebar?.classList.contains("is-open")) {
      setSidebarOpen(false);
      menuToggle?.focus();
    }
  });

  document.addEventListener("click", (event) => {
    if (!sidebar?.classList.contains("is-open")) return;
    if (sidebar.contains(event.target) || menuToggle?.contains(event.target)) return;
    setSidebarOpen(false);
  });

  loadCurrentUser();
  loadHistory();
})();
