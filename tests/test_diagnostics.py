from datetime import datetime, timedelta, timezone
from diagnostics import ProcessMemoryTracker, analyse_diagnostics

def iso(minutes_ago=0):
    return (datetime.now(timezone.utc)-timedelta(minutes=minutes_ago)).isoformat()

def test_analysis_detects_sustained_cpu_and_ram_pressure():
    samples=[{"timestamp":iso(4),"cpu_percent":92,"ram_percent":87,"disk_percent":60},
      {"timestamp":iso(3),"cpu_percent":96,"ram_percent":89,"disk_percent":61},
      {"timestamp":iso(2),"cpu_percent":91,"ram_percent":90,"disk_percent":61},
      {"timestamp":iso(1),"cpu_percent":60,"ram_percent":72,"disk_percent":61}]
    result=analyse_diagnostics(samples,window="1h")
    ids={f["id"] for f in result["findings"]}
    assert "cpu_percent" in ids and "ram_percent" in ids
    assert next(f for f in result["findings"] if f["id"]=="cpu_percent")["evidence"]["peak_percent"]==96
    assert "does not establish causation" in " ".join(result["limitations"])

def test_analysis_correlates_event_by_time_without_claiming_cause():
    samples=[{"timestamp":iso(3),"cpu_percent":93,"ram_percent":40,"disk_percent":30},
      {"timestamp":iso(2),"cpu_percent":95,"ram_percent":40,"disk_percent":30},
      {"timestamp":iso(1),"cpu_percent":92,"ram_percent":40,"disk_percent":30}]
    result=analyse_diagnostics(samples,os_events=[{"at":iso(2),"kind":"process-crash","source":"test","summary":"Crash marker"}],window="1h",event_source_status="available")
    finding=next(f for f in result["findings"] if f["id"]=="event-correlation")
    assert finding["evidence"]["correlations"][0]["nearest_pressure_seconds"]==0
    assert "Temporal correlation only" in finding["evidence"]["correlations"][0]["interpretation"]

def test_analysis_ignores_bad_timestamps_and_rejects_bad_windows():
    result=analyse_diagnostics([{"timestamp":"not-a-date","cpu_percent":99}],window="1h")
    assert result["sample_count"]==0 and "Insufficient" in result["summary"]
    try: analyse_diagnostics([],window="forever"); assert False,"Expected unsupported window"
    except ValueError: pass

def test_process_memory_tracker_reports_repeated_growth_and_can_clear():
    tracker=ProcessMemoryTracker(max_snapshots=10,min_interval_seconds=0);now=datetime.now(timezone.utc)
    for age,rss in [(60,100.0),(30,120.0),(0,180.0)]:
        tracker._snapshots.append({"sampled_at":(now-timedelta(seconds=age)).isoformat(),
          "processes":[{"identity":"321:123.456","pid":321,"name":"test-worker","rss_mb":rss}]})
    growth=tracker.get_growth("1h",now=now)
    assert len(growth)==1 and growth[0]["pid"]==321 and growth[0]["growth_mb"]==80
    tracker.clear();assert tracker.get_growth("1h",now=now)==[]
