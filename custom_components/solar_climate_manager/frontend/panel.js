/* Native HA panel. No external scripts, build step, or separate server. */
const TEXT = {
  uk: {
    subtitle: "Кондиціонери та спільний енергетичний бюджет", groups: "Енергетичні групи",
    devices: "Пристрої", independent: "Поза групами", create: "Створити групу",
    add: "Додати кондиціонер", refresh: "Оновити", settings: "Налаштувати",
    sources: "Спільні джерела", policy: "Правила групи", rename: "Назва та пріоритет",
    join: "Додати до групи", leave: "Вийти з групи", remove: "Видалити порожню групу",
    comfort: "Комфорт", energy: "Облік потужності", reconfigure: "Змінити прив’язки",
    load: "Навантаження", available: "Доступна потужність", reserve: "Резерв запусків",
    unlimited: "Без заданого ліміту", missing: "Немає даних", unavailable: "Пристрій недоступний",
    temperature: "Температура / ціль", measured: "Виміряна потужність", estimated: "Планова потужність",
    priority: "Пріоритет", noGroups: "Створіть групу, щоб кондиціонери використовували спільний бюджет.",
    noDevices: "Спочатку додайте кондиціонер і датчик кімнатної температури.",
    noIndependent: "Усі пристрої вже належать до груп.", noMembers: "У цій групі ще немає пристроїв.",
    noCandidates: "Немає незалежних пристроїв. Додайте кондиціонер або спочатку виведіть його з іншої групи.",
    choose: "Виберіть пристрій", next: "Далі", save: "Зберегти", confirm: "Підтвердити",
    cancel: "Скасувати", close: "Закрити", loading: "Завантаження…", saving: "Збереження…",
    saved: "Зміни збережено", failed: "Не вдалося виконати дію. Перевірте з’єднання та спробуйте ще раз.",
    lost: "Зв’язок із Home Assistant втрачено. Показані дані можуть бути застарілими.",
    disconnected: "Немає з’єднання", admin: "Ця сторінка доступна адміністратору Home Assistant.",
    retry: "Спробувати ще раз", optional: "необов’язково", chooseEntity: "Виберіть сутність або введіть її ID",
    preview: "Спостереження не надсилає команд. Рішення з позначкою «Прогноз» є розрахунковими.",
    chooseHint: "Створення групи приєднає цей пристрій. Перед зміною складу переведіть відповідні пристрої у спостереження.",
    unknownField: "Це поле не підтримується сторінкою. Скористайтеся налаштуваннями інтеграції.",
    integration: "Відкрити інтеграцію", mode: "Режим роботи", on: "Увімкнено", off: "Вимкнено",
    lastUpdate: "Оновлено", finish: "Готово", sessionLost: "Не вдалося перевірити результат збереження. Оновіть дані перед повторною дією.",
    availableHint: "Бюджет цієї групи; показники різних пристроїв групи не підсумовуються.",
    learning: "Уточнення потужності", configured: "Задана оцінка", learned: "Навчена оцінка",
    samples: "Прийняті цикли", consistent: "Узгоджені спостереження", insufficient: "Недостатньо даних",
    resetLearning: "Скинути навчання",
    history: "Історія та діагностика", exportHistory: "Завантажити JSON", time: "Час",
    decision: "Рішення / причина", command: "Команда / помилка", actual: "Фактичний стан",
    historyHint: "До 24 годин / 3000 записів на пристрій. Збір працює із закритою сторінкою; перезапуск HA або перезавантаження інтеграції очищає історію. Таблиця: останні 200 записів; JSON: усі доступні записи. Час — локальний для браузера. Рішення не є підтвердженням виконання команди.",
    historyEmpty: "Історія ще не накопичена.",
    runningCount: "Працюють зараз", unavailableCount: "Недоступні",
  },
  en: {
    subtitle: "Air conditioners and a shared energy budget", groups: "Energy groups",
    devices: "Devices", independent: "Outside groups", create: "Create group", add: "Add air conditioner",
    refresh: "Refresh", settings: "Configure", sources: "Shared sources", policy: "Group policy",
    rename: "Name and priority", join: "Join group", leave: "Leave group", remove: "Delete empty group",
    comfort: "Comfort", energy: "Power accounting", reconfigure: "Change bindings",
    load: "Load", available: "Available power", reserve: "Start reservations", unlimited: "No configured limit",
    missing: "No data", unavailable: "Device unavailable", temperature: "Temperature / target",
    measured: "Measured power", estimated: "Planned power", priority: "Priority",
    noGroups: "Create a group to share one energy budget between air conditioners.",
    noDevices: "Start by adding an air conditioner and its room temperature sensor.",
    noIndependent: "All devices already belong to groups.", noMembers: "This group has no devices yet.",
    noCandidates: "No independent devices. Add an air conditioner or first remove it from another group.",
    choose: "Choose a device", next: "Next", save: "Save", confirm: "Confirm", cancel: "Cancel",
    close: "Close", loading: "Loading…", saving: "Saving…", saved: "Changes saved",
    failed: "The action failed. Check the connection and try again.",
    lost: "Connection to Home Assistant lost. Displayed data may be out of date.", disconnected: "Disconnected",
    admin: "This page is available to Home Assistant administrators.", retry: "Try again", optional: "optional",
    chooseEntity: "Choose an entity or enter its ID", preview: "Observation sends no commands. Preview decisions are hypothetical.",
    chooseHint: "Creating a group joins this device. Switch affected devices to Observation before changing membership.",
    unknownField: "This field is not supported here. Use the integration settings.", integration: "Open integration",
    mode: "Operation mode", on: "On", off: "Off", lastUpdate: "Updated", finish: "Done",
    sessionLost: "Could not verify whether the change was saved. Refresh the data before repeating the action.",
    availableHint: "This group's budget; do not add together the readings of its members.",
    learning: "Power learning", configured: "Configured estimate", learned: "Learned estimate",
    samples: "Accepted cycles", consistent: "Consistent observations", insufficient: "Insufficient data",
    resetLearning: "Reset learning",
    history: "History and diagnostics", exportHistory: "Download JSON", time: "Time",
    decision: "Decision / reason", command: "Command / error", actual: "Actual state",
    historyHint: "Up to 24 hours / 3000 records per device. Collection continues with the page closed; HA restart or integration reload clears history. Table: latest 200 records; JSON: all available records. Times use the browser time zone. Decisions do not confirm command execution.",
    historyEmpty: "No history collected yet.",
    runningCount: "Running now", unavailableCount: "Unavailable",
  },
};

