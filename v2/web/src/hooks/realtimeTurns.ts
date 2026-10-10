import {callsAgent,type WakePolicy} from '../wake';
type Event=Record<string,unknown>;
type Turn={role:'user'|'assistant';text:string};
type Call={type:'function_call';name:string;call_id:string;arguments:string};
type Options={policy:WakePolicy;send:(event:Event)=>void;onTurn:(turn:Turn)=>void;onBusy:(busy:boolean)=>void;tool:(call:Call)=>Promise<string>;onError:(message:string)=>void};

/** Explicit inputs isolate responses from unaddressed audio still being transcribed. */
export class RealtimeTurns {
 private heard=new Set<string>();
 private finished=new Set<string>();
 private queue:string[]=[];
 private input:Event[]=[];
 private history:Event[]=[];
 private question='';
 private answer='';
 private pending=false;
 private playing=false;
 private disposed=false;
 private active=false;
 private responseId='';
 private transcript='';
 constructor(private options:Options){}
 dispose(){this.disposed=true;this.queue=[];this.input=[];this.history=[];this.heard.clear();this.finished.clear();}
 private respond(){
  if(this.disposed||this.pending||this.playing)return;
  if(!this.active){
   const question=this.queue.shift();
   if(!question){this.options.onBusy(false);return;}
   this.active=true;this.question=question;this.answer='';
   this.input=[...this.history,{type:'message',role:'user',content:[{type:'input_text',text:question}]}];
  }
  this.pending=true;this.responseId='';this.transcript='';this.options.onBusy(true);
  this.options.send({type:'response.create',response:{conversation:'none',input:this.input}});
 }
 handle(event:Event){
  if(this.disposed)return;
  const type=String(event.type||'');
  if(type==='conversation.item.input_audio_transcription.completed'||type==='conversation.item.input_audio_transcription.failed'){
   const id=String(event.item_id||'');
   if(!id||this.heard.has(id))return;
   this.heard.add(id);this.options.send({type:'conversation.item.delete',item_id:id});
   const text=String(event.transcript||'').trim();
   if(type.endsWith('.failed')||!text||!callsAgent(text,this.options.policy))return;
   this.options.onTurn({role:'user',text});this.queue.push(text);this.respond();
  }else if(type==='response.created'){
   const response=event.response as Event|undefined;
   if(!this.active||!this.pending){this.options.send({type:'response.cancel',response_id:response?.id});return;}
   this.responseId=String(response?.id||'');
  }else if(type==='output_audio_buffer.started')this.playing=true;
  else if(type==='output_audio_buffer.stopped'||type==='output_audio_buffer.cleared'){this.playing=false;this.respond();}
  else if(type==='response.output_audio_transcript.delta'&&this.active&&this.pending&&event.response_id===this.responseId)this.transcript+=String(event.delta||'');
  else if(type==='response.output_audio_transcript.done'&&this.active&&this.pending&&event.response_id===this.responseId)this.transcript=String(event.transcript||this.transcript);
  else if(type==='response.done')void this.complete(event);
 }
 private async complete(event:Event){
  const response=event.response as Event|undefined,id=String(response?.id||'');
  if(!id||!this.active||!this.pending||id!==this.responseId||this.finished.has(id))return;
  this.finished.add(id);
  const output=Array.isArray(response?.output)?response.output as Event[]:[];
  if(response?.status!=='completed'){
   this.options.onError('음성 응답을 완료하지 못했습니다. 호출명과 함께 다시 질문해 주세요.');
   this.active=false;this.pending=false;this.respond();return;
  }
  if(this.transcript.trim()){this.answer+=this.transcript.trim()+'\n';this.options.onTurn({role:'assistant',text:this.transcript.trim()});}
  this.transcript='';
  const calls=output.filter(item=>item.type==='function_call').map(item=>({type:'function_call' as const,name:String(item.name||''),call_id:String(item.call_id||''),arguments:String(item.arguments||'{}')}));
  if(calls.length){
   // Keep the response locked until ALL tools finish; one continuation per batch.
   const results=await Promise.all(calls.map(async call=>{
    try{return await this.options.tool(call);}catch{return JSON.stringify({error:'도구 조회에 실패했습니다.'});}
   }));
   if(this.disposed)return;
   this.input.push(...calls,...calls.map((call,i)=>({type:'function_call_output',call_id:call.call_id,output:results[i]})));
  }else {
   this.history.push({type:'message',role:'user',content:[{type:'input_text',text:this.question}]});
   if(this.answer.trim())this.history.push({type:'message',role:'assistant',content:[{type:'output_text',text:this.answer.trim()}]});
   this.history=this.history.slice(-20);this.active=false;
  }
  this.pending=false;this.respond();
 }
}
