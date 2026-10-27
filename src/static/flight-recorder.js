// NEXUS // System Flight Recorder UI. Uses only local API data and browser-local alert preferences.
const RECORDER_WINDOWS = [
  { value: '5m', label: 'Last 5 minutes' },
  { value: '15m', label: 'Last 15 minutes' },
  { value: '1h', label: 'Last hour' },
  { value: '6h', label: 'Last 6 hours' },
  { value: '24h', label: 'Last 24 hours' }
];
const RECORDER_ALERT_DEFAULTS = { cpu: 90, ram: 90, disk: 95, consecutive: 3 };
const RECORDER_ALERT_STORAGE_KEY = 'nexus-recorder-alerts-v1';

function loadRecorderSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(RECORDER_ALERT_STORAGE_KEY) || '{}');
    const consecutive = Number(saved.consecutive);
    state.alertConfig = {
      cpu: Math.max(1, clamp(saved.cpu === undefined ? RECORDER_ALERT_DEFAULTS.cpu : saved.cpu)),
      ram: Math.max(1, clamp(saved.ram === undefined ? RECORDER_ALERT_DEFAULTS.ram : saved.ram)),
      disk: Math.max(1, clamp(saved.disk === undefined ? RECORDER_ALERT_DEFAULTS.disk : saved.disk)),
      consecutive: Math.max(1, Math.min(10,
        Number.isFinite(consecutive) && consecutive ? consecutive : RECORDER_ALERT_DEFAULTS.consecutive))
    };
  } catch (_) {
    state.alertConfig = Object.assign({}, RECORDER_ALERT_DEFAULTS);
  }
  return state.alertConfig;
}

function saveRecorderSettings() {
  const controls = {
    cpu: document.getElementById('alert-cpu'),
    ram: document.getElementById('alert-ram'),
    disk: document.getElementById('alert-disk'),
    consecutive: document.getElementById('alert-consecutive')
  };
  if (!controls.cpu || !controls.ram || !controls.disk || !controls.consecutive) return;
  const next = {
    cpu: Math.max(1, Math.min(100, Number(controls.cpu.value))),
    ram: Math.max(1, Math.min(100, Number(controls.ram.value))),
    disk: Math.max(1, Math.min(100, Number(controls.disk.value))),
    consecutive: Math.max(1, Math.min(10, Number(controls.consecutive.value)))
  };
  if (Object.values(next).some(value => !Number.isFinite(value))) return;
  state.alertConfig = next;
  try { localStorage.setItem(RECORDER_ALERT_STORAGE_KEY, JSON.stringify(next)); } catch (_) {}
  state.alertCounters = {};
  addLog('INFO', 'Flight Recorder alert thresholds updated.');
}

