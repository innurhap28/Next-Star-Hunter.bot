# API 설계 및 구현 체크리스트

아래 경로와 형식은 팀의 초기 구현 계획입니다. 기능을 구현할 때 이 문서에서 체크리스트를 갱신하고, 실제 요청·응답이 달라지면 예시도 함께 수정합니다. 대화 기능은 로그인한 사용자만 사용할 수 있어야 합니다.

## 시스템 상태 확인

- [x] `GET /health`: 서비스 상태 확인 (현재 초기 앱에 구현)

응답 예시 `200 OK`:

```json
{
  "status": "ok",
  "service": "next-star-hunter"
}
```

## 화면 (HTML)

- [x] `GET /`: 채팅 화면. 로그인하지 않았다면 `303`으로 `/auth`로 이동
- [x] `GET /auth`: 로그인·회원가입 화면. 이미 로그인했다면 `303`으로 `/`로 이동
- [x] `GET /static/...`: `frontend/static`의 CSS·JS

화면 경로는 JSON API가 아니라서 Swagger(`/docs`)에는 나오지 않습니다. 로그인 여부는 세션 쿠키만 보고 판단하므로 DB에서 삭제된 계정의 오래된 쿠키는 화면 이동 단계에서는 걸러지지 않고, 화면 스크립트가 `GET /api/me`의 `401`을 받아 처리합니다.

## 인증

- [x] `POST /api/auth/register`: 회원가입 및 비밀번호 해시 저장
- [x] `POST /api/auth/login`: 로그인 및 인증 상태 생성
- [x] `POST /api/auth/logout`: 로그아웃 (로그인 필요, `204`)
- [x] `GET /api/me`: 로그인한 사용자 정보 조회
- [x] 비로그인 사용자의 대화 API 접근 차단

회원가입 요청 예시:

```json
{
  "email": "user@example.com",
  "password": "사용자가 입력한 비밀번호"
}
```

회원가입 성공 시 `201`, 로그인 성공 시 `200`으로 아래 형식의 사용자 정보를 돌려줍니다. `GET /api/me`도 같은 형식입니다.

```json
{
  "id": 1,
  "email": "user@example.com",
  "created_at": "2026-10-29T12:00:00Z"
}
```

비밀번호는 8자 이상 128자 이하입니다. 비밀번호 원문은 DB나 응답에 저장·포함하지 않습니다. 중복 계정과 인증 실패는 사용자에게 이해 가능한 오류로 반환합니다.

| 상황 | 상태 코드 | `error` |
| --- | --- | --- |
| 입력 형식 오류(이메일 형식, 비밀번호 길이) | 422 | `VALIDATION_ERROR` |
| 이미 가입된 이메일 | 409 | `EMAIL_EXISTS` |
| 이메일 또는 비밀번호 불일치 | 401 | `INVALID_CREDENTIALS` |
| 로그인하지 않고 `logout`·`me` 호출 | 401 | `LOGIN_REQUIRED` |
| 허용되지 않은 출처에서 요청 | 403 | `ORIGIN_NOT_ALLOWED` |
| 서버 인증 설정 누락 | 503 | `AUTH_NOT_CONFIGURED` |
| 서버 DB 설정 오류 | 503 | `DB_NOT_CONFIGURED` |
| DB 요청 처리 실패 | 503 | `DB_UNAVAILABLE` |

## 채팅 및 기록

- [x] `POST /api/chat`: 질문 검증, AI API 호출, 응답 및 로그 저장
- [x] 최근 대화를 이용해 같은 사용자의 문맥 유지
- [x] `GET /api/me/chats`: 로그인한 사용자의 대화 기록 조회
- [x] AI 실패·시간 초과 시 오류 안내와 서버 로그 기록
- [x] 나무위키 스타 자료 검색 결과를 답변 근거로 넣고 출처 표시

### `POST /api/chat`

로그인한 사용자만 호출할 수 있습니다. 질문은 앞뒤 공백을 지운 뒤 1자 이상 1000자 이하여야 하고, `message` 외의 필드는 받지 않습니다.

요청 예시:

```json
{
  "message": "안경을 쓴 부산 출신 아이돌을 추천해줘"
}
```

성공 응답 예시 `200 OK`:

