import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from onetouch_agent.data_hub import OnetouchRepository
from v2.api import create_app
from v2.domain import resolve_quote,EvidenceRegistry
from v2.compound import analyze,comparison_tables

def test_plan_grounding_quote_evidence_and_bounded_repair():
    class Model:
        def __init__(self):self.responses=self
        def with_options(self,**kwargs):return self
        def create(self,**kwargs):
            payload=json.loads(kwargs['input'])
            if 'requests' not in payload: return SimpleNamespace(output_text=json.dumps({'parts':[{'request':'품질','quote':'품질'},{'request':'없는 요청','quote':'추가 상상'}]}))
            return SimpleNamespace(output_text=json.dumps({'checks':[{'request':'품질','quote':'합격','evidence_indices':[8]}]}))
    calls=[]
    def retrieve(q,parts):
        calls.append(parts)
        if len(calls)==2:raise RuntimeError('repair unavailable')
        return {'text':'합격','records':[{'result':'합격'}],'evidence':[]}
    result=analyze('품질 비교',[],retrieve,Model(),'test')
    assert len(calls)==2 and result['text']=='합격' and result['partial']
    assert '없는 요청' not in calls[0]
    assert all(c['status']=='unconfirmed' for c in result['request_coverage'])


def test_all_recommendations_and_scope(tmp_path,monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    repo=OnetouchRepository(tmp_path/'test.db');client=TestClient(create_app(repo))
    groups=client.get('/api/workspace').json()['questions']
    assert list(map(len,groups.values()))==[10,10,10]
    for qs in groups.values():
        for q in qs:
            a=client.post('/api/chat',json={'question':q})
            assert a.status_code==200,(q,a.text)
            assert a.json()['engine']=='langgraph'
            assert a.json()['records'] or a.json()['evidence']
    history=[{'question':'QT-260904-002의 원가','answer':'QT-260904-001'}]
    a=client.post('/api/chat',json={'question':'그 견적의 BOM은?','history':history}).json()
    assert a['context']['quote_id']=='QT-260904-002'
    assert all(r['quote_id']=='QT-260904-002' for r in a['records'])
    client.post('/api/chat/reset')
    assert client.post('/api/chat',json={'question':'그 견적 BOM'}).status_code==422
    assert resolve_quote(repo,'DWG-260904-002 도면',None,[])=='QT-260904-002'

def test_registry_isolates_quote_material_and_drawing(tmp_path):
    repo=OnetouchRepository(tmp_path/'scope.db');r=EvidenceRegistry(repo,'QT-260904-002')
    a=json.loads(r.execute('get_cost_estimate',{'quote_id':'QT-260904-001'}))
    assert all(v['quote_id']=='QT-260904-002' for v in a['result'])
    a=json.loads(r.execute('get_drawing_features',{'drawing_id':None}))
    assert all(v['drawing_id']=='DWG-260904-002' for v in a['result'])
    a=json.loads(r.execute('get_material_availability',{'risks_only':False}))
    assert a['result'] and all(v['specification']=='SS400 3.2T' for v in a['result'])
    assert 'error' in json.loads(r.execute('browse_data_table',{'table':'quote_requests'}))

def test_partial_source_failure_and_zero_units(tmp_path):
    repo=OnetouchRepository(tmp_path/'failure.db');r=EvidenceRegistry(repo)
    def fail(**kwargs):raise RuntimeError('offline')
    r.handlers['get_cost_estimate']=fail
    r.execute('get_cost_estimate',{'quote_id':None})
    r.execute('get_bom',{'quote_id':'QT-260904-001'})
    assert r.errors and r.records
    table=comparison_tables([{'value':0,'unit':'원'},{'value':None,'unit':'원'}])[0]
    assert table['rows']==[['0','원'],['미확인','원']]


def test_voice_tool_uses_same_graph(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    monkeypatch.setenv('COCKPIT_ACCESS_TOKEN','test-code')
    monkeypatch.setattr('v2.api.OpenAI',lambda **kwargs:SimpleNamespace(close=lambda:None))
    monkeypatch.setattr('v2.api.ManufacturingAgent.ask',lambda *a,**k:SimpleNamespace(text='견적 원가 확인',evidence=[],sources=[],data_tools=[],searched_documents=True))
    client=TestClient(create_app(OnetouchRepository(tmp_path/'voice.db')))
    response=client.post('/api/realtime/tool',headers={'Authorization':'Bearer test-code'},json={'name':'analyze_manufacturing_question','arguments':{'question':'그 견적 원가 비교','history':[{'role':'user','text':'QT-260904-002 원가'}]}})
    assert response.status_code==200
    a=json.loads(response.json()['output'])
    assert a['engine']=='langgraph' and a['context']['quote_id']=='QT-260904-002'
    assert a['records'] and a['voice_summary']