export const fieldDefault = (field) => field.description?.suggested_value ?? field.default;
export const fieldKind = (field) => Object.keys(field.selector || {})[0] || field.type;
const SHARED_SECTIONS = {
  grid: ["grid_available_entity", "grid_on_means_available", "grid_power_entity", "grid_positive", "grid_import_limit_entity", "grid_absence_delay", "grid_max_data_age"],
  battery: ["soc_entity", "minimum_soc", "restart_soc", "battery_power_entity", "battery_positive", "max_battery_discharge"],
  solar: ["pv_power_entity", "forecast_power_now_entity", "forecast_power_30m_entity", "forecast_power_60m_entity", "start_delay", "shortage_delay"],
  consumption: ["load_power_entity", "load_scope", "load_includes_battery_charging", "power_max_data_age"],
};
export function formDefaults(fields) {
  const result = {};
  for (const field of fields) {
    if (Array.isArray(field.schema)) result[field.name] = formDefaults(field.schema);
    else {
      const value = fieldDefault(field);
      if (value !== undefined && value !== null) result[field.name] = value;
    }
  }
  return result;
}
export function readForm(fields, form) {
  const result = {};
  for (const field of fields) {
    if (Array.isArray(field.schema)) {
      result[field.name] = readForm(field.schema, form);
      continue;
    }
    const input = form.elements.namedItem(field.name);
    if (!input) throw new Error("unsupported_field");
    const kind = fieldKind(field);
    if (kind === "boolean") result[field.name] = input.checked;
    else if (input.value !== "") result[field.name] = kind === "number" ? Number(input.value) : input.value;
  }
  return result;
}

function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (cls) node.className = cls;
  return node;
}

