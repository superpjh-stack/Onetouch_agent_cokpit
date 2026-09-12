import json

import pytest

from onetouch_agent import OnetouchRepository, OnetouchToolRegistry


def test_dashboard_and_confidence_routing(tmp_path):
    repo = OnetouchRepository(tmp_path / "demo.db")
    dashboard = repo.dashboard("2026-09-04")
    assert dashboard == {"new_quotes": 3, "drawing_reviews": 2, "approval_pending": 3,
                         "manual_routes": 1, "average_confidence": 86.0,
                         "material_risks": 1, "provenance": "demo_data"}
    routes = {row["quote_id"]: row["review_route"] for row in repo.cost_estimate(None)}
    assert "자동 산출 후보" in routes["QT-260904-001"]
    assert routes["QT-260904-003"] == "수작업 견적 전환"


def test_quote_snapshot_links_drawing_bom_routing_and_approval(tmp_path):
    repo = OnetouchRepository(tmp_path / "demo.db")
    snapshot = repo.quote_snapshot("QT-260904-002")
    assert snapshot["drawing"]["slots"] == 6
    assert snapshot["drawing"]["exception_reason"] == "슬롯 간격 치수 중복"
    assert snapshot["bom"] and snapshot["routing"] and snapshot["approvals"]
    assert snapshot["estimate"]["model_status"] == "시제품 데모·미검증"


def test_similar_quote_and_material_risk(tmp_path):
    repo = OnetouchRepository(tmp_path / "demo.db")
    similar = repo.similar_quotes("표준 잔넬")
    assert len(similar) == 2
    assert all("quote_variance_pct" in row for row in similar)
    risks = repo.material_availability(True)
    assert len(risks) == 1
    assert risks[0]["specification"] == "SS400 3.2T"


def test_registry_is_strict_and_read_only(tmp_path):
    registry = OnetouchToolRegistry(OnetouchRepository(tmp_path / "demo.db"))
    assert len(registry.definitions) == 12
    assert all(tool["strict"] and tool["parameters"]["additionalProperties"] is False for tool in registry.definitions)
    assert all(not any(word in tool["name"] for word in ["approve", "send", "write", "update", "release"]) for tool in registry.definitions)
    assert "error" in json.loads(registry.execute("approve_quote", {}))
    payload = json.loads(registry.execute("get_rules", {"source_table": None}))
    assert payload["status"] == "ok" and payload["demo_data"] is True


def test_order_cost_feedback_keeps_actuals_separate(tmp_path):
    repo = OnetouchRepository(tmp_path / "demo.db")
    feedback = repo.order_feedback(None)
    assert {row["feedback_status"] for row in feedback} == {"학습후보", "검증완료"}
    assert all(row["planned_cost_krw"] != row["actual_cost_krw"] for row in feedback)


def test_local_knowledge_rules_and_table_browser(tmp_path):
    repo = OnetouchRepository(tmp_path / "demo.db")
    results = repo.search_knowledge("도면 개정 승인", 3)
    assert results and any(row["document_id"] == "OT-KB-005" for row in results)
    document_ids = {row["document_id"] for row in repo.knowledge_documents()}
    assert all(rule["source_document"] in document_ids for rule in repo.rules(None))
    assert repo.table_catalog()
    assert repo.browse_table("quote_requests", 2, 0)
    with pytest.raises(ValueError):
        repo.browse_table("sqlite_master")
