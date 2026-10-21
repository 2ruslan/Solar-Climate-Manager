// Standalone browser checks; no Home Assistant commands or external services.
const {test, expect} = require('playwright/test');
const fs = require('node:fs');
const path = require('node:path');
test.use({launchOptions:process.env.SCM_TEST_CHANNEL?{channel:process.env.SCM_TEST_CHANNEL}:{}});

test('inline trends on desktop and mobile, ranges, gaps, cache and errors', async ({page}) => {
  const errors=[];
  page.on('pageerror',error=>errors.push(String(error)));
  const script=fs.readFileSync(path.join(__dirname,'../../custom_components/solar_climate_manager/frontend/panel.js'),'utf8');
  await page.route('http://scm.test/**',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body style="margin:0"></body></html>'}));
  await page.goto('http://scm.test/');
  await page.addScriptTag({type:'module',content:script});
  await page.evaluate(async()=>{
    await customElements.whenDefined('solar-climate-panel');
    window.historyCalls=0;
    window.failHistory=false;
    const now=Date.now()/1000;
    window.rows=[7200,7140,3600,3540,120,60,0].map((age,i)=>({timestamp:now-age,state:{temperature:21+i/10,target_temperature:23,ac_power:600+i*80,power_accounting:'measured'}}));
    window.device={device_id:'one',entry_id:'one',name:'Вітальня',climate_entity:'climate.room',loaded:true,group_id:null,running:true,temperature:21.6,target:23,mode:'observation',power_accounting:'measured',measured_power:1080,planned_power:1200};
    window.panel=document.createElement('solar-climate-panel');
    panel.hass={language:'uk',user:{is_admin:true},connection:{},callWS:async msg=>{
      if(msg.type.endsWith('/history')) {historyCalls++;if(failHistory)throw Error('offline');return {generated_at:now,rows};}
      return {devices:[device],groups:[],version:'test',translations:{options:{step:{init:{sections:{}}}}}};
    }};
    document.body.append(panel);
  });
  await page.setViewportSize({width:1280,height:1080});
  await expect(page.locator('.chart svg')).toHaveCount(2);
  await expect(page.getByText('Працюють зараз',{exact:true})).toBeVisible();
  await expect(page.locator('dialog')).not.toBeVisible();
  const range=page.locator('.trends select');
  await expect(range).toHaveValue('6');
  const full=await page.locator('.chart path').first().getAttribute('d');
  expect((full.match(/M/g)||[]).length).toBe(3); // Gaps are not connected.
  await range.selectOption('1');
  await expect(page.locator('.chart path').first()).not.toHaveAttribute('d',full);
  expect(await page.evaluate(()=>historyCalls)).toBe(1);
  await page.evaluate(()=>{panel._chartCache.get('one').at=0;return panel.refresh();});
  await expect.poll(()=>page.evaluate(()=>historyCalls)).toBe(2);
  await page.screenshot({path:'test-results/trends-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect(page.locator('.chart svg')).toHaveCount(2);
  expect(await page.evaluate(()=>panel.shadowRoot.querySelector('.page').scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({path:'test-results/trends-mobile.png',fullPage:true});
  await page.evaluate(()=>{rows=[];panel._chartCache.clear();panel._signature=null;return panel.refresh();});
  await expect(page.getByText('За цей період немає вимірювань.',{exact:true})).toHaveCount(2);
  await page.evaluate(()=>{failHistory=true;panel._chartCache.clear();panel._signature=null;return panel.refresh();});
  await expect(page.getByRole('button',{name:'Спробувати ще раз'})).toBeVisible();
  await page.evaluate(()=>{failHistory=false;device.power_accounting='estimated';rows=[{timestamp:Date.now()/1000-10,state:{temperature:22,target_temperature:23,ac_power:900,power_accounting:'estimated'}}];});
  await page.getByRole('button',{name:'Спробувати ще раз'}).click();
  await expect(page.locator('.chart svg')).toHaveCount(1);
  expect(errors).toEqual([]);
});
