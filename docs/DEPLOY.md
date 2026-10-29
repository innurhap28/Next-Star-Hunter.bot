# 배포 런북

이 문서는 운영 배포를 처음 하거나 다시 할 때 그대로 따라 하는 절차입니다. 값(비밀 키·비밀번호)은
문서에 적지 않고 Railway 대시보드에서 팀이 직접 입력합니다.

## 배포 대상

| 항목 | 값 |
| --- | --- |
| 배포 플랫폼 | Railway (GitHub 연동 자동배포) |
| Railway 프로젝트 소유자 | 황승재님 |
| 저장소 | `innurhap28/Next-Star-Hunter.bot` |
| 배포 브랜치 | `main` |
| 자동배포 조건 | `main`에 릴리스 PR이 병합되면 Railway가 빌드·배포를 시작한다 |
| GitHub Secrets | 0개 (Railway가 저장소를 직접 감시하므로 토큰이 필요 없다) |
| 데이터베이스 | Railway PostgreSQL 플러그인 |

## Railway 서비스 설정

서비스(Settings 탭)에 아래 값을 넣습니다. Railway 설정 파일(`railway.toml` 등)은 만들지 않고 설정은 대시보드에서만 관리합니다.

| 항목 | 값 | 이유 |
| --- | --- | --- |
| Root Directory | `/` (비움) | 저장소 루트에 `requirements.txt`와 `backend/`가 같이 있다 |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir backend` | 앱 모듈이 `backend/app/main.py`라서 `--app-dir backend`가 필요하고, `$PORT`(Railway 주입)를 그대로 바인딩해야 라우팅이 붙는다 |
| Healthcheck Path | `/health` | `backend/app/main.py`의 `/health`는 DB·LLM 없이 `{"status":"ok","service":"next-star-hunter"}`를 돌려준다 |
| Restart Policy | `ON_FAILURE` | 앱이 죽었을 때만 재시작하고 정상 배포를 반복 재시작하지 않는다 |
| 리전(권고) | `asia-southeast1` | 국내 사용자 지연을 줄이기 위한 권고값이며 강제는 아니다 |

## 환경변수

Variables 탭에서 **이름만** 만들고 값은 팀이 직접 입력합니다. 저장소·PR·이 문서에 값을 남기지 마세요.

| 변수 | 얻는 방법 / 설명 |
| --- | --- |
| `SECRET_KEY` | 팀이 직접 생성: `python -c "import secrets; print(secrets.token_hex(32))"`. **32자 이상**이어야 인증이 켜진다(`backend/app/config.py`의 `auth_configured()`) |
| `DATABASE_URL` | Postgres 서비스의 참조 변수 `${{Postgres.DATABASE_URL}}` 로 넣는다(값 복사 불필요) |
| `LLM_API_KEY` | copa 키. AI 관련해서 꼭 넣어야 하는 값은 이것뿐입니다 |
| `LLM_BASE_URL` | 기본값(copa)을 쓰면 넣지 않아도 됩니다 |
| `LLM_API_STYLE` | 요청 형식(`anthropic` 또는 `openai`) |
| `LLM_MODEL` | 기본값 `claude-sonnet-4`. 바꿀 때는 `claude-haiku-4`만 가능 |
| `LLM_TIMEOUT_SECONDS` | AI API 호출 제한 시간(초) |
| `LLM_MAX_COMPLETION_TOKENS` | 응답 최대 토큰 수 |
| `SESSION_HTTPS_ONLY` | 운영이므로 `true` |
| `ENABLE_API_DOCS` | 운영이므로 `false` (`/docs`·`/openapi.json` 비노출) |
| `LOG_FILE_PATH` | 선택. 영속 볼륨을 쓸 때만 경로를 넣는다(예: `/data/logs/app.log`). 콘솔 로그와 같은 형식으로 파일에도 남고, 열 수 없으면 경고만 남긴다 |
| `PORT` | 입력하지 않는다 — Railway가 런타임에 자동 주입 |

`DATABASE_URL` 스킴은 손대지 않아도 됩니다. `backend/app/database.py`의 `build_engine()`이
`postgres`·`postgresql`·`postgresql+psycopg`를 모두 받아 `postgresql+psycopg`로 정규화하므로
Railway가 주입하는 `postgresql:` 스킴 URL을 그대로 써도 됩니다. 단 PostgreSQL URL이 아니거나
DB 이름이 비어 있으면 `ValueError`가 나고 인증 API가 503 `DB_NOT_CONFIGURED`로 응답합니다
(`backend/app/dependencies.py`의 `get_db`). 이때도 `/health`는 정상으로 보이니 DB 오류를 `/health`로 판별하지 마세요.

## 최초 배포 절차

1. **저장소 admin이 브라우저에서** Railway에 GitHub App을 설치하고 `innurhap28/Next-Star-Hunter.bot`
   저장소 접근을 허용한다.
2. Railway에서 New Project를 만든다.
3. `Deploy from GitHub repo` → 위 저장소를 고른다.
4. 브랜치를 `main`으로 지정한다.
5. `## Railway 서비스 설정` 표의 값을 Settings에 입력한다.
6. `New` → `Database` → `PostgreSQL` 플러그인을 추가한다.
7. `## 환경변수` 표의 변수를 추가하고(값은 팀이 입력), `DATABASE_URL`은 참조 변수로 연결한다.
8. Deploy를 누르고 Build Logs → Deploy Logs 순서로 확인한다.
9. 도메인을 발급받는다(Settings → Networking → Generate Domain).

## 배포 확인

```bash
curl -s https://<도메인>/health
# 기대: {"status":"ok","service":"next-star-hunter"}
```

자동 스모크 검사는 `.github/workflows/deploy-smoke.yml`이 담당합니다. 이 워크플로는 저장소 변수
`DEPLOY_URL`을 읽으므로, **스킴(`https://`)을 뺀 호스트만** 넣습니다.

```bash
gh variable set DEPLOY_URL --body <호스트>
```

변수가 없으면 워크플로는 실패하지 않고 notice만 남기고 건너뜁니다.

## 롤백

대시보드 → 서비스 → Deployments에서 직전 정상 배포를 고르고 `Redeploy`를 누릅니다.
CLI로 특정 배포를 되돌리는 방법은 따로 정리하지 않았습니다.
급하면 문제 커밋을 revert하는 PR을 `develop`에 병합한 뒤, `develop` → `main` 릴리스 PR로 반영하는 방법이 가장 확실합니다. `main`에는 직접 PR을 만들지 않습니다.

## 문제 해결

| 증상 | 먼저 볼 곳 |
| --- | --- |
| 빌드 실패 | Railway **Build Logs**. `requirements.txt` 설치 오류·Python 버전 불일치를 확인 |
| 배포는 됐는데 헬스체크 실패 | Start Command에 `--app-dir backend`가 빠졌는지, `--port $PORT` 대신 고정 포트를 썼는지 |
| `/health`는 200인데 로그인·조회가 503 | `DB_NOT_CONFIGURED`면 `DATABASE_URL`, `AUTH_NOT_CONFIGURED`면 `SECRET_KEY`(32자 이상)와 DB URL 존재 여부 |
| 쿠키가 저장되지 않음 | `SESSION_HTTPS_ONLY=true`인데 HTTP로 접속했는지 확인 |

## 데이터(나무위키 덤프)

스타 프로필 자료의 출처는 나무위키 덤프이며 라이선스는 CC BY-NC-SA 2.0 KR입니다. 비영리 목적으로만 사용하고 출처를 표시합니다. 원본 데이터는 저장소에 커밋하지 않습니다.
