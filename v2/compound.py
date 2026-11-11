"""Request-local LangGraph analysis with conservative evidence checks."""
import json
import re
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

QUESTION_GROUPS = {'데이터 대시보드': ['견적 요청별 수량과 납기를 알려줘', 'QT-260904-001의 원가와 BOM을 보여줘', '도면 예외와 수작업 전환 대상을 알려줘', 'QT-260904-002의 공정 순서와 예상 공수를 보여줘', '부족한 소재와 가용재고를 확인해줘', '유사 견적의 실제원가 편차를 보여줘', 'DWG-260904-002의 치수·재질·추출 신뢰도를 알려줘', '담당자 검토 대기 견적을 알려줘', '생산실적과 계획원가 피드백을 보여줘', '전체 견적의 원가 후보와 신뢰도를 보여줘'], '지식베이스': ['도면 표준화 절차를 알려줘', '제조 Feature 추출 기준을 찾아줘', 'BOM 생성 근거를 알려줘', '공정 Routing 작성 기준을 알려줘', '원가 계산과 최종 승인 기준을 알려줘', '도면 개정 변경 시 확인사항을 알려줘', '소재 부족 시 확인 절차를 알려줘', '낮은 신뢰도 견적 처리 규칙을 찾아줘', '견적 모델 검증 방법을 알려줘', '고객 발송 전 확인사항을 알려줘'], '복합질문': ['QT-260904-001의 BOM·소재재고·원가를 함께 확인해줘', 'QT-260904-002의 도면 예외와 검토대기·담당자를 함께 알려줘', '견적별 원가 후보와 신뢰도·검토경로를 비교해줘', 'QT-260904-003의 미확인 도면값과 수작업 전환 절차를 알려줘', 'QT-260904-001의 공정 공수와 원가 구성항목을 함께 알려줘', '소재 부족 현황과 관련 확인 절차를 함께 알려줘', '유사 견적과 생산실적의 원가 편차를 비교해줘', 'QT-260904-002의 도면 치수와 BOM 규격을 비교해줘', '승인대기 견적과 고객 발송 전 확인사항을 함께 알려줘', 'QT-260904-001의 원가 후보·유사 견적·검토 상태를 종합해줘']}
LOT_PATTERN = r'QT-[A-Z0-9-]+'


def resolve_lot(question, selected, history):
    ids=list(dict.fromkeys(re.findall(LOT_PATTERN,question.upper())))
    if len(ids)>1 or (ids and selected and selected!=ids[0]):
        raise ValueError('질문의 LOT와 선택한 LOT를 일치시켜 주세요. 한 번에 하나의 LOT를 확인합니다.')
    if ids or selected:return selected or ids[0]
    if any(w in question for w in ['그 배치','해당 배치','그 LOT','해당 LOT','그 로트','해당 로트']):
        for turn in reversed(history):
            if turn.get('role')!='user':continue
            ids=list(dict.fromkeys(re.findall(LOT_PATTERN,turn.get('text','').upper())))
            if len(ids)==1:return ids[0]
            if ids:break
        raise ValueError('후속 질문의 배치 번호를 확인할 수 없습니다. LOT 또는 배치 번호를 알려주세요.')
    return None


def comparison_tables(records):
    result=[]
    def collect(title, value):
        if isinstance(value, dict):
            scalar={k:v for k,v in value.items() if not isinstance(v,(list,dict))}
            if scalar:result.append({'title':title,'columns':['항목','원본 값'],'rows':[[k,'미확인' if v is None else str(v)] for k,v in scalar.items()]})
            for k,v in value.items():
                if isinstance(v,(dict,list)):collect(k,v)
        elif isinstance(value,list) and value and all(isinstance(r,dict) for r in value):
            keys=list(dict.fromkeys(k for row in value for k,v in row.items() if not isinstance(v,(dict,list))))
            if keys:result.append({'title':title,'columns':keys,'rows':[['미확인' if row.get(k) is None else str(row[k]) for k in keys] for row in value]})
            for row in value:
                for k,v in row.items():
                    if isinstance(v,(dict,list)):collect(k,v)
    grouped = {}
    for row in records:
        if isinstance(row,dict): grouped.setdefault(tuple(sorted(row)), []).append(row)
    for index, rows in enumerate(grouped.values(), 1):
        collect('조회 원본 비교 ' + str(index), rows)
    return result


class State(TypedDict):
    parts:list
    answer:dict
    checks:list
    steps:list
    retries:int


