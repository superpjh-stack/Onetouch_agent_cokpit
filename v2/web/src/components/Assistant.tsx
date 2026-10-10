import {forwardRef,useEffect,useImperativeHandle,useRef,useState} from 'react';
import {Mic,MicOff,PhoneOff,Play,Send,X,Volume2,RotateCcw,Save,LoaderCircle} from 'lucide-react';
import {request,track,type Answer,type Workspace,type User,type WorkItem} from '../types';
import {useVoice} from '../hooks/useVoice';
import {useRealtimeVoice} from '../hooks/useRealtimeVoice';

export type AssistantHandle={ask:(text:string,lot?:string)=>void;focus:()=>void};
type Props={data:Workspace;token:string;user:User|null;lot:string;onLot:(lot:string)=>void;onSettings:()=>void;onSave:(answer:Answer,question:string)=>void;work:WorkItem|null;open:boolean;onClose:()=>void;voiceFirst?:boolean;onQuestion?:(question:string)=>void};
export const Assistant=forwardRef<AssistantHandle,Props>(function Assistant({data,token,user,lot,onLot,onSettings,onSave,work,open,onClose,voiceFirst=false,onQuestion},ref){
 const [mode,setMode]=useState<'ai'|'demo'>(data.meta.ai_configured?'ai':'demo');
 const [text,setText]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [pendingQuestion,setPendingQuestion]=useState('');
 const [messages,setMessages]=useState<{question:string;answer:Answer}[]>([]),[transcribed,setTranscribed]=useState(false),[liveTurns,setLiveTurns]=useState<{role:'user'|'assistant';text:string}[]>([]);
 const staged=useRef<string|null>(null),heard=useRef('');
 const lock=useRef(false),epoch=useRef(0),abort=useRef<AbortController|null>(null),input=useRef<HTMLTextAreaElement>(null),panel=useRef<HTMLElement>(null),chatScroll=useRef<HTMLDivElement>(null);
 const voice=useVoice(token,value=>{setText(value);heard.current=value;setTranscribed(true);input.current?.focus()});
 const realtime=useRealtimeVoice(token,lot,turn=>setLiveTurns(items=>[...items,turn]));
 const voiceAvailable=data.meta.ai_configured&&(!!token||!!data.meta.local_dev_ai);
 function cancel(){epoch.current++;abort.current?.abort();lock.current=false;setBusy(false);setPendingQuestion('');voice.cancel();realtime.stop()}
 useEffect(()=>{cancel();setMessages(work?.snapshots?.length?work.snapshots:work?.snapshot?[work.snapshot]:[]);setLiveTurns([]);setText(staged.current||'');staged.current=null;setError('');setTranscribed(false)},[lot,work?.id,user?.id,token,mode]);
 useEffect(()=>()=>{epoch.current++;abort.current?.abort()},[]);
 useEffect(()=>{if(!open)return;const previous=document.activeElement as HTMLElement|null;input.current?.focus();return()=>previous?.focus()},[open]);
 useEffect(()=>{if(!open){voice.cancel();realtime.stop()}},[open]);
 useEffect(()=>{const frame=requestAnimationFrame(()=>{const node=chatScroll.current;if(node)node.scrollTop=node.scrollHeight});return()=>cancelAnimationFrame(frame)},[messages,pendingQuestion,busy,error,liveTurns]);
 async function ask(question:string,explicitLot?:string,source:'text'|'suggestion'='suggestion'){
   if(lock.current||!question.trim())return;
   onQuestion?.(question.trim());
   const selected=explicitLot??lot;
   if(explicitLot!==undefined&&(explicitLot!==lot||work)){staged.current=question;onLot(explicitLot);return}
   lock.current=true;setBusy(true);setPendingQuestion(question.trim());setError('');voice.cancel();const run=epoch.current;abort.current=new AbortController();
   const spoken=transcribed&&source==='text';if(spoken&&question!==heard.current)track('transcript_edited');track('question_submitted',{source:spoken?'voice':source,mode});const began=performance.now();
   try{
    const answer=await request<Answer>('/chat',{method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},body:JSON.stringify({question,quote_id:selected||null,history:messages.slice(-6).map(m=>({question:m.question,answer:m.answer.text})),mode}),signal:abort.current.signal});
    if(run!==epoch.current)return;
    track('answer_ready',{mode,duration_ms:performance.now()-began});
    setMessages(m=>[...m,{question,answer}]);setPendingQuestion('');setText('');setTranscribed(false);
   }catch(e){if(run===epoch.current&&(e as Error).name!=='AbortError'){setPendingQuestion('');setError((e as Error).message);setText(question)}}
   finally{if(run===epoch.current){setBusy(false);lock.current=false}}
 }
 useImperativeHandle(ref,()=>({ask,focus:()=>input.current?.focus()}));
 function reset(){cancel();setMessages([]);setLiveTurns([]);setText('');setError('');setTranscribed(false)}
 function trap(e:React.KeyboardEvent){if(!open)return;if(e.key==='Escape'){voice.cancel();onClose()}if(e.key==='Tab'){const nodes=Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea,select,summary')??[]).filter(el=>el.getClientRects().length);const first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}}
 return <aside ref={panel} className={`assistant-panel ${open?'mobile-open':''} ${voiceFirst?'voice-first':''}`} role={open?'dialog':undefined} aria-modal={open||undefined} aria-label="업무 에이전트" onKeyDown={trap}>
  <header className="agent-header"><div><span className="eyebrow">CAD · BOM · 공정 · 원가</span><h2>원터치 AI Agent</h2><p>견적과 문서 근거를 함께 찾아 간결하게 답합니다.</p></div><button className="icon-btn" aria-label="대화 초기화" onClick={reset}><RotateCcw size={18}/></button><button className="icon-btn agent-close" aria-label="대화 닫기" onClick={()=>{voice.cancel();onClose()}}><X/></button></header>
  <label className="context-picker">응답 방식<select aria-label="응답 방식" value={mode} onChange={e=>setMode(e.target.value as 'demo'|'ai')}><option value="demo">데모 조회 · AI 분석 아님</option><option value="ai" disabled={!data.meta.ai_configured}>AI 분석</option></select></label>
  <label className="context-picker">질문 대상 견적<select value={lot} disabled={!!work} onChange={e=>onLot(e.target.value)}><option value="">전체 기록</option>{data.quotes.map(l=><option value={l.quote_id} key={l.quote_id}>{l.quote_id} · {l.product_name}</option>)}</select></label>
  {work&&<p className="context-note">이어 보는 업무: {work.title}</p>}
  <div className="chat-scroll" ref={chatScroll}>
    {!messages.length&&!pendingQuestion&&<div className="agent-welcome"><h3>확인할 일을<br/>말씀해 주세요.</h3><p>선택한 견적과 원터치 기록을 기준으로 다음 확인사항을 정리합니다.</p><div className="suggestions">{['견적 요청과 승인대기 현황을 알려줘','선택 견적의 원가와 BOM을 알려줘','도면 예외와 수작업 전환 대상을 알려줘'].map(q=><button disabled={busy} onClick={()=>ask(q)} key={q}>{q}</button>)}</div></div>}
    {messages.map((m,i)=><article className="exchange" key={i}><p className="user-message">{m.question}</p><div className="assistant-message"><div className="answer-label">{m.answer.mode==='demo'?'데모 조회 · AI 분석 아님':'AI 답변 · 조회 전용'}</div><p>{m.answer.text}</p><small>질문 대상: {m.answer.context?.quote_id||'전체 기록'}</small><details onToggle={e=>{if(e.currentTarget.open)track('evidence_opened')}}><summary>문서 {m.answer.evidence.length}개 · 조회 기록 {m.answer.records.length}건</summary>{m.answer.evidence.map((ev,j)=><details className="source-detail" key={j}><summary>{ev.filename}</summary><pre>{ev.text}</pre></details>)}{m.answer.records.map((row,j)=><details className="source-detail" key={j}><summary>기록 {j+1} · {String(row.quote_id??row.item_name??row.name??'조회 결과')}</summary><pre>{JSON.stringify(row,null,2)}</pre></details>)}{!m.answer.evidence.length&&!m.answer.records.length&&<p>연결된 근거가 없습니다.</p>}</details><div className="answer-actions"><button disabled={!voiceAvailable||realtime.active} onClick={()=>voice.speak(m.answer.summary||m.answer.text)}><Volume2 size={16}/>답변 듣기</button></div>{m.answer.captured_at&&<small>근거 보존: {new Date(m.answer.captured_at).toLocaleString('ko-KR')}</small>}</div></article>)}
    {liveTurns.map((turn,i)=>turn.role==='user'?<p className="user-message live-caption" key={`live-${i}`}>{turn.text}</p>:<div className="assistant-message live-caption" key={`live-${i}`}><div className="answer-label">실시간 음성 · AI 답변</div><p>{turn.text}</p></div>)}
    {pendingQuestion&&<p className="user-message pending-message">{pendingQuestion}</p>}
    {busy&&<p role="status" className="thinking"><LoaderCircle className="spin" size={18}/>기록을 확인하고 있습니다. <button onClick={cancel}>대기 취소</button></p>}
  </div>
  <div className={`realtime-voice ${realtime.active?'active':''}`} aria-live="polite">
   {!realtime.active?<button className="voice-start" disabled={busy} onClick={()=>{if(!voiceAvailable){onSettings();return}voice.cancel();setLiveTurns([]);void realtime.start()}}><Mic size={22}/>{voiceAvailable?'음성 질문 시작':'음성 연결 설정'}</button>:<><div className="live-status"><i/><span>{realtime.state==='permission'?'마이크 권한 확인 중':realtime.state==='connecting'?'연결 중':realtime.state==='speaking'?'듣고 있어요':realtime.state==='responding'?'답변 준비 중':'말씀해 주세요'}</span></div><button className="icon-btn" aria-label={realtime.muted?'마이크 켜기':'마이크 끄기'} onClick={realtime.toggleMute}>{realtime.muted?<MicOff size={19}/>:<Mic size={19}/>}</button>{realtime.needsPlay&&<button className="icon-btn" aria-label="음성 재생" onClick={()=>void realtime.play()}><Play size={19}/></button>}<button className="voice-end" onClick={realtime.stop}><PhoneOff size={17}/>종료</button></>}
  </div>
  {voice.state==='ready'&&<button className="listen-button" onClick={()=>void voice.play()}><Play size={16}/>준비된 음성 재생</button>}
  {['generating','ready','playing'].includes(voice.state)&&<button className="listen-button" onClick={voice.cancel}><X size={16}/>답변 음성 중지</button>}
  {voice.error&&<p className="voice-error" role="alert">{voice.error}</p>}
  {realtime.error&&<p className="voice-error" role="alert">{realtime.error}</p>}
  {error&&<p className="voice-error" role="alert">{error}</p>}
  <form className="composer" onSubmit={e=>{e.preventDefault();ask(text,undefined,'text')}}>{transcribed&&<p className="transcript-notice">인식한 문장과 견적·수치를 확인한 뒤 보내세요.</p>}<textarea ref={input} aria-label="에이전트에게 질문" value={text} onChange={e=>setText(e.target.value)} rows={3} maxLength={2000} placeholder="질문을 입력하거나 말해 주세요" disabled={busy||voice.state!=='idle'}/><div><small>{mode==='demo'?'샘플 DB·문서 조회':'AI 지식 응답'}</small><button className="send-button" aria-label="질문 보내기" disabled={!text.trim()||busy||voice.state!=='idle'}><Send size={18}/></button></div></form>
  <p className="assistant-disclaimer">{voiceAvailable?'마이크 음성은 실시간 처리되며 앱에 녹음 파일로 저장하지 않습니다.':'음성 사용은 설정에서 AI 연결이 필요합니다.'}<br/>견적 확정·고객 발송은 담당자가 결정합니다.</p>
 </aside>
});
