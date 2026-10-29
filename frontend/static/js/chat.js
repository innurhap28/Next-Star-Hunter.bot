(() => {
  const form = document.querySelector("[data-chat-form]");
  const input = document.querySelector("[data-chat-input]");
  const list = document.querySelector("[data-message-list]");
  const welcome = document.querySelector("[data-welcome]");
  const sidebar = document.querySelector(".sidebar");
  const userLabel = document.querySelector("[data-user-label]");
  const loginLink = document.querySelector("[data-login-link]");
  const logoutButton = document.querySelector("[data-logout-button]");

  if (!form || !input || !list) return;

  const addMessage = (text, role) => {
    const item = document.createElement("div");
    item.className = `message message-${role}`;
    item.textContent = text;
    list.append(item);
  };

  const readResponse = async (response) => {
    if (response.status === 204) return null;
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(body.message || "요청을 처리하지 못했습니다.");
      error.status = response.status;
      throw error;
    }
    return body;
  };

  const loadCurrentUser = async () => {
    try {
      const response = await fetch("/api/me", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const user = await readResponse(response);
      if (userLabel) userLabel.textContent = user.email.split("@")[0];
      if (loginLink) loginLink.hidden = true;
      if (logoutButton) logoutButton.hidden = false;
    } catch (error) {
      if (error.status === 401) return;
      // Keep the guest view usable if the API is unavailable during a static preview.
      console.info("Could not load the current session.", error.message);
    }
  };

  loadCurrentUser();

  logoutButton?.addEventListener("click", async () => {
    logoutButton.disabled = true;
    try {
      const response = await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
      await readResponse(response);
      window.location.assign("/auth");
    } catch (error) {
      logoutButton.disabled = false;
      window.alert(error instanceof TypeError
        ? "서버에 연결할 수 없습니다. FastAPI 서버에서 페이지를 열었는지 확인해 주세요."
        : error.message);
    }
  });

  const submitMessage = (text) => {
    const value = text.trim();
    if (!value) return;
    if (welcome) welcome.hidden = true;
    addMessage(value, "user");
    input.value = "";
    input.style.height = "auto";
    input.focus();
    // The backend does not expose a chat endpoint yet.
    window.setTimeout(() => addMessage("스타 추천 API는 아직 연결되지 않았습니다.", "assistant"), 250);
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitMessage(input.value);
  });

  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  document.querySelectorAll("[data-suggestion]").forEach((button) => {
    button.addEventListener("click", () => submitMessage(button.dataset.suggestion || ""));
  });

  document.querySelector("[data-new-chat]")?.addEventListener("click", () => {
    list.replaceChildren();
    if (welcome) welcome.hidden = false;
    input.value = "";
    input.focus();
  });

  document.querySelector("[data-menu-toggle]")?.addEventListener("click", () => {
    sidebar?.classList.toggle("is-open");
  });
})();
