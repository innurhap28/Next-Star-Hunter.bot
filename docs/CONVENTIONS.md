# 협업 규칙

## 브랜치 전략

- `main`: 배포 기준 브랜치입니다. `develop`에서 릴리스 PR로만 반영하며, 배포는 `main`에 반영된 코드로 진행합니다.
- `develop`: 통합 브랜치입니다. 모든 작업 브랜치는 PR을 통해 `develop`에 병합합니다.
- `docs/setup-all`: 문서 변경을 모아 작업하는 브랜치입니다. 기능 브랜치에서 개별적으로 문서를 수정하지 않고, 문서 변경은 팀이 이 브랜치에서 함께 정리한 뒤 PR로 `develop`에 병합합니다.
- `frontend/<주제>`, `backend/<주제>`, `chore/<주제>`: 기능별 작업 브랜치로 사용합니다.
- `main`과 `develop`에는 직접 push하지 않고 PR로만 반영합니다. PR과 병합 기록을 저장소에 남깁니다.
- 작업 브랜치에 `develop`의 최신 변경이 필요하면 `develop`을 작업 브랜치에 머지해서 가져옵니다. 이미 push한 커밋은 rebase나 force push로 고치지 않습니다.
- 배포 전에는 `develop` → `main` 릴리스 PR을 만들어 검토하고 병합한 뒤 배포합니다.

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
| 협업 자동화(CI·라벨) | `chore/collab-automation` |
| 배포 런북 | `chore/deploy-runbook` |

문서 주제(프로젝트 개요, 아키텍처, API, DB, 배포, 팀 기여 등)가 달라도 별도 브랜치를 만들지 않고 현재 사용 중인 `docs/setup-all` 브랜치에서 함께 정리합니다.

## 커밋 메시지

변경 목적이 드러나도록 짧게 작성합니다. 권장 형식은 `<type>: <내용>`입니다.

예시:

```text
feat: 대화 화면 입력 폼 추가
fix: health 응답 형식 수정
docs: API 명세 초안 작성
refactor: 설정 로딩 코드 정리
```

사용하는 type은 `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `merge`입니다. `develop`을 작업 브랜치에 가져오는 머지 커밋은 `merge: develop 최신 변경 반영`처럼 적습니다.

기능 변경은 작고 검토하기 쉬운 단위로 커밋합니다. 과제 요구에 따라 팀원별 유의미한 커밋을 10회 이상 남깁니다.

## 라벨 규칙

라벨 이름은 이 문서와 워크플로·보호 설정이 함께 참조합니다. 콜론 뒤 공백까지 포함해 아래 표기 그대로 사용합니다(예: `priority: P0`).

| 라벨 | 의미 | 부착 방식 |
| --- | --- | --- |
| `priority: P0` | 서비스 중단·마감 임박. 당일 처리 | 자동 — 이슈 폼 드롭다운 |
| `priority: P1` | 이번 스프린트 내 처리 | 자동 — 이슈 폼 드롭다운 |
| `priority: P2` | 기본값. 순서대로 처리 | 자동 — 이슈 폼 드롭다운 |
| `priority: P3` | 여유 있을 때 | 자동 — 이슈 폼 드롭다운 |
| `area: backend` | `backend/**` (API·모델·설정) | 자동 — 이슈 폼 / PR 변경 경로 |
| `area: frontend` | `backend/app/templates/**`, `backend/app/static/**`, `frontend/**` | 자동 — 이슈 폼 / PR 변경 경로 |
| `area: docs` | `docs/**`, `README.md`, `temp.md` | 자동 — 이슈 폼 / PR 변경 경로 |
| `area: infra` | `.github/**`, `requirements*.txt`, `Dockerfile*`, `docker-compose*`, `pyproject.toml` | 자동 — 이슈 폼 / PR 변경 경로 |
| `area: db` | `**/models/**`, `**/migrations/**`, `**/*.sql` | 자동 — 이슈 폼 / PR 변경 경로 |
| `type: feat` | 기능 추가 | 수동 |
| `type: fix` | 버그 수정 | 수동 |
| `type: docs` | 문서 | 수동 |
| `type: refactor` | 리팩터링 | 수동 |
| `type: test` | 테스트 | 수동 |
| `type: chore` | 설정·빌드 잡무 | 수동 |

- **자동 부착**: `priority:*`는 이슈 폼의 우선순위 드롭다운에서 고른 값으로, `area:*`는 이슈 폼의 분야 드롭다운과 PR의 변경 경로로 정해집니다. PR의 경로 기반 부착은 라벨러가 담당하며, `sync-labels`를 쓰지 않으므로 경로 규칙이 잡지 못하는 변경에서 사람이 붙인 `area:*`를 지우지 않습니다.
- **수동 부착**: `type:*`은 자동화 대상이 아니므로 PR 작성자나 리뷰어가 직접 붙입니다. 폼을 거치지 않은 이슈(자유 형식·빈 본문)에서는 자동화가 사람이 붙인 라벨을 건드리지 않으므로, 예외 상황의 `priority:*`·`area:*`도 직접 붙입니다.

## 머지 조건

| 브랜치 | 머지 조건 |
| --- | --- |
| `main` | PR 필수, 승인 1개, CI `lint`+`test` 통과, 대화 해결 필수 |
| `develop` | 승인 없이 CI `lint`+`test` 통과만 확인 |

`main`은 아래 조건을 모두 만족해야 머지됩니다.

- PR을 통해서만 머지합니다(보호 대상 브랜치에 직접 push 금지).
- 승인 1개가 필요하고 **자기 승인은 인정되지 않습니다**.
- CI의 `lint`와 `test` 두 잡이 모두 통과해야 합니다. `lint`는 저장소 전체가 아니라 **이 PR/커밋에서 변경된 파이썬 파일만** 검사합니다(기존 린트 부채는 별도 이슈로 정리).
- 최신 커밋에 대한 승인이 유지되어야 합니다(`require_last_push_approval`). 승인 후 새 커밋을 push하면 다시 승인을 받아야 하며, 이전 승인은 무효가 됩니다(`dismiss_stale_reviews`).
- 리뷰 대화가 모두 해결(resolve)되어야 합니다.
- force push와 브랜치 삭제는 금지됩니다.

`develop`은 승인 없이 CI 통과만으로 머지할 수 있지만, 대화 해결 필수와 force push·브랜치 삭제 금지는 `main`과 동일하게 적용됩니다.

승인 없이 머지가 막히면 그것은 **정상 동작**입니다. 규칙을 완화해야 할 때는 이슈에 누가·언제·왜 완화했는지 남기고, 일이 끝나면 즉시 원래 규칙으로 되돌립니다.

## Pull Request

PR의 대상 브랜치는 기본적으로 `develop`이고, 배포용 릴리스 PR만 `main`을 대상으로 합니다. PR에는 변경 목적, 주요 수정 사항, 확인 방법을 적습니다. 화면이나 API 응답이 바뀌면 예시 또는 캡처를 포함하고, 검토 후 병합합니다.

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

## 문서 위치

설계 문서(`design/`)와 구현 계획 문서는 저장소에 넣지 않고 팀 공유 드라이브나 각자 로컬에 둡니다. 저장소의 `docs/`에는 제품 문서만 둡니다: API, ARCHITECTURE, DATABASE, CONVENTIONS, DEPLOY, CONTRIBUTORS.