function renderFlightRecorder() {
  loadRecorderSettings();
  const main = document.getElementById('main-content');
  const selectedWindow = state.recorderWindow || '1h';
  const windowOptions = RECORDER_WINDOWS.map(item =>
    '<option value="' + item.value + '"' + (item.value === selectedWindow ? ' selected' : '') + '>' + item.label + '</option>'
  ).join('');
  main.innerHTML =
    '<section class="page-intro"><div><div class="eyebrow">SYSTEM FLIGHT RECORDER / LOCAL HISTORY</div><h2>Telemetry history</h2><p>Replay real resource samples, inspect process relationships, export a session, and tune local threshold alerts.</p></div><span class="live-tag"><span class="pulse-dot"></span> LOCAL RECORDING</span></section>' +
    '<section class="panel"><div class="flight-toolbar"><div><span class="eyebrow">REPLAY WINDOW</span><p class="muted">History persists across page reloads and is bounded by local retention settings.</p></div><div class="flight-toolbar-actions"><label for="history-window" class="muted">Window</label><select id="history-window" class="flight-select">' + windowOptions + '</select><button class="secondary-button" type="button" data-action="export-session-json">Export session JSON</button><button class="primary-button" type="button" data-action="export-session-csv">Export CSV</button></div></div></section>' +
    '<div class="flight-summary"><section class="panel"><span>Latest CPU load</span><strong id="flight-cpu">—</strong><span id="flight-cpu-meta">Waiting for a stored sample</span></section><section class="panel"><span>Latest RAM use</span><strong id="flight-ram">—</strong><span id="flight-ram-meta">Waiting for a stored sample</span></section><section class="panel"><span>Recorded samples</span><strong id="flight-sample-count">0</strong><span id="flight-sample-meta">Selected time window</span></section></div>' +
    '<div class="flight-columns"><section class="panel"><div class="panel-heading"><div><span class="eyebrow">RESOURCE HISTORY</span><h3>CPU, memory, and disk</h3></div><span id="flight-storage-label" class="panel-tag">LOCAL SQLITE</span></div><div id="flight-chart" class="flight-chart-wrap"><p class="empty-state">Loading actual telemetry samples…</p></div><div class="flight-legend"><span><i class="cpu-legend"></i>CPU</span><span><i class="ram-legend"></i>RAM</span><span><i class="disk-legend"></i>Disk</span></div></section>' +
    '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">CONFIGURABLE ALERTS</span><h3>Threshold rules</h3></div><span class="panel-tag">BROWSER LOCAL</span></div><p class="muted">Trigger after consecutive samples above a threshold. Desktop notifications are optional and require explicit permission.</p><div class="alert-config"><label for="alert-cpu">CPU threshold (%)<input id="alert-cpu" type="number" min="1" max="100" step="1" value="' + state.alertConfig.cpu + '"></label><label for="alert-ram">RAM threshold (%)<input id="alert-ram" type="number" min="1" max="100" step="1" value="' + state.alertConfig.ram + '"></label><label for="alert-disk">Disk threshold (%)<input id="alert-disk" type="number" min="1" max="100" step="1" value="' + state.alertConfig.disk + '"></label><label for="alert-consecutive">Consecutive samples (1–10)<input id="alert-consecutive" type="number" min="1" max="10" step="1" value="' + state.alertConfig.consecutive + '"></label></div><div class="alert-actions"><button class="secondary-button" type="button" data-action="enable-notifications">Enable desktop notifications</button></div></section></div>' +
    '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">RECORDER EVENTS</span><h3>Recent alerts</h3></div><span class="panel-tag">MOST RECENT FIRST</span></div><div id="recorder-alert-list" class="alert-list"><p class="empty-state">No threshold alerts have fired in this browser session.</p></div></section>' +
    '<p class="table-note">Recorded metrics exclude host name, OS user name, process command lines, and executable paths. Samples are stored in your local user data directory; use the clear/delete instructions in docs/FLIGHT_RECORDER.md to remove them.</p>';
  loadRecorderHistory();
  renderRecorderAlerts();
}

function recorderPolyline(samples, field) {
  if (!samples.length) return '';
  return samples.map((item, index) => {
    const x = samples.length === 1 ? 500 : 24 + (index / (samples.length - 1)) * 952;
    const value = Math.max(0, Math.min(100, Number(item[field]) || 0));
    return x.toFixed(1) + ',' + (226 - (value / 100) * 200).toFixed(1);
  }).join(' ');
}

function renderRecorderChart(samples) {
  const container = document.getElementById('flight-chart');
  if (!container) return;
  if (!samples.length) {
    container.innerHTML = '<p class="empty-state">No samples for this window yet. Keep NEXUS running; recording starts automatically.</p>';
    return;
  }
  const grid = [26, 76, 126, 176, 226].map(y =>
    '<line class="flight-chart-grid" x1="24" y1="' + y + '" x2="976" y2="' + y + '"></line>'
  ).join('');
  container.innerHTML =
    '<svg class="flight-chart" viewBox="0 0 1000 250" role="img" aria-label="Historical CPU, RAM, and disk utilization percentages">' +
    grid +
    '<polyline class="flight-chart-cpu" points="' + recorderPolyline(samples, 'cpu_percent') + '"></polyline>' +
    '<polyline class="flight-chart-ram" points="' + recorderPolyline(samples, 'ram_percent') + '"></polyline>' +
    '<polyline class="flight-chart-disk" points="' + recorderPolyline(samples, 'disk_percent') + '"></polyline>' +
    '<text x="4" y="29" class="chart-svg-label">100%</text><text x="8" y="230" class="chart-svg-label">0%</text></svg>' +
    '<div class="chart-axis"><span>' + escapeHTML(new Date(samples[0].timestamp).toLocaleString()) + '</span><span>' +
    escapeHTML(new Date(samples[samples.length - 1].timestamp).toLocaleString()) + '</span></div>';
}

