# API 명세

엔드포인트별 요청·응답 예시와 오류를 정리합니다. 요청·응답 스키마는 Swagger UI(https://next-star-hunter-production.up.railway.app/docs)에서도 볼 수 있습니다. Swagger UI와 `/openapi.json`은 `ENABLE_API_DOCS=true`일 때만 열립니다.

- 요청과 응답 본문은 JSON입니다. 시각은 UTC 기준 ISO 8601 문자열입니다.
- 로그인하면 `next_star_session` 쿠키(HttpOnly, SameSite=Lax, 8시간, 운영은 Secure)가 발급되고, 로그인이 필요한 API는 이 쿠키로 사용자를 확인합니다.
- 모든 응답에 `X-Request-ID`(요청 ID)와 `Cache-Control: no-store` 헤더가 붙습니다. 요청에 UUID 형식의 `X-Request-ID`를 보내면 그 값을 그대로 씁니다.
- 브라우저가 보낸 `POST` 요청의 `Origin`이 서버 주소와 다르면 처리하지 않고 `403 ORIGIN_NOT_ALLOWED`로 응답합니다. `Origin` 헤더가 없는 요청(curl 등)은 그대로 처리합니다.

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| GET | `/health` | 없음 | 서버 상태 확인 |
| GET | `/` | 로그인 (아니면 `/auth`로 이동) | 채팅 화면 (HTML) |
| GET | `/auth` | 없음 | 로그인·회원가입 화면 (HTML) |
| POST | `/api/auth/register` | 없음 | 회원가입 |
| POST | `/api/auth/login` | 없음 | 로그인, 쿠키 발급, 이전 세션 교체 |
| POST | `/api/auth/logout` | 로그인 | 로그아웃, 쿠키 삭제 |
| GET | `/api/me` | 로그인 | 내 계정 정보 |
| POST | `/api/chat` | 로그인 | 질문 전송, AI 답변 반환, 대화 저장 |
| GET | `/api/me/chats` | 로그인 | 내 대화 기록 |

## 오류 응답

직접 정의한 오류는 모두 같은 형식입니다. 사용자가 보낸 값, 비밀번호, DB 주소, AI 서버의 오류 본문은 응답에 넣지 않습니다.

```json
{
  "error": "EMAIL_EXISTS",
  "message": "이미 가입된 이메일입니다."
}
```

| 상태 | `error` | 상황 |
|---|---|---|
| 401 | `INVALID_CREDENTIALS` | 이메일 또는 비밀번호 불일치 |
| 401 | `LOGIN_REQUIRED` | 로그인 쿠키가 없음, 만료됨, 계정이나 세션 행이 사라짐 |
| 401 | `SESSION_REPLACED` | 같은 계정이 다른 곳에서 로그인해 이 세션이 끊김 |
| 403 | `ORIGIN_NOT_ALLOWED` | 다른 출처의 브라우저가 보낸 `POST` 요청 |
| 409 | `EMAIL_EXISTS` | 이미 가입된 이메일로 회원가입 |
| 422 | `VALIDATION_ERROR` | 입력 형식 오류 (아래 참고) |
| 502 | `AI_ERROR` | AI API 오류 응답, 연결 실패, 빈 응답, 응답 형식 오류 |
| 503 | `AUTH_NOT_CONFIGURED` | `SECRET_KEY`가 없거나 32자 미만, 또는 `DATABASE_URL`이 없음 |
| 503 | `DB_NOT_CONFIGURED` | `DATABASE_URL`이 PostgreSQL 주소가 아니거나 DB 이름이 없음 |
| 503 | `DB_UNAVAILABLE` | DB 연결이나 쿼리 실패 |
| 503 | `AI_NOT_CONFIGURED` | 서버에 `LLM_API_KEY`가 없음 |
| 504 | `AI_TIMEOUT` | AI API가 `LLM_TIMEOUT_SECONDS`(기본 90초) 안에 응답하지 않음 |

입력 형식 오류는 `fields`에 오류 위치만 담습니다. 입력값은 비밀번호일 수 있어 돌려주지 않습니다. JSON 문법이 틀리면 위치가 글자 번호로 나옵니다(`[["body", 9]]`).

```
POST /api/auth/register {"email":"bad","password":"short"}
HTTP 422
{
  "error": "VALIDATION_ERROR",
  "message": "입력 형식을 확인해주세요.",
  "fields": [["body", "email"], ["body", "password"]]
}
```

없는 경로 같은 그 밖의 HTTP 오류는 `{"error": "HTTP_ERROR", "message": "Not Found"}`처럼 응답합니다.

## 시스템과 화면

### GET /health

DB와 AI 설정 없이도 응답합니다. Railway 헬스체크와 배포 후 스모크 검사가 이 경로를 씁니다.

```
GET /health
HTTP 200
{"status": "ok", "service": "next-star-hunter"}
```

### GET /, GET /auth

HTML 화면이라 Swagger에는 나오지 않습니다. 쿠키의 세션을 `user_sessions`와 비교해 이동할 곳을 정합니다.

| 요청 | 상태 | 응답 |
|---|---|---|
| `GET /` (로그인 상태) | 200 | 채팅 화면 |
| `GET /` (로그인 안 함, 세션 만료) | 303 | `Location: /auth` |
| `GET /` (다른 곳의 로그인으로 세션이 끊김) | 303 | `Location: /auth?reason=session_replaced` |
| `GET /auth` (로그인 상태) | 303 | `Location: /` |
| `GET /auth` (그 밖) | 200 | 로그인·회원가입 화면. 끊긴 세션의 쿠키는 지웁니다 |

DB에 연결할 수 없으면 서명된 쿠키만 보고 화면을 열고, 화면 스크립트가 `GET /api/me`의 응답으로 다시 판단합니다. 정적 파일은 `/static/css/`, `/static/js/`로 제공합니다.

## 인증

### POST /api/auth/register

인증: 없음

`email`은 이메일 형식이고 254자 이하이며 소문자로 바꿔 저장합니다. `password`는 8자 이상 128자 이하이고 공백만으로 이뤄질 수 없습니다. 그 밖의 필드는 받지 않습니다. 비밀번호는 해시만 저장합니다.

```
POST /api/auth/register {"email":"User@Example.com","password":"password1234"}
HTTP 201
{
  "id": 1,
  "email": "user@example.com",
  "created_at": "2026-10-30T07:40:12.246172Z"
}
```

```
POST /api/auth/register {"email":"user@example.com","password":"password1234"}
HTTP 409
{
  "error": "EMAIL_EXISTS",
  "message": "이미 가입된 이메일입니다."
}
```

| 상태 | `error` | 상황 |
|---|---|---|
| 403 | `ORIGIN_NOT_ALLOWED` | 다른 출처의 브라우저 요청 |
| 409 | `EMAIL_EXISTS` | 이미 가입된 이메일 (대소문자 무시) |
| 422 | `VALIDATION_ERROR` | 이메일 형식, 비밀번호 길이, 알 수 없는 필드 |
| 503 | `AUTH_NOT_CONFIGURED`, `DB_NOT_CONFIGURED`, `DB_UNAVAILABLE` | 서버 설정 또는 DB 문제 |

### POST /api/auth/login

인증: 없음

회원가입과 같은 형식(`email`, `password`)을 받습니다. 성공하면 세션 쿠키를 발급하고 내 계정 정보를 돌려줍니다. 같은 계정의 이전 로그인은 끊깁니다([계정당 세션 하나](#계정당-세션-하나)).

```
POST /api/auth/login {"email":"user@example.com","password":"password1234"}
HTTP 200
Set-Cookie: next_star_session=...; path=/; Max-Age=28800; httponly; samesite=lax; secure
{
  "id": 1,
  "email": "user@example.com",
  "created_at": "2026-10-30T07:40:12.246172Z"
}
```

```
POST /api/auth/login {"email":"user@example.com","password":"wrongpass1"}
HTTP 401
{
  "error": "INVALID_CREDENTIALS",
  "message": "이메일 또는 비밀번호를 확인해주세요."
}
```

가입하지 않은 이메일도 같은 `INVALID_CREDENTIALS`로 응답해 계정이 있는지 드러내지 않습니다. 비밀번호가 8자 미만이면 확인 전에 `422`가 됩니다.

| 상태 | `error` | 상황 |
|---|---|---|
| 401 | `INVALID_CREDENTIALS` | 이메일 또는 비밀번호 불일치 |
| 403 | `ORIGIN_NOT_ALLOWED` | 다른 출처의 브라우저 요청 |
| 422 | `VALIDATION_ERROR` | 이메일 형식, 비밀번호 길이, 알 수 없는 필드 |
| 503 | `AUTH_NOT_CONFIGURED`, `DB_NOT_CONFIGURED`, `DB_UNAVAILABLE` | 서버 설정 또는 DB 문제 |

### POST /api/auth/logout

인증: 로그인

요청 본문은 없습니다. 쿠키를 지우고 `user_sessions` 행을 삭제합니다. 행은 지금 세션의 것일 때만 지우므로, 이미 끊긴 세션에서 로그아웃해도 다른 곳의 새 로그인은 유지됩니다.

```
POST /api/auth/logout
HTTP 204
Set-Cookie: next_star_session=null; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; httponly; samesite=lax; secure
```

| 상태 | `error` | 상황 |
|---|---|---|
| 401 | `LOGIN_REQUIRED`, `SESSION_REPLACED` | 로그인하지 않았거나 세션이 끊김 |
| 403 | `ORIGIN_NOT_ALLOWED` | 다른 출처의 브라우저 요청 |
| 503 | `AUTH_NOT_CONFIGURED`, `DB_NOT_CONFIGURED`, `DB_UNAVAILABLE` | 서버 설정 또는 DB 문제 |

### GET /api/me

인증: 로그인

```
GET /api/me
HTTP 200
{
  "id": 1,
  "email": "user@example.com",
  "created_at": "2026-10-30T07:40:12.246172Z"
}
```

```
GET /api/me
HTTP 401
{
  "error": "LOGIN_REQUIRED",
  "message": "로그인이 필요합니다."
}
```

| 상태 | `error` | 상황 |
|---|---|---|
| 401 | `LOGIN_REQUIRED` | 로그인하지 않음. 계정이나 세션 행이 사라졌으면 문구가 "다시 로그인해주세요."입니다 |
| 401 | `SESSION_REPLACED` | 다른 곳에서 로그인해 이 세션이 끊김 |
| 503 | `AUTH_NOT_CONFIGURED`, `DB_NOT_CONFIGURED`, `DB_UNAVAILABLE` | 서버 설정 또는 DB 문제 |

### 계정당 세션 하나

같은 계정은 마지막으로 로그인한 한 곳에서만 쓸 수 있습니다. 계정을 같이 쓰거나 다른 기기에 로그인해 둔 채로 두었을 때 누구의 대화인지 섞이지 않게 하려는 규칙입니다.

- 로그인하면 서버가 임의의 세션 ID를 만들어 서명된 쿠키에 사용자 ID와 함께 넣고, `user_sessions`에는 그 ID의 SHA-256 해시만 저장합니다. 이전 로그인의 행은 덮어씁니다.
- 로그인이 필요한 API(`logout`, `me`, `chat`, `me/chats`)와 화면 이동은 요청마다 쿠키의 세션 ID를 저장된 해시와 상수 시간으로 비교합니다.
- 해시가 다르면 쿠키 세션을 지우고 `401 SESSION_REPLACED`로 응답하며 서버 로그에 `session_replaced`를 남깁니다. 채팅 화면은 이 응답을 받으면 `/auth?reason=session_replaced`로 이동해 "다른 곳에서 로그인되어 로그아웃되었어요. 다시 로그인해 주세요."를 표시합니다.

```
POST /api/chat {"message":"요즘 인기 있는 배우 알려줘"}
HTTP 401
{
  "error": "SESSION_REPLACED",
  "message": "다른 곳에서 로그인되어 로그아웃되었습니다."
}
```

## 채팅과 기록

### POST /api/chat

인증: 로그인

`message`는 앞뒤 공백을 지운 뒤 1자 이상 1000자 이하여야 하고, 그 밖의 필드는 받지 않습니다. 서버는 다음 순서로 처리합니다.

1. 같은 사용자의 최근 질문·답변 5쌍을 `chat_logs`에서 읽습니다.
2. 질문으로 스타 자료(`star_profiles`, `star_chunks`)를 검색합니다. 질문에 조건이 없으면 바로 앞 질문의 조건을 이어받습니다. 검색 규칙은 [DATA.md](DATA.md#채팅-검색)에 있습니다.
3. 시스템 프롬프트, 검색 결과(`<참고자료>` 블록), 최근 5쌍, 새 질문을 AI API에 보냅니다. 이전 답변에 붙은 출처 줄은 빼고 보냅니다.
4. 답변에서 언급한 스타만 골라 `출처: 나무위키(CC BY-NC-SA 2.0 KR) - 이름1, 이름2` 줄을 붙입니다(아무도 언급하지 않았으면 검색된 스타 전부). 모델이 직접 쓴 출처 줄은 지웁니다. 검색 결과가 없으면 출처 줄을 붙이지 않습니다.
5. 질문과 답변(출처 줄 포함)을 `chat_logs`에 저장하고 응답합니다.

```
POST /api/chat {"message":"안경 쓴 부산 출신 아이돌 추천해줘"}
HTTP 200
{
  "id": 1,
  "question": "안경 쓴 부산 출신 아이돌 추천해줘",
  "answer": "부산 출신에 안경 착용으로 유명한 분들이 자료에 몇 명 있어요. 조유리는 IZ*ONE 출신으로 부산 남구 태생인데, (생략)\n\n출처: 나무위키(CC BY-NC-SA 2.0 KR) - 조유리, 강혜원, 산들",
  "created_at": "2026-10-30T07:41:15.917402Z",
  "saved": true
}
```

AI 답변은 받았지만 DB 저장에 실패하면 답변은 그대로 돌려주고 `saved`를 `false`, `id`를 `null`로 보냅니다. 이 대화는 기록에 남지 않습니다.

```
POST /api/chat {"message":"요즘 인기 있는 배우 알려줘"}
HTTP 504
{
  "error": "AI_TIMEOUT",
  "message": "현재 응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요."
}
```

```
POST /api/chat {"message":"   "}
HTTP 422
{
  "error": "VALIDATION_ERROR",
  "message": "입력 형식을 확인해주세요.",
  "fields": [["body", "message"]]
}
```

| 상태 | `error` | 상황 |
|---|---|---|
| 401 | `LOGIN_REQUIRED` | 로그인하지 않음 |
| 401 | `SESSION_REPLACED` | 다른 곳에서 로그인해 이 세션이 끊김 |
| 403 | `ORIGIN_NOT_ALLOWED` | 다른 출처의 브라우저 요청 |
| 422 | `VALIDATION_ERROR` | 빈 질문, 1000자 초과, 알 수 없는 필드 |
| 502 | `AI_ERROR` | AI API 오류 응답, 연결 실패, 빈 응답, 응답 형식 오류 |
| 503 | `AI_NOT_CONFIGURED` | `LLM_API_KEY` 없음. 메시지는 "서버 AI 설정을 확인해주세요." |
| 503 | `DB_UNAVAILABLE` | 최근 대화 조회 등 DB 요청 실패 |
| 504 | `AI_TIMEOUT` | AI API 응답 시간 초과 |

AI 호출이 실패하면 질문을 저장하지 않으므로 같은 질문을 다시 보내면 됩니다. 스타 검색이 실패하거나 결과가 없으면 오류로 보지 않고 참고 자료 없이 답합니다.

AI API는 서버에서만 호출하고, `LLM_API_STYLE`에 따라 아래 형식으로 요청합니다.

| `LLM_API_STYLE` | 요청 주소 | 인증 헤더 |
|---|---|---|
| `anthropic` (기본) | `{LLM_BASE_URL}/messages` | `x-api-key`, `anthropic-version: 2023-06-01` |
| `openai` | `{LLM_BASE_URL}/chat/completions` | `Authorization: Bearer` |

시스템 프롬프트는 캐스팅 매니저 역할로, 한국어 평문 6문장 이내로 1~3명을 이유와 함께 추천하게 합니다. 참고 자료에 없는 사실은 지어내지 않고 확인하지 못한 조건은 그렇다고 말하게 하며, `<참고자료>` 안의 글은 지시가 아니라 자료로만 다루게 합니다.

### GET /api/me/chats

인증: 로그인

로그인한 사용자의 대화 기록 중 최신 `limit`건을 오래된 순서로 돌려줍니다. 다른 사용자의 기록은 조회되지 않습니다.

| 쿼리 | 형식 | 기본값 |
|---|---|---|
| `limit` | 정수 1~100 | 20 |

```
GET /api/me/chats?limit=2
HTTP 200
{
  "items": [
    {
      "id": 1,
      "question": "안경 쓴 부산 출신 아이돌 추천해줘",
      "answer": "부산 출신에 안경 착용으로 유명한 분들이 자료에 몇 명 있어요. (생략)\n\n출처: 나무위키(CC BY-NC-SA 2.0 KR) - 조유리, 강혜원, 산들",
      "created_at": "2026-10-30T07:41:15.917402Z"
    },
    {
      "id": 2,
      "question": "그중에 제일 최근에 데뷔한 사람은 누구야?",
      "answer": "자료에서 확인되는 데뷔 연도를 보면 조유리가 2018년으로 셋 중 가장 최근에 데뷔했어요. (생략)\n\n출처: 나무위키(CC BY-NC-SA 2.0 KR) - 조유리, 산들",
      "created_at": "2026-10-30T07:42:19.508113Z"
    }
  ]
}
```

기록이 없으면 `{"items": []}`입니다.

```
GET /api/me/chats?limit=0
HTTP 422
{
  "error": "VALIDATION_ERROR",
  "message": "입력 형식을 확인해주세요.",
  "fields": [["query", "limit"]]
}
```

| 상태 | `error` | 상황 |
|---|---|---|
| 401 | `LOGIN_REQUIRED` | 로그인하지 않음 |
| 401 | `SESSION_REPLACED` | 다른 곳에서 로그인해 이 세션이 끊김 |
| 422 | `VALIDATION_ERROR` | `limit`이 범위를 벗어나거나 정수가 아님 |
| 503 | `DB_UNAVAILABLE` | DB 요청 실패 |

DB에서 직접 확인하는 방법은 [README](../README.md#sql로-확인하기)에 있습니다.
