import {apiPath} from '../apiPath';
import {useCallback,useEffect,useRef,useState} from 'react';
const callsAgent = (text:string)=>!!text.trim();

export type RealtimeVoiceState='idle'|'permission'|'connecting'|'listening'|'speaking'|'responding'|'answering'|'error';
type Turn={role:'user'|'assistant';text:string};

export function useRealtimeVoice(token:string,lot:string,onTurn:(turn:Turn)=>void,onEvidence:(name:string,output:string)=>void){
 const [state,setState]=useState<RealtimeVoiceState>('idle'),[error,setError]=useState(''),[muted,setMuted]=useState(false),[needsPlay,setNeedsPlay]=useState(false);
 const pc=useRef<RTCPeerConnection|null>(null),channel=useRef<RTCDataChannel|null>(null),media=useRef<MediaStream|null>(null),audio=useRef<HTMLAudioElement|null>(null),epoch=useRef(0);
 const requests=useRef(new Set<AbortController>());
 const turnEpoch=useRef(0), requestedTurn=useRef(0);
 const responseTurns=useRef(new Map<string,number>());
 const voiceHistory=useRef<Turn[]>([]);
 const toolCalls=useRef(new Set<string>());
 const toolOutputs=useRef(new Map<string,{name:string;output:string}>());
 const toolsInResponse=useRef(0);
 const responseActive=useRef(false),queuedResponse=useRef(false);
 function requestResponse(){
  if(responseActive.current){queuedResponse.current=true;return}
  if(channel.current?.readyState==='open'){responseActive.current=true;requestedTurn.current=turnEpoch.current;queuedResponse.current=false;channel.current.send(JSON.stringify({type:'response.create'}))}
 }
 const assistantText=useRef(''),callback=useRef(onTurn);callback.current=onTurn;
 const evidenceCallback=useRef(onEvidence);evidenceCallback.current=onEvidence;
 const supported=window.isSecureContext&&!!navigator.mediaDevices?.getUserMedia&&typeof RTCPeerConnection!=='undefined';

 const stop=useCallback(()=>{
  voiceHistory.current=[];turnEpoch.current++;responseTurns.current.clear();epoch.current++;responseActive.current=false;queuedResponse.current=false;
  requests.current.forEach(request=>request.abort());requests.current.clear();
  channel.current?.close();channel.current=null;
  pc.current?.close();pc.current=null;
  media.current?.getTracks().forEach(t=>t.stop());media.current=null;
  if(audio.current){audio.current.pause();audio.current.srcObject=null;audio.current.remove()}audio.current=null;
  assistantText.current='';toolCalls.current.clear();toolOutputs.current.clear();toolsInResponse.current=0;setMuted(false);setNeedsPlay(false);setError('');setState('idle');
 },[]);
 useEffect(()=>()=>stop(),[stop]);
 useEffect(()=>{stop()},[token,lot,stop]);

 const play=useCallback(async()=>{if(!audio.current)return;try{await audio.current.play();setNeedsPlay(false)}catch{setNeedsPlay(true);setError('소리가 준비됐습니다. 재생을 눌러 주세요.')}},[]);
 function finishAssistant(text?:string){const final=(text||assistantText.current).trim();assistantText.current='';if(final){voiceHistory.current=[...voiceHistory.current,{role:'assistant' as const,text:final}].slice(-12);callback.current({role:'assistant',text:final})}}
 async function runTool(name:string,callId:string,argumentsText:string,run:number){
  if(run!==epoch.current||!callId||toolCalls.current.has(callId))return;toolCalls.current.add(callId);toolsInResponse.current++;
  const turn=turnEpoch.current;
  let args:Record<string,unknown>={};
  try{args=JSON.parse(argumentsText||'{}') as Record<string,unknown>}catch{args={}}
  let output:string;
  const request=new AbortController();requests.current.add(request);
  try{
   const response=await fetch(apiPath('/api/realtime/tool'),{signal:request.signal,method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({name,arguments:name === "analyze_manufacturing_question" ? {...args, quote_id:lot || null, history:voiceHistory.current} : args})});
   const payload=await response.json().catch(()=>({}));
   if(!response.ok)throw new Error(String(payload.detail||'제조 데이터 조회에 실패했습니다.'));
   output=String(payload.output||JSON.stringify({error:'빈 도구 응답'}));
  }catch(e){output=JSON.stringify({error:(e as Error).message})}finally{requests.current.delete(request)}
  if(run!==epoch.current||turn!==turnEpoch.current)return;
  toolOutputs.current.set(callId,{name,output});
 }
 async function finishResponse(run:number){
  const turn=turnEpoch.current;
  if(run!==epoch.current)return;
  finishAssistant();
  if(toolsInResponse.current){
   setState('responding');
   while(run===epoch.current&&turn===turnEpoch.current&&toolsInResponse.current){
    const pending=[...toolCalls.current].filter(id=>toolOutputs.current.has(id));
    if(!pending.length){await new Promise(resolve=>setTimeout(resolve,20));continue}
    const dc=channel.current;
    if(!dc||dc.readyState!=='open')return;
    for(const id of pending){
     const item=toolOutputs.current.get(id)!;toolOutputs.current.delete(id);toolCalls.current.delete(id);toolsInResponse.current--;
     evidenceCallback.current(item.name,item.output);
     dc.send(JSON.stringify({type:'conversation.item.create',item:{type:'function_call_output',call_id:id,output:item.output}}));
    }
   }
   if(run===epoch.current&&turn===turnEpoch.current)requestResponse();
   return;
  }
  if(queuedResponse.current){requestResponse();return}
  setState('listening');
 }
 function handleEvent(raw:string,run:number){
  if(run!==epoch.current)return;
  try{
   const event=JSON.parse(raw) as Record<string,unknown>,type=String(event.type||'');
   const responseId=String(event.response_id||'');
   if(responseId&&responseTurns.current.has(responseId)&&responseTurns.current.get(responseId)!==turnEpoch.current)return;
   if(type==='input_audio_buffer.speech_started'){
    turnEpoch.current++;queuedResponse.current=false;assistantText.current='';
    requests.current.forEach(request=>request.abort());requests.current.clear();
    const dc=channel.current;
    if(dc?.readyState==='open'){
     if(responseActive.current)dc.send(JSON.stringify({type:'response.cancel'}));
     dc.send(JSON.stringify({type:'output_audio_buffer.clear'}));
     for(const id of toolCalls.current)if(!toolOutputs.current.has(id))dc.send(JSON.stringify({type:'conversation.item.create',item:{type:'function_call_output',call_id:id,output:JSON.stringify({cancelled:true})}}));
    }
    toolCalls.current.clear();toolOutputs.current.clear();toolsInResponse.current=0;
    setState('speaking');
   }
   else if(type==='input_audio_buffer.speech_stopped')setState('responding');
   else if(type==='conversation.item.input_audio_transcription.completed'){
    const transcript=String(event.transcript||'').trim();
    if(transcript&&callsAgent(transcript)){
     voiceHistory.current=[...voiceHistory.current,{role:'user' as const,text:transcript}].slice(-12);
     callback.current({role:'user',text:transcript});
     requestResponse();
    }else{
     if(event.item_id&&channel.current?.readyState==='open')channel.current.send(JSON.stringify({type:'conversation.item.delete',item_id:event.item_id}));
     if(!responseActive.current)setState('listening');
    }
   }else if(type==='response.created'){
    const response=event.response as {id?:string}|undefined;
    if(response?.id)responseTurns.current.set(response.id,requestedTurn.current);
    responseActive.current=true;
    if(requestedTurn.current===turnEpoch.current)setState('responding');
   }
   else if(type==='response.output_audio.delta'){setState('answering')}
   else if(type==='response.output_audio_transcript.delta'){setState('answering');assistantText.current+=String(event.delta||'')}
   else if(type==='response.output_audio_transcript.done')finishAssistant(String(event.transcript||''));
   else if(type==='response.function_call_arguments.done')void runTool(String(event.name||''),String(event.call_id||''),String(event.arguments||'{}'),run);
   else if(type==='response.done'){
    responseActive.current=false;
    const response=event.response as {id?:string}|undefined;
    const old=response?.id ? responseTurns.current.get(response.id)!==turnEpoch.current : requestedTurn.current!==turnEpoch.current;
    if(old){if(queuedResponse.current)requestResponse();return}
    void finishResponse(run);
   }
   else if(type==='error'){const detail=event.error as Record<string,unknown>|undefined;if(detail?.code==='response_cancel_not_active')return;stop();setError(String(detail?.message||'실시간 음성 연결에 문제가 생겼습니다.'));setState('error')}
  }catch{/* Ignore unknown provider events; audio continues over WebRTC. */}
 }
 async function start(){
  if(state!=='idle'&&state!=='error')return;
  stop();const run=epoch.current;setError('');
  if(!supported){setError('이 브라우저에서는 실시간 마이크를 사용할 수 없습니다. HTTPS 또는 localhost에서 열어 주세요.');setState('error');return}
  setState('permission');
  try{
   const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
   if(run!==epoch.current){stream.getTracks().forEach(t=>t.stop());return}media.current=stream;
   const peer=new RTCPeerConnection();pc.current=peer;
   const player=document.createElement('audio');player.autoplay=true;player.setAttribute('playsinline','');audio.current=player;
   peer.ontrack=e=>{if(run!==epoch.current)return;player.srcObject=e.streams[0];void play()};
   peer.onconnectionstatechange=()=>{if(run!==epoch.current)return;if(['failed','disconnected'].includes(peer.connectionState)){stop();setError('실시간 음성 연결이 끊겼습니다. 다시 시작해 주세요.');setState('error')}else if(peer.connectionState==='connected')setState('listening')};
   stream.getTracks().forEach(t=>peer.addTrack(t,stream));
   const dc=peer.createDataChannel('oai-events');channel.current=dc;dc.onmessage=e=>handleEvent(String(e.data),run);dc.onopen=()=>{if(run===epoch.current)setState('listening')};
   setState('connecting');const offer=await peer.createOffer();if(run!==epoch.current)return;await peer.setLocalDescription(offer);if(run!==epoch.current)return;
   const params=new URLSearchParams();if(lot)params.set('quote_id',lot);
   const request=new AbortController();requests.current.add(request);
   const response=await fetch(apiPath('/api/realtime/session')+(params.size?'?'+params:''),{signal:request.signal,method:'POST',headers:{'Content-Type':'application/sdp',Authorization:'Bearer '+token},body:offer.sdp});
   const answer=await response.text();requests.current.delete(request);if(!response.ok){let message='실시간 음성 세션을 시작하지 못했습니다.';try{message=JSON.parse(answer).detail||message}catch{}throw new Error(message)}
   if(run!==epoch.current)return;await peer.setRemoteDescription({type:'answer',sdp:answer});
  }catch(e){if(run===epoch.current){const message=(e as Error).name==='NotAllowedError'?'마이크 권한을 허용해 주세요.':(e as Error).message;stop();setError(message);setState('error')}}
 }
 function toggleMute(){const next=!muted;media.current?.getAudioTracks().forEach(t=>{t.enabled=!next});setMuted(next)}
 return {state,error,muted,needsPlay,supported,start,stop,toggleMute,play,active:!['idle','error'].includes(state)};
}