async function loadRecorderHistory() {
  const selector = document.getElementById('history-window');
  if (selector) state.recorderWindow = selector.value;
  const windowName = state.recorderWindow || '1h';
  try {
    const payload = await api('/history?window=' + encodeURIComponent(windowName) + '&limit=120');
    state.recorderHistory = Array.isArray(payload.samples) ? payload.samples : [];
    renderRecorderChart(state.recorderHistory);
    setText('flight-sample-count', String(payload.count || 0));
    setText('flight-sample-meta', 'Actual samples · ' + windowName);
    const last = state.recorderHistory[state.recorderHistory.length - 1];
    if (last) {
      setText('flight-cpu', Number(last.cpu_percent).toFixed(1) + '%');
      setText('flight-cpu-meta', 'Latest stored sample · ' + new Date(last.timestamp).toLocaleTimeString());
      setText('flight-ram', Number(last.ram_percent).toFixed(1) + '%');
      setText('flight-ram-meta', Number(last.ram_used_gb).toFixed(1) + ' / ' + Number(last.ram_total_gb).toFixed(1) + ' GiB');
    } else {
      setText('flight-cpu', '—');
      setText('flight-cpu-meta', 'Waiting for a stored sample');
      setText('flight-ram', '—');
      setText('flight-ram-meta', 'Waiting for a stored sample');
    }
  } catch (error) {
    const container = document.getElementById('flight-chart');
    if (container) container.innerHTML = '<p class="empty-state error-text">' + escapeHTML(error.message) + '</p>';
  }
}

function evaluateRecorderAlerts(data) {
  if (!state.alertConfig || !data) return;
  const metrics = [
    { key: 'cpu', label: 'CPU', value: Number(data.cpu && data.cpu.percent) },
    { key: 'ram', label: 'RAM', value: Number(data.ram && data.ram.percent) },
    { key: 'disk', label: 'Disk', value: Number(data.disk && data.disk.percent) }
  ];
  const now = Date.now();
  metrics.forEach(metric => {
    const threshold = Number(state.alertConfig[metric.key]);
    if (!Number.isFinite(metric.value) || !Number.isFinite(threshold)) return;
    state.alertCounters[metric.key] = metric.value >= threshold ? (state.alertCounters[metric.key] || 0) + 1 : 0;
    const cooldownElapsed = now - (state.alertLastFired[metric.key] || 0) >= 60000;
    if (state.alertCounters[metric.key] >= Number(state.alertConfig.consecutive) && cooldownElapsed) {
      state.alertLastFired[metric.key] = now;
      const alert = {
        at: new Date(now).toISOString(),
        key: metric.key,
        label: metric.label,
        value: Math.round(metric.value * 10) / 10,
        threshold
      };
      state.alerts.unshift(alert);
      state.alerts = state.alerts.slice(0, 100);
      addLog('WARN', metric.label + ' usage reached ' + alert.value + '% (threshold ' + threshold + '%).');
      if (window.Notification && Notification.permission === 'granted') {
        try { new Notification('NEXUS resource alert', { body: metric.label + ' usage is ' + alert.value + '%' }); } catch (_) {}
      }
      renderRecorderAlerts();
    }
  });
}

function renderRecorderAlerts() {
  const container = document.getElementById('recorder-alert-list');
  if (!container) return;
  if (!state.alerts.length) {
    container.innerHTML = '<p class="empty-state">No threshold alerts have fired in this browser session.</p>';
    return;
  }
  container.innerHTML = state.alerts.slice(0, 20).map(alert =>
    '<article class="alert-row"><time>' + escapeHTML(new Date(alert.at).toLocaleString()) + '</time><strong>' +
    escapeHTML(alert.label) + ' threshold reached</strong><p>' + Number(alert.value).toFixed(1) +
    '% used · configured threshold ' + Number(alert.threshold).toFixed(0) + '%</p></article>'
  ).join('');
}

async function enableRecorderNotifications() {
  if (!('Notification' in window)) {
    window.alert('Desktop notifications are not supported by this browser.');
    return;
  }
  try {
    const permission = await Notification.requestPermission();
    if (permission === 'granted') window.alert('Desktop notifications enabled for NEXUS alerts.');
    else window.alert('Notification permission was not granted. In-app alerts will still work.');
  } catch (_) {
    window.alert('The browser could not enable desktop notifications. In-app alerts will still work.');
  }
}

