/* Native HA panel. No external scripts, build step, or separate server. */
const TEXT = {
  uk: {
    subtitle: "Кондиціонери та спільний енергетичний бюджет", groups: "Енергетичні групи",
    devices: "Пристрої", independent: "Не додані до групи", create: "Створити групу",
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
    noCandidates: "Немає пристроїв для приєднання. Додайте кондиціонер або спочатку виведіть його з іншої групи.",
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
    historyHint: "Останні 12 годин. Хвилинні знімки зберігаються окремо від подій до 24 годин; збір працює із закритою сторінкою. Перезапуск HA або reload очищає історію. Час — локальний для браузера. Рішення не підтверджує команду; увімкнений режим не доводить роботу компресора. JSON містить усю доступну історію.",
    stats12: "Статистика за 12 годин", covered: "Покриття даними", unknown: "Невідомий час", onTime: "Увімкнений режим", offTime: "Вимкнений режим", blockedTime: "Тимчасове блокування", hours: "год", events: "Події та причини", telemetry: "Показники за 12 годин", event: "Подія", externalChange: "Зовнішня зміна (не розпізнана як власна)", stateChange: "Зміна стану / рішення", eventLoss: "Частина подій витіснена лімітом; хвилинні знімки збережено.", ranges: "Мінімум — максимум", pv: "Генерація / прогноз", battery: "Батарея / SOC", grid: "Мережа / імпорт / ліміт", acTemperature: "Температура AC / задана AC", guards: "Дозвіл / потреба / блокування", yes: "Так", no: "Ні",
    historyEmpty: "Історія ще не накопичена.",
    runningCount: "Працюють зараз", unavailableCount: "Недоступні",
  },
  en: {
    subtitle: "Air conditioners and a shared energy budget", groups: "Energy groups",
    devices: "Devices", independent: "Not assigned to a group", create: "Create group", add: "Add air conditioner",
    refresh: "Refresh", settings: "Configure", sources: "Shared sources", policy: "Group policy",
    rename: "Name and priority", join: "Join group", leave: "Leave group", remove: "Delete empty group",
    comfort: "Comfort", energy: "Power accounting", reconfigure: "Change bindings",
    load: "Load", available: "Available power", reserve: "Start reservations", unlimited: "No configured limit",
    missing: "No data", unavailable: "Device unavailable", temperature: "Temperature / target",
    measured: "Measured power", estimated: "Planned power", priority: "Priority",
    noGroups: "Create a group to share one energy budget between air conditioners.",
    noDevices: "Start by adding an air conditioner and its room temperature sensor.",
    noIndependent: "All devices already belong to groups.", noMembers: "This group has no devices yet.",
    noCandidates: "No devices available to join. Add an air conditioner or first remove it from another group.",
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
    historyHint: "Last 12 hours. Minute samples are retained separately from events for up to 24 hours, even with the page closed. HA restart or reload clears history. Times use the browser time zone. Decisions do not confirm commands; on mode does not prove compressor activity. JSON includes all available history.",
    stats12: "12-hour statistics", covered: "Data coverage", unknown: "Unknown time", onTime: "On mode", offTime: "Off mode", blockedTime: "Temporary block", hours: "h", events: "Events and reasons", telemetry: "12-hour readings", event: "Event", externalChange: "External change (not recognized as our own)", stateChange: "State / decision change", eventLoss: "Some events were evicted by the limit; minute samples are retained.", ranges: "Minimum — maximum", pv: "Generation / forecast", battery: "Battery / SOC", grid: "Grid / import / limit", acTemperature: "AC temperature / AC setpoint", guards: "Permission / demand / block", yes: "Yes", no: "No",
    historyEmpty: "No history collected yet.",
    runningCount: "Running now", unavailableCount: "Unavailable",
  },
};

