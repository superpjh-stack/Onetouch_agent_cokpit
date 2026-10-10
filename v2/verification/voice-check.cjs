// Browser lifecycle verification only: no microphone, provider call, or API key is used.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1280,height:900}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{
  window.voiceTest={deny:false,tracks:[],peers:[],fastTimeout:false};
  const originalTimeout=window.setTimeout;
  window.setTimeout=(fn,ms,...args)=>originalTimeout(fn,window.voiceTest.fastTimeout&&ms===30000?100:ms,...args);
  Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async()=>{
   if(window.voiceTest.deny)throw new DOMException('Denied','NotAllowedError');
   const track={enabled:true,stopped:false,stop(){this.stopped=true}};
   window.voiceTest.tracks.push(track);
   return {getTracks:()=>[track],getAudioTracks:()=>[track]};
  }});
  window.RTCPeerConnection=class {
   constructor(){this.connectionState='new';window.voiceTest.peers.push(this)}
   addTrack(){}
   createDataChannel(){return this.channel={readyState:'open',close(){this.readyState='closed'},sent:[],send(raw){this.sent.push(JSON.parse(raw))}}}
   async createOffer(){return {type:'offer',sdp:'v=0 mock-offer'}}
   async setLocalDescription(){}
   async setRemoteDescription(){this.connectionState='connected';this.onconnectionstatechange?.();this.channel.onopen?.()}
   close(){this.connectionState='closed'}
  };
 });
 await page.route('**/api/workspace',async route=>{
  const response=await route.fetch();const data=await response.json();
  data.meta.ai_configured=true;data.meta.local_dev_ai=true;
  await route.fulfill({json:data});
 });
 let failure=false,delay=false;
 await page.route('**/api/realtime/session*',async route=>{
  if(delay)await new Promise(r=>setTimeout(r,700));
  await route.fulfill(failure?{status:502,json:{detail:'모의 음성 연결 실패'}}:{status:200,contentType:'application/sdp',body:'v=0 mock-answer'}).catch(()=>{});
 });
 await page.goto('http://127.0.0.1:8517');
 const start=page.getByRole('button',{name:'음성 질문 시작',exact:true});
 await page.evaluate(()=>{window.voiceTest.deny=true});
 await start.click();
 await page.getByText('마이크 권한을 허용해 주세요.',{exact:true}).waitFor();
 await page.evaluate(()=>{window.voiceTest.deny=false});
 await start.click();
 await page.getByText('원터치 호출 대기 중',{exact:true}).waitFor();
 // Wake checks are exercised through the actual browser event handler.
 await page.evaluate(()=>{
  const dc=window.voiceTest.peers.at(-1).channel;
  const emit=e=>dc.onmessage({data:JSON.stringify(e)});
  emit({type:'conversation.item.input_audio_transcription.completed',item_id:'ambient',transcript:'주변 대화'});
  emit({type:'conversation.item.input_audio_transcription.completed',item_id:'wrong',transcript:'니즈, 재고'});
 });
 assert.equal(await page.evaluate(()=>window.voiceTest.peers.at(-1).channel.sent.filter(e=>e.type==='response.create').length),0);
 await page.evaluate(()=>{
  const dc=window.voiceTest.peers.at(-1).channel;
  const event={type:'conversation.item.input_audio_transcription.completed',item_id:'called',transcript:'원터치, 원가'};
  dc.onmessage({data:JSON.stringify(event)});dc.onmessage({data:JSON.stringify(event)});
 });
 assert.equal(await page.evaluate(()=>window.voiceTest.peers.at(-1).channel.sent.filter(e=>e.type==='response.create').length),1);
 assert.equal(await page.getByText('원터치, 원가',{exact:true}).count(),1);
 await page.getByRole('button',{name:'마이크 끄기',exact:true}).click();
 assert.equal(await page.evaluate(()=>window.voiceTest.tracks.at(-1).enabled),false);
 await page.getByRole('button',{name:'마이크 켜기',exact:true}).click();
 assert.equal(await page.evaluate(()=>window.voiceTest.tracks.at(-1).enabled),true);
 await page.getByRole('button',{name:'종료',exact:true}).click();
 assert(await page.evaluate(()=>window.voiceTest.tracks.every(t=>t.stopped)));
 assert(await page.evaluate(()=>window.voiceTest.peers.every(p=>p.connectionState==='closed'&&p.channel.readyState==='closed')));
 // Peer disconnect must release the microphone and allow retry.
 await start.click();await page.getByText('원터치 호출 대기 중',{exact:true}).waitFor();
 await page.evaluate(()=>{const peer=window.voiceTest.peers.at(-1);peer.connectionState='disconnected';peer.onconnectionstatechange()});
 await page.getByText('실시간 음성 연결이 끊겼습니다. 다시 시작해 주세요.',{exact:true}).waitFor();
 assert(await page.evaluate(()=>window.voiceTest.tracks.every(t=>t.stopped)));
 // Provider errors also release all resources.
 await start.click();await page.getByText('원터치 호출 대기 중',{exact:true}).waitFor();
 await page.evaluate(()=>window.voiceTest.peers.at(-1).channel.onmessage({data:JSON.stringify({type:'error',error:{message:'모의 제공자 오류'}})}));
 await page.getByText('모의 제공자 오류',{exact:true}).waitFor();
 assert(await page.evaluate(()=>window.voiceTest.tracks.every(t=>t.stopped)));
 failure=true;await start.click();await page.getByText('모의 음성 연결 실패',{exact:true}).waitFor();
 assert(await page.evaluate(()=>window.voiceTest.tracks.every(t=>t.stopped)));
 // Late session response after quotation switch must not reconnect.
 failure=false;delay=true;
 await start.click();await page.getByText('연결 중',{exact:true}).waitFor();
 await page.getByLabel('질문 대상 견적').selectOption('QT-260904-002');
 await page.waitForTimeout(900);
 assert(await start.isVisible());
 assert(await page.evaluate(()=>window.voiceTest.tracks.every(t=>t.stopped)));
 assert(await page.evaluate(()=>window.voiceTest.peers.every(p=>p.connectionState==='closed')));
 // Accelerated connection deadline: verify timeout releases acquired microphone.
 await page.evaluate(()=>{window.voiceTest.fastTimeout=true});
 await start.click();
 await page.getByText('음성 연결 시간이 초과되었습니다. 마이크 권한과 네트워크를 확인한 뒤 다시 시작하세요.',{exact:true}).waitFor();
 assert(await page.evaluate(()=>window.voiceTest.tracks.every(t=>t.stopped)));
 await page.waitForTimeout(800);
 assert(await start.isVisible());
 assert.deepEqual(errors,[]);
 await browser.close();
 console.log('Mock voice lifecycle passed: wake filtering and duplicate transcript, denied permission, connect, mute/unmute, stop, disconnect, provider/API error, late response after quote switch, connection timeout.');
})().catch(e=>{console.error(e);process.exit(1)});
