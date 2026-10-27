"""Evidence-based, bounded local diagnostics for NEXUS-DASH 2.x."""
from __future__ import annotations
import os, platform, re, threading, time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import psutil
DIAGNOSTICS_VERSION="2.0.0"
PRESSURE_LIMITS={"cpu_percent":85.0,"ram_percent":85.0,"disk_percent":90.0}
WINDOW_SECONDS={"5m":300,"15m":900,"1h":3600,"6h":21600,"24h":86400}
MEMORY_GROWTH_MIN_MB=32.0
MAX_MEMORY_SNAPSHOTS=720
MAX_OS_EVENTS=100

def _parse_time(value:Any)->datetime|None:
    if not isinstance(value,str): return None
    try:
        parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError,ValueError,OverflowError): return None

def _finite(value:Any)->float|None:
    if isinstance(value,bool) or value is None:return None
    try: result=float(value)
    except (TypeError,ValueError,OverflowError):return None
    return result if result==result and result not in (float("inf"),float("-inf")) else None

class ProcessMemoryTracker:
    """Bounded in-memory process RSS history; identities are never written to SQLite."""
    def __init__(self,*,max_snapshots:int=MAX_MEMORY_SNAPSHOTS,min_interval_seconds:float=15.0):
        self.max_snapshots=max(3,int(max_snapshots));self.min_interval_seconds=max(0.0,float(min_interval_seconds))
        self._snapshots:deque[dict[str,Any]]=deque(maxlen=self.max_snapshots)
        self._lock=threading.RLock();self._last_sample_monotonic=0.0
    def sample(self,*,now:datetime|None=None,force:bool=False)->bool:
        mono=time.monotonic()
        with self._lock:
            if not force and mono-self._last_sample_monotonic<self.min_interval_seconds:return False
            self._last_sample_monotonic=mono
        at=(now or datetime.now(timezone.utc)).astimezone(timezone.utc);processes=[]
        try:
            for process in psutil.process_iter(["pid","name","memory_info","create_time"]):
                try:
                    info=process.info;memory=info.get("memory_info");pid=int(info.get("pid") or 0)
                    created=_finite(info.get("create_time"));rss=_finite(getattr(memory,"rss",None))
                    if pid<=0 or created is None or rss is None:continue
                    processes.append({"identity":f"{pid}:{created:.3f}","pid":pid,
                      "name":str(info.get("name") or "Unknown")[:160],"rss_mb":round(max(0.0,rss)/(1024**2),2)})
                except (psutil.Error,OSError,TypeError,ValueError,AttributeError):continue
        except (psutil.Error,OSError):return False
        with self._lock:self._snapshots.append({"sampled_at":at.isoformat(),"processes":processes})
        return True
    def get_growth(self,window:str="1h",*,now:datetime|None=None)->list[dict[str,Any]]:
        if window not in WINDOW_SECONDS:raise ValueError("Unsupported diagnostics window.")
        cutoff=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)-timedelta(seconds=WINDOW_SECONDS[window])
        with self._lock:snapshots=list(self._snapshots)
        observations:dict[str,list[tuple[datetime,dict[str,Any]]]]={}
        for snapshot in snapshots:
            at=_parse_time(snapshot.get("sampled_at"))
            if at is None or at<cutoff:continue
            for process in snapshot.get("processes",[]):observations.setdefault(process["identity"],[]).append((at,process))
        growth=[]
        for values in observations.values():
            if len(values)<3:continue
            values.sort(key=lambda item:item[0]);first_at,first=values[0];last_at,last=values[-1]
            elapsed=(last_at-first_at).total_seconds();delta=float(last["rss_mb"])-float(first["rss_mb"])
            if elapsed<20 or delta<MEMORY_GROWTH_MIN_MB:continue
            growth.append({"pid":int(last["pid"]),"name":str(last["name"]),"first_seen":first_at.isoformat(),
              "last_seen":last_at.isoformat(),"samples":len(values),"initial_mb":round(float(first["rss_mb"]),2),
              "current_mb":round(float(last["rss_mb"]),2),"growth_mb":round(delta,2),
              "growth_mb_per_minute":round(delta/max(elapsed/60,1/60),2),
              "confidence":"limited" if len(values)<5 else "moderate"})
        growth.sort(key=lambda item:item["growth_mb"],reverse=True);return growth[:25]
    def clear(self)->None:
        with self._lock:self._snapshots.clear();self._last_sample_monotonic=0.0