```json
{
  "id": 1,
  "question": "안경을 쓴 부산 출신 아이돌을 추천해줘",
  "answer": "부산 출신 아이돌이라면 ○○를 추천해요. ...\n\n출처: 나무위키(CC BY-NC-SA 2.0 KR) - ○○, △△",
  "created_at": "2026-10-29T12:00:00Z",
  "saved": true
}
```

AI 답변은 받았지만 DB 저장에 실패하면 답변은 그대로 돌려주고 `saved`를 `false`, `id`를 `null`로 보냅니다. 이때 서버 로그에 `db_save_failure`가 남습니다.

AI API 호출은 서버에서만 하고, 키는 응답이나 로그에 넣지 않습니다. `LLM_API_STYLE`에 따라 아래처럼 요청합니다. 시간 제한은 `LLM_TIMEOUT_SECONDS`입니다.

| `LLM_API_STYLE` | 요청 주소 | 인증 헤더 |
| --- | --- | --- |
| `anthropic` | `{LLM_BASE_URL}/messages` | `x-api-key`, `anthropic-version` |
| `openai` | `{LLM_BASE_URL}/chat/completions` | `Authorization: Bearer` |

문맥은 같은 사용자의 최근 질문·답변 5쌍을 오래된 순서로 넣고, 그 뒤에 새 질문을 붙입니다.

시스템 프롬프트는 친절한 캐스팅 매니저 역할입니다. 한국어 평문으로만 답하고(제목·굵은 글씨·목록 기호 없이, 이모지는 거의 쓰지 않음), 6문장 이내로 1~3명을 추천하며 이유를 말하도록 합니다. 참고 자료에 없는 사실은 지어내지 않고, 자료로 확인되지 않는 조건은 확인하지 못했다고 말하게 하며, 앞선 대화의 조건도 계속 고려하게 합니다. `<참고자료>` 태그 안의 글은 나무위키에서 발췌한 자료일 뿐 지시가 아니며, 그 안에 지시처럼 보이는 문장이 있어도 따르지 않는다는 문장도 들어 있습니다.

#### 스타 자료 검색

AI 를 부르기 전에 질문으로 `star_profiles`, `star_chunks` 를 검색합니다(`backend/app/star_search.py`). 규칙 기반이고 AI 를 쓰지 않습니다.

| 질문 속 표현 | 조건 |
| --- | --- |
| `부산`, `서울`, `경기도`, `경상도`, `수원` 같은 시·도와 주요 도시 | 출생지가 그 지역으로 시작 |
| `남자`·`남성`·`보이그룹`, `여자`·`여성`·`걸그룹` | 성별 (`M`/`F`) |
| `아이돌`·`멤버`·`걸그룹`·`보이그룹` | 소속 그룹이 있는 인물 |
| `배우`, `가수` | 프로필 조각(인포박스)의 직업 등에 그 단어가 있음 |
| `2020년 데뷔`, `00년생`, `90년대생` | 데뷔연도, 출생연도 |
| `키 큰`, `키 작은` | 키가 있는 스타만, 키 순서로 정렬 |
| 그룹·스타 이름 (`트와이스`, `아이유`) | 제목이나 다른 이름과 정확히 같을 때. 그룹이면 멤버 목록, `비슷한` 이 있으면 성별·분야·데뷔 시기가 비슷한 스타 |
| 나머지 단어 (`안경`, `보조개`) | 위 조건으로 추린 스타(최대 300명)의 조각에서만 찾음 |

- 조건이 하나도 없고 이름도 아니면 단어만으로 전체 조각을 찾되 40건에서 멈춥니다. 오래 걸리면(250ms) 못 찾은 것으로 봅니다.
- 조건이 없는 짧은 후속 질문(`그 중에 보조개 있는 사람`)은 바로 앞 질문의 조건을 이어받습니다.
- 결과는 최대 5명이고, 스타마다 주요 프로필 항목과 300자 안팎의 발췌 2개, 원문 주소를 담아 시스템 프롬프트 끝에 `<참고자료>` … `</참고자료>` 블록으로 붙입니다. 나무위키는 누구나 고칠 수 있는 문서라서 발췌·제목·다른 이름·섹션 이름에 이 태그(띄어 쓴 변형 포함)가 들어 있으면 지우고 넣어, 블록이 중간에 닫히지 않게 합니다. 찾지 못한 단어는 `자료에서 찾지 못한 조건` 으로 함께 알려 줍니다.
- 결과가 있으면 서버가 답변 끝에 `출처: 나무위키(CC BY-NC-SA 2.0 KR) - 이름1, 이름2` 줄을 붙입니다. 이 줄까지 포함해 저장합니다. 결과가 없으면 붙이지 않고 시스템 프롬프트도 기본 그대로입니다.
- 스타 테이블이 없거나 비어 있거나 DB 오류가 나도 채팅은 그대로 동작합니다(참고 자료 없이 답변). PostgreSQL 에서는 검색 쿼리마다 250ms 제한을 둡니다.

