# Next Star Hunter (다음 아이돌 발굴가)

> **“내 눈은 틀리지 않아, 얘는 무조건 뜬다!”**

사용자의 취향과 조건을 바탕으로 아이돌·배우·가수 등 스타를 추천하는 웹 기반 AI 챗봇 서비스입니다. 로그인한 사용자가 자연어로 조건을 입력하면 서버가 AI API를 호출해 응답하고, 질문과 답변을 사용자별 대화 기록으로 저장합니다.

## 프로젝트 개요

- **문제 정의**: 관심 있는 스타를 외모·프로필 취향에 맞춰 발견하고 싶지만 조건을 조합해 탐색하기 어렵습니다.
- **타겟 사용자**: 새로운 아이돌, 배우, 가수 등을 취향에 맞춰 찾아보고 싶은 사용자입니다.
- **핵심 시나리오**: 회원가입 및 로그인 후 “안경을 쓴 부산 출신 아이돌을 추천해줘”처럼 질문하고, 같은 화면에서 추천과 이어지는 답변을 확인합니다. 이전 대화는 문맥에 활용되고 사용자별 기록으로 저장됩니다.

## 핵심 기능 계획

- 성별, 헤어스타일, 액세서리, 출신 지역 등 취향 조건을 이용한 스타 추천
- 조건 선택이 어려울 때 활용하는 랜덤 스타 헌팅
- 캐스팅 매니저와 대화하는 듯한 챗봇 UI
- 회원가입·로그인 및 로그인 사용자 전용 질문 기능
- 최근 대화를 활용한 문맥 유지와 사용자별 대화 기록 조회
- AI API 오류·타임아웃 안내, 입력 검증, 운영 로그

## 기술 스택

- **언어 / 백엔드**: Python, FastAPI
- **화면**: FastAPI 서버 렌더링 템플릿(Jinja2), Vanilla JavaScript, CSS
- **데이터베이스**: PostgreSQL, SQLAlchemy
- **AI 연동**: 서버에서 환경 변수로 설정한 AI API를 호출합니다. API 키를 브라우저에 전달하지 않습니다.
- **설정 / 세션**: pydantic-settings, itsdangerous 및 비밀번호 해시 관련 라이브러리

웹 UI는 FastAPI와 템플릿으로 구현합니다. Streamlit이나 Gradio로 대체하지 않습니다. 데이터베이스는 확장성을 고려해 PostgreSQL을 사용합니다. 외부 자료를 사용할 경우 출처·이용 조건을 확인하고 정제한 스타 정보를 서비스에서 활용할 계획입니다. 데이터 원천과 수집 방식은 확인 후 문서화합니다.

## 시스템 구조

```text
브라우저 ──> FastAPI 웹 화면 / API ──> 인증 및 입력 검증
                         ├──> AI API (서버 측 호출, 제한 시간 적용)
                         └──> PostgreSQL (사용자 및 대화 로그)
```

FastAPI는 화면, 인증, 질문 요청을 처리합니다. 질문을 받은 뒤 같은 사용자의 최근 대화를 문맥으로 구성해 AI API를 호출하고, 질문·응답·사용자·생성 시각을 PostgreSQL에 저장합니다. AI 호출 실패나 시간 초과는 서비스 프로세스를 종료시키지 않고 사용자 안내와 로그로 처리합니다.

## 데이터 및 대화 기록

대화 로그에는 최소한 다음 정보가 포함됩니다.

- 사용자 식별자
- 생성 시각
- 사용자 질문
- AI 응답

스타 프로필과 시각적 취향 태그는 다음과 같은 개념 구조로 관리할 계획입니다. 실제 스키마는 구현에 맞춰 [데이터베이스 문서](docs/DATABASE.md)에 기록합니다.

```json
{
  "name": "스타 이름",
  "group": "그룹 또는 솔로",
  "category": "아이돌",
  "profile": {"gender": "정보 확인 필요", "birthplace": "정보 확인 필요"},
  "visual_tags": ["안경", "곱슬머리"],
  "source_url": "자료 출처"
}
```

## API 및 로그 확인

API의 실제 경로와 요청·응답 예시는 구현 기준으로 [API 명세](docs/API.md)에 기록합니다. 로그인 사용자는 자신의 대화 로그를 조회할 수 있어야 합니다. 로그 조회 API/화면 또는 검증 SQL·스크립트 중 제공되는 방법을 문서에 명시합니다.

서버 로그에는 요청 수신, AI 호출 시작 및 성공/실패, DB 저장 성공/실패 이벤트를 남깁니다. 민감정보와 API 키는 로그에 기록하지 않습니다.

## 실행 및 환경 변수

Python 3.9 이상을 사용합니다.

### macOS (zsh)

저장소 루트에서 가상환경을 만들고 활성화한 뒤 의존성을 설치합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --app-dir backend
```

### Windows PowerShell

저장소 루트에서 가상환경을 만들고 활성화한 뒤 의존성을 설치합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --app-dir backend
```

PowerShell에서 가상환경 활성화가 실행 정책에 의해 차단되면, 현재 PowerShell 창에만 적용되는 설정을 실행한 뒤 다시 활성화합니다.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Health 확인

