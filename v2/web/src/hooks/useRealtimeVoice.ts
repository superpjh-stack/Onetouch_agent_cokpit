import {useCallback,useEffect,useRef,useState} from 'react';
import {track} from '../types';

export type RealtimeVoiceState='idle'|'permission'|'connecting'|'listening'|'speaking'|'responding'|'error';
type Turn={role:'user'|'assistant';text:string};

export function useRealtimeVoice(token:string,lot:string,onTurn:(turn:Turn)=>void){
 const [state,setState]=useState<RealtimeVoiceState>('idle'),[error,setError]=useState(''),[muted,setMuted]=useState(false),[needsPlay,setNeedsPlay]=useState(false);
 const pc=useRef<RTCPeerConnection|null>(null),channel=useRef<RTCDataChannel|null>(null),media=useRef<MediaStream|null>(null),audio=useRef<HTMLAudioElement|null>(null),epoch=useRef(0);
 const toolCalls=useRef(new Set<string>());
 const completedResponses=useRef(new Set<string>()),transcripts=useRef(new Set<string>());
 const responseTurns=useRef(new Map<string,number>());
 const turnEpoch=useRef(0),responseActive=useRef(false),pendingContinuation=useRef(false),userSpeaking=useRef(false);
 const controller=useRef<AbortController|null>(null),connectTimer=useRef<ReturnType<typeof setTimeout>|null>(null),starting=useRef(false);
 const assistantText=useRef(''),callback=useRef(onTurn);callback.current=onTurn;
 const supported=window.isSecureContext&&!!navigator.mediaDevices?.getUserMedia&&typeof RTCPeerConnection!=='undefined';

 const stop=useCallback(()=>{
  epoch.current++;starting.current=false;
  turnEpoch.current++;responseActive.current=false;pendingContinuation.current=false;userSpeaking.current=false;
  completedResponses.current.clear();transcripts.current.clear();
  responseTurns.current.clear();
  controller.current?.abort();controller.current=null;
  if(connectTimer.current)clearTimeout(connectTimer.current);connectTimer.current=null;
  channel.current?.close();channel.current=null;
  pc.current?.close();pc.current=null;
  media.current?.getTracks().forEach(t=>t.stop());media.current=null;
  if(audio.current){audio.current.pause();audio.current.srcObject=null;audio.current.remove()}audio.current=null;
  assistantText.current='';toolCalls.current.clear();setMuted(false);setNeedsPlay(false);setError('');setState('idle');
 },[]);
 useEffect(()=>()=>stop(),[stop]);
 useEffect(()=>{stop()},[token,lot,stop]);

 const play=useCallback(async()=>{const player=audio.current,run=epoch.current;if(!player)return;try{await player.play();if(run===epoch.current){setNeedsPlay(false);setError('')}}catch{if(run===epoch.current){setNeedsPlay(true);setError('소리가 준비됐습니다. 재생을 눌러 주세요.')}}},[]);
 function finishAssistant(text?:string){const final=(text||assistantText.current).trim();assistantText.current='';if(final)callback.current({role:'assistant',text:final})}
 function continueResponse(){
  if(!pendingContinuation.current||responseActive.current||userSpeaking.current||channel.current?.readyState!=='open')return;
  pendingContinuation.current=false;responseActive.current=true;
  channel.current.send(JSON.stringify({type:'response.create'}));
 }
 async function runTool(name:string,callId:string,argumentsText:string,run:number,turn:number){
  if(run!==epoch.current||toolCalls.current.has(callId))return;toolCalls.current.add(callId);setState('responding');
  let args:Record<string,unknown>={};
  try{args=JSON.parse(argumentsText||'{}') as Record<string,unknown>}catch{args={}}
  let output:string;
  try{
   const response=await fetch('/api/realtime/tool',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({name,arguments:args}),signal:controller.current?.signal});
   const payload=await response.json().catch(()=>({}));
   if(!response.ok)throw new Error(String(payload.detail||'데이터 플랫폼 도구 호출에 실패했습니다.'));
   output=String(payload.output||JSON.stringify({error:'빈 도구 응답'}));
  }catch(e){output=JSON.stringify({error:(e as Error).message})}
  if(run!==epoch.current||turn!==turnEpoch.current||channel.current?.readyState!=='open')return;
  channel.current.send(JSON.stringify({type:'conversation.item.create',item:{type:'function_call_output',call_id:callId,output}}));
 }
 async function finishResponse(response:Record<string,unknown>,run:number){
  const id=String(response.id||'');
  if(!id||completedResponses.current.has(id))return;
  completedResponses.current.add(id);
  const responseTurn=responseTurns.current.get(id);responseTurns.current.delete(id);
  if(responseTurn!==undefined&&responseTurn!==turnEpoch.current)return;
  responseActive.current=false;
  if(response.status!=='completed'){assistantText.current='';setState('listening');return}
  finishAssistant();
  const calls=(Array.isArray(response.output)?response.output:[]).filter((item:Record<string,unknown>)=>item.type==='function_call');
  if(!calls.length){continueResponse();setState(responseActive.current?'responding':'listening');track('answer_ready',{mode:'ai'});return}
  const turn=turnEpoch.current;setState('responding');
  await Promise.all(calls.map((call:Record<string,unknown>)=>runTool(String(call.name||''),String(call.call_id||''),String(call.arguments||'{}'),run,turn)));
  if(run!==epoch.current||turn!==turnEpoch.current)return;
  pendingContinuation.current=true;continueResponse();
 }
 function handleEvent(raw:string,run:number){
  if(run!==epoch.current)return;
  try{
   const event=JSON.parse(raw) as Record<string,unknown>,type=String(event.type||'');
   if(type==='input_audio_buffer.speech_started'){turnEpoch.current++;pendingContinuation.current=false;userSpeaking.current=true;assistantText.current='';setState('speaking');track('voice_started')}
   else if(type==='input_audio_buffer.speech_stopped'){userSpeaking.current=false;setState('responding')}
   else if(type==='response.created'){
    const response=event.response as Record<string,unknown>|undefined;
    if(response?.id)responseTurns.current.set(String(response.id),turnEpoch.current);
    responseActive.current=true;pendingContinuation.current=false;setState('responding');
   }
   else if(type==='conversation.item.input_audio_transcription.completed'){
    const id=String(event.item_id||'');if(id&&transcripts.current.has(id))return;if(id)transcripts.current.add(id);
    const transcript=String(event.transcript||'').trim();if(transcript){callback.current({role:'user',text:transcript});track('transcript_ready')}
   }else if(type==='response.output_audio_transcript.delta')assistantText.current+=String(event.delta||'');
   else if(type==='response.output_audio_transcript.done')finishAssistant(String(event.transcript||''));
   else if(type==='response.done')void finishResponse((event.response||{}) as Record<string,unknown>,run);
   else if(type==='error'){const detail=event.error as Record<string,unknown>|undefined;stop();setError(String(detail?.message||'실시간 음성 연결에 문제가 생겼습니다.'));setState('error')}
  }catch{/* Ignore unknown provider events; audio continues over WebRTC. */}
 }
 async function start(){
  if(starting.current||(state!=='idle'&&state!=='error'))return;
  stop();const run=epoch.current;setError('');

  if(!supported){setError('이 브라우저에서는 실시간 마이크를 사용할 수 없습니다. HTTPS 또는 localhost에서 열어 주세요.');setState('error');return}
  starting.current=true;controller.current=new AbortController();
  connectTimer.current=setTimeout(()=>{if(run===epoch.current){stop();setError('음성 연결 시간이 초과되었습니다. 마이크 권한과 네트워크를 확인한 뒤 다시 시작하세요.');setState('error')}},30000);
  setState('permission');
  try{
   const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
   if(run!==epoch.current){stream.getTracks().forEach(t=>t.stop());return}media.current=stream;
   const peer=new RTCPeerConnection();pc.current=peer;
   const player=document.createElement('audio');player.autoplay=true;player.setAttribute('playsinline','');audio.current=player;
   peer.ontrack=e=>{if(run!==epoch.current)return;player.srcObject=e.streams[0];void play()};
   peer.onconnectionstatechange=()=>{if(run!==epoch.current)return;if(['failed','disconnected'].includes(peer.connectionState)){stop();setError('실시간 음성 연결이 끊겼습니다. 다시 시작해 주세요.');setState('error')}else if(peer.connectionState==='connected'){starting.current=false;if(connectTimer.current)clearTimeout(connectTimer.current);connectTimer.current=null;setState('listening')}};
   stream.getTracks().forEach(t=>peer.addTrack(t,stream));
   const dc=peer.createDataChannel('oai-events');channel.current=dc;dc.onmessage=e=>handleEvent(String(e.data),run);dc.onopen=()=>{if(run===epoch.current)setState('listening')};
   setState('connecting');const offer=await peer.createOffer();if(run!==epoch.current)return;await peer.setLocalDescription(offer);if(run!==epoch.current)return;
   const params=new URLSearchParams();if(lot)params.set('quote_id',lot);
   const response=await fetch('/api/realtime/session'+(params.size?'?'+params:''),{method:'POST',headers:{'Content-Type':'application/sdp',Authorization:'Bearer '+token},body:offer.sdp,signal:controller.current?.signal});
   const answer=await response.text();if(!response.ok){let message='실시간 음성 세션을 시작하지 못했습니다.';try{message=JSON.parse(answer).detail||message}catch{}throw new Error(message)}
   if(run!==epoch.current)return;await peer.setRemoteDescription({type:'answer',sdp:answer});track('question_submitted',{source:'voice',mode:'ai'});
  }catch(e){if(run===epoch.current){const message=(e as Error).name==='NotAllowedError'?'마이크 권한을 허용해 주세요.':(e as Error).message;stop();setError(message);setState('error')}}
 }
 function toggleMute(){const next=!muted;media.current?.getAudioTracks().forEach(t=>{t.enabled=!next});setMuted(next)}
 return {state,error,muted,needsPlay,supported,start,stop,toggleMute,play,active:!['idle','error'].includes(state)};
}
