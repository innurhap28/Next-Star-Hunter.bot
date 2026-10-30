(() => {
  const tabs = [...document.querySelectorAll("[data-auth-tab]")];
  const panels = [...document.querySelectorAll("[data-auth-panel]")];
  const message = document.querySelector("[data-form-message]");
  const setMessage = (text, isError = false) => {
    if (!message) return;
    message.textContent = text;
    message.classList.toggle("is-error", isError);
  };

  // Shown when another login replaced this session (the chat page redirects here).
  const notice = document.querySelector("[data-session-notice]");
  const params = new URLSearchParams(window.location.search);
  if (notice && params.get("reason") === "session_replaced") {
    notice.textContent = "다른 곳에서 로그인되어 로그아웃되었어요. 다시 로그인해 주세요.";
    notice.hidden = false;
    params.delete("reason");
    const query = params.toString();
    window.history.replaceState(null, "", window.location.pathname + (query ? `?${query}` : "") + window.location.hash);
  }

  const selectTab = (name) => {
    tabs.forEach((tab) => {
      const active = tab.dataset.authTab === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    panels.forEach((panel) => { panel.hidden = panel.dataset.authPanel !== name; });
  };

  const fieldMessages = {
    email: "이메일 형식을 확인해 주세요.",
    password: "비밀번호는 8자 이상 128자 이하로 입력해 주세요. 공백만으로는 만들 수 없습니다.",
  };

  const readResponse = async (response) => {
    if (response.status === 204) return null;
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      // VALIDATION_ERROR lists invalid inputs as ["body", "<field>"] without echoing their values.
      const fields = (Array.isArray(body.fields) ? body.fields : [])
        .map((loc) => (Array.isArray(loc) ? loc[loc.length - 1] : loc))
        .filter((name) => typeof name === "string");
      const fieldMessage = fields.map((name) => fieldMessages[name]).find(Boolean);
      const error = new Error(fieldMessage || body.message || "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.");
      error.status = response.status;
      error.fields = fields;
      throw error;
    }
    return body;
  };

  const explainNetworkError = () => "서버에 연결할 수 없습니다. FastAPI 서버에서 같은 주소로 페이지를 열었는지 확인해 주세요.";

  const redirectIfAlreadyLoggedIn = async () => {
    try {
      const response = await fetch("/api/me", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      await readResponse(response);
      window.location.replace("/");
    } catch (error) {
      if (error.status !== 401) {
        // Static previews and an unconfigured backend can still show the auth form.
        console.info("Could not check the current session.", error.message);
      }
    }
  };

  redirectIfAlreadyLoggedIn();

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      selectTab(tab.dataset.authTab);
      setMessage("");
    });
  });

  document.querySelectorAll(".auth-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;

      const isSignup = form.dataset.authPanel === "signup";
      // The confirmation is checked in the browser only; the API never receives it.
      if (isSignup && form.elements.password.value !== form.elements.password_confirm.value) {
        setMessage("비밀번호가 서로 달라요. 같은 비밀번호를 다시 입력해 주세요.", true);
        form.elements.password_confirm.focus();
        return;
      }
      const submitButton = form.querySelector('button[type="submit"]');
      const email = form.elements.email.value.trim();
      const password = form.elements.password.value;
      submitButton.disabled = true;
      setMessage(isSignup ? "계정을 만들고 있습니다…" : "로그인하고 있습니다…");

      try {
        if (isSignup) {
          const response = await fetch("/api/auth/register", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
          });
          await readResponse(response);
          document.querySelector("#login-email").value = email;
          selectTab("login");
          document.querySelector("#login-password")?.focus();
          setMessage("가입이 완료됐어요. 비밀번호를 입력해 로그인해 주세요.");
          return;
        }

        const response = await fetch("/api/auth/login", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
        await readResponse(response);
        setMessage("로그인됐어요. 채팅 화면으로 이동합니다.");
        window.setTimeout(() => window.location.assign("/"), 350);
      } catch (error) {
        setMessage(error instanceof TypeError ? explainNetworkError() : error.message, true);
        const invalidInput = (error.fields || []).map((name) => form.elements[name]).find(Boolean);
        invalidInput?.focus();
      } finally {
        submitButton.disabled = false;
      }
    });
  });
})();
