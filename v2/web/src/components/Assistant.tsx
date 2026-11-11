import {forwardRef,useEffect,useImperativeHandle,useRef,useState} from 'react';
import {Mic,MicOff,PhoneOff,Play,Send,X,Volume2,RotateCcw,Copy,Check,LoaderCircle} from 'lucide-react';
import {request,track,type Answer,type Workspace,type User,type WorkItem} from '../types';

import {useVoice} from '../hooks/useVoice';
import {useRealtimeVoice} from '../hooks/useRealtimeVoice';

export type AssistantHandle={ask:(text:string,lot?:string)=>void;focus:()=>void};
type Props={data:Workspace;token:string;user:User|null;lot:string;onLot:(lot:string)=>void;onSettings:()=>void;onSave:(answer:Answer,question:string)=>void;work:WorkItem|null;open:boolean;onClose:()=>void;voiceFirst?:boolean;onQuestion?:(question:string)=>void};
export const Assistant=forwardRef<AssistantHandle,Props>(function Assistant({data,token,user,lot,onLot,onSettings,onSave,work,open,onClose,voiceFirst=false,onQuestion},ref){
 const mode:'ai'|'demo'=data.meta.ai_configured?'ai':'demo';
 const [copied,setCopied]=useState<number|null>(null);
 const [text,setText]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [pendingQuestion,setPendingQuestion]=useState('');
 const [messages,setMessages]=useState<{question:string;answer:Answer}[]>([]),[transcribed,setTranscribed]=useState(false),[liveTurns,setLiveTurns]=useState<{role:'user'|'assistant';text:string;answer?:Answer}[]>([]);
 const staged=useRef<string|null>(null),heard=useRef('');
 const lock=useRef(false),epoch=useRef(0),abort=useRef<AbortController|null>(null),input=useRef<HTMLTextAreaElement>(null),panel=useRef<HTMLElement>(null),chatScroll=useRef<HTMLDivElement>(null);
 const voice=useVoice(token,value=>{setText(value);heard.current=value;setTranscribed(true);input.current?.focus()});
 const realtime=useRealtimeVoice(token,lot,turn=>setLiveTurns(items=>[...items,turn]),(_name,output)=>{try{const answer=JSON.parse(output) as Answer;if(answer.text&&answer.records)setLiveTurns(items=>[...items,{role:'assistant',text:answer.text,answer}])}catch{}});
 const voiceAvailable=data.meta.ai_configured&&(!!token||!!data.meta.local_dev_ai);
 function cancel(){epoch.current++;abort.current?.abort();lock.current=false;setBusy(false);setPendingQuestion('');voice.cancel();realtime.stop()}
 useEffect(()=>{cancel();setMessages(work?.snapshots?.length?work.snapshots:work?.snapshot?[work.snapshot]:[]);setLiveTurns([]);setText(staged.current||'');staged.current=null;setError('');setTranscribed(false);setCopied(null)},[lot,work?.id,user?.id,token,mode]);
 useEffect(()=>()=>{epoch.current++;abort.current?.abort()},[]);
 useEffect(()=>{if(!open)return;const previous=document.activeElement as HTMLElement|null;input.current?.focus();return()=>previous?.focus()},[open]);
 useEffect(()=>{if(!open){voice.cancel();realtime.stop()}},[open]);
 useEffect(()=>{const frame=requestAnimationFrame(()=>{const node=chatScroll.current;const latest=node?.querySelector<HTMLElement>('.exchange:last-of-type .assistant-message');if(node&&latest)node.scrollTop+=latest.getBoundingClientRect().top-node.getBoundingClientRect().top});return()=>cancelAnimationFrame(frame)},[messages.length]);
 useEffect(()=>{const node=chatScroll.current;const users=node?.querySelectorAll<HTMLElement>('.user-message.live-caption');const latest=users?.[users.length-1];if(node&&latest)node.scrollTop+=latest.getBoundingClientRect().top-node.getBoundingClientRect().top},[liveTurns.filter(t=>t.role==='user').length]);
 async function ask(question:string,explicitLot?:string,source:'text'|'suggestion'='suggestion'){
   if(lock.current||!question.trim())return;
   onQuestion?.(question.trim());
   const selected=explicitLot??lot;
   if(explicitLot!==undefined&&(explicitLot!==lot||work)){staged.current=question;onLot(explicitLot);return}
   lock.current=true;setBusy(true);setPendingQuestion(question.trim());setError('');voice.cancel();realtime.stop();const run=epoch.current;abort.current=new AbortController();
   const spoken=transcribed&&source==='text';if(spoken&&question!==heard.current)track('transcript_edited');track('question_submitted',{source:spoken?'voice':source,mode});const began=performance.now();
   try{
    const answer=await request<Answer>('/chat',{method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},body:JSON.stringify({question,quote_id:selected||null,history:messages.slice(-6).map(m=>({question:m.question,answer:m.answer.text})),mode}),signal:abort.current.signal});
    if(run!==epoch.current)return;
    if(answer.ignored){setPendingQuestion('');return;}
    track('answer_ready',{mode,duration_ms:performance.now()-began});
    setMessages(m=>[...m,{question,answer}]);setPendingQuestion('');setText('');setTranscribed(false);
   }catch(e){if(run===epoch.current&&(e as Error).name!=='AbortError'){setPendingQuestion('');setError((e as Error).message);setText(question)}}
   finally{if(run===epoch.current){setBusy(false);lock.current=false}}
 }
 useImperativeHandle(ref,()=>({ask,focus:()=>input.current?.focus()}));
 function reset(){cancel();setMessages([]);setLiveTurns([]);setText('');setError('');setTranscribed(false);setCopied(null)}
 function trap(e:React.KeyboardEvent){if(!open)return;if(e.key==='Escape'){voice.cancel();onClose()}if(e.key==='Tab'){const nodes=Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea,select,summary')??[]).filter(el=>el.getClientRects().length);const first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}}
 return <aside ref={panel} className={`assistant-panel ${open?'mobile-open':''} ${voiceFirst?'voice-first':''}`} role={open?'dialog':undefined} aria-modal={open||undefined} aria-label="업무 에이전트" onKeyDown={trap}>
  <header className="agent-header"><div><span className="eyebrow">CAD · BOM · 공정 · 원가</span><h2>원터치 에이전트</h2></div><button className="icon-btn" aria-label="대화 초기화" onClick={reset}><RotateCcw size={18}/></button><button className="icon-btn agent-close" aria-label="대화 닫기" onClick={()=>{voice.cancel();onClose()}}><X/></button></header>
  {work&&<p className="context-note">이어 보는 업무: {work.title}</p>}
  <div className="chat-scroll" ref={chatScroll}>
    {!messages.length&&!pendingQuestion&&!liveTurns.length&&<div className="agent-welcome"><h3>오늘 궁금한거 질문해!!</h3></div>}
    {messages.map((m,i)=><article className="exchange" key={i}><p className="user-message">{m.question}</p><div className="assistant-message"><div className="answer-label">{m.answer.mode==='demo'?'자료 조회':'AI 분석'}</div><Analysis answer={m.answer}/><small>질문 대상: {m.answer.context?.quote_id||'전체 기록'}</small><details onToggle={e=>{if(e.currentTarget.open)track('evidence_opened')}}><summary>출처 · 샘플/미승인 · 문서 {m.answer.evidence.length}개 · 조회 기록 {m.answer.records.length}건</summary>{m.answer.evidence.map((ev,j)=><details className="source-detail" key={j}><summary>{ev.filename}</summary><pre>{ev.text}</pre></details>)}{m.answer.records.map((row,j)=><details className="source-detail" key={j}><summary>기록 {j+1} · {String(row.quote_id??row.item_name??row.name??'조회 결과')}</summary><pre>{JSON.stringify(row,null,2)}</pre></details>)}{!m.answer.evidence.length&&!m.answer.records.length&&<p>연결된 근거가 없습니다.</p>}</details><div className="answer-actions"><button disabled={!voiceAvailable||realtime.active} onClick={()=>voice.speak(m.answer.summary||m.answer.text)}><Volume2 size={16}/>답변 듣기</button><button onClick={async()=>{const content=`${m.question}\n\n${m.answer.text}\n\n질문 대상: ${m.answer.context?.quote_id||'전체 기록'}\n근거 문서: ${m.answer.evidence.map(e=>e.filename).join(', ')||'없음'}`;try{if(navigator.clipboard&&window.isSecureContext)await navigator.clipboard.writeText(content);else{const field=document.createElement('textarea');field.value=content;field.style.position='fixed';field.style.opacity='0';document.body.appendChild(field);field.select();const ok=document.execCommand('copy');field.remove();if(!ok)throw new Error('copy');}setCopied(i)}catch{setError('복사하지 못했습니다. 답변을 선택해 복사해 주세요.')}}}>{copied===i?<Check size={16}/>:<Copy size={16}/>} {copied===i?'복사 완료':'답변 복사'}</button></div>{m.answer.captured_at&&<small>근거 보존: {new Date(m.answer.captured_at).toLocaleString('ko-KR')}</small>}</div></article>)}
    {liveTurns.map((turn,i)=>turn.role==='user'?<p className="user-message live-caption" key={`live-${i}`}>{turn.text}</p>:<div className="assistant-message live-caption" key={`live-${i}`}><div className="answer-label">실시간 음성 · AI 답변</div>{turn.answer?<Analysis answer={turn.answer}/>:<p>{turn.text}</p>}</div>)}
    {pendingQuestion&&<p className="user-message pending-message">{pendingQuestion}</p>}
    {busy&&<p role="status" className="thinking"><LoaderCircle className="spin" size={18}/>기록을 확인하고 있습니다. <button onClick={cancel}>대기 취소</button></p>}
  </div>
  <div className={`realtime-voice ${realtime.active?'active':''}`} aria-live="polite">
   {!realtime.active?<button className="voice-start" disabled={busy} onClick={()=>{if(!voiceAvailable){onSettings();return}voice.cancel();setLiveTurns([]);void realtime.start()}}><Mic size={22}/>{voiceAvailable?'음성 질문 시작':'음성 연결 설정'}</button>:<><div className="live-status"><i/><span>{realtime.state==='permission'?'마이크 권한 확인 중':realtime.state==='connecting'?'연결 중':realtime.state==='speaking'?'듣고 있어요':realtime.state==='responding'?'답변 준비 중':'편하게 말씀하세요'}</span></div><button className="icon-btn" aria-label={realtime.muted?'마이크 켜기':'마이크 끄기'} onClick={realtime.toggleMute}>{realtime.muted?<MicOff size={19}/>:<Mic size={19}/>}</button>{realtime.needsPlay&&<button className="icon-btn" aria-label="음성 재생" onClick={()=>void realtime.play()}><Play size={19}/></button>}<button className="voice-end" onClick={realtime.stop}><PhoneOff size={17}/>종료</button></>}
  </div>
  {voice.state==='ready'&&<button className="listen-button" onClick={()=>void voice.play()}><Play size={16}/>준비된 음성 재생</button>}
  {['generating','ready','playing'].includes(voice.state)&&<button className="listen-button" onClick={voice.cancel}><X size={16}/>답변 음성 중지</button>}
  {voice.error&&<p className="voice-error" role="alert">{voice.error}</p>}
  {realtime.error&&<p className="voice-error" role="alert">{realtime.error}</p>}
  {error&&<p className="voice-error" role="alert">{error}</p>}
  <form className="composer" onSubmit={e=>{e.preventDefault();ask(text,undefined,'text')}}>{transcribed&&<p className="transcript-notice">인식한 문장과 견적·수치를 확인한 뒤 보내세요.</p>}<textarea ref={input} aria-label="에이전트에게 질문" value={text} onChange={e=>setText(e.target.value)} rows={2} maxLength={2000} placeholder="견적·도면·BOM·원가에 대해 질문하세요" onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing&&e.keyCode!==229){e.preventDefault();if(voice.state==='idle')void ask(text,undefined,'text')}}} disabled={busy||realtime.active||voice.state!=='idle'}/><div><small>Enter로 보내기 · Shift+Enter 줄바꿈</small><button className="send-button" aria-label="질문 보내기" disabled={!text.trim()||busy||realtime.active||voice.state!=='idle'}><Send size={18}/><span>보내기</span></button></div></form>
  <p className="assistant-disclaimer">{voiceAvailable?'호출명 없이 질문하세요. 음성은 실시간 처리를 위해 전송됩니다.':'음성 사용은 설정에서 AI 연결이 필요합니다.'}<br/>견적 확정·고객 발송은 담당자가 결정합니다.</p>
 </aside>
});

