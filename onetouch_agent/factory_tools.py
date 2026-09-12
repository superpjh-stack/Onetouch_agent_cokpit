from __future__ import annotations

import json
from typing import Any, Callable

from .data_hub import OnetouchRepository


def nullable_string(description: str) -> dict[str, Any]:
    return {"type": ["string", "null"], "description": description}


class OnetouchToolRegistry:
    def __init__(self, repository: OnetouchRepository) -> None:
        self.handlers: dict[str, Callable[..., Any]] = {
            "get_quote_requests": repository.quote_requests,
            "get_drawing_features": repository.drawing_features,
            "get_bom": repository.bom,
            "get_routing": repository.routing,
            "get_cost_estimate": repository.cost_estimate,
            "compare_similar_quotes": repository.similar_quotes,
            "get_material_availability": repository.material_availability,
            "get_quote_review_queue": repository.approval_queue,
            "get_order_cost_feedback": repository.order_feedback,
            "get_rules": repository.rules,
            "search_local_knowledge": repository.search_knowledge,
            "browse_data_table": repository.browse_table,
        }

    @property
    def definitions(self) -> list[dict[str, Any]]:
        specs = [
            ("get_quote_requests", "견적 요청의 고객·제품군·수량·요청일·납기·상태를 조회한다.", {"quote_id": nullable_string("견적 ID, 전체이면 null")}),
            ("get_drawing_features", "도면의 길이·폭·높이·두께·재질·홀·슬롯·간격과 추출 신뢰도·예외를 조회한다.", {"drawing_id": nullable_string("도면 ID, 전체이면 null")}),
            ("get_bom", "도면 제조특징에서 생성한 견적 BOM과 재료금액 근거를 조회한다.", {"quote_id": {"type": "string", "description": "정확한 견적 ID"}}),
            ("get_routing", "피딩·롤포밍·타공·절단·포장 Routing과 예상 공수·비용을 조회한다.", {"quote_id": {"type": "string", "description": "정확한 견적 ID"}}),
            ("get_cost_estimate", "표준원가식과 XGBoost 후보 모델의 견적 원가·신뢰도·검토경로·기여요인을 조회한다.", {"quote_id": nullable_string("견적 ID, 전체이면 null")}),
            ("compare_similar_quotes", "유사 제품군의 과거 견적과 실제 제조원가 편차를 비교한다.", {"product_family": nullable_string("제품군, 전체이면 null")}),
            ("get_material_availability", "BOM 산출에 필요한 소재의 가용재고·예약재고·안전재고 위험을 조회한다.", {"risks_only": {"type": "boolean", "description": "부족 소재만 조회할지"}}),
            ("get_quote_review_queue", "견적·도면 예외·수작업 전환의 검토대기와 담당 역할을 조회한다.", {"quote_id": nullable_string("견적 ID, 전체이면 null"), "pending_only": {"type": "boolean", "description": "미완료 건만 조회할지"}}),
            ("get_order_cost_feedback", "견적에서 수주·생산으로 이어진 계획원가와 실제원가 피드백을 조회한다.", {"quote_id": nullable_string("견적 ID, 전체이면 null")}),
            ("get_rules", "견적·도면·소재의 샘플 판정 규칙과 담당자 후속조치를 조회한다.", {"source_table": nullable_string("원천 테이블명, 전체이면 null")}),
            ("search_local_knowledge", "도면 표준, 절차, 원가 기준, 승인 규정을 로컬 지식문서에서 검색한다.", {"query": {"type": "string", "description": "검색어"}, "limit": {"type": "integer", "minimum": 1, "maximum": 10, "description": "최대 결과 수"}}),
            ("browse_data_table", "허용된 Data Hub 테이블을 읽기 전용으로 조회한다.", {"table": {"type": "string", "enum": list(OnetouchRepository.TABLE_LABELS), "description": "조회 테이블"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}, "offset": {"type": "integer", "minimum": 0}}),
        ]
        return [{"type": "function", "name": name, "description": description, "strict": True,
                 "parameters": {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}}
                for name, description, properties in specs]

    def execute(self, name: str, arguments: str | dict[str, Any]) -> str:
        if name not in self.handlers:
            return json.dumps({"error": f"허용되지 않은 읽기 도구: {name}"}, ensure_ascii=False)
        try:
            values = json.loads(arguments) if isinstance(arguments, str) else arguments
            result = self.handlers[name](**values)
            return json.dumps({"status": "ok", "demo_data": True, "source": "원터치 견적 Data Hub", "tool": name, "result": result}, ensure_ascii=False, default=str)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return json.dumps({"error": str(exc), "tool": name}, ensure_ascii=False)
