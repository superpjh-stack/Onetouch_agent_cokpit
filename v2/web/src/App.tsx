import {useEffect, useMemo, useRef, useState, type ReactNode} from 'react';
import {BookOpen, ChevronRight, CircleAlert, Database, FileText, History, Factory, LoaderCircle, Menu, RefreshCw, Search, Settings2, Sparkles, Table2, X} from 'lucide-react';
import {ConnectionSettings} from './components/ConnectionSettings';
import {readAccessCode} from './accessCode';
import {Assistant, type AssistantHandle} from './components/Assistant';
import {request, type Document, type Row, type Workspace} from './types';

type LibraryTab = 'knowledge' | 'data';
type SidePanel = 'library' | 'questions' | null;
type RecommendationTab = '견적·도면' | '문서·규칙';

function Modal({title, onClose, children}:{title:string; onClose:()=>void; children:ReactNode}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); return () => ref.current?.close(); }, []);
  return <dialog ref={ref} className="modal" onCancel={onClose} onClick={event => {
    if (event.target === event.currentTarget) onClose();
  }}><header><h2>{title}</h2><button className="icon-button" aria-label="닫기" onClick={onClose}><X size={19}/></button></header><div className="modal-body">{children}</div></dialog>;
}

const cleanDocumentName = (filename:string) => filename.replace(/^NF-KB-\d+_/, '').replace(/\.md$/, '').replaceAll('_', ' ');

