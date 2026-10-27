// NEXUS // CORE DASHBOARD — dependency-free, accessible frontend.
const API_BASE = 'http://127.0.0.1:8000/api';
const POLL_INTERVAL_MS = 2000;
const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: '◈' },
  { id: 'processes', label: 'Processes', icon: '▤' },
  { id: 'analytics', label: 'Analytics', icon: '◉' },
  { id: 'flight-recorder', label: 'Flight Recorder', icon: '◷' },
  { id: 'diagnostics', label: 'Bottleneck Detective', icon: '⌁' },
  { id: 'system', label: 'System Core', icon: '⌘' },
  { id: 'security', label: 'Security', icon: '⬡' },
  { id: 'terminal', label: 'Diagnostic Terminal', icon: '>_' },
  { id: 'logs', label: 'Session Logs', icon: '≡' }
];
const app = document.getElementById('app');
const state = {
  tab: 'dashboard', stats: null, processes: [], history: [], logs: [],
  theme: 'dark', connection: 'unknown', statsTimer: null, processTimer: null, historyTimer: null, diagnosticsTimer: null,
  previousNetwork: null, networkRates: { sent: 0, received: 0 }, processFilter: '',
  recorderHistory: [], processTree: [], processView: 'list', alerts: [], diagnostics: null, diagnosticsWindow: '1h',
  alertConfig: { cpu: 90, ram: 90, disk: 95, consecutive: 3 }, alertCounters: {}, alertLastFired: {}
};