function flattenProcessTree(nodes, output) {
  (nodes || []).forEach(node => {
    output.push({
      pid: Number(node.pid), name: node.name || 'Unknown', cpu: Number(node.cpu) || 0,
      ram_mb: Number(node.ram_mb) || 0, status: node.status || 'unknown',
      can_terminate: Boolean(node.can_terminate)
    });
    flattenProcessTree(node.children || [], output);
  });
  return output;
}

function processTreeNodeMarkup(node, depth) {
  const title = '<span class="tree-pid">PID ' + Number(node.pid) + '</span> <span class="tree-name">' +
    escapeHTML(node.name) + '</span><span class="tree-meta"><span>CPU ' + Number(node.cpu).toFixed(1) +
    '%</span><span>RAM ' + Number(node.ram_mb).toFixed(1) + ' MB</span><span>' +
    escapeHTML(node.status || 'unknown') + '</span></span>';
  const children = Array.isArray(node.children) ? node.children : [];
  if (!children.length) return '<li><div class="tree-leaf">' + title + '</div></li>';
  const descendants = children.map(child => processTreeNodeMarkup(child, depth + 1)).join('');
  return '<li><details' + (depth < 1 ? ' open' : '') + '><summary>' + title +
    '</summary><ul>' + descendants + '</ul></details></li>';
}

async function loadProcessTree() {
  const container = document.getElementById('process-tree');
  if (!container) return;
  container.innerHTML = '<p class="muted">Refreshing process relationships…</p>';
  try {
    const payload = await api('/process-tree?limit=500');
    state.processTree = Array.isArray(payload.items) ? payload.items : [];
    state.processes = flattenProcessTree(state.processTree, []);
    setText('process-tree-count', String(payload.count || state.processes.length) + (payload.truncated ? ' · LIMITED' : ' PROCESSES'));
    container.innerHTML = state.processTree.length
      ? '<ul class="process-tree-list">' + state.processTree.map(node => processTreeNodeMarkup(node, 0)).join('') + '</ul>'
      : '<p class="empty-state">No accessible processes were returned.</p>';
    if (payload.truncated) container.insertAdjacentHTML('beforeend', '<p class="table-note">The snapshot reached its configured process limit; not every process is shown.</p>');
  } catch (error) {
    container.innerHTML = '<p class="empty-state error-text">' + escapeHTML(error.message) + '</p>';
  }
}

function setProcessView(view) {
  state.processView = view === 'tree' ? 'tree' : 'list';
  const list = document.getElementById('process-list-view');
  const tree = document.getElementById('process-tree-view');
  if (list) list.hidden = state.processView !== 'list';
  if (tree) tree.hidden = state.processView !== 'tree';
  document.querySelectorAll('[data-action="process-list-view"], [data-action="process-tree-view"]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.getAttribute('data-action') === 'process-' + state.processView + '-view'));
  });
  if (state.processView === 'tree') loadProcessTree(); else loadProcesses();
}

function downloadRecorderFile(filename, blob) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function exportRecorderSession(format) {
  try {
    if (format === 'csv') {
      const response = await fetch(API_BASE + '/history/export?format=csv&window=24h&limit=2000');
      if (!response.ok) {
        let message = 'Export failed (' + response.status + ')';
        try { const payload = await response.json(); if (payload.detail) message = payload.detail; } catch (_) {}
        throw new Error(message);
      }
      const blob = await response.blob();
      downloadRecorderFile('nexus-session-telemetry.csv', blob);
      addLog('INFO', 'Exported telemetry samples as CSV.');
      return;
    }
    const payload = await api('/history?window=24h&limit=2000');
    const exportData = {
      application: 'NEXUS-DASH',
      exported_at: new Date().toISOString(),
      history_window: '24h',
      telemetry_samples: payload.samples || [],
      browser_session_events: state.logs,
      resource_alerts: state.alerts,
      alert_settings: state.alertConfig,
      process_snapshot: state.processes.map(process => ({
        pid: process.pid, name: process.name, cpu: process.cpu, ram_mb: process.ram_mb,
        status: process.status, can_terminate: process.can_terminate
      }))
    };
    downloadRecorderFile(
      'nexus-session-' + new Date().toISOString().replace(/[:.]/g, '-') + '.json',
      new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json;charset=utf-8' })
    );
    addLog('INFO', 'Exported Flight Recorder session JSON.');
  } catch (error) {
    addLog('ERROR', 'Session export failed: ' + error.message);
    window.alert('Could not export the session: ' + error.message);
  }
}
