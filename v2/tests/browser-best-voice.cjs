const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL || undefined});const page=await browser.newPage();
 await page.addInitScript(()=>{
  window.mockState={stopped:0,closed:0,track:null,dc:null,sent:[]};
  Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async()=>{
   const track={enabled:true,stop(){window.mockState.stopped++}};window.mockState.track=track;
   return {getTracks:()=>[track],getAudioTracks:()=>[track]};
  }});
  window.RTCPeerConnection=class{
   addTrack(){}createDataChannel(){const dc={readyState:'open',send(message){window.mockState.sent.push(JSON.parse(message))},close(){}};window.mockState.dc=dc;return dc}
   async createOffer(){return {type:'offer',sdp:'v=0'}}async setLocalDescription(){}async setRemoteDescription(){window.mockState.dc.onopen()}
   close(){window.mockState.closed++}
  };
 });
 await page.route('**/api/workspace',async route=>{const response=await route.fetch();const data=await response.json();data.meta.ai_configured=true;data.meta.local_dev_ai=true;await route.fulfill({json:data})});
 await page.route('**/api/realtime/session*',route=>route.fulfill({status:502,json:{detail:'테스트 연결 실패'}}));
 await page.goto(process.env.ONETOUCH_URL || 'http://127.0.0.1:8522');
 await page.getByRole('button',{name:'음성 질문 시작',exact:true}).click();
 await page.getByRole('alert').filter({hasText:'테스트 연결 실패'}).waitFor();
 if(await page.evaluate(()=>window.mockState.stopped)!==1)throw Error('Failure did not release microphone');
 await page.unroute('**/api/realtime/session*');
 await page.route('**/api/realtime/session*',route=>route.fulfill({body:'v=0',contentType:'application/sdp'}));
 await page.getByRole('button',{name:'음성 질문 시작',exact:true}).click();
 await page.getByText('편하게 말씀하세요',{exact:true}).waitFor();
 await page.evaluate(()=>window.mockState.dc.onmessage({data:JSON.stringify({type:'conversation.item.input_audio_transcription.completed',transcript:'자재 현황을 알려줘',item_id:'ignored-test'})}));
 if(!await page.evaluate(()=>window.mockState.sent.some(e=>e.type==='response.create')))throw Error('Unaddressed voice did not trigger response');
 await page.evaluate(()=>window.mockState.dc.onmessage({data:JSON.stringify({type:'conversation.item.input_audio_transcription.completed',transcript:'임진강, 자재 현황을 알려줘'})}));
 if(!await page.evaluate(()=>window.mockState.sent.some(e=>e.type==='response.create')))throw Error('Addressed voice did not trigger response');
 // Interrupt a slow tool call and reject its late transcript and evidence.
 let releaseTool; const toolGate=new Promise(resolve=>releaseTool=resolve);
 let toolStarted; const started=new Promise(resolve=>toolStarted=resolve);
 await page.route('**/api/realtime/tool',async route=>{toolStarted();await toolGate;await route.fulfill({json:{output:JSON.stringify({text:'STALE_TOOL_ANSWER'})}}).catch(()=>{})});
 await page.evaluate(()=>{const emit=e=>window.mockState.dc.onmessage({data:JSON.stringify(e)});emit({type:'response.created',response:{id:'old-response'}});emit({type:'response.function_call_arguments.done',response_id:'old-response',name:'analyze_manufacturing_question',call_id:'slow-call',arguments:'{"question":"자재 상태"}'});emit({type:'response.done',response:{id:'old-response'}})});
 await Promise.race([started,new Promise((_,reject)=>setTimeout(()=>reject(Error("Tool request did not start")),5000))]);
 await page.evaluate(()=>{const emit=e=>window.mockState.dc.onmessage({data:JSON.stringify(e)});emit({type:'input_audio_buffer.speech_started'});emit({type:'conversation.item.input_audio_transcription.completed',transcript:'납기부터 알려줘'});emit({type:'response.output_audio_transcript.done',response_id:'old-response',transcript:'STALE_SPOKEN_ANSWER'});emit({type:'response.created',response:{id:'new-response'}});emit({type:'response.output_audio_transcript.done',response_id:'new-response',transcript:'새 질문의 답변입니다.'});emit({type:'response.done',response:{id:'new-response'}})});
 releaseTool();await page.waitForTimeout(150);
 if(await page.getByText(/STALE_TOOL_ANSWER|STALE_SPOKEN_ANSWER/).count())throw Error('Interrupted answer leaked');
 await page.getByText('새 질문의 답변입니다.',{exact:true}).waitFor();
 if(!await page.evaluate(()=>window.mockState.sent.some(e=>e.type==='output_audio_buffer.clear')))throw Error('Audio not cleared');
 await page.getByRole('button',{name:'마이크 끄기',exact:true}).click();
 if(await page.evaluate(()=>window.mockState.track.enabled)!==false)throw Error('Mute failed');
 await page.getByRole('button',{name:'마이크 켜기',exact:true}).click();
 await page.getByRole('button',{name:'종료',exact:true}).click();
 if(await page.evaluate(()=>window.mockState.stopped)!==2)throw Error('Stop did not release microphone');
 console.log('Voice lifecycle: PASS');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
