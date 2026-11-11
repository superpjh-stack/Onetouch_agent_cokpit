# 원터치 에이전트 · make_best_agent 적용

기존 CAD 견적 V2의 저장소·API 키 설정·접근코드 기능을 유지하고 복합질문과 음성을 개선했습니다. 데이터와 지식문서는 모두 기존 2026-09-04 가상·미승인 자료입니다. 실제 CAD 추출, 모델 학습·검증, 견적 승인·고객 발송을 새로 구현한 것은 아닙니다.

- 데이터/지식베이스/복합질문 각 10개. 호출명 없이 질문하며 견적 선택창은 기본 화면에서 제거했습니다.
- LangGraph: 원문 요청 보존 → 원문 인용에 근거한 분해 → 범위 확인·다중 조회 → 답변 인용/근거 연결 검사 → 미확인 요청 최대 1회 보완.
- QT 견적과 DWG 도면 ID를 연결하고 최근 사용자 질문에서만 후속 견적을 확인합니다. 여러 견적을 명시하거나 선택 범위가 충돌하면 확인 요청을 반환합니다. ID 없는 전체 비교는 지원합니다.
- 선택 견적의 도면·BOM·공정·원가·검토·실적을 강제로 같은 범위로 조회합니다. 소재는 BOM 규격, 유사 견적은 제품군으로 제한하고 임의 테이블 조회는 금지합니다.
- 비교표는 원본 레코드만 사용합니다. 다른 스키마는 분리하고 0·null·단위를 보존합니다. 0원 원가는 입력 불충분 상태와 함께 해석해야 합니다.
- 실시간 음성도 같은 그래프를 사용합니다. 끼어들기 시 진행 중 브라우저 요청과 출력 오디오를 취소하며 이전 턴 응답·근거를 무시합니다. 별도 2~3문장 요약을 읽습니다. 서버에서 시작된 모델 호출 비용의 취소는 보장하지 않습니다.
- 블루·슬레이트·구리색 화면, PC 3열/모바일 패널, 하단 입력창, 새 답변 첫 부분 유지. 기존 답변 복사와 문서·레코드 상세 보기를 유지합니다.

## 실행과 확인

```sh
uv pip install --python .venv-v2/bin/python -r v2/requirements.lock
npm --prefix v2/web ci
npm --prefix v2/web run build
./scripts/run_v2.sh
```

기존 DB 대신 별도 샘플로 미리보기:

```sh
ONETOUCH_DB_PATH=/tmp/onetouch-best-agent-preview.db DATABASE_URL='' POSTGRES_URL='' .venv-v2/bin/uvicorn v2.api:app --host 127.0.0.1 --port 8522 --no-proxy-headers
```

검증 결과:

- `pytest tests v2/tests -q`: 46개 통과. 추천질문 30개 전체 조회, 견적 격리·도면 연결·후속 질문·부분 조회 실패·0/null·원문 밖 요청 배제·1회 보완·음성 그래프 경로·기존 키 설정 포함.
- 프런트엔드 빌드 통과.
- `v2/tests/browser-best-ui.cjs`: PC/390px 모바일, 추천질문 3그룹, 비교표·답변 시작점·새 대화 확인.
- `v2/tests/browser-best-voice.cjs`: 모의 WebRTC 실패/재연결/호출명 없는 질문/끼어들기/늦은 응답 차단/마이크 해제 확인.
- 실제 AI로 QT-260904-002 도면 예외·원가·검토 상태 복합질문과 요약 확인.

브라우저 검증은 `PLAYWRIGHT_MODULE` 모듈 경로, `PLAYWRIGHT_CHANNEL=chrome`, 필요 시 `ONETOUCH_URL`을 지정합니다. 기존 `wake-voice.cjs` 및 `verification/voice-check.cjs`는 과거 호출명 필수 정책의 기록이며 현재 정책 검증은 `browser-best-voice.cjs`를 사용합니다. 실제 마이크 음질과 이번 버전의 운영 배포는 아직 검증하지 않았습니다.
