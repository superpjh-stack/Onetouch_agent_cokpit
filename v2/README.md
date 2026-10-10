# 원터치 AI Agent V2

니즈푸드 최신 프로젝트 `e032b50`(2026-10-10)의 화면·호출명 흐름을 2026-10-11에 반영했습니다. 설치된 스킬의 니즈푸드 번들은 2026-09-28이므로 이번 변경은 최신 원본을 직접 대조했습니다. 회사 데이터는 원터치 견적·CAD 데이터이며 PostgreSQL, 읽기 전용 도구와 연결 설정을 유지합니다.

- 왼쪽 질문·최근 이력, 중앙 대화, 오른쪽 지식베이스·DB 및 최신 고객용 디자인.
- 질문은 **“원터치, 선택 견적의 원가를 알려줘”**처럼 시작합니다. “원터치야”, “원터치님”도 허용합니다. 직접 입력·과거 이력에 호출명을 자동 삽입하지 않습니다.
- 문자·서버에서 호출명을 검사하고 음성에서는 최종 전사 후 호출된 질문만 순차 처리합니다. 주변 발화는 응답 문맥에서 제거합니다. VAD 자동 응답·끼어들기는 끄고, 도구 결과와 음성 재생 완료 후 다음 호출 질문을 처리합니다.
- 답변 복사에는 질문·답변·대상 견적·근거 문서가 포함됩니다. HTTPS에서는 Clipboard API, HTTP에서는 복사 대체 처리를 사용합니다.
- AI 연결 여부에 따라 AI/데모를 선택하며 데모와 샘플 근거 표시를 유지합니다. 기존 초기화·연결 제한시간·키 교체 정리 동작을 보존합니다.

## 실행

Python 3.12와 Node 22 이상을 사용합니다. 기존 Streamlit V1은 루트 `app.py`로 계속 실행할 수 있습니다.

```sh
python3.12 -m venv .venv-v2
.venv-v2/bin/pip install -r v2/requirements.lock
npm ci --prefix v2/web
npm run build --prefix v2/web
./scripts/run_v2.sh
```

주소: http://127.0.0.1:8517

개발 화면: `npm run dev --prefix v2/web` → http://127.0.0.1:5177 (API는 8517에서 별도 실행).

## 사용 흐름

- 오른쪽 지식베이스: 문서 검색과 원문 모달. 데이터허브: 12개 허용 테이블, 첫 10개 원본 레코드 상세.
- 중앙: 전체/개별 견적 선택, 직접 질문, 근거 펼침, 대화 초기화.
- 왼쪽: 세션 질의이력 최대 20개, 견적·도면/문서·규칙 추천질문 각각 10개.
- 모바일: 자료·질문 버튼으로 보조 패널 열기.
- 실시간 음성: WebRTC 연결, 자막, 읽기 전용 견적 도구 12개, 음소거, 종료, 호출된 질문 순차 처리. 답변 듣기는 TTS이며 수동 재생·중지를 지원합니다. 음성 연결은 30초 제한시간을 적용하며 취소·오류·견적 변경 시 요청과 마이크를 정리합니다.
- 음성 도구는 완료된 응답의 호출들을 모아 결과를 전달하고 후속 응답을 한 번만 생성합니다. 중복 이벤트·취소된 응답·종료 후 늦은 도구 결과를 차단합니다. 키를 저장·교체하면 대화와 음성 연결을 새로 시작합니다. 대화 초기화는 서버 응답을 기다리지 않고 즉시 진행합니다.
- 견적·접근 코드·응답 방식 변경 시 진행 중 문자 응답을 취소하고 음성 자원을 정리합니다. 서버에 공유 대화 ID를 보관하지 않으며 문자 대화의 최근 6턴만 요청 문맥으로 보냅니다.

## 설정과 데이터

필요한 항목을 `v2/.env.example`에서 루트 `.env`로 가져옵니다. 기존 `.env`를 덮어쓰지 마세요.

