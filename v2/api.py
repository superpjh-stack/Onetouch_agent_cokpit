"""Quotation V2: existing read-only repository + evidence-backed conversation."""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

from v2.openai_settings import save_api_key
from v2.compound import analyze, QUESTION_GROUPS
from v2.domain import EvidenceRegistry, resolve_quote
from v2.wake import WAKE_POLICY, calls_agent, addressed_question, question_content
from onetouch_agent.data_hub import DEMO_DATE
from onetouch_agent.postgres_hub import create_repository
from onetouch_agent.factory_tools import OnetouchToolRegistry
from onetouch_agent.service import ManufacturingAgent
from onetouch_agent.prompts import AGENT_INSTRUCTIONS

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
QUESTIONS = QUESTION_GROUPS


class Turn(BaseModel):
    question: str = Field(max_length=2000)
    answer: str = Field(max_length=10000)


class Chat(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    quote_id: str | None = Field(default=None, max_length=80)
    mode: Literal['demo', 'ai'] = 'demo'
    history: list[Turn] = Field(default_factory=list, max_length=6)


class ToolCall(BaseModel):
    name: str = Field(max_length=100)
    arguments: dict = Field(default_factory=dict)


class Speech(BaseModel):
    text: str = Field(min_length=1, max_length=4000)



def local_request(request: Request) -> bool:
    return bool(request.client and request.client.host in {'127.0.0.1', '::1'}
                and request.url.hostname in {'localhost', '127.0.0.1', '::1'}
                and 'x-forwarded-for' not in request.headers
                and 'forwarded' not in request.headers)


def create_app(repository=None, settings_file: Path | None = None):
    settings_file = settings_file or ROOT / ".env"
    app = FastAPI(title='원터치 견적 AI Agent', version='2.2.0')
    app.state.repo = repository or create_repository(os.getenv('ONETOUCH_DB_PATH', str(ROOT / 'data/onetouch_demo.db')))
    requests = defaultdict(deque)
    access_attempts = defaultdict(deque)
    rate_lock = threading.Lock()

    def valid_access_code(supplied):
        expected = [os.getenv('COCKPIT_ACCESS_TOKEN', '')]
        expected.extend(os.getenv('COCKPIT_ACCESS_TOKENS', '').split(','))
        matched = False
        for candidate in expected:
            candidate = candidate.strip()
            matched = hmac.compare_digest(candidate, supplied) | matched if candidate else matched
        return matched

    def require_ai(request):
        supplied = request.headers.get('authorization', '').removeprefix('Bearer ').strip()
        if not local_request(request) and not valid_access_code(supplied):
            raise HTTPException(401, '설정에서 관리자가 발급한 AI 접근 코드를 입력해 주세요.')
        key = os.getenv('OPENAI_API_KEY', '')
        if not key:
            raise HTTPException(503, '서버 OPENAI_API_KEY가 설정되지 않았습니다. 데모 조회는 사용할 수 있습니다.')
        identity = hashlib.sha256((supplied or (request.client.host if request.client else 'unknown')).encode()).hexdigest()
        with rate_lock:
            now = time.monotonic()
            for entry in list(requests):
                if not requests[entry] or requests[entry][-1] < now - 60:
                    del requests[entry]
            queue = requests[identity]
            while queue and queue[0] < now - 60:
                queue.popleft()
            if len(queue) >= 30:
                raise HTTPException(429, '요청이 많습니다. 잠시 후 다시 시도해 주세요.')
            queue.append(now)
        return key

    def validate_quote(quote_id):
        if quote_id and not app.state.repo.quote_requests(quote_id):
            raise HTTPException(404, '등록된 견적 ID가 아닙니다.')

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'version': '2.2.0'}

    @app.post('/api/access/check')
    def check_access(request: Request):
        if local_request(request):
            return {'authorized': True}
        supplied = request.headers.get('authorization', '').removeprefix('Bearer ').strip()
        source = request.client.host if request.client else 'unknown'
        with rate_lock:
            now = time.monotonic()
            attempts = access_attempts[source]
            while attempts and attempts[0] < now - 60:
                attempts.popleft()
            if len(attempts) >= 10:
                raise HTTPException(429, '코드 확인 요청이 많습니다. 잠시 후 다시 시도해 주세요.')
            attempts.append(now)
        if not valid_access_code(supplied):
            raise HTTPException(401, '접근 코드가 서버 설정과 일치하지 않습니다. 관리자에게 발급된 AI 접근 코드를 확인하세요.')
        return {'authorized': True}

    @app.get('/api/workspace')
    def workspace(request: Request):
        repo = app.state.repo
        return {'quotes': [{**row, 'product_name': row['product_family']} for row in repo.quote_requests(None)],
                'kpi': repo.dashboard(), 'questions': QUESTIONS,
                'tables': [{**row, 'count': row['rows'], 'exists': True} for row in repo.table_catalog()],
                'meta': {'wake': WAKE_POLICY, 'company': '원터치', 'version': '2.2.0', 'demo_data': True, 'as_of': DEMO_DATE,
                         'backend': 'PostgreSQL' if os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL') else 'SQLite',
                         'ai_configured': bool(os.getenv('OPENAI_API_KEY')),
                         'local_dev_ai': local_request(request), 'model': os.getenv('OPENAI_MODEL', 'gpt-5.6-sol'),
                         'retrieved_at': datetime.now(timezone.utc).isoformat()}}

    @app.post('/api/settings/openai')
    async def configure_openai(request: Request):
        if not local_request(request):
            raise HTTPException(403, 'API 키는 이 컴퓨터에서 직접 접속해 설정하세요.')
        if request.headers.get('origin', '').rstrip('/') != str(request.base_url).rstrip('/'):
            raise HTTPException(403, '동일 출처 설정 화면에서 입력하세요.')
        raw = await request.body()
        if len(raw) > 4096:
            raise HTTPException(413, '입력 크기를 확인하세요.')
        try:
            payload = json.loads(raw)
            key = payload.get('api_key', '') if isinstance(payload, dict) else ''
            if not isinstance(key, str):
                raise ValueError
            key = key.strip()
            if not re.fullmatch(r'sk-[A-Za-z0-9_-]{20,1024}', key):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(422, 'OpenAI API 키 형식을 확인하세요.') from None
        model = os.getenv('OPENAI_REALTIME_MODEL', 'gpt-realtime-2.1')
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(f'https://api.openai.com/v1/models/{model}',
                                            headers={'Authorization': f'Bearer {key}'})
        except httpx.HTTPError:
            raise HTTPException(502, 'OpenAI에 연결하지 못했습니다. 네트워크를 확인한 뒤 다시 시도하세요.') from None
        if response.status_code == 401:
            raise HTTPException(422, 'API 키가 유효하지 않습니다. 키를 다시 확인하세요.')
        if response.status_code in {403, 404}:
            raise HTTPException(422, '이 키로 음성 모델을 확인하지 못했습니다. 프로젝트의 모델·API 권한을 확인하세요.')
        if response.is_error:
            raise HTTPException(502, 'OpenAI 연결 확인에 실패했습니다. 잠시 후 다시 시도하세요.')
        try:
            save_api_key(settings_file, key)
        except OSError:
            raise HTTPException(500, '서버 설정을 저장하지 못했습니다. 파일 권한을 확인하세요.') from None
        return {'configured': True, 'realtime_model': model}

    @app.get('/api/documents')
    def documents():
        return [{**row, 'content': row['body'], 'source': row['source_label']}
                for row in app.state.repo.browse_table('knowledge_documents', 100)]

    @app.get('/api/tables/{table}')
    def table_rows(table: str, limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0)):
        try:
            return app.state.repo.browse_table(table, limit, offset)
        except ValueError as exc:
            raise HTTPException(404, '조회가 허용되지 않은 테이블입니다.') from exc

    @app.get('/api/quotes/{quote_id}')
    def quote(quote_id: str):
        validate_quote(quote_id)
        return app.state.repo.quote_snapshot(quote_id)

    @app.post('/api/chat/reset')
    def reset():
        # Conversations are request-scoped. No shared provider response ID is retained.
        return {'status': 'ok'}

    @app.post('/api/chat')
    def chat(body: Chat, request: Request):
        question = body.question.strip()
        if not question:
            raise HTTPException(422, '질문을 입력해 주세요.')
        repo = app.state.repo
        history = [{'role': role, 'text': text} for turn in body.history for role, text in [('user',turn.question),('assistant',turn.answer)]]
        try:
            quote_id = resolve_quote(repo, question, body.quote_id, history)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        validate_quote(quote_id)
        now = datetime.now(timezone.utc).isoformat()
        base = {'mode': body.mode, 'context': {'quote_id': quote_id, 'as_of': DEMO_DATE}, 'captured_at': now, 'demo_data': True}
        client = OpenAI(api_key=require_ai(request), timeout=40, max_retries=0) if body.mode == 'ai' else None
        def retrieve(original, parts):
            registry = EvidenceRegistry(repo, quote_id)
            lookup = retrieve_demo(repo, original+'\n'+'\n'.join(parts), quote_id, registry, base)
            if not client:
                return lookup
            prompt = json.dumps({'question':original,'requests':parts,'quote_id':quote_id,'history':history,'records':registry.records,'documents':lookup['evidence'],'note':'수치는 가상 샘플이며 승인된 견적이 아닙니다. 0원도 입력 불충분일 수 있으므로 수작업 전환·미검증 상태를 반드시 함께 설명하세요.'},ensure_ascii=False)
            answer = ManufacturingAgent(client, model=os.getenv('OPENAI_MODEL','gpt-5.6-sol'), factory_tools=registry).ask(prompt)
            evidence = list(lookup['evidence'])
            for item in answer.evidence:
                if item not in evidence:evidence.append(item)
            return {**base,'text':answer.text,'records':registry.records,'evidence':evidence,'sources':answer.sources,'data_tools':answer.data_tools,'searched_documents':answer.searched_documents,'lookup_errors':registry.errors}
        try:
            result = analyze(question, history, retrieve, client, os.getenv('OPENAI_MODEL','gpt-5.6-sol'))
            result['summary'] = result['voice_summary']
            return result
        except Exception as exc:
            raise HTTPException(502,'분석을 완료하지 못했습니다. 서버 모델 설정과 연결을 확인해 주세요.') from exc
        finally:
            if client:client.close()

    def retrieve_demo(repo, question, quote_id, registry, base):
        # Deterministic demo lookup: no invented interpretation or calculations.
        query = '\n'.join(question_content(line) for line in question.splitlines())
        docs = json.loads(registry.execute('search_local_knowledge',{'query':query,'limit':6})).get('result',[]) if query else []
        q = query.lower()
        calls = []
        ids = [quote_id] if quote_id else [row['quote_id'] for row in repo.quote_requests(None)]
        if any(word in q for word in ['bom', '자재']):
            calls += [('get_bom', {'quote_id': item}) for item in ids]
        if any(word in q for word in ['공정', '공수', 'routing']):
            calls += [('get_routing', {'quote_id': item}) for item in ids]
        if any(word in q for word in ['원가', '신뢰도', '검토경로']):
            calls.append(('get_cost_estimate', {'quote_id': quote_id}))
        if any(word in q for word in ['도면', '치수', '재질', '수작업']):
            drawing = repo.quote_requests(quote_id)[0]['drawing_id'] if quote_id else None
            calls.append(('get_drawing_features', {'drawing_id': drawing}))
        if any(word in q for word in ['소재', '재고', '부족']):
            calls.append(('get_material_availability', {'risks_only': '부족' in q}))
        if any(word in q for word in ['승인', '검토', '발송']):
            calls.append(('get_quote_review_queue', {'quote_id': quote_id, 'pending_only': True}))
        if any(word in q for word in ['유사', '과거', '편차']):
            family = repo.quote_requests(quote_id)[0]['product_family'] if quote_id else None
            calls.append(('compare_similar_quotes', {'product_family': family}))
        if any(word in q for word in ['실적', '피드백', '계획원가']):
            calls.append(('get_order_cost_feedback', {'quote_id': quote_id}))
        if any(word in q for word in ['규칙', '기준']):
            calls.append(('get_rules', {'source_table': None}))
        if any(word in q for word in ['견적', '현황', '납기', '요청']):
            calls.append(('get_quote_requests', {'quote_id': quote_id}))
        for name, args in calls:
            registry.execute(name, args)
        lines = [f'데모 조회 결과 · {quote_id or "전체 견적"} · 샘플 기준 {DEMO_DATE}']
        if registry.records:
            lines.append(f'관련 원본 레코드 {len(registry.records)}건을 찾았습니다. 아래 조회 기록에서 수치·단위·상태를 확인하세요.')
            for row in registry.records:
                if row['source_tool'] == 'get_cost_estimate':
                    lines.append(f'{row["quote_id"]}: 원가 후보 {row["estimated_total_krw"]:,.0f}원 · {row["review_route"]}')
        elif not docs:
            lines.append('현재 견적 Data Hub와 등록 문서에서 확인할 수 없습니다.')
        if docs:
            lines.append('관련 문서: ' + ', '.join(row['title'] for row in docs))
        lines.append('정해진 검색에 따른 샘플 조회이며 AI 분석·승인 결과가 아닙니다. 문서와 규칙은 샘플·미승인입니다.')
        return {**base, 'text': '\n'.join(lines), 'records': registry.records, 'evidence': docs,
                'sources': [row['filename'] for row in docs], 'data_tools': [name for name, _ in calls],
                'searched_documents': bool(docs), 'lookup_errors': registry.errors}

    @app.post('/api/realtime/session')
    async def realtime(request: Request, quote_id: str | None = Query(None, max_length=80)):
        key = require_ai(request)
        validate_quote(quote_id)
        if request.headers.get('content-type', '').split(';')[0] != 'application/sdp':
            raise HTTPException(415, 'WebRTC 연결 정보가 필요합니다.')
        offer = await request.body()
        if not offer or len(offer) > 100_000:
            raise HTTPException(413, 'WebRTC 연결 정보가 올바르지 않습니다.')
        try:
            sdp = offer.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise HTTPException(422, 'WebRTC 연결 형식이 올바르지 않습니다.') from exc
        registry = OnetouchToolRegistry(app.state.repo)
        session = {'type': 'realtime', 'model': os.getenv('OPENAI_REALTIME_MODEL', 'gpt-realtime-2.1'),
            'instructions': AGENT_INSTRUCTIONS + ' 호출명 없이 질문에 답하세요. 모든 업무 질문은 analyze_manufacturing_question으로 원문 그대로 전달하고 결과의 voice_summary를 2~3문장으로 읽으세요. 자세한 근거는 화면으로 안내하세요.',
            'output_modalities': ['audio'], 'tools': [{'type':'function','name':'analyze_manufacturing_question','description':'견적·도면 복합질문 근거 분석','parameters':{'type':'object','properties':{'question':{'type':'string'}},'required':['question'],'additionalProperties':False}}],
            'tool_choice': 'auto', 'audio': {'input': {'transcription': {'model': 'gpt-4o-mini-transcribe', 'language': 'ko'},
            'noise_reduction': {'type': 'near_field'}, 'turn_detection': {'type': 'semantic_vad', 'eagerness': 'high', 'create_response': False, 'interrupt_response': True}},
            'output': {'voice': os.getenv('OPENAI_REALTIME_VOICE', 'marin')}}}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                upstream = await client.post('https://api.openai.com/v1/realtime/calls',
                    headers={'Authorization': f'Bearer {key}'}, files={'sdp': (None, sdp, 'application/sdp'),
                    'session': (None, json.dumps(session, ensure_ascii=False), 'application/json')})
        except httpx.HTTPError as exc:
            raise HTTPException(502, '실시간 음성 서비스에 연결하지 못했습니다.') from exc
        if upstream.status_code >= 400:
            raise HTTPException(502, '음성 연결에 실패했습니다. 모델 사용 권한과 서버 설정을 확인하세요.')
        return Response(upstream.text, media_type='application/sdp')

    @app.post('/api/realtime/tool')
    def realtime_tool(body: ToolCall, request: Request):
        require_ai(request)
        if body.name != 'analyze_manufacturing_question':
            return {'output': json.dumps({'error':'허용되지 않은 조회 도구입니다.'},ensure_ascii=False)}
        turns=body.arguments.get('history',[])[-12:]
        history=[Turn(question=str(t.get('text',''))[:2000],answer='') for t in turns if t.get('role')=='user'][-6:]
        answer=chat(Chat(question=body.arguments.get('question',''),quote_id=body.arguments.get('quote_id'),history=history,mode='ai'),request)
        return {'output':json.dumps(answer,ensure_ascii=False,default=str)}

    @app.post('/api/voice/speak')
    def speak(body: Speech, request: Request):
        key = require_ai(request)
        try:
            response = OpenAI(api_key=key, timeout=30, max_retries=0).audio.speech.create(
                model='gpt-4o-mini-tts', voice='marin', input=body.text, response_format='mp3')
            return Response(response.content, media_type='audio/mpeg')
        except Exception as exc:
            raise HTTPException(502, '답변 음성을 생성하지 못했습니다.') from exc

    dist = ROOT / 'v2/web/dist'
    if (dist / 'assets').exists():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

    @app.get('/')
    def index():
        if not (dist / 'index.html').exists():
            raise HTTPException(503, '먼저 npm run build --prefix v2/web를 실행하세요.')
        return FileResponse(dist / 'index.html')

    return app


app = create_app()
