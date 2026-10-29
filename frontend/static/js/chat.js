(() => {
  const form = document.querySelector("[data-chat-form]");
  const input = document.querySelector("[data-chat-input]");
  const list = document.querySelector("[data-message-list]");
  const welcome = document.querySelector("[data-welcome]");
  const sidebar = document.querySelector(".sidebar");

  if (!form || !input || !list) return;

  const addMessage = (text, role) => {
    const item = document.createElement("div");
    item.className = `message message-${role}`;
    item.textContent = text;
    list.append(item);
  };

  const submitMessage = (text) => {
    const value = text.trim();
    if (!value) return;
    if (welcome) welcome.hidden = true;
    addMessage(value, "user");
    input.value = "";
    input.style.height = "auto";
    input.focus();
    // 채팅 API가 정해지면 사용자 메시지 전송과 응답 처리를 연결합니다.
    window.setTimeout(() => addMessage("추천 기능은 서버 API 연결 후 사용할 수 있습니다.", "assistant"), 250);
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