- 서버 `OPENAI_API_KEY`: AI 분석·음성에 필요. **연결 설정 → OpenAI API 키 → API 키 저장**에서 입력합니다. 설정 화면 바로가기: http://127.0.0.1:8517/?setup=openai
- API 키 설정은 직접 로컬·동일 출처 요청만 허용합니다. 설정된 음성 모델의 접근 권한을 확인한 뒤 루트 `.env`를 원자적으로 갱신하고 권한 0600으로 저장합니다. 다른 설정은 보존하며 키를 응답·로그·브라우저 저장소에 반환하지 않습니다. 실제 대화 품질이나 과금 한도까지 보장하는 검증은 아닙니다. 셸에서 `OPENAI_API_KEY`를 별도 export한 경우 재시작 전에 그 값도 정리하세요.
- 직접 로컬 접속은 접근 코드 입력 없이 사용합니다. 외부 접근 코드는 localStorage에 보관하고 기존 sessionStorage 값을 이전합니다. 연결 설정에서 교체·삭제하며 API 키와 별개입니다. 저장된 코드 변경은 다른 열린 탭에도 반영됩니다. 질문 이력은 sessionStorage를 유지합니다.
- `OPENAI_MODEL`, `OPENAI_REALTIME_MODEL`, `OPENAI_REALTIME_VOICE`: 모델/음성 설정. 기본값은 스킬 스냅샷 기준이며 계정 가용성 확인이 필요합니다.
- `COCKPIT_ACCESS_TOKEN`: 외부의 유료 AI 경로 접근 코드. 로컬 예외는 요청 호스트와 클라이언트가 모두 루프백이고 전달 헤더가 없을 때만 적용합니다. 실행 스크립트의 `--no-proxy-headers`를 유지하세요.
- `DATABASE_URL` 또는 기존 `POSTGRES_URL`: 기존 PostgreSQL 어댑터 사용. 미설정이면 기존 `data/onetouch_demo.db`. 선택적 `ONETOUCH_DB_PATH`로 별도 SQLite 경로를 지정합니다.

데모는 정해진 키워드·DB·문서 검색이며 자연어 AI 분석이 아닙니다. 모든 견적·원가·신뢰도는 2026-09-04 샘플이며 문서와 규칙은 미승인입니다. 원가 모델 실행, CAD 파일 Parsing, ERP 실연동, 견적 승인·고객발송은 구현 완료 기능이 아닙니다.

현재 서비스는 로컬용입니다. 접근 코드는 유료 AI API만 보호하며 문서·DB 조회는 공개 경로입니다. 외부 공개 배포에는 별도 사용자 인증과 데이터 접근 제어가 필요합니다. 업무 저장·인계·사용자 계정 UI는 이번 범위에 없습니다. 대화/이력은 브라우저 세션 범위이며 영구 업무 저장이 아닙니다.

## 검증

```sh
.venv-v2/bin/python -m pytest tests v2/tests -q
npm run build --prefix v2/web
# 별도로 Playwright와 Chromium이 설치된 환경
node v2/tests/wake-voice.cjs
node v2/verification/ui-check.cjs
node v2/verification/voice-check.cjs
node v2/verification/settings-check.cjs
```

브라우저 확인용 스크립트는 `PLAYWRIGHT_MODULE`에 설치된 Playwright 모듈 경로를 지정할 수도 있습니다. 검증 결과는 [verification/RESULTS.md](verification/RESULTS.md)에 기록합니다.

음성 연결 형식은 [OpenAI WebRTC 공식 문서](https://developers.openai.com/api/docs/guides/voice-webrtc)를 참고했습니다. 실제 유료 AI·음성, 실기기 마이크, PostgreSQL, Docker 및 외부 배포는 별도 검증 대상입니다.

음성 도구 후속 응답 구현은 [OpenAI Realtime 대화 공식 문서](https://developers.openai.com/api/docs/guides/realtime-conversations)의 `response.done`과 `function_call_output`, `response.create` 규약을 따릅니다.

## V2 Docker 배포

저장소 루트를 빌드 컨텍스트로 사용하는 `v2/Dockerfile`은 React 화면을 빌드한 뒤 FastAPI를 일반 사용자로 실행합니다. 내부 포트는 기존 컨테이너와 같은 8501입니다.

기존 Compose 프로젝트의 이름·환경파일·PostgreSQL 볼륨을 유지하고 먼저 DB를 백업한 뒤 실행합니다:

```sh
docker compose -f docker-compose.yml -f v2/docker-compose.yml config --quiet
docker compose -f docker-compose.yml -f v2/docker-compose.yml build app
docker compose -f docker-compose.yml -f v2/docker-compose.yml up -d --no-deps app
```

이 명령은 이미 실행 중인 기존 PostgreSQL을 사용합니다. 신규 설치에서는 `--no-deps`를 제외합니다. 기본 외부 포트는 기존 8507이며 기존 호스팅 설정이 다르면 그 포트 매핑을 유지하세요. `down -v`나 DB 초기화는 실행하지 않습니다. `/api/health`와 견적 조회를 확인한 뒤 배포 완료로 판단합니다.

서버 API 키와 외부 AI 접근 코드는 배포 호스트 환경파일의 `OPENAI_API_KEY`, `COCKPIT_ACCESS_TOKEN`으로 공급합니다. 브라우저 키 설정은 직접 로컬용이므로 외부 Docker 접속에서 허용되지 않습니다. 외부 음성 마이크에는 HTTPS가 필요합니다. 문서·DB 조회는 공개 경로이므로 운영 데이터 공개 시 별도 인증이 필요합니다.