const STYLE = `
  .inline-settings { margin-top:12px; border:1px solid var(--divider-color,#dce5df); border-radius:10px; }
  .inline-settings>summary { padding:14px 16px; cursor:pointer; font-weight:600; }
  .inline-body { padding:0 16px; max-width:900px; }
  .inline-body form { margin:0 0 16px; grid-template-columns:repeat(2,minmax(0,1fr)); align-items:start; }
  .inline-body .form-actions,.inline-body .error { grid-column:1/-1; }
  @media(max-width:700px) { .inline-body form { grid-template-columns:1fr; } }
  :host { display:block; height:100%; color:var(--primary-text-color,#20352f); background:var(--primary-background-color,#f4f7f5); font-family:var(--paper-font-body1_-_font-family,Roboto,Arial,sans-serif); }
  * { box-sizing:border-box; } .page { height:100%; overflow:auto; } header { position:sticky; top:0; z-index:2; background:var(--card-background-color,#fff); border-bottom:1px solid var(--divider-color,#e0e8e3); padding:16px 24px; display:flex; align-items:center; gap:12px; }
  h1 { font-size:21px; margin:0 0 4px; font-weight:650; } h2 { font-size:20px; margin:0; } h3 { font-size:17px; margin:0; overflow-wrap:anywhere; } p { margin:6px 0; line-height:1.5; } .subtle { color:var(--secondary-text-color,#61756b); font-size:13px; } .grow { flex:1; min-width:0; }
  main { max-width:1280px; margin:auto; padding:24px; } .toolbar,.actions,.heading { display:flex; align-items:center; flex-wrap:wrap; gap:10px; } .toolbar { justify-content:space-between; margin-bottom:24px; } .heading { justify-content:space-between; margin-bottom:14px; }
  button,select,input { font:inherit; } button { cursor:pointer; border:1px solid var(--divider-color,#dce5df); background:var(--card-background-color,#fff); color:var(--primary-text-color,#20352f); border-radius:9px; padding:9px 13px; min-height:40px; } button:hover { border-color:var(--primary-color,#22876c); } button:disabled { opacity:.5; cursor:default; } button.primary { background:var(--primary-color,#22876c); color:var(--text-primary-color,#fff); border-color:transparent; } button.danger { color:var(--error-color,#b93e3e); } button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible { outline:3px solid var(--primary-color,#22876c); outline-offset:2px; }
  .summary { display:flex; gap:26px; flex-wrap:wrap; } .summary strong { font-size:23px; display:block; } .group { background:var(--card-background-color,#fff); border:1px solid var(--divider-color,#dce5df); border-radius:16px; padding:20px; margin-bottom:20px; } .metrics { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin:18px 0; } .metric { background:var(--secondary-background-color,#eff5f1); border-radius:11px; padding:14px; } .metric strong { display:block; font-size:23px; margin-top:5px; font-weight:600; }
  .device { padding:18px 0; border-top:1px solid var(--divider-color,#e4eae7); } .device:first-child { border-top:0; } .device-top { display:flex; gap:12px; align-items:flex-start; } .badge { font-size:12px; padding:5px 9px; border-radius:20px; background:var(--secondary-background-color,#eff5f1); display:inline-block; } .values { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; margin:14px 0; } .values strong { display:block; margin-top:5px; font-size:16px; } .reason { margin:8px 0 14px; } .empty { border:1px dashed var(--divider-color,#dce5df); border-radius:14px; padding:24px; margin:16px 0; color:var(--secondary-text-color,#61756b); }
  .notice { padding:12px 16px; border-radius:10px; background:var(--secondary-background-color,#eff5f1); margin:12px 0; line-height:1.5; } .error { color:var(--error-color,#b93e3e); } #status:empty,#notice:empty { display:none; } .section { margin-top:30px; } select,input { border:1px solid var(--divider-color,#c9d7ce); color:var(--primary-text-color,#20352f); background:var(--card-background-color,#fff); border-radius:8px; min-height:42px; padding:9px; max-width:100%; } .mode { min-width:190px; } a { color:var(--primary-color,#22876c); }
  dialog { border:1px solid var(--divider-color,#dce5df); border-radius:16px; padding:0; width:min(620px,calc(100vw - 24px)); max-height:calc(100dvh - 32px); color:var(--primary-text-color,#20352f); background:var(--card-background-color,#fff); } dialog::backdrop { background:rgba(15,30,25,.5); } .dialog-body { padding:24px; } .dialog-head { display:flex; align-items:center; gap:12px; margin-bottom:12px; } form { display:grid; gap:16px; margin-top:18px; } label { display:grid; gap:7px; font-size:14px; } label.check { display:flex; align-items:center; gap:10px; } input[type=checkbox] { min-height:22px; width:22px; } .form-actions { display:flex; justify-content:flex-end; gap:10px; position:sticky; bottom:0; background:var(--card-background-color,#fff); padding:12px 0 0; } .menu { display:grid; gap:10px; margin-top:18px; } .menu button { text-align:start; } .field-error { font-size:13px; } .footer { margin:20px 0; }
  dialog.history { width:min(1200px,calc(100vw - 24px)); } .history-scroll { overflow:auto; max-height:60vh; margin-top:16px; } table { border-collapse:collapse; width:100%; font-size:13px; } th,td { text-align:start; padding:10px; border-bottom:1px solid var(--divider-color,#dce5df); min-width:120px; } th { position:sticky; top:0; background:var(--card-background-color,#fff); }
  @media(max-width:700px) { header { padding:12px; } h1 { font-size:18px; } main { padding:16px 12px; } .group { padding:16px; } .metrics { gap:7px; } .metric { padding:10px; } .metric strong { font-size:18px; } .values { grid-template-columns:1fr 1fr; } .values>div:last-child { grid-column:1/-1; } .actions { gap:7px; } .dialog-body { padding:18px; } .summary { gap:20px; } .device-top { flex-wrap:wrap; } }
  @media(prefers-reduced-motion:reduce) { * { scroll-behavior:auto!important; } }
`;

