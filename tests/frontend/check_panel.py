"""Browser smoke checks against real HA schemas exported by test_panel.py.

Run after the HA suite in the same environment. No real HA commands are sent.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "custom_components/solar_climate_manager"
FIXTURE = json.loads(Path("/tmp/scm-panel-fixture.json").read_text())
FIXTURE["labels"] = {
    lang: json.loads((COMPONENT / f"translations/{lang}.json").read_text())
    for lang in ("en", "uk")
}
HTML = """<!doctype html><html><meta charset="utf-8">
<style>html,body{margin:0;height:100%}solar-climate-panel{height:100%}</style>
<script type="module">
import '/panel.js';
window.fixture=await (await fetch('/fixture')).json();
window.calls=[];window.offline=false;window.failWrite=false;
window.current=null;
const menu=step=>({type:'menu',step_id:step,flow_id:'test',menu_options:step==='init'?['energy','group']:['group_create','group_join']});
window.hass={language:'uk',user:{is_admin:true},connection:{},states:{
 'sensor.room':{entity_id:'sensor.room',attributes:{friendly_name:'Кімната'}},
 'climate.test':{entity_id:'climate.test',attributes:{friendly_name:'Вітальня'}}
},
 callWS:async msg=>{if(window.offline)throw Error('offline');return {...structuredClone(fixture.overview),translations:fixture.labels[msg.language]};},
 callService:async (...args)=>{calls.push(['service',...args]);},
 callApi:async(method,path,data)=>{
  calls.push([method,path,data]);
  if(method==='DELETE')return {};
  if(window.failWrite)throw Error('offline');
  if(path.endsWith('/flow')){current='init';return menu(current);}
  if(data.next_step_id){current=data.next_step_id;return current==='group'?menu(current):structuredClone(fixture.forms[current]);}
  if(current==='group_create')current='group_sources';
  else if(current==='group_sources')current='group_policy';
  else return {type:'create_entry'};
  return structuredClone(fixture.forms[current]);
 }};
fixture.overview.devices[0].name='Вітальня';
fixture.overview.devices[1].name='Спальня';
const independent=structuredClone(fixture.overview.devices[0]);
Object.assign(independent,{device_id:'independent',entry_id:'independent',name:'Кабінет',group_id:null,power_accounting:'estimated',action:'wait'});
fixture.overview.devices.push(independent);
window.panel=document.createElement('solar-climate-panel');panel.hass=hass;document.body.append(panel);
</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/panel.js":
            body = (COMPONENT / "frontend/panel.js").read_bytes()
            kind = "text/javascript"
        elif self.path == "/fixture":
            body = json.dumps(FIXTURE).encode()
            kind = "application/json"
        else:
            body = HTML.encode()
            kind = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 1080})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}")
            expect(page.get_by_role("heading", name="Будинок")).to_be_visible()
            page.screenshot(path="/tmp/scm-panel-desktop.png", full_page=True)
            page.get_by_role("button", name="Облік потужності").first.click()
            expect(page.locator('[name="estimated_ac_power"]')).to_have_value("900")
            page.locator('[name="estimated_ac_power"]').fill("1200")
            page.locator('[name="power_accounting"]').select_option("estimated")
            page.screenshot(path="/tmp/scm-panel-form.png")
            page.get_by_role("button", name="Зберегти", exact=True).click()
            expect(page.get_by_role("heading", name="Зміни збережено")).to_be_visible()
            saved = page.evaluate("calls.at(-1)[2]")
            assert saved["estimated_ac_power"] == 1200
            assert saved["power_accounting"] == "estimated"
            assert "ac_power_entity" not in saved
            page.get_by_role("button", name="Готово", exact=True).click()
            page.get_by_role("button", name="Створити групу", exact=True).click()
            page.get_by_role("button", name="Кабінет", exact=True).click()
            page.locator('[name="name"]').fill("Нова група")
            page.get_by_role("button", name="Далі", exact=True).click()
            expect(page.locator('[name="grid_on_means_available"]')).to_be_checked()
            page.locator('[name="grid_on_means_available"]').uncheck()
            page.get_by_role("button", name="Далі", exact=True).click()
            assert page.evaluate("calls.at(-1)[2].grid_on_means_available") is False
            expect(page.locator('[name="minimum_soc"]')).to_have_value("85")
            page.get_by_role("button", name="Скасувати", exact=True).click()
            expect(page.locator("dialog")).not_to_be_visible()
            assert page.evaluate("calls.at(-1)[0]") == "DELETE"
            page.get_by_role("button", name="Додати до групи", exact=True).last.click()
            expect(page.locator('[name="group_id"]')).to_have_value(FIXTURE["overview"]["groups"][0]["group_id"])
            page.get_by_role("button", name="Скасувати", exact=True).click()
            page.locator("select.mode").first.select_option("disabled")
            assert page.evaluate("calls.at(-1)[0]") == "service"
            page.get_by_role("button", name="Облік потужності").first.click()
            page.evaluate("window.failWrite=true")
            page.get_by_role("button", name="Зберегти", exact=True).click()
            expect(page.get_by_text("Не вдалося перевірити результат збереження.", exact=False)).to_be_visible()
            page.get_by_role("button", name="Закрити", exact=True).click()
            page.evaluate("window.failWrite=false;window.offline=true;panel.refresh()")
            expect(page.get_by_text("Зв’язок із Home Assistant втрачено.", exact=False)).to_be_visible()
            page.evaluate("window.offline=false;panel.refresh()")
            page.set_viewport_size({"width": 390, "height": 844})
            page.evaluate("panel.shadowRoot.querySelector('.page').scrollTop=0")
            page.screenshot(path="/tmp/scm-panel-mobile.png", full_page=True)
            assert page.evaluate("panel.shadowRoot.querySelector('.page').scrollWidth") <= 390
            page.evaluate("hass.language='en';panel.hass={...hass}")
            expect(page.get_by_role("button", name="Create group", exact=True)).to_be_visible()
            page.evaluate("fixture.overview.groups[0].name='<img src=x onerror=alert(1)>';panel.refresh()")
            expect(page.get_by_role("heading", name="<img src=x onerror=alert(1)>")).to_be_visible()
            assert page.locator("img").count() == 0
            page.evaluate("hass.user.is_admin=false;panel.refresh()")
            expect(page.get_by_text("This page is available to Home Assistant administrators.")).to_be_visible()
            assert page.get_by_role("button", name="Create group", exact=True).count() == 0
            assert not errors, errors
            browser.close()
            print("Browser checks passed: forms, wizard, cancel, join, mode, errors, mobile, EN/UK, admin, text escaping")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