const columnLabels:Record<string,string>={quote_id:'견적 ID',drawing_id:'도면 ID',estimated_total_krw:'원가 후보(원)',material_cost_krw:'재료비(원)',labor_cost_krw:'가공비(원)',confidence:'신뢰도',review_route:'검토경로',specification:'규격',quantity:'소요량',unit:'단위',amount_krw:'금액(원)',unit_price_krw:'단가(원)',setup_min:'준비시간(분)',run_min:'가공시간(분)',available_kg:'가용재고(kg)',reserved_kg:'예약재고(kg)',free_kg:'미예약재고(kg)',safety_stock_kg:'안전재고(kg)',length_mm:'길이(mm)',width_mm:'폭(mm)',height_mm:'높이(mm)',thickness_mm:'두께(mm)',feature_confidence:'추출 신뢰도',status:'상태',source_tool:'조회 도구',demo_data:'샘플 여부'};
function Analysis({answer}:{answer:Answer}){return <div className="compound-answer">{answer.comparison_tables?.map((t,i)=><section key={i}><h4>{t.title}</h4><div className="comparison-scroll"><table><thead><tr>{t.columns.map(c=><th key={c}>{columnLabels[c]||c}</th>)}</tr></thead><tbody>{t.rows.map((r,j)=><tr key={j}>{r.map((v,k)=><td key={k}>{v}</td>)}</tr>)}</tbody></table></div></section>)}{answer.comparison_tables?.length?<details><summary>상세 분석 보기</summary><p>{answer.text}</p></details>:<p>{answer.text}</p>}<details><summary>요청별 답변 확인</summary>{answer.request_coverage?.map((c,i)=><p key={i}><strong>{c.status==='answered'?'근거 연결 확인':'추가 확인 필요'}</strong> · {c.request}</p>)}<small>답변 인용과 근거 연결 검사이며 정확성 보증은 아닙니다.</small></details>{answer.lookup_errors?.map((e,i)=><p key={i}>{e.tool}: {e.message}</p>)}</div>}