function escapeHTML(value) {
  return String(value === null || value === undefined ? '' : value)
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
function formatBytesPerSecond(bytes) {
  const value = Math.max(0, Number(bytes) || 0);
  if (value >= 1048576) return (value / 1048576).toFixed(2) + ' MB/s';
  if (value >= 1024) return (value / 1024).toFixed(1) + ' KB/s';
  return value.toFixed(0) + ' B/s';
}
function formatDuration(seconds) {
  let value = Math.max(0, Math.floor(Number(seconds) || 0));
  const days = Math.floor(value / 86400);
  value %= 86400;
  const hours = Math.floor(value / 3600);
  value %= 3600;
  const minutes = Math.floor(value / 60);
  const parts = [];
  if (days) parts.push(days + 'd');
  if (hours || days) parts.push(hours + 'h');
  parts.push(minutes + 'm');
  return parts.join(' ');
}
function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}
function clamp(value) { return Math.max(0, Math.min(100, Number(value) || 0)); }
function setProgress(id, percent) {
  const element = document.getElementById(id);
  if (element) element.style.width = clamp(percent) + '%';
}
function addLog(level, message) {
  const now = new Date();
  state.logs.unshift({ time: now.toLocaleTimeString([], { hour12: false }), date: now.toISOString(), level, message });
  state.logs = state.logs.slice(0, 100);
  if (state.tab === 'logs') renderLogs();
  if (state.tab === 'dashboard') renderActivity();
}
function setConnection(connected, detail) {
  const next = connected ? 'online' : 'offline';
  const changed = state.connection !== next;
  state.connection = next;
  const dot = document.getElementById('connection-dot');
  const label = document.getElementById('connection-label');
  if (dot) dot.className = 'status-dot ' + (connected ? 'is-online' : 'is-offline');
  if (label) label.textContent = connected ? 'API ONLINE' : 'API OFFLINE';
  if (changed && next !== 'unknown') addLog(connected ? 'INFO' : 'WARN', connected ? 'Local system API connection restored.' : 'Local system API is unreachable.');
  if (!connected && detail) setText('connection-note', detail);
}
async function api(path, options) {
  const settings = Object.assign({ method: 'GET', headers: {} }, options || {});
  const controller = new AbortController();
  const timeout = window.setTimeout(function () { controller.abort(); }, 6000);
  settings.signal = controller.signal;
  try {
    const response = await fetch(API_BASE + path, settings);
    let payload = {};
    try { payload = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(payload.detail || payload.message || ('Request failed (' + response.status + ')'));
    return payload;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The local API request timed out.');
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

function buildShell() {
  const nav = NAV_ITEMS.map(function (item) {
    return '<li><button class="nav-item" type="button" data-tab="' + item.id +
      '" aria-current="' + (item.id === state.tab ? 'page' : 'false') + '">' +
      '<span class="nav-icon" aria-hidden="true">' + item.icon + '</span><span>' + item.label + '</span></button></li>';
  }).join('');
  app.innerHTML =
    '<aside class="sidebar" id="sidebar" aria-label="Main navigation">' +
      '<a class="brand" href="#" data-action="home" aria-label="NEXUS dashboard home"><span class="brand-mark" aria-hidden="true">N</span>' +
      '<span class="brand-copy"><strong>NEXUS</strong><small>CORE / LOCAL MONITOR</small></span></a>' +
      '<div class="sidebar-label">WORKSPACE</div><nav><ul class="nav-menu">' + nav + '</ul></nav>' +
      '<div class="sidebar-bottom"><div class="local-badge"><span class="pulse-dot"></span><div><strong>LOCAL NODE</strong><small>Loopback mode</small></div></div>' +
      '<p class="build-label">NEXUS CORE <span>v2.0.0</span></p></div></aside>' +
    '<button class="sidebar-scrim" type="button" data-action="close-menu" aria-label="Close navigation"></button>' +
    '<section class="workspace"><header class="topbar"><div class="topbar-left">' +
      '<button class="icon-button menu-toggle" type="button" data-action="toggle-menu" aria-label="Toggle navigation" aria-expanded="false">☰</button>' +
      '<div><div class="eyebrow">SYSTEM / OVERVIEW</div><h1 id="page-title">Dashboard</h1></div></div>' +
      '<div class="topbar-actions"><div class="connection-pill"><span class="status-dot" id="connection-dot"></span><span id="connection-label">CONNECTING</span></div>' +
      '<button class="icon-button" type="button" data-action="refresh" aria-label="Refresh current view" title="Refresh">↻</button>' +
      '<button class="icon-button" type="button" data-action="theme" aria-label="Toggle color theme" title="Toggle theme">◐</button></div></header>' +
      '<main class="main-content" id="main-content" tabindex="-1"></main>' +
      '<footer class="footer"><span>NEXUS // LOCAL SYSTEM TELEMETRY</span><span id="last-updated">WAITING FOR METRICS</span></footer></section>';
  document.body.classList.toggle('light-mode', state.theme === 'light');
  bindEvents();
}
function bindEvents() {
  app.addEventListener('click', handleClick);
  app.addEventListener('input', function (event) {
    if (event.target && event.target.id === 'process-search') {
      state.processFilter = event.target.value;
      renderProcessRows();
    }
  });
  app.addEventListener('change', function (event) {
    const target = event.target;
    if (target && target.id === 'history-window') loadRecorderHistory();
    if (target && target.id === 'diagnostic-window') { state.diagnosticsWindow = ['15m', '1h', '6h', '24h'].includes(target.value) ? target.value : '1h'; loadDiagnostics(); }
    if (target && ['alert-cpu', 'alert-ram', 'alert-disk', 'alert-consecutive'].includes(target.id)) saveRecorderSettings();
  });
  app.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') closeMenu();
    if (event.key === 'Enter' && event.target && event.target.id === 'terminal-input') {
      event.preventDefault();
      runTerminal();
    }
  });
}
function handleClick(event) {
  const target = event.target.closest('[data-tab], [data-action]');
  if (!target) return;
  if (target.hasAttribute('data-tab')) { switchTab(target.getAttribute('data-tab')); return; }
  const action = target.getAttribute('data-action');
  if (action === 'toggle-menu') {
    const open = document.getElementById('sidebar').classList.toggle('open');
    document.querySelector('.menu-toggle').setAttribute('aria-expanded', String(open));
  } else if (action === 'close-menu') closeMenu();
  else if (action === 'theme') {
    state.theme = state.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('nexus-theme', state.theme); } catch (_) {}
    document.body.classList.toggle('light-mode', state.theme === 'light');
  } else if (action === 'refresh') refreshCurrentView();
  else if (action === 'home') { event.preventDefault(); switchTab('dashboard'); }
  else if (action === 'terminal-send') runTerminal();
  else if (action === 'terminal-clear') {
    const output = document.getElementById('terminal-output');
    if (output) output.replaceChildren();
  } else if (action === 'process-refresh') {
    if (state.processView === 'tree') loadProcessTree(); else loadProcesses();
  } else if (action === 'process-tree-view') setProcessView('tree');
  else if (action === 'process-list-view') setProcessView('list');
  else if (action === 'export-session-json') exportRecorderSession('json');
  else if (action === 'export-session-csv') exportRecorderSession('csv');
  else if (action === 'enable-notifications') enableRecorderNotifications();
  else if (action === 'diagnostic-refresh') loadDiagnostics();
  else if (action === 'export-diagnostic-report') exportDiagnosticReport();
  else if (action === 'clear-logs') {
    state.logs = [];
    renderLogs();
  } else if (action === 'terminate-process') terminateProcess(Number(target.getAttribute('data-pid')));
}
function closeMenu() {
  const sidebar = document.getElementById('sidebar');
  if (sidebar) sidebar.classList.remove('open');
  const toggle = document.querySelector('.menu-toggle');
  if (toggle) toggle.setAttribute('aria-expanded', 'false');
}
function switchTab(tab) {
  if (!NAV_ITEMS.some(function (item) { return item.id === tab; })) return;
  state.tab = tab;
  closeMenu();
  document.querySelectorAll('.nav-item').forEach(function (button) {
    button.setAttribute('aria-current', button.getAttribute('data-tab') === tab ? 'page' : 'false');
  });
  const item = NAV_ITEMS.find(function (entry) { return entry.id === tab; });
  document.getElementById('page-title').textContent = item.label;
  renderContent();
  addLog('INFO', 'Opened ' + item.label + ' view.');
  startPolling();
  document.getElementById('main-content').focus({ preventScroll: true });
}
function metricCard(title, valueId, value, metaId, meta, kind) {
  const icons = { cpu: '◈', ram: '▥', gpu: '⬡', network: '↕', samples: '◎', time: '◷' };
  return '<section class="metric-card metric-' + kind + '"><div class="metric-top"><span>' + title +
    '</span><span class="metric-glyph" aria-hidden="true">' + (icons[kind] || '◈') +
    '</span></div><div class="metric-value" id="' + valueId + '">' + value +
    '</div><div class="metric-meta" id="' + metaId + '">' + meta + '</div><div class="metric-accent"></div></section>';
}
function securityItem(number, title, copy) {
  return '<section class="panel security-item"><span class="security-number">' + number + '</span><div><h3>' +
    title + '</h3><p>' + copy + '</p></div><span class="security-check" aria-hidden="true">✓</span></section>';
}