export class SolarClimatePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this._lang = "en";
    this._busy = false;
    this._refreshing = false;
    this._dialogBusy = false;
    this._flow = null;
    this._inlineEditors = new Set();
    this._fieldId = 0;
    this._visibility = () => { if (!document.hidden) this.refresh(); };
  }
  set hass(value) {
    const changed = this._hass?.connection !== value.connection;
    this._hass = value;
    const lang = value.language?.startsWith("uk") ? "uk" : "en";
    if (lang !== this._lang) { this._lang = lang; this._labels = null; this._signature = null; }
    if (this.isConnected && (changed || !this._data || !this._labels)) this.refresh();
  }
  get hass() { return this._hass; }
  t(key) { return TEXT[this._lang][key] || key; }
  connectedCallback() {
    if (!this._shell) this._init();
    this._timer = setInterval(() => { if (!document.hidden) this.refresh(); }, 5000);
    document.addEventListener("visibilitychange", this._visibility);
    this.refresh();
  }
  disconnectedCallback() {
    clearInterval(this._timer);
    document.removeEventListener("visibilitychange", this._visibility);
    this._cancelFlow();
    for (const editor of this._inlineEditors) editor.cancel();
  }
  _init() {
    this._shell = true;
    const style = el("style", STYLE);
    const page = el("div", null, "page");
    const header = el("header");
    const menu = this.button("☰", () => this.dispatchEvent(new CustomEvent("hass-toggle-menu", {bubbles:true,composed:true})));
    menu.setAttribute("aria-label", "Home Assistant menu");
    this._title = el("div", null, "grow");
    header.append(menu, this._title);
    const main = el("main");
    this._status = el("div", null, "notice error"); this._status.id = "status"; this._status.setAttribute("role","alert");
    this._notice = el("div", null, "notice"); this._notice.id = "notice"; this._notice.setAttribute("role","status");
    this._overview = el("div");
    main.append(this._status, this._notice, this._overview);
    this._dialog = el("dialog"); this._dialog.setAttribute("aria-labelledby","dialog-title");
    this._dialog.addEventListener("cancel", event => { if (this._dialogBusy) event.preventDefault(); else this._cancelFlow(); });
    page.append(header,main); this.shadowRoot.append(style,page,this._dialog);
    this._overview.textContent = this.t("loading");
  }
  button(text, action, cls="") {
    const button = el("button", text, cls); button.type="button";
    button.addEventListener("click", action); return button;
  }
  errorText(code) {
    return this._labels?.options?.error?.[code] || this._labels?.config?.error?.[code] ||
      this._labels?.options?.abort?.[code] || this._labels?.config?.abort?.[code] || this.t("failed");
  }
  stateText(kind, value) {
    return this._labels?.entity?.sensor?.[kind]?.state?.[value] ||
      this._labels?.entity?.select?.[kind]?.state?.[value] || value || this.t("missing");
  }
  watts(value) { return Number.isFinite(value) ? `${Math.round(value).toLocaleString(this._lang)} W` : this.t("missing"); }
  async refresh() {
    if (!this._hass || !this._shell || !this.isConnected || this._refreshing) return;
    this._title.replaceChildren(el("h1","Solar Climate Manager"),el("div",this.t("subtitle"),"subtle"));
    if (!this._hass.user?.is_admin) { for (const editor of this._inlineEditors) editor.cancel(); this._status.textContent=this.t("admin"); this._overview.replaceChildren(); return; }
    this._refreshing=true;
    try {
      const data = await this._hass.callWS({type:"solar_climate_manager/overview",language:this._lang,include_translations:!this._labels});
      if (!this.isConnected) return;
      if (data.translations) { this._labels=data.translations; delete data.translations; }
      this._data=data;
      this._status.textContent=data.error ? this.errorText(data.error) : "";
      const signature=JSON.stringify(data);
      const focused=this.shadowRoot.activeElement;
      if (signature !== this._signature && !this._inlineEditors.size && !["INPUT","SELECT"].includes(focused?.tagName)) {
        this._signature=signature; this._renderOverview();
      }
    } catch (error) { this._status.textContent=error.code === "unauthorized" ? this.t("admin") : this.t("lost"); }
    finally { this._refreshing=false; }
  }
  _renderOverview() {
    const data=this._data;
    const content=el("div");
    const toolbar=el("div",null,"toolbar");
    const stats=el("div",null,"summary");
    for (const [count,key] of [[data.groups.length,"groups"],[data.devices.length,"devices"],[data.devices.filter(d=>!d.group_id).length,"independent"],[data.devices.filter(d=>d.loaded && d.running===true).length,"runningCount"],[data.devices.filter(d=>!d.loaded).length,"unavailableCount"]]) {
      const stat=el("div",null,"subtle"); stat.append(el("strong",count),el("span",this.t(key))); stats.append(stat);
    }
    const actions=el("div",null,"actions");
    const create=this.button(this.t("create"),()=>this.chooseDevice("group_create"),"primary"); create.disabled=!!data.error;
    actions.append(create,this.button(this.t("add"),()=>this.startFlow(null,"user")),this.button(this.t("refresh"),()=>{this._signature=null;this.refresh();}));
    toolbar.append(stats,actions); content.append(toolbar);
    content.append(el("p",this.t("preview"),"subtle"));
    if (!data.devices.length) content.append(el("div",this.t("noDevices"),"empty"));
    if (!data.groups.length) content.append(el("div",this.t("noGroups"),"empty"));
    for (const group of data.groups) content.append(this.groupCard(group));
    const independent=data.devices.filter(d=>!d.group_id);
    const section=el("section",null,"section"); section.append(el("h2",this.t("independent")));
    if (!independent.length) section.append(el("p",this.t("noIndependent"),"subtle"));
    else { const card=el("div",null,"group"); independent.forEach(d=>card.append(this.deviceCard(d))); section.append(card); }
    content.append(section);
    const footer=el("div",null,"footer subtle");
    const link=el("a",this.t("integration")); link.href="/config/integrations/integration/solar_climate_manager";
    footer.append(link,el("span",` · ${data.version}`)); content.append(footer);
    this._overview.replaceChildren(content);
  }
  groupCard(group) {
    const card=el("section",null,"group");
    const heading=el("div",null,"heading");
    heading.append(el("h2",group.name),el("span",`${group.members.length} · ${this.t("devices")}`,"badge"));
    card.append(heading);
    const metrics=el("div",null,"metrics");
    for (const [key,value] of [["load",this.watts(group.load_power)],["available",group.unlimited?this.t("unlimited"):this.watts(group.available_power)],["reserve",this.watts(group.reserved_power)]]) {
      const metric=el("div",null,"metric"); metric.append(el("div",this.t(key),"subtle"),el("strong",value)); metrics.append(metric);
    }
    card.append(metrics,el("p",this.t("availableHint"),"subtle"));
    const actions=el("div",null,"actions");
    actions.append(this.button(this.t("join"),()=>this.chooseDevice("group_join",group.group_id)));
    const representative=this._data.devices.find(d=>d.group_id===group.group_id && d.loaded);
    if (!group.members.length) {
      const entry=this._data.devices.find(d=>d.loaded);
      const remove=this.button(this.t("remove"),()=>this.startFlow(entry,"group_delete",{group_id:group.group_id}),"danger");
      remove.disabled=!entry || group.has_reservations; actions.append(remove);
      card.append(el("p",this.t("noMembers"),"subtle"));
    }
    card.append(actions);
    if (group.edit_block) card.append(el("p",this.errorText(group.edit_block),"subtle reason"));
    if (representative) for (const name of Object.keys(SHARED_SECTIONS)) {
      card.append(this.inlineSettings(representative, name, true));
    }
    const members=el("div");
    for (const member of group.members) {
      const device=this._data.devices.find(d=>d.device_id===member.device_id);
      members.append(device ? this.deviceCard(device) : el("div",this.t("unavailable"),"device error"));
    }
    card.append(members); return card;
  }
  deviceCard(device) {
    const card=el("article",null,"device");
    const top=el("div",null,"device-top"); const title=el("div",null,"grow");
    title.append(el("h3",device.name),el("div",device.climate_entity,"subtle"));
    top.append(title,el("span",!device.loaded?this.t("unavailable"):device.running===null?this.t("missing"):this.t(device.running?"on":"off"),"badge"));
    card.append(top);
    const values=el("div",null,"values");
    const temp=Number.isFinite(device.temperature)?`${device.temperature.toLocaleString(this._lang)} °C`:this.t("missing");
    const power=device.power_accounting==="estimated" || device.measured_power===null;
    for (const [key,text] of [["temperature",`${temp} / ${device.target} °C`],[power?"estimated":"measured",this.watts(power?device.planned_power:device.measured_power)],["priority",device.group_id?device.priority:"—"]]) {
      const value=el("div"); value.append(el("div",this.t(key),"subtle"),el("strong",text)); values.append(value);
    }
    card.append(values);
    if (device.learning?.enabled) {
      const learned=device.learning;
      card.append(el("p",`${this.t(learned.source)} · ${this.t(learned.confidence)} · ${this.t("samples")}: ${learned.samples}`,"subtle"));
      const status=this._labels?.selector?.learning_status?.options?.[learned.status] || learned.status;
      card.append(el("p",`${this.t("learning")}: ${status}${learned.learned_watts===null?"":` · ${this.watts(learned.learned_watts)}`}`,"subtle"));
    }
    const action=this.stateText(device.group_id?"group_action":"strategy_action",device.action);
    const reason=this.stateText(device.group_id?"group_reason":"strategy_reason",device.reason);
    card.append(el("p",`${action} · ${reason}`,"reason"));
    if (device.group_id && device.command_status && device.command_status!=="idle") card.append(el("p",this.stateText("group_command_status",device.command_status),"subtle reason"));
    const actions=el("div",null,"actions");
    const mode=el("select",null,"mode"); mode.setAttribute("aria-label",`${this.t("mode")}: ${device.name}`);
    for (const value of ["disabled","observation","control","temporary_block"]) { const option=el("option",this.stateText("operation_mode",value));option.value=value;mode.append(option); }
    mode.value=device.mode; mode.disabled=!device.loaded || !device.mode_entity;
    mode.addEventListener("change",async()=>{
      mode.disabled=true;
      try { await this._hass.callService("select","select_option",{entity_id:device.mode_entity,option:mode.value});this._notice.textContent=this.t("saved"); }
      catch { this._notice.textContent=this.t("failed");mode.value=device.mode; }
      finally { mode.blur();this._signature=null;await this.refresh(); }
    });
    actions.append(mode);
    const history=this.button(this.t("history"),()=>this.showHistory(device));
    history.disabled=!device.loaded; actions.append(history);
    if (device.group_id) {
      actions.append(this.button(this.t("leave"),()=>this.startFlow(device,"group_leave")));
      const reset=this.button(this.t("resetLearning"),()=>this.startFlow(device,"learning_reset"));
      reset.disabled=!device.loaded;actions.append(reset);
    } else {
      const join=this.button(this.t("join"),()=>this.startFlow(device,"group_join"));join.disabled=!this._data.groups.length || !!this._data.error;actions.append(join);
    }
    card.append(actions);
    if (device.edit_block) card.append(el("p",this.errorText(device.edit_block),"subtle"));
    if (device.loaded) for (const name of (device.group_id ? ["comfort","consumption"] : ["comfort","grid","battery","solar","consumption"])) {
      card.append(this.inlineSettings(device, name, false));
    }
    if(device.loaded) {
      card.append(this.inlineSettings(device,"reconfigure",false,"reconfigure"));
      if(device.group_id)card.append(this.inlineSettings(device,"rename",false,"group_member"));
    }
    return card;
  }
  inlineSettings(device, name, shared, step=null) {
    const host=el("details",null,"inline-settings");
    const title=step?this.t(name):this._labels?.options?.step?.init?.sections?.[name]?.name || name;
    host.append(el("summary",title));
    const body=el("div",null,"inline-body");host.append(body);
    const config=step==="reconfigure";
    const base=`config/config_entries/${config?"":"options/"}flow`;
    const editor={host,flow:null,busy:false,closed:false,cancel:async()=>{
      editor.closed=true;this._inlineEditors.delete(editor);
      const flow=editor.flow;editor.flow=null;
      if(flow?.flow_id && !["create_entry","abort"].includes(flow.type)) {
        try {await this._hass.callApi("DELETE",`${base}/${flow.flow_id}`);} catch { /* Expired flow. */ }
      }
    }};
    const close=async()=>{await editor.cancel();host.open=false;body.replaceChildren();this._signature=null;this.refresh();};
    const render=()=>{
      const flow=editor.flow;
      body.replaceChildren();
      if(flow.type!=="form") {
        body.append(el("p",this.errorText(flow.reason),"error"),this.button(this.t("close"),close));return;
      }
      const labels=this._labels[config?"config":"options"].step[step || (shared?"group_settings":"init")];
      const fields=step?flow.data_schema:shared ? SHARED_SECTIONS[name].map(key=>flow.data_schema.find(f=>f.name===key)).filter(Boolean) :
        flow.data_schema.find(f=>f.name===name)?.schema || [];
      const fieldLabels=shared || step?labels:labels.sections[name];
      const form=el("form");let supported=fields.length>0;
      if(flow.errors?.base)form.append(el("p",this.errorText(flow.errors.base),"error"));
      for(const field of fields) {
        const rendered=this.renderField(field,fieldLabels,flow.errors || {},{});
        if(rendered)form.append(rendered);else supported=false;
      }
      if(!supported)form.append(el("p",this.t("unknownField"),"error"));
      const actions=el("div",null,"form-actions");
      const save=el("button",this.t("save"),"primary");save.type="submit";save.disabled=!supported;
      actions.append(this.button(this.t("cancel"),close),save);form.append(actions);body.append(form);
      form.addEventListener("submit",async event=>{
        event.preventDefault();if(editor.busy || !form.reportValidity())return;
        const input=formDefaults(flow.data_schema);
        const changed=readForm(fields,form);
        if(shared || step) {
          for(const field of fields)delete input[field.name];
          Object.assign(input,changed);
        } else {input[name]=changed;input.settings_action="save";}
        editor.busy=true;form.querySelectorAll("button,input,select").forEach(node=>node.disabled=true);
        try {
          editor.flow=await this._hass.callApi("POST",`${base}/${flow.flow_id}`,input);
          if(editor.closed)return;
          if(editor.flow.type==="create_entry" || editor.flow.type==="abort" && editor.flow.reason==="reconfigure_successful") {
            this._notice.textContent=this.t("saved");await close();
          } else render();
        } catch {
          body.replaceChildren(el("p",this.t("sessionLost"),"error"),this.button(this.t("close"),close));
        } finally {editor.busy=false;}
      });
    };
    host.addEventListener("toggle",async()=>{
      if(!host.open) {if(editor.busy && !editor.closed){host.open=true;return;}await editor.cancel();return;}
      if(this._inlineEditors.has(editor))return;
      editor.closed=false;editor.busy=true;this._inlineEditors.add(editor);
      body.replaceChildren(el("p",this.t("loading")));
      try {
        editor.flow=await this._hass.callApi("POST",base,config?{handler:"solar_climate_manager",entry_id:device.entry_id}:{handler:device.entry_id});
        if((shared || step?.startsWith("group_")) && !editor.closed) {
          editor.flow=await this._hass.callApi("POST",`${base}/${editor.flow.flow_id}`,{...formDefaults(editor.flow.data_schema),settings_action:"group"});
          if(editor.flow.type==="menu")editor.flow=await this._hass.callApi("POST",`${base}/${editor.flow.flow_id}`,{next_step_id:step || "group_settings"});
        }
        if(editor.closed || !host.isConnected){await editor.cancel();return;}
        render();
      } catch {body.replaceChildren(el("p",this.t("failed"),"error"),this.button(this.t("close"),close));}
      finally {editor.busy=false;}
    });
    return host;
  }
  async showHistory(device) {
    const body=this._openDialog(`${this.t("history")} · ${device.name}`,this.t("historyHint"));
    this._dialog.classList.add("history");
    const status=el("p",this.t("loading")); body.append(status);
    try {
      const result=await this._hass.callWS({type:"solar_climate_manager/history",entry_id:device.entry_id});
      if (!body.isConnected || !this._dialog.open) return;
      status.textContent=`${result.rows.length} · ${this.t("lastUpdate")}: ${new Date(result.generated_at*1000).toLocaleString(this._lang)}`;
      const actions=el("div",null,"actions");
      actions.append(this.button(this.t("refresh"),()=>this.showHistory(device)),this.button(this.t("exportHistory"),()=>{
        const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:"application/json"}));
        const link=el("a");link.href=url;link.download="solar-climate-history.json";body.append(link);link.click();link.remove();
        setTimeout(()=>URL.revokeObjectURL(url),1000);
      }));body.append(actions);
      if (!result.rows.length) { body.append(el("p",this.t("historyEmpty")));return; }
      const scroll=el("div",null,"history-scroll");scroll.tabIndex=0;
      const table=el("table");const head=el("thead");const titles=el("tr");
      for (const key of ["time","mode","temperature","actual","measured","available","reserve","decision","command"]) {
        const th=el("th",this.t(key));th.scope="col";titles.append(th);
      }
      head.append(titles);table.append(head);const rows=el("tbody");
      const value=v=>v===null || v===undefined?this.t("missing"):String(v);
      for (const row of result.rows.slice(-200).reverse()) {
        const s=row.state;const tr=el("tr");
        if (s.command_failed || s.group_command_status==="failed" || s.invalid_data || s.energy_data_invalid) tr.className="error";
        const grouped=s.group_action && s.group_action!=="independent";
        const cells=[new Date(row.timestamp*1000).toLocaleString(this._lang),this.stateText("operation_mode",s.automation_mode),
          `${value(s.temperature)} / ${value(s.target_temperature)} °C`,s.running===true?this.t("on"):s.running===false?this.t("off"):this.t("missing"),
          s.power_accounting==="estimated"?this.t("missing"):this.watts(s.ac_power),this.watts(s.group_available_power),this.watts(s.group_reserved_power),
          `${value(grouped?s.group_action:s.strategy_action)} / ${value(grouped?s.group_reason:s.strategy_reason)}`,
          `${value(s.group_command_status)} / ${value(s.command_error)}`];
        cells.forEach(cell=>tr.append(el("td",cell)));rows.append(tr);
      }
      table.append(rows);scroll.append(table);body.append(scroll);
    } catch { if (body.isConnected) status.textContent=this.t("failed"); }
  }
  _openDialog(title, description) {
    this._dialog.classList.remove("history");
    this._dialog.replaceChildren();
    const body=el("div",null,"dialog-body");
    const heading=el("div",null,"dialog-head");const h=el("h2",title,"grow");h.id="dialog-title";
    heading.append(h,this.button(this.t("close"),()=>this.closeDialog()));body.append(heading);
    if (description) body.append(el("p",description,"subtle"));
    this._dialog.append(body);if (!this._dialog.open) this._dialog.showModal();return body;
  }
  chooseDevice(step, groupId) {
    const body=this._openDialog(this.t("choose"),this.t("chooseHint"));
    const choices=this._data.devices.filter(d=>!d.group_id && d.loaded);
    if (!choices.length) {body.append(el("p",this.t("noCandidates")));return;}
    const menu=el("div",null,"menu");
    for (const device of choices) {
      const button=this.button(device.name,()=>this.startFlow(device,step,groupId?{group_id:groupId}:{}));
      button.disabled=!!device.edit_block;menu.append(button);
      if (device.edit_block) menu.append(el("p",this.errorText(device.edit_block),"subtle"));
    }
    body.append(menu);
  }
  async startFlow(device, step, prefill={}) {
    if (this._dialogBusy) return;
    this._dialogBusy=true;await this._cancelFlow();
    this._creatingGroup=step==="group_create";
    this._flowDevice=device;
    this._prefill=prefill;this._flowSection=step==="user" || step==="reconfigure"?"config":"options";
    this._flowBase=`config/config_entries/${this._flowSection==="options"?"options/":""}flow`;
    this._openDialog(this.t("loading"));
    try {
      const payload=this._flowSection==="options"?{handler:device.entry_id}:{handler:"solar_climate_manager",...(device?{entry_id:device.entry_id}:{})};
      this._flow=await this._hass.callApi("POST",this._flowBase,payload);
      if (this._flowSection==="options" && this._flow.step_id==="init" &&
          (step.startsWith("group_") || step==="learning_reset")) {
        const input={...formDefaults(this._flow.data_schema || []),
          settings_action:step.startsWith("group_")?"group":step};
        this._flow=await this._hass.callApi("POST",`${this._flowBase}/${this._flow.flow_id}`,input);
      }
      if (this._flow.type==="menu" && step!=="init") {
        const path=step.startsWith("group_") && this._flow.step_id!=="group"?["group",step]:[step];
        for (const next of path) {
          if (this._flow.type!=="menu") break;
          this._flow=await this._hass.callApi("POST",`${this._flowBase}/${this._flow.flow_id}`,{next_step_id:next});
        }
      }
      if (!this.isConnected) { await this._cancelFlow();return; }
      this._renderFlow();
    } catch { this._flowError(this.t("failed")); }
    finally { this._dialogBusy=false; }
  }
  _flowError(message) {
    const body=this._openDialog(this.t("failed"));body.append(el("p",message,"error"));
  }
  _renderFlow() {
    const flow=this._flow;
    if (flow.type==="create_entry" || flow.type==="abort") {
      const success=flow.type==="create_entry" || flow.reason==="reconfigure_successful";
      this._flow=null;
      const body=this._openDialog(success?this.t("saved"):this.t("failed"));
      if (!success) body.append(el("p",this.errorText(flow.reason),"error"));
      body.append(this.button(this.t("finish"),()=>this.closeDialog(),"primary"));
      this._signature=null;this.refresh();return;
    }
    const section=this._labels?.[this._flowSection] || {};
    const labels=section.step?.[flow.step_id] || {};
    const body=this._openDialog(labels.title || this.t("settings"), labels.description);
    if (flow.errors?.base) body.append(el("p",this.errorText(flow.errors.base),"notice error"));
    if (flow.type==="menu") {
      const menu=el("div",null,"menu");
      const choices=Array.isArray(flow.menu_options)?flow.menu_options:Object.keys(flow.menu_options || {});
      for (const step of choices) menu.append(this.button(labels.menu_options?.[step] || step,()=>this.submitFlow({next_step_id:step})));
      if (flow.step_id==="init") menu.append(this.button(this.t("reconfigure"),()=>{
        if(this._flowDevice)this.startFlow(this._flowDevice,"reconfigure");
      }));
      body.append(menu);return;
    }
    if (flow.type!=="form") {body.append(el("p",this.t("failed"),"error"));return;}
    const form=el("form"); let supported=true;
    for (const field of flow.data_schema || []) {
      const result=this.renderField(field,labels,flow.errors || {});
      if (!result) { supported=false;form.append(el("p",this.t("unknownField"),"error")); }
      else form.append(result);
    }
    this._prefill={};
    const actions=el("div",null,"form-actions");
    actions.append(this.button(this.t("cancel"),()=>this.closeDialog()));
    const next=flow.step_id==="group_create" || (flow.step_id==="group_sources" && this._creatingGroup);
    const save=el("button",this.t(next?"next":(flow.data_schema?.length?"save":"confirm")),"primary");save.type="submit";save.disabled=!supported;actions.append(save);form.append(actions);
    form.addEventListener("submit",event=>{event.preventDefault();if(form.reportValidity())this.submitFlow(readForm(flow.data_schema || [],form));});
    body.append(form);
  }
  renderField(field,labels,errors,prefill=this._prefill) {
    if (Array.isArray(field.schema)) {
      const group=el("details");
      group.open=!field.collapsed;
      const sectionLabels=labels.sections?.[field.name] || {};
      group.append(el("summary",sectionLabels.name || field.name));
      const content=el("div");content.style.cssText="display:grid;gap:16px;padding:16px 0";
      if(sectionLabels.description)content.append(el("p",sectionLabels.description,"subtle"));
      for(const child of field.schema) {
        const rendered=this.renderField(child,sectionLabels,errors,prefill);
        if(!rendered)return null;
        content.append(rendered);
      }
      group.append(content);
      return group;
    }
    const kind=fieldKind(field); const selector=field.selector?.[kind] || {};
    if (!["number","text","string","boolean","select","entity"].includes(kind)) return null;
    const label=el("label",null,kind==="boolean"?"check":"");
    const text=labels.data?.[field.name] || field.name;
    const value=prefill?.[field.name] ?? fieldDefault(field);
    let input;
    if (kind==="select") {
      input=el("select");
      if (!field.required) {const blank=el("option","—");blank.value="";input.append(blank);}
      for(const item of selector.options || field.options || []) {
        const val=typeof item==="string"?item:item.value;
        const title=typeof item==="string"?this._labels?.selector?.[selector.translation_key]?.options?.[item] || item:item.label;
        const option=el("option",title);option.value=val;input.append(option);
      }
    } else {
      input=el("input");input.type=kind==="boolean"?"checkbox":kind==="number"?"number":"text";
      if(kind==="number") {for(const key of ["min","max","step"]) if(selector[key]!==undefined) input[key]=selector[key];}
      if(kind==="text" || kind==="string") input.maxLength=255;
      if(kind==="entity") {
        const list=el("datalist");list.id=`entities-${++this._fieldId}`;input.setAttribute("list",list.id);input.placeholder=this.t("chooseEntity");
        let filters=selector.filter || [{domain:selector.domain,device_class:selector.device_class}];if(!Array.isArray(filters))filters=[filters];
        for(const state of Object.values(this._hass.states || {})) {
          if(!filters.some(f=>(!f.domain || (Array.isArray(f.domain)?f.domain:[f.domain]).includes(state.entity_id.split(".")[0])) && (!f.device_class || (Array.isArray(f.device_class)?f.device_class:[f.device_class]).includes(state.attributes.device_class))))continue;
          const option=el("option",state.attributes.friendly_name || state.entity_id);option.value=state.entity_id;list.append(option);
        }
        label.append(list);
      }
    }
    input.name=field.name;input.required=!!field.required && kind!=="boolean";
    if(kind==="boolean")input.checked=!!value;else if(value!==undefined && value!==null)input.value=String(value);
    const caption=el("span",`${text}${field.required?"":` (${this.t("optional")})`}`);
    label.append(caption,input);
    if(errors[field.name])label.append(el("span",this.errorText(errors[field.name]),"field-error error"));
    return label;
  }
  async submitFlow(input) {
    if(this._dialogBusy || !this._flow?.flow_id)return;
    this._dialogBusy=true;
    this._dialog.querySelectorAll("button,input,select").forEach(n=>n.disabled=true);
    try {
      this._flow=await this._hass.callApi("POST",`${this._flowBase}/${this._flow.flow_id}`,input);
      if (!this.isConnected) { await this._cancelFlow();return; }
      this._renderFlow();
    } catch(error) {
      // Do not blindly retry a write after a network failure: it may have committed.
      this._flowError(this.t("sessionLost"));this._signature=null;this.refresh();
    } finally {this._dialogBusy=false;}
  }
  async _cancelFlow() {
    const flow=this._flow;this._flow=null;
    if(flow?.flow_id && !["create_entry","abort"].includes(flow.type)) {
      try {await this._hass.callApi("DELETE",`${this._flowBase}/${flow.flow_id}`);} catch { /* May already be completed. */ }
    }
  }
  async closeDialog() {
    if(this._dialogBusy)return;
    await this._cancelFlow();this._dialog.close();this._signature=null;this.refresh();
  }
}

if (!customElements.get("solar-climate-panel")) customElements.define("solar-climate-panel",SolarClimatePanel);
