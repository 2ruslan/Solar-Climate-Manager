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
  if(path.endsWith('/flow')){if(!path.includes('/options/')){current='reconfigure';return structuredClone(fixture.forms.reconfigure);}current='init';return structuredClone(data.handler==='independent'?fixture.forms.independent:fixture.forms.energy);}
  if(data.settings_action==='group'){current='group';return menu(current);}
  if(data.settings_action==='learning_reset'){current='learning_reset';return structuredClone(fixture.forms[current]);}
  if(data.next_step_id){current=data.next_step_id;return current==='group'?menu(current):structuredClone(fixture.forms[current]);}
  if(current==='group_create')current='group_sources';
  else if(current==='group_sources')current='group_policy';
  else return {type:'create_entry'};
  return structuredClone(fixture.forms[current]);
 }};
fixture.overview.devices[0].name='Вітальня';
fixture.overview.devices[0].learning={enabled:true,supported:true,status:'ready',source:'learned',confidence:'consistent',samples:3,learned_watts:1200};
fixture.overview.devices[0].power_accounting='estimated';fixture.overview.devices[0].planned_power=1440;
fixture.overview.devices[1].name='Спальня';
const independent=structuredClone(fixture.overview.devices[0]);
Object.assign(independent,{device_id:'independent',entry_id:'independent',name:'Кабінет',group_id:null,power_accounting:'estimated',action:'wait'});
independent.learning={enabled:false};
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
            page.locator(".device").first.locator("summary").filter(has_text="Споживання").click()
            expect(page.locator("dialog")).not_to_be_visible()
            assert page.locator('[name="settings_action"]').count() == 0
            expect(page.locator('[name="estimated_ac_power"]')).to_have_value("900")
            page.locator('[name="estimated_ac_power"]').fill("1200")
            page.locator('[name="power_accounting"]').select_option("estimated")
            page.locator('[name="power_learning_enabled"]').check()
            page.evaluate("fixture.overview.devices[0].temperature=22;panel.refresh()")
            expect(page.locator('[name="estimated_ac_power"]')).to_have_value("1200")
            page.screenshot(path="/tmp/scm-panel-form.png")
            page.get_by_role("button", name="Зберегти", exact=True).click()
            expect(page.locator("#notice")).to_have_text("Зміни збережено")
            saved = page.evaluate("calls.at(-1)[2]")
            assert saved["consumption"]["estimated_ac_power"] == 1200
            assert saved["consumption"]["power_accounting"] == "estimated"
            assert saved["consumption"]["power_learning_enabled"] is True
            assert "ac_power_entity" not in saved["consumption"]
            assert "temperature_entity" in saved["comfort"]
            page.locator(".device").last.locator("summary").filter(has_text="Мережа").click()
            for title in ("Клімат і розклад", "Мережа", "Батарея", "Сонячна генерація", "Споживання"):
                expect(page.locator(".device").last.locator("summary").filter(has_text=title)).to_be_visible()
            page.locator('[name="grid_on_means_available"]').uncheck()
            page.locator('[name="grid_positive"]').select_option("export")
            page.get_by_role("button", name="Зберегти", exact=True).click()
            saved = page.evaluate("calls.at(-1)[2]")
            assert saved["grid"]["grid_on_means_available"] is False
            assert saved["grid"]["grid_positive"] == "export"
            assert set(saved) == {"comfort", "grid", "battery", "solar", "consumption", "settings_action"}
            expect(page.locator('[name="grid_positive"]')).to_have_count(0)
            page.locator(".device").last.locator("summary").filter(has_text="Сонячна генерація").click()
            page.locator('[name="generation_forecast_entity"]').fill("sensor.forecast")
            page.get_by_role("button", name="Зберегти", exact=True).click()
            expect(page.locator('[name="generation_forecast_entity"]')).to_have_count(0)
            saved = page.evaluate("calls.at(-1)[2]")
            assert saved["solar"]["generation_forecast_entity"] == "sensor.forecast"
            page.locator(".group").first.locator(":scope > details > summary").filter(has_text="Батарея").click()
            page.locator('[name="minimum_soc"]').fill("70")
            page.get_by_role("button", name="Зберегти", exact=True).click()
            expect(page.locator('[name="minimum_soc"]')).to_have_count(0)
            saved = page.evaluate("calls.at(-1)[2]")
            assert saved["minimum_soc"] == 70
            assert saved["load_power_entity"] == "sensor.load"
            assert "settings_action" not in saved
            page.locator(".device").first.locator("summary").filter(has_text="Назва та пріоритет").click()
            expect(page.locator('[name="priority"]')).to_be_visible()
            page.locator('[name="priority"]').fill("9")
            page.get_by_role("button", name="Зберегти", exact=True).click()
            expect(page.locator('[name="priority"]')).to_have_count(0)
            assert page.evaluate("calls.at(-1)[2].priority") == 9
            page.locator(".device").first.locator("summary").filter(has_text="Змінити прив’язки").click()
            expect(page.locator('[name="climate_entity"]')).to_have_value("climate.test")
            page.get_by_role("button", name="Скасувати", exact=True).click()
            expect(page.locator('[name="climate_entity"]')).to_have_count(0)
            assert page.evaluate("calls.at(-1)[0]") == "DELETE"
            expect(page.get_by_text("Навчена оцінка · Узгоджені спостереження", exact=False)).to_be_visible()
            page.get_by_role("button", name="Скинути навчання", exact=True).first.click()
            page.get_by_role("button", name="Підтвердити", exact=True).click()
            expect(page.get_by_role("heading", name="Зміни збережено")).to_be_visible()
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
            page.locator(".device").first.locator("summary").filter(has_text="Споживання").click()
            expect(page.locator('[name="estimated_ac_power"]')).to_be_visible()
            page.evaluate("window.failWrite=true")
            page.get_by_role("button", name="Зберегти", exact=True).click()
            expect(page.get_by_text("Не вдалося перевірити результат збереження.", exact=False)).to_be_visible()
            page.get_by_role("button", name="Закрити", exact=True).click()
            page.evaluate("window.failWrite=false;window.offline=true;panel.refresh()")
            expect(page.get_by_text("Зв’язок із Home Assistant втрачено.", exact=False)).to_be_visible()
            page.evaluate("window.offline=false;panel.refresh()")
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator(".device").first.locator("summary").filter(has_text="Клімат і розклад").click()
            expect(page.locator('[name="target_temperature"]')).to_be_visible()
            assert page.evaluate("panel.shadowRoot.querySelector('.page').scrollWidth") <= 390
            page.get_by_role("button", name="Скасувати", exact=True).click()
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
