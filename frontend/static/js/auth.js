(() => {
  const tabs = [...document.querySelectorAll("[data-auth-tab]")];
  const panels = [...document.querySelectorAll("[data-auth-panel]")];
  const message = document.querySelector("[data-form-message]");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const selected = tab.dataset.authTab;
      tabs.forEach((item) => {
        const active = item === tab;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", String(active));
      });
      panels.forEach((panel) => { panel.hidden = panel.dataset.authPanel !== selected; });
      if (message) message.textContent = "";
    });
  });

  // 인증 API 경로가 정해지면 폼 제출 처리를 연결합니다.
  document.querySelectorAll(".auth-form").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (form.action.endsWith("#")) {
        event.preventDefault();
        if (message) message.textContent = "인증 기능은 서버 API 연결 후 사용할 수 있습니다.";
      }
    });
  });
})();
