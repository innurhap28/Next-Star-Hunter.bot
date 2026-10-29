# 데이터베이스 설계

PostgreSQL을 사용합니다. 아래 스키마를 기준으로 구현하고, 팀의 설계가 바뀌면 이 문서와 ERD를 함께 갱신합니다.

## 구현 체크리스트

- [x] PostgreSQL 연결 설정 및 스키마 생성
- [x] 사용자 계정과 비밀번호 해시 저장
- [x] 사용자별 질문·응답·생성 시각 누적 저장
- [x] 로그인 사용자 기준으로 본인 대화만 조회
- [x] DB 확인용 SQL, 스크립트 또는 로그 조회 API/화면 제공

## 관계

```mermaid
erDiagram
    USERS ||--o{ CHAT_LOGS : owns
    USERS {
        integer id PK
        varchar email UK
        varchar password_hash
        timestamptz created_at
    }
    CHAT_LOGS {
        integer id PK
        integer user_id FK
        text question
        text answer
        timestamptz created_at
    }
```

한 사용자는 여러 대화 로그를 가질 수 있습니다. 각 로그는 하나의 사용자에게 속합니다.

## 테이블 및 필드

### `users`

| 필드 | 형식 | 설명 |
| --- | --- | --- |
| `id` | 정수, 기본 키 | 사용자 식별자 |
| `email` | 문자열, 고유 | 로그인 계정 식별자 |
| `password_hash` | 문자열 | 비밀번호 해시. 원문 비밀번호는 저장하지 않습니다. |
| `created_at` | 시간대 포함 시각 | 계정 생성 시각 |

### `chat_logs`

| 필드 | 형식 | 설명 |
| --- | --- | --- |
| `id` | 정수, 기본 키 | 대화 로그 식별자 |
| `user_id` | 정수, 외래 키 | `users.id` 참조 |
| `question` | 텍스트 | 사용자가 입력한 질문 |
| `answer` | 텍스트 | AI가 생성한 응답 |
| `created_at` | 시간대 포함 시각 | 대화 생성 시각 |

사용자별 로그 조회는 `user_id`로 제한합니다. 최신 기록을 빠르게 가져오도록 `(user_id, created_at, id)` 인덱스 `ix_chat_logs_user_created`를 둡니다.

## 대화 로그 확인 방법

- API: 로그인한 뒤 `GET /api/me/chats?limit=N`으로 본인 기록을 봅니다. 자세한 형식은 [API 명세](API.md)에 있습니다.
- SQL: `scripts/check_logs.sql`에 사용자별 대화 수와 한 사용자의 최근 20건을 보는 쿼리가 있습니다.

```bash
psql "$DATABASE_URL" -v email='user@example.com' -f scripts/check_logs.sql
```

`psql`은 `postgresql://` 형식 주소를 받으므로, `DATABASE_URL`이 `postgresql+psycopg://`로 시작하면 `+psycopg`를 빼고 넣습니다.
