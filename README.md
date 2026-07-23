# 매일미사 말씀 추출기

한국천주교주교회의 매일미사 페이지에서 날짜별 제1독서, 제2독서, 선택·대체
독서와 복음을 가져와 브라우저에서 읽고 하나의 UTF-8 TXT 파일로 내려받는
Streamlit 앱입니다. 기존 [`missa_extract.py`](missa_extract.py)의 공개 추출
함수를 재사용하며 OpenAI API나 API 키를 사용하지 않습니다.

앱의 시작 파일은 프로젝트 루트의 `app.py`입니다.

## 로컬 실행

Python 3.9 이상을 권장합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
streamlit run app.py
```

`streamlit` 명령이 PATH에 없다고 나오면 같은 앱을 다음처럼 실행할 수 있습니다.

```bash
python3 -m streamlit run app.py
```

명령을 실행하면 브라우저에서 보통 `http://localhost:8501`이 열립니다. 화면에서
빠른 날짜 또는 직접 날짜 범위를 고르고 **말씀 추출하기**를 누르세요. 성공한
날짜가 하나 이상이면 **TXT 파일 다운로드** 버튼이 나타납니다.
각 날짜의 **이 날짜 본문 복사** 버튼으로 해당 날짜의 말씀 전체를 복사할 수 있고,
여러 날짜를 추출했을 때는 **전체 본문 복사** 버튼으로 성공한 모든 날짜를 한 번에
복사할 수 있습니다. 복사되는 내용은 날짜·독서 제목·성경 본문을 TXT와 같은 순서로
유지합니다.

## 테스트

실제 사이트를 반복 호출하지 않도록 웹 앱 보조 함수 테스트는 mock을 사용합니다.
기존 CLI 추출기 테스트도 같은 명령으로 모두 실행됩니다.

```bash
python3 -m unittest discover -s tests -v
```

## GitHub 저장소 만들기와 push

현재 폴더가 아직 Git 저장소가 아닐 때만 첫 번째 명령을 실행합니다. 아래의
`사용자명`과 `저장소명`은 실제 GitHub 값으로 바꿔야 합니다.

```bash
git init
git add app.py missa_web.py missa_extract.py requirements.txt README.md .gitignore tests
git commit -m "Add Streamlit Daily Missa extractor"
git branch -M main
git remote add origin https://github.com/사용자명/저장소명.git
git push -u origin main
```

이미 `origin`이 설정되어 있다면 `git remote add origin ...`은 생략합니다. 이
프로젝트는 사용자 허락 없이 원격 저장소를 만들거나 push하지 않습니다.

## Streamlit Community Cloud 배포

