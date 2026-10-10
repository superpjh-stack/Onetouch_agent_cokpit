// No credentials are saved: provider/settings responses are mocked in the browser.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 const page=await context.newPage();
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let local=true,configured=false,fail=true,saves=0;
 await context.route('**/api/workspace',async route=>{
  const response=await route.fetch(),data=await response.json();
  data.meta.local_dev_ai=local;data.meta.ai_configured=configured;
  await route.fulfill({json:data});
 });
 await context.route('**/api/settings/openai',async route=>{
  saves++;
  if(fail)await route.fulfill({status:502,json:{detail:'모의 연결 실패'}});
  else {configured=true;await route.fulfill({json:{configured:true}});}
 });
 await page.goto('http://127.0.0.1:8517/?setup=openai');
 await page.getByLabel('OpenAI API 키',{exact:true}).fill('sk-browser-test-placeholder');
 await page.getByRole('button',{name:'API 키 저장',exact:true}).click();
 await page.getByText('모의 연결 실패',{exact:true}).waitFor();
 fail=false;
 await page.getByRole('button',{name:'API 키 저장',exact:true}).click();
 await page.getByText('서버에 API 키를 저장했습니다. AI 분석과 음성을 사용할 수 있습니다.',{exact:true}).waitFor();
 assert.equal(await page.getByLabel('OpenAI API 키',{exact:true}).inputValue(),'');
 assert.equal(await page.getByLabel('AI 접근 코드',{exact:true}).count(),0);
 assert(await page.evaluate(()=>!JSON.stringify({...localStorage,...sessionStorage}).includes('sk-browser')));
 await page.screenshot({path:'v2/verification/settings-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:'v2/verification/settings-mobile.png',fullPage:true});
 // Migration, restart, second tab, replacement and deletion on remote UI.
 local=false;
 await page.evaluate(()=>sessionStorage.setItem('onetouch_access_token','legacy-code'));
 await page.reload();
 assert.equal(await page.getByLabel('OpenAI API 키',{exact:true}).count(),0);
 assert.equal(await page.getByLabel('AI 접근 코드',{exact:true}).inputValue(),'legacy-code');
 assert.equal(await page.evaluate(()=>sessionStorage.getItem('onetouch_access_token')),null);
 await page.getByLabel('AI 접근 코드',{exact:true}).fill('new-code');
 await page.getByRole('button',{name:'연결 적용',exact:true}).click();
 await page.reload();
 assert.equal(await page.getByLabel('AI 접근 코드',{exact:true}).inputValue(),'new-code');
 const other=await context.newPage();await other.goto('http://127.0.0.1:8517/?setup=openai');
 assert.equal(await other.getByLabel('AI 접근 코드',{exact:true}).inputValue(),'new-code');
 await page.getByRole('button',{name:'접근 코드 삭제',exact:true}).click();
 await page.reload();
 assert.equal(await page.getByLabel('AI 접근 코드',{exact:true}).inputValue(),'');
 await other.reload();
 assert.equal(await other.getByLabel('AI 접근 코드',{exact:true}).inputValue(),'');
 assert.equal(saves,2);assert.deepEqual(errors,[]);
 await browser.close();console.log('Settings passed: local/remote UI, failed/successful save, key not retained, desktop/mobile, migration, reload, new tab, replace/delete.');
})().catch(e=>{console.error(e);process.exit(1)});
