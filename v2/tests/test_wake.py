import json
from pathlib import Path
from types import SimpleNamespace
from fastapi.testclient import TestClient
from onetouch_agent.data_hub import OnetouchRepository
from v2.api import create_app
from v2.wake import calls_agent, WAKE_POLICY


def test_shared_wake_cases():
    for text, expected in json.loads(Path(__file__).with_name('wake_cases.json').read_text()):
        assert calls_agent(text, {**WAKE_POLICY,'require_wake_name':True}) == expected, text
    assert calls_agent('송월님, 재고', {'agent_name':'송월','wake_aliases':['송월님'],'require_wake_name':True})
    assert not calls_agent('원터치, 재고', {'agent_name':'송월','wake_aliases':['송월님'],'require_wake_name':True})


def test_unaddressed_question_reads_evidence(tmp_path):
    client=TestClient(create_app(OnetouchRepository(tmp_path/'test.db')))
    response=client.post('/api/chat',json={'question':'원가와 BOM'})
    assert response.status_code==200
    assert response.json()['records'] and not response.json().get('ignored')


def test_workspace_recommendations_and_addressed_demo(tmp_path):
    client=TestClient(create_app(OnetouchRepository(tmp_path/'test.db')))
    data=client.get('/api/workspace').json()
    assert data['meta']['wake']==WAKE_POLICY
    assert all(calls_agent(q) for group in data['questions'].values() for q in group)
    result=client.post('/api/chat',json={'question':'원터치님, 원가와 BOM','quote_id':'QT-260904-002'}).json()
    assert '14,559,200' in result['text'] and result['records']