서버 실행 상태를 유지한 채 새 터미널에서 요청합니다.

macOS:

```bash
curl http://127.0.0.1:8000/health
```

PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

정상 응답은 다음과 같습니다.

```json
{"status":"ok","service":"next-star-hunter"}
```

현재 `/health`는 DB와 AI API 설정 없이 확인할 수 있습니다. 회원 인증, DB 연결, AI 호출 기능을 실행할 때는 `.env.example`을 `.env`로 복사해 환경에 맞게 설정하세요. DB 초기화 절차는 백엔드 기능 구현에 맞춰 구체화합니다. `.env`는 Git에 추가하지 않습니다.

환경 변수 키 목록:

| 변수 | 용도 |
| --- | --- |
| `SECRET_KEY` | 세션 및 서명용 비밀 키 |
| `DATABASE_URL` | PostgreSQL 데이터베이스 연결 주소 |
| `LOG_FILE_PATH` | 선택 사항인 로그 파일 경로 |
| `LLM_API_KEY` | AI API 인증 키 |
| `LLM_BASE_URL` | AI API 주소. 기본값 copa(`https://copa.codyssey.kr/v1`) |
| `LLM_API_STYLE` | AI API 요청 형식 선택 |
| `LLM_MODEL` | 모델. 기본값 `claude-sonnet-4`(예비로 `claude-haiku-4`만 허용) |
| `LLM_TIMEOUT_SECONDS` | AI API 호출 시간 제한(초) |
| `LLM_MAX_COMPLETION_TOKENS` | 응답 최대 토큰 수 |
| `LLM_JSON_MODE` | JSON 응답 모드 사용 여부 |
| `CHAT_TOTAL_TIMEOUT_SECONDS` | 전체 채팅 요청 시간 제한(초) |
| `KNOWLEDGE_USAGE_SCOPE` | 자료 사용 범위 설정 |
| `SESSION_HTTPS_ONLY` | HTTPS 전용 세션 쿠키 설정 |
| `ENABLE_API_DOCS` | API 문서 노출 여부 |

실제 키와 비밀번호를 README나 저장소에 넣지 마세요. 배포 절차와 운영 환경 변수는 [배포 런북](docs/DEPLOY.md)을 참고하세요. 현재 평가 시 외부 네트워크에서 접속 가능한 서비스 URL을 제공해야 합니다.

## 개발 단계

1. 출처와 이용 조건을 확인할 수 있는 스타 자료를 선정하고 프로필·태그를 정리합니다.
2. FastAPI 기반 회원가입·로그인, 입력 검증, 질문 처리와 AI API 연동을 구현합니다.
3. PostgreSQL에 사용자 및 대화 기록을 저장하고 로그인 사용자별 조회를 제공합니다.
4. Jinja2 기반 챗봇 화면과 랜덤 추천 흐름을 구현합니다.
5. 오류 처리·운영 로그와 배포를 마치고 외부 접속 URL 및 실행 방법을 문서화합니다.

## 협업 및 산출물

`main`과 `develop` 브랜치를 사용하고, 기능 단위 브랜치에서 작업해 PR로 `develop`에 병합합니다. 배포 전에는 `develop`을 `main`으로 병합하는 릴리스 PR을 만듭니다. 브랜치·커밋·머지 규칙은 [협업 규칙](docs/CONVENTIONS.md)에 정리했습니다. 팀원별 유의미한 커밋 10회 이상과 PR 이력을 저장소에 남깁니다.

### 팀 구성 및 역할

| 담당 | 주요 역할 |
| --- | --- |
| 김시현 | 서비스 기획과 작업 조율, `frontend/` 화면 구현, 초기 FastAPI 앱 구성 및 프론트엔드 연동 기반 마련, `docs` 브랜치에서 프로젝트 문서 관리 |
| 황승재 | `backend/`의 백엔드 기능 구현(인증, DB, AI 연동, 대화 기록 및 예외 처리), 배포 환경 구성과 서비스 배포 |
| 공동 작업 | API 계약과 데이터 형식 협의, 프론트엔드·백엔드 통합, 기능 흐름 확인 및 배포 전 점검 |

각 담당자는 맡은 영역의 구현 내용과 진행 상황을 공유하고, 통합 단계에서는 함께 동작을 확인합니다. 개인별 실제 기여 내역은 작업과 Git 이력에 맞춰 [팀 기여 문서](docs/CONTRIBUTORS.md)에 구체적으로 기록합니다.

- 팀 구성원 및 개인별 작업 요약: [팀 기여 문서](docs/CONTRIBUTORS.md)
- 시스템 구조: [아키텍처 문서](docs/ARCHITECTURE.md)
- API 요청·응답 명세: [API 문서](docs/API.md)
- DB 테이블 및 필드: [데이터베이스 문서](docs/DATABASE.md)
- 배포 절차와 운영 환경 변수: [배포 런북](docs/DEPLOY.md)

저장소 링크, 배포 URL, 실제 실행 명령, 로그 확인 방법은 구현 및 배포 후 검증 가능한 값으로 채웁니다.
