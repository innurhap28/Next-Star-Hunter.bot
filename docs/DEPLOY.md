# 배포 런북

이 문서는 운영 배포를 처음 하거나 다시 할 때 그대로 따라 하는 절차입니다. 값(비밀 키·비밀번호)은
문서에 적지 않고 Railway 대시보드에서 팀이 직접 입력합니다.

## 배포 대상

| 항목 | 값 |
| --- | --- |
| 서비스 주소 | https://next-star-hunter-production.up.railway.app |
| 배포 플랫폼 | Railway (GitHub 연동 자동배포) |
| Railway 프로젝트 소유자 | 황승재님 |
| 저장소 | `innurhap28/Next-Star-Hunter.bot` |
| 배포 브랜치 | `main` |
| 자동배포 조건 | `main`에 릴리스 PR이 병합되고 그 커밋의 CI(`lint`, `test`)가 통과하면 Railway가 빌드·배포를 시작한다 |
| GitHub Secrets | 0개 (Railway가 저장소를 직접 감시하므로 토큰이 필요 없다) |
| 데이터베이스 | 같은 Railway 프로젝트의 PostgreSQL |

## Railway 서비스 설정

서비스(Settings 탭)에 아래 값을 넣습니다. Railway 설정 파일(`railway.toml` 등)은 만들지 않고 설정은 대시보드에서만 관리합니다.

