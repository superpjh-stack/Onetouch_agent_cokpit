"""Quote scope is derived only from explicit IDs and user messages."""
import json,re
from onetouch_agent.factory_tools import OnetouchToolRegistry

def resolve_quote(repo,question,selected,history):
    ids=list(dict.fromkeys(re.findall(r'(?:QT|DWG)-[A-Za-z0-9-]+',question.upper())))
    if not ids and not selected and any(w in question for w in ('그 견적','해당 견적','그 도면','해당 도면','그 건','해당 건','이 견적')):
        for turn in reversed(history):
            if turn['role']=='user':
                ids=list(dict.fromkeys(re.findall(r'(?:QT|DWG)-[A-Za-z0-9-]+',turn['text'].upper())))
                if ids:break
        if not ids:raise ValueError('후속 질문의 견적 ID를 알려주세요.')
    quotes=[]
    for identifier in ids:
        if identifier.startswith('DWG-'):
            matches=[r['quote_id'] for r in repo.quote_requests(None) if r['drawing_id']==identifier]
            if len(matches)!=1:raise ValueError('도면에 연결된 견적을 하나로 확인할 수 없습니다. 견적 ID를 알려주세요.')
            quotes.extend(matches)
        else:quotes.append(identifier)
    quotes=list(dict.fromkeys(quotes))
    if len(quotes)>1 or (quotes and selected and quotes[0]!=selected):raise ValueError('한 번에 하나의 견적을 지정해 주세요. 전체 비교는 ID 없이 질문할 수 있습니다.')
    return selected or (quotes[0] if quotes else None)

class EvidenceRegistry(OnetouchToolRegistry):
    def __init__(self,repository,quote_id=None):
        super().__init__(repository);self.records=[];self.errors=[];self.repo=repository;self.quote_id=quote_id
        if quote_id:self.handlers.pop('browse_data_table',None)
    @property
    def definitions(self):return [d for d in super().definitions if d['name'] in self.handlers]
    def execute(self,name,arguments):
        args=json.loads(arguments) if isinstance(arguments,str) else dict(arguments)
        if self.quote_id:
            quote=self.repo.quote_requests(self.quote_id)[0]
            if name in ('get_quote_requests','get_bom','get_routing','get_cost_estimate','get_quote_review_queue','get_order_cost_feedback'):args['quote_id']=self.quote_id
            if name=='get_drawing_features':args['drawing_id']=quote['drawing_id']
            if name=='compare_similar_quotes':args['product_family']=quote['product_family']
        try:payload=json.loads(super().execute(name,args))
        except Exception:payload={'error':'자료 조회 실패','tool':name}
        if payload.get('status')=='ok':
            rows=payload['result']
            if self.quote_id and name=='get_material_availability':
                specs={r['specification'] for r in self.repo.bom(self.quote_id)}
                rows=[r for r in rows if r['specification'] in specs];payload['result']=rows
            if name!='search_local_knowledge':
                for row in rows if isinstance(rows,list) else [rows]:
                    if isinstance(row,dict):
                        record={'source_tool':name,'demo_data':True,**row}
                        if record not in self.records:self.records.append(record)
        else:self.errors.append({'tool':name,'message':'조회 실패 또는 대상 범위 밖의 자료입니다.'})
        return json.dumps(payload,ensure_ascii=False,default=str)
