// NEXUS // Evidence-based troubleshooting UI; local API only.
const DIAGNOSTIC_WINDOWS=[{value:"15m",label:"Last 15 minutes"},{value:"1h",label:"Last hour"},{value:"6h",label:"Last 6 hours"},{value:"24h",label:"Last 24 hours"}];
function renderDiagnostics(){
 const main=document.getElementById("main-content");if(!main)return;const selected=state.diagnosticsWindow||"1h";
 const options=DIAGNOSTIC_WINDOWS.map(x=>'<option value="'+x.value+'"'+(selected===x.value?' selected':'')+'>'+x.label+'</option>').join("");
 main.innerHTML=
 '<section class="page-intro"><div><div class="eyebrow">DIAGNOSTICS / EVIDENCE-BASED ANALYSIS</div><h2>Bottleneck Detective</h2><p>Investigate resource pressure, sustained process-memory growth, and nearby OS crash or hang indicators.</p></div><span class="live-tag">LOCAL ANALYSIS</span></section>'+
 '<section class="panel diagnostic-toolbar"><div><span class="eyebrow">ANALYSIS WINDOW</span><p class="muted">Findings use recorded samples and best-effort OS events. They identify leads, not proven root causes.</p></div><div class="diagnostic-actions"><label for="diagnostic-window">Window<select id="diagnostic-window" class="flight-select">'+options+'</select></label><button class="secondary-button" type="button" data-action="diagnostic-refresh">↻ Analyze now</button><button class="primary-button" type="button" data-action="export-diagnostic-report">Export report JSON</button></div></section>'+
 '<section class="panel diagnostic-summary"><div><span class="eyebrow">ASSESSMENT</span><h3 id="diagnostic-summary-title">Collecting evidence…</h3><p id="diagnostic-summary-copy" class="muted">Loading telemetry and process-memory observations.</p></div><div class="diagnostic-summary-meta"><span id="diagnostic-sample-count">— samples</span><span id="diagnostic-event-status">OS events: checking</span><span id="diagnostic-generated-at">Not yet analyzed</span></div></section>'+
 '<div class="diagnostic-grid"><section class="panel"><div class="panel-heading"><div><span class="eyebrow">FINDINGS</span><h3>Likely bottlenecks</h3></div><span id="diagnostic-finding-count" class="panel-tag">0 FINDINGS</span></div><div id="diagnostic-findings" class="diagnostic-findings"><p class="empty-state">Analyzing evidence…</p></div></section>'+
 '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">PROCESS MEMORY</span><h3>Growth candidates</h3></div><span class="panel-tag">IN-MEMORY HISTORY</span></div><p class="muted">Tracks resident memory across repeated snapshots. Growth is a clue, not proof of a leak.</p><div id="diagnostic-memory" class="diagnostic-memory"><p class="empty-state">Waiting for repeated process snapshots.</p></div></section></div>'+
 '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">CRASH / HANG CORRELATION</span><h3>Operating-system events</h3></div><span id="diagnostic-correlation-count" class="panel-tag">0 CORRELATIONS</span></div><div id="diagnostic-events" class="diagnostic-events"><p class="empty-state">Checking available local event sources…</p></div></section>'+
 '<section class="panel"><div class="panel-heading"><div><span class="eyebrow">INTERPRETATION</span><h3>Important limitations</h3></div></div><ul id="diagnostic-limitations" class="diagnostic-limitations"><li>Correlation does not prove causation.</li><li>Memory growth alone does not establish a leak.</li></ul></section>'+
 '<p class="table-note">Process-memory history stays in RAM and resets when the API restarts. Reports may include process names, PIDs, and sanitised OS event metadata. Review before sharing.</p>';loadDiagnostics();
}
function diagnosticSeverityClass(s){return s==="critical"?"severity-critical":s==="warning"?"severity-warning":"severity-info";}
function renderDiagnosticResults(data){
 const title=document.getElementById("diagnostic-summary-title");if(!title)return;
 const findings=Array.isArray(data.findings)?data.findings:[],memory=Array.isArray(data.memory_growth)?data.memory_growth:[],events=Array.isArray(data.correlated_events)?data.correlated_events:[];
 document.getElementById("diagnostic-summary-copy").textContent=data.summary||"No summary available.";
 document.getElementById("diagnostic-sample-count").textContent=String(data.sample_count||0)+" samples";
 document.getElementById("diagnostic-event-status").textContent="OS events: "+String(data.event_source_status||"unknown");
 document.getElementById("diagnostic-generated-at").textContent=data.generated_at?"Analyzed "+new Date(data.generated_at).toLocaleTimeString():"Not yet analyzed";
 document.getElementById("diagnostic-finding-count").textContent=findings.length+" FINDING"+(findings.length===1?"":"S");
 document.getElementById("diagnostic-correlation-count").textContent=events.length+" CORRELATION"+(events.length===1?"":"S");
 title.textContent=findings.length?"Review recommended findings":"No strong signal detected";
 document.getElementById("diagnostic-findings").innerHTML=findings.length?findings.map(item=>
  '<article class="diagnostic-finding '+diagnosticSeverityClass(item.severity)+'"><div class="diagnostic-finding-head"><span class="severity-chip">'+escapeHTML(String(item.severity||"info").toUpperCase())+'</span><h4>'+escapeHTML(item.title)+'</h4></div><p>'+escapeHTML(item.summary)+'</p><div class="diagnostic-evidence">'+Object.entries(item.evidence||{}).filter(([k,v])=>typeof v!=="object"&&v!==null).map(([k,v])=>'<span><small>'+escapeHTML(k.replaceAll("_"," "))+'</small><strong>'+escapeHTML(v)+'</strong></span>').join("")+'</div><p class="diagnostic-recommendation"><strong>Next step:</strong> '+escapeHTML(item.recommendation)+'</p><small class="muted">Confidence: '+escapeHTML(item.confidence||"limited")+'</small></article>'
 ).join(""):'<p class="empty-state">No configured pressure threshold or repeated memory-growth signal was found. Intermittent faults can still exist.</p>';
 document.getElementById("diagnostic-memory").innerHTML=memory.length?memory.slice(0,12).map(item=>
  '<article class="diagnostic-memory-row"><div><strong>'+escapeHTML(item.name)+'</strong><small>PID '+Number(item.pid)+' · '+Number(item.samples)+' observations</small></div><div><strong>+'+Number(item.growth_mb).toFixed(1)+' MB</strong><small>'+Number(item.growth_mb_per_minute||0).toFixed(1)+' MB/min · '+escapeHTML(item.confidence)+'</small></div></article>'
 ).join(""):'<p class="empty-state">No process met the repeated-growth threshold yet. Keep NEXUS running and revisit under a comparable workload.</p>';
 document.getElementById("diagnostic-events").innerHTML=events.length?events.map(item=>
  '<article class="diagnostic-event-row"><time>'+escapeHTML(new Date(item.at).toLocaleString())+'</time><strong>'+escapeHTML(item.kind)+'</strong><p>'+escapeHTML(item.summary)+'</p><small class="muted">'+escapeHTML(item.interpretation)+'</small></article>'
 ).join(""):'<p class="empty-state">No crash/hang event was correlated with pressure, or the OS did not expose readable events.</p>';
 document.getElementById("diagnostic-limitations").innerHTML=(Array.isArray(data.limitations)?data.limitations:[]).map(item=>"<li>"+escapeHTML(item)+"</li>").join("");
}
async function loadDiagnostics(){
 const summary=document.getElementById("diagnostic-summary-title");if(!summary)return;summary.textContent="Analyzing evidence…";
 try{const data=await api("/diagnostics?window="+encodeURIComponent(state.diagnosticsWindow||"1h"));state.diagnostics=data;renderDiagnosticResults(data);}
 catch(error){summary.textContent="Diagnostics unavailable";const copy=document.getElementById("diagnostic-summary-copy");if(copy)copy.textContent=error.message+" Check the local API.";const node=document.getElementById("diagnostic-findings");if(node)node.innerHTML='<p class="empty-state error-text">'+escapeHTML(error.message)+'</p>';}
}
async function exportDiagnosticReport(){
 try{const response=await fetch(API_BASE+"/diagnostics/report?window="+encodeURIComponent(state.diagnosticsWindow||"1h"));
 if(!response.ok){let message="Report export failed ("+response.status+")";try{const p=await response.json();if(p.detail)message=p.detail;}catch(_){}throw new Error(message);}
 const blob=await response.blob();downloadRecorderFile("nexus-diagnostics-"+new Date().toISOString().replace(/[:.]/g,"-")+".json",blob);addLog("INFO","Exported diagnostics report.");
 }catch(error){addLog("ERROR","Diagnostics report export failed: "+error.message);window.alert("Could not export diagnostics report: "+error.message);}
}