def collect_os_events(window:str="1h",*,now:datetime|None=None)->dict[str,Any]:
    """Read bounded OS crash/hang indicators without invoking a shell."""
    if window not in WINDOW_SECONDS:raise ValueError("Unsupported diagnostics window.")
    current=(now or datetime.now(timezone.utc)).astimezone(timezone.utc);cutoff=current-timedelta(seconds=WINDOW_SECONDS[window])
    events:list[dict[str,Any]]=[];status="unsupported";system=platform.system().lower()
    if system=="windows":
        status="unavailable"
        try:
            import win32evtlog
            handle=win32evtlog.OpenEventLog(None,"Application")
            try:
                flags=win32evtlog.EVENTLOG_BACKWARDS_READ|win32evtlog.EVENTLOG_SEQUENTIAL_READ
                labels={1000:("application-crash","Windows recorded an application fault."),
                  1001:("error-report","Windows recorded an application error report."),
                  1002:("application-hang","Windows recorded an application hang."),
                  1026:("dotnet-crash","Windows recorded a .NET runtime failure.")}
                for _ in range(8):
                    batch=win32evtlog.ReadEventLog(handle,flags,0)
                    if not batch:break
                    for event in batch:
                        event_id=int(event.EventID)&0xFFFF;at=getattr(event,"TimeGenerated",None)
                        if event_id not in labels or at is None:continue
                        at=at.astimezone(timezone.utc)  # naive event-log times are interpreted in the host local timezone
                        if cutoff<=at<=current:
                            kind,summary=labels[event_id];events.append({"at":at.isoformat(),"source":"Windows Application log","kind":kind,"summary":summary,"event_id":event_id})
                status="available"
            finally:win32evtlog.CloseEventLog(handle)
        except ImportError:status="optional-dependency-missing"
        except Exception:status="permission-or-provider-error"
    elif system=="linux":
        patterns=[
          (re.compile(r"\bsegfault\b",re.I),"process-crash","Kernel log contains a segmentation-fault indicator."),
          (re.compile(r"\bout of memory\b|\boom-kill\b|\bkilled process\b",re.I),"memory-pressure","System log contains an out-of-memory or process-kill indicator."),
          (re.compile(r"\bcore dumped\b|\bcore dump\b",re.I),"process-crash","System log contains a core-dump indicator."),
          (re.compile(r"\bblocked for more than\b|\bsoft lockup\b|\bhard lockup\b",re.I),"system-hang","Kernel log contains a stall or lockup indicator.")]
        paths=(Path("/var/log/syslog"),Path("/var/log/messages"),Path("/var/log/kern.log"),Path("/var/log/apport.log"));readable=0
        for path in paths:
            try:
                if not path.is_file():continue
                readable+=1
                with path.open("r",encoding="utf-8",errors="replace") as stream:tail=deque(stream,maxlen=2500)
                for line in tail:
                    match=re.match(r"^([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})",line)
                    if not match:continue
                    try:
                        at=datetime.strptime(match.group(1),"%b %d %H:%M:%S").replace(year=datetime.now().astimezone().year).astimezone(timezone.utc)
                        if at>current+timedelta(days=2):at=at.replace(year=at.year-1)
                    except ValueError:continue
                    if not cutoff<=at<=current:continue
                    for pattern,kind,summary in patterns:
                        if pattern.search(line):events.append({"at":at.isoformat(),"source":path.name,"kind":kind,"summary":summary});break
            except OSError:continue
        status="available" if readable else "no-readable-log-files"
    elif system=="darwin":
        readable=0
        for directory in (Path("/Library/Logs/DiagnosticReports"),Path.home()/"Library/Logs/DiagnosticReports"):
            try:
                if not directory.is_dir():continue
                readable+=1
                for entry in os.scandir(directory):
                    try:
                        if not entry.is_file() or not entry.name.lower().endswith((".crash",".hang",".ips")):continue
                        at=datetime.fromtimestamp(entry.stat().st_mtime,timezone.utc)
                        if cutoff<=at<=current:events.append({"at":at.isoformat(),"source":"DiagnosticReports",
                          "kind":"application-hang" if ".hang" in entry.name.lower() else "process-crash",
                          "summary":"A recent application diagnostic report file was found.","application":entry.name.split(".")[0][:120]})
                    except OSError:continue
            except OSError:continue
        status="available" if readable else "no-readable-diagnostic-report-directory"
    events.sort(key=lambda item:item["at"],reverse=True)
    return {"status":status,"count":min(len(events),MAX_OS_EVENTS),"events":events[:MAX_OS_EVENTS],"source_platform":platform.system()}