| 항목 | 값 | 이유 |
| --- | --- | --- |
| Root Directory | `/` (비움) | 저장소 루트에 `requirements.txt`와 `backend/`가 같이 있다 |
| Wait for CI | 켬 | GitHub의 CI가 통과한 커밋만 배포한다 |
| Pre-deploy Command | `PYTHONPATH=backend python -m app.init_db` | 새 버전을 띄우기 전에 테이블을 만든다. 이미 있는 테이블은 그대로 두고 없는 테이블만 추가한다. 대화방 기능 전 DB면 `chat_logs.conversation_id` 열을 더하고 기존 대화를 사용자별 `이전 대화` 방으로 묶는다(다시 실행해도 바뀌지 않음, [DATABASE.md](DATABASE.md#기존-db-업그레이드)). 실패하면 배포가 멈추고 이전 버전이 계속 돈다 |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir backend` | 앱 모듈이 `backend/app/main.py`라서 `--app-dir backend`가 필요하고, `$PORT`(Railway 주입)를 그대로 바인딩해야 라우팅이 붙는다 |
| Healthcheck Path | `/health` | DB·AI 설정 없이 `{"status":"ok","service":"next-star-hunter"}`를 돌려준다. 이 응답이 와야 새 배포로 트래픽이 넘어간다 |
| Restart Policy | `ON_FAILURE` | 앱이 죽었을 때만 재시작하고 정상 배포를 반복 재시작하지 않는다 |
| App Sleeping (Serverless) | 끔 | 요청이 없을 때 잠들면 첫 요청이 느려지고, 그 사이 AI 호출이 시간 초과로 보일 수 있다 |
| 리전(권고) | `asia-southeast1` | 국내 사용자 지연을 줄이기 위한 권고값이며 강제는 아니다 |

## 환경변수

Variables 탭에서 **이름만** 만들고 값은 팀이 직접 입력합니다. 저장소·PR·이 문서에 값을 남기지 마세요. 표에 없는 `LLM_*` 변수는 넣지 않으면 기본값(copa 주소, `anthropic` 형식, `claude-sonnet-4`, 90초, 8000토큰)을 씁니다. AI 관련해서 꼭 넣어야 하는 값은 `LLM_API_KEY` 하나입니다.

| 변수 | 운영 값 | 설명 |
| --- | --- | --- |
| `SECRET_KEY` | 필수 | 팀이 직접 생성: `python -c "import secrets; print(secrets.token_hex(32))"`. **32자 이상**이어야 인증이 켜진다(`backend/app/config.py`의 `auth_configured()`). 바꾸면 모든 사용자가 로그아웃된다 |
| `DATABASE_URL` | 필수 | Postgres 서비스의 참조 변수 `${{Postgres.DATABASE_URL}}`로 넣는다(값 복사 불필요) |
| `LLM_API_KEY` | 필수 | copa 키 |
| `SESSION_HTTPS_ONLY` | `true` | 세션 쿠키를 HTTPS에서만 보낸다 |
| `ENABLE_API_DOCS` | `true` | `/docs`(Swagger UI)·`/openapi.json`을 열어 API를 확인할 수 있게 한다. 닫으려면 `false` |
| `LOG_FILE_PATH` | 선택 | 영속 볼륨을 붙였을 때만 경로를 넣는다(예: `/data/logs/app.log`). 콘솔 로그와 같은 형식으로 파일에도 남고, 열 수 없으면 경고만 남긴다 |
| `ADMIN_EMAIL` | 선택 | 관리자 계정 이메일. 이 계정만 `/api/admin/*`를 쓸 수 있다. 이 이메일로는 회원가입이 막혀 있어 Pre-deploy의 `init_db`로만 만들어진다. 이미 있는 계정을 지정하면 운영자 본인 계정인지 먼저 확인한다. 비우면 관리자 없음 |
| `ADMIN_PASSWORD` | 선택 | 관리자 비밀번호(8자 이상). Pre-deploy의 `init_db`가 계정이 없을 때만 만들고 기존 비밀번호는 덮어쓰지 않으므로, 계정이 만들어진 뒤에 값을 바꿔도 반영되지 않는다 |
| `PORT` | 넣지 않음 | Railway가 런타임에 자동 주입 |

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
6. `New` → `Database` → `PostgreSQL`을 추가한다.
7. `## 환경변수` 표의 변수를 추가하고(값은 팀이 입력), `DATABASE_URL`은 참조 변수로 연결한다.
8. Deploy를 누르고 Build Logs → Deploy Logs 순서로 확인한다. Pre-deploy 단계에서
   `Database tables ready`가 나오면 테이블이 준비된 것이다.
9. 도메인을 발급받는다(Settings → Networking → Generate Domain).
10. 스타 자료를 적재한다(아래 `## 스타 자료 적재`). 적재하지 않아도 채팅은 참고 자료 없이 동작한다.

## 배포 확인

```bash
curl -s https://next-star-hunter-production.up.railway.app/health
# 기대: {"status":"ok","service":"next-star-hunter"}
```

브라우저로 서비스 주소에 들어가면 `/auth`로 이동해야 하고, 가입·로그인 뒤 질문을 보내 답변과 출처 줄이 나오는지 확인합니다.

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
| Pre-deploy 단계 실패 | Deploy Logs의 `DB initialization failed (오류 종류)`. `DATABASE_URL` 참조 변수와 Postgres 서비스 상태를 확인 |
| 로그인은 되는데 채팅만 `503 AI_NOT_CONFIGURED` | `LLM_API_KEY`가 비어 있는지 확인 |
| 답변에 출처 줄이 전혀 붙지 않음 | 스타 자료를 적재했는지 확인. Deploy Logs의 `star_search_done ... hits=0`, `star_search_failure`를 본다 |

## 스타 자료 적재

스타 자료(`star_profiles`, `star_chunks`)는 앱이 아니라 적재 스크립트가 채웁니다. Railway PostgreSQL은 기본적으로 프로젝트 안에서만 접속되므로, 적재할 때만 TCP Proxy를 켜고 끝나면 끕니다.

1. Railway → Postgres 서비스 → Settings → Networking에서 TCP Proxy를 켠다.
2. Postgres 서비스의 Variables에서 `DATABASE_PUBLIC_URL`(TCP Proxy 주소)을 확인한다. 값은 터미널 환경 변수로만 쓰고 파일에 저장하지 않는다.
3. 덤프 추출 결과(`data/namu/`)가 있는 PC의 저장소 루트에서 적재한다.

   ```bash
   python -m scripts.namuwiki.load --input data/namu --database-url "$DATABASE_PUBLIC_URL"
   ```

4. 끝나면 TCP Proxy를 끈다. 앱은 내부 주소(`DATABASE_URL`)로 접속하므로 영향이 없다.

적재는 트랜잭션 하나라서 실패하면 이전 데이터가 그대로 남습니다. 추출 방법과 적재 옵션은 [DATA.md](DATA.md)에 있습니다.

## 데이터(나무위키 덤프)

스타 프로필 자료의 출처는 나무위키 덤프이며 라이선스는 CC BY-NC-SA 2.0 KR입니다. 비영리 목적으로만 사용하고, 자료를 쓴 답변에는 서버가 출처 줄을 붙입니다. 원본 데이터와 추출 결과는 저장소에 커밋하지 않습니다.
