from pathlib import Path

from cockpit_runtime import render_cockpit
from onetouch_agent import (DEMO_DATE, QUESTION_GROUPS, WELCOME_MESSAGE, ManufacturingAgent,
                            OnetouchToolRegistry, create_repository, quote_snapshot,
                            risk_label, timestamp, user_question_history)


BASE_DIR = Path(__file__).parent
repository = create_repository(BASE_DIR / "data" / "onetouch_demo.db")
registry = OnetouchToolRegistry(repository)
kpi = repository.dashboard(DEMO_DATE)


def agent_factory(client, model, tools):
    return ManufacturingAgent(client, model=model, factory_tools=tools)


def snapshot(quote_id):
    data = quote_snapshot(repository, quote_id)
    quote = data["quote"]
    drawing = data["drawing"]
    estimate = data["estimate"]
    risk, icon = risk_label(data)
    approvals = [f"{row['owner_role']}: {row['decision']}" for row in data["approvals"]]
    if drawing.get("exception_reason"):
        approvals.insert(0, f"설계·견적: {drawing['exception_reason']}")
    confidence = float(estimate.get("confidence") or 0) * 100
    return {
        "risk": risk,
        "icon": icon,
        "primary_label": "제품·고객",
        "primary": f"{quote.get('product_family', '-')} · {quote.get('customer', '-')}",
        "progress": None,
        "caption": f"신뢰도 {confidence:.0f}% · {estimate.get('review_route', '-')} · 납기 {quote.get('due_at', '-')}",
        "counts": [("BOM", len(data["bom"])), ("공정", len(data["routing"])), ("승인", len(data["approvals"]))],
        "approvals": approvals,
        "brief": f"{quote_id}의 도면 Feature·BOM·Routing·원가·유사견적·소재위험과 승인사항을 브리핑해줘",
    }


render_cockpit(
    base_dir=BASE_DIR,
    page_title="원터치 CAD 견적 Agent Cockpit",
    icon="📐",
    title="원터치 CAD 견적 AI Agent",
    subtitle="도면의 선과 구멍을 제조 언어로 번역해, BOM·공정·원가·승인까지 한 대화로 잇습니다.",
    repository=repository,
    registry=registry,
    agent_factory=agent_factory,
    question_groups=QUESTION_GROUPS,
    welcome_message=WELCOME_MESSAGE,
    timestamp=timestamp,
    history_fn=user_question_history,
    metrics=[
        ("오늘 신규견적", f"{kpi['new_quotes']}건"),
        ("도면 검토필요", f"{kpi['drawing_reviews']}건"),
        ("승인대기", f"{kpi['approval_pending']}건"),
        ("수작업 전환", f"{kpi['manual_routes']}건"),
        ("평균 신뢰도", f"{kpi['average_confidence']}%"),
        ("소재 위험", f"{kpi['material_risks']}건"),
    ],
    entity_label="견적",
    entity_ids=[row["quote_id"] for row in repository.quote_requests(None)],
    snapshot_builder=snapshot,
    knowledge_label="도면표준·원가기준·공정능력·견적승인 문서",
    knowledge_base_name="원터치 CAD 견적 지식베이스",
    source_label="원터치 견적 Data Hub",
    chat_placeholder="도면·Feature·BOM·Routing·원가·소재에 질문하세요",
    safety_note="모든 도면·원가·신뢰도는 미검증 데모입니다. 견적확정·고객발송·수주전환·소재대체는 사람이 승인합니다.",
)