def analyse_diagnostics(samples:list[dict[str,Any]],memory_growth:list[dict[str,Any]]|None=None,
 os_events:list[dict[str,Any]]|None=None,*,window:str="1h",now:datetime|None=None,event_source_status:str="unknown")->dict[str,Any]:
    """Summarise observed pressure and temporal correlations without asserting causality."""
    if window not in WINDOW_SECONDS:raise ValueError("Unsupported diagnostics window.")
    current=(now or datetime.now(timezone.utc)).astimezone(timezone.utc);cleaned=[]
    for sample in samples[-2000:]:
        at=_parse_time(sample.get("timestamp") or sample.get("sampled_at"))
        if at is None:continue
        cleaned.append({"at":at,"cpu_percent":_finite(sample.get("cpu_percent")),"ram_percent":_finite(sample.get("ram_percent")),"disk_percent":_finite(sample.get("disk_percent"))})
    cleaned.sort(key=lambda item:item["at"]);cutoff=current-timedelta(seconds=WINDOW_SECONDS[window])
    cleaned=[item for item in cleaned if cutoff<=item["at"]<=current]
    growth=list(memory_growth or [])[:25];events=[e for e in (os_events or [])[:MAX_OS_EVENTS] if _parse_time(e.get("at")) is not None]
    findings=[];pressure_times=[]
    labels={"cpu_percent":("CPU saturation",85.0,"Inspect top CPU processes and compare activity with the expected workload."),
      "ram_percent":("System memory pressure",85.0,"Review memory-growth candidates under a repeatable workload."),
      "disk_percent":("System-volume capacity pressure",90.0,"Check capacity and large files; disk occupancy is not disk I/O latency.")}
    for field,(label,threshold,recommendation) in labels.items():
        values=[(item["at"],item[field]) for item in cleaned if item[field] is not None]
        if not values:continue
        nums=[v for _,v in values];peak=max(nums);average=sum(nums)/len(nums);above=[(at,v) for at,v in values if v>=threshold]
        if not above:continue
        pressure_times.extend(at for at,_ in above);sustained=len(above)>=3 and len(above)/len(values)>=.25
        severity="critical" if sustained and peak>=95 else "warning" if sustained else "info"
        findings.append({"id":field,"severity":severity,"title":label,
          "summary":f"{len(above)} of {len(values)} recorded samples met or exceeded {threshold:.0f}%." if sustained else f"A peak of {peak:.1f}% crossed the {threshold:.0f}% investigation threshold; sustained pressure is not established.",
          "evidence":{"peak_percent":round(peak,1),"average_percent":round(average,1),"threshold_percent":threshold,
            "samples_above_threshold":len(above),"samples_considered":len(values),"first_observed":above[0][0].isoformat(),"last_observed":above[-1][0].isoformat()},
          "recommendation":recommendation,"confidence":"moderate" if sustained and len(values)>=6 else "limited"})
    for item in growth:
        delta=_finite(item.get("growth_mb")) or 0
        if delta<MEMORY_GROWTH_MIN_MB:continue
        pid=int(item.get("pid") or 0);name=str(item.get("name") or "Process")[:120]
        findings.append({"id":f"memory-growth-{pid}","severity":"warning" if delta>=128 else "info","title":"Observed process memory growth",
          "summary":f"{name} (PID {pid}) increased resident memory by {delta:.1f} MB during the observed interval.",
          "evidence":{"pid":pid,"process":name,"growth_mb":round(delta,2),"growth_mb_per_minute":_finite(item.get("growth_mb_per_minute")),
            "initial_mb":_finite(item.get("initial_mb")),"current_mb":_finite(item.get("current_mb")),"samples":int(item.get("samples") or 0)},
          "recommendation":"Repeat under a comparable workload. Growth can be normal caching or workload accumulation; this signal alone does not prove a memory leak.",
          "confidence":str(item.get("confidence") or "limited")})
    correlations=[]
    for event in events:
        at=_parse_time(event.get("at"))
        if at is None:continue
        nearest=min((abs((at-p).total_seconds()) for p in pressure_times),default=None)
        if nearest is not None and nearest<=600:
            correlations.append({"at":at.isoformat(),"kind":str(event.get("kind") or "os-event"),
              "summary":str(event.get("summary") or "OS diagnostic event observed.")[:220],"source":str(event.get("source") or "operating system"),
              "nearest_pressure_seconds":int(nearest),"interpretation":"Temporal correlation only; this does not establish causation."})
    if correlations:findings.append({"id":"event-correlation","severity":"warning","title":"OS event near a resource-pressure interval",
      "summary":f"{len(correlations)} crash, hang, or system-pressure indicator(s) occurred within ten minutes of recorded resource pressure.",
      "evidence":{"correlations":correlations[:20]},"recommendation":"Compare event timestamps with application logs and workload. Timing is a lead, not proof pressure caused the event.","confidence":"limited"})
    rank={"critical":0,"warning":1,"info":2};findings.sort(key=lambda f:(rank.get(f["severity"],3),f["title"]))
    if not cleaned:summary="Insufficient recorded telemetry for this window. Keep the recorder running and try again after more samples arrive."
    elif not findings:summary="No configured pressure threshold or sustained process-memory growth signal was detected. Intermittent or application-specific faults may still exist."
    else:summary=f"{len(findings)} finding(s) need review; highest severity is {findings[0]['severity']}. Recommendations are leads, not automatic fixes."
    return {"version":DIAGNOSTICS_VERSION,"generated_at":current.isoformat(),"window":window,"sample_count":len(cleaned),
      "event_source_status":event_source_status,"summary":summary,"findings":findings,"memory_growth":growth,"correlated_events":correlations[:20],
      "limitations":["Resource thresholds indicate pressure, not root cause.","Temporal correlation does not establish causation.","Process memory increase alone is not proof of a memory leak; compare repeatable workloads.",
        "OS crash/event visibility depends on platform, log availability, optional dependencies, and permissions.",
        "Process-memory history is held in memory only and resets when the API process restarts."]}
