import {useCallback,useEffect,useRef,useState} from 'react';
import {track} from '../types';
import type {WakePolicy} from '../wake';
import {RealtimeTurns} from './realtimeTurns';

export type RealtimeVoiceState='idle'|'permission'|'connecting'|'listening'|'speaking'|'responding'|'error';
type Turn={role:'user'|'assistant';text:string};

export function useRealtimeVoice(token:string,lot:string,onTurn:(turn:Turn)=>void,policy:WakePolicy){
 const [state,setState]=useState<RealtimeVoiceState>('idle'),[error,setError]=useState(''),[muted,setMuted]=useState(false),[needsPlay,setNeedsPlay]=useState(false);
 const pc=useRef<RTCPeerConnection|null>(null),channel=useRef<RTCDataChannel|null>(null),media=useRef<MediaStream|null>(null),audio=useRef<HTMLAudioElement|null>(null),epoch=useRef(0);
 const turns=useRef<RealtimeTurns|null>(null);
 const controller=useRef<AbortController|null>(null),connectTimer=useRef<ReturnType<typeof setTimeout>|null>(null),starting=useRef(false);
 const assistantText=useRef(''),callback=useRef(onTurn);callback.current=onTurn;
 const supported=window.isSecureContext&&!!navigator.mediaDevices?.getUserMedia&&typeof RTCPeerConnection!=='undefined';

 const stop=useCallback(()=>{
  epoch.current++;starting.current=false;
  turns.current?.dispose();turns.current=null;
  controller.current?.abort();controller.current=null;
  if(connectTimer.current)clearTimeout(connectTimer.current);connectTimer.current=null;
  channel.current?.close();channel.current=null;
  pc.current?.close();pc.current=null;
  media.current?.getTracks().forEach(t=>t.stop());media.current=null;
  if(audio.current){audio.current.pause();audio.current.srcObject=null;audio.current.remove()}audio.current=null;
  assistantText.current='';setMuted(false);setNeedsPlay(false);setError('');setState('idle');
 },[]);
 useEffect(()=>()=>stop(),[stop]);
 useEffect(()=>{stop()},[token,lot,policy,stop]);

 const play=useCallback(async()=>{const player=audio.current,run=epoch.current;if(!player)return;try{await player.play();if(run===epoch.current){setNeedsPlay(false);setError('')}}catch{if(run===epoch.current){setNeedsPlay(true);setError('소리가 준비됐습니다. 재생을 눌러 주세요.')}}},[]);
 function handleEvent(raw:string,run:number){
  if(run!==epoch.current)return;
  let event:Record<string,unknown>;try{event=JSON.parse(raw)}catch{return}
  if(event.type==='error'){const detail=event.error as Record<string,unknown>|undefined;stop();setError(String(detail?.message||'실시간 음성 연결에 문제가 생겼습니다.'));setState('error');return}
  turns.current?.handle(event);
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
   turns.current=new RealtimeTurns({policy,
    send:event=>{if(run===epoch.current&&channel.current?.readyState==='open')channel.current.send(JSON.stringify(event))},
    onTurn:turn=>{if(run===epoch.current)callback.current(turn)},
    onBusy:busy=>{if(run===epoch.current)setState(busy?'responding':'listening')},
    onError:message=>{if(run===epoch.current)setError(message)},
    tool:async call=>{
     if(run!==epoch.current)return JSON.stringify({error:'음성 세션이 종료되었습니다.'});
     const response=await fetch('/api/realtime/tool',{method:'POST',signal:controller.current?.signal,headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({name:call.name,arguments:JSON.parse(call.arguments)})});
     const payload=await response.json();return response.ok?String(payload.output):JSON.stringify({error:payload.detail||'도구 조회 실패'});
    },
   });
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
