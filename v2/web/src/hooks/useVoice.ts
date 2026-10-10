import {useCallback, useEffect, useRef, useState} from 'react';
import {track} from '../types';

export type VoiceState = 'idle'|'permission'|'recording'|'stopping'|'review'|'transcribing'|'generating'|'ready'|'playing';
const MAX_BYTES = 20 * 1024 * 1024;
const formats: Record<string,string> = {'audio/webm':'webm','video/webm':'webm','audio/mp4':'m4a','video/mp4':'mp4','audio/mpeg':'mp3','audio/mp3':'mp3','audio/wav':'wav','audio/x-wav':'wav','audio/ogg':'ogg','audio/flac':'flac','audio/x-m4a':'m4a'};

export function useVoice(token:string, onTranscript:(text:string)=>void) {
  const [state,setState]=useState<VoiceState>('idle'), [error,setError]=useState(''), [seconds,setSeconds]=useState(0);
  const stateRef=useRef<VoiceState>('idle'), epoch=useRef(0), stream=useRef<MediaStream|null>(null), recorder=useRef<MediaRecorder|null>(null);
  const pending=useRef<Blob|null>(null), timer=useRef<ReturnType<typeof setInterval>|null>(null), controller=useRef<AbortController|null>(null);
  const player=useRef<HTMLAudioElement|null>(null), url=useRef(''), playbackBusy=useRef(false), callback=useRef(onTranscript);
  callback.current=onTranscript;
  const canRecord=window.isSecureContext&&!!navigator.mediaDevices?.getUserMedia&&typeof MediaRecorder!=='undefined';
  const transition=useCallback((next:VoiceState)=>{stateRef.current=next;setState(next)},[]);
  const release=useCallback(()=>{stream.current?.getTracks().forEach(track=>track.stop());stream.current=null;if(timer.current)clearInterval(timer.current);timer.current=null},[]);
  const cancel=useCallback(()=>{
    epoch.current++;controller.current?.abort();controller.current=null;
    const rec=recorder.current;recorder.current=null;
    if(rec){rec.onstop=null;rec.ondataavailable=null;rec.onerror=null;if(rec.state!=='inactive')rec.stop()}
    release();pending.current=null;
    const audio=player.current;player.current=null;playbackBusy.current=false;
    if(audio){audio.onended=null;audio.onerror=null;audio.pause();audio.removeAttribute('src');audio.load()}
    if(url.current)URL.revokeObjectURL(url.current);url.current='';setError('');transition('idle');
  },[release,transition]);
  useEffect(()=>()=>cancel(),[cancel]);
  useEffect(()=>{cancel()},[token,cancel]);

  async function transcribe(file:Blob) {
    if(!['idle','review'].includes(stateRef.current))return;
    const retry=stateRef.current==='review';
    cancel();const run=epoch.current;
    if(!file.size||file.size>MAX_BYTES){setError('비어 있지 않은 20MB 이하의 음성 파일을 선택하세요.');return}
    const mime=file.type.split(';')[0].toLowerCase(), ext=formats[mime];
    if(!ext&&!(file instanceof File&&!mime)){setError('지원되는 음성 파일을 선택하세요.');return}
    pending.current=file;
    if(!retry)track('voice_started');
    transition('transcribing');controller.current=new AbortController();const began=performance.now();
    const form=new FormData();form.append('file',file,file instanceof File?file.name:`recording.${ext}`);
    try {
      const response=await fetch('/api/voice/transcribe',{method:'POST',headers:{Authorization:'Bearer '+token},body:form,signal:controller.current.signal});
      const result=await response.json();if(!response.ok)throw new Error(result.detail||'음성 변환에 실패했습니다.');
      if(run!==epoch.current)return;
      if(!result.text?.trim())throw new Error('문장을 확인하지 못했어요. 다시 녹음하거나 직접 입력하세요.');
      pending.current=null;controller.current=null;track('transcript_ready',{duration_ms:performance.now()-began});callback.current(result.text);transition('idle');
    } catch(e){if(run===epoch.current){controller.current=null;setError((e as Error).message);transition('review')}}
  }

  function stop(){
    if(stateRef.current!=='recording')return;
    transition('stopping');
    if(recorder.current?.state==='recording')recorder.current.stop();
    release();
  }
  async function start() {
    if(!['idle','playing','ready','generating'].includes(stateRef.current))return;
    cancel();setSeconds(0);const run=epoch.current;
    if(!canRecord){setError('이 환경에서는 마이크를 사용할 수 없습니다. HTTPS에서 열거나 음성 파일·문자 입력을 이용하세요.');return}
    transition('permission');track('voice_started');
    try {
      const media=await navigator.mediaDevices.getUserMedia({audio:true});
      if(run!==epoch.current){media.getTracks().forEach(track=>track.stop());return}
      stream.current=media;
      const mime=['audio/webm;codecs=opus','audio/mp4','audio/webm','audio/ogg;codecs=opus'].find(type=>MediaRecorder.isTypeSupported(type));
      const rec=new MediaRecorder(media,mime?{mimeType:mime}:undefined);recorder.current=rec;
      const chunks:Blob[]=[];let bytes=0;
      rec.ondataavailable=e=>{if(run===epoch.current&&e.data.size){chunks.push(e.data);bytes+=e.data.size;if(bytes>MAX_BYTES){cancel();setError('녹음 용량이 너무 큽니다. 짧게 다시 녹음하세요.')}}};
      rec.onerror=()=>{if(run===epoch.current){cancel();setError('녹음이 중단됐습니다. 다시 시도하거나 문자로 입력하세요.')}};
      rec.onstop=()=>{
        if(run!==epoch.current)return;
        release();recorder.current=null;
        const blob=new Blob(chunks,{type:rec.mimeType||chunks[0]?.type||''});
        if(!blob.size){cancel();setError('녹음된 소리가 없습니다. 다시 녹음하거나 문자로 입력하세요.');return}
        if(!formats[blob.type.split(';')[0]]){cancel();setError('이 브라우저의 녹음 형식을 지원하지 않습니다. 음성 파일·문자 입력을 이용하세요.');return}
        pending.current=blob;transition('review');
      };
      rec.start(500);transition('recording');const began=Date.now();
      timer.current=setInterval(()=>{const elapsed=Math.min(60,Math.floor((Date.now()-began)/1000));setSeconds(elapsed);if(elapsed>=60)stop()},250);
    }catch(e){if(run===epoch.current){cancel();setError((e as Error).name==='NotAllowedError'?'마이크 권한을 허용하거나 문자로 입력하세요.':'마이크를 연결하지 못했습니다. 문자 입력을 이용하세요.')}}
  }
  useEffect(()=>{
    const hidden=()=>{if(document.hidden){if(stateRef.current==='recording'){stop();setError('화면 전환으로 녹음을 중단했습니다. 내용을 변환하거나 취소하세요.')}else if(['permission','playing','ready','generating'].includes(stateRef.current))cancel()}};
    document.addEventListener('visibilitychange',hidden);return()=>document.removeEventListener('visibilitychange',hidden);
  },[cancel,release,transition]);
  async function play(){
    const audio=player.current,run=epoch.current;if(!audio||playbackBusy.current)return;
    playbackBusy.current=true;setError('');
    try{await audio.play();if(run===epoch.current)transition('playing')}
    catch(e){if(run===epoch.current){if((e as Error).name==='NotAllowedError'){transition('ready');setError('음성이 준비됐습니다. 재생 버튼을 눌러 들어보세요.')}else{cancel();setError('음성을 재생하지 못했습니다. 텍스트 답변을 확인하세요.')}}}
    finally{if(run===epoch.current)playbackBusy.current=false}
  }
  async function speak(text:string){
    if(!['idle','ready','playing'].includes(stateRef.current))return;
    cancel();const run=epoch.current;transition('generating');controller.current=new AbortController();
    try{
      const response=await fetch('/api/voice/speak',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({text:text.slice(0,4000)}),signal:controller.current.signal});
      if(!response.ok){const result=await response.json();throw new Error(result.detail||'음성을 만들지 못했습니다.')}
      const blob=await response.blob();if(run!==epoch.current)return;
      controller.current=null;url.current=URL.createObjectURL(blob);const audio=new Audio(url.current);player.current=audio;
      audio.onended=()=>{if(run===epoch.current)cancel()};audio.onerror=()=>{if(run===epoch.current){cancel();setError('음성을 재생하지 못했습니다. 텍스트 답변을 확인하세요.')}};
      await play();
    }catch(e){if(run===epoch.current){cancel();setError((e as Error).message)}}
  }
  return {state,error,seconds,canRecord,start,stop,cancel,transcribe,speak,play,convert:()=>pending.current&&transcribe(pending.current)};
}