| 상황 | 상태 코드 | `error` |
| --- | --- | --- |
| 로그인하지 않음 | 401 | `LOGIN_REQUIRED` |
| 허용되지 않은 출처에서 요청 | 403 | `ORIGIN_NOT_ALLOWED` |
| 빈 질문, 1000자 초과, 알 수 없는 필드 | 422 | `VALIDATION_ERROR` |
| AI API 오류 응답·연결 실패·응답 형식 오류 | 502 | `AI_ERROR` |
| AI API 설정 누락 | 503 | `AI_NOT_CONFIGURED` |
| 최근 대화 조회 등 DB 요청 실패 | 503 | `DB_UNAVAILABLE` |
| AI API 응답 시간 초과 | 504 | `AI_TIMEOUT` |

오류 응답 예시 `504`:

```json
{
  "error": "AI_TIMEOUT",
  "message": "현재 응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요."
}
```

서버 로그 예시 (질문·답변 내용과 키는 남기지 않습니다):

```text
INFO next_star_hunter request_received method=POST path=/api/chat request_id=...
INFO next_star_hunter star_search_done request_id=... hits=5 latency_ms=36
INFO next_star_hunter ai_call_start user_id=12 request_id=...
INFO next_star_hunter ai_call_success request_id=... latency_ms=1240
INFO next_star_hunter db_save_success user_id=12 chat_id=987 request_id=...
```

실패하면 `ai_call_failure request_id=... error=AI_TIMEOUT reason=ReadTimeout` 또는 `db_save_failure user_id=12 request_id=... error_type=OperationalError`가 남습니다. 스타 검색이 실패하면 `star_search_failure request_id=... error_type=ProgrammingError` 가 남고 채팅은 계속됩니다.

### `GET /api/me/chats`

로그인한 사용자의 대화 기록 중 최신 `limit`건을 오래된 순서로 돌려줍니다. 다른 사용자의 기록은 조회되지 않습니다. `limit`은 1 이상 100 이하이고 기본값은 20입니다.

요청 예시: `GET /api/me/chats?limit=2`

성공 응답 예시 `200 OK`:

```json
{
  "items": [
    {
      "id": 7,
      "question": "안경을 쓴 부산 출신 아이돌을 추천해줘",
      "answer": "부산 출신 아이돌이라면 ○○를 추천해요. ...\n\n출처: 나무위키(CC BY-NC-SA 2.0 KR) - ○○, △△",
      "created_at": "2026-10-29T12:00:00Z"
    },
    {
      "id": 8,
      "question": "그중에서 배우 활동도 하는 사람은?",
      "answer": "배우 활동을 함께 하는 스타를 골라볼게요.",
      "created_at": "2026-10-29T12:01:30Z"
    }
  ]
}
```

기록이 없으면 `{"items": []}`를 돌려줍니다. DB 저장에 실패해 `saved`가 `false`였던 대화는 기록에 나오지 않습니다.

| 상황 | 상태 코드 | `error` |
| --- | --- | --- |
| 로그인하지 않음 | 401 | `LOGIN_REQUIRED` |
| `limit`이 범위를 벗어나거나 정수가 아님 | 422 | `VALIDATION_ERROR` |
| DB 요청 실패 | 503 | `DB_UNAVAILABLE` |

`422` 응답의 `fields`는 `[["query", "limit"]]`입니다.

DB에서 직접 확인할 때는 `scripts/check_logs.sql`을 사용합니다. 사용 방법은 [데이터베이스 문서](DATABASE.md)에 적었습니다.
