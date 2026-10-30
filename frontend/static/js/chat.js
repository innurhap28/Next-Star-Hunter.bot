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
  const menuButton = document.querySelector("[data-user-menu-button]");
  const userMenu = document.querySelector("[data-user-menu]");
  const userEmail = document.querySelector("[data-user-email]");
  const adminLink = document.querySelector("[data-admin-link]");
  const menuLogout = document.querySelector("[data-menu-logout]");
  const layout = document.querySelector(".chat-layout");
  const resizer = document.querySelector("[data-sidebar-resizer]");
  const scroller = list?.closest(".conversation") || list?.parentElement;

  if (!form || !input || !list) return;

  // Same limits as POST /api/chat (strip, 1..1000 chars).
  const MAX_LENGTH = 1000;
  // GET /api/me/conversations allows 1..100; titles are cut at 40 chars like the server.
  const CONVERSATION_LIMIT = 50;
  const TITLE_LENGTH = 40;
  const LAST_CONVERSATION_KEY = "nsh.lastConversation";
  const NETWORK_ERROR = "서버에 연결할 수 없습니다. FastAPI 서버에서 페이지를 열었는지 확인해 주세요.";
  const errorMessages = {
    AI_TIMEOUT: "현재 응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요.",
    AI_ERROR: "AI 답변을 받지 못했어요. 잠시 후 다시 시도해 주세요.",
    AI_NOT_CONFIGURED: "AI 연결 설정이 아직 준비되지 않았어요. 관리자에게 알려 주세요.",
    DB_UNAVAILABLE: "서버 저장소에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.",
    VALIDATION_ERROR: `질문은 공백을 제외하고 1자 이상 ${MAX_LENGTH}자 이하로 입력해 주세요.`,
  };

  // While waiting for an answer, a spinner shows first; after this delay random texts take over.
  const LOADING_FIRST_DELAY = 3000;
  const LOADING_TEXT_INTERVAL = 3000;
  const LOADING_FADE = 350;

  // Same name as the profile (email part before @), filled in by loadCurrentUser.
  let displayName = userLabel?.textContent.trim() || "게스트";

  const loadingTexts = (name) => [
    "너는 승마장 출입 금지야. 너만 보면 말이 안 나와서…",
    "너 린스 안 써도 되겠다. 나만의 프린스니까.",
    "너 린스 안 써도 되겠다. 나만의 프린세스니까.",
    "이기자를 거꾸로 말하면 뭔지 알아?",
    `${name} 귀여울 때마다 벽 치다가 우리 집 원룸 됐어.`,
    "너 요즘 밴드한다며? 마이 허스밴드",
    `${name}은 물복임? 딱복임? 아니면 내 삶에 찾아온 행복이자 축복임?`,
    `너 굴 좋아해? 난 좋아해 ${name} 얼굴`,
    `${name} 때문에 비 올 것 같아. 내 심장마비.`,
    "너 타지에서 왔지? 내 마음을 흔드는 판타지.",
    `${name} 쿨톤이야 웜톤이야? 아니면 내 평생의 완주하지 못할 사랑의 마라톤이야?`,
  ];

  let conversations = [];
  const state = {
    busy: false,
    // Conversation shown in the message area; null means a new chat not saved yet.
    currentId: null,
    loadingTransitionTimer: null,
    loadingTipTimer: null,
    loadingTipIndex: -1,
  };

  const setStatus = (text, isError = false) => {
    if (!status) return;
    status.textContent = text;
    status.classList.toggle("is-error", isError);
  };

  // Another login replaces this session, so the next API call answers 401 SESSION_REPLACED.
  const goToLogin = (error) => {
    const replaced = error?.code === "SESSION_REPLACED";
    window.location.assign(replaced ? "/auth?reason=session_replaced" : "/auth");
  };

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
    const text = errorMessages[error.code] || error.message || "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
    return error.code ? `${text} (error: ${error.code})` : text;
  };

  const formatTime = (value) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("ko-KR");
  };

  // Only the message area scrolls, so moving its scrollTop never moves the page.
  const scrollToBottom = () => {
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
  };

  // 새로고침하면 브라우저가 이전 스크롤 위치를 되살리려 하는데, 기록이 다 그려지기 전에
  // 위치를 잡아서 대화 중간쯤에 멈추는 일이 있었다. 그래서 자동 복원은 끄고,
  // 처음 기록을 그린 뒤에는 레이아웃이 끝난 다음 차례(setTimeout 0)에 한 번 더 맨 아래로 내린다.
  if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
  let historyRestored = false;

  const restoreHistory = () => {
    scrollToBottom();
    if (historyRestored) return;
    historyRestored = true;
    setTimeout(() => scrollToBottom(), 0);
  };

  // The server puts "˗ˋˏ name ˎˊ˗" on the first line when it recommends a star.
  const TITLE_LINE = /^˗ˋˏ (.+) ˎˊ˗$/;

  // User and AI text always goes through textContent, never innerHTML.
  const setAnswer = (item, text) => {
    const value = String(text ?? "");
    const lineEnd = value.indexOf("\n");
    const firstLine = (lineEnd === -1 ? value : value.slice(0, lineEnd)).trim();
    const match = firstLine.match(TITLE_LINE);
    if (!match) {
      item.textContent = value;
      return;
    }
    const title = document.createElement("strong");
    title.className = "answer-title";
    title.textContent = firstLine;
    const body = document.createElement("span");
    body.className = "answer-body";
    body.textContent = lineEnd === -1 ? "" : value.slice(lineEnd + 1).replace(/^\s*\n/, "");
    item.replaceChildren(title, body);
  };

  const addMessage = (text, role, options = {}) => {
    const item = document.createElement("div");
    item.className = `message message-${role}`;
    if (role === "assistant") setAnswer(item, text);
    else item.textContent = text;
    if (options.chatId != null) item.dataset.chatId = String(options.chatId);
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

  // Remember which conversation was open so a reload reopens it.
  const remember = (id) => {
    try {
      if (id == null) window.localStorage.removeItem(LAST_CONVERSATION_KEY);
      else window.localStorage.setItem(LAST_CONVERSATION_KEY, String(id));
    } catch {
      // Storage can be blocked (private mode); the last conversation just is not remembered.
    }
  };

  const rememberedId = () => {
    try {
      const value = Number(window.localStorage.getItem(LAST_CONVERSATION_KEY));
      return Number.isInteger(value) && value > 0 ? value : null;
    } catch {
      return null;
    }
  };

  // "방금 전", "5분 전", "3시간 전", "2일 전", then the date.
  const formatRelative = (value) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const minutes = Math.floor((Date.now() - date.getTime()) / 60000);
    if (minutes < 1) return "방금 전";
    if (minutes < 60) return `${minutes}분 전`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}시간 전`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}일 전`;
    return date.toLocaleDateString("ko-KR");
  };

  // Same rule as the server: stripped message, first 40 chars + "…" if longer.
  const titleFrom = (message) => {
    const chars = [...message.trim()];
    return chars.length > TITLE_LENGTH ? `${chars.slice(0, TITLE_LENGTH).join("")}…` : chars.join("");
  };

  const getJson = async (url) => {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    return readResponse(response);
  };

  const renderConversations = () => {
    if (!historyNav) return;
    historyNav.querySelectorAll(".history-entry").forEach((item) => item.remove());
    conversations.forEach((conversation) => {
      const isCurrent = conversation.id === state.currentId;
      const entry = document.createElement("div");
      entry.className = "history-entry";
      entry.classList.toggle("is-current", isCurrent);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "history-item";
      if (isCurrent) button.setAttribute("aria-current", "true");
      button.title = `${conversation.title}\n${formatTime(conversation.updated_at)}`;
      const title = document.createElement("span");
      title.className = "history-title";
      title.textContent = conversation.title;
      const time = document.createElement("span");
      time.className = "history-time";
      time.textContent = formatRelative(conversation.updated_at);
      button.append(title, time);
      button.addEventListener("click", () => openConversation(conversation.id));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "history-delete";
      remove.textContent = "×";
      remove.setAttribute("aria-label", `"${conversation.title}" 대화방 삭제`);
      remove.title = "대화방 삭제";
      remove.addEventListener("click", () => deleteConversation(conversation.id, remove));
      entry.append(button, remove);
      historyNav.append(entry);
    });
    if (historyEmpty) historyEmpty.hidden = conversations.length > 0;
  };

  const loadConversations = async () => {
    const body = await getJson(`/api/me/conversations?limit=${CONVERSATION_LIMIT}`);
    conversations = Array.isArray(body?.items) ? body.items : [];
    renderConversations();
  };

  // Refresh the list without stopping the screen; errors only go to the status line.
  const refreshConversations = async () => {
    try {
      await loadConversations();
    } catch (error) {
      if (error.status === 401) {
        goToLogin(error);
        return;
      }
      setStatus(`대화 목록을 불러오지 못했어요. ${describeError(error)}`, true);
    }
  };

  // "새 대화": empty message area, no current conversation. The next question makes a new one.
  const startNewChat = () => {
    state.currentId = null;
    remember(null);
    list.replaceChildren();
    if (welcome) welcome.hidden = false;
    renderConversations();
  };

  // The conversation is gone (deleted in another tab, for example): reload the list and start over.
  const handleMissingConversation = async () => {
    startNewChat();
    await refreshConversations();
    setStatus("대화방을 찾을 수 없어 새 대화를 시작했어요.", true);
  };

  const openConversation = async (id) => {
    if (state.busy) return;
    closeSidebar();
    if (id === state.currentId && list.childElementCount > 0) return;
    // Sending waits for the chats so the two never overlap on screen.
    setSending(true);
    setStatus("");
    try {
      const body = await getJson(`/api/me/conversations/${encodeURIComponent(id)}/chats`);
      const items = Array.isArray(body?.items) ? body.items : [];
      state.currentId = id;
      remember(id);
      list.replaceChildren();
      items.forEach((chat) => {
        addMessage(chat.question, "user", { id: chat.id, chatId: chat.id, time: chat.created_at });
        addMessage(chat.answer, "assistant", { chatId: chat.id, time: chat.created_at });
      });
      if (welcome) welcome.hidden = items.length > 0;
      renderConversations();
      restoreHistory();
    } catch (error) {
      if (error.status === 401) {
        goToLogin(error);
        return;
      }
      if (error.code === "CONVERSATION_NOT_FOUND") {
        await handleMissingConversation();
        return;
      }
      setStatus(`대화를 불러오지 못했어요. ${describeError(error)}`, true);
    } finally {
      setSending(false);
    }
  };

  const deleteConversation = async (id, button) => {
    if (state.busy) return;
    if (!window.confirm("이 대화방을 삭제할까요? 안의 대화도 모두 지워지고 되돌릴 수 없습니다.")) return;
    button.disabled = true;
    try {
      const response = await fetch(`/api/me/conversations/${encodeURIComponent(id)}`, {
        method: "DELETE",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      await readResponse(response);
      conversations = conversations.filter((conversation) => conversation.id !== id);
      if (id === state.currentId) startNewChat();
      else renderConversations();
      setStatus("대화방을 삭제했어요.");
    } catch (error) {
      if (error.status === 401) {
        goToLogin(error);
        return;
      }
      button.disabled = false;
      if (error.status === 404) {
        // Already gone: show the current list again.
        if (id === state.currentId) startNewChat();
        await refreshConversations();
        setStatus("이미 삭제된 대화방이에요. 목록을 새로 불러왔어요.");
        return;
      }
      setStatus(`대화방을 삭제하지 못했어요. ${describeError(error)}`, true);
    }
  };

  // After an answer is saved: move (or add) its conversation to the top of the list.
  const touchConversation = (id, question, time) => {
    const found = conversations.find((conversation) => conversation.id === id);
    const conversation = found || { id, title: titleFrom(question), created_at: time, chat_count: 0 };
    conversation.updated_at = time;
    conversation.chat_count = (conversation.chat_count || 0) + 1;
    conversations = [conversation, ...conversations.filter((item) => item.id !== id)];
    renderConversations();
    // A new conversation gets its real title and times from the server.
    if (!found) refreshConversations();
  };

  // First screen: the last opened conversation if it still exists, else the most recent one.
  const loadInitialConversation = async () => {
    setSending(true);
    try {
      await loadConversations();
    } catch (error) {
      if (error.status === 401) {
        goToLogin(error);
        return;
      }
      setStatus(`대화 목록을 불러오지 못했어요. ${describeError(error)}`, true);
      return;
    } finally {
      setSending(false);
    }
    const saved = rememberedId();
    const target = conversations.find((conversation) => conversation.id === saved) || conversations[0];
    if (target) await openConversation(target.id);
    else startNewChat();
  };

  const loadCurrentUser = async () => {
    try {
      const response = await fetch("/api/me", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const user = await readResponse(response);
      const name = user.email.split("@")[0];
      displayName = name;
      if (userLabel) userLabel.textContent = name;
      if (userAvatar) userAvatar.textContent = name.charAt(0).toUpperCase();
      if (userEmail) userEmail.textContent = user.email;
      if (adminLink) adminLink.hidden = user.is_admin !== true;
      if (loginLink) loginLink.hidden = true;
      if (logoutButton) logoutButton.hidden = false;
    } catch (error) {
      if (error.status === 401) {
        goToLogin(error);
        return;
      }
      console.info("Could not load the current session.", error.message);
    }
  };

  const logOut = async (button) => {
    button.disabled = true;
    try {
      const response = await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
      // 401 means the session has already expired, so the user is logged out either way.
      if (response.status !== 401) await readResponse(response);
      goToLogin();
    } catch (error) {
      button.disabled = false;
      window.alert(describeError(error));
    }
  };

  logoutButton?.addEventListener("click", () => logOut(logoutButton));
  menuLogout?.addEventListener("click", () => logOut(menuLogout));

  // Account menu under the profile button.
  const menuItems = () => [...(userMenu?.querySelectorAll("[role=menuitem]") || [])].filter((item) => !item.hidden);
  const isMenuOpen = () => Boolean(userMenu && !userMenu.hidden);

  const setMenuOpen = (open, focusButton = false) => {
    if (!userMenu || !menuButton) return;
    userMenu.hidden = !open;
    menuButton.setAttribute("aria-expanded", String(open));
    if (open) menuItems()[0]?.focus();
    else if (focusButton) menuButton.focus();
  };

  menuButton?.addEventListener("click", () => setMenuOpen(!isMenuOpen()));

  menuButton?.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setMenuOpen(true);
      if (event.key === "ArrowUp") menuItems().at(-1)?.focus();
    }
  });

  userMenu?.addEventListener("keydown", (event) => {
    const items = menuItems();
    const index = items.indexOf(document.activeElement);
    let next = null;
    if (event.key === "ArrowDown") next = items[(index + 1) % items.length];
    else if (event.key === "ArrowUp") next = items[(index - 1 + items.length) % items.length];
    else if (event.key === "Home") next = items[0];
    else if (event.key === "End") next = items.at(-1);
    else if (event.key === "Tab") setMenuOpen(false);
    if (next) {
      event.preventDefault();
      next.focus();
    }
  });

  const setSending = (value) => {
    state.busy = value;
    if (sendButton) sendButton.disabled = value;
    form.setAttribute("aria-busy", String(value));
    document.querySelectorAll("[data-suggestion]").forEach((button) => { button.disabled = value; });
  };

  // Python counts code points, so count them the same way (emoji are 1 char, not 2).
  const countChars = (value) => [...value].length;

  const stopLoadingIndicator = () => {
    clearTimeout(state.loadingTransitionTimer);
    clearTimeout(state.loadingTipTimer);
    state.loadingTransitionTimer = null;
    state.loadingTipTimer = null;
  };

  // Pending answer row: spinner + "답변을 준비하고 있어요…", then random texts every 3 seconds.
  const startLoadingIndicator = (pending) => {
    stopLoadingIndicator();
    pending.classList.add("is-pending");
    pending.setAttribute("aria-busy", "true");
    pending.setAttribute("role", "status");
    pending.setAttribute("aria-live", "polite");
    const spinner = document.createElement("span");
    spinner.className = "loading-spinner";
    spinner.setAttribute("aria-hidden", "true");
    const message = document.createElement("span");
    message.className = "loading-text loading-message";
    message.textContent = "답변을 준비하고 있어요…";
    const tip = document.createElement("span");
    tip.className = "loading-text loading-tip";
    tip.hidden = true;
    pending.replaceChildren(spinner, message, tip);

    const texts = loadingTexts(displayName);
    let firstTip = true;
    state.loadingTipIndex = -1;

    const showRandomLoadingTip = () => {
      if (!state.busy) return;
      // Fade the current text out, then swap it while it is invisible.
      if (firstTip) message.classList.add("is-leaving");
      tip.classList.remove("is-visible");
      state.loadingTransitionTimer = setTimeout(() => {
        if (!state.busy) return;
        if (firstTip) message.hidden = true;
        firstTip = false;
        let index = Math.floor(Math.random() * texts.length);
        while (texts.length > 1 && index === state.loadingTipIndex) {
          index = Math.floor(Math.random() * texts.length);
        }
        state.loadingTipIndex = index;
        tip.textContent = texts[index];
        tip.hidden = false;
        requestAnimationFrame(() => tip.classList.add("is-visible"));
        state.loadingTipTimer = setTimeout(showRandomLoadingTip, LOADING_TEXT_INTERVAL);
      }, LOADING_FADE);
    };

    state.loadingTipTimer = setTimeout(showRandomLoadingTip, LOADING_FIRST_DELAY);
  };

  const finishLoadingIndicator = (pending) => {
    stopLoadingIndicator();
    pending.classList.remove("is-pending");
    pending.removeAttribute("aria-busy");
    pending.removeAttribute("role");
    pending.removeAttribute("aria-live");
  };

  const resizeInput = () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
  };

  const submitMessage = async (text) => {
    if (state.busy) return;
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
    const pending = addMessage("", "assistant");
    setSending(true);
    startLoadingIndicator(pending);
    scrollToBottom();

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ message: value, conversation_id: state.currentId }),
      });
      const chat = await readResponse(response);
      finishLoadingIndicator(pending);
      setAnswer(pending, chat.answer);
      pending.title = formatTime(chat.created_at);
      if (chat.saved && chat.id != null) {
        const question = pending.previousElementSibling;
        question?.setAttribute("id", `chat-${chat.id}`);
        if (question) question.dataset.chatId = String(chat.id);
        pending.dataset.chatId = String(chat.id);
      } else {
        addNote("이 대화는 저장되지 않았어요. 새로고침하면 기록에 보이지 않습니다.");
      }
      if (chat.conversation_id != null) {
        state.currentId = chat.conversation_id;
        remember(chat.conversation_id);
        touchConversation(chat.conversation_id, value, chat.created_at);
      }
    } catch (error) {
      finishLoadingIndicator(pending);
      if (error.status === 401) {
        goToLogin(error);
        return;
      }
      pending.remove();
      if (error.code === "CONVERSATION_NOT_FOUND") {
        await handleMissingConversation();
        setStatus("대화방을 찾을 수 없어 새 대화를 시작했어요. 질문을 다시 보내 주세요.", true);
      } else {
        addMessage(describeError(error), "error");
      }
      if (error.code === "VALIDATION_ERROR") setStatus(errorMessages.VALIDATION_ERROR, true);
      // Put the question back so it can be sent again.
      if (!input.value) {
        input.value = value;
        resizeInput();
      }
    } finally {
      stopLoadingIndicator();
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

  // Saved conversations stay in the sidebar; the next question starts a new one.
  document.querySelector("[data-new-chat]")?.addEventListener("click", () => {
    if (state.busy) return;
    startNewChat();
    input.value = "";
    resizeInput();
    setStatus("");
    closeSidebar();
    input.focus();
  });

  // Sidebar width: drag the edge (mouse or touch) or use the arrow keys on it.
  const SIDEBAR_MIN = 200;
  const SIDEBAR_MAX = 480;
  const SIDEBAR_STEP = 16;
  const WIDTH_KEY = "nsh.sidebarWidth";

  const clampWidth = (value) => Math.round(Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, value)));

  const applySidebarWidth = (value) => {
    const width = clampWidth(value);
    layout?.style.setProperty("--sidebar-width", `${width}px`);
    resizer?.setAttribute("aria-valuenow", String(width));
    return width;
  };

  const saveSidebarWidth = (width) => {
    try {
      window.localStorage.setItem(WIDTH_KEY, String(width));
    } catch {
      // Storage can be blocked (private mode); the width just is not remembered.
    }
  };

  const currentSidebarWidth = () => sidebar?.getBoundingClientRect().width || SIDEBAR_MIN;

  if (resizer && sidebar && layout) {
    try {
      const saved = Number(window.localStorage.getItem(WIDTH_KEY));
      if (saved) applySidebarWidth(saved);
    } catch {
      // Ignore unreadable storage and keep the default width.
    }

    let dragging = false;
    resizer.addEventListener("pointerdown", (event) => {
      dragging = true;
      resizer.setPointerCapture?.(event.pointerId);
      resizer.classList.add("is-dragging");
      event.preventDefault();
    });
    resizer.addEventListener("pointermove", (event) => {
      if (!dragging) return;
      applySidebarWidth(event.clientX - sidebar.getBoundingClientRect().left);
    });
    const stopDragging = () => {
      if (!dragging) return;
      dragging = false;
      resizer.classList.remove("is-dragging");
      saveSidebarWidth(clampWidth(currentSidebarWidth()));
    };
    resizer.addEventListener("pointerup", stopDragging);
    resizer.addEventListener("pointercancel", stopDragging);

    resizer.addEventListener("keydown", (event) => {
      const width = currentSidebarWidth();
      let next = null;
      if (event.key === "ArrowLeft") next = width - SIDEBAR_STEP;
      else if (event.key === "ArrowRight") next = width + SIDEBAR_STEP;
      else if (event.key === "Home") next = SIDEBAR_MIN;
      else if (event.key === "End") next = SIDEBAR_MAX;
      if (next === null) return;
      event.preventDefault();
      saveSidebarWidth(applySidebarWidth(next));
    });
  }

  // The mobile sidebar remembers whether it was open, so a reload keeps the same screen.
  const SIDEBAR_OPEN_KEY = "nsh.sidebarOpen";
  const mobileQuery = window.matchMedia?.("(max-width: 720px)");

  function setSidebarOpen(open, remember = true) {
    sidebar?.classList.toggle("is-open", open);
    menuToggle?.setAttribute("aria-expanded", String(open));
    menuToggle?.setAttribute("aria-label", open ? "대화 메뉴 닫기" : "대화 메뉴 열기");
    if (!remember) return;
    try {
      window.localStorage.setItem(SIDEBAR_OPEN_KEY, open ? "1" : "0");
    } catch {
      // Storage can be blocked (private mode); the state just is not remembered.
    }
  }

  try {
    if (mobileQuery?.matches && window.localStorage.getItem(SIDEBAR_OPEN_KEY) === "1") {
      setSidebarOpen(true, false);
    }
  } catch {
    // Ignore unreadable storage and start with the sidebar closed.
  }

  function closeSidebar() {
    if (sidebar?.classList.contains("is-open")) setSidebarOpen(false);
  }

  menuToggle?.addEventListener("click", () => {
    setSidebarOpen(!sidebar?.classList.contains("is-open"));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isMenuOpen()) {
      setMenuOpen(false, true);
      return;
    }
    if (event.key === "Escape" && sidebar?.classList.contains("is-open")) {
      setSidebarOpen(false);
      menuToggle?.focus();
    }
  });

  document.addEventListener("click", (event) => {
    if (isMenuOpen() && !userMenu.contains(event.target) && !menuButton?.contains(event.target)) {
      setMenuOpen(false);
    }
    if (!sidebar?.classList.contains("is-open")) return;
    if (sidebar.contains(event.target) || menuToggle?.contains(event.target)) return;
    setSidebarOpen(false);
  });

  loadCurrentUser();
  loadInitialConversation();
})();