function renderContent() {
  const main = document.getElementById('main-content');
  if (state.tab === 'dashboard') {
    main.innerHTML =
      '<section class="page-intro"><div><div class="eyebrow">LIVE TELEMETRY / LOCAL MACHINE</div><h2>System overview</h2><p>Resource utilisation from the machine running the local NEXUS service.</p></div><div class="live-tag"><span class="pulse-dot"></span> LIVE SAMPLING</div></section>' +
      '<div class="metrics-grid">' +
      metricCard('CPU LOAD', 'cpu-value', '--%', 'cpu-meta', 'CPU cores', 'cpu') +
      metricCard('MEMORY', 'ram-value', '-- / -- GiB', 'ram-meta', 'System RAM', 'ram') +
      metricCard('GPU MEMORY', 'gpu-value', 'N/A', 'gpu-meta', 'Optional NVIDIA telemetry', 'gpu') +
      metricCard('NETWORK RATE', 'network-value', '-- / --', 'network-meta', 'Upload / download', 'network') + '</div>' +
      '<div class="content-grid"><section class="panel span-2"><div class="panel-heading"><div><span class="eyebrow">PERFORMANCE</span><h3>CPU utilisation</h3></div><span class="panel-tag">RECENT SAMPLES</span></div><div id="cpu-chart" class="bar-chart" role="img" aria-label="Recent CPU utilisation samples"></div><div class="chart-axis"><span>Older samples</span><span>Latest</span></div></section>' +
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">STORAGE</span><h3>System disk</h3></div><span id="disk-percent" class="big-inline">--%</span></div><div class="progress-track"><div id="disk-bar" class="progress-value"></div></div><div id="disk-meta" class="muted">Waiting for data</div><div class="divider"></div><div class="panel-heading compact"><span>Memory pressure</span><strong id="ram-inline">--%</strong></div><div class="progress-track"><div id="ram-bar" class="progress-value"></div></div></section>' +
      '<section class="panel span-2"><div class="panel-heading"><div><span class="eyebrow">SESSION EVENTS</span><h3>Recent activity</h3></div><button class="text-button" type="button" data-tab="logs">View all →</button></div><ul id="activity-list" class="activity-list"></ul></section>' +
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">CONNECTION</span><h3>Local API</h3></div><span id="api-state" class="state-chip">CHECKING</span></div><p id="connection-note" class="muted">Connecting to 127.0.0.1:8000…</p><div class="divider"></div><div class="mini-facts"><span>Transport</span><strong>HTTP / loopback</strong><span>Refresh interval</span><strong>2 seconds</strong></div></section></div>';
    updateDashboard();
  } else if (state.tab === 'analytics') {
    main.innerHTML = '<section class="page-intro"><div><div class="eyebrow">TELEMETRY / TRENDS</div><h2>Analytics</h2><p>Charts use samples collected during this browser session; no historical dataset is fabricated.</p></div></section>' +
      '<div class="metrics-grid compact-metrics">' + metricCard('CURRENT CPU','analytics-cpu','--%','analytics-cpu-meta','CPU load','cpu') +
      metricCard('CURRENT RAM','analytics-ram','--%','analytics-ram-meta','RAM utilisation','ram') +
      metricCard('SAMPLES','analytics-count','0','analytics-count-meta','In this session','samples') +
      metricCard('SAMPLE WINDOW','analytics-window','—','analytics-window-meta','Approximate duration','time') +
      '</div><section class="panel"><div class="panel-heading"><div><span class="eyebrow">RECENT HISTORY</span><h3>CPU and memory</h3></div><span class="panel-tag">SESSION ONLY</span></div><div id="analytics-chart" class="history-chart"></div><div class="chart-legend"><span><i class="legend-dot cpu-legend"></i>CPU</span><span><i class="legend-dot ram-legend"></i>RAM</span></div></section>';
    updateAnalytics();
  } else if (state.tab === 'flight-recorder') {
    renderFlightRecorder();
  } else if (state.tab === 'diagnostics') {
    renderDiagnostics();
  } else if (state.tab === 'processes') {
    main.innerHTML = '<section class="page-intro"><div><div class="eyebrow">PROCESS CONTROL / LOCAL USER</div><h2>Process manager</h2><p>Inspect process snapshots. Termination is restricted to processes owned by your current OS user; protected processes cannot be terminated.</p></div><button class="primary-button" type="button" data-action="process-refresh">↻ Refresh</button></section>' +
      '<div class="view-switch"><button type="button" class="secondary-button" data-action="process-list-view" aria-pressed="true">List view</button><button type="button" class="secondary-button" data-action="process-tree-view" aria-pressed="false">Process tree</button></div>' +
      '<section class="panel" id="process-list-view"><div class="table-toolbar"><label class="search-box"><span aria-hidden="true">⌕</span><input id="process-search" type="search" placeholder="Filter by PID, name, or status…" autocomplete="off"></label><span id="process-count" class="panel-tag">LOADING</span></div>' +
      '<div class="table-scroll"><table><thead><tr><th>PID</th><th>Process</th><th>CPU</th><th>Memory</th><th>Status</th><th>Action</th></tr></thead><tbody id="process-list"><tr><td colspan="6" class="table-message">Loading process snapshot…</td></tr></tbody></table></div><p class="table-note">Process snapshots are best-effort. Operating-system permissions can hide details or deny termination.</p></section>' +
      '<section class="panel" id="process-tree-view" hidden><div class="panel-heading"><div><span class="eyebrow">PROCESS RELATIONSHIPS</span><h3>Parent / child tree</h3></div><span id="process-tree-count" class="panel-tag">LOADING</span></div><p class="table-note">A bounded snapshot; inaccessible or very short-lived processes may be omitted. Process-tree view is observational.</p><div id="process-tree" class="process-tree"><p class="muted">Loading process relationships…</p></div></section>';
    state.processFilter = '';
    const processListView = document.getElementById('process-list-view');
    const processTreeView = document.getElementById('process-tree-view');
    if (processListView) processListView.hidden = state.processView !== 'list';
    if (processTreeView) processTreeView.hidden = state.processView !== 'tree';
    document.querySelectorAll('[data-action="process-list-view"], [data-action="process-tree-view"]').forEach(function (button) {
      button.setAttribute('aria-pressed', String(button.getAttribute('data-action') === 'process-' + state.processView + '-view'));
    });
  } else if (state.tab === 'system') {
    main.innerHTML = '<section class="page-intro"><div><div class="eyebrow">MACHINE PROFILE / RUNTIME</div><h2>System core</h2><p>Details reported by the operating system running the backend.</p></div></section><div class="system-grid" id="system-details"><section class="panel"><p class="muted">Waiting for system telemetry…</p></section></div>';
    updateSystem();
  } else if (state.tab === 'security') {
    main.innerHTML = '<section class="page-intro"><div><div class="eyebrow">LOCAL DEFENCE / CONFIGURATION</div><h2>Security center</h2><p>This describes app safeguards; it is not a claim that the host is malware-free.</p></div></section>' +
      '<div class="security-banner"><span class="security-symbol">⬡</span><div><strong>Local monitoring mode</strong><p>The backend binds to loopback and rejects unapproved browser origins.</p></div></div><div class="security-grid">' +
      securityItem('01','Loopback binding','The bundled server starts on 127.0.0.1 only. Do not change this for internet-facing deployment.') +
      securityItem('02','Read-only diagnostic terminal','Exact commands map to Python diagnostics. Arbitrary shell execution and command chaining are not supported.') +
      securityItem('03','Restricted process termination','Protected PIDs are blocked, and only processes owned by the current OS user may be terminated.') +
      securityItem('04','Cross-origin guard','Browser origins are allowlisted. Credentialed CORS is disabled.') +
      '</div><p class="warning-note"><strong>Important:</strong> Loopback software still has local-user privileges. Keep the API on localhost and never expose port 8000 through a reverse proxy or port forward.</p>';
  } else if (state.tab === 'terminal') {
    main.innerHTML = '<section class="page-intro"><div><div class="eyebrow">DIAGNOSTICS / ALLOWLISTED COMMANDS</div><h2>Diagnostic terminal</h2><p>Read-only diagnostic commands only. This is not a general-purpose shell.</p></div><span class="panel-tag">NO SHELL EXECUTION</span></section>' +
      '<section class="terminal-panel"><div class="terminal-topline"><span class="terminal-lights"><i></i><i></i><i></i></span><span>NEXUS_DIAGNOSTICS / LOCAL</span><button type="button" class="text-button" data-action="terminal-clear">Clear</button></div>' +
      '<div id="terminal-output" class="terminal-output" role="log" aria-live="polite"><p class="terminal-muted">NEXUS diagnostic console · v1.2</p><p class="terminal-muted">Type <strong>help</strong> to list safe, read-only commands.</p></div>' +
      '<div class="terminal-form"><label for="terminal-input" class="terminal-prompt">nexus<span>›</span></label><input id="terminal-input" type="text" maxlength="120" autocomplete="off" spellcheck="false" placeholder="help"><button type="button" class="primary-button" data-action="terminal-send">Run</button></div><p class="terminal-footnote">Commands run as the current local user. Never paste secrets into diagnostic output.</p></section>';
  } else if (state.tab === 'logs') {
    main.innerHTML = '<section class="page-intro"><div><div class="eyebrow">BROWSER SESSION / EVENTS</div><h2>Session logs</h2><p>Events captured while this page is open. They exist in memory and are cleared on reload.</p></div><button class="secondary-button" type="button" data-action="clear-logs">Clear logs</button></section><section class="panel"><div id="logs-list" class="logs-list"></div></section>';
    renderLogs();
  }
}
function updateDashboard() {
  const data = state.stats;
  if (!data) return;
  setText('cpu-value', data.cpu.percent.toFixed(1) + '%');
  setText('cpu-meta', data.cpu.cores + ' logical / ' + data.cpu.physical_cores + ' physical cores');
  setText('ram-value', data.ram.used_gb.toFixed(1) + ' / ' + data.ram.total_gb.toFixed(1) + ' GiB');
  setText('ram-meta', data.ram.percent.toFixed(1) + '% utilised');
  setText('gpu-value', data.gpu.total_gb === null ? 'N/A' : data.gpu.used_gb.toFixed(1) + ' / ' + data.gpu.total_gb.toFixed(1) + ' GiB');
  setText('gpu-meta', data.gpu.status === 'Available' ? 'NVIDIA memory telemetry' : 'Optional NVIDIA telemetry unavailable');
  setText('network-value', '↑ ' + formatBytesPerSecond(state.networkRates.sent) + ' / ↓ ' + formatBytesPerSecond(state.networkRates.received));
  setText('network-meta', 'Live rate · totals ' + data.network.sent_mb.toFixed(1) + ' / ' + data.network.recv_mb.toFixed(1) + ' MB');
  setText('disk-percent', data.disk.percent.toFixed(1) + '%');
  setText('disk-meta', data.disk.used_gb.toFixed(1) + ' / ' + data.disk.total_gb.toFixed(1) + ' GiB used');
  setText('ram-inline', data.ram.percent.toFixed(1) + '%');
  setProgress('disk-bar', data.disk.percent);
  setProgress('ram-bar', data.ram.percent);
  drawBars('cpu-chart', state.history.map(function (item) { return item.cpu; }), 'CPU');
  setText('api-state', 'CONNECTED');
  const chip = document.getElementById('api-state');
  if (chip) chip.className = 'state-chip is-online';
  setText('connection-note', 'Local metrics received at ' + new Date(data.sampled_at).toLocaleTimeString());
  setText('last-updated', 'UPDATED ' + new Date(data.sampled_at).toLocaleTimeString());
  renderActivity();
}
function updateAnalytics() {
  const data = state.stats;
  if (data) {
    setText('analytics-cpu', data.cpu.percent.toFixed(1) + '%');
    setText('analytics-cpu-meta', data.cpu.cores + ' logical cores');
    setText('analytics-ram', data.ram.percent.toFixed(1) + '%');
    setText('analytics-ram-meta', data.ram.used_gb.toFixed(1) + ' / ' + data.ram.total_gb.toFixed(1) + ' GiB');
  }
  setText('analytics-count', String(state.history.length));
  setText('analytics-count-meta', 'Collected in this session');
  const seconds = state.history.length > 1 ? Math.round((state.history[state.history.length - 1].at - state.history[0].at) / 1000) : 0;
  setText('analytics-window', state.history.length < 2 ? '—' : formatDuration(seconds));
  setText('analytics-window-meta', state.history.length < 2 ? 'Waiting for samples' : 'Approximate sample window');
  const chart = document.getElementById('analytics-chart');
  if (!chart) return;
  if (!state.history.length) { chart.innerHTML = '<p class="empty-state">Metrics will appear after the first successful sample.</p>'; return; }
  chart.innerHTML = state.history.map(function (item) {
    const stamp = new Date(item.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    return '<div class="history-row"><time>' + stamp + '</time><span class="history-label">CPU</span><div class="history-track"><i class="history-cpu" style="width:' + clamp(item.cpu) +
      '%"></i></div><strong>' + item.cpu.toFixed(0) + '%</strong><span class="history-label">RAM</span><div class="history-track"><i class="history-ram" style="width:' + clamp(item.ram) +
      '%"></i></div><strong>' + item.ram.toFixed(0) + '%</strong></div>';
  }).join('');
}
function updateSystem() {
  const container = document.getElementById('system-details');
  const data = state.stats;
  if (!container || !data) return;
  const s = data.system;
  const details = [
    ['Hostname', s.hostname], ['Operating system', s.platform + ' ' + s.platform_release],
    ['Architecture', s.architecture], ['Python runtime', s.python_version], ['Current user', s.user],
    ['Uptime', s.uptime], ['Boot time (UTC)', new Date(s.boot_time).toLocaleString()],
    ['Logical CPU cores', String(data.cpu.cores)], ['Physical CPU cores', String(data.cpu.physical_cores)],
    ['RAM capacity', data.ram.total_gb.toFixed(2) + ' GiB'], ['System disk', data.disk.total_gb.toFixed(2) + ' GiB'],
    ['GPU telemetry', data.gpu.status]
  ];
  container.innerHTML = details.map(function (item, index) {
    return '<section class="panel system-fact"><span class="eyebrow">' + String(index + 1).padStart(2, '0') +
      ' / SYSTEM PROPERTY</span><p>' + escapeHTML(item[0]) + '</p><strong>' + escapeHTML(item[1]) + '</strong></section>';
  }).join('');
}
function renderActivity() {
  const list = document.getElementById('activity-list');
  if (!list) return;
  if (!state.logs.length) { list.innerHTML = '<li class="empty-state">No session events yet.</li>'; return; }
  list.innerHTML = state.logs.slice(0, 5).map(function (item) {
    return '<li class="activity-item"><span class="activity-level level-' + item.level.toLowerCase() + '">' + escapeHTML(item.level) +
      '</span><span class="activity-message">' + escapeHTML(item.message) + '</span><time>' + escapeHTML(item.time) + '</time></li>';
  }).join('');
}
function renderLogs() {
  const list = document.getElementById('logs-list');
  if (!list) return;
  if (!state.logs.length) { list.innerHTML = '<p class="empty-state">No events in this browser session yet.</p>'; return; }
  list.innerHTML = state.logs.map(function (item) {
    return '<article class="log-row"><time>' + escapeHTML(item.date) + '</time><span class="activity-level level-' +
      item.level.toLowerCase() + '">' + escapeHTML(item.level) + '</span><p>' + escapeHTML(item.message) + '</p></article>';
  }).join('');
}
function drawBars(containerId, values, label) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!values.length) { container.innerHTML = '<p class="empty-state">Collecting samples…</p>'; return; }
  container.innerHTML = values.slice(-24).map(function (value) {
    const bounded = clamp(value);
    return '<div class="bar-column"><div class="bar-value">' + Math.round(bounded) + '%</div><div class="bar-track"><i class="bar-fill" style="height:' +
      bounded + '%" title="' + label + ' ' + bounded.toFixed(1) + '%"></i></div></div>';
  }).join('');
}
async function fetchStats() {
  try {
    const data = await api('/stats');
    const now = Date.now();
    if (state.previousNetwork) {
      const elapsed = Math.max((now - state.previousNetwork.at) / 1000, 0.1);
      state.networkRates.sent = Math.max(0, (data.network.sent_bytes - state.previousNetwork.sent) / elapsed);
      state.networkRates.received = Math.max(0, (data.network.recv_bytes - state.previousNetwork.received) / elapsed);
    }
    state.previousNetwork = { at: now, sent: data.network.sent_bytes, received: data.network.recv_bytes };
    state.stats = data;
    evaluateRecorderAlerts(data);
    state.history.push({ at: now, cpu: data.cpu.percent, ram: data.ram.percent });
    state.history = state.history.slice(-30);
    setConnection(true);
    if (state.tab === 'dashboard') updateDashboard();
    else if (state.tab === 'analytics') updateAnalytics();
    else if (state.tab === 'system') updateSystem();
    else if (state.tab === 'flight-recorder') renderRecorderAlerts();
  } catch (error) {
    setConnection(false, error.message + ' Start the backend with: python server.py');
    const chip = document.getElementById('api-state');
    if (chip) { chip.textContent = 'OFFLINE'; chip.className = 'state-chip is-offline'; }
    setText('connection-note', error.message + ' Start the backend with: python server.py');
    setText('last-updated', 'API UNAVAILABLE');
  }
}
function startPolling() {
  if (state.statsTimer) window.clearInterval(state.statsTimer);
  if (state.processTimer) window.clearInterval(state.processTimer);
  if (state.historyTimer) window.clearInterval(state.historyTimer);
  if (state.diagnosticsTimer) window.clearInterval(state.diagnosticsTimer);
  state.statsTimer = null;
  state.processTimer = null;
  state.historyTimer = null;
  state.diagnosticsTimer = null;
  if (['dashboard', 'analytics', 'system', 'flight-recorder'].includes(state.tab)) {
    fetchStats();
    state.statsTimer = window.setInterval(fetchStats, POLL_INTERVAL_MS);
  }
  if (state.tab === 'flight-recorder') {
    loadRecorderHistory();
    state.historyTimer = window.setInterval(loadRecorderHistory, 15000);
  }
  if (state.tab === 'diagnostics') {
    loadDiagnostics();
    state.diagnosticsTimer = window.setInterval(loadDiagnostics, 30000);
  }
  if (state.tab === 'processes') {
    if (state.processView === 'tree') loadProcessTree(); else loadProcesses();
    state.processTimer = window.setInterval(function () {
      if (state.processView === 'tree') loadProcessTree(); else loadProcesses();
    }, 10000);
  }
}
async function loadProcesses() {
  try {
    const payload = await api('/processes?limit=100');
    state.processes = Array.isArray(payload.items) ? payload.items : [];
    renderProcessRows();
  } catch (error) {
    const tbody = document.getElementById('process-list');
    if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="table-message error-text">' + escapeHTML(error.message) + '</td></tr>';
  }
}
function renderProcessRows() {
  const tbody = document.getElementById('process-list');
  if (!tbody) return;
  const query = state.processFilter.trim().toLowerCase();
  const rows = state.processes.filter(function (process) {
    return [process.pid, process.name, process.status].some(function (value) { return String(value).toLowerCase().includes(query); });
  });
  setText('process-count', String(rows.length) + ' MATCHING');
  if (!rows.length) { tbody.innerHTML = '<tr><td colspan="6" class="table-message">No processes match this filter.</td></tr>'; return; }
  tbody.innerHTML = rows.map(function (process) {
    const action = process.can_terminate
      ? '<button type="button" class="danger-button" data-action="terminate-process" data-pid="' + Number(process.pid) + '">Terminate</button>'
      : '<span class="protected-label">Protected</span>';
    return '<tr><td class="mono-cell">' + Number(process.pid) + '</td><td class="process-name">' + escapeHTML(process.name) +
      '</td><td>' + Number(process.cpu).toFixed(1) + '%</td><td>' + Number(process.ram_mb).toFixed(1) +
      ' MB</td><td><span class="process-status">' + escapeHTML(process.status) + '</span></td><td>' + action + '</td></tr>';
  }).join('');
}
async function terminateProcess(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return;
  const process = state.processes.find(function (item) { return item.pid === pid; });
  if (!process || !process.can_terminate) { addLog('WARN', 'Blocked termination request for protected process ' + pid + '.'); return; }
  if (!window.confirm('Terminate ' + process.name + ' (PID ' + pid + ')? Unsaved work may be lost.')) return;
  try {
    await api('/process/kill', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pid }) });
    addLog('WARN', 'Termination requested for ' + process.name + ' (PID ' + pid + ').');
    await loadProcesses();
  } catch (error) {
    addLog('ERROR', 'Could not terminate PID ' + pid + ': ' + error.message);
    window.alert('Process was not terminated: ' + error.message);
  }
}
function appendTerminal(text, tone) {
  const output = document.getElementById('terminal-output');
  if (!output) return;
  const line = document.createElement('p');
  line.className = 'terminal-line' + (tone ? ' terminal-' + tone : '');
  line.textContent = text;
  output.appendChild(line);
  output.scrollTop = output.scrollHeight;
}
async function runTerminal() {
  const input = document.getElementById('terminal-input');
  if (!input) return;
  const command = input.value.trim();
  if (!command) return;
  input.value = '';
  if (command.toLowerCase() === 'clear') {
    const output = document.getElementById('terminal-output');
    if (output) output.replaceChildren();
    return;
  }
  appendTerminal('nexus › ' + command, 'command');
  const button = document.querySelector('[data-action="terminal-send"]');
  if (button) button.disabled = true;
  try {
    const result = await api('/terminal', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command }) });
    if (result.stdout) appendTerminal(result.stdout, 'stdout');
    if (result.stderr) appendTerminal(result.stderr, 'error');
    if (result.returncode !== 0 && !result.stderr) appendTerminal('Exited with code ' + result.returncode, 'error');
  } catch (error) { appendTerminal(error.message, 'error'); }
  finally { if (button) button.disabled = false; input.focus(); }
}
async function refreshCurrentView() {
  if (['dashboard', 'analytics', 'system', 'flight-recorder'].includes(state.tab)) await fetchStats();
  if (state.tab === 'flight-recorder') await loadRecorderHistory();
  if (state.tab === 'diagnostics') await loadDiagnostics();
  if (state.tab === 'processes') {
    if (state.processView === 'tree') await loadProcessTree(); else await loadProcesses();
  }
}
function init() {
  try {
    const saved = localStorage.getItem('nexus-theme');
    if (saved === 'light' || saved === 'dark') state.theme = saved;
  } catch (_) {}
  loadRecorderSettings();
  buildShell();
  addLog('INFO', 'NEXUS dashboard session started.');
  renderContent();
  startPolling();
}
window.addEventListener('beforeunload', function () {
  if (state.statsTimer) window.clearInterval(state.statsTimer);
  if (state.processTimer) window.clearInterval(state.processTimer);
  if (state.historyTimer) window.clearInterval(state.historyTimer);
  if (state.diagnosticsTimer) window.clearInterval(state.diagnosticsTimer);
});
init();
