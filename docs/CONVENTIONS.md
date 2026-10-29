# 협업 규칙

## 브랜치 전략

- `main`: 통합 가능한 기준 브랜치입니다. 초기 FastAPI 실행 기반처럼 팀장이 맡기로 한 초기 작업은 합의된 범위에서 `main`에 반영합니다.
- `docs/setup-all`: 문서 변경을 모아 작업하는 브랜치입니다. 기능 브랜치에서 개별적으로 문서를 수정하지 않고, 문서 변경은 팀이 이 브랜치에서 함께 정리합니다.
- `frontend/<주제>` 및 `backend/<주제>`: 기능별 작업 브랜치로 사용합니다.
- 기능 작업은 가능한 한 작업 브랜치에서 진행하고 PR을 통해 `main`에 병합합니다. PR과 병합 기록을 저장소에 남깁니다.

## 브랜치 이름 예시

필요한 작업에 맞는 이름을 골라 그대로 사용할 수 있습니다.

| 작업 | 브랜치 이름 |
| --- | --- |
| 랜딩/홈 화면 | `frontend/home-page` |
| 채팅 화면 | `frontend/chat-screen` |
| 로그인 화면 | `frontend/login-page` |
| 회원가입 화면 | `frontend/signup-page` |
| 대화 기록 화면 | `frontend/chat-history` |
| FastAPI 초기 구성 | `backend/fastapi-setup` |
| 회원가입·로그인 API | `backend/auth-api` |
| PostgreSQL 연결 및 모델 | `backend/postgres-models` |
| AI API 연동 | `backend/ai-integration` |
| 채팅·문맥 처리 | `backend/chat-context` |
| 대화 기록 조회 | `backend/chat-history-api` |
| 입력 검증·오류 처리 | `backend/validation-errors` |
| 로깅 | `backend/request-logging` |
| 배포 설정 | `backend/deployment` |

문서 주제(프로젝트 개요, 아키텍처, API, DB, 팀 기여 등)가 달라도 별도 브랜치를 만들지 않고 현재 사용 중인 `docs/setup-all` 브랜치에서 함께 정리합니다.

## 커밋 메시지

변경 목적이 드러나도록 짧게 작성합니다. 권장 형식은 `<type>: <내용>`입니다.

예시:

```text
feat: 대화 화면 입력 폼 추가
fix: health 응답 형식 수정
docs: API 명세 초안 작성
refactor: 설정 로딩 코드 정리
```

기능 변경은 작고 검토하기 쉬운 단위로 커밋합니다. 과제 요구에 따라 팀원별 유의미한 커밋을 10회 이상 남깁니다.

## Pull Request

PR에는 변경 목적, 주요 수정 사항, 확인 방법을 적습니다. 화면이나 API 응답이 바뀌면 예시 또는 캡처를 포함하고, 검토 후 병합합니다.

```markdown
## 작업 목적

<!-- 어떤 문제를 해결하거나 어떤 기능을 추가하는지 적습니다. -->

## 주요 변경 사항

-
-

## 확인 방법

- [ ] 실행 또는 요청으로 확인함
- [ ] 관련 기능에 영향이 없는지 확인함
- [ ] 확인하지 못한 항목과 이유를 적음

## 화면/API 변경 (해당하는 경우)

<!-- 화면 캡처 또는 요청·응답 예시를 첨부합니다. -->

## 설정·DB·문서 영향 (해당하는 경우)

<!-- 환경 변수, DB 스키마, 문서 변경 사항을 적습니다. -->

## 연결된 이슈 또는 참고 사항

```
