from __future__ import annotations

from datetime import datetime
from typing import Any


QUESTION_GROUPS = {
    "견적 DB": [
        "오늘 신규 견적의 신뢰도·예외·승인 우선순위를 브리핑해줘",
        "납기가 임박한 견적과 수작업 전환 건을 알려줘",
        "DWG-260904-002에서 추출한 길이·두께·홀·슬롯과 예외를 알려줘",
        "신뢰도 80% 미만 도면과 원본 확인사항을 알려줘",
        "QT-260904-001의 BOM과 공정 Routing 산출 근거를 설명해줘",
        "홀·슬롯 수가 공정시간과 원가에 미치는 영향을 알려줘",
        "QT-260904-002의 원가 구성과 주요 기여요인을 알려줘",
        "표준 잔넬의 유사 견적과 실제 제조원가 편차를 비교해줘",
        "가용재고가 부족한 소재와 영향을 받는 견적을 알려줘",
        "견적 승인대기 건의 근거 상태와 담당자를 정리해줘",
    ],
    "지식문서": [
        "원터치 CAD 견적의 표준 업무 흐름을 알려줘",
        "도면 개정번호가 없을 때 확인 절차를 알려줘",
        "CAD 제조 Feature 추출 항목과 검토 기준은 무엇이야?",
        "CAD Parsing과 OCR 결과가 다를 때 어떻게 해야 해?",
        "BOM과 공정 Routing 생성 기준을 설명해줘",
        "견적 원가를 어떤 항목으로 나누어 확인해야 해?",
        "견적 신뢰도 구간별 승인 절차를 알려줘",
        "소재가 부족할 때 대체 승인 절차를 알려줘",
        "견적 모델 검증 시 제품군별로 무엇을 봐야 해?",
        "견적 근거 추적성을 확보하는 방법을 알려줘",
    ],
    "판정 규칙": [
        "현재 등록된 샘플 판정 규칙을 요약해줘",
        "수작업 견적으로 전환되는 조건과 담당자를 알려줘",
        "소재 안전재고 부족 규칙과 다음 조치를 알려줘",
        "도면 개정 미확인 규칙에 걸린 견적을 찾아줘",
        "80~95% 신뢰도 견적의 승인 규칙을 알려줘",
        "95% 이상 견적도 사람이 승인해야 하는 이유를 알려줘",
        "QT-260904-002에 적용할 규칙 후보를 정리해줘",
        "QT-260904-003에 적용할 규칙 후보를 정리해줘",
        "자동 고객발송이 금지되는 근거를 알려줘",
        "규칙별 담당자와 근거 문서를 표로 정리해줘",
    ],
}

WELCOME_MESSAGE = {
    "role": "assistant",
    "content": "안녕하세요. 원터치 CAD 견적 Agent입니다.  \n도면 객체와 제조 Feature를 읽고 BOM·Routing·원가·유사견적·소재·승인 근거를 하나의 대화로 연결합니다.",
    "sources": [], "evidence": [], "data_tools": [], "created_at": "시작",
}


def timestamp() -> str:
    return datetime.now().strftime("%H:%M")


def user_question_history(messages: list[dict[str, Any]], limit: int = 8) -> list[dict[str, str]]:
    return [{"content": str(message.get("content", "")), "created_at": str(message.get("created_at", ""))}
            for message in reversed(messages) if message.get("role") == "user"][:limit]


def quote_snapshot(repository: Any, quote_id: str) -> dict[str, Any]:
    return repository.quote_snapshot(quote_id)


def risk_label(snapshot: dict[str, Any]) -> tuple[str, str]:
    if not snapshot:
        return "확인 필요", "⚪"
    confidence = float(snapshot["estimate"].get("confidence") or 0)
    exception = bool(snapshot["drawing"].get("exception_reason"))
    material_risk = any(row.get("status") == "부족" for row in snapshot.get("materials", []))
    score = (2 if confidence < .8 else (1 if confidence < .95 else 0)) + int(exception) + int(material_risk)
    return ("높음", "🔴") if score >= 3 else (("주의", "🟠") if score else ("안정", "🟢"))