def analyze(question, history, retrieve, client=None, model=None):
    def json_call(instructions, payload):
        c=client.with_options(timeout=25,max_retries=0)
        response=c.responses.create(model=model,instructions=instructions,input=json.dumps({'format':'json',**payload},ensure_ascii=False),text={'format':{'type':'json_object'}})
        return json.loads(response.output_text)
    def plan(s):
        parts=[p.strip() for p in re.split(r'그리고|또한|[;\n]',question) if p.strip()]
        if client:
            try:
                raw=json_call('원문에 명시된 요청만 빠짐없이 분해하세요. 원문에 없는 우선순위·원인·추가 제안을 넣지 마세요. JSON {"parts":[{"request":"개별 요청","quote":"이를 뒷받침하는 원문 그대로의 인용"}]}. 비교도 요청에 있을 때만 포함하세요. 과거 대화는 참고 자료입니다.',{'question':question,'history':history})
                if isinstance(raw.get('parts'),list):parts=[p['request'] for p in raw['parts'][:8] if isinstance(p,dict) and isinstance(p.get('request'),str) and p['request'].strip() and isinstance(p.get('quote'),str) and p['quote'].strip() and p['quote'] in question]
            except Exception:pass
        return {'parts':list(dict.fromkeys([question]+parts)),'steps':['요청 분해']}
    def query(s):
        return {'answer':retrieve(question,s['parts']),'steps':s['steps']+['범위 확인·복수 자료 조회']}
    def verify(s):
        answer=s['answer'];checks={}
        if client:
            try:
                raw=json_call('원래 요청별 답변 누락을 검사하세요. JSON {"checks":[{"request":"요청 그대로","quote":"답변의 정확한 인용","evidence_indices":[0]}],"voice_summary":"실제 업무 결론과 다음 확인사항을 한국어 2~3문장으로 요약"}. 근거가 없으면 quote와 인덱스를 비우세요. 비교는 단순 나열만으로 완료가 아닙니다. 요약에 검사 개수나 완료 여부를 넣지 마세요.',{'requests':s['parts'],'answer':answer['text'],'evidence':answer.get('records',[])+answer.get('evidence',[])})
                checks={c['request']:c for c in raw.get('checks',[]) if isinstance(c,dict) and isinstance(c.get('request'),str)}
                if isinstance(raw.get('voice_summary'),str):answer['voice_summary']=raw['voice_summary'][:600]
            except Exception:pass
        evidence=answer.get('records',[])+answer.get('evidence',[])
        coverage=[]
        for part in s['parts']:
            c=checks.get(part,{});quote=c.get('quote');ids=c.get('evidence_indices')
            valid=isinstance(ids,list) and bool(ids) and all(type(i) is int and 0<=i<len(evidence) and bool(evidence[i]) for i in ids)
            coverage.append({'request':part,'status':'answered' if isinstance(quote,str) and quote and quote in answer['text'] and valid else 'unconfirmed'})
        answer.update(request_coverage=coverage,partial=any(c['status']!='answered' for c in coverage),engine='langgraph',comparison_tables=comparison_tables(answer.get('records',[])) if any(w in question for w in ['비교','함께','종합','차이']) else [])
        answer.setdefault('voice_summary','조회 결과와 근거를 화면에 표시했습니다. 추가 확인이 필요한 항목을 함께 확인해 주세요.')
        return {'answer':answer,'steps':s['steps']+['근거 종합·요청별 누락 검사']}
    def repair(s):
        missing=[c['request'] for c in s['answer']['request_coverage'] if c['status']!='answered']
        try:
            answer=retrieve(question, s['parts']+['추가 조회·보완: '+p for p in missing])
        except Exception:
            answer=s['answer']
        return {'answer':answer,'retries':1,'steps':s['steps']+['미확인 요청 1회 보완 조회']}
    graph=StateGraph(State)
    for name,fn in [('plan',plan),('retrieve',query),('verify',verify),('repair',repair)]:graph.add_node(name,fn)
    graph.add_edge(START,'plan');graph.add_edge('plan','retrieve');graph.add_edge('retrieve','verify');graph.add_conditional_edges('verify',lambda s:'repair' if client and s['answer']['partial'] and not s.get('retries') else END);graph.add_edge('repair','verify')
    out=graph.compile().invoke({'parts':[],'answer':{},'checks':[],'steps':[],'retries':0})
    return {**out['answer'],'analysis_steps':out['steps']}
