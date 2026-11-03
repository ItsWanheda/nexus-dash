/* NEXUS local feature panels: process intelligence, timeline, alerts, workspace and settings. */
(function (global) {
  'use strict';
  const ALERT_KEY = 'nexus-alert-center-v1';
  const WORKSPACE_KEY = 'nexus-dashboard-layout-v1';
  const ALERT_DEFAULTS = { cpu: 90, ram: 90, disk: 95, disk_activity: 95, consecutive: 3, cooldown_seconds: 120 };
  let alertState = { rules: Object.assign({}, ALERT_DEFAULTS), counters: {}, lastFired: {}, alerts: [], snoozed: {} };
  let workspace = { profile: 'general', layouts: {} };
  let settingsSnapshot = null;

  function readJSON(key, fallback) {
    try { const value = JSON.parse(localStorage.getItem(key) || 'null'); return value && typeof value === 'object' ? value : fallback; }
    catch (_) { return fallback; }
  }
  function persistAlerts() {
    try { localStorage.setItem(ALERT_KEY, JSON.stringify(alertState)); } catch (_) {}
    state.alerts = alertState.alerts;
  }
  function persistWorkspace() {
    try { localStorage.setItem(WORKSPACE_KEY, JSON.stringify(workspace)); } catch (_) {}
  }
  function downloadJSON(name, value) {
    const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = name; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function fmt(value, digits) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(digits === undefined ? 1 : digits) : '—';
  }
  function init() {
    const saved = readJSON(ALERT_KEY, {});
    alertState = {
      rules: Object.assign({}, ALERT_DEFAULTS, { cpu: state.alertConfig.cpu, ram: state.alertConfig.ram, disk: state.alertConfig.disk, consecutive: state.alertConfig.consecutive }, saved.rules || {}),
      counters: saved.counters || {},
      lastFired: saved.lastFired || {},
      alerts: Array.isArray(saved.alerts) ? saved.alerts.slice(0, 100) : [],
      snoozed: saved.snoozed || {}
    };
    state.alerts = alertState.alerts;
    workspace = Object.assign({ profile: 'general', layouts: {} }, readJSON(WORKSPACE_KEY, {}));
  }

  function evaluateAlerts(data) {
    if (!data || !data.cpu || !data.ram || !data.disk) return;
    const rules = alertState.rules;
    const metrics = [
      { key: 'cpu', label: 'CPU utilisation', value: Number(data.cpu.percent), threshold: Number(rules.cpu), unit: '%' },
      { key: 'ram', label: 'System memory pressure', value: Number(data.ram.percent), threshold: Number(rules.ram), unit: '%' },
      { key: 'disk', label: 'System volume capacity', value: Number(data.disk.percent), threshold: Number(rules.disk), unit: '%' },
      { key: 'disk_activity', label: 'Disk activity', value: Number(data.storage_io && data.storage_io.activity_percent), threshold: Number(rules.disk_activity), unit: '%' }
    ];
    const now = Date.now();
    metrics.forEach(metric => {
      if (!Number.isFinite(metric.value) || !Number.isFinite(metric.threshold)) return;
      const active = alertState.alerts.find(item => item.key === metric.key && item.status === 'active');
      if (active && metric.value < metric.threshold - 5) {
        active.status = 'resolved';
        active.resolved_at = new Date(now).toISOString();
        active.resolved_value = metric.value;
        persistAlerts();
      }
      alertState.counters[metric.key] = metric.value >= metric.threshold
        ? (Number(alertState.counters[metric.key]) || 0) + 1 : 0;
      const cooldown = Math.max(30, Math.min(3600, Number(rules.cooldown_seconds) || 120)) * 1000;
      const elapsed = now - (Number(alertState.lastFired[metric.key]) || 0);
      const snoozedUntil = Number(alertState.snoozed[metric.key]) || 0;
      if (metric.value >= metric.threshold && alertState.counters[metric.key] >= Number(rules.consecutive || 3)
          && !active && elapsed >= cooldown && now >= snoozedUntil) {
        const alert = {
          id: metric.key + '-' + now, key: metric.key, label: metric.label,
          value: Math.round(metric.value * 10) / 10, threshold: metric.threshold, unit: metric.unit,
          severity: metric.value >= metric.threshold + 8 ? 'critical' : 'warning',
          status: 'active', acknowledged: false, at: new Date(now).toISOString(),
          description: metric.label + ' exceeded its configured threshold.'
        };
        alertState.alerts.unshift(alert);
        alertState.alerts = alertState.alerts.slice(0, 100);
        alertState.lastFired[metric.key] = now;
        persistAlerts();
        addLog(alert.severity === 'critical' ? 'ERROR' : 'WARN',
          alert.label + ' is ' + fmt(alert.value) + '% (threshold ' + fmt(alert.threshold, 0) + '%).');
        if (window.Notification && Notification.permission === 'granted') {
          try { new Notification('NEXUS alert: ' + alert.label, { body: fmt(alert.value) + '% · threshold ' + fmt(alert.threshold, 0) + '%' }); } catch (_) {}
        }
      }
    });
    if (state.tab === 'alerts') renderAlertRows();
  }

  function renderTab(tab, main) {
    if (tab === 'timeline') renderTimeline(main);
    else if (tab === 'alerts') renderAlertCenter(main);
    else if (tab === 'settings') renderSettings(main);
  }
  function renderTimeline(main) {
    main.innerHTML =
      '<section class="page-intro"><div><div class="eyebrow">INVESTIGATION / EVENT CORRELATION</div><h2>Investigation Timeline</h2><p>Review stored resource spikes, process starts and exits, and your own incident markers in one chronological view.</p></div><button class="secondary-button" data-action="timeline-refresh" type="button">↻ Refresh</button></section>' +
      '<section class="panel timeline-composer"><div><span class="eyebrow">USER MARKER</span><h3>Annotate an incident</h3><p class="muted">Add a note such as “started game”, “IDE build”, “app froze”, or “network lag”.</p></div><div class="timeline-form"><label>Event title<input id="timeline-title" maxlength="120" placeholder="Started a game / compilation / app froze"></label><label>Notes<textarea id="timeline-note" maxlength="500" rows="2" placeholder="What changed? What did you notice?"></textarea></label><button class="primary-button" data-action="timeline-add-marker" type="button">Save marker</button></div></section>' +
      '<section class="panel"><div class="timeline-toolbar"><div><span class="eyebrow">RECORDED EVENTS</span><h3>Incident window</h3></div><label>Window<select id="timeline-window" class="flight-select"><option value="5m">5 minutes</option><option value="15m">15 minutes</option><option value="1h">1 hour</option><option value="6h">6 hours</option><option value="24h" selected>24 hours</option></select></label></div><div id="timeline-events" class="timeline-events"><p class="empty-state">Loading local events…</p></div></section>' +
      '<p class="table-note">Events are stored locally in SQLite. Process start/exit detection is best-effort and starts after the process tracker establishes its initial snapshot.</p>';
    loadTimeline();
  }
  async function loadTimeline() {
    const target = document.getElementById('timeline-events');
    if (!target) return;
    const selector = document.getElementById('timeline-window');
    const windowName = selector ? selector.value : (state.timelineWindow || '24h');
    state.timelineWindow = windowName;
    target.innerHTML = '<p class="empty-state">Loading timeline events…</p>';
    try {
      const result = await api('/timeline?window=' + encodeURIComponent(windowName) + '&limit=500');
      const events = Array.isArray(result.events) ? result.events.slice().reverse() : [];
      if (!events.length) {
        target.innerHTML = '<p class="empty-state">No events were recorded in this window yet. Add a marker or keep the local recorder running.</p>';
        return;
      }
      target.innerHTML = events.map(item => {
        const severity = ['critical', 'warning'].includes(item.severity) ? item.severity : 'info';
        return '<article class="timeline-event timeline-' + severity + '"><div class="timeline-event-rail"><i></i></div><div class="timeline-event-main"><div class="timeline-event-top"><span class="timeline-category">' +
          escapeHTML(String(item.category || 'system').replaceAll('-', ' ')) + '</span><time>' + escapeHTML(new Date(item.timestamp).toLocaleString()) +
          '</time></div><h4>' + escapeHTML(item.title) + '</h4><p>' + escapeHTML(item.detail || '') + '</p></div></article>';
      }).join('');
    } catch (error) { target.innerHTML = '<p class="empty-state error-text">' + escapeHTML(error.message) + '</p>'; }
  }
  async function addTimelineMarker() {
    const title = document.getElementById('timeline-title'), note = document.getElementById('timeline-note');
    if (!title || !title.value.trim()) { window.alert('Enter a short event title first.'); return; }
    try {
      await api('/timeline/markers', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title.value.trim(), note: note ? note.value.trim() : '' }) });
      title.value = ''; if (note) note.value = '';
      addLog('INFO', 'Added an investigation timeline marker.');
      await loadTimeline();
    } catch (error) { window.alert('Could not save timeline marker: ' + error.message); }
  }

  function alertRuleInput(label, key, value) {
    return '<label>' + escapeHTML(label) + ' threshold (%)<input data-alert-rule="' + key + '" type="number" min="1" max="100" step="1" value="' + Number(value) + '"></label>';
  }
  function renderAlertCenter(main) {
    const active = alertState.alerts.filter(item => item.status === 'active').length;
    const resolved = alertState.alerts.filter(item => item.status === 'resolved').length;
    main.innerHTML =
      '<section class="page-intro"><div><div class="eyebrow">ALERTS / RESOURCE GUARD</div><h2>Advanced Alert Center</h2><p>Local rules use consecutive samples, cooldowns, and a recovery margin to reduce repeated noise. Alert history stays on this device.</p></div><button class="secondary-button" data-action="enable-notifications" type="button">Enable notifications</button></section>' +
      '<div class="alert-center-summary"><section class="panel"><span>Active alerts</span><strong id="alert-active-count">' + active + '</strong></section><section class="panel"><span>Resolved</span><strong id="alert-resolved-count">' + resolved + '</strong></section><section class="panel"><span>Notification permission</span><strong>' + (window.Notification ? escapeHTML(Notification.permission) : 'Unsupported') + '</strong></section></div>' +
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">RULE CONFIGURATION</span><h3>Pressure thresholds</h3></div><span class="panel-tag">LOCAL STORAGE</span></div><div class="alert-center-config">' +
      alertRuleInput('CPU', 'cpu', alertState.rules.cpu) + alertRuleInput('RAM', 'ram', alertState.rules.ram) +
      alertRuleInput('Disk capacity', 'disk', alertState.rules.disk) + alertRuleInput('Disk activity', 'disk_activity', alertState.rules.disk_activity) +
      '<label>Consecutive samples<input id="alert-center-consecutive" type="number" min="1" max="10" value="' + Number(alertState.rules.consecutive) + '"></label><label>Cooldown (seconds)<input id="alert-center-cooldown" type="number" min="30" max="3600" step="30" value="' + Number(alertState.rules.cooldown_seconds) + '"></label></div><div class="alert-actions"><button class="primary-button" data-action="save-alert-rules" type="button">Save rules</button><span class="muted">A rule resolves after usage falls 5 percentage points below its trigger.</span></div></section>' +
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">ACTIVE / ACKNOWLEDGE</span><h3>Current alerts</h3></div><span id="alert-active-label" class="panel-tag">' + active + ' ACTIVE</span></div><div id="alert-active-list" class="alert-center-list"></div></section>' +
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">HISTORY</span><h3>Resolved alerts</h3></div><button class="text-button" data-action="clear-resolved-alerts" type="button">Clear resolved</button></div><div id="alert-resolved-list" class="alert-center-list"></div></section>' +
      '<p class="table-note">GPU temperature, network error-rate, and unexpected-exit alerts remain unavailable unless the OS/provider exposes those specific signals. NEXUS does not fabricate unsupported readings.</p>';
    renderAlertRows();
  }
  function renderAlertRows() {
    const activeNode = document.getElementById('alert-active-list'), resolvedNode = document.getElementById('alert-resolved-list');
    if (!activeNode || !resolvedNode) return;
    const active = alertState.alerts.filter(item => item.status === 'active');
    const resolved = alertState.alerts.filter(item => item.status === 'resolved');
    const row = item => '<article class="alert-center-row alert-' + (item.severity === 'critical' ? 'critical' : 'warning') + '"><div><div class="alert-center-top"><span class="severity-chip">' + escapeHTML(String(item.severity).toUpperCase()) + '</span><time>' + escapeHTML(new Date(item.at).toLocaleString()) +
      '</time></div><strong>' + escapeHTML(item.label) + '</strong><p>' + fmt(item.value) + item.unit + ' · trigger ' + fmt(item.threshold, 0) + item.unit + (item.acknowledged ? ' · acknowledged' : '') + '</p></div>' +
      (item.status === 'active' ? '<div class="alert-row-actions"><button class="secondary-button compact-button" data-action="acknowledge-alert" data-alert-id="' + escapeHTML(item.id) + '">Acknowledge</button><button class="secondary-button compact-button" data-action="snooze-alert" data-alert-id="' + escapeHTML(item.id) + '">Snooze 10m</button></div>' : '<span class="protected-label">Resolved</span>') + '</article>';
    activeNode.innerHTML = active.length ? active.map(row).join('') : '<p class="empty-state">No active alerts. The local rules are monitoring available signals.</p>';
    resolvedNode.innerHTML = resolved.length ? resolved.slice(0, 30).map(row).join('') : '<p class="empty-state">No resolved alerts yet.</p>';
    setText('alert-active-count', String(active.length)); setText('alert-resolved-count', String(resolved.length)); setText('alert-active-label', active.length + ' ACTIVE');
  }
  function saveAlertRules() {
    const rules = Object.assign({}, alertState.rules);
    document.querySelectorAll('[data-alert-rule]').forEach(input => {
      const value = Number(input.value), key = input.getAttribute('data-alert-rule');
      if (Number.isFinite(value) && value >= 1 && value <= 100) rules[key] = value;
    });
    const consecutive = Number(document.getElementById('alert-center-consecutive')?.value);
    const cooldown = Number(document.getElementById('alert-center-cooldown')?.value);
    if (!Number.isInteger(consecutive) || consecutive < 1 || consecutive > 10 || !Number.isInteger(cooldown) || cooldown < 30 || cooldown > 3600) {
      window.alert('Consecutive samples must be 1–10 and cooldown must be 30–3600 seconds.'); return;
    }
    rules.consecutive = consecutive; rules.cooldown_seconds = cooldown;
    alertState.rules = rules;
    state.alertConfig = { cpu: rules.cpu, ram: rules.ram, disk: rules.disk, consecutive: rules.consecutive };
    alertState.counters = {}; persistAlerts(); addLog('INFO', 'Advanced alert rules saved.');
  }
  function alertAction(action, target) {
    const id = target.getAttribute('data-alert-id'), item = alertState.alerts.find(entry => entry.id === id);
    if (!item) return;
    item.acknowledged = true;
    if (action === 'snooze-alert') alertState.snoozed[item.key] = Date.now() + 10 * 60 * 1000;
    persistAlerts(); renderAlertRows();
  }

  const widgetIds = ['cpu-metric', 'ram-metric', 'gpu-metric', 'network-metric', 'cpu-chart', 'disk-card', 'activity-card', 'connection-card'];
  function currentLayout() {
    if (!workspace.layouts[workspace.profile]) workspace.layouts[workspace.profile] = { hidden: [], order: {}, sizes: {} };
    return workspace.layouts[workspace.profile];
  }
  function defaultHidden(profile) {
    if (profile === 'gaming') return ['connection-card'];
    if (profile === 'developer' || profile === 'laptop') return ['gpu-metric'];
    return [];
  }
  function tagDashboardWidgets() {
    const metrics = document.querySelector('.metrics-grid'), content = document.querySelector('.content-grid');
    if (!metrics || !content) return;
    Array.from(metrics.children).forEach((node, index) => { node.dataset.widgetId = ['cpu-metric', 'ram-metric', 'gpu-metric', 'network-metric'][index]; node.dataset.widgetGroup = 'metrics'; });
    Array.from(content.children).forEach((node, index) => { node.dataset.widgetId = ['cpu-chart', 'disk-card', 'activity-card', 'connection-card'][index]; node.dataset.widgetGroup = 'content'; });
  }
  function toolbarMarkup() {
    return '<div class="dashboard-toolbar"><label>Layout<select id="dashboard-profile" class="flight-select"><option value="general">General</option><option value="gaming">Gaming</option><option value="developer">Developer</option><option value="workstation">Workstation</option><option value="laptop">Laptop</option></select></label><label>Chart window<select id="dashboard-range" class="flight-select"><option value="5m">5 minutes</option><option value="15m">15 minutes</option><option value="1h" selected>1 hour</option><option value="6h">6 hours</option><option value="24h">24 hours</option></select></label><label>Chart style<select id="dashboard-chart-style" class="flight-select"><option value="bars">Bars</option><option value="line">Line</option></select></label><label>Chart refresh<select id="dashboard-refresh" class="flight-select"><option value="5">5 seconds</option><option value="10">10 seconds</option><option value="30">30 seconds</option></select></label><button class="secondary-button" data-action="dashboard-edit" type="button">Customize</button></div><div id="dashboard-editor" class="dashboard-editor" hidden></div>';
  }
  function applyDashboard() {
    if (state.tab !== 'dashboard') return;
    const intro = document.querySelector('#main-content .page-intro');
    if (intro && !document.getElementById('dashboard-toolbar')) {
      const wrapper = document.createElement('div'); wrapper.id = 'dashboard-toolbar'; wrapper.innerHTML = toolbarMarkup(); intro.after(wrapper);
    }
    tagDashboardWidgets();
    const layout = currentLayout();
    ['metrics', 'content'].forEach(group => {
      const container = document.querySelector(group === 'metrics' ? '.metrics-grid' : '.content-grid');
      if (!container) return;
      const nodes = Array.from(container.children), order = layout.order[group] || [];
      nodes.sort((a, b) => { const ai = order.indexOf(a.dataset.widgetId), bi = order.indexOf(b.dataset.widgetId); return (ai < 0 ? 999 : ai) - (bi < 0 ? 999 : bi); });
      nodes.forEach(node => {
        container.appendChild(node);
        const id = node.dataset.widgetId;
        node.hidden = layout.hidden.includes(id) || defaultHidden(workspace.profile).includes(id);
        node.classList.toggle('widget-wide', layout.sizes[id] === 'wide');
        node.draggable = true;
        node.addEventListener('dragstart', event => { event.dataTransfer.setData('text/plain', id); });
        node.addEventListener('dragover', event => event.preventDefault());
        node.addEventListener('drop', event => {
          event.preventDefault();
          const from = event.dataTransfer.getData('text/plain'), moving = Array.from(container.children).find(item => item.dataset.widgetId === from);
          if (moving && moving !== node) { container.insertBefore(moving, node); saveWidgetOrder(group, container); }
        });
      });
    });
    const profile = document.getElementById('dashboard-profile');
    if (profile) profile.value = workspace.profile;
    const refresh = document.getElementById('dashboard-refresh');
    if (refresh) refresh.value = String([5, 10, 30].includes(Number(workspace.refreshIntervalSeconds)) ? workspace.refreshIntervalSeconds : 10);
    const editor = document.getElementById('dashboard-editor');
    if (editor && !editor.dataset.ready) {
      editor.innerHTML = '<div class="dashboard-editor-head"><strong>Visible widgets and sizing</strong><span class="muted">Drag cards to reorder them.</span></div>' +
        widgetIds.map(id => '<label><input type="checkbox" data-widget-visible="' + id + '" ' + (layout.hidden.includes(id) || defaultHidden(workspace.profile).includes(id) ? '' : 'checked') + '> ' + escapeHTML(id.replaceAll('-', ' ')) +
          '<select data-widget-size="' + id + '"><option value="normal">Normal</option><option value="wide"' + (layout.sizes[id] === 'wide' ? ' selected' : '') + '>Wide</option></select></label>').join('');
      editor.dataset.ready = '1';
    }
  }
  function saveWidgetOrder(group, container) { currentLayout().order[group] = Array.from(container.children).map(node => node.dataset.widgetId); persistWorkspace(); }
  function renderDashboardChart() {
    const container = document.getElementById('cpu-chart');
    if (!container) return false;
    const samples = state.dashboardHistory || [], style = document.getElementById('dashboard-chart-style')?.value || 'bars';
    if (!samples.length) return false;
    if (style === 'line') {
      const values = samples.slice(-120);
      const points = values.map((item, index) => {
        const x = values.length === 1 ? 500 : 20 + index / (values.length - 1) * 960;
        return x.toFixed(1) + ',' + (220 - Math.max(0, Math.min(100, Number(item.cpu_percent) || 0)) * 2).toFixed(1);
      }).join(' ');
      container.classList.add('chart-line-mode');
      container.innerHTML = '<svg viewBox="0 0 1000 240" role="img" aria-label="Historical CPU utilisation"><polyline points="' + points + '"></polyline></svg>';
    } else {
      container.classList.remove('chart-line-mode');
      drawBars('cpu-chart', samples.map(item => Number(item.cpu_percent) || 0), 'CPU');
    }
    return true;
  }
  async function loadDashboardHistory() {
    const selector = document.getElementById('dashboard-range');
    if (!selector) return;
    try {
      const result = await api('/history?window=' + encodeURIComponent(selector.value) + '&limit=120');
      state.dashboardHistory = Array.isArray(result.samples) ? result.samples : [];
      renderDashboardChart();
    } catch (_) {}
  }

  function renderSettings(main) {
    main.innerHTML = '<section class="page-intro"><div><div class="eyebrow">LOCAL CONFIGURATION / DATA LIFECYCLE</div><h2>Settings & Configuration</h2><p>Control the recorder, retention, process sampling, privacy, and desktop behaviour. Settings stay in your local NEXUS data directory.</p></div></section>' +
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">RECORDER</span><h3>Sampling and retention</h3></div><span class="panel-tag">LOCAL JSON</span></div><div id="settings-form" class="settings-grid"><p class="empty-state">Loading saved settings…</p></div><div class="settings-actions"><button class="primary-button" data-action="save-settings" type="button">Save settings</button><button class="secondary-button" data-action="export-settings" type="button">Export settings</button><label class="secondary-button file-import-label">Import settings<input id="settings-import" type="file" accept="application/json,.json" hidden></label><button class="danger-button" data-action="clear-history" type="button">Delete local telemetry history</button></div><p id="settings-status" class="table-note" aria-live="polite"></p></section>' +
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">DATA LOCATION</span><h3>Local storage</h3></div></div><div id="settings-location" class="settings-location">Reading current storage location…</div><p class="table-note">Changing the data directory requires restarting NEXUS. Set NEXUS_DATA_DIR before launch. Retention changes are enforced on subsequent writes.</p></section>' +
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">DESKTOP CLIENT</span><h3>Windows desktop mode</h3></div><span class="panel-tag" id="desktop-runtime-status">BROWSER MODE</span></div><p class="muted">The packaged Windows client embeds the local API in a native WebView window and can stay in the system tray. Startup registration is opt-in and is enabled only through an explicit desktop command-line action.</p><div class="mini-facts"><span>Desktop runtime</span><strong id="desktop-runtime-detail">Checking</strong><span>Startup mode</span><strong>Opt-in</strong><span>Network exposure</span><strong>Loopback only</strong></div></section>';
    loadSettings();
  }
  function settingsFormMarkup(s) {
    return '<div class="settings-field"><label>Recorder interval<select id="setting-sampling" class="flight-select"><option value="5">5 seconds</option><option value="10">10 seconds</option><option value="15">15 seconds</option><option value="30">30 seconds</option></select></label><label>Retention<select id="setting-retention" class="flight-select"><option value="1">24 hours</option><option value="7">7 days</option><option value="30">30 days</option></select></label><label>Process history interval<select id="setting-process-interval" class="flight-select"><option value="5">5 seconds</option><option value="10">10 seconds</option><option value="15">15 seconds</option><option value="30">30 seconds</option></select></label><label>Excluded process names<input id="setting-exclusions" maxlength="2000" value="' + escapeHTML((s.process_exclusions || []).join(', ')) + '" placeholder="e.g. chrome.exe, code.exe"></label></div>' +
      '<div class="settings-toggles"><label><input type="checkbox" id="setting-background" ' + (s.background_recording ? 'checked' : '') + '> Background recording</label><label><input type="checkbox" id="setting-process-history" ' + (s.process_history_enabled ? 'checked' : '') + '> Per-process history</label><label><input type="checkbox" id="setting-privacy" ' + (s.privacy_mode ? 'checked' : '') + '> Privacy mode (raw samples exclude process identifiers)</label><label><input type="checkbox" id="setting-start-minimized" ' + (s.start_minimized ? 'checked' : '') + '> Start desktop window minimized</label></div>';
  }
  async function loadSettings() {
    const form = document.getElementById('settings-form'); if (!form) return;
    try {
      const s = await api('/settings'); settingsSnapshot = s; form.innerHTML = settingsFormMarkup(s);
      document.getElementById('setting-sampling').value = String(s.sampling_interval_seconds);
      document.getElementById('setting-retention').value = String(s.retention_days);
      document.getElementById('setting-process-interval').value = String(s.process_history_interval_seconds);
      const location = document.getElementById('settings-location');
      if (location) location.innerHTML = '<div><span>Data directory</span><strong>' + escapeHTML(s.data_directory) + '</strong></div><div><span>SQLite database</span><strong>' + escapeHTML(s.database_path) + '</strong></div><div><span>History policy</span><strong>' + escapeHTML(s.retention_note) + '</strong></div>';
      const runtime = document.getElementById('desktop-runtime-status'), detail = document.getElementById('desktop-runtime-detail');
      if (runtime) runtime.textContent = s.desktop_runtime ? 'DESKTOP RUNTIME' : 'BROWSER MODE';
      if (detail) detail.textContent = s.desktop_runtime ? 'Embedded WebView' : 'Browser / local web server';
      setText('settings-status', 'Saved settings loaded.');
    } catch (error) { form.innerHTML = '<p class="empty-state error-text">' + escapeHTML(error.message) + '</p>'; }
  }
  async function saveSettings() {
    if (!document.getElementById('settings-form')) return;
    const exclusions = (document.getElementById('setting-exclusions').value || '').split(',').map(value => value.trim()).filter(Boolean);
    const payload = {
      sampling_interval_seconds: Number(document.getElementById('setting-sampling').value),
      retention_days: Number(document.getElementById('setting-retention').value),
      process_history_interval_seconds: Number(document.getElementById('setting-process-interval').value),
      process_exclusions: exclusions,
      background_recording: document.getElementById('setting-background').checked,
      process_history_enabled: document.getElementById('setting-process-history').checked,
      privacy_mode: document.getElementById('setting-privacy').checked,
      start_minimized: document.getElementById('setting-start-minimized').checked
    };
    try {
      const result = await api('/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      settingsSnapshot = result; setText('settings-status', 'Settings saved. Sampling and retention changes are applied by the local service.');
      addLog('INFO', 'Local NEXUS settings updated.');
    } catch (error) { setText('settings-status', error.message); }
  }
  function exportSettings() {
    if (!settingsSnapshot) { window.alert('Load settings before exporting.'); return; }
    const clean = Object.fromEntries(Object.entries(settingsSnapshot).filter(([key]) => !['data_directory', 'database_path', 'retention_note', 'desktop_runtime'].includes(key)));
    downloadJSON('nexus-settings-' + new Date().toISOString().slice(0, 10) + '.json', clean);
  }
  async function importSettings(file) {
    try {
      const parsed = JSON.parse(await file.text());
      const allowed = ['sampling_interval_seconds', 'retention_days', 'background_recording', 'process_history_enabled', 'process_history_interval_seconds', 'process_exclusions', 'privacy_mode', 'start_minimized'];
      const payload = Object.fromEntries(Object.entries(parsed).filter(([key]) => allowed.includes(key)));
      await api('/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      await loadSettings(); setText('settings-status', 'Settings imported and validated.');
    } catch (error) { setText('settings-status', 'Import failed: ' + error.message); }
  }
  async function clearHistory() {
    if (!window.confirm('Delete all local telemetry samples and investigation timeline events? This cannot be undone.')) return;
    try {
      await api('/history', { method: 'DELETE' }); setText('settings-status', 'Local telemetry history and timeline events were deleted.');
      addLog('WARN', 'Deleted local telemetry history and timeline events.');
    } catch (error) { setText('settings-status', error.message); }
  }

  async function inspectProcess(pid, createTime) {
    const panel = document.getElementById('process-inspector'), body = document.getElementById('process-inspector-content');
    if (!panel || !body || !Number.isFinite(pid) || !Number.isFinite(createTime) || createTime <= 0) return;
    panel.hidden = false; body.innerHTML = '<p class="empty-state">Inspecting PID ' + Number(pid) + '…</p>';
    setText('process-inspector-title', 'PID ' + Number(pid) + ' · loading'); state.selectedProcess = { pid, create_time: createTime };
    try {
      const p = await api('/processes/' + Number(pid) + '?create_time=' + encodeURIComponent(createTime));
      state.selectedProcess = { pid: p.pid, create_time: p.create_time, name: p.name };
      const history = Array.isArray(p.history) ? p.history : [];
      const memoryValues = history.slice(-90).map(item => Number(item.rss_mb) || 0);
      const peak = memoryValues.length ? Math.max(...memoryValues) : p.rss_mb;
      const averageCpu = history.length ? history.reduce((sum, item) => sum + (Number(item.cpu_percent) || 0), 0) / history.length : null;
      const parent = p.parent ? escapeHTML(p.parent.name) + ' (PID ' + Number(p.parent.pid) + ')' : 'Unavailable';
      const children = (p.children || []).map(child => escapeHTML(child.name) + ' (' + Number(child.pid) + ')').join(', ') || 'None visible';
      const handles = p.handles.status === 'Available' ? (p.handles.count !== null ? p.handles.count + ' handles' : '') + (p.handles.file_descriptors !== null ? ' · ' + p.handles.file_descriptors + ' file descriptors' : '') : 'Unsupported by this OS/provider';
      const initialRam = history.length ? Number(history[0].rss_mb) : Number(p.rss_mb);
      const ramGrowth = Number(p.rss_mb) - initialRam;
      body.innerHTML = '<div class="process-detail-grid">' +
        processFact('CPU now', fmt(p.cpu_percent) + '%') + processFact('CPU average', averageCpu === null ? 'Warming up' : fmt(averageCpu) + '%') +
        processFact('RAM now', fmt(p.rss_mb) + ' MB') + processFact('RAM observed peak', fmt(peak) + ' MB') +
        processFact('Initial RAM', fmt(initialRam) + ' MB') + processFact('Observed RAM growth', (ramGrowth >= 0 ? '+' : '') + fmt(ramGrowth) + ' MB') +
        processFact('Threads', p.threads) + processFact('Uptime', formatDuration(p.uptime_seconds)) +
        processFact('Parent process', parent) + processFact('Children', children) +
        processFact('Disk read rate', p.io.read_rate_bytes_per_sec === null ? 'Unavailable' : formatBytesPerSecond(p.io.read_rate_bytes_per_sec)) +
        processFact('Disk write rate', p.io.write_rate_bytes_per_sec === null ? 'Unavailable' : formatBytesPerSecond(p.io.write_rate_bytes_per_sec)) +
        processFact('Handles / descriptors', handles) + processFact('Start time', new Date(p.started_at).toLocaleString()) + '</div>' +
        '<section class="process-executable"><span class="eyebrow">EXECUTABLE METADATA</span><strong>' + escapeHTML(p.executable.name || p.name) + '</strong><code>' + escapeHTML(p.executable.path || 'Executable path unavailable') + '</code><small>' + (p.executable.size_bytes === null ? 'File size unavailable' : fmt(p.executable.size_bytes / 1048576, 2) + ' MiB') + '</small></section>' +
        '<section class="process-history"><div class="panel-heading"><div><span class="eyebrow">MEMORY / CPU HISTORY</span><h4>Observed process trend</h4></div><span class="panel-tag">' + escapeHTML(p.history_status) + '</span></div><div id="process-history-chart" class="process-history-chart">' + processHistoryMarkup(history) + '</div><p class="table-note">History is sampled only for the highest-memory processes, keyed by PID and creation time. It resets when the API restarts.</p></section>' +
        '<div class="process-compare-controls"><label>Compare with<select id="process-compare-target" class="flight-select">' + state.processes.filter(item => Number(item.pid) !== Number(p.pid) && Number(item.create_time) > 0).slice(0, 100).map(item => '<option value="' + Number(item.pid) + '" data-create-time="' + Number(item.create_time) + '">' + escapeHTML(item.name) + ' · PID ' + Number(item.pid) + '</option>').join('') + '</select></label><button class="secondary-button" data-action="process-compare" type="button">Compare processes</button></div><div id="process-compare-result"></div>';
      setText('process-inspector-title', p.name + ' · PID ' + p.pid);
      panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) { body.innerHTML = '<p class="empty-state error-text">' + escapeHTML(error.message) + '</p>'; }
  }
  function processFact(label, value) {
    return '<div class="process-fact"><span>' + escapeHTML(label) + '</span><strong>' + escapeHTML(value === null || value === undefined ? 'Unavailable' : value) + '</strong></div>';
  }
  function processHistoryMarkup(history) {
    if (!history.length) return '<p class="empty-state">No process samples yet. Enable process history and revisit shortly.</p>';
    const points = history.slice(-60), max = Math.max(1, ...points.map(item => Number(item.rss_mb) || 0));
    const memory = points.map(item => '<i title="' + escapeHTML(new Date(item.timestamp).toLocaleTimeString() + ' · ' + fmt(item.rss_mb) + ' MB RAM') + '" style="height:' + Math.max(2, Number(item.rss_mb) / max * 100) + '%"></i>').join('');
    const cpu = points.map(item => '<i title="' + escapeHTML(new Date(item.timestamp).toLocaleTimeString() + ' · ' + fmt(item.cpu_percent) + '% CPU') + '" style="height:' + Math.max(2, Math.min(100, Number(item.cpu_percent) || 0)) + '%"></i>').join('');
    return '<div class="process-trend-series"><span>RAM history</span><div class="process-memory-bars">' + memory + '</div></div><div class="process-trend-series"><span>CPU history</span><div class="process-cpu-bars">' + cpu + '</div></div><div class="chart-axis"><span>Older</span><span>Latest</span></div>';
  }
  async function compareProcesses() {
    const first = state.selectedProcess, select = document.getElementById('process-compare-target');
    if (!first || !select || !select.selectedOptions.length) return;
    const option = select.selectedOptions[0], secondPid = Number(select.value), secondCreate = Number(option.dataset.createTime);
    const target = document.getElementById('process-compare-result'); if (!target) return;
    target.innerHTML = '<p class="muted">Comparing process snapshots…</p>';
    try {
      const result = await api('/process-compare?pid_a=' + first.pid + '&create_time_a=' + first.create_time + '&pid_b=' + secondPid + '&create_time_b=' + secondCreate);
      const a = result.processes[0], b = result.processes[1];
      target.innerHTML = '<div class="process-compare-grid"><section><strong>' + escapeHTML(a.name) + ' · ' + a.pid + '</strong><p>CPU ' + fmt(a.cpu_percent) + '% · RAM ' + fmt(a.rss_mb) + ' MB · Threads ' + a.threads + '</p></section><section><strong>' + escapeHTML(b.name) + ' · ' + b.pid + '</strong><p>CPU ' + fmt(b.cpu_percent) + '% · RAM ' + fmt(b.rss_mb) + ' MB · Threads ' + b.threads + '</p></section></div>';
    } catch (error) { target.innerHTML = '<p class="error-text">' + escapeHTML(error.message) + '</p>'; }
  }

  let dashboardRefreshTimer = null;
  function scheduleDashboardRefresh() {
    if (dashboardRefreshTimer) window.clearInterval(dashboardRefreshTimer);
    const seconds = [5, 10, 30].includes(Number(workspace.refreshIntervalSeconds)) ? Number(workspace.refreshIntervalSeconds) : 10;
    dashboardRefreshTimer = window.setInterval(loadDashboardHistory, seconds * 1000);
  }
  function afterRender() {
    if (state.tab === 'dashboard') {
      applyDashboard(); loadDashboardHistory(); scheduleDashboardRefresh();
    } else if (dashboardRefreshTimer) {
      window.clearInterval(dashboardRefreshTimer); dashboardRefreshTimer = null;
    }
  }
  function updateLegacyRules(config) {
    if (!config) return;
    ['cpu', 'ram', 'disk', 'consecutive'].forEach(key => {
      const value = Number(config[key]);
      if (Number.isFinite(value) && value > 0) alertState.rules[key] = value;
    });
    persistAlerts();
  }
  function handleChange(target) {
    if (!target) return;
    if (target.id === 'timeline-window') loadTimeline();
    else if (target.id === 'dashboard-profile') {
      workspace.profile = target.value; persistWorkspace();
      const editor = document.getElementById('dashboard-editor'); if (editor) editor.dataset.ready = '';
      applyDashboard();
    }
    else if (target.id === 'dashboard-range') loadDashboardHistory();
    else if (target.id === 'dashboard-chart-style') renderDashboardChart();
    else if (target.id === 'dashboard-refresh') {
      workspace.refreshIntervalSeconds = [5, 10, 30].includes(Number(target.value)) ? Number(target.value) : 10;
      persistWorkspace(); scheduleDashboardRefresh();
    }
    else if (target.id === 'dashboard-refresh') {
      workspace.refreshIntervalSeconds = [5, 10, 30].includes(Number(target.value)) ? Number(target.value) : 10;
      persistWorkspace(); scheduleDashboardRefresh();
    }
    else if (target.dataset.widgetVisible) {
      const layout = currentLayout(), id = target.dataset.widgetVisible;
      layout.hidden = target.checked ? layout.hidden.filter(x => x !== id) : Array.from(new Set(layout.hidden.concat(id)));
      persistWorkspace(); applyDashboard();
    } else if (target.dataset.widgetSize) {
      currentLayout().sizes[target.dataset.widgetSize] = target.value; persistWorkspace(); applyDashboard();
    } else if (target.id === 'settings-import' && target.files && target.files[0]) importSettings(target.files[0]);
  }
  function handleAction(action, target) {
    if (action === 'timeline-refresh') { loadTimeline(); return true; }
    if (action === 'timeline-add-marker') { addTimelineMarker(); return true; }
    if (action === 'save-alert-rules') { saveAlertRules(); return true; }
    if (action === 'acknowledge-alert' || action === 'snooze-alert') {
      const id = target.getAttribute('data-alert-id'), item = alertState.alerts.find(entry => entry.id === id);
      if (item) { item.acknowledged = true; if (action === 'snooze-alert') alertState.snoozed[item.key] = Date.now() + 600000; persistAlerts(); renderAlertRows(); }
      return true;
    }
    if (action === 'clear-resolved-alerts') { alertState.alerts = alertState.alerts.filter(item => item.status !== 'resolved'); persistAlerts(); renderAlertRows(); return true; }
    if (action === 'save-settings') { saveSettings(); return true; }
    if (action === 'export-settings') { exportSettings(); return true; }
    if (action === 'clear-history') { clearHistory(); return true; }
    if (action === 'inspect-process') { inspectProcess(Number(target.dataset.pid), Number(target.dataset.createTime)); return true; }
    if (action === 'process-compare') { compareProcesses(); return true; }
    if (action === 'close-process-inspector') { const node = document.getElementById('process-inspector'); if (node) node.hidden = true; return true; }
    if (action === 'dashboard-edit') { const editor = document.getElementById('dashboard-editor'); if (editor) editor.hidden = !editor.hidden; return true; }
    return false;
  }
  global.NexusEnhancements = { init, renderTab, afterRender, handleAction, handleChange, evaluateAlerts, renderAlertRows, loadTimeline, renderDashboardChart, updateLegacyRules };
})(window);
