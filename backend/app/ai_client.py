"""Server-side AI API calls. The API key never leaves this module."""
import httpx

SYSTEM_PROMPT = (
    "너는 'Next Star Hunter'의 친절한 캐스팅 매니저야. "
    "사용자가 말한 취향(분위기, 외모, 장르, 출신 등)을 바탕으로 "
    "한국 아이돌·가수·배우를 추천하고 이유를 짧게 설명해. "
    "항상 한국어로 답해. 확실하지 않은 정보는 지어내지 말고 잘 모르겠다고 말해."
)
ANTHROPIC_VERSION = "2023-06-01"


class AIError(Exception):
    """Failure that is safe to show: code and message only, no upstream body."""
    status_code = 502
    code = "AI_ERROR"
    message = "AI 응답을 받지 못했어요. 잠시 후 다시 시도해 주세요."

    def __init__(self, reason=""):
        # reason is for server logs only (status code or exception type).
        super().__init__(reason)
        self.reason = reason or self.code.lower()


class AITimeout(AIError):
    status_code = 504
    code = "AI_TIMEOUT"
    message = "현재 응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요."


class AINotConfigured(AIError):
    status_code = 503
    code = "AI_NOT_CONFIGURED"
    message = "서버 AI 설정을 확인해주세요."


def build_messages(history, question):
    """Previous Q/A pairs (oldest first) followed by the new question."""
    messages = []
    for item in history:
        messages.append({"role": "user", "content": item.question})
        messages.append({"role": "assistant", "content": item.answer})
    messages.append({"role": "user", "content": question})
    return messages


def _anthropic_request(settings, messages):
    url = settings.LLM_BASE_URL.rstrip("/") + "/messages"
    headers = {"x-api-key": settings.LLM_API_KEY.get_secret_value(),
               "anthropic-version": ANTHROPIC_VERSION}
    body = {"model": settings.LLM_MODEL, "max_tokens": settings.LLM_MAX_COMPLETION_TOKENS,
            "system": SYSTEM_PROMPT, "messages": messages}
    return url, headers, body


def _openai_request(settings, messages):
    url = settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {"Authorization": "Bearer " + settings.LLM_API_KEY.get_secret_value()}
    body = {"model": settings.LLM_MODEL, "max_tokens": settings.LLM_MAX_COMPLETION_TOKENS,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages]}
    return url, headers, body


def _read_answer(style, data):
    if style == "anthropic":
        parts = [block["text"] for block in data["content"] if block.get("type") == "text"]
        answer = "".join(parts)
    else:
        answer = data["choices"][0]["message"]["content"]
    if not isinstance(answer, str) or not answer.strip():
        raise AIError("empty_answer")
    return answer.strip()


def ask_ai(settings, history, question, transport=None):
    """Return the answer text or raise an AIError subclass."""
    if not settings.llm_configured():
        raise AINotConfigured()
    messages = build_messages(history, question)
    if settings.LLM_API_STYLE == "anthropic":
        url, headers, body = _anthropic_request(settings, messages)
    else:
        url, headers, body = _openai_request(settings, messages)
    try:
        with httpx.Client(timeout=settings.LLM_TIMEOUT_SECONDS, transport=transport) as client:
            response = client.post(url, headers=headers, json=body)
    except httpx.TimeoutException as error:
        raise AITimeout(type(error).__name__) from None
    except httpx.HTTPError as error:
        raise AIError(type(error).__name__) from None
    if response.status_code >= 400:
        raise AIError(f"http_{response.status_code}")
    try:
        return _read_answer(settings.LLM_API_STYLE, response.json())
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise AIError("bad_response") from None
