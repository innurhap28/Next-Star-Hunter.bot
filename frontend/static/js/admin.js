(() => {
  const status = document.querySelector("[data-admin-status]");
  const usersBody = document.querySelector("[data-users-body]");
  const usersTotal = document.querySelector("[data-users-total]");
  const usersPage = document.querySelector("[data-users-page]");
  const prevButton = document.querySelector("[data-users-prev]");
  const nextButton = document.querySelector("[data-users-next]");
  const chatsTitle = document.querySelector("[data-chats-title]");
  const chatsList = document.querySelector("[data-chats-list]");
  const showAllButton = document.querySelector("[data-show-all-chats]");

  if (!usersBody || !chatsList) return;

  const PAGE_SIZE = 50;
  const CHAT_LIMIT = 50;
  const NETWORK_ERROR = "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";

  let offset = 0;
  let total = 0;
  let selectedUserId = null;

  const setStatus = (text, isError = false) => {
    if (!status) return;
    status.textContent = text;
    status.classList.toggle("is-error", isError);
  };

  // 401: 로그인 화면으로, 403: 관리자가 아니므로 채팅 화면으로 보낸다.
  const leavePage = (error) => {
    if (error.status === 401) {
      const replaced = error.code === "SESSION_REPLACED";
      window.location.assign(replaced ? "/auth?reason=session_replaced" : "/auth");
      return true;
    }
    if (error.status === 403) {
      window.location.assign("/");
      return true;
    }
    return false;
  };

  const getJson = async (url) => {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(body.message || "요청을 처리하지 못했습니다.");
      error.status = response.status;
      error.code = body.error;
      throw error;
    }
    return body;
  };

  const showError = (prefix, error) => {
    if (leavePage(error)) return;
    const text = error instanceof TypeError ? NETWORK_ERROR : error.message;
    setStatus(error.code ? `${prefix} ${text} (error: ${error.code})` : `${prefix} ${text}`, true);
  };

  const formatTime = (value) => {
    if (!value) return "-";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString("ko-KR");
  };

  const formatDate = (value) => {
    if (!value) return "-";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "-" : date.toLocaleDateString("ko-KR");
  };

  const cell = (text) => {
    const td = document.createElement("td");
    td.textContent = text;
    return td;
  };

  const loadStats = async () => {
    try {
      const stats = await getJson("/api/admin/stats");
      for (const key of ["users", "chats", "chats_today"]) {
        const target = document.querySelector(`[data-stat="${key}"]`);
        if (target) target.textContent = Number(stats[key] ?? 0).toLocaleString("ko-KR");
      }
    } catch (error) {
      showError("현황을 불러오지 못했어요.", error);
    }
  };

  const renderUsers = (items) => {
    usersBody.replaceChildren();
    if (!items.length) {
      const row = document.createElement("tr");
      const td = cell("가입한 사용자가 없습니다.");
      td.colSpan = 4;
      td.className = "admin-empty";
      row.append(td);
      usersBody.append(row);
      return;
    }
    for (const user of items) {
      const row = document.createElement("tr");
      row.className = "admin-user-row";
      row.classList.toggle("is-selected", user.id === selectedUserId);
      const emailCell = document.createElement("td");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "admin-user-button";
      button.textContent = user.email;
      button.addEventListener("click", () => selectUser(user));
      emailCell.append(button);
      row.append(
        emailCell,
        cell(formatDate(user.created_at)),
        cell(String(user.chat_count ?? 0)),
        cell(formatTime(user.last_chat_at)),
      );
      usersBody.append(row);
    }
  };

  const updatePager = () => {
    const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    const page = Math.floor(offset / PAGE_SIZE) + 1;
    if (usersPage) usersPage.textContent = `${page} / ${pages}`;
    if (usersTotal) usersTotal.textContent = `총 ${total.toLocaleString("ko-KR")}명`;
    if (prevButton) prevButton.disabled = offset === 0;
    if (nextButton) nextButton.disabled = offset + PAGE_SIZE >= total;
  };

  const loadUsers = async () => {
    try {
      const data = await getJson(`/api/admin/users?limit=${PAGE_SIZE}&offset=${offset}`);
      total = Number(data.total) || 0;
      renderUsers(Array.isArray(data.items) ? data.items : []);
      updatePager();
    } catch (error) {
      showError("사용자 목록을 불러오지 못했어요.", error);
    }
  };

  const renderChats = (items, showEmail) => {
    chatsList.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "admin-empty";
      empty.textContent = "저장된 대화가 없습니다.";
      chatsList.append(empty);
      return;
    }
    for (const chat of items) {
      const article = document.createElement("article");
      article.className = "admin-chat";
      const meta = document.createElement("div");
      meta.className = "admin-chat-meta";
      meta.textContent = showEmail ? `${chat.email} · ${formatTime(chat.created_at)}` : formatTime(chat.created_at);
      const question = document.createElement("p");
      question.className = "message message-user";
      question.textContent = chat.question;
      const answer = document.createElement("p");
      answer.className = "message message-assistant";
      answer.textContent = chat.answer;
      article.append(meta, question, answer);
      chatsList.append(article);
    }
  };

  const loadChats = async (user) => {
    const query = user ? `user_id=${encodeURIComponent(user.id)}&limit=${CHAT_LIMIT}` : `limit=${CHAT_LIMIT}`;
    if (chatsTitle) chatsTitle.textContent = user ? `${user.email} 의 대화` : "전체 최근 대화";
    if (showAllButton) showAllButton.hidden = !user;
    try {
      const data = await getJson(`/api/admin/chats?${query}`);
      renderChats(Array.isArray(data.items) ? data.items : [], !user);
    } catch (error) {
      showError("대화를 불러오지 못했어요.", error);
    }
  };

  const selectUser = (user) => {
    selectedUserId = user.id;
    for (const row of usersBody.querySelectorAll(".admin-user-row")) row.classList.remove("is-selected");
    const button = [...usersBody.querySelectorAll(".admin-user-button")].find((item) => item.textContent === user.email);
    button?.closest("tr")?.classList.add("is-selected");
    loadChats(user);
    chatsList.scrollIntoView({ block: "start" });
  };

  prevButton?.addEventListener("click", () => {
    offset = Math.max(0, offset - PAGE_SIZE);
    loadUsers();
  });

  nextButton?.addEventListener("click", () => {
    offset += PAGE_SIZE;
    loadUsers();
  });

  showAllButton?.addEventListener("click", () => {
    selectedUserId = null;
    for (const row of usersBody.querySelectorAll(".admin-user-row")) row.classList.remove("is-selected");
    loadChats(null);
  });

  loadStats();
  loadUsers();
  loadChats(null);
})();
