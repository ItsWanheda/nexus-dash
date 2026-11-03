/* NEXUS-DASH: historical analytics and network investigation views. */
(function (global) {
  'use strict';
  let networkTimer = null, connectionTimer = null, analyticsTimer = null;
  let processNetworkTimer = null, networkQualityTimer = null;
  let latestAnalytics = null;
  function el(id) { return document.getElementById(id); }
  function esc(value) { return String(value == null ? '' : value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'","&#39;"); }
  function n(value,digits) { const x=Number(value); return Number.isFinite(x)?x.toFixed(digits===undefined?1:digits):'—'; }
  function count(value) { const x=Number(value); return Number.isFinite(x)&&x>=0?Math.round(x).toLocaleString():'—'; }
  function rate(value) {
    const x=Number(value); if(!Number.isFinite(x)||x<0)return '—';
    if(x>=1073741824)return (x/1073741824).toFixed(2)+' GB/s';
    if(x>=1048576)return (x/1048576).toFixed(2)+' MB/s';
    if(x>=1024)return (x/1024).toFixed(1)+' KB/s';
    return x.toFixed(0)+' B/s';
  }
  function fact(label,value) { return '<section class="panel"><span>'+esc(label)+'</span><strong>'+esc(value)+'</strong></section>'; }
  function set(id,value) { const node=el(id); if(node)node.textContent=value; }

  function renderNetwork(main) {
    main.innerHTML =
      '<section class="page-intro"><div><div class="eyebrow">NETWORK / INTERFACE OBSERVABILITY</div><h2>Network Intelligence</h2><p>Per-interface throughput, packet errors, link state, live sockets, process attribution and user-triggered connectivity diagnostics.</p></div><button class="secondary-button" data-action="network-refresh" type="button">↻ Refresh</button></section>'+
      '<div class="network-summary-grid" id="network-summary">'+fact('Interfaces','—')+fact('Connected','—')+fact('Upload','—')+fact('Download','—')+'</div>'+
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">LINKS / COUNTERS</span><h3>Network interfaces</h3></div><span id="network-state" class="panel-tag">LOADING</span></div><div class="table-scroll"><table class="network-table"><thead><tr><th>Interface</th><th>Link</th><th>Speed</th><th>Upload</th><th>Download</th><th>Errors</th><th>Drops</th></tr></thead><tbody id="network-interface-rows"><tr><td colspan="7" class="table-message">Loading counters…</td></tr></tbody></table></div><p class="table-note">Initial rate readings warm up after service start or adapter reconnect. IP and MAC addresses are not collected or stored.</p></section>'+
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">HISTORY / TRAFFIC</span><h3>Upload and download</h3></div><div class="network-history-controls"><select id="network-history-window" class="flight-select"><option value="1h">1 hour</option><option value="6h">6 hours</option><option value="24h" selected>24 hours</option><option value="7d">7 days</option><option value="30d">30 days</option></select><button class="text-button" data-action="network-history-refresh" type="button">Refresh history</button></div></div><div id="network-history-chart" class="deep-chart"><p class="empty-state">Loading history…</p></div><p class="table-note">This chart uses bounded aggregate system traffic buckets across the full selected window. Per-interface counters are shown above and summarized in Advanced Analytics.</p><div class="deep-chart-legend"><span class="upload-legend">Upload</span><span class="download-legend">Download</span></div></section>'+
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">LIVE SOCKET TABLE</span><h3>Connections and process attribution</h3></div><button class="text-button" data-action="network-connections-refresh" type="button">↻ Refresh connections</button></div><div class="connection-options"><label><input id="network-reveal-addresses" type="checkbox"> Reveal local and remote IP addresses for this view</label><span id="network-connection-status" class="panel-tag">LOADING</span></div><div id="network-connection-summary" class="connection-summary"></div><div class="table-scroll"><table class="network-table"><thead><tr><th>Process</th><th>PID</th><th>Protocol</th><th>State</th><th>Local port</th><th>Remote endpoint</th></tr></thead><tbody id="network-connection-rows"><tr><td colspan="6" class="table-message">Loading connections…</td></tr></tbody></table></div><p class="table-note">Socket data is live-only and never written to the recorder. IP addresses stay hidden unless explicitly revealed. Permissions may limit visibility.</p></section>'+
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">APPLICATION BANDWIDTH</span><h3>Per-process network attribution</h3></div><button class="text-button" data-action="network-process-refresh" type="button">↻ Refresh</button></div><span id="network-process-status" class="panel-tag">CHECKING</span><div id="network-process-rows" class="table-scroll"><p class="empty-state">Checking the configured OS accounting provider…</p></div><p class="table-note">This table reports measured byte rates only when a per-process accounting provider is available. Linux NetHogs is supported when installed and permitted to capture. Windows ETW/WFP and macOS per-process byte providers are not implemented in this build; socket ownership is not presented as bandwidth.</p></section>' +
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">CONTINUOUS NETWORK QUALITY</span><h3>Configured target history</h3></div><button class="text-button" data-action="network-quality-refresh" type="button">↻ Refresh</button></div><span id="network-quality-status" class="panel-tag">CHECKING</span><div id="network-quality-rows" class="table-scroll"><p class="empty-state">Loading configured DNS/TCP health checks…</p></div><p class="table-note">Configure up to three host/port targets in Settings and explicitly enable monitoring. NEXUS samples them no more than once per minute. No default external targets are added.</p></section>' +
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">ON-DEMAND PROBE</span><h3>DNS and TCP connectivity</h3></div><span class="panel-tag">USER INITIATED</span></div><p class="muted">Resolve a host and perform up to three TCP handshakes. No HTTP request or application payload is sent. The target is not saved.</p><div class="network-probe-form"><label>Hostname or IP<input id="network-probe-host" type="text" maxlength="253" placeholder="example.com" autocomplete="off" spellcheck="false"></label><label>TCP port<input id="network-probe-port" type="number" min="1" max="65535" value="443"></label><button class="primary-button" data-action="network-diagnose" type="button">Run test</button></div><div id="network-probe-result" class="network-probe-result" aria-live="polite"></div></section>';
    loadNetwork(); loadConnections(); loadNetworkHistory(); loadProcessNetwork(); loadNetworkQuality();
  }

  async function loadNetwork() {
    const rows=el('network-interface-rows'); if(!rows)return;
    try {
      const data=await api('/network');
      const items=Array.isArray(data.interfaces)?data.interfaces:[];
      const active=items.filter(x=>x.is_up===true).length;
      const upload=items.reduce((v,x)=>v+(Number(x.sent_bytes_per_sec)||0),0);
      const download=items.reduce((v,x)=>v+(Number(x.received_bytes_per_sec)||0),0);
      el('network-summary').innerHTML=fact('Interfaces',count(data.interface_count))+fact('Connected',count(active))+fact('Upload',rate(upload))+fact('Download',rate(download));
      set('network-state',String(data.status||'UNKNOWN').toUpperCase());
      if(!items.length){rows.innerHTML='<tr><td colspan="7" class="table-message">No per-interface counters are available.</td></tr>';return;}
      rows.innerHTML=items.map(item=>{
        const link=item.is_up===true?'<span class="network-link-up">UP</span>':item.is_up===false?'<span class="network-link-down">DOWN</span>':'—';
        const errors=item.errors_in_delta===null||item.errors_out_delta===null?'—':count((Number(item.errors_in_delta)||0)+(Number(item.errors_out_delta)||0));
        const drops=item.drops_in_delta===null||item.drops_out_delta===null?'—':count((Number(item.drops_in_delta)||0)+(Number(item.drops_out_delta)||0));
        return '<tr><td><strong>'+esc(item.name)+'</strong>'+(item.is_loopback?'<small>Loopback</small>':'')+'</td><td>'+link+'</td><td>'+(item.speed_mbps?count(item.speed_mbps)+' Mbps':'—')+'</td><td>'+rate(item.sent_bytes_per_sec)+'</td><td>'+rate(item.received_bytes_per_sec)+'</td><td>'+errors+'</td><td>'+drops+'</td></tr>';
      }).join('');
    } catch(error){rows.innerHTML='<tr><td colspan="7" class="table-message error-text">'+esc(error.message)+'</td></tr>';set('network-state','UNAVAILABLE');}
  }

  async function loadConnections() {
    const rows=el('network-connection-rows');if(!rows)return;
    const reveal=Boolean(el('network-reveal-addresses')&&el('network-reveal-addresses').checked);
    try {
      const data=await api('/network/connections?limit=150&include_addresses='+String(reveal));
      set('network-connection-status',String(data.status||'UNKNOWN').toUpperCase()+' · '+count(data.count)+' TOTAL');
      const summary=el('network-connection-summary');
      if(summary){
        const states=Object.entries(data.by_state||{}).sort((a,b)=>b[1]-a[1]).slice(0,5);
        const protocols=Object.entries(data.by_protocol||{}).map(x=>x[0]+' '+x[1]).join(' · ');
        summary.innerHTML='<span>'+esc(protocols||'No protocol counts')+'</span>'+states.map(x=>'<span>'+esc(x[0])+' '+count(x[1])+'</span>').join('')+'<span>'+(reveal?'Addresses revealed for this view':'IP addresses hidden')+'</span>';
      }
      if(!data.connections||!data.connections.length){rows.innerHTML='<tr><td colspan="6" class="table-message">'+esc(data.reason||'No connection rows were returned.')+'</td></tr>';return;}
      rows.innerHTML=data.connections.map(item=>{
        const local=reveal?(item.local_address||'—'):'Port '+(item.local_port||'—');
        const remote=reveal?(item.remote_address||'—'):'Hidden · port '+(item.remote_port||'—');
        return '<tr><td>'+esc(item.process)+'</td><td class="mono-cell">'+(item.pid===null?'—':count(item.pid))+'</td><td>'+esc(item.protocol)+'</td><td>'+esc(item.state)+'</td><td>'+esc(local)+'</td><td>'+esc(remote)+'</td></tr>';
      }).join('');
    } catch(error){rows.innerHTML='<tr><td colspan="6" class="table-message error-text">'+esc(error.message)+'</td></tr>';}
  }

  async function loadNetworkHistory() {
    const target=el('network-history-chart');if(!target)return;
    const windowName=el('network-history-window')?el('network-history-window').value:'24h';
    try {
      const report=await api('/analytics?window='+encodeURIComponent(windowName)+'&compare_previous=false');
      const points=(report.trend||[]).filter(item=>
        Number.isFinite(Number(item.network_upload_average))&&Number.isFinite(Number(item.network_download_average))
      ).slice(-120);
      if(!points.length){target.innerHTML='<p class="empty-state">No complete network rate pairs have been recorded across this window yet.</p>';return;}
      const max=Math.max(1,...points.map(item=>Math.max(Number(item.network_upload_average),Number(item.network_download_average))));
      target.innerHTML='<div class="network-history-bars">'+points.map(item=>{
        const up=Math.max(1,Number(item.network_upload_average)/max*100);
        const down=Math.max(1,Number(item.network_download_average)/max*100);
        return '<div class="network-history-column" title="'+esc(new Date(item.epoch*1000).toLocaleString())+
          ' · ↑ '+esc(rate(item.network_upload_average))+' · ↓ '+esc(rate(item.network_download_average))+
          '"><i class="network-upload-bar" style="height:'+up.toFixed(1)+'%"></i><i class="network-download-bar" style="height:'+down.toFixed(1)+'%"></i></div>';
      }).join('')+'</div><div class="chart-axis"><span>'+esc(new Date(points[0].epoch*1000).toLocaleString())+'</span><span>'+esc(new Date(points[points.length-1].epoch*1000).toLocaleString())+'</span></div>';
    } catch(error){target.innerHTML='<p class="empty-state error-text">'+esc(error.message)+'</p>';}
  }


  function renderProcessNetwork(result) {
    const target=el('network-process-rows');if(!target)return;
    const items=Array.isArray(result.history)&&result.history.length?result.history:result.items||[];
    set('network-process-status',String(result.status||'UNKNOWN').toUpperCase()+' · '+String(result.provider||'NO PROVIDER'));
    if(!items.length){
      target.innerHTML='<p class="empty-state">'+esc(result.reason||'No per-process bandwidth samples are available yet.')+'</p>';
      return;
    }
    const latest=new Map();
    items.forEach(item=>latest.set(Number(item.pid),item));
    const rows=Array.from(latest.values()).sort((a,b)=>
      (Number(b.upload_bytes_per_sec)||0)+(Number(b.download_bytes_per_sec)||0)-
      (Number(a.upload_bytes_per_sec)||0)-(Number(a.download_bytes_per_sec)||0));
    target.innerHTML='<table class="network-table"><thead><tr><th>Process</th><th>PID</th><th>Upload</th><th>Download</th><th>Provider</th></tr></thead><tbody>'+
      rows.slice(0,50).map(item=>'<tr><td>'+esc(item.process_name||'Unknown')+'</td><td class="mono-cell">'+count(item.pid)+'</td><td>'+rate(item.upload_bytes_per_sec)+'</td><td>'+rate(item.download_bytes_per_sec)+'</td><td>'+esc(item.provider||result.provider||'—')+'</td></tr>').join('')+
      '</tbody></table>';
  }
  async function loadProcessNetwork() {
    const target=el('network-process-rows');if(!target)return;
    try{
      const result=await api('/network/processes?window=24h&limit=500');
      renderProcessNetwork(result);
    }catch(error){
      set('network-process-status','UNAVAILABLE');
      target.innerHTML='<p class="empty-state error-text">'+esc(error.message)+'</p>';
    }
  }
  async function loadNetworkQuality() {
    const target=el('network-quality-rows');if(!target)return;
    try{
      const result=await api('/network/quality?window=24h&limit=1000');
      const samples=Array.isArray(result.samples)?result.samples:[];
      const latest=new Map();
      samples.forEach(item=>latest.set(String(item.host_label)+':'+String(item.port),item));
      const state=result.status==='enabled'?'MONITORING ENABLED':'MONITORING DISABLED';
      set('network-quality-status',state+' · '+String(latest.size)+' TARGETS');
      if(!samples.length){
        target.innerHTML='<p class="empty-state">'+(result.status==='enabled'
          ?'No samples yet. Monitoring runs once a minute for configured targets while background recording is enabled.'
          :'Enable continuous network quality monitoring and configure up to three host/port targets in Settings.')+'</p>';
        return;
      }
      const rows=Array.from(latest.values()).sort((a,b)=>Number(b.sampled_epoch)-Number(a.sampled_epoch));
      target.innerHTML='<table class="network-table"><thead><tr><th>Target</th><th>Status</th><th>DNS</th><th>TCP</th><th>Jitter</th><th>Loss</th><th>Last check</th></tr></thead><tbody>'+
        rows.map(item=>'<tr><td>'+esc(item.host_label)+':'+count(item.port)+'</td><td>'+esc(item.status)+'</td><td>'+n(item.dns_latency_ms)+' ms</td><td>'+n(item.tcp_latency_ms)+' ms</td><td>'+n(item.jitter_ms)+' ms</td><td>'+n(item.packet_loss_percent)+'%</td><td>'+esc(new Date(Number(item.sampled_epoch)*1000).toLocaleString())+'</td></tr>').join('')+
        '</tbody></table>';
    }catch(error){
      set('network-quality-status','UNAVAILABLE');
      target.innerHTML='<p class="empty-state error-text">'+esc(error.message)+'</p>';
    }
  }

  async function diagnose() {
    const host=el('network-probe-host'),port=el('network-probe-port'),target=el('network-probe-result');
    if(!host||!port||!target||!host.value.trim()){if(target)target.textContent='Enter a hostname or IP address first.';return;}
    const button=document.querySelector('[data-action="network-diagnose"]');if(button)button.disabled=true;
    target.textContent='Resolving and testing TCP handshakes…';
    try {
      const data=await api('/network/diagnostics?host='+encodeURIComponent(host.value.trim())+'&port='+encodeURIComponent(port.value)+'&attempts=3');
      const latency=data.tcp_latency_ms||{};
      const facts=[
        ['Status',data.status],['DNS',data.dns_latency_ms===null?'Unavailable':n(data.dns_latency_ms)+' ms'],
        ['Resolved addresses',data.resolved_address_count],['Successful handshakes',data.success_count+' / '+(data.success_count+data.failure_count)],
        ['TCP average',latency.average===null?'Unavailable':n(latency.average)+' ms'],['Jitter',latency.jitter===null?'Unavailable':n(latency.jitter)+' ms'],
        ['Attempt loss',data.packet_loss_percent===undefined?'—':n(data.packet_loss_percent)+'%']
      ];
      target.innerHTML='<div class="network-probe-facts">'+facts.map(x=>'<div><span>'+esc(x[0])+'</span><strong>'+esc(x[1])+'</strong></div>').join('')+'</div><p class="table-note">'+esc(data.message)+'</p>';
    } catch(error){target.textContent=error.message;} finally{if(button)button.disabled=false;}
  }

  function renderAnalytics(main) {
    main.innerHTML=
      '<section class="page-intro"><div><div class="eyebrow">HISTORICAL / RESOURCE INTELLIGENCE</div><h2>Advanced Analytics</h2><p>Percentiles, distributions, historical comparisons and incident frequency from actual local recorder data. No generic health score.</p></div><button class="secondary-button" data-action="analytics-refresh" type="button">↻ Refresh</button></section>'+
      '<section class="panel analytics-toolbar"><label>Analysis window<select id="analytics-window" class="flight-select"><option value="1h">1 hour</option><option value="6h">6 hours</option><option value="24h" selected>24 hours</option><option value="7d">7 days</option><option value="30d">30 days</option></select></label><label class="analytics-compare-toggle"><input id="analytics-compare" type="checkbox" checked> Compare previous equal-length period</label><span id="analytics-sample-status" class="panel-tag">LOADING</span><button class="secondary-button" type="button" data-action="analytics-export">Export JSON</button></section>'+
      '<div id="analytics-summary-grid" class="analytics-summary-grid">'+fact('CPU average','—')+fact('RAM average','—')+fact('Disk p95','—')+fact('Network download','—')+'</div>'+
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">TIME SERIES / TRENDS</span><h3>Resource utilisation</h3></div><span class="panel-tag">UTC BUCKETS</span></div><div id="analytics-trend-chart" class="analytics-trend-chart"><p class="empty-state">Loading history…</p></div><div class="analytics-legend"><span class="cpu-series">CPU</span><span class="ram-series">Memory</span><span class="disk-series">Disk</span></div></section>'+
      '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">EVIDENCE / SCORECARDS</span><h3>Independent pressure indicators</h3></div><span class="panel-tag">NO COMBINED SCORE</span></div><div id="analytics-scorecards" class="analytics-scorecards"></div></section>'+
      '<div class="analytics-two-column"><section class="panel"><div class="panel-heading"><h3>Utilisation distributions</h3></div><div id="analytics-distribution"></div></section><section class="panel"><div class="panel-heading"><h3>Incident frequency</h3></div><div id="analytics-incidents"></div></section></div>'+
      '<section class="panel"><div class="panel-heading"><h3>Previous-period comparison</h3></div><div id="analytics-comparison" class="table-scroll"></div></section>'+
      '<section class="panel"><div class="panel-heading"><h3>Network by interface</h3></div><div id="analytics-network-table" class="table-scroll"></div></section>'+
      '<p class="table-note">Missing readings and history gaps remain missing. Thermal history is not recorded in this version. Statistics are descriptive and do not prove root cause.</p>';
    loadAnalytics();
  }
  function metric(value,suffix){return value===null||value===undefined?'—':n(value)+(suffix||'');}
  function renderAnalyticsSummary(data) {
    const m=data.metrics||{},net=data.network||{};
    el('analytics-summary-grid').innerHTML=
      fact('CPU average',metric(m.cpu_percent&&m.cpu_percent.average,'%'))+
      fact('RAM average',metric(m.ram_percent&&m.ram_percent.average,'%'))+
      fact('Disk latency p95',metric(m.disk_latency_ms&&m.disk_latency_ms.p95,' ms'))+
      fact('Download average',metric(net.download&&net.download.average,' B/s'));
  }
  function renderTrend(data) {
    const target=el('analytics-trend-chart'),rows=data.trend||[];if(!target)return;
    if(!rows.length){target.innerHTML='<p class="empty-state">Not enough persisted samples to chart this period.</p>';return;}
    const series=[['cpu_average','cpu-line'],['ram_average','ram-line'],['disk_average','disk-line']];
    const paths=series.map(s=>{
      const valid=rows.map((r,i)=>({value:Number(r[s[0]]),index:i})).filter(p=>Number.isFinite(p.value));
      if(!valid.length)return '';
      const points=valid.map(p=>{
        const x=rows.length<=1?500:20+p.index/(rows.length-1)*960;
        const y=210-Math.max(0,Math.min(100,p.value))*1.8;
        return x.toFixed(1)+','+y.toFixed(1);
      }).join(' ');
      return '<polyline class="'+s[1]+'" points="'+points+'"></polyline>';
    }).join('');
    target.innerHTML='<svg viewBox="0 0 1000 230" role="img" aria-label="CPU, memory and disk historical trend">'+paths+'</svg><div class="chart-axis"><span>'+esc(new Date(rows[0].epoch*1000).toLocaleString())+'</span><span>'+esc(new Date(rows[rows.length-1].epoch*1000).toLocaleString())+'</span></div>';
  }
  function statusLabel(status) {
    const labels={'no-sustained-pressure':'No sustained pressure','intermittent-pressure':'Intermittent pressure','sustained-pressure':'Sustained pressure','no-observed-errors':'No counter errors observed','insufficient-data':'Insufficient data','not-recorded':'Not recorded'};
    return labels[status]||status;
  }
  function renderScorecards(data) {
    el('analytics-scorecards').innerHTML=(data.scorecards||[]).map(item=>{
      const cls=item.status==='sustained-pressure'?'scorecard-high':item.status==='intermittent-pressure'?'scorecard-watch':item.status==='no-sustained-pressure'||item.status==='no-observed-errors'?'scorecard-ok':'scorecard-muted';
      let evidence='';
      if(item.key==='storage'){evidence='Activity p95 '+metric(item.activity&&item.activity.p95,'%')+' · latency p95 '+metric(item.latency&&item.latency.p95,' ms');}
      else if(item.key==='network'){evidence=count(item.errors)+' errors · '+count(item.drops)+' drops · link up '+metric(item.link_up_percent,'%');}
      else evidence='Average '+metric(item.average,'%')+' · p95 '+metric(item.p95,'%')+' · peak '+metric(item.maximum,'%')+' · samples above threshold '+count(item.samples_above_threshold);
      if(item.note)evidence+=' · '+item.note;
      return '<article class="analytics-scorecard '+cls+'"><div><strong>'+esc(item.title)+'</strong><span>'+esc(statusLabel(item.status))+'</span></div><p>'+esc(evidence)+'</p></article>';
    }).join('');
  }
  function renderDistribution(data) {
    function group(title,values){return '<div class="distribution-group"><strong>'+title+'</strong>'+(values||[]).map(item=>'<div class="distribution-row"><span>'+esc(item.range)+'</span><div><i style="width:'+Math.max(0,Math.min(100,Number(item.percent)||0))+'%"></i></div><small>'+count(item.count)+' · '+n(item.percent)+'%</small></div>').join('')+'</div>';}
    el('analytics-distribution').innerHTML=group('CPU',data.distribution&&data.distribution.cpu)+group('Memory',data.distribution&&data.distribution.memory);
  }
  function renderIncidents(data) {
    const incidents=data.incidents||{},items=Object.entries(incidents.by_category||{}).sort((a,b)=>b[1]-a[1]);
    el('analytics-incidents').innerHTML='<div class="incident-count">'+count(incidents.total)+'<span>events in selected window</span></div>'+(items.length?items.map(x=>'<div class="incident-frequency"><span>'+esc(x[0].replaceAll('-',' '))+'</span><strong>'+count(x[1])+'</strong></div>').join(''):'<p class="empty-state">No timeline events in this period.</p>');
  }
  function renderComparison(data) {
    const target=el('analytics-comparison'),comparison=data.comparison||{};
    const labels={cpu_percent:'CPU average',ram_percent:'RAM average',disk_percent:'Disk capacity',disk_activity_percent:'Disk activity',disk_latency_ms:'Disk latency',disk_read_bytes_per_sec:'Disk read throughput',disk_write_bytes_per_sec:'Disk write throughput',disk_read_iops:'Disk read IOPS',disk_write_iops:'Disk write IOPS'};
    const keys=Object.keys(labels).filter(k=>comparison[k]);
    if(!keys.length){target.innerHTML='<p class="empty-state">Enable previous-period comparison and collect enough samples.</p>';return;}
    target.innerHTML='<table class="network-table"><thead><tr><th>Metric</th><th>Previous average</th><th>Current average</th><th>Change</th></tr></thead><tbody>'+keys.map(key=>{
      const item=comparison[key],suffix=key.includes('bytes_per_sec')?' B/s':key.includes('iops')?' IOPS':key.includes('latency')?' ms':'%';
      const change=item.change===null?'—':(item.change>0?'+':'')+n(item.change)+suffix;
      const pct=item.change_percent===null?'':' ('+(item.change_percent>0?'+':'')+n(item.change_percent)+'%)';
      return '<tr><td>'+labels[key]+'</td><td>'+metric(item.previous,suffix)+'</td><td>'+metric(item.current,suffix)+'</td><td>'+change+pct+'</td></tr>';
    }).join('')+'</tbody></table>';
  }
  function renderNetworkAnalytics(data) {
    const list=data.network&&data.network.interfaces||[];
    if(!list.length){el('analytics-network-table').innerHTML='<p class="empty-state">No interface history yet.</p>';return;}
    el('analytics-network-table').innerHTML='<table class="network-table"><thead><tr><th>Interface</th><th>Upload</th><th>Download</th><th>Errors</th><th>Drops</th><th>Link up</th></tr></thead><tbody>'+list.map(x=>'<tr><td>'+esc(x.name)+(x.loopback?' · loopback':'')+'</td><td>'+count(x.sent_bytes)+' B</td><td>'+count(x.received_bytes)+' B</td><td>'+count(x.error_delta_count)+'</td><td>'+count(x.drop_delta_count)+'</td><td>'+metric(x.link_up_percent,'%')+'</td></tr>').join('')+'</tbody></table>';
  }
  async function loadAnalytics() {
    const status=el('analytics-sample-status');if(!status)return;
    const windowName=el('analytics-window').value,compare=el('analytics-compare').checked;
    status.textContent='LOADING';
    try {
      const data=await api('/analytics?window='+encodeURIComponent(windowName)+'&compare_previous='+String(compare));
      latestAnalytics=data;
      status.textContent=count(data.sample_count)+' SAMPLES · '+String(data.coverage.status||'').toUpperCase();
      renderAnalyticsSummary(data);renderTrend(data);renderScorecards(data);
      renderDistribution(data);renderIncidents(data);renderComparison(data);renderNetworkAnalytics(data);
    } catch(error){status.textContent='UNAVAILABLE';el('analytics-trend-chart').innerHTML='<p class="empty-state error-text">'+esc(error.message)+'</p>';}
  }
  function exportAnalytics() {
    if(!latestAnalytics)return;
    const blob=new Blob([JSON.stringify(latestAnalytics,null,2)],{type:'application/json;charset=utf-8'});
    const url=URL.createObjectURL(blob),anchor=document.createElement('a');
    anchor.href=url;anchor.download='nexus-analytics-'+new Date().toISOString().slice(0,10)+'.json';
    anchor.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function handleChange(target) {
    if(!target)return;
    if(target.id==='network-reveal-addresses')loadConnections();
    else if(target.id==='network-history-window')loadNetworkHistory();
    else if(target.id==='analytics-window'||target.id==='analytics-compare')loadAnalytics();
  }
  function handleAction(action) {
    if(action==='network-refresh'){loadNetwork();loadConnections();loadNetworkHistory();loadProcessNetwork();loadNetworkQuality();return true;}
    if(action==='network-process-refresh'){loadProcessNetwork();return true;}
    if(action==='network-quality-refresh'){loadNetworkQuality();return true;}
    if(action==='network-connections-refresh'){loadConnections();return true;}
    if(action==='network-history-refresh'){loadNetworkHistory();return true;}
    if(action==='network-diagnose'){diagnose();return true;}
    if(action==='analytics-refresh'){loadAnalytics();return true;}
    if(action==='analytics-export'){exportAnalytics();return true;}
    return false;
  }
  function stopTimers() {
    if(networkTimer)clearInterval(networkTimer);
    if(connectionTimer)clearInterval(connectionTimer);
    if(analyticsTimer)clearInterval(analyticsTimer);
    if(processNetworkTimer)clearInterval(processNetworkTimer);
    if(networkQualityTimer)clearInterval(networkQualityTimer);
    networkTimer=connectionTimer=analyticsTimer=processNetworkTimer=networkQualityTimer=null;
  }
  function afterRender() {
    stopTimers();
    if(state.tab==='network'){
      loadProcessNetwork();loadNetworkQuality();
      networkTimer=setInterval(loadNetwork,5000);
      connectionTimer=setInterval(loadConnections,15000);
      processNetworkTimer=setInterval(loadProcessNetwork,15000);
      networkQualityTimer=setInterval(loadNetworkQuality,60000);
    }
    else if(state.tab==='analytics')analyticsTimer=setInterval(loadAnalytics,30000);
  }
  async function refreshCurrentView() {
    if(state.tab==='network'){await loadNetwork();await loadConnections();await loadNetworkHistory();await loadProcessNetwork();await loadNetworkQuality();}
    else if(state.tab==='analytics')await loadAnalytics();
  }
  global.NexusDeepTelemetry={renderNetwork,renderAnalytics,handleChange,handleAction,afterRender,refreshCurrentView};
})(window);