export const fieldDefault = (field) => field.description?.suggested_value ?? field.default;
export const fieldKind = (field) => Object.keys(field.selector || {})[0] || field.type;
export function chartSegments(rows,key,start,end) {
  const result=[];let segment=[];let previous=null;
  for(const row of rows) {
    if(row.timestamp<start || row.timestamp>end)continue;
    const value=row.state?.[key];
    if(!Number.isFinite(value) || previous!==null && row.timestamp-previous>90) {
      if(segment.length)result.push(segment);segment=[];
    }
    if(Number.isFinite(value))segment.push([row.timestamp,value]);
    previous=row.timestamp;
  }
  if(segment.length)result.push(segment);
  return result;
}
export function gridIntervals(rows,start,end) {
  return rows.flatMap((r,i)=>{
    const until=Math.min(end,rows[i+1]?.timestamp ?? end,r.timestamp+90);
    const from=Math.max(start,r.timestamp);
    return typeof r.state?.grid_available==="boolean" && until>from && r.timestamp<=end?
      [{start:from,end:until,available:r.state.grid_available}]:[];
  });
}
export function historySummary(input, now) {
  const start=now-12*3600;
  const all=input.filter(r=>Number.isFinite(r.timestamp) && r.timestamp<=now).slice().sort((a,b)=>a.timestamp-b.timestamp);
  const rows=all.filter(r=>r.timestamp>=start);
  const totals={covered:0,on:0,off:0,blocked:0};
  for(let i=0;i<all.length;i++) {
    const row=all[i], end=all[i+1]?.timestamp ?? now;
    // Never extend a stale observation through a gap in collection.
    if(end-row.timestamp>90)continue;
    const seconds=Math.max(0,end-Math.max(start,row.timestamp));
    totals.covered+=seconds;
    if(row.state.running===true)totals.on+=seconds;
    if(row.state.running===false)totals.off+=seconds;
    if(row.state.automation_mode==="temporary_block")totals.blocked+=seconds;
  }
  return {start,rows,totals,unknown:12*3600-totals.covered};
}
const SHARED_SECTIONS = {
  grid: ["grid_available_entity", "grid_on_means_available", "grid_power_entity", "grid_positive", "grid_import_limit_entity", "grid_absence_delay"],
  battery: ["soc_entity", "minimum_soc", "restart_soc", "battery_power_entity", "battery_positive"],
  solar: ["pv_power_entity", "generation_forecast_entity"],
  consumption: ["load_power_entity", "load_scope", "load_includes_battery_charging"],
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
  .dashboard-tabs { display:flex; gap:8px; border-bottom:1px solid var(--divider-color,#dce5df); margin-bottom:24px; padding-bottom:10px; }
  .dashboard-tabs [aria-selected=true],.periods [aria-pressed=true] { color:var(--primary-color,#03a9f4); border-color:var(--primary-color,#03a9f4); }
  .energy-tiles { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; margin:18px 0; }
  .energy-tile,.chart-card,.dashboard-devices>.device { border:1px solid var(--divider-color,#dce5df); border-radius:12px; padding:16px; min-width:0; background:var(--card-background-color,#fff); }
  .energy-tile strong { display:block; font-size:25px; margin:12px 0 8px; }
  .tile-label { font-size:14px; display:flex; align-items:center; gap:8px; }.tile-label ha-icon { width:22px; height:22px; }
  .dashboard-charts { display:grid; grid-template-columns:1.4fr 1fr; gap:16px; margin-bottom:22px; }
  .dashboard-devices { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; margin-top:16px; }
  .dashboard-devices .values strong { font-size:24px; }.dashboard-devices .reason { padding:10px; background:var(--secondary-background-color,#eff5f1); border-radius:8px; }
  .dashboard-group { margin-bottom:32px; }.periods { display:flex; gap:4px; flex-wrap:wrap; }
  .chart { width:100%; display:block; color:var(--secondary-text-color,#61756b); touch-action:pan-y; }
  .chart-legend { display:flex; flex-wrap:wrap; gap:14px; font-size:12px; margin:12px 0 4px; }.chart-legend span { display:flex; align-items:center; gap:6px; }
  .chart-legend i { width:18px; height:0; border-top:3px solid; }.chart-readout { min-height:36px; font-size:12px; color:var(--secondary-text-color,#61756b); }
  .target-stepper { display:flex; align-items:center; gap:8px; }.target-stepper button { min-width:40px; }.target-stepper strong { min-width:64px; text-align:center; }
  .dashboard-devices .actions { margin-top:12px; }.dashboard-devices .mode { min-width:0; max-width:100%; }
  .grid-key { display:flex; gap:12px; font-size:12px; flex-wrap:wrap; }.grid-key span { padding-left:8px; border-left:8px solid; }
  main { max-width:1600px !important; }
  @media(max-width:1100px) { .energy-tiles { grid-template-columns:repeat(3,minmax(0,1fr)); }.dashboard-charts { grid-template-columns:1fr; } }
  @media(max-width:700px) { .energy-tiles { grid-template-columns:repeat(2,minmax(0,1fr)); }.dashboard-devices { grid-template-columns:1fr; }.energy-tile strong { font-size:22px; }.dashboard-tabs button { padding:9px; }.dashboard-group>.heading { align-items:flex-start; }.chart-card { padding:10px; }.dashboard-devices .values { gap:8px; }.dashboard-devices .values strong { font-size:20px; } }
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
  .history-events pre { white-space:pre-wrap; overflow-wrap:anywhere; } .history-stats .metric { overflow-wrap:anywhere; }
  @media(max-width:700px) { .history-stats .metrics { grid-template-columns:1fr 1fr; } }
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
    this._analysisOpen = new Set();
    this._tab="overview";this._hours=12;this._charts=null;this._chartFetched=0;this._quickBusy=false;
    this._fieldId = 0;
    this._visibility = () => { if (!document.hidden) this.refresh(); };
  }
  set hass(value) {
    const changed = this._hass?.connection !== value.connection;
    this._hass = value;
    const lang = value.language?.startsWith("uk") ? "uk" : "en";
    if (lang !== this._lang) { this._lang = lang; this._labels = null; this._signature = null; }
    this.updateEntityValues();
    if (this.isConnected && (changed || !this._data || !this._labels)) this.refresh();
  }
  get hass() { return this._hass; }
  updateEntityValues() {
    for (const input of this.shadowRoot.querySelectorAll("input[data-entity-preview]")) {
      this.updateEntityValue(input);
    }
  }
  updateEntityValue(input) {
    const preview = input.parentElement.querySelector(".entity-value");
    if (!preview) return;
    const id = input.value.trim();
    const state = this._hass.states?.[id];
    preview.hidden = !id;
    const uk = this._lang === "uk";
    let value = !state ? (uk ? "Об’єкт не знайдено" : "Entity not found") :
      state.state === "unavailable" ? (uk ? "Недоступно" : "Unavailable") :
      state.state === "unknown" || state.state == null ? (uk ? "Невідомо" : "Unknown") :
      `${state.state}${state.attributes.unit_of_measurement ? ` ${state.attributes.unit_of_measurement}` : ""}`;
    preview.textContent = `${uk ? "Поточне значення" : "Current value"}: ${value}`;
  }
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
      if(Date.now()-this._chartFetched>60000 || !this._charts) {
        try {
          this._charts=await this._hass.callWS({type:"solar_climate_manager/dashboard"});
          this._chartError=false;this._signature=null;
        } catch {this._chartError=true;this._signature=null;}
        this._chartFetched=Date.now();
      }
      if(!this.isConnected)return;
      this._status.textContent=data.error ? this.errorText(data.error) : "";
      const signature=JSON.stringify(data);
      const focused=this.shadowRoot.activeElement;
      if (signature !== this._signature && !this._quickBusy && !this._inlineEditors.size && !["INPUT","SELECT"].includes(focused?.tagName)) {
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
    actions.append(create,this.button(this.t("add"),()=>this.startFlow(null,"user")),this.button(this.t("refresh"),()=>{this._signature=null;this._chartFetched=0;this.refresh();}));
    toolbar.append(stats,actions); content.append(toolbar);
    const tabs=el("nav",null,"dashboard-tabs");tabs.setAttribute("role","tablist");
    for(const [id,uk,en] of [["overview","Огляд","Overview"],["analysis","Аналітика","Analytics"],["settings","Налаштування","Settings"]]) {
      const button=this.button(this._lang==="uk"?uk:en,()=>this.selectTab(id));
      button.setAttribute("role","tab");button.setAttribute("aria-selected",String(this._tab===id));tabs.append(button);
    }
    content.append(tabs);
    content.append(el("p",this.t("preview"),"subtle"));
    if (!data.devices.length) content.append(el("div",this.t("noDevices"),"empty"));
    if (!data.groups.length) content.append(el("div",this.t("noGroups"),"empty"));
    for (const group of data.groups) content.append(this._tab==="settings"?this.groupCard(group):this.dashboardGroup(group));
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
  selectTab(tab,deviceId=null) {
    if(this._inlineEditors.size || this._quickBusy) {
      this._notice.textContent=this._lang==="uk"?"Спочатку збережіть або закрийте відкриті налаштування.":"Save or close the open settings first.";return;
    }
    this._tab=tab;this._renderOverview();
    if(deviceId)Array.from(this.shadowRoot.querySelectorAll("[data-device-id]")).find(n=>n.dataset.deviceId===deviceId)?.scrollIntoView({block:"start"});
  }
  temperature(value) {return Number.isFinite(value)?`${value.toLocaleString(this._lang,{minimumFractionDigits:1,maximumFractionDigits:1})} °C`:this.t("missing");}
  dashboardGroup(group) {
    const uk=this._lang==="uk",card=el("section",null,"dashboard-group");
    const heading=el("div",null,"heading");heading.append(el("h2",group.name));
    const periods=el("div",null,"periods");
    for(const hours of [1,6,12,24]) {
      const button=this.button(`${hours} ${uk?"год":"h"}`,()=>{this._hours=hours;this._renderOverview();});
      button.setAttribute("aria-pressed",String(this._hours===hours));periods.append(button);
    }
    heading.append(periods);card.append(heading);
    const tiles=el("div",null,"energy-tiles");
    const grid=group.grid_available===true?(uk?"Є живлення":"Connected"):group.grid_available===false?(uk?"Немає мережі":"Disconnected"):this.t("missing");
    const battery=Number.isFinite(group.battery_power)?`${group.battery_power<0?(uk?"Заряджання":"Charging"):(uk?"Розряджання":"Discharging")} ${this.watts(Math.abs(group.battery_power))}`:this.t("missing");
    const items=[
      ["mdi:white-balance-sunny",uk?"Сонячна генерація":"Solar generation",this.watts(group.pv_power),`${uk?"Прогноз зараз":"Forecast now"}: ${this.watts(group.generation_forecast)}`,"#e9b331"],
      ["mdi:home-lightning-bolt",uk?"Навантаження групи":"Group load",this.watts(group.load_power),this.t("availableHint"),"#03a9f4"],
      ["mdi:battery",uk?"Батарея":"Battery",Number.isFinite(group.soc)?`${group.soc} %`:this.t("missing"),battery,"#48b979"],
      ["mdi:transmission-tower",uk?"Мережа":"Grid",grid,`${uk?"Імпорт (+) / експорт (−)":"Import (+) / export (−)"}: ${this.watts(group.grid_power)} · ${uk?"Ліміт":"Limit"}: ${group.unlimited?this.t("unlimited"):this.watts(group.grid_import_limit)}`,"#48b979"],
      ["mdi:lightning-bolt",uk?"Доступно групі":"Group headroom",group.unlimited?this.t("unlimited"):this.watts(group.available_power),`${this.t("reserve")}: ${this.watts(group.reserved_power)}`,"#03a9f4"],
    ];
    for(const [icon,title,value,note,color] of items) {
      const tile=el("div",null,"energy-tile"),label=el("div",null,"tile-label"),symbol=el("ha-icon");symbol.setAttribute("icon",icon);label.style.color=color;label.append(symbol,el("span",title));
      tile.append(label,el("strong",value),el("div",note,"subtle"));tiles.append(tile);
    }
    card.append(tiles);
    const rows=this._charts?.groups?.[group.group_id] || [];
    const charts=el("div",null,"dashboard-charts");
    charts.append(this.lineChart(uk?"Генерація та споживання":"Generation and consumption",rows,[["pv_power",uk?"Сонце":"Solar","#e9b331"],["generation_forecast",uk?"Прогноз":"Forecast","#f39a39",true],["load_power",uk?"Будинок":"House","#03a9f4"]],"kW",.001));
    const batteryCard=this.lineChart(uk?"Батарея та мережа":"Battery and grid",rows,[["soc",uk?"Заряд батареї":"Battery charge","#48b979"]],"%");
    batteryCard.append(this.gridChart(rows));charts.append(batteryCard);card.append(charts);
    if(this._chartError)card.append(el("p",uk?"Не вдалося оновити графіки. Попередні дані можуть бути застарілими.":"Charts could not refresh. Previous data may be stale.","error"));
    card.append(el("p",uk?"Історія до 24 год; після перезапуску HA або reload збирається заново. Розриви означають відсутність даних.":"Up to 24h of history; collection restarts after HA restart or reload. Gaps indicate missing data.","subtle"));
    card.append(el("h3",this.t("devices")));
    const members=el("div",null,"dashboard-devices");
    for(const member of group.members) {
      const device=this._data.devices.find(d=>d.device_id===member.device_id);
      members.append(device?this.dashboardDevice(device):el("div",this.t("unavailable"),"device"));
    }
    if(!group.members.length)members.append(el("p",this.t("noMembers")));
    card.append(members);return card;
  }
  chartWindow() {
    const end=this._charts?.generated_at || Date.now()/1000;
    return {start:end-this._hours*3600,end};
  }
  svgNode(tag,attrs={},text=null) {
    const node=document.createElementNS("http://www.w3.org/2000/svg",tag);
    for(const [k,v] of Object.entries(attrs))node.setAttribute(k,String(v));
    if(text!==null)node.textContent=text;return node;
  }
  lineChart(title,rows,fields,unit,scale=1) {
    const card=el("section",null,"chart-card");card.append(el("h3",title));
    const {start,end}=this.chartWindow(),legend=el("div",null,"chart-legend");
    const series=fields.map(([key,label,color,dashed])=>{
      const item=el("span"),line=el("i");line.style.borderColor=color;if(dashed)line.style.borderTopStyle="dashed";item.append(line,el("span",label));legend.append(item);
      return {key,color,dashed,segments:chartSegments(rows,key,start,end)};
    });
    card.append(legend);
    const values=series.flatMap(s=>s.segments.flatMap(segment=>segment.map(p=>p[1]*scale)));
    if(!values.length) {card.append(el("p",this.t("historyEmpty"),"empty"));return card;}
    let min=unit==="kW"?0:Math.floor(Math.min(...values)-1),max=Math.ceil(Math.max(...values)+(unit==="kW"?.2:1));
    if(unit==="%") {min=Math.max(0,min);max=Math.min(100,max);}if(max<=min)max=min+1;
    const x=t=>48+(t-start)/(end-start)*652,y=v=>180-(v*scale-min)/(max-min)*152;
    const svg=this.svgNode("svg",{viewBox:"0 0 720 220",class:"chart",role:"img","aria-label":title});
    for(let i=0;i<=4;i++) {
      const py=28+i*38,value=max-(max-min)*i/4;
      svg.append(this.svgNode("line",{x1:48,x2:700,y1:py,y2:py,stroke:"currentColor",opacity:.18}),this.svgNode("text",{x:43,y:py+4,"text-anchor":"end",fill:"currentColor","font-size":12},value.toLocaleString(this._lang,{maximumFractionDigits:1})));
    }
    for(let i=0;i<=4;i++) {
      const time=start+(end-start)*i/4,px=x(time);
      svg.append(this.svgNode("line",{x1:px,x2:px,y1:28,y2:180,stroke:"currentColor",opacity:.1}),this.svgNode("text",{x:px,y:205,"text-anchor":i===0?"start":i===4?"end":"middle",fill:"currentColor","font-size":12},new Date(time*1000).toLocaleTimeString(this._lang,{hour:"2-digit",minute:"2-digit"})));
    }
    svg.append(this.svgNode("text",{x:5,y:14,fill:"currentColor","font-size":12},unit));
    for(const s of series)for(const segment of s.segments) {
      if(segment.length===1)svg.append(this.svgNode("circle",{cx:x(segment[0][0]),cy:y(segment[0][1]),r:3,fill:s.color}));
      else svg.append(this.svgNode("path",{d:segment.map(([t,v],i)=>`${i?"L":"M"}${x(t).toFixed(1)},${y(v).toFixed(1)}`).join(" "),stroke:s.color,"stroke-width":2.5,fill:"none","stroke-dasharray":s.dashed?"7 5":"none"}));
    }
    const readout=el("div",`${this._hours} ${this.t("hours")} · ${this.t("lastUpdate")}: ${new Date(end*1000).toLocaleTimeString(this._lang)}`,"chart-readout");
    svg.addEventListener("pointermove",event=>{
      const box=svg.getBoundingClientRect(),time=start+(((event.clientX-box.left)/box.width*720-48)/652)*(end-start);
      const row=rows.reduce((best,r)=>r.timestamp>=start && r.timestamp<=end && (!best || Math.abs(r.timestamp-time)<Math.abs(best.timestamp-time))?r:best,null);
      if(!row || Math.abs(row.timestamp-time)>90){readout.textContent=this.t("missing");return;}
      readout.textContent=`${new Date(row.timestamp*1000).toLocaleTimeString(this._lang)} · `+fields.map(([key,label])=>`${label}: ${Number.isFinite(row.state[key])?(row.state[key]*scale).toLocaleString(this._lang,{maximumFractionDigits:2})+" "+unit:this.t("missing")}`).join(" · ");
    });
    card.append(svg,readout);return card;
  }
  gridChart(rows) {
    const {start,end}=this.chartWindow(),box=el("div"),uk=this._lang==="uk";
    const svg=this.svgNode("svg",{viewBox:"0 0 720 24",class:"chart",role:"img","aria-label":uk?"Історія наявності мережі":"Grid availability history"});
    svg.append(this.svgNode("rect",{x:48,y:4,width:652,height:14,fill:"var(--divider-color,#777)"}));
    for(const interval of gridIntervals(rows,start,end))svg.append(this.svgNode("rect",{x:48+(interval.start-start)/(end-start)*652,y:4,width:(interval.end-interval.start)/(end-start)*652,height:14,fill:interval.available?"#48b979":"#e9b331"}));
    const key=el("div",null,"grid-key");
    for(const [text,color] of [[uk?"Є мережа":"Connected","#48b979"],[uk?"Відсутня":"Disconnected","#e9b331"],[this.t("missing"),"#777"]]){const item=el("span",text);item.style.borderColor=color;key.append(item);}
    box.append(svg,key);return box;
  }
  dashboardDevice(device) {
    const uk=this._lang==="uk",card=el("article",null,"device");card.dataset.deviceId=device.device_id;
    const top=el("div",null,"device-top"),title=el("div",null,"grow");title.append(el("h3",device.name));
    const state=!device.loaded?this.t("unavailable"):device.hvac_state==="heat"?(uk?"Нагрівання":"Heating"):device.hvac_state==="cool"?(uk?"Охолодження":"Cooling"):device.running===false?this.t("off"):this.t("missing");
    top.append(title,el("span",state,"badge"));card.append(top);
    const analysis=device.power_analysis,measured=Number.isFinite(device.measured_power),estimated=device.running && Number.isFinite(analysis?.watts);
    const power=measured?this.watts(device.measured_power):device.running===false?this.t("off"):this.watts(estimated?analysis.watts:device.planned_power);
    const values=el("div",null,"values");
    for(const [label,value] of [[uk?"У кімнаті":"Room",this.temperature(device.temperature)],[uk?"Задано":"Target",this.temperature(device.target)],[measured?this.t("measured"):estimated?(uk?"Потужність · оцінка":"Power · estimate"):this.t("estimated"),power]]){const item=el("div");item.append(el("div",label,"subtle"),el("strong",value));values.append(item);}
    card.append(values,el("p",`${uk?"Датчик AC":"AC sensor"}: ${this.temperature(device.ac_temperature)} → ${uk?"уставка AC":"AC setpoint"}: ${this.temperature(device.ac_set_temperature)}`,"subtle"));
    card.append(this.lineChart(uk?"Температура кімнати":"Room temperature",this._charts?.devices?.[device.entry_id] || [],[["temperature",uk?"Кімната":"Room","#03a9f4"],["target_temperature",uk?"Задана":"Target","#e9b331",true]],"°C"));
    card.append(el("p",`${this.stateText("group_action",device.action)} · ${this.stateText("group_reason",device.reason)}`,"reason"));
    const actions=el("div",null,"actions"),mode=el("select",null,"mode");mode.setAttribute("aria-label",`${this.t("mode")}: ${device.name}`);
    for(const value of ["disabled","observation","control","temporary_block"]){const o=el("option",this.stateText("operation_mode",value));o.value=value;mode.append(o);}mode.value=device.mode;mode.disabled=!device.loaded || !device.mode_entity;
    mode.addEventListener("change",async()=>{mode.disabled=true;try{await this._hass.callService("select","select_option",{entity_id:device.mode_entity,option:mode.value});}catch{this._notice.textContent=this.t("failed");}finally{mode.blur();this._signature=null;await this.refresh();}});
    const target=el("div",null,"target-stepper");
    const down=this.button("−",()=>this.quickTarget(device,-1)),up=this.button("+",()=>this.quickTarget(device,1));
    down.setAttribute("aria-label",uk?"Зменшити цільову температуру":"Decrease target temperature");up.setAttribute("aria-label",uk?"Збільшити цільову температуру":"Increase target temperature");down.disabled=up.disabled=!device.loaded || !!device.edit_block || this._quickBusy;
    target.append(down,el("strong",this.temperature(device.target)),up);actions.append(mode,target,el("span",`${uk?"Вентилятор":"Fan"}: ${device.fan_mode || "—"}`,"badge"));
    actions.append(this.button(this.t("settings"),()=>this.selectTab("settings",device.device_id)));
    const history=this.button(this.t("history"),()=>this.showHistory(device));history.disabled=!device.loaded;actions.append(history);card.append(actions);
    if(device.command_status && device.command_status!=="idle")card.append(el("p",this.stateText("group_command_status",device.command_status),"subtle"));
    if(this._tab==="analysis" && analysis) {const details=this.analysisCard(analysis,device.device_id);details.open=true;card.append(details);}else card.append(this.button(uk?"Аналіз потужності":"Power analysis",()=>this.selectTab("analysis",device.device_id)));
    return card;
  }
  async quickTarget(device,direction) {
    if(this._quickBusy || this._inlineEditors.size || device.edit_block)return;
    this._quickBusy=true;this._renderOverview();
    const base="config/config_entries/options/flow";let flow=null;
    try {
      flow=await this._hass.callApi("POST",base,{handler:device.entry_id});
      const input=formDefaults(flow.data_schema || []),comfort=flow.data_schema?.find(f=>f.name==="comfort");
      const field=comfort?.schema?.find(f=>f.name==="target_temperature"),spec=field?.selector?.number;
      if(!spec || !Number.isFinite(input.comfort?.target_temperature))throw Error("unsupported");
      const value=Number((input.comfort.target_temperature+direction*(spec.step || .5)).toFixed(2));
      if(spec.min!==undefined && value<spec.min || spec.max!==undefined && value>spec.max)throw Error("bounds");
      input.comfort.target_temperature=value;
      const result=await this._hass.callApi("POST",`${base}/${flow.flow_id}`,input);
      if(result.type!=="create_entry")throw Error(result.errors?.base || result.reason || "failed");
      flow=null;this._notice.textContent=this.t("saved");
    } catch {this._notice.textContent=this.t("failed");}
    finally {
      if(flow?.flow_id)try{await this._hass.callApi("DELETE",`${base}/${flow.flow_id}`);}catch{ /* best-effort cancellation */ }
      this._quickBusy=false;this._signature=null;await this.refresh();this._renderOverview();
    }
  }
  groupCard(group) {
    const card=el("section",null,"group");
    const heading=el("div",null,"heading");
    heading.append(el("h2",group.name),el("span",`${group.members.length} · ${this.t("devices")}`,"badge"));
    card.append(heading);
    if(group.background_analysis) {
      const background=group.background_analysis;
      card.append(el("p",`${this._lang==="uk"?"Фон будинку при вимкнених кондиціонерах (медіана доступних даних за 24 год)":"House background with ACs off (median of available 24h data)"}: ${this.watts(background.watts)} · ${background.samples}`,"subtle"));
    }
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
    card.dataset.deviceId=device.device_id;
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
    if(device.power_analysis)card.append(this.analysisCard(device.power_analysis,device.device_id));
    if (device.learning?.enabled) {
      const learned=device.learning;
      card.append(el("p",`${this.t(learned.source)} · ${this.t(learned.confidence)} · ${this.t("samples")}: ${learned.samples}`,"subtle"));
      const status=this._labels?.selector?.learning_status?.options?.[learned.status] || learned.status;
      card.append(el("p",`${this.t("learning")}: ${status}${learned.learned_watts===null?"":` · ${this.watts(learned.learned_watts)}`}`,"subtle"));
    }
    const action=this.stateText("group_action",device.action);
    const reason=this.stateText("group_reason",device.reason);
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
    if (device.loaded) for (const name of ["comfort","consumption"]) {
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
      const summary=historySummary(result.rows,result.generated_at);
      const card=el("section",null,"group history-stats");card.append(el("h3",this.t("stats12")));
      card.append(el("p",`${new Date(summary.start*1000).toLocaleString(this._lang)} — ${new Date(result.generated_at*1000).toLocaleString(this._lang)}`,"subtle"));
      const metrics=el("div",null,"metrics");
      for(const [key,seconds] of [["covered",summary.totals.covered],["unknown",summary.unknown],["onTime",summary.totals.on],["offTime",summary.totals.off],["blockedTime",summary.totals.blocked]]) {
        const metric=el("div",this.t(key),"metric");metric.append(el("strong",`${(seconds/3600).toFixed(2)} ${this.t("hours")}`));metrics.append(metric);
      }
      card.append(metrics);body.append(card);
      if(result.events_dropped_through>=summary.start)card.append(el("p",this.t("eventLoss"),"error"));
      if (!summary.rows.length) { body.append(el("p",this.t("historyEmpty")));return; }
      const chart=(title,fields,unit)=>{
        const section=el("section",null,"group");section.append(el("h4",this.t(title)));
        const ns="http://www.w3.org/2000/svg", svg=document.createElementNS(ns,"svg");
        svg.setAttribute("viewBox","0 0 800 160");svg.setAttribute("role","img");svg.setAttribute("aria-label",this.t(title));svg.style.width="100%";
        const values=summary.rows.flatMap(r=>fields.map(([key])=>r.state[key])).filter(v=>typeof v==="number" && Number.isFinite(v));
        const low=Math.min(...values), high=Math.max(...values), span=high-low || 1;
        const legend=el("p",null,"subtle");
        fields.forEach(([key,label],index)=>{
          const color=["#277dba","#cf6825","#208c60"][index];
          const series=summary.rows.map(r=>r.state[key]).filter(v=>typeof v==="number" && Number.isFinite(v));
          const item=el("span",`${label}: ${series.length?`${Math.min(...series).toFixed(1)} — ${Math.max(...series).toFixed(1)} ${unit}`:this.t("missing")} · `);item.style.color=color;legend.append(item);
          let points=[],previous=null;
          const flush=()=>{if(points.length){const line=document.createElementNS(ns,"polyline");line.setAttribute("points",points.join(" "));line.setAttribute("fill","none");line.setAttribute("stroke",color);line.setAttribute("stroke-width","2");svg.append(line);}points=[];};
          for(const row of summary.rows){
            const v=row.state[key];
            if(typeof v!=="number" || !Number.isFinite(v)){flush();previous=null;continue;}
            if(previous!==null && row.timestamp-previous>90)flush();
            points.push(`${20+(row.timestamp-summary.start)/43200*760},${130-(v-low)/span*110}`);previous=row.timestamp;
          }flush();
        });
        for(const [x,time] of [[20,summary.start],[780,result.generated_at]]) {const label=document.createElementNS(ns,"text");label.setAttribute("x",String(x));label.setAttribute("y","155");label.setAttribute("text-anchor",x===20?"start":"end");label.setAttribute("fill","currentColor");label.textContent=new Date(time*1000).toLocaleTimeString(this._lang);svg.append(label);}
        section.append(el("p",this.t("ranges"),"subtle"),legend,svg);body.append(section);
      };
      chart("temperature",[["temperature",this.t("temperature")],["target_temperature",this.t("comfort")]],"°C");
      chart("pv",[["pv_power","PV"],["generation_forecast",this.t("pv")],["load_power",this.t("load")]],"W");
      chart("battery",[["soc","SOC"]],"%");
      const eventSection=el("details",null,"group history-events");eventSection.open=true;
      const events=summary.rows.filter(row=>row.kind==="event");eventSection.append(el("summary",`${this.t("events")} (${events.length})`));
      const eventScroll=el("div",null,"history-scroll");
      for(const row of events.slice().reverse()) {
        const s=row.state, external=row.event?.type==="external_change";
        const grouped=s.group_action && s.group_action!=="independent";
        const text=`${new Date(row.timestamp*1000).toLocaleString(this._lang)} · ${this.t(external?"externalChange":"stateChange")} · ${this.stateText("operation_mode",s.automation_mode)} · ${s.running===true?this.t("on"):s.running===false?this.t("off"):this.t("missing")} · ${this.stateText(grouped?"group_reason":"strategy_reason",grouped?s.group_reason:s.strategy_reason)} · ${this.stateText("group_command_status",s.group_command_status)} / ${this.stateText("command_error",s.command_error)}`;
        eventScroll.append(el("p",text));
        if(external)eventScroll.append(el("pre",JSON.stringify(row.event.changes,null,2)));
      }eventSection.append(eventScroll);body.append(eventSection);
      body.append(el("h3",this.t("telemetry")));
      const scroll=el("div",null,"history-scroll");scroll.tabIndex=0;
      const table=el("table");const head=el("thead");const titles=el("tr");
      for (const key of ["time","mode","temperature","acTemperature","actual","measured","pv","load","grid","battery","available","reserve","guards","decision","command"]) {
        const th=el("th",this.t(key));th.scope="col";titles.append(th);
      }
      head.append(titles);table.append(head);const rows=el("tbody");
      const value=v=>v===null || v===undefined?this.t("missing"):String(v);
      const flag=v=>v===true?this.t("yes"):v===false?this.t("no"):this.t("missing");
      for (const row of summary.rows.slice().reverse()) {
        const s=row.state;const tr=el("tr");
        if (s.command_failed || s.group_command_status==="failed" || s.invalid_data || s.energy_data_invalid) tr.className="error";
        const grouped=s.group_action && s.group_action!=="independent";
        const cells=[new Date(row.timestamp*1000).toLocaleString(this._lang),this.stateText("operation_mode",s.automation_mode),
          `${value(s.temperature)} / ${value(s.target_temperature)} °C`,`${value(s.ac_temperature)} / ${value(s.ac_set_temperature)} °C`,s.running===true?this.t("on"):s.running===false?this.t("off"):this.t("missing"),
          s.effective_power_accounting==="estimated"?this.t("missing"):this.watts(s.ac_power),
          `${this.watts(s.pv_power)} / ${this.watts(s.generation_forecast)}`,this.watts(s.load_power),
          `${flag(s.grid_available)} / ${this.watts(s.grid_power)} / ${this.watts(s.grid_import_limit)}`,
          `${this.watts(s.battery_power)} / ${value(s.soc)} %`,this.watts(s.group_available_power),this.watts(s.group_reserved_power),
          `${flag(s.control_allowed)} / ${flag(s.demand)} / ${flag(s.manual_pause)}`,
          `${this.stateText(grouped?"group_action":"strategy_action",grouped?s.group_action:s.strategy_action)} / ${this.stateText(grouped?"group_reason":"strategy_reason",grouped?s.group_reason:s.strategy_reason)}`,
          `${this.stateText("group_command_status",s.group_command_status)} / ${this.stateText("command_error",s.command_error)}`];
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
    if(kind==="entity") {
      const preview=el("span",null,"entity-value subtle");
      preview.id=`entity-value-${++this._fieldId}`;
      preview.setAttribute("aria-live","polite");
      input.dataset.entityPreview="";
      input.setAttribute("aria-describedby",preview.id);
      label.append(preview);
      input.addEventListener("input",()=>this.updateEntityValue(input));
      input.addEventListener("change",()=>this.updateEntityValue(input));
      this.updateEntityValue(input);
    }
    if(errors[field.name])label.append(el("span",this.errorText(errors[field.name]),"field-error error"));
    return label;
  }
  analysisCard(analysis,deviceId) {
    const uk=this._lang==="uk";
    const card=el("details",null,"power-analysis");
    card.open=this._analysisOpen.has(deviceId);
    card.addEventListener("toggle",()=>{if(card.isConnected){if(card.open)this._analysisOpen.add(deviceId);else this._analysisOpen.delete(deviceId);}});
    card.append(el("summary",uk?"Аналіз потужності":"Power analysis"));
    const statuses={
      waiting_background:["Потрібен стабільний фон перед запуском","Waiting for a stable off baseline"],
      ready:["Фон зібрано; очікування циклу","Baseline ready; waiting for a cycle"],
      checking_background:["Перевірка фону після вимкнення","Checking the off baseline"],
      collecting:["Збір профілю; очікування завершення циклу","Collecting; waiting for cycle completion"],
      settling:["Стабілізація після зміни режиму","Settling after a setting change"],
      multiple_running:["Кілька кондиціонерів працюють: внески неоднозначні","Multiple ACs running: contributions are ambiguous"],
      invalid_data:["Недостатньо актуальних даних","Missing or stale data"],
      data_gap:["Перерва в даних; потрібен новий цикл","Data gap; a new cycle is needed"],
      background_changed:["Цикл відхилено: змінився фон будинку","Cycle rejected: house background changed"],
      overlapping_cycle:["Цикл відхилено: перекриття запусків","Cycle rejected: overlapping starts"],
      cycle_too_long:["Цикл понад 6 годин не використано","Cycle longer than 6 hours excluded"],
      unsupported_load:["Потрібне навантаження, що включає всі кондиціонери","Load must include every AC"],
      storage_error:["Сховище аналізу недоступне","Analysis storage unavailable"],
      analysis_error:["Помилка аналізу; керування працює незалежно","Analysis error; control operates independently"],
    };
    card.append(el("p",uk?"Лише аналіз — не впливає на керування. Оцінка за лічильником будинку, не окреме вимірювання кондиціонера.":"Analysis only — does not affect control. Estimated from the house meter, not a dedicated AC measurement.","subtle"));
    card.append(el("p",statuses[analysis.status]?.[uk?0:1] || analysis.status));
    const confidence={insufficient:uk?"Недостатньо даних":"Insufficient data",low:uk?"Низька":"Low",moderate:uk?"Помірна":"Moderate"};
    card.append(el("p",`${uk?"Оцінка для поточних умов":"Estimate for current conditions"}: ${this.watts(analysis.watts)} · ${uk?"Якість":"Quality"}: ${confidence[analysis.confidence] || analysis.confidence}`));
    if(Number.isFinite(analysis.low))card.append(el("p",`${uk?"Діапазон спостережень (10–90%), не гарантія":"Observed range (10–90%), not a guarantee"}: ${this.watts(analysis.low)} – ${this.watts(analysis.high)}`));
    card.append(el("p",`${uk?"Відповідних циклів / усього":"Matching / total cycles"}: ${analysis.matching_cycles} / ${analysis.cycles} · ${uk?"Відхилених циклів групи":"Rejected group cycles"}: ${analysis.rejected_cycles}`));
    if(analysis.updated_at)card.append(el("p",`${this.t("lastUpdate")}: ${new Date(analysis.updated_at*1000).toLocaleString(this._lang)}`,"subtle"));
    const conditions=analysis.conditions;
    if(conditions)card.append(el("p",`${conditions.mode} · ${conditions.indoor} → ${conditions.target} °C · ${conditions.fan} · ${conditions.phase==="startup"?(uk?"Після запуску":"After startup"):(uk?"Усталена робота":"Steady operation")}`));
    if(analysis.profiles?.length) {
      const scroll=el("div",null,"history-scroll");
      const table=el("table");const head=el("tr");
      for(const title of uk?["Час","Режим / вентилятор","Температура AC → уставка","Зовні","Фаза","Оцінка"]:["Time","Mode / fan","AC temperature → setpoint","Outside","Phase","Estimate"])head.append(el("th",title));
      const thead=el("thead");thead.append(head);table.append(thead);
      const body=el("tbody");
      for(const row of analysis.profiles.slice(-50).reverse()) {
        const c=row.conditions;const tr=el("tr");
        for(const value of [new Date(row.time*1000).toLocaleString(this._lang),`${c.mode} / ${c.fan}`,`${c.indoor} → ${c.target} °C`,c.outdoor===null?"—":`${c.outdoor} °C`,c.phase==="startup"?(uk?"Запуск":"Startup"):(uk?"Усталена":"Steady"),this.watts(row.watts)])tr.append(el("td",value));
        body.append(tr);
      }
      table.append(body);scroll.append(table);card.append(scroll);
    }
    return card;
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