1. 위 파일들을 GitHub의 공개 또는 접근 가능한 비공개 저장소에 push합니다.
2. [Streamlit Community Cloud](https://share.streamlit.io/)에 로그인합니다.
3. **Create app** 또는 **New app**을 선택합니다.
4. 다음 값을 지정합니다.

   ```text
   Repository: 사용자의 GitHub 저장소
   Branch: main
   Main file path: app.py
   ```

5. 배포를 시작하고 로그에서 `requirements.txt` 설치와 앱 기동을 확인합니다.
6. 배포된 화면에서 날짜 한 건을 추출하고 TXT 다운로드까지 확인합니다.

Secrets 설정은 필요하지 않습니다. 이 앱은 `OPENAI_API_KEY`와 OpenAI API를
사용하지 않습니다.

## 동작과 제한 사항

- 모든 상대 날짜는 `Asia/Seoul` 기준입니다.
- 한 번의 요청은 최대 31일이며, 날짜별 요청 사이에 짧은 간격을 둡니다.
- 성공한 날짜는 한 시간 동안 캐시하고, 추출 오류는 장시간 보관하지 않습니다.
- 날짜 하나가 실패해도 나머지 날짜를 계속 처리합니다.
- 매일미사 사이트의 HTML 구조가 바뀌면 추출 결과에 영향을 받을 수 있습니다.
- 내려받는 TXT는 메모리에서 만들기 때문에 서버에 영구 저장하지 않습니다.

---

# 기존 하루 앱

하나의 목표를 오늘의 할 일로 나누고, 캘린더와 실행 문서에서 기록을 이어 보는 개인 실행 관리 MVP입니다. UI와 이메일은 한국어이며 모든 실제 시각은 PostgreSQL `timestamptz`(UTC)로 저장하고 화면에서 `Asia/Seoul` 기준으로 표시합니다.

## 구현 범위

- 이메일 Magic Link 로그인과 첫 목표 온보딩
- 단일 활성 목표, 오늘 할 일 생성·수정·완료·막힘·삭제
- 예상 시간, 완료 기준, 정렬 순서 지원
- 월간 캘린더, 날짜별 개수와 선택 날짜 목록
- 목표·성공 기준·자동 저장 메모·주간 계획·완료/막힘 기록·주간 요약을 합친 실행 문서
- 이메일/시간/사용 여부/시간대 설정과 즉시 테스트
- `CRON_SECRET`으로 보호한 due reminder endpoint
- 사용자·날짜별 중복 발송 방지 및 성공/실패 기록
- Resend가 없을 때 서버 로그와 UI 미리보기를 쓰는 개발 provider
- 390px부터 데스크톱까지 대응하는 모바일 우선 UI와 하단 내비게이션

## 주요 구조

```text
src/
  app/
    api/reminders/due/     # cron용 보호 endpoint
    api/reminders/test/    # 로그인 사용자 테스트 메일
    auth/callback/         # Magic Link callback
    login/                 # 로그인 화면
  components/              # 오늘, 캘린더, 실행 문서, 설정, 편집 sheet
  lib/
    notifications/         # provider 인터페이스, Resend/console, 중복 방지 서비스
    supabase/              # browser/server/admin client
    date.ts                # KST↔UTC, 캘린더 계산
    task-domain.ts         # 순수 CRUD/조회 로직
supabase/
  migrations/              # schema, trigger, RLS
  tests/rls.sql            # 실제 Postgres RLS 격리 테스트
  seed.sql                 # 선택적 로컬 seed
```

## 외부 키 없이 로컬 실행

Node.js 20 이상과 pnpm이 필요합니다.

```bash
cp .env.example .env.local
pnpm install
pnpm dev
```

`.env.example`의 `NEXT_PUBLIC_DEMO_MODE=true`를 유지하면 Supabase와 Resend 없이 실행됩니다. 데모 데이터는 브라우저 `localStorage`에만 저장되며 설정의 “데모 데이터 초기화”로 되돌릴 수 있습니다. 개발 모드의 테스트 이메일은 실제로 전송하지 않고 서버 로그와 설정 화면에 제목/본문을 표시합니다.

## 환경변수

| 이름 | 용도 |
| --- | --- |
| `NEXT_PUBLIC_DEMO_MODE` | `true`면 외부 서비스 없는 로컬 데모 |
| `NEXT_PUBLIC_APP_URL` | 이메일의 오늘 화면 링크와 배포 URL |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase 프로젝트 URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | 브라우저용 publishable/anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | cron endpoint의 서버 전용 key. 클라이언트 노출 금지 |
| `RESEND_API_KEY` | 실제 이메일 전송. 없으면 console provider |
| `REMINDER_FROM_EMAIL` | Resend에서 검증한 발신 주소 |
| `CRON_SECRET` | cron endpoint Bearer 인증 secret |

실제 값이 든 `.env.local`은 Git에 포함하지 않습니다.

## Supabase 설정

1. 새 Supabase 프로젝트를 만들고 SQL Editor에서 `supabase/migrations/20260721000000_initial_haru.sql`을 실행합니다. Supabase CLI를 사용한다면 `supabase db push`로 적용할 수 있습니다.
2. Authentication > URL Configuration에서 Site URL을 배포 URL로 지정하고 Redirect URLs에 `http://localhost:3000/auth/callback`과 `https://배포주소/auth/callback`을 추가합니다.
3. Authentication > Providers > Email을 켭니다. 개발 중 즉시 확인하려면 이메일 확인/속도 제한 설정을 프로젝트 정책에 맞춰 조정합니다.
4. 프로젝트 URL, anon key, service role key를 배포 환경변수에 넣고 `NEXT_PUBLIC_DEMO_MODE=false`로 설정합니다.
5. 테스트 사용자를 만든 뒤 선택적으로 `supabase/seed.sql`을 실행할 수 있습니다. 앱 자체에도 현실적인 데모 데이터가 포함되어 있어 이 단계는 필수가 아닙니다.

Migration은 모든 사용자 테이블에 `user_id`를 두고 RLS를 활성화합니다. `auth.uid() = user_id` 정책으로 본인 행만 조회·변경할 수 있고, task의 `user_id`와 goal 소유자가 일치하는지 trigger로 한 번 더 확인합니다. 완료/막힘 전환은 메인 메모를 수정하지 않고 `daily_logs`에 별도 기록됩니다.

## Resend 설정

1. Resend에서 도메인과 발신 주소를 검증합니다.
2. `RESEND_API_KEY`, `REMINDER_FROM_EMAIL`을 서버 환경변수로 추가합니다.
3. 앱 설정에서 수신 주소를 저장한 뒤 “지금 테스트 알림 보내기”로 확인합니다.

provider 교체가 필요하면 `NotificationProvider`를 구현하고 `getNotificationProvider()`의 선택 로직만 바꾸면 됩니다. 발송 오류는 `notification_deliveries.status = failed`와 `error_message`에 기록되며 task transaction과 분리되어 있습니다.

## Cron 설정

Endpoint는 `GET`/`POST /api/reminders/due`이며 다음 헤더가 필수입니다.

```text
Authorization: Bearer <CRON_SECRET>
```

10분 간격 호출을 권장합니다. 사용자의 현지 시간이 설정 시간을 지났고 당일 `dedupe_key`가 없을 때만 발송하므로 cron 재시도에도 같은 일일 이메일이 중복 발송되지 않습니다.

### Vercel Cron

저장소의 `vercel.json`에 `*/10 * * * *` 일정이 포함되어 있습니다. Vercel 프로젝트 환경변수에 `CRON_SECRET`을 설정하면 Vercel Cron이 같은 Bearer 값을 사용합니다.

### Supabase Cron 예시

Database Extensions에서 `pg_cron`, `pg_net`, Vault를 활성화하고 URL/secret을 Vault에 저장한 다음 실행합니다.

```sql
select vault.create_secret('https://your-app.example.com', 'haru_app_url');
select vault.create_secret('replace-with-a-long-random-secret', 'haru_cron_secret');

select cron.schedule(
  'haru-due-reminders',
  '*/10 * * * *',
  $$
  select net.http_post(
    url := (select decrypted_secret from vault.decrypted_secrets where name = 'haru_app_url') || '/api/reminders/due',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'haru_cron_secret')
    ),
    body := '{}'::jsonb
  );
  $$
);
```

앱의 `CRON_SECRET`과 Vault secret은 같은 값이어야 합니다.

## 배포

Vercel에서 저장소를 가져오고 Framework Preset을 Next.js로 둡니다. 위 환경변수를 Production/Preview에 각각 입력한 뒤 배포합니다. 배포 후에는 다음을 확인합니다.

1. Supabase Site URL과 redirect URL이 실제 HTTPS 주소인지 확인합니다.
2. `NEXT_PUBLIC_APP_URL`을 실제 주소로 변경합니다.
3. 휴대폰에서 Magic Link 로그인, 오늘 할 일 CRUD, 캘린더, 실행 문서 자동 저장을 확인합니다.
4. 설정에서 테스트 이메일을 보낸 뒤 `notification_deliveries` 행을 확인합니다.
5. cron 실행 기록과 due endpoint 응답의 `sent`, `duplicate`, `failed`, `skipped` 수치를 확인합니다.

## 검증

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Vitest는 할 일 CRUD/날짜별 조회, KST 경계 변환, 알림 중복 방지, provider 오류 격리, migration의 RLS 정책을 검사합니다. Supabase CLI가 있다면 `supabase test db`로 `supabase/tests/rls.sql`의 두 사용자 실제 RLS 격리 테스트도 실행할 수 있습니다.

## 현재 제한 사항과 다음 단계

- 활성 목표는 사용자당 하나이며 목표 전환/보관 UI는 아직 없습니다.
- 리치 메모는 제목·굵게·목록·링크만 지원합니다. 협업형 블록 편집기는 범위 밖입니다.
- 알림 시간대 UI는 첫 MVP 요구에 맞춰 `Asia/Seoul`만 제공합니다.
- 복잡한 반복 작업, 드래그앤드롭, 외부 캘린더/문서 연동은 없습니다.
- Web Push와 오프라인 PWA 캐시는 다음 단계 TODO입니다.