export default function App() {
  const assistant = useRef<AssistantHandle>(null);
  const [data, setData] = useState<Workspace|null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tableError, setTableError] = useState('');
  const [tableLoading, setTableLoading] = useState(false);
  const [libraryTab, setLibraryTab] = useState<LibraryTab>('knowledge');
  const [recommendationTab, setRecommendationTab] = useState<RecommendationTab>('견적·도면');
  const [sidePanel, setSidePanel] = useState<SidePanel>(null);
  const [search, setSearch] = useState('');
  const [selectedRow, setSelectedRow] = useState<Row|null>(null);
  const [selectedDocument, setSelectedDocument] = useState<Document|null>(null);
  const [selectedTable, setSelectedTable] = useState('quote_requests');
  const [contextLot, setContextLot] = useState('');
  const [token, setToken] = useState(readAccessCode);
  const [connectionVersion, setConnectionVersion] = useState(0);
  const [settings, setSettings] = useState(() => new URLSearchParams(location.search).get('setup') === 'openai');
  const [history, setHistory] = useState<string[]>(() => {
    try { return (() => { const value:unknown = JSON.parse(sessionStorage.getItem('onetouch_question_history') || '[]'); return Array.isArray(value) ? value.filter((item):item is string => typeof item === 'string').slice(0,20) : []; })(); }
    catch { return []; }
  });

  function load() {
    setLoading(true); setError('');
    Promise.all([request<Workspace>('/workspace'), request<Document[]>('/documents')])
      .then(([workspace, docs]) => { setData(workspace); setDocuments(docs); })
      .catch(reason => setError(reason.message)).finally(() => setLoading(false));
  }
  useEffect(load, []);
  useEffect(() => {
    const sync = (event: StorageEvent) => { if (event.key === 'onetouch_access_token' || event.key === null) setToken(readAccessCode()); };
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);
  useEffect(() => {
    if (!data || libraryTab !== 'data') return;
    const controller = new AbortController(); setRows([]); setTableLoading(true); setTableError('');
    request<Row[]>(`/tables/${selectedTable}?limit=10&offset=0`, {signal:controller.signal}).then(setRows).catch(reason => {if(!controller.signal.aborted)setTableError(reason.message)}).finally(() => {if(!controller.signal.aborted)setTableLoading(false)});
    return () => controller.abort();
  }, [data, selectedTable, libraryTab]);
  useEffect(() => {
    if (!sidePanel) return;
    const close = (event:KeyboardEvent) => { if (event.key === 'Escape') setSidePanel(null); };
    document.body.classList.add('panel-open'); window.addEventListener('keydown', close);
    return () => { document.body.classList.remove('panel-open'); window.removeEventListener('keydown', close); };
  }, [sidePanel]);
  useEffect(() => { sessionStorage.setItem('onetouch_question_history', JSON.stringify(history)); }, [history]);

  const recommendations = useMemo(() => data?.questions[recommendationTab]?.slice(0, 10) ?? [], [data, recommendationTab]);
  const filteredDocuments = documents.filter(document => `${document.filename} ${document.content}`.toLowerCase().includes(search.toLowerCase()));
  const activeTable = data?.tables.find(table => table.table === selectedTable);
  function ask(question:string) { assistant.current?.ask(question, contextLot); setSidePanel(null); }
  function rememberQuestion(question:string) { setHistory(items => [question, ...items.filter(item => item !== question)].slice(0, 20)); }

  if (loading) return <div className="state-page"><LoaderCircle className="spin"/><h1>원터치 제조 기록을 준비하고 있습니다.</h1></div>;
  if (error || !data) return <div className="state-page" role="alert"><CircleAlert/><h1>기록을 불러오지 못했습니다.</h1><p>{error}</p><button className="primary-button" onClick={load}>다시 연결</button></div>;

  return <div className="onetouch-app">
    <header className="app-header">
      <div className="brand"><span className="brand-mark"><Factory size={22}/></span><div><strong>원터치 견적 AI</strong><small>도면 · 견적 · 원가</small></div></div>
      <div className="record-status"><span>샘플 기록 기준</span><strong>{data.meta.as_of}</strong></div>
      <div className="header-actions"><button className="mobile-panel-button" onClick={() => setSidePanel('library')}><Menu size={18}/>자료</button><button className="mobile-panel-button" onClick={() => setSidePanel('questions')}><Sparkles size={18}/>질문</button><button className="icon-button" aria-label="데이터 새로고침" onClick={load}><RefreshCw size={18}/></button><button className="settings-button" onClick={() => { setSettings(true); }}><Settings2 size={17}/>연결 설정</button></div>
    </header>

    {sidePanel && <button className="panel-backdrop" aria-label="패널 닫기" onClick={() => setSidePanel(null)}/>}
    <div className="workspace-grid">
      <aside className={`question-panel ${sidePanel === 'questions' ? 'mobile-open' : ''}`}>
        <div className="side-heading"><div><span>질문</span><h2>후보 질문과 이력</h2></div><button className="icon-button mobile-close" aria-label="질문 패널 닫기" onClick={() => setSidePanel(null)}><X size={18}/></button></div>
        <section className="history-section"><h3><History size={17}/>최근 질문 <span>{history.length}</span></h3>{history.length ? <div className="history-list">{history.map((question, index) => <button key={`${question}-${index}`} onClick={() => ask(question)}><span>{question}</span><ChevronRight size={15}/></button>)}</div> : <p className="empty-note">이 세션에서 질문하면 여기에 쌓입니다.</p>}</section>
        <section className="recommend-section"><h3><Sparkles size={17}/>질문 예시</h3><div className="recommend-tabs" role="tablist" aria-label="질문 예시 분류"><button role="tab" aria-selected={recommendationTab === '견적·도면'} className={recommendationTab === '견적·도면' ? 'active' : ''} onClick={() => setRecommendationTab('견적·도면')}>견적·도면</button><button role="tab" aria-selected={recommendationTab === '문서·규칙'} className={recommendationTab === '문서·규칙' ? 'active' : ''} onClick={() => setRecommendationTab('문서·규칙')}>문서·규칙</button></div><ol>{recommendations.map((question, index) => <li key={question}><button onClick={() => ask(question)}><span>{String(index + 1).padStart(2, '0')}</span>{question}</button></li>)}</ol></section>
      </aside>
      <main className="conversation-panel"><Assistant key={connectionVersion} ref={assistant} data={data} token={token} user={null} lot={contextLot} onLot={setContextLot} onSettings={() => { setSettings(true); }} onSave={() => setSettings(true)} work={null} open={false} onClose={() => {}} onQuestion={rememberQuestion}/></main>

      <aside className={`library-panel ${sidePanel === 'library' ? 'mobile-open' : ''}`}>
        <div className="side-heading"><div><span>연결된 자료</span><h2>지식베이스 · DB</h2></div><button className="icon-button mobile-close" aria-label="자료 패널 닫기" onClick={() => setSidePanel(null)}><X size={18}/></button></div>
        <div className="library-tabs" role="tablist"><button role="tab" aria-selected={libraryTab === 'knowledge'} className={libraryTab === 'knowledge' ? 'active' : ''} onClick={() => setLibraryTab('knowledge')}><BookOpen size={17}/>지식베이스</button><button role="tab" aria-selected={libraryTab === 'data'} className={libraryTab === 'data' ? 'active' : ''} onClick={() => setLibraryTab('data')}><Database size={17}/>데이터허브</button></div>
        {libraryTab === 'knowledge' ? <><label className="side-search"><Search size={16}/><span className="sr-only">문서 검색</span><input value={search} onChange={event => setSearch(event.target.value)} placeholder="문서명 또는 공정 검색"/></label><p className="source-note">샘플 지식베이스 {documents.length}개 · 미승인 예시</p><div className="document-list">{filteredDocuments.map(document => <button key={document.document_id} onClick={() => setSelectedDocument(document)}><FileText size={18}/><span><strong>{document.title || cleanDocumentName(document.filename)}</strong><small>{document.source} / {document.status}</small></span><ChevronRight size={16}/></button>)}</div>{!filteredDocuments.length && <p className="empty-note">등록된 문서가 없습니다.</p>}</> : <><label className="table-picker">조회할 데이터<select value={selectedTable} onChange={event => setSelectedTable(event.target.value)}>{data.tables.map(table => <option key={table.table} value={table.table}>{table.label} ({table.count})</option>)}</select></label><p className="source-note">{data.meta.backend} · 샘플 데이터 조회 전용</p><div className="data-preview"><div><Table2 size={18}/><strong>{activeTable?.label}</strong><span>{activeTable?.count ?? 0}건</span></div>{tableLoading && <p className="empty-note" role="status">기록을 불러오는 중입니다.</p>}{tableError && <p className="empty-note" role="alert">{tableError}</p>}{rows.slice(0, 10).map((row, index) => <button key={index} onClick={() => setSelectedRow(row)}><span>{String(row.quote_id ?? row.drawing_id ?? row.rule_id ?? row.material_code ?? row.item_name ?? row.name ?? `기록 ${index + 1}`)}</span><ChevronRight size={15}/></button>)}</div></>}
      </aside>


    </div>

    {selectedRow && <Modal title="원본 레코드 · 샘플 데이터" onClose={() => setSelectedRow(null)}><pre className="document-content">{JSON.stringify(selectedRow,null,2)}</pre></Modal>}
    {selectedDocument && <Modal title={selectedDocument.title || cleanDocumentName(selectedDocument.filename)} onClose={() => setSelectedDocument(null)}><div className="document-meta"><code>{selectedDocument.document_id}</code><span>{selectedDocument.status}</span></div><pre className="document-content">{selectedDocument.content}</pre></Modal>}
    {settings && <Modal title="AI 연결 설정" onClose={() => setSettings(false)}><ConnectionSettings data={data} token={token} onToken={setToken} onConfigured={() => { setConnectionVersion(value => value + 1); setData(current => current ? {...current, meta: {...current.meta, ai_configured: true}} : current); }} onClose={() => setSettings(false)}/></Modal>}
  </div>;
}
