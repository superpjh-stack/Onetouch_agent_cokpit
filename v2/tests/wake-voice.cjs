const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {execFileSync}=require('node:child_process');
const web=path.resolve(__dirname,'../web');
const build=fs.mkdtempSync(path.join(os.tmpdir(),'onetouch-wake-'));
execFileSync(process.execPath,[path.join(web,'node_modules/typescript/bin/tsc'),'--module','commonjs','--target','es2022','--skipLibCheck','--outDir',build,path.join(web,'src/wake.ts'),path.join(web,'src/hooks/realtimeTurns.ts')]);
process.on('exit',()=>fs.rmSync(build,{recursive:true,force:true}));
const {callsAgent}=require(path.join(build,'wake.js'));
const {RealtimeTurns}=require(path.join(build,'hooks/realtimeTurns.js'));
const policy={agent_name:'원터치',wake_aliases:['원터치','원터치야','원터치님'],require_wake_name:true};
function harness(tool=async()=>'{"ok":true}'){
 const sent=[],turns=[],errors=[];
 const controller=new RealtimeTurns({policy,send:x=>sent.push(structuredClone(x)),onTurn:x=>turns.push(x),onBusy:()=>{},onError:x=>errors.push(x),tool});
 return {controller,sent,turns,errors,transcribe:(id,text)=>controller.handle({type:'conversation.item.input_audio_transcription.completed',item_id:id,transcript:text}),responses:()=>sent.filter(x=>x.type==='response.create')};
}
function created(h,id){h.controller.handle({type:'response.created',response:{id}})}
function done(h,id,output=[]){h.controller.handle({type:'response.done',response:{id,status:'completed',output}})}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('Python and browser use the same wake grammar',()=>{
 for(const [text,expected] of require('./wake_cases.json'))assert.equal(callsAgent(text,policy),expected,text);
 assert.equal(callsAgent('송월님, 재고',{...policy,agent_name:'송월',wake_aliases:['송월님']}),true);
 assert.equal(callsAgent('원터치, 재고',{...policy,agent_name:'송월',wake_aliases:['송월님']}),false);
 assert.equal(callsAgent('A+B, 재고',{...policy,agent_name:'A+B',wake_aliases:[]}),true);
 assert.equal(callsAgent('AAAB, 재고',{...policy,agent_name:'A+B',wake_aliases:[]}),false);
});
test('ambient speech deleted and duplicate transcripts ignored',()=>{
 const h=harness();h.transcribe('a','오늘 재고');h.transcribe('b','원터치플랫폼');
 assert.equal(h.responses().length,0);assert.equal(h.turns.length,0);
 h.transcribe('c','원터치, 재고');h.transcribe('c','원터치, 재고');
 assert.equal(h.responses().length,1);assert.equal(h.turns.length,1);
 assert.equal(h.sent.filter(x=>x.type==='conversation.item.delete').length,3);
 assert.equal(h.responses()[0].response.conversation,'none');
 assert.equal(JSON.stringify(h.responses()).includes('오늘 재고'),false);
});
test('each next question requires address and waits for playback',()=>{
 const h=harness();h.transcribe('a','원터치, 재고');created(h,'r1');
 h.controller.handle({type:'output_audio_buffer.started'});
 h.transcribe('b','그럼 생산은?');h.transcribe('c','원터치님, 생산은?');
 h.controller.handle({type:'response.output_audio_transcript.done',response_id:'r1',transcript:'샘플 재고입니다.'});done(h,'r1');
 assert.equal(h.responses().length,1);
 h.controller.handle({type:'output_audio_buffer.stopped'});
 assert.equal(h.responses().length,2);
 assert.equal(JSON.stringify(h.responses()[1]).includes('그럼 생산은'),false);
 assert.equal(JSON.stringify(h.responses()[1]).includes('샘플 재고입니다.'),true);
 done(h,'r1');assert.equal(h.responses().length,2);
});
test('all asynchronous tools finish before one continuation',async()=>{
 const resolvers=[];const h=harness(()=>new Promise(resolve=>resolvers.push(resolve)));
 h.transcribe('a','원터치, 조회');created(h,'r1');
 done(h,'r1',[{type:'function_call',name:'one',call_id:'c1',arguments:'{}'},{type:'function_call',name:'two',call_id:'c2',arguments:'{}'}]);
 h.transcribe('b','주변 대화');h.transcribe('c','원터치, 다음 질문');
 resolvers[0]('{}');await tick();assert.equal(h.responses().length,1);
 resolvers[1]('{}');await tick();assert.equal(h.responses().length,2);
 assert.equal(h.responses()[1].response.input.filter(x=>x.type==='function_call_output').length,2);
 created(h,'r2');done(h,'r2');assert.equal(h.responses().length,3);
});
test('ending session drops queued questions and late tool results',async()=>{
 let resolve;const h=harness(()=>new Promise(r=>resolve=r));
 h.transcribe('a','원터치, 조회');created(h,'r1');done(h,'r1',[{type:'function_call',name:'one',call_id:'c1',arguments:'{}'}]);
 h.transcribe('b','원터치, 다음');h.controller.dispose();resolve('{}');await tick();
 h.transcribe('c','원터치, 늦은 발화');assert.equal(h.responses().length,1);
});
test('failed transcription removed without response; unsolicited response cancelled',()=>{
 const h=harness();h.controller.handle({type:'conversation.item.input_audio_transcription.failed',item_id:'failed'});
 created(h,'unsolicited');assert.equal(h.responses().length,0);
 assert.equal(h.sent[0].type,'conversation.item.delete');assert.equal(h.sent[1].type,'response.cancel');
});
