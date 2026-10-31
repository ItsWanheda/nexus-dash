// NEXUS // Storage view. Rates are derived from counter deltas and are unavailable until sampled.
function storageDisplayRate(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'Unavailable';
  return formatBytesPerSecond(Number(value));
}
function storageDisplayNumber(value, unit, digits) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'Unavailable';
  return Number(value).toFixed(digits === undefined ? 1 : digits) + (unit ? ' ' + unit : '');
}
function storagePolyline(samples, field, maximum) {
  if (!samples.length) return '';
  let drawing = false;
  const commands = [];
  samples.forEach(function (sample, index) {
    const raw = sample[field];
    if (raw === null || raw === undefined || !Number.isFinite(Number(raw))) { drawing = false; return; }
    const x = samples.length === 1 ? 500 : 24 + (index / (samples.length - 1)) * 952;
    const value = Math.max(0, Number(raw));
    const y = 218 - Math.min(1, value / maximum) * 190;
    commands.push((drawing ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1));
    drawing = true;
  });
  return commands.join(' ');
}
function renderStorageChart(samples) {
  const container = document.getElementById('storage-history-chart');
  if (!container) return;
  if (!samples.length) {
    container.innerHTML = '<p class="empty-state">No disk I/O history yet. Keep NEXUS running to record actual counter samples.</p>';
    return;
  }
  const values = samples.reduce(function (all, sample) {
    all.push(Number(sample.disk_read_bytes_per_sec) || 0, Number(sample.disk_write_bytes_per_sec) || 0);
    return all;
  }, []);
  const maximum = Math.max(1024, ...values) * 1.1;
  const grid = [28, 75, 123, 170, 218].map(function (y) {
    return '<line class="flight-chart-grid" x1="24" y1="' + y + '" x2="976" y2="' + y + '"></line>';
  }).join('');
  container.innerHTML = '<svg class="flight-chart" viewBox="0 0 1000 245" role="img" aria-label="Historical disk read and write throughput">' +
    grid + '<path class="storage-chart-read" d="' + storagePolyline(samples, 'disk_read_bytes_per_sec', maximum) + '"></path>' +
    '<path class="storage-chart-write" d="' + storagePolyline(samples, 'disk_write_bytes_per_sec', maximum) + '"></path>' +
    '<text x="4" y="30" class="chart-svg-label">' + escapeHTML(formatBytesPerSecond(maximum)) + '</text>' +
    '<text x="8" y="224" class="chart-svg-label">0 B/s</text></svg><div class="chart-axis"><span>' +
    escapeHTML(new Date(samples[0].timestamp).toLocaleString()) + '</span><span>' +
    escapeHTML(new Date(samples[samples.length - 1].timestamp).toLocaleString()) + '</span></div>';
}
function renderStorage() {
  const main = document.getElementById('main-content');
  if (!main) return;
  state.storageWindow = state.storageWindow || '1h';
  main.innerHTML =
    '<section class="page-intro"><div><div class="eyebrow">STORAGE / I/O INTELLIGENCE</div><h2>Storage activity</h2><p>Separate drive capacity from actual read/write performance. Rates are calculated from OS counters; unsupported metrics are never inferred.</p></div><div class="live-tag"><span class="pulse-dot"></span> LIVE I/O</div></section>' +
    '<div class="storage-summary">' +
      '<section class="panel"><span>Read throughput</span><strong id="storage-read">Warming up</strong><small id="storage-read-meta">Disk reads</small></section>' +
      '<section class="panel"><span>Write throughput</span><strong id="storage-write">Warming up</strong><small id="storage-write-meta">Disk writes</small></section>' +
      '<section class="panel"><span>Read / write IOPS</span><strong id="storage-iops">Warming up</strong><small>Operations per second</small></section>' +
      '<section class="panel"><span>Activity / latency</span><strong id="storage-activity">Unavailable</strong><small id="storage-latency">Platform counters</small></section>' +
    '</div>' +
    '<section class="panel"><div class="storage-toolbar"><div><span class="eyebrow">HISTORICAL PERFORMANCE</span><h3>Read and write throughput</h3><p class="muted">Aggregate system counters recorded by the local Flight Recorder.</p></div><div class="flight-toolbar-actions"><label for="storage-history-window" class="muted">Window</label><select id="storage-history-window" class="flight-select"><option value="15m">15 minutes</option><option value="1h" selected>1 hour</option><option value="6h">6 hours</option><option value="24h">24 hours</option></select><button type="button" class="secondary-button" data-action="storage-refresh">↻ Refresh</button></div></div><div id="storage-history-chart" class="flight-chart-wrap"><p class="muted">Loading stored disk I/O samples…</p></div><div class="flight-legend"><span><i class="storage-read-legend"></i>Read</span><span><i class="storage-write-legend"></i>Write</span></div></section>' +
    '<section class="panel storage-table-panel"><div class="panel-heading"><div><span class="eyebrow">PHYSICAL DEVICES</span><h3>Per-drive I/O and health</h3></div><span id="storage-device-count" class="panel-tag">LOADING</span></div><div class="table-scroll"><table><thead><tr><th>Device</th><th>Read / write</th><th>IOPS</th><th>Activity</th><th>Latency</th><th>Temperature</th><th>SMART health</th></tr></thead><tbody id="storage-device-list"><tr><td colspan="7" class="table-message">Collecting device counters…</td></tr></tbody></table></div></section>' +
    '<section class="panel storage-table-panel"><div class="panel-heading"><div><span class="eyebrow">MOUNTED VOLUMES</span><h3>Drive capacity</h3></div><span id="storage-drive-count" class="panel-tag">LOADING</span></div><div class="table-scroll"><table><thead><tr><th>Mount</th><th>Device</th><th>Filesystem</th><th>Used</th><th>Free</th><th>Capacity</th></tr></thead><tbody id="storage-drive-list"><tr><td colspan="6" class="table-message">Collecting mounted volumes…</td></tr></tbody></table></div></section>' +
    '<section class="panel storage-table-panel"><div class="panel-heading"><div><span class="eyebrow">PROCESS I/O</span><h3>Top disk activity</h3></div><span class="panel-tag">LIVE SNAPSHOT</span></div><div class="table-scroll"><table><thead><tr><th>Process</th><th>PID</th><th>Read rate</th><th>Write rate</th><th>Read / write IOPS</th></tr></thead><tbody id="storage-process-list"><tr><td colspan="5" class="table-message">Collecting process I/O counters…</td></tr></tbody></table></div><p class="table-note">Per-process counters are best-effort and remain in memory only. Operating-system permissions and provider support can limit visibility.</p></section>' +
    '<p id="storage-capabilities" class="table-note">SMART health requires smartmontools and appropriate device permissions. Missing activity or latency counters mean that the OS did not expose those values.</p>';
  loadStorage();
  loadStorageHistory();
}
async function loadStorageHistory() {
  const selector = document.getElementById('storage-history-window');
  if (selector) state.storageWindow = selector.value;
  const windowName = state.storageWindow || '1h';
  try {
    const payload = await api('/history?window=' + encodeURIComponent(windowName) + '&limit=240');
    renderStorageChart(Array.isArray(payload.samples) ? payload.samples : []);
  } catch (error) {
    const chart = document.getElementById('storage-history-chart');
    if (chart) chart.innerHTML = '<p class="empty-state error-text">' + escapeHTML(error.message) + '</p>';
  }
}
async function loadStorage() {
  const list = document.getElementById('storage-device-list');
  if (!list) return;
  try {
    const payload = await api('/storage');
    const totals = payload.totals || {};
    setText('storage-read', storageDisplayRate(totals.read_bytes_per_sec));
    setText('storage-write', storageDisplayRate(totals.write_bytes_per_sec));
    setText('storage-read-meta', storageDisplayNumber(totals.read_iops, 'read IOPS', 1));
    setText('storage-iops', storageDisplayNumber(totals.read_iops, '', 1) + ' / ' + storageDisplayNumber(totals.write_iops, '', 1));
    setText('storage-activity', storageDisplayNumber(totals.activity_percent, '%', 1));
    setText('storage-latency', storageDisplayNumber(totals.latency_ms, 'ms response', 2));
    const devices = Array.isArray(payload.devices) ? payload.devices : [];
    setText('storage-device-count', String(devices.length) + ' DEVICES');
    list.innerHTML = devices.length ? devices.map(function (device) {
      const smart = device.smart || {};
      return '<tr><td class="mono-cell">' + escapeHTML(device.device) + '</td><td>' +
        storageDisplayRate(device.read_bytes_per_sec) + ' / ' + storageDisplayRate(device.write_bytes_per_sec) +
        '</td><td>' + storageDisplayNumber(device.read_iops, 'R', 1) + ' / ' + storageDisplayNumber(device.write_iops, 'W', 1) +
        '</td><td>' + storageDisplayNumber(device.activity_percent, '%', 1) + '</td><td>' +
        storageDisplayNumber(device.latency_ms, 'ms', 2) + '</td><td>' +
        storageDisplayNumber(device.temperature_c, '°C', 1) + '</td><td>' +
        escapeHTML(smart.health || smart.status || 'Unavailable') + '</td></tr>';
    }).join('') : '<tr><td colspan="7" class="table-message">No per-device I/O counters were exposed.</td></tr>';
    const drives = Array.isArray(payload.drives) ? payload.drives : [];
    setText('storage-drive-count', String(drives.length) + ' VOLUMES');
    const driveList = document.getElementById('storage-drive-list');
    if (driveList) driveList.innerHTML = drives.length ? drives.map(function (drive) {
      const used = drive.used_gb === null ? 'Unavailable' : Number(drive.used_gb).toFixed(1) + ' GiB';
      const free = drive.free_gb === null ? 'Unavailable' : Number(drive.free_gb).toFixed(1) + ' GiB';
      const total = drive.total_gb === null ? 'Unavailable' : Number(drive.total_gb).toFixed(1) + ' GiB';
      return '<tr><td class="process-name">' + escapeHTML(drive.mountpoint) + '</td><td class="mono-cell">' +
        escapeHTML(drive.device) + '</td><td>' + escapeHTML(drive.filesystem) + '</td><td>' + used +
        '</td><td>' + free + '</td><td>' + (drive.percent === null ? 'Unavailable' : Number(drive.percent).toFixed(1) + '%') +
        '</td></tr>';
    }).join('') : '<tr><td colspan="6" class="table-message">No mounted volumes were returned.</td></tr>';
    const processes = Array.isArray(payload.top_processes) ? payload.top_processes : [];
    const processList = document.getElementById('storage-process-list');
    if (processList) processList.innerHTML = processes.length ? processes.map(function (process) {
      return '<tr><td class="process-name">' + escapeHTML(process.name) + '</td><td class="mono-cell">' + Number(process.pid) +
        '</td><td>' + storageDisplayRate(process.read_bytes_per_sec) + '</td><td>' +
        storageDisplayRate(process.write_bytes_per_sec) + '</td><td>' +
        storageDisplayNumber(process.read_iops, 'R', 1) + ' / ' + storageDisplayNumber(process.write_iops, 'W', 1) +
        '</td></tr>';
    }).join('') : '<tr><td colspan="5" class="table-message">No process I/O deltas were visible in this sampling interval.</td></tr>';
    setText('storage-capabilities',
      'Disk I/O: ' + (payload.capabilities && payload.capabilities.psutil_disk_io || 'Unavailable') +
      ' · Activity: ' + (payload.capabilities && payload.capabilities.disk_activity_percent || 'Unavailable') +
      ' · Latency: ' + (payload.capabilities && payload.capabilities.disk_latency || 'Unavailable') +
      ' · SMART: ' + (payload.capabilities && payload.capabilities.smart || 'Unavailable') +
      '. Process names and PIDs are live-only and are not written to SQLite.');
  } catch (error) {
    list.innerHTML = '<tr><td colspan="7" class="table-message error-text">' + escapeHTML(error.message) + '</td></tr>';
  }
}
