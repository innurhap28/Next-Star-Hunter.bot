# 시스템 아키텍처

## 전체 흐름

```mermaid
flowchart LR
    U[사용자 브라우저] --> F[Frontend]
    F --> A[FastAPI]
    A -->|로그인 사용자 질문| AI[AI API]
    A --> DB[(PostgreSQL)]
    AI --> A
    A --> F
```

화면은 `frontend/`에서, API와 서버 기능은 `backend/`에서 구현합니다. 브라우저는 FastAPI에 요청하고, 서버가 인증 및 입력을 확인한 뒤 필요하면 AI API와 PostgreSQL을 사용합니다. AI API 키는 서버 환경 변수로만 관리합니다.

## 주요 컴포넌트

| 컴포넌트 | 역할 |
| --- | --- |
| Frontend | 질문 입력과 AI 응답·대화 기록 표시 |
| FastAPI | 웹 요청 처리, 인증·접근 제어, 입력 검증, AI 및 DB 연동 |
| AI API | 질문과 최근 대화 문맥을 바탕으로 답변 생성 |
| PostgreSQL | 사용자 정보 및 질문·응답 로그 저장 |

## 프로젝트 구조

```text
backend/app/
├── main.py           # 앱 생성, 미들웨어(세션·요청 로그), 라우터 등록
├── config.py         # 환경 변수 설정 (Settings)
├── database.py       # DB 엔진·세션 생성
├── models.py         # SQLAlchemy 테이블 (users, chat_logs, star_profiles, star_chunks)
├── schemas.py        # 요청·응답 Pydantic 스키마
├── dependencies.py   # get_db, get_current_user (로그인 확인 공통 의존성)
├── security.py       # 비밀번호 해시·검증
├── routers/          # API 경로: auth.py(계정), chat.py(채팅·기록), pages.py(화면)
├── crud/             # DB 접근 함수: users.py, chat_logs.py
├── ai_client.py      # AI API 호출, 타임아웃·실패 처리
└── star_search.py    # 스타 데이터 검색과 AI 참고 자료 구성
```

라우터는 요청 검증, HTTP 오류 응답, 로그 기록만 맡고, 쿼리와 저장(commit/rollback)은 `crud/` 함수를 호출합니다. 예를 들어 회원가입은 `get_user_by_email`, `create_user`를, 채팅은 `recent_chat_pairs`, `save_chat_log`를, 기록 조회는 `list_user_chats`를 사용합니다. 스타 데이터 검색 쿼리는 검색 로직과 붙어 있어 `star_search.py`에 그대로 둡니다.

## 구현 계획 체크리스트

- [x] `frontend/`에서 로그인·회원가입 화면과 질문 입력 채팅 화면 구현
- [x] 채팅 화면에서 AI 답변 표시와 대화 기록 연결 (`POST /api/chat`, `GET /api/me/chats` 사용)
- [x] FastAPI 앱과 `GET /health` 상태 확인 경로 구성
- [x] 회원가입·로그인 및 로그인 상태 접근 제어 (채팅 API 포함)
- [x] PostgreSQL 사용자·대화 로그 연결 (`POST /api/chat`에서 대화 저장)
- [x] 서버에서 AI API 호출 및 타임아웃·실패 처리
- [x] 최근 대화 문맥 구성 (같은 사용자의 최근 5쌍)
- [ ] 사용자별 대화 기록 조회
- [x] 요청, AI 호출 결과, DB 저장 결과 로그 기록

## 질문 처리 흐름 계획

1. 로그인한 사용자가 화면에서 질문을 보냅니다.
2. FastAPI가 인증 상태와 입력값을 확인합니다.
3. 서버가 같은 사용자의 최근 대화 일부를 문맥으로 구성해 AI API를 호출합니다.
4. 성공한 질문과 답변을 사용자 식별자 및 생성 시각과 함께 PostgreSQL에 저장합니다.
5. 응답을 화면에 반환합니다. 실패 또는 시간 초과 시 오류를 기록하고 사용자에게 안내합니다.
