# 원터치 CAD 견적 AI Agent Cockpit

원터치의 CAD 도면 기반 수작업 견적을 `도면 표준화 → CAD 객체 추출 → 제조 Feature → BOM·공정 Routing → 원가 계산 → 견적 승인 → 생산실적 피드백`으로 연결하는 실행형 Streamlit 프로토타입입니다.

## 완성된 Agent Cockpit

- 상단: 신규견적, 도면검토, 승인대기, 수작업 전환, 신뢰도, 소재위험 KPI
- 왼쪽: 대화 이력과 `견적 DB / 지식문서 / 판정 규칙` 추천질문 각 10개
- 중앙: 견적 Data Hub와 로컬·업로드 문서 근거를 함께 조회하는 고대비 채팅 콘솔
- 오른쪽: 선택 견적 상황, 승인대기, 로컬 지식검색, 읽기 전용 DB·규칙 브라우저
- 설정: 마스킹된 API 키 출처, 모델, 검색 깊이와 OpenAI File Search 문서 인덱싱

API 키가 없어도 데모 견적·승인상황·지식문서·Data Hub를 확인할 수 있습니다. API 키를 연결하면 추천질문·과거 질문·직접입력·견적 브리핑이 하나의 대화 경로로 동작합니다. 모든 Agent 도구는 조회 전용이며 성공 응답에 `status: ok`, `demo_data: true`가 포함됩니다.

## 확인된 사업 배경

- 2014년 설립된 금속가공·기계제작 기업
- 잔넬·T바·각관·C형강 생산, 1차 적용은 표준 잔넬 3~5종과 주문형 잔넬
- 2024년 매출 30억원, 상시고용 8명, 2022년 자체 ERP 구축
- 주요 설비: 언코일러·어큐뮬레이터·피더·롤포밍기·고주파용접기
- 현행 CAD 견적은 수시간 소요, 하루 3~5건, 편차 약 ±10%
- 불량률 약 4%, 월 1~2회 비계획 정지, 물류·LOT 추적 미흡

## 적용 기술과 경계

- CAD Parsing(Autodesk API 후보)과 YOLOv8·OCR: 도면 객체·문자 추출
- Rule/GNN 후보: BOM과 공정 Routing 생성
- XGBoost＋표준원가식: 견적 원가 후보 산출
- SHAP: 원가 기여요인 설명
- Responses API Function Calling: 9개 읽기 전용 견적 도구
- File Search: 도면표준·원가기준·공정능력·승인규정 검색

품질예측과 예지보전은 구체 적용 범위와 데이터가 확인되지 않아 이번 프로토타입의 실행 기능에서 제외했습니다. MES를 대체한다고 가정하지 않으며, 기존 ERP와 입고·재고·수주·생산실적 데이터를 API 또는 조회 View로 연결하는 구조입니다.

## 목표와 데모 구분

| KPI | 목표 | 현재 표시 |
|---|---:|---|
| 견적 리드타임 | 80% 이상 단축 | 목표·미검증 |
| 견적 오차 | ±5% 이내 | 목표·미검증 |
| CAD 객체 인식 | 90% 이상 | 목표·미검증 |
| 견적 근거 추적 | 100% | 목표·미검증 |

화면의 도면, 고객, 수량, 소재단가, BOM, 공정시간, 원가와 신뢰도는 모두 `demo_data`입니다.

## 신뢰도 라우팅

- 95% 이상: 자동 산출 후보 → 담당자 최종 승인
- 80~95%: 담당자 확인·승인
- 80% 미만: 수작업 견적 전환

견적 확정, 고객발송, 수주전환, 소재 대체, BOM·공정 변경은 자동 실행하지 않습니다.

## 로컬 실행과 테스트

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py

python -m pytest -q
```

Python 명령이 `python3`인 환경에서는 위 명령을 `python3 -m ...` 형태로 실행하세요. `DATABASE_URL`이 없으면 SQLite 데모를 사용하고, 설정하면 PostgreSQL + pgvector를 운영 백엔드로 사용합니다.

## Docker Compose 배포

```bash
cp .env.example .env
# .env에서 POSTGRES_PASSWORD와 OPENAI_API_KEY 설정
docker compose up --build -d
```

Compose 배포 시 앱은 `http://localhost:8507`에서 열립니다. PostgreSQL healthcheck가 통과한 뒤 앱이 시작되며 데이터는 `onetouch_pgdata` 볼륨에 보존됩니다. `.env`와 API 키는 이미지에 복사되지 않습니다.

서버 키를 교체할 때는 배포 호스트의 환경변수 또는 Compose 옆 `.env`만 수정하고 `docker compose up -d --force-recreate app`으로 앱 컨테이너를 다시 만드세요. 전체 키는 화면 입력란에 미리 채워지지 않고 끝 네 자리만 표시됩니다.

## SQLite → PostgreSQL 이전

프로덕션 DB에 데모·검증 데이터를 옮길 때 DB 파일을 직접 복사하지 말고 마이그레이션 스크립트를 사용합니다.

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --database-url 'postgresql://onetouch:비밀번호@localhost:5432/onetouch'
```

기본 동작은 대상 테이블을 교체하므로 반복 실행해도 중복되지 않습니다. 기존 행을 보존해야 할 때만 `--append`를 추가하세요.

## 데이터와 승인 경계

- `sample_docs/` 문서와 `rules` 테이블은 모두 `샘플·미승인`입니다.
- SQLite는 오프라인 테스트와 첫 실행용이며 운영 아키텍처는 PostgreSQL + pgvector입니다.
- 견적확정, 고객발송, 수주전환, 소재대체, BOM·공정 변경은 Agent가 실행하지 않습니다.
- 문서 임베딩이나 API 키가 없어도 한국어 토큰·문자쌍 기반 로컬 검색은 계속 동작합니다.
