# 팀 구성 및 기여

PR과 Git 이력을 기준으로 정리했습니다. PR 번호가 없는 항목은 아직 리뷰 중인 브랜치입니다.

| 구성원 | 담당 영역 | 작업 요약 |
| --- | --- | --- |
| 김시현(팀장, `innurhap28`) | 기획, 프론트엔드, 문서·CI, 데이터 추출 | 서비스 기획과 화면 흐름 정리, 초기 FastAPI 앱과 `/health` 구성, 로그인·회원가입·채팅 화면(PR #5), 페이지 라우트와 `/static` 연결(PR #28), 채팅 화면을 채팅·기록 API에 연결하고 오류 안내 표시(PR #32), 다른 곳 로그인으로 끊긴 경우 안내 표시(`frontend/session-notice`), 나무위키 덤프 스트리밍 리더와 스타 문서 추출 CLI(PR #31), CI(lint·test)와 ruff·pytest 설정, PR 템플릿과 라벨·머지 규칙 문서(PR #12), 린트 정리와 테스트 폴더 통합(PR #36), Railway 배포 런북(PR #14), README·API·아키텍처·DB·협업 문서(PR #1, #17, `docs/setup-all`) |
| 황승재(`bidulgiya999`) | 백엔드, DB, 배포 | PostgreSQL 연결과 users·chat_logs 모델, 비밀번호 해시와 회원가입·로그인·로그아웃·내 정보 API(PR #4), 로컬 PostgreSQL 준비와 Swagger 오류 명세(PR #8), Swagger health 증빙(PR #6), 비밀번호 해시 호환(PR #18), Swagger 로그인 예시와 로컬 출처 판단 수정(PR #23), AI API·로그 설정(PR #19), AI 호출 모듈과 `POST /api/chat`(PR #29), `GET /api/me/chats`와 로그 확인 SQL(PR #30), 나무마크 정제·청킹·스타 테이블 적재(PR #33), 채팅 스타 검색과 출처 표시(PR #35), 이슈 폼과 라벨 자동화(PR #12), crud 계층 분리(`backend/crud-layer`), 계정당 세션 하나 규칙과 `user_sessions` 테이블(`backend/single-session`), Railway 프로젝트와 배포 |

## 작업 요약 체크리스트

### 팀장

- [x] 기획 및 화면 흐름 정리
- [x] 로그인·회원가입·채팅 화면 구현과 채팅·대화 기록 API 연결
- [x] 초기 FastAPI 구성과 페이지 라우트
- [x] 나무위키 덤프에서 스타 문서 추출
- [x] CI(lint·test)와 협업 규칙, PR 템플릿
- [x] 문서 작업과 docs 브랜치에서 팀 문서 통합 (README 최종 정리 포함)
- [ ] 배포 후 외부 접속 URL을 README에 추가

### 팀원

- [x] 인증 (회원가입·로그인·로그아웃·내 정보)과 비로그인 접근 차단
- [x] PostgreSQL 연동과 사용자별 대화 기록 저장·조회
- [x] AI API 연동, 입력 검증, 타임아웃·오류 처리, 운영 로그
- [x] 스타 자료 정제·적재와 채팅 검색
- [x] DB 접근을 crud 함수로 분리, 계정당 세션 하나 규칙 (리뷰 중)
- [ ] 서비스 배포 및 외부 접속 확인

### 공동

- [x] API 계약과 데이터 형식 협의
- [x] 서로의 PR 리뷰·승인
- [ ] 배포 전 통합 동작 확인
