/*
 * Gas Renew card, served and auto-loaded by the gas_renew integration.
 *
 *   type: custom:gas-renew-card
 *   entity: sensor.kitchen_lpg_level   # the Level sensor
 *   name: Kitchen LPG                  # optional, defaults to the device name
 *   confirm_renew: true                # optional, ask before renewing
 */
const CARD_VERSION = "1.1.0";

const TEXT = {
  en: {
    renewed: "The gas tank has been renewed today. Awesome!",
    good: (d, date) =>
      `Looking good so far. It's been ${d} ${d === 1 ? "day" : "days"} since last change on ${date}.`,
    warn: (lvl) =>
      `You really need to consider checking your spare tank now. Current tank is probably <b>${lvl}</b>.`,
    left: (kg, size) => `about ${kg} kg left of ${size} kg`,
    day: (d, n) => `Day ${d} of ${n}`,
    empty: "Empty around",
    last: "Last change",
    renew: "Renew",
    confirm: "Mark a new cylinder as fitted today?",
    levels: { full: "Full", medium: "Medium", low: "Low", critical: "Critical" },
    missing: "Pick the Level sensor of a Gas Renew cylinder.",
  },
  ms: {
    renewed: "Tong gas telah ditukar hari ini. Syabas!",
    good: (d, date) => `Setakat ini baik. Sudah ${d} hari sejak tong ditukar pada ${date}.`,
    warn: (lvl) =>
      `Anda perlu semak tong gas simpanan sekarang. Tong semasa mungkin sudah <b>${lvl}</b>.`,
    left: (kg, size) => `lebih kurang ${kg} kg lagi daripada ${size} kg`,
    day: (d, n) => `Hari ${d} daripada ${n}`,
    empty: "Dijangka habis",
    last: "Tukar terakhir",
    renew: "Renew",
    confirm: "Tandakan tong baharu dipasang hari ini?",
    levels: { full: "Penuh", medium: "Sederhana", low: "Rendah", critical: "Kritikal" },
    missing: "Pilih sensor Tahap bagi tong Gas Renew.",
  },
};

const FILL = {
  full: "#00A19A",
  medium: "#00A19A",
  low: "#F2A100",
  critical: "#DB4437",
};

function cylinderSvg(pct, color) {
  const top = 86, bot = 224;
  const y = bot - ((bot - top) * Math.max(0, Math.min(100, pct))) / 100;
  const body =
    "M56 128 C56 96 92 84 128 84 C164 84 200 96 200 128 L200 206 Q200 224 182 224 L74 224 Q56 224 56 206 Z";
  return `
  <svg viewBox="0 0 256 256" class="cyl" role="img" aria-label="${pct}%">
    <defs><clipPath id="gr-body"><path d="${body}"/></clipPath></defs>
    <path d="M78 218 L178 218 L184 240 Q184 244 180 244 L76 244 Q72 244 72 240 Z" fill="#007C76"/>
    <path d="${body}" class="cyl-empty"/>
    <rect x="50" y="${y}" width="160" height="${bot - y + 2}" fill="${color}" clip-path="url(#gr-body)"/>
    <line x1="56" y1="${y}" x2="200" y2="${y}" stroke="#fff" stroke-opacity=".55" stroke-width="2" clip-path="url(#gr-body)"/>
    <path d="M56 164 L200 164" stroke="#000" stroke-opacity=".10" stroke-width="3" clip-path="url(#gr-body)"/>
    <rect x="72" y="132" width="12" height="78" rx="6" fill="#fff" fill-opacity=".28"/>
    <rect x="116" y="58" width="24" height="30" rx="4" fill="#5F6B73"/>
    <rect x="110" y="52" width="36" height="10" rx="3" fill="#5F6B73"/>
    <path fill="#E2231A" fill-rule="evenodd" d="M84 30 Q84 20 94 20 L162 20 Q172 20 172 30 L172 92 L84 92 Z M104 38 Q100 38 100 42 L100 58 Q100 62 104 62 L152 62 Q156 62 156 58 L156 42 Q156 38 152 38 Z"/>
    <path d="M84 84 L172 84 L172 92 L84 92 Z" fill="#B5160F"/>
  </svg>`;
}

class GasRenewCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error("entity is required (the Gas Renew Level sensor)");
    this._config = { confirm_renew: true, ...config };
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._sig = null;
  }

  set hass(hass) {
    this._hass = hass;
    const st = hass.states[this._config.entity];
    // Only re-render when something we show changed.
    const sig = st ? `${st.state}|${st.last_updated}|${hass.locale?.language}` : "missing";
    if (sig === this._sig) return;
    this._sig = sig;
    this._render();
  }

  getCardSize() {
    return 5;
  }

  static getStubConfig(hass) {
    const e = Object.keys(hass.states).find(
      (id) => id.startsWith("sensor.") && hass.states[id].attributes.renew_entity !== undefined
    );
    return { entity: e || "" };
  }

  _t() {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").slice(0, 2);
    return TEXT[lang] || TEXT.en;
  }

  _fmtDate(iso, long) {
    if (!iso) return "—";
    const [y, m, d] = iso.split("-").map(Number);
    const dt = new Date(y, m - 1, d);
    const lang = this._hass?.locale?.language || "en";
    return dt.toLocaleDateString(lang, long
      ? { weekday: "long", day: "numeric", month: "long", year: "numeric" }
      : { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  }

  _name(st) {
    if (this._config.name) return this._config.name;
    const ent = this._hass.entities?.[this._config.entity];
    const dev = ent?.device_id ? this._hass.devices?.[ent.device_id] : null;
    return dev?.name_by_user || dev?.name || st.attributes.friendly_name || "LPG";
  }

  _render() {
    const t = this._t();
    const st = this._hass.states[this._config.entity];
    if (!st || st.attributes.renew_entity === undefined) {
      this.shadowRoot.innerHTML = `<ha-card><ha-alert alert-type="warning">${t.missing}</ha-alert></ha-card>`;
      return;
    }
    const a = st.attributes;
    const level = st.state;
    const pct = Number(a.percentage ?? 0);
    const color = FILL[level] || FILL.full;
    const lvlText = t.levels[level] || level;
    const days = Number(a.days_in_use ?? 0);

    let alertType = "success";
    let msg;
    if (days === 0) msg = t.renewed;
    else if (level === "low") { alertType = "warning"; msg = t.warn(lvlText.toUpperCase()); }
    else if (level === "critical") { alertType = "error"; msg = t.warn(lvlText.toUpperCase()); }
    else msg = t.good(days, this._fmtDate(a.last_change, true));

    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 16px; }
        .head { display:flex; align-items:center; gap:10px; }
        .head ha-icon { color:#FF6D00; }
        .title { font-size: 1.35em; flex:1; color: var(--primary-text-color); }
        .chip { font-weight:700; font-size:.8em; letter-spacing:.04em; padding:4px 12px;
                border-radius:14px; color:${color}; background:${color}22; }
        .main { display:flex; gap:12px; align-items:center; margin:8px 0 12px; }
        .cyl { width:130px; height:130px; flex:none; }
        .cyl-empty { fill: ${color}26; }
        .pct { font-size:2.6em; font-weight:700; line-height:1; color: var(--primary-text-color); }
        .sub { color: var(--secondary-text-color); margin:6px 0 8px; }
        .bar { height:8px; border-radius:4px; background: var(--divider-color, #eee); overflow:hidden; }
        .bar > div { height:100%; width:${pct}%; background:${color}; border-radius:4px; }
        .meta { color: var(--secondary-text-color); font-size:.92em; margin-top:8px; line-height:1.5; }
        .meta b { color: var(--primary-text-color); }
        .foot { display:flex; align-items:center; justify-content:space-between; margin-top:12px; }
        .last { color: var(--secondary-text-color); font-size:.85em; }
        button { display:flex; align-items:center; gap:6px; border:0; cursor:pointer; font-weight:700;
                 letter-spacing:.05em; color:#fff; background:#00A19A; padding:8px 16px; border-radius:18px;
                 font-size:.9em; text-transform:uppercase; }
        button:hover { filter: brightness(1.08); }
        button ha-icon { --mdc-icon-size:18px; }
      </style>
      <ha-card>
        <div class="head">
          <ha-icon icon="mdi:fire"></ha-icon>
          <div class="title">${this._name(st)}</div>
          <div class="chip">${lvlText.toUpperCase()}</div>
        </div>
        <div class="main">
          ${cylinderSvg(pct, color)}
          <div style="flex:1;min-width:0">
            <div class="pct">${pct}%</div>
            <div class="sub">${t.left(Number(a.remaining_kg).toFixed(1), a.cylinder_kg)}</div>
            <div class="bar"><div></div></div>
            <div class="meta">
              ${t.day(days, a.duration)}<br/>
              ${t.empty} <b>${this._fmtDate(a.expected_empty, false)}</b>
            </div>
          </div>
        </div>
        <ha-alert alert-type="${alertType}">${msg}</ha-alert>
        <div class="foot">
          <div class="last">${t.last} ${this._fmtDate(a.last_change, false)}</div>
          <button id="renew"><ha-icon icon="mdi:refresh"></ha-icon>${t.renew}</button>
        </div>
      </ha-card>`;

    this.shadowRoot.getElementById("renew").addEventListener("click", () => {
      if (this._config.confirm_renew && !window.confirm(t.confirm)) return;
      this._hass.callService("button", "press", { entity_id: a.renew_entity });
    });
  }
}

if (!customElements.get("gas-renew-card")) {
  customElements.define("gas-renew-card", GasRenewCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "gas-renew-card",
    name: "Gas Renew",
    description: "LPG cylinder level with renew button",
    preview: true,
  });
  console.info(`%c GAS-RENEW-CARD %c ${CARD_VERSION} `, "color:#fff;background:#00A19A", "");
}
