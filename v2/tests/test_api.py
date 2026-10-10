import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from onetouch_agent.data_hub import OnetouchRepository
from v2.api import create_app, EvidenceRegistry


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('COCKPIT_ACCESS_TOKEN', raising=False)
    return TestClient(create_app(OnetouchRepository(tmp_path / 'demo.db')))


def test_workspace_and_documents(client):
    data = client.get('/api/workspace').json()
    assert len(data['quotes']) == 3
    assert all(len(items) == 10 for items in data['questions'].values())
    assert data['meta']['demo_data'] is True
    assert not data['meta']['ai_configured']
    assert len(client.get('/api/documents').json()) == 7
    assert client.get('/api/tables/settings').status_code == 404
    assert client.get('/api/tables/quote_requests?limit=101').status_code == 422


def test_quote_context_and_raw_evidence(client):
    answer = client.post('/api/chat', json={'question': '원터치, 원가와 BOM', 'quote_id': 'QT-260904-002'}).json()
    assert answer['mode'] == 'demo'
    assert answer['records']
    assert all(row['quote_id'] == 'QT-260904-002' for row in answer['records'])
    assert '14,559,200원' in answer['text']
    assert answer['evidence']
    assert client.post('/api/chat', json={'question': '원터치, QT-missing 원가'}).status_code == 404
    assert client.post('/api/chat', json={'question': '  '}).status_code == 422


def test_explicit_quote_overrides_selection(client):
    answer = client.post('/api/chat', json={'question': '원터치, QT-260904-001 원가', 'quote_id': 'QT-260904-002'}).json()
    assert answer['context']['quote_id'] == 'QT-260904-001'
    assert all(row['quote_id'] == 'QT-260904-001' for row in answer['records'])


def test_demo_unknown_and_reset(client):
    answer = client.post('/api/chat', json={'question': '원터치, 화성의 날씨'}).json()
    assert not answer['records']
    assert '확인할 수 없습니다' in answer['text']
    assert client.post('/api/chat/reset').status_code == 200


def test_remote_paid_endpoints_require_token(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-secret')
    monkeypatch.setenv('COCKPIT_ACCESS_TOKEN', 'test-code')
    for path, body in [('/api/chat', {'question': '원터치, 원가', 'mode': 'ai'}),
                       ('/api/realtime/tool', {'name': 'get_cost_estimate', 'arguments': {'quote_id': None}}),
                       ('/api/voice/speak', {'text': '확인'})]:
        assert client.post(path, json=body).status_code == 401
    assert client.post('/api/realtime/session', content='sdp', headers={'content-type': 'application/sdp'}).status_code == 401
    response = client.post('/api/realtime/tool', json={'name': 'delete_quote', 'arguments': {}}, headers={'Authorization': 'Bearer test-code'})
    assert 'error' in json.loads(response.json()['output'])
    assert 'test-secret' not in client.get('/api/workspace').text


def test_ai_returns_actual_tool_records(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-secret')
    monkeypatch.setenv('COCKPIT_ACCESS_TOKEN', 'test-code')
    class FakeResponses:
        def __init__(self): self.count = 0
        def create(self, **kwargs):
            self.count += 1
            if self.count == 1:
                return SimpleNamespace(id='first', output_text='', output=[SimpleNamespace(type='function_call', name='get_cost_estimate', arguments='{"quote_id":"QT-260904-001"}', call_id='one')])
            return SimpleNamespace(id='second', output=[], output_text='견적 후보입니다. 근거: QT-260904-001')
    monkeypatch.setattr('v2.api.OpenAI', lambda **kwargs: SimpleNamespace(responses=FakeResponses()))
    result = client.post('/api/chat', json={'question': '원터치, 원가', 'mode': 'ai', 'quote_id': 'QT-260904-001'}, headers={'Authorization': 'Bearer test-code'})
    assert result.status_code == 200
    assert result.json()['records'][0]['estimated_total_krw'] == 15179600
    assert result.json()['mode'] == 'ai'


def test_no_key_local_and_forwarded_access(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('COCKPIT_ACCESS_TOKEN', raising=False)
    local = TestClient(create_app(OnetouchRepository(tmp_path / 'local.db')), base_url='http://localhost', client=('127.0.0.1', 1234))
    assert local.post('/api/chat', json={'question': '원터치, 원가', 'mode': 'ai'}).status_code == 503
    assert local.post('/api/chat', json={'question': '원터치, 원가', 'mode': 'ai'}, headers={'X-Forwarded-For': '8.8.8.8'}).status_code == 401


def test_realtime_session_contract(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-secret')
    monkeypatch.setenv('COCKPIT_ACCESS_TOKEN', 'test-code')
    captured = {}
    class FakeHTTP:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(status_code=201, text='v=0\r\nmock-answer')
    monkeypatch.setattr('v2.api.httpx.AsyncClient', FakeHTTP)
    headers = {'Authorization': 'Bearer test-code', 'content-type': 'application/sdp'}
    response = client.post('/api/realtime/session?quote_id=QT-260904-002', content='v=0', headers=headers)
    assert response.status_code == 200
    session = json.loads(captured['files']['session'][1])
    assert len(session['tools']) == 12
    assert 'QT-260904-002' in session['instructions']
    assert session['audio']['input']['turn_detection']['interrupt_response'] is False
    assert client.post('/api/realtime/session', content=b'\xff', headers=headers).status_code == 422
