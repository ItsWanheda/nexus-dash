// NEXUS // Hardware view. All values come from the local API and retain provider status.
function hardwareValue(metric, precision) {
  if (!metric || metric.value === null || metric.value === undefined) return 'Unavailable';
  if (typeof metric.value === 'boolean') return metric.value ? 'Yes' : 'No';
  const value = typeof metric.value === 'number'
    ? metric.value.toFixed(precision === undefined ? 1 : precision)
    : String(metric.value);
  return value + (metric.unit ? ' ' + metric.unit : '');
}
function hardwareStatus(status) {
  const value = String(status || 'Unavailable');
  const tone = value.toLowerCase().replace(/[^a-z-]/g, '');
  return '<span class="telemetry-status status-' + tone + '">' + escapeHTML(value) + '</span>';
}
function hardwareReadingRow(label, metric, precision) {
  return '<div class="telemetry-reading"><span>' + escapeHTML(label) + '</span><strong>' +
    escapeHTML(hardwareValue(metric, precision)) + '</strong>' +
    (metric && metric.status ? hardwareStatus(metric.status) : '') + '</div>';
}
function hardwareSensorMarkup(sensors, unit, valueKey) {
  if (!Array.isArray(sensors) || !sensors.length) return '<p class="empty-state">Unavailable — no readings were exposed by the current sensor provider.</p>';
  return '<div class="sensor-list">' + sensors.map(function (sensor) {
    const value = sensor[valueKey];
    return '<div class="sensor-row"><div><strong>' + escapeHTML(sensor.label || sensor.provider || 'Sensor') +
      '</strong><small>' + escapeHTML(sensor.provider || 'Operating system') + '</small></div><strong>' +
      (value === null || value === undefined ? 'Unavailable' : Number(value).toFixed(1) + ' ' + unit) + '</strong></div>';
  }).join('') + '</div>';
}
function renderHardware() {
  const main = document.getElementById('main-content');
  if (!main) return;
  main.innerHTML =
    '<section class="page-intro"><div><div class="eyebrow">HARDWARE / SENSOR INTELLIGENCE</div><h2>Hardware telemetry</h2><p>Component-level readings from the local operating system and optional hardware providers. Unsupported measurements remain unavailable.</p></div><div class="live-tag"><span class="pulse-dot"></span> LIVE HARDWARE</div></section>' +
    '<div class="telemetry-toolbar"><span id="hardware-sampled" class="panel-tag">WAITING FOR SENSOR DATA</span><button class="secondary-button" type="button" data-action="hardware-refresh">↻ Refresh hardware</button></div>' +
    '<div class="telemetry-grid">' +
    '<section class="panel telemetry-panel"><div class="panel-heading"><div><span class="eyebrow">PROCESSOR</span><h3>CPU</h3></div><span id="hardware-cpu-status" class="panel-tag">LOADING</span></div><div id="hardware-cpu-summary" class="telemetry-reading-list"><p class="muted">Collecting CPU readings…</p></div><div class="divider"></div><h4 class="telemetry-subheading">Logical cores</h4><div id="hardware-cores" class="core-grid"><p class="muted">Waiting for core readings…</p></div><div class="divider"></div><h4 class="telemetry-subheading">CPU temperature sensors</h4><div id="hardware-cpu-temperatures"><p class="muted">Waiting for sensors…</p></div></section>' +
    '<section class="panel telemetry-panel"><div class="panel-heading"><div><span class="eyebrow">GRAPHICS</span><h3>GPU devices</h3></div><span id="hardware-gpu-status" class="panel-tag">LOADING</span></div><div id="hardware-gpu"><p class="muted">Enumerating display adapters and available sensor providers…</p></div></section>' +
    '<section class="panel telemetry-panel"><div class="panel-heading"><div><span class="eyebrow">SYSTEM MEMORY</span><h3>RAM and pagefile</h3></div><span id="hardware-memory-status" class="panel-tag">LOADING</span></div><div id="hardware-memory" class="telemetry-reading-list"><p class="muted">Collecting memory readings…</p></div></section>' +
    '<section class="panel telemetry-panel"><div class="panel-heading"><div><span class="eyebrow">BOARD SENSORS</span><h3>Motherboard and cooling</h3></div><span id="hardware-board-status" class="panel-tag">LOADING</span></div><h4 class="telemetry-subheading">System and board identity</h4><div id="hardware-system-identity" class="telemetry-reading-list"><p class="muted">Reading SMBIOS / DMI…</p></div><div class="divider"></div><h4 class="telemetry-subheading">Temperatures</h4><div id="hardware-board-temperatures"></div><div class="divider"></div><h4 class="telemetry-subheading">Fan speeds</h4><div id="hardware-fans"></div><p class="table-note">Sensor visibility depends on firmware, drivers, permissions, and the platform.</p></section>' +
    '<section class="panel telemetry-panel"><div class="panel-heading"><div><span class="eyebrow">PORTABLE POWER</span><h3>Battery</h3></div><span id="hardware-battery-status" class="panel-tag">LOADING</span></div><div id="hardware-battery" class="telemetry-reading-list"><p class="muted">Checking battery telemetry…</p></div></section>' +
    '</div><p class="table-note">Readings update every five seconds while this view is open. CPU voltage, battery health, and charge cycles are shown as unavailable unless a provider reports a real value. Detailed drive temperature and health are available in Storage when supported.</p>';
  loadHardware();
}
async function loadHardware() {
  const main = document.getElementById('hardware-cpu-summary');
  if (!main) return;
  try {
    const payload = await api('/hardware');
    setText('hardware-sampled', 'SAMPLED ' + new Date(payload.sampled_at).toLocaleTimeString());
    const cpu = payload.cpu || {};
    setText('hardware-cpu-status', cpu.utilization_percent && cpu.utilization_percent.status || 'Unavailable');
    const cpuSummary = [
      hardwareReadingRow('Processor model', { value: cpu.model || 'Unavailable', unit: '', status: cpu.model && cpu.model !== 'Unavailable' ? 'Available' : 'Unavailable' }),
      hardwareReadingRow('Overall utilisation', cpu.utilization_percent),
      hardwareReadingRow('Average frequency', cpu.frequency_mhz, 0),
      hardwareReadingRow('Logical / physical cores', { value: String(cpu.logical_cores || 0) + ' / ' + String(cpu.physical_cores || 0), unit: '', status: 'Available' }),
      hardwareReadingRow('CPU voltage', cpu.voltage_v, 2)
    ].join('');
    main.innerHTML = cpuSummary;
    const cores = Array.isArray(cpu.cores) ? cpu.cores : [];
    document.getElementById('hardware-cores').innerHTML = cores.length
      ? cores.map(function (core) {
          const metric = core.utilization_percent || {};
          const percent = metric.value === null || metric.value === undefined ? 0 : Math.max(0, Math.min(100, Number(metric.value)));
          return '<div class="core-card"><div><span>CORE ' + Number(core.core + 1) + '</span><strong>' +
            (metric.value === null || metric.value === undefined ? 'Unavailable' : Number(metric.value).toFixed(1) + '%') +
            '</strong></div><div class="progress-track"><div class="progress-value" style="width:' + percent + '%"></div></div><small>' +
            escapeHTML(hardwareValue(core.frequency_mhz, 0)) + '</small></div>';
        }).join('')
      : '<p class="empty-state">Per-core utilisation is unavailable.</p>';
    document.getElementById('hardware-cpu-temperatures').innerHTML =
      hardwareSensorMarkup(cpu.temperatures && cpu.temperatures.sensors, '°C', 'current_c');
    const gpu = payload.gpu || {};
    setText('hardware-gpu-status', gpu.status || 'Unavailable');
    const gpuDevices = Array.isArray(gpu.devices) ? gpu.devices : [];
    document.getElementById('hardware-gpu').innerHTML = gpuDevices.length
      ? gpuDevices.map(function (device) {
          return '<article class="hardware-device"><div class="panel-heading compact"><strong>' + escapeHTML(device.name || 'GPU device') +
            '</strong>' + hardwareStatus(device.status) + '</div><div class="hardware-device-meta"><span>' + escapeHTML(device.vendor || 'Unknown vendor') + '</span>' +
            (device.device_id ? '<span>Device ' + escapeHTML(device.device_id) + '</span>' : '') +
            (device.driver ? '<span>Driver ' + escapeHTML(device.driver) + '</span>' : '') +
            (device.driver_version ? '<span>Driver version ' + escapeHTML(device.driver_version) + '</span>' : '') +
            (device.vendor_id ? '<span>Vendor ID ' + escapeHTML(device.vendor_id) + '</span>' : '') +
            (device.pci_address ? '<span>PCI ' + escapeHTML(device.pci_address) + '</span>' : '') + '</div><div class="telemetry-reading-list">' +
            hardwareReadingRow('GPU utilisation', device.utilization_percent) +
            hardwareReadingRow('VRAM used', device.memory_used_gb) +
            hardwareReadingRow('VRAM total', device.memory_total_gb) +
            hardwareReadingRow('Temperature', device.temperature_c) +
            hardwareReadingRow('Power draw', device.power_w) +
            hardwareReadingRow('Graphics clock', device.graphics_clock_mhz, 0) +
            hardwareReadingRow('Memory clock', device.memory_clock_mhz, 0) +
            hardwareReadingRow('Fan speed', device.fan_percent) +
            hardwareReadingRow('Fan tachometer', device.fan_rpm) + '</div>' +
            (device.reason ? '<p class="table-note">' + escapeHTML(device.reason) + '</p>' : '') + '</article>';
        }).join('')
      : '<p class="empty-state">' + escapeHTML(gpu.reason || 'No display adapter was reported by the available operating-system inventory providers.') + '</p>';
    const memory = payload.memory || {};
    setText('hardware-memory-status', memory.percent && memory.percent.status || 'Unavailable');
    const swap = memory.swap || {};
    document.getElementById('hardware-memory').innerHTML = [
      hardwareReadingRow('Total RAM', memory.total_gb),
      hardwareReadingRow('Used RAM', memory.used_gb),
      hardwareReadingRow('Available RAM', memory.available_gb),
      hardwareReadingRow('Utilisation', memory.percent),
      hardwareReadingRow('Cached memory', memory.cached_gb),
      hardwareReadingRow('Buffers', memory.buffers_gb),
      hardwareReadingRow('Shared memory', memory.shared_gb),
      hardwareReadingRow('Swap / pagefile used', swap.used_gb),
      hardwareReadingRow('Swap / pagefile total', swap.total_gb),
      hardwareReadingRow('Swap utilisation', swap.percent)
    ].join('') + '<div class="memory-pressure"><span>Memory pressure</span><strong>' +
      escapeHTML((memory.pressure && memory.pressure.level) || 'Unavailable') + '</strong><small>' +
      escapeHTML((memory.pressure && memory.pressure.source) || 'No pressure provider') + '</small></div>';
    const board = payload.motherboard || {};
    const system = payload.system || {};
    const identity = board.identity || {};
    const bios = board.bios || {};
    const identityRows = [
      ['System manufacturer', system.manufacturer], ['System model', system.model],
      ['System family', system.family], ['Motherboard manufacturer', identity.manufacturer],
      ['Motherboard model', identity.model], ['Board version', identity.version],
      ['BIOS vendor', bios.vendor], ['BIOS version', bios.version], ['BIOS release', bios.release_date]
    ];
    document.getElementById('hardware-system-identity').innerHTML =
      identityRows.map(function (pair) {
        return hardwareReadingRow(pair[0], {
          value: pair[1] || null, unit: '',
          status: pair[1] ? 'Available' : 'Unavailable'
        });
      }).join('') + '<p class="table-note">Source: ' + escapeHTML(board.identity_source || 'SMBIOS / DMI / WMI') + '</p>';
    const boardHasIdentity = Boolean(identity.model || system.model);
    setText('hardware-board-status', (board.temperatures && board.temperatures.status) || (board.fans && board.fans.status) || (boardHasIdentity ? 'Inventory only' : 'Unavailable'));
    document.getElementById('hardware-board-temperatures').innerHTML =
      hardwareSensorMarkup(board.temperatures && board.temperatures.sensors, '°C', 'current_c');
    const fans = board.fans && board.fans.sensors;
    document.getElementById('hardware-fans').innerHTML = Array.isArray(fans) && fans.length
      ? '<div class="sensor-list">' + fans.map(function (fan) {
          return '<div class="sensor-row"><div><strong>' + escapeHTML(fan.label || fan.provider || 'Fan') +
            '</strong><small>' + escapeHTML(fan.provider || 'Operating system') + '</small></div><strong>' +
            Number(fan.rpm).toFixed(0) + ' RPM</strong></div>';
        }).join('') + '</div>'
      : '<p class="empty-state">Unavailable — no fan tachometer readings were exposed.</p>';
    const battery = payload.battery || {};
    setText('hardware-battery-status', battery.status || 'Unavailable');
    document.getElementById('hardware-battery').innerHTML = [
      hardwareReadingRow('Charge level', battery.percentage),
      hardwareReadingRow('Charging', battery.charging),
      hardwareReadingRow('Estimated remaining', battery.seconds_remaining ? {
        value: battery.seconds_remaining.value === null ? null : Math.round(Number(battery.seconds_remaining.value) / 60),
        unit: 'min', status: battery.seconds_remaining.status, reason: battery.seconds_remaining.reason
      } : null),
      hardwareReadingRow('Battery health', battery.health_percent),
      hardwareReadingRow('Charge cycles', battery.charge_cycles)
    ].join('');
  } catch (error) {
    ['hardware-cpu-summary','hardware-gpu','hardware-memory','hardware-board-temperatures','hardware-fans','hardware-battery'].forEach(function (id) {
      const element = document.getElementById(id);
      if (element) element.innerHTML = '<p class="empty-state error-text">' + escapeHTML(error.message) + '</p>';
    });
  }
}
