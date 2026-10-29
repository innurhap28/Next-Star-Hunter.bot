(() => {
  const tabs = [...document.querySelectorAll("[data-auth-tab]")];
  const panels = [...document.querySelectorAll("[data-auth-panel]")];
  const message = document.querySelector("[data-form-message]");
  const setMessage = (text, isError = false) => {
    if (!message) return;
    message.textContent = text;
    message.classList.toggle("is-error", isError);
  };

  const selectTab = (name) => {
    tabs.forEach((tab) => {
      const active = tab.dataset.authTab === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    panels.forEach((panel) => { panel.hidden = panel.dataset.authPanel !== name; });
  };

  const readResponse = async (response) => {
    if (response.status === 204) return null;
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(body.message || "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.");
      error.status = response.status;
      throw error;
    }
    return body;
  };

  const explainNetworkError = () => "서버에 연결할 수 없습니다. FastAPI 서버에서 같은 주소로 페이지를 열었는지 확인해 주세요.";

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
      } finally {
        submitButton.disabled = false;
      }
    });
  });
})();
