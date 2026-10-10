import json
from pathlib import Path
from types import SimpleNamespace
from fastapi.testclient import TestClient
from onetouch_agent.data_hub import OnetouchRepository
from v2.api import create_app
from v2.wake import calls_agent, WAKE_POLICY


def test_shared_wake_cases():
    for text, expected in json.loads(Path(__file__).with_name('wake_cases.json').read_text()):
        assert calls_agent(text) == expected, text
    assert calls_agent('송월님, 재고', {'agent_name':'송월','wake_aliases':['송월님'],'require_wake_name':True})
    assert not calls_agent('원터치, 재고', {'agent_name':'송월','wake_aliases':['송월님'],'require_wake_name':True})


def test_unaddressed_question_never_reads_db_or_calls_ai(tmp_path, monkeypatch):
    repo=OnetouchRepository(tmp_path/'test.db')
    client=TestClient(create_app(repo))
    def forbidden(*args, **kwargs): raise AssertionError('must not execute')
    monkeypatch.setattr(repo,'quote_requests',forbidden)
    monkeypatch.setattr(repo,'search_knowledge',forbidden)
    monkeypatch.setattr('v2.api.OpenAI',forbidden)
    for question in ['원가', '니즈, 원가', '원터치플랫폼 원가']:
        for mode in ['demo','ai']:
            result=client.post('/api/chat',json={'question':question,'mode':mode,'history':[{'question':'원터치, 원가','answer':'이전 답변'}]})
            assert result.status_code==200
            assert result.json()['ignored'] and not result.json()['text']
            assert not result.json()['records'] and not result.json()['evidence']


def test_workspace_recommendations_and_addressed_demo(tmp_path):
    client=TestClient(create_app(OnetouchRepository(tmp_path/'test.db')))
    data=client.get('/api/workspace').json()
    assert data['meta']['wake']==WAKE_POLICY
    assert all(calls_agent(q) for group in data['questions'].values() for q in group)
    result=client.post('/api/chat',json={'question':'원터치님, 원가와 BOM','quote_id':'QT-260904-002'}).json()
    assert '14,559,200' in result['text'] and result['records']
