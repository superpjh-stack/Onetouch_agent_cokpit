from types import SimpleNamespace

import pytest

from onetouch_agent import ManufacturingAgent, OnetouchRepository, OnetouchToolRegistry


class FakeResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            call = SimpleNamespace(type="function_call", name="get_cost_estimate", call_id="call-1",
                                   arguments='{"quote_id":"QT-260904-001"}')
            return SimpleNamespace(id="resp-1", output=[call], output_text="")
        return SimpleNamespace(id="resp-2", output=[], output_text="담당자 승인 전 견적 후보입니다.")


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


def test_agent_executes_quote_tool_loop(tmp_path):
    client = FakeClient()
    registry = OnetouchToolRegistry(OnetouchRepository(tmp_path / "demo.db"))
    answer = ManufacturingAgent(client, factory_tools=registry).ask("QT-260904-001 원가는?")
    assert answer.data_tools == ["get_cost_estimate"]
    assert answer.response_id == "resp-2"
    assert client.responses.calls[1]["input"][0]["type"] == "function_call_output"


def test_agent_rejects_blank_question(tmp_path):
    registry = OnetouchToolRegistry(OnetouchRepository(tmp_path / "demo.db"))
    with pytest.raises(ValueError):
        ManufacturingAgent(FakeClient(), factory_tools=registry).ask(" ")
